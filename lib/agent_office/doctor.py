"""office doctor: what is installed, who updates it, and whether this release is tested with it.

Read-only. It runs each component's own `--version`, asks `herdr integration status` (which reads
files), and reads the Firstmate checkout with git. The components and tested versions are data,
config/components.toml.

Installed is not active, so for the herdr config and the meter it reports both. Installed: what
`office install` wrote, against what your config makes now, and which meter herdr links. Active:
what the office's herdr session runs. herdr reports neither its config nor its plugins' state,
so that comes from the meter plugin's own records: its start hook writes the config the server
started with, and each pass of its loop writes the version and settings it runs with. The one
question it asks herdr is `herdr --session <office.session> status server`, which only answers
whether that server runs and on which socket.

Every problem is listed and makes it exit 1. A version or owner it cannot find out is a problem
too: unknown is not healthy.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as C

MANIFEST = C.REPO / "config" / "components.toml"
METER = C.REPO / "herdr"
METER_ID = "agent-office.meter"
SETTINGS = ("enabled", "interval_seconds", "warn_tokens", "alarm_tokens")
# a dotted version, or a dated build such as WezTerm's 20240203-110809-5046fc22
_VERSION = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}|\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.]+)?")
_SYSTEM = ("/usr/bin/", "/bin/", "/usr/sbin/", "/sbin/")


def _run(argv, env, cwd=None):
    """stdout of a finished command, or None. Never a shell: argv is a list."""
    try:
        r = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def version(cmd: str, env, args=None) -> str | None:
    """The first version in what the program says, on whichever line: eza and ShellCheck put
    their name on the first."""
    out = _run([cmd, *(args or ["--version"])], env)
    m = _VERSION.search(out or "")
    return m.group(0) if m else None


def owner(real: Path, update: str | None) -> str | None:
    """Who updates the program at this real path, from where its owner puts it."""
    parts = real.parts
    for mark, label in (("Cellar", "Homebrew"), ("Caskroom", "Homebrew cask")):
        if mark in parts and parts.index(mark) + 1 < len(parts):
            return f"{label} ({parts[parts.index(mark) + 1]})"
    if "node_modules" in parts:
        # the outermost package is the one installed; any deeper one is its dependency
        i = parts.index("node_modules")
        pkg = parts[i + 1] if i + 1 < len(parts) else ""
        if pkg.startswith("@") and i + 2 < len(parts):
            pkg += "/" + parts[i + 2]
        return f"npm, global ({pkg})"
    if real.parts[1:3] == ("nix", "store"):
        return "Nix"
    if str(real).startswith(_SYSTEM):
        return "the system's packages"
    # not under a package manager: a self-updater owns its own updates; anything else is unknown
    return f"itself ({update})" if update else None


class Report:
    def __init__(self, env):
        self.env = env
        self.home = str(C.home(env))
        # a resolved path names the home through its links (macOS's /var is /private/var)
        self.homes = (self.home, str(Path(self.home).resolve()))
        self.rows = []
        self.facts = []
        self.problems = []

    def show(self, p) -> str:
        s = str(p)
        for h in self.homes:
            if s == h or s.startswith(h + "/"):
                return "~" + s[len(h):]
        return s

    def row(self, name, *cols, problems=()):
        self.rows.append(("ok" if not problems else "PROBLEM", name, *cols))
        self.problems += [f"{name}: {p}" for p in problems]

    def fact(self, name, value, problems=()):
        self.facts.append((name, value))
        self.problems += [f"{name}: {p}" for p in problems]

    def component(self, c: dict):
        name, cmd = c["name"], c["command"]
        found = shutil.which(cmd, path=self.env.get("PATH", ""))
        if not found:
            how = " (`office tools` installs it)" if {"release", "npm", "brew", "cask"} & c.keys() else ""
            self.row(name, "-", "-", "-", problems=[f"{cmd} is not on PATH{how}"])
            return
        real = Path(found).resolve()
        ver, own, problems = version(found, self.env, c.get("version_args")), owner(real, c.get("update")), []
        cask = Path(found).parent.parent / "Caskroom" / c.get("cask", "")
        if own is None and "cask" in c and cask.is_dir():
            # a cask's app lives in /Applications; Homebrew's link to it is what says who owns it
            own = f"Homebrew cask ({c['cask']})"
        if ver is None:
            problems.append(f"`{cmd} --version` gave no version")
        if own is None:
            problems.append(f"nothing says how {self.show(real)} is updated (owner unknown)")
        tested, pin = c.get("tested"), c.get("pin")
        if tested is None and pin:
            compat = "pinned" if ver == pin else "not the pin" if ver else "-"
            if ver and ver != pin:
                problems.append(f"{ver or 'an unknown version'} is not the pinned version {pin}, the one"
                                " read before it was trusted")
        elif tested is None:
            compat = "no version pinned"
        elif ver in tested:
            compat = "tested"
        else:
            compat = "not tested"
            problems.append(f"{ver or 'an unknown version'} is not a version this release is tested with"
                            f" (tested: {', '.join(tested) or 'none yet'})")
        self.row(name, ver or "unknown", own or "unknown", compat, problems=problems)

    def integration(self, harness: str):
        out = _run(["herdr", "integration", "status"], self.env)
        state = None
        for line in (out or "").splitlines():
            if line.startswith(harness + ": "):
                # "claude: current (v10) (<path>)": the state, without the path
                state = line[len(harness) + 2:].rsplit(" (", 1)[0]
        if state is None:
            self.row(f"herdr {harness} integration", "unknown", "herdr", "-",
                     problems=["`herdr integration status` did not report it"])
        elif state.startswith("current"):
            self.row(f"herdr {harness} integration", state, "herdr", "current")
        else:
            self.row(f"herdr {harness} integration", state, "herdr", "-",
                     problems=[f"{state}: `herdr integration install {harness}` installs it"])

    def firstmate(self, fm: dict, tested: list):
        code = C.expand(fm["code"], self.env)
        home = C.expand(fm.get("home", fm["code"]), self.env)
        source = fm["source"]
        rev = _run(["git", "-C", str(code), "rev-parse", "HEAD"], self.env) if code.is_dir() else None
        rev = rev.strip() if rev else None
        problems = []
        if not code.is_dir():
            problems.append(f"no checkout at {self.show(code)} (firstmate.code)")
        elif rev is None:
            problems.append(f"git read no commit in {self.show(code)}")
        remotes = _run(["git", "-C", str(code), "remote", "-v"], self.env) if rev else ""
        urls = {_norm(l.split()[1]) for l in (remotes or "").splitlines() if len(l.split()) > 1}
        if rev and _norm(source) not in urls:
            problems.append(f"no remote of the checkout is the configured source {_bare(source)}")
        if rev and rev not in tested:
            problems.append(f"commit {rev[:12]} is not a revision this release is tested with"
                            f" (tested: {', '.join(t[:12] for t in tested) or 'none yet'})")
        own = "git, from firstmate.source" if rev and _norm(source) in urls else "unknown"
        compat = "-" if not rev else "tested" if rev in tested else "not tested"
        self.row("firstmate", rev[:12] if rev else "unknown", own, compat, problems=problems)
        self.fact("firstmate source", _bare(source))
        self.fact("firstmate code", self.show(code))
        self.fact("firstmate home", self.show(home),
                  problems=[] if home.is_dir() else [f"no folder at {self.show(home)} (firstmate.home)"])

    def treehouse_root(self, th: dict):
        if "root" not in th:
            self.fact("treehouse root", "treehouse's own choice")
            return
        root = C.expand(th["root"], self.env)
        self.fact("treehouse root", self.show(root),
                  problems=[] if root.is_dir() else [f"no folder at {self.show(root)} (treehouse.root)"])

    def installed(self, cfg: dict):
        """What office install wrote, against what your config and this release make now."""
        try:
            herdr = C.herdr_config(cfg)
        except C.ConfigError as e:
            self.fact("herdr config, installed", "unknown", problems=e.problems)
            herdr = None
        for name, path, want in (("herdr config, installed", C.state_dir(self.env) / "herdr" / "config.toml", herdr),
                                 ("meter settings, installed", C.meter_path(self.env), C.meter_settings(cfg))):
            if want is None:
                continue
            try:
                have = path.read_text()
            except (OSError, UnicodeDecodeError):
                have = None
            if have is None:
                self.fact(name, "not written", problems=["not written yet: run `office install`"])
            elif have != want:
                self.fact(name, f"{self.show(path)}, out of date",
                          problems=["older than your config or this release: run `office install`"])
            else:
                self.fact(name, f"{self.show(path)}, matches your config")

    def meter_plugin(self, enabled: bool):
        """The meter herdr links: the folder in its plugins.json, read like herdr reads it."""
        name = "meter plugin, installed"
        here = _plugin_version(METER)
        if not enabled:
            self.fact(name, f"{here or 'unknown'}, not needed: meter.enabled = false")
            return
        try:
            reg = json.loads((C.herdr_dirs(self.env)[0] / "plugins.json").read_text())
            entry = next((p for p in reg if isinstance(p, dict) and p.get("plugin_id") == METER_ID), None)
        except (OSError, ValueError, TypeError):
            entry = None
        link = f"`herdr plugin link {self.show(METER)}`"
        if entry is None:
            self.fact(name, f"{here or 'unknown'}, not linked into herdr",
                      problems=[f"herdr does not link the meter: {link} links it"])
            return
        root = Path(str(entry.get("plugin_root", "")))
        if not _same(root, METER):
            self.fact(name, f"{_plugin_version(root) or 'unknown'} at {self.show(root)}",
                      problems=[f"herdr links {self.show(root)}, not this release's {self.show(METER)}: "
                                f"{link} links it"])
            return
        problems = [] if entry.get("enabled", True) else [f"disabled in herdr: `herdr plugin enable {METER_ID}`"]
        self.fact(name, f"{here or 'unknown'} at {self.show(METER)}, linked into herdr", problems=problems)

    def active(self, cfg: dict, session: str):
        """What the office's herdr session runs. Nothing is active when it is not running."""
        env = {k: v for k, v in self.env.items() if k != "HERDR_SOCKET_PATH"}  # --session picks the socket
        try:
            st = json.loads(_run(["herdr", "--session", session, "status", "server", "--json"], env) or "")
        except ValueError:
            st = None
        name = f"office session {session}"
        if not isinstance(st, dict) or "running" not in st:
            self.fact(name, "unknown", problems=["`herdr status server` did not say whether it runs"])
            return
        if not st["running"]:
            self.fact(name, "not running, so nothing of it is active")
            return
        self.fact(name, "running")
        socket = st.get("socket")
        state = C.herdr_dirs(self.env)[1] / "plugins" / METER_ID
        now = int(datetime.datetime.now().timestamp())

        gen = C.state_dir(self.env) / "herdr" / "config.toml"
        started = _record(state, ".server.json", socket)
        name = "herdr config, active"
        if started is None:
            self.fact(name, "unknown", problems=[
                "no record of the config this session started with: the meter plugin's start hook writes it"])
        elif not _same(Path(str(started.get("herdr_config", ""))), gen):
            self.fact(name, self.show(started.get("herdr_config")), problems=[
                f"the session runs {self.show(started.get('herdr_config'))}, not the generated {self.show(gen)}"])
        elif started.get("sha256") != _sha(gen):
            self.fact(name, f"the generated config as it was when the session started, {_ago(now, started.get('at'))} ago", problems=[
                "the generated config changed after the session started: restart the session to load it "
                "(herdr does not report `herdr server reload-config`, so a reload cannot be confirmed)"])
        else:
            self.fact(name, f"the generated config, as installed (the session started {_ago(now, started.get('at'))} ago)")

        want = {k: cfg["meter"][k] for k in SETTINGS}
        run = _record(state, ".json", socket)
        name = "meter, active"
        if run is None:
            if want["enabled"]:
                self.fact(name, "none", problems=[
                    "no meter has run in this session: link the plugin, then restart the session"])
            else:
                self.fact(name, "none, and none needed: meter.enabled = false")
            return
        got = run.get("settings") or {}
        every = got.get("interval_seconds") if isinstance(got.get("interval_seconds"), int) else 30
        last = run.get("last_pass")
        problems = []
        if not _alive(run.get("pid")) or not isinstance(last, int) or now - last > 3 * every + 10:
            problems.append(f"stopped: its last pass was {_ago(now, last)} ago")
        here = _plugin_version(METER)
        if run.get("version") != here or not _same(Path(str(run.get("root", ""))), METER):
            problems.append(f"it runs {run.get('version') or 'an unknown version'} from "
                            f"{self.show(run.get('root'))}, installed is {here} at {self.show(METER)}: replace "
                            "the running meter (GETTING-STARTED.md, \"Apply meter updates\")")
        if {k: got.get(k) for k in SETTINGS} != want:
            problems.append(f"it runs with {_settings(got)} from {self.show(got.get('source'))}, "
                            f"your config says {_settings(want)}: run `office install`")
        self.fact(name, f"{run.get('version') or 'unknown'}, last pass {_ago(now, last)} ago, "
                        f"{_settings(got)}", problems=problems)

    def print(self, out):
        heads = ("", "", "version", "owner (updates it)", "compatibility")
        widths = [max(len(r[i]) for r in [heads, *self.rows]) for i in range(len(heads))]
        for r in [heads, *self.rows]:
            print("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip(), file=out)
        print(file=out)
        width = max(len(n) for n, _ in self.facts)
        for name, value in self.facts:
            print(f"  {name.ljust(width)}  {value}", file=out)
        print(file=out)
        if not self.problems:
            print("No problems.", file=out)
            return
        print(f"{len(self.problems)} problem(s):", file=out)
        for p in self.problems:
            print("  " + p, file=out)


def _plugin_version(root: Path) -> str | None:
    try:
        with open(root / "herdr-plugin.toml", "rb") as f:
            v = C.tomllib.load(f).get("version")
    except (OSError, C.tomllib.TOMLDecodeError):
        return None
    return v if isinstance(v, str) else None


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError):
        return False


def _sha(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _record(state: Path, suffix: str, socket) -> dict | None:
    """The meter's record for the server on this socket: one file per socket, named by its cksum."""
    for f in sorted(state.glob("meter.*" + suffix)) if socket and state.is_dir() else []:
        if f.name.count(".") != suffix.count(".") + 1:  # meter.<key>.json, not meter.<key>.server.json
            continue
        try:
            rec = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("socket") == socket:
            return rec
    return None


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ago(now: int, then) -> str:
    if not isinstance(then, int):
        return "an unknown time"
    s = max(0, now - then)
    return f"{s}s" if s < 120 else f"{s // 60}m" if s < 7200 else f"{s // 3600}h"


def _settings(m: dict) -> str:
    if m.get("enabled") is False:
        return "the meter off"
    return (f"every {m.get('interval_seconds')}s, ▲ past {m.get('warn_tokens')}, "
            f"▲▲ past {m.get('alarm_tokens')}")


def _bare(url: str) -> str:
    """A URL without a user or token in it, for printing."""
    return re.sub(r"^([a-z+]+://)[^/@]*@", r"\1", url)


def _norm(url: str) -> str:
    u = url.strip().rstrip("/")
    return u[:-4] if u.endswith(".git") else u


def run(args, env=None, out=sys.stdout, err=sys.stderr, manifest: Path = MANIFEST) -> int:
    if args in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    if args:
        print(f"office doctor: unknown option {args[0]}\n{USAGE}", file=err)
        return 2
    env = dict(os.environ if env is None else env)
    rep = Report(env)
    path = C.config_path(env)
    try:
        cfg = C.load(path)
        comps = C.read_toml(manifest, str(manifest))
    except C.ConfigError as e:
        print("office doctor: the config has problems. Fix them first:", file=err)
        for p in e.problems:
            print("  " + p.replace(rep.home, "~"), file=err)
        return 1

    print("office doctor: read-only. Your home folder is shown as ~.", file=out)
    print(f"Agent Office {_office_version()} at {rep.show(C.REPO)}, "
          f"config {rep.show(path)}{'' if path.exists() else ' (not there: the defaults)'}", file=out)
    print(file=out)
    extra = [c for c in comps.get("component", []) if c.get("profile") == "workstation"]
    for c in comps.get("component", []):
        if c not in extra:
            rep.component(c)
    # the workstation tools are optional: the ones you have are checked, the rest not missed
    have = [c for c in extra if shutil.which(c["command"], path=env.get("PATH", ""))]
    for c in have:
        rep.component(c)
    harness = cfg["firstmate"]["harness"]
    for h in comps.get("harness", []):
        if h["name"] == harness:
            rep.component(h)
    rep.integration(harness)
    rep.firstmate(cfg["firstmate"], comps.get("firstmate", {}).get("tested", []))
    rep.treehouse_root(cfg.get("treehouse", {}))
    if extra:
        rep.fact("workstation tools", f"{len(have)} of {len(extra)} installed"
                 + ("" if len(have) == len(extra) else " (optional: `office tools --workstation`)"))
    rep.installed(cfg)
    rep.meter_plugin(cfg["meter"]["enabled"])
    rep.active(cfg, cfg["office"]["session"])
    rep.print(out)
    return 1 if rep.problems else 0


def _office_version() -> str:
    from .cli import VERSION
    return VERSION


USAGE = """\
usage: office doctor

Read-only. For each component: the installed version, who updates it (a package manager or the
tool itself) and whether this release is tested with that version, or it is the pinned one
(config/components.toml). Of the optional workstation tools, the ones you have.
Also herdr's integration for your harness, and your Firstmate source, checkout and home.
For the herdr config and the meter it shows what is installed and, when the office's herdr
session runs, what is active in it: an update on disk is not active until the session loads it.
It starts nothing and changes nothing. Exit 0 only when it finds no problem: a version, owner or
state it cannot find out counts as a problem."""
