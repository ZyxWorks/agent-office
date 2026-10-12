"""office update: bring every component to the set this release is tested with, through its owner.

`office update --check` only plans. For this checkout (the CLI, preset and meter), each tool in
config/components.toml, Firstmate and the generated config it shows the installed version, the
target, who owns the update, the exact action, what needs a restart afterwards, and what blocks
it. It asks git and each program for versions, asks the remotes for their newest commit
(`git ls-remote`, which fetches nothing) and writes nothing.

`office update` shows that plan, asks, and applies it under a lock, one component at a time:

- this checkout: git, fast-forward only, to the newest commit of the branch it follows. When it
  moved, the rest runs from the new release, with the new release's plan.
- a tool npm owns: `npm install -g --ignore-scripts <package>@<pin>`.
- a tool Homebrew owns: `brew upgrade`, only after Homebrew said it has the target version.
- a tool that updates itself: its own release asset at the pin, SHA-256 checked, over the program
  where its own installer put it. Its `update` command is never run: none of them takes a
  version, each installs its newest, and herdr's can hand a running server over.
- Firstmate: its own updater when the checkout has one and the newest commit of its source is a
  tested revision; otherwise git, fast-forward only, to the tested revision.
- the generated config: what `office install` does.

The target is the pin or tested version in the manifest, never "the latest". A tool with no
version there is left to its owner. Nothing is downgraded, merged, rebased, reset or stashed, and
a program is only ever updated by the one owner its real path names.

It never restarts anything. What a running session, Firstmate or daemon still has to load is
reported as updated on disk but not yet active, with the command for it. Every component ends as
exactly one of updated, unchanged, skipped, failed or pending, and it exits 0 only when all of
them are updated or unchanged. The state folder's update.json records the run as it goes, so a
run that was cut off is reported, and picked up, by the next one.
"""

from __future__ import annotations

import datetime
import fcntl
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config as C
from . import doctor, install, tools
from .tools import Failed

MANIFEST = doctor.MANIFEST
RECORD = "update.json"
LOCK = "update.lock"
OFFICE = "agent-office"
STATES = ("updated", "unchanged", "skipped", "failed", "pending")


class Skipped(Exception):
    """Found out while applying that the owner cannot reach the target. Nothing was changed."""


@dataclass
class Item:
    name: str
    have: str
    target: str
    owner: str
    action: str = ""           # what runs, when run is set
    after: str = ""            # what needs a restart before the update is active
    blocker: str = ""          # why it cannot be updated: it will be skipped
    note: str = ""             # why there is nothing to do
    run: Optional[Callable[[], str]] = None   # returns old -> new, raises Failed or Skipped
    pending: str = ""          # set by run: on disk, and what still runs the old one

    @property
    def kind(self) -> str:
        return "blocked" if self.blocker else "update" if self.run else "ok"


class Checkout:
    """A git checkout: read with git, and moved only by a fast-forward."""

    def __init__(self, path: Path, env):
        self.path = path
        # never a question on the terminal: a remote that wants a password counts as unreachable
        self.env = dict(env, GIT_TERMINAL_PROMPT="0")

    def git(self, *args) -> Optional[str]:
        out = doctor._run(["git", "-C", str(self.path), *args], self.env)
        return None if out is None else out.strip()

    def head(self) -> Optional[str]:
        return self.git("rev-parse", "HEAD") if self.path.is_dir() else None

    def dirty(self) -> int:
        """Tracked files with uncommitted changes. Untracked ones are yours and never in the way:
        git itself refuses a fast-forward that would overwrite one. Without optional locks, so
        that asking does not rewrite the index: --check writes nothing."""
        return len((self.git("--no-optional-locks", "status", "--porcelain", "--untracked-files=no")
                    or "").splitlines())

    def tip(self, remote: str, ref: str) -> Optional[str]:
        """The commit the remote has at ref, asked of the remote itself. Nothing is fetched."""
        out = self.git("ls-remote", remote, ref)
        return out.split()[0] if out else None

    def toward(self, head: str, rev: str, upstream: Optional[str] = None) -> str:
        """How head stands to rev: same, older (a fast-forward reaches rev), newer or diverged."""
        if head == rev:
            return "same"
        if self.git("cat-file", "-e", rev + "^{commit}") is None:
            # rev is not here yet, so head lacks it; commits of its own on top make two histories
            ahead = self.git("rev-list", "--count", f"{upstream}..HEAD") if upstream else "0"
            return "older" if ahead in ("0", None) else "diverged"
        if self.git("merge-base", "--is-ancestor", head, rev) is not None:
            return "older"
        return "newer" if self.git("merge-base", "--is-ancestor", rev, head) is not None else "diverged"

    def forward(self, fetch: list, rev: str) -> str:
        old = self.head()
        tools.call(["git", "-C", str(self.path), *fetch], self.env)
        tools.call(["git", "-C", str(self.path), "merge", "--ff-only", rev], self.env)
        if self.head() != rev:
            raise Failed(f"git did not leave it at {rev[:12]}")
        return f"{old[:12]} -> {rev[:12]}"


class Update:
    def __init__(self, env, out, cfg: dict, comps: dict, plat: str):
        self.env = env
        self.out = out
        self.cfg = cfg
        self.comps = comps
        self.tools = tools.Tools(env, out, plat)
        self.show = doctor.Report(env).show
        self.session = cfg["office"]["session"]
        self.record = C.state_dir(env) / RECORD

    def say(self, line=""):
        print(line, file=self.out)

    # --- the plan, one item per component -----------------------------------------------------

    def plan(self) -> list:
        comps = self.comps.get("component", [])
        return [self.office(),
                *(self.tool(c) for c in comps if c.get("profile") != "workstation"),
                # the workstation tools are optional: the ones you have, as office doctor does
                *(self.tool(c) for c in comps if c.get("profile") == "workstation" and self.tools.which(c["command"])),
                self.firstmate(self.cfg["firstmate"], self.comps.get("firstmate", {})),
                self.config()]

    def _move(self, it: Item, co: Checkout, where: str, action: str, run):
        """An update that moves a checkout forward, or the reason it cannot."""
        dirty = co.dirty()
        if where == "diverged":
            it.blocker = ("it has commits the target does not have (diverged), so it cannot be "
                          "fast-forwarded: Agent Office never merges, rebases or resets a checkout")
        elif where == "newer":
            it.blocker = "it is past the target already: Agent Office never moves a checkout back"
        elif dirty:
            it.blocker = (f"{dirty} tracked file(s) in {self.show(co.path)} have uncommitted changes (dirty): "
                          "commit or stash them, then run this again")
        else:
            it.action, it.run = action, run

    def office(self) -> Item:
        co = Checkout(C.REPO, self.env)
        head = co.head()
        it = Item(OFFICE, head[:12] if head else "unknown", "-", "unknown",
                  after="the meter and the herdr config of a running office session")
        top = co.git("rev-parse", "--show-toplevel") if head else None
        if top is None or not doctor._same(Path(top), C.REPO):
            it.blocker = (f"{self.show(C.REPO)} is not a git checkout, so nothing says how it is updated "
                          "(owner unknown): get the new release the way you got this one")
            return it
        branch = co.git("symbolic-ref", "--short", "-q", "HEAD")
        remote = co.git("config", f"branch.{branch}.remote") if branch else None
        ref = co.git("config", f"branch.{branch}.merge") if branch else None
        if not remote or not ref or remote == ".":
            it.blocker = (f"{'the branch ' + branch if branch else 'a detached HEAD'} follows no remote branch, "
                          "so nothing says where its updates come from (owner unknown)")
            return it
        up = f"{remote}/{ref.replace('refs/heads/', '', 1)}"
        it.owner = f"git, {up}"
        tip = co.tip(remote, ref)
        if tip is None:
            it.blocker = f"the remote {remote} did not answer (offline?), so the newest {up} is unknown"
            return it
        it.target = tip[:12]
        where = co.toward(head, tip, "@{upstream}")
        if where == "newer":
            it.note = f"it has commits {up} does not have yet"
        elif where != "same":
            self._move(it, co, where, f"git fetch {remote} {ref}, then git merge --ff-only {tip[:12]}, "
                       f"in {self.show(C.REPO)}", lambda: co.forward(["fetch", remote, ref], tip))
        return it

    def tool(self, c: dict) -> Item:
        name, cmd, pin, tested = c["name"], c["command"], c.get("pin"), c.get("tested") or []
        target = pin or (tested[-1] if tested else None)
        got = doctor.find(c, self.env)
        if got is None:
            how = ": `office tools` installs it" if {"release", "npm", "brew", "cask"} & c.keys() else ""
            return Item(name, "-", target or "-", "-", blocker=f"{cmd} is not on PATH{how}")
        found, ver, own = got
        real = Path(found).resolve()
        it = Item(name, ver or "unknown", target or "-", doctor.label(own) or "unknown")
        ok = {pin, *tested} - {None}
        if not ok:
            it.note = "no version pinned"
        elif ver is None:
            it.blocker = f"`{cmd} --version` gave no version"
        elif ver in ok:
            pass
        elif tools._vtuple(ver) > tools._vtuple(target):
            it.blocker = (f"{ver} is newer than the target {target}: Agent Office never downgrades, and "
                          "this release is not tested with it")
        elif own is None:
            it.blocker = f"nothing says how {self.show(real)} is updated (owner unknown)"
        elif own[0] == "npm":
            step = self.tools.step(c) if c.get("npm") == own[1] else None
            if step is None:
                it.blocker = f"it comes from the npm package {own[1]}, which is not the one this release pins"
            elif step.kind == "manual":
                it.blocker = step.what
            else:
                it.action, it.run = step.what, step.run
        elif own[0] in ("brew", "cask"):
            flag = "--cask" if own[0] == "cask" else "--formula"
            it.action = f"brew upgrade {flag} {own[1]}, when Homebrew has {target} (asked first)"
            it.run = lambda: self._brew(flag, own[1], ok)
        elif own[0] == "self":
            self._release(it, c, real, pin)
        else:
            it.blocker = f"{doctor.label(own)} own it: update it there"
        if it.run:
            it.after = (f"`{c['restart']}`, for what already runs" if "restart" in c else
                        "a running herdr server" if name == "herdr" else "")
            it.run = self._checked(it, c, it.run, ok)
        return it

    def _release(self, it: Item, c: dict, real: Path, pin):
        # A self-updater takes no version: `herdr update`, `treehouse update` and `no-mistakes
        # update` each install their newest release, which is not the pin, and herdr's can hand a
        # running server over. So the pinned asset goes where the tool's own installer put it,
        # as `office tools` installs it, and only there.
        rel = c.get("release", {})
        asset = rel.get(self.tools.plat)
        dest = C.expand(rel["dir"], self.env) / c["command"] if rel else None
        if not pin or asset is None or not doctor._same(real, dest):
            why = (f"it is at {self.show(real)}, not where its own installer puts it" if asset and pin
                   else f"this release pins no asset of it for {self.tools.plat}")
            it.blocker = (f"{why}, and `{c['update']}` installs its newest version, not the target: "
                          "update it yourself, then run office doctor")
            return
        it.action = (f"its release asset {asset['asset']} at {pin}, SHA-256 checked, over {self.show(dest)} "
                     f"(`{c['update']}` takes no version, so it is not run)")
        it.run = lambda: self.tools._install_release(c, asset, dest, None)

    def _brew(self, flag: str, name: str, ok: set) -> str:
        # Homebrew has one version of a package, its own. Asking first keeps a newer one, which
        # this release is not tested with, from being installed in the name of an update.
        try:
            info = json.loads(doctor._run(["brew", "info", "--json=v2", flag, name], self.env) or "")
            has = info["casks"][0]["version"] if flag == "--cask" else info["formulae"][0]["versions"]["stable"]
        except (ValueError, LookupError, TypeError):
            raise Skipped(f"Homebrew did not say which version of {name} it has")
        if has not in ok:
            raise Skipped(f"Homebrew has {has}, not the target {', '.join(sorted(ok))}: `brew update` "
                          "refreshes what Homebrew knows")
        # without its auto-update, so what it installs is what it just said it has
        tools.call(["brew", "upgrade", flag, name], dict(self.env, HOMEBREW_NO_AUTO_UPDATE="1"))
        return name

    def _checked(self, it: Item, c: dict, run, ok: set):
        """The owner's update, then the version read again: only the target counts as updated."""
        def go():
            run()
            got = doctor.find(c, self.env)
            now = got[1] if got else None
            if now not in ok:
                raise Failed(f"its owner left it at {now or 'no readable version'}, not the target {it.target}")
            if "restart" in c:
                it.pending = f"what already runs keeps {it.have} until you run `{c['restart']}`"
            return f"{it.have} -> {now}"
        return go

    def firstmate(self, fm: dict, spec: dict) -> Item:
        tested = spec.get("tested", [])
        code = C.expand(fm["code"], self.env)
        home = C.expand(fm.get("home", fm["code"]), self.env)
        co = Checkout(code, self.env)
        head = co.head()
        it = Item("firstmate", head[:12] if head else "-", tested[-1][:12] if tested else "-", "unknown",
                  after="a running Firstmate: `fm restart`")
        if head is None:
            it.blocker = (f"no git checkout at {self.show(code)} (firstmate.code): Agent Office does not "
                          "install Firstmate")
            return it
        remote = next((n for n, url in doctor.remotes(code, self.env).items()
                       if url == doctor._norm(fm["source"])), None)
        if remote is None:
            it.blocker = (f"no remote of the checkout is the configured source {doctor._bare(fm['source'])}, "
                          "so nothing says where its updates come from (owner unknown)")
            return it
        it.owner = f"git, {remote} (firstmate.source)"
        if head in tested:
            return it
        if not tested:
            it.blocker = ("no Firstmate revision is tested with this release yet, so there is no target "
                          "(config/components.toml)")
            return it
        tip = co.tip(remote, "HEAD")
        if tip is None:
            it.blocker = f"the remote {remote} did not answer (offline?)"
            return it
        updater = code / spec["update"] if "update" in spec else None
        if updater is None or not updater.is_file() or not os.access(updater, os.X_OK):
            target = tested[-1]
            self._move(it, co, co.toward(head, target), f"git fetch {remote}, then git merge --ff-only "
                       f"{target[:12]}, in {self.show(code)}", lambda: co.forward(["fetch", remote], target))
            return it
        # Firstmate's updater takes no revision: it fast-forwards to the newest commit of origin's
        # default branch, and its registered secondmates with it. So it runs only when that commit
        # is a tested one.
        it.owner = f"Firstmate's own updater ({spec['update']})"
        it.target = tip[:12]
        if remote != "origin":
            it.blocker = f"its own updater pulls origin, and firstmate.source is the remote {remote}"
        elif tip not in tested:
            it.blocker = (f"its own updater goes to the newest commit of its source, {tip[:12]}, which is not "
                          f"a revision this release is tested with (tested: {', '.join(t[:12] for t in tested)})")
        else:
            self._move(it, co, co.toward(head, tip), f"FM_HOME={self.show(home)} {self.show(updater)}",
                       lambda: self._firstmate(co, updater, home, tip))
        return it

    def _firstmate(self, co: Checkout, updater: Path, home: Path, tip: str) -> str:
        old = co.head()
        said = tools.call([str(updater)], dict(self.env, FM_HOME=str(home)), cwd=str(co.path))
        if co.head() != tip:
            last = (said.strip().splitlines() or ["it said nothing"])[-1]
            raise Failed(f"Firstmate's updater left the checkout at {co.head()[:12]}, not {tip[:12]}: {last}")
        return f"{old[:12]} -> {tip[:12]}"

    def config(self) -> Item:
        steps = self._behind()
        it = Item("config", f"{len(steps)} file(s) behind" if steps else "in place",
                  "this release", "office install")
        if steps:
            it.action = "office install --yes: " + ", ".join(
                self.show(s.path) + (" (backed up first)" if s.asks else "") for s in steps)
            it.after = "the herdr config of a running office session"
            it.run = self._install
        return it

    def _behind(self) -> list:
        steps = install.Installer(self.env, self.out).plan(*install.wanted(self.env))
        return [s for s in steps if s.kind not in ("keep", "manual")]

    def _install(self) -> str:
        out, err = io.StringIO(), io.StringIO()
        if install.run(["--yes"], self.env, out, err) != 0 or self._behind():
            raise Failed((err.getvalue() or out.getvalue()).strip() or "office install left files behind")
        return "written by office install"

    def print_plan(self, items: list):
        heads = ("", "", "installed", "target", "owner (updates it)")
        named = [i for i in items if i.kind != "ok" or i.note != "no version pinned"]
        rows = [(i.kind, i.name, i.have, i.target, i.owner) for i in named]
        widths = [max(len(r[n]) for r in [heads, *rows]) for n in range(len(heads))]
        pad = " " * (widths[0] + 4)
        for r, i in zip([heads, *rows], [None, *named]):
            self.say("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
            if i is None:
                continue
            if i.blocker:
                self.say(f"{pad}blocker: {i.blocker}")
            elif i.run:
                self.say(f"{pad}runs: {i.action}")
                self.say(f"{pad}restart: {i.after or 'nothing, the next run uses it'}")
            elif i.note:
                self.say(f"{pad}{i.note}")
        loose = [i.name for i in items if i not in named]
        if loose:
            self.say(f"  {'ok'.ljust(widths[0])}  no version pinned, so their owner decides: {', '.join(loose)}")
        self.say()

    # --- applying it --------------------------------------------------------------------------

    def _save(self, rec: dict):
        install.Installer._write(self.record, (json.dumps(rec, indent=2) + "\n").encode())

    def _one(self, it: Item) -> dict:
        if it.blocker:
            return {"state": "skipped", "detail": it.blocker}
        if it.run is None:
            return {"state": "unchanged", "detail": it.have + (f", {it.note}" if it.note else "")}
        try:
            detail = it.run()
        except Skipped as e:
            return {"state": "skipped", "detail": str(e)}
        except (Failed, OSError) as e:
            return {"state": "failed", "detail": str(e)}
        if it.pending:
            return {"state": "pending", "detail": f"{detail} on disk, not yet active: {it.pending}"}
        return {"state": "updated", "detail": detail}

    def apply(self, items: list, earlier: Optional[dict], again: list) -> int:
        rec = {"schema": 1, "state": "running", "pid": os.getpid(), "repo": str(C.REPO), "current": None,
               "started": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "results": {}}
        # what a run that was cut off had finished stays its result, not this run's "unchanged"
        done = {n: r for n, r in (earlier or {}).get("results", {}).items()
                if isinstance(r, dict) and r.get("state") in ("updated", "pending")}
        self._save(rec)
        for it in items:
            if it.run:
                rec["current"] = it.name
                self._save(rec)
            r = self._one(it)
            if r["state"] == "unchanged" and it.name in done:
                r = {"state": done[it.name]["state"],
                     "detail": done[it.name]["detail"].replace(" (earlier in this update)", "") + " (earlier in this update)"}
            rec["results"][it.name] = r
            rec["current"] = None
            if it.run:
                self._save(rec)
            if it.name == OFFICE and it.run and r["state"] == "updated":
                # The modules in memory and the plan are the old release's. The new one takes over:
                # it reads this record, shows its own plan and asks again unless --yes was given.
                # The lock goes with this process image, and the new one takes it again.
                rec["handoff"] = True
                self._save(rec)
                self.say(f"  updated    {OFFICE}  {r['detail']}")
                self.say("Agent Office itself moved, so the rest runs from the new release.")
                self.say()
                self.out.flush()
                os.execv(sys.executable, [sys.executable, str(C.REPO / "bin" / "office"), "update", *again])

        results = rec["results"]
        for name, why in self.inactive({n for n, r in results.items() if r["state"] == "updated"}).items():
            r = results.get(name)
            if r and r["state"] in ("updated", "unchanged"):
                on_disk = f"{r['detail']} on disk" if r["state"] == "updated" else "on disk"
                results[name] = {"state": "pending", "detail": f"{on_disk}, not yet active: {why}"}
        self.print_results(items, results)
        rec["state"] = "done"
        rec["exit"] = 0 if all(r["state"] in ("updated", "unchanged") for r in results.values()) else 1
        self._save(rec)
        return rec["exit"]

    def inactive(self, changed: set) -> dict:
        """What is on disk but not what the office's running session uses, by component. A
        stopped session runs nothing old; one herdr says nothing about counts for what changed."""
        st = doctor.server_status(self.env, self.session)
        stop = (f"restart the herdr session {self.session} when its agents can stop: `office off`, then "
                "`office on`. office update never does that itself")
        if st is None:
            return {n: f"herdr did not say whether the session {self.session} runs, so it may still run the "
                       "old one" for n in changed & {OFFICE, "herdr", "config", "firstmate"}}
        if not st["running"]:
            return {}
        why = {}
        herdr = next((c for c in self.comps.get("component", []) if c["name"] == "herdr"), None)
        got = doctor.find(herdr, self.env) if herdr else None
        runs = st.get("version")
        if (st.get("restart_needed") or st.get("server_binary_stale") or (runs and got and runs != got[1])
                or (not runs and "herdr" in changed)):
            why["herdr"] = f"the session {self.session} still runs herdr {runs or 'as it started'}: {stop}"
        rep = doctor.Report(self.env)
        rep.active(self.cfg, self.session)
        for p in rep.problems:
            fact, _, said = p.partition(": ")
            name = {"herdr config, active": "config", "meter, active": OFFICE}.get(fact)
            if name:
                why[name] = said
        if "firstmate" in changed:
            why["firstmate"] = ("a running Firstmate keeps the instructions it started with: `fm restart` "
                                "(its hooks and flags: quit it, then `fm`)")
        return why

    def print_results(self, items: list, results: dict):
        self.say("Results:")
        loose = [i.name for i in items if i.note == "no version pinned" and results[i.name]["state"] == "unchanged"]
        width = max(len(n) for n in results)
        for name, r in results.items():
            if name not in loose:
                self.say(f"  {r['state']:<9}  {name.ljust(width)}  {r['detail']}")
        if loose:
            self.say(f"  {'unchanged':<9}  no version pinned, so their owner decides: {', '.join(loose)}")
        count = {s: sum(1 for r in results.values() if r["state"] == s) for s in STATES}
        self.say()
        self.say(", ".join(f"{count[s]} {'updated on disk but not yet active' if s == 'pending' else s}"
                           for s in STATES if count[s]) + ".")


def _held(path: Path) -> bool:
    """Whether a running office update holds the lock. Opened to read: asking writes nothing."""
    try:
        f = open(path)
    except OSError:
        return False
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
    return False


def _unfinished(rec: dict) -> str:
    """What a record that never reached "done" says about its run, for the run that finds it."""
    if rec.get("handoff"):
        return (f"The office update started {rec.get('started')} updated Agent Office itself, so the plan "
                "above is the new release's. `office update` goes on from it.")
    done = [n for n, r in rec.get("results", {}).items()
            if isinstance(r, dict) and r.get("state") in ("updated", "pending")]
    return (f"The last office update (started {rec.get('started')}) was cut off"
            + (f" while it updated {rec['current']}" if rec.get("current") else "") + "."
            + (f" It had updated: {', '.join(done)}." if done else "")
            + " `office update` picks it up: what is at its target stays, the rest is in the plan above.")


def run(args, env=None, out=sys.stdout, err=sys.stderr, manifest: Path = MANIFEST,
        plat: Optional[str] = None) -> int:
    check_only = yes = False
    for a in args:
        if a in ("--check", "-n", "--dry-run"):
            check_only = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a in ("-h", "--help"):
            print(USAGE, file=out)
            return 0
        else:
            print(f"office update: unknown option {a}\n{USAGE}", file=err)
            return 2
    env = dict(os.environ if env is None else env)
    home = str(C.home(env))
    try:
        cfg = C.load(C.config_path(env))
        comps = C.read_toml(manifest, str(manifest))
        u = Update(env, out, cfg, comps, plat or tools.platform_key())
        state = C.state_dir(env)
        busy = _held(state / LOCK)
        if busy and not check_only:
            print("office update: another office update is running for this installation. "
                  "Let it finish, then try again.", file=err)
            return 1
        items = u.plan()
    except C.ConfigError as e:
        print("office update: the config has problems. Fix them first:", file=err)
        for p in e.problems:
            print("  " + p.replace(home, "~"), file=err)
        return 1

    from .cli import VERSION
    print(f"office update{' --check: the plan, and nothing is changed' if check_only else ': the plan'}. "
          "Your home folder is shown as ~.", file=out)
    print(f"Agent Office {VERSION} at {u.show(C.REPO)}, config {u.show(C.config_path(env))}", file=out)
    print(file=out)
    u.print_plan(items)
    prior = C.read_json(u.record)
    unfinished = prior if prior and prior.get("state") == "running" else None
    if busy:
        print("Another office update is running now: this plan is what it started from.", file=out)
    elif unfinished:
        print(_unfinished(unfinished), file=out)
    todo = [i for i in items if i.run]
    blocked = [i for i in items if i.blocker]
    if check_only:
        print(f"{len(todo)} to update, {len(blocked)} blocked. A restart is never done by office update: "
              "it is reported as updated on disk but not yet active, with the command.", file=out)
        return 0
    if todo and not yes and not install._confirm(f"Update {len(todo)} component(s) above? [y/N] "):
        print("office update: not confirmed. Nothing was changed. "
              "Run it in a terminal to answer, or pass --yes.", file=err)
        return 1
    state.mkdir(parents=True, exist_ok=True)
    lock = open(state / LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        print("office update: another office update is running for this installation. "
              "Let it finish, then try again.", file=err)
        return 1
    try:
        return u.apply(items, unfinished, ["--yes"] if yes else [])
    except KeyboardInterrupt:
        # the record still says which component it was on: the next run reports and picks it up
        print("\noffice update: stopped. Run it again to pick it up; `office update --check` shows "
              "where it stopped.", file=err)
        return 130
    finally:
        lock.close()


USAGE = """\
usage: office update [--check] [--yes]

Bring every component to the set this release is tested with, each through its own owner: this
checkout (the CLI, preset and meter) by git, fast-forward only; a tool npm owns by npm at the
pin; one Homebrew owns by `brew upgrade`, when Homebrew has the target; one that updates itself
by its own release asset at the pin, SHA-256 checked; Firstmate by its own updater, or git,
fast-forward only, to a tested revision; the generated config as office install writes it.
The targets are the pins and tested versions in config/components.toml, never "the latest".
A dirty or diverged checkout, an unreachable remote, an unknown owner or a missing tool blocks
that component only. Nothing is downgraded, merged, reset or restarted.

Each component ends as updated, unchanged, skipped, failed, or updated on disk but not yet
active (pending), with the command that activates it. Exit 0 only when all of them are updated
or unchanged. One update runs at a time, and one that was cut off is picked up by the next.

  --check   show the plan, change nothing
  --yes     do not ask first"""
