"""office install: show every change, then make it, and keep a backup of anything it replaces.

What it writes, and nothing else:

- your config, ~/.config/agent-office/config.toml, from a starter, only when there is none,
- herdr's config, generated from the preset and your [herdr] keys, under the state folder,
- the meter's settings, your [meter] keys, under the state folder, where the meter plugin reads
  them on every pass,
- the `office`, `fm` and `officeoff-all` commands, links in ~/.local/bin,
- the meter plugin's link in herdr, made by herdr itself (`herdr plugin link`): the sidebar
  numbers and the preset's Shift+arrow come from that plugin,
- with [editor] on, the editor pane's two nvim plugins, checked out at the commits
  config/components.toml pins and checked against their SHA-256,
- and it removes the line that loads the tmux office's (0.x) `office` function from your zsh
  startup files: zsh finds a function before any command on PATH, so while it is loaded the
  1.0 command is never reached.

~/.tmux.conf keeps its tmux office lines: every verb 1.0 has not built yet still runs the tmux
office, and without them its tmux has no prefix, keys or borders.

It starts nothing and never touches your own ~/.config/herdr/config.toml: the generated config
is a separate file, and herdr only uses it once the office starts herdr against it.

Every file it writes is recorded in the state folder's manifest.json with its hash. A file that
still has that hash is ours and is updated without asking; anything else is somebody's work,
so replacing it is shown, backed up and asked about first. A link is never written through: a
startup file that is a link (into a dotfiles repo, say) is left alone and you are told what to
remove from it.
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import config as C
from . import vendors as V

# What bin/install-tmux (the 0.x installer) wrote. The comment lines go only when they sit
# right above the line they explain, so a comment you wrote yourself stays.
LEGACY_ZSH = (
    re.compile(r"^\s*(source|\.)\s+.*/office\.zsh\s*$"),
    "# office — one command for a multi-agent tmux cockpit",
)
ZSH_STARTUP = (".zshenv", ".zprofile", ".zshrc", ".zlogin")
# A shell function or alias named fm hides the fm command the same way. It is your own code, not
# something an installer wrote, so it is only pointed out, never removed.
OWN_FM = re.compile(r"^\s*(function\s+fm\b|fm\s*\(\s*\)|alias\s+fm=)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Step:
    kind: str                  # create | update | replace | edit | manual | keep
    path: Path
    what: str
    run: Optional[Callable[[], None]] = None
    diff: list = field(default_factory=list)
    record: Optional[dict] = None   # the manifest entry once run; None: not ours to record

    @property
    def asks(self) -> bool:
        return self.kind in ("replace", "edit")


class Installer:
    def __init__(self, env=None, out=sys.stdout):
        self.env = dict(os.environ if env is None else env)
        self.home = C.home(self.env)
        self.out = out
        self.state = C.state_dir(self.env)
        self.manifest_path = self.state / "manifest.json"
        self.stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.manifest = self._read_manifest()

    # --- small helpers ------------------------------------------------------------------------

    def show(self, p: Path) -> str:
        s = str(p)
        h = str(self.home)
        return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s

    def say(self, line=""):
        print(line, file=self.out)

    def _read_manifest(self) -> dict:
        try:
            m = json.loads(self.manifest_path.read_text())
            if isinstance(m, dict) and m.get("schema") == 1:
                m.setdefault("owned", {})
                m.setdefault("backups", [])
                return m
        except (OSError, ValueError):
            pass
        return {"schema": 1, "owned": {}, "backups": []}

    def _backup(self, p: Path) -> Path:
        rel = os.path.relpath(p, self.home) if str(p).startswith(str(self.home) + "/") else str(p).lstrip("/")
        dst = self.state / "backups" / self.stamp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        n = 1
        while dst.exists() or dst.is_symlink():  # two runs in one second must not share a backup
            dst = dst.with_name(f"{Path(rel).name}.{n}")
            n += 1
        if p.is_symlink():
            os.symlink(os.readlink(p), dst)
        else:
            shutil.copy2(p, dst)
        self.manifest["backups"].append({"path": str(p), "backup": str(dst), "at": self.stamp})
        return dst

    @staticmethod
    def _write(p: Path, data: bytes, mode: Optional[int] = None):
        # beside the target and renamed over it: a crash leaves the old file or the new one
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.agent-office.tmp")
        tmp.write_bytes(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, p)

    @staticmethod
    def _link(p: Path, target: str):
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.agent-office.tmp")
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        os.symlink(target, tmp)
        os.replace(tmp, p)

    @staticmethod
    def _diff(old: bytes, new: bytes, name: str) -> list:
        try:
            a, b = old.decode().splitlines(), new.decode().splitlines()
        except UnicodeDecodeError:
            return ["(binary file)"]
        d = list(difflib.unified_diff(a, b, f"{name} (now)", f"{name} (after)", lineterm="", n=1))
        return d if len(d) <= 60 else d[:60] + [f"... {len(d) - 60} more diff lines"]

    # --- what we want on disk -----------------------------------------------------------------

    def want_file(self, p: Path, data: bytes, what: str, ours=lambda b: b) -> Step:
        """`ours` takes out of the file what its program put there itself (herdr, in its config)."""
        rec = {"kind": "file", "sha256": _sha(data)}

        def run(backup=False):
            def go():
                if backup:
                    self._backup(p)
                self._write(p, data)
            return go

        if p.is_symlink():
            return Step("replace", p, f"{what} (now a link to {os.readlink(p)})", run(True), record=rec)
        if p.is_dir():
            return Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        if not p.exists():
            return Step("create", p, what, run(), record=rec)
        cur = p.read_bytes()
        if cur == data:
            return Step("keep", p, what, record=rec)
        mine = self.manifest["owned"].get(str(p), {})
        if mine.get("kind") == "file" and mine.get("sha256") in (_sha(cur), _sha(ours(cur))):
            return Step("update", p, what, run(), self._diff(cur, data, p.name), rec)
        why = "changed by hand since it was written" if mine else "not written by Agent Office"
        return Step("replace", p, f"{what} ({why})", run(True), self._diff(cur, data, p.name), rec)

    def want_link(self, p: Path, target: str, what: str) -> Step:
        rec = {"kind": "link", "target": target}

        def run(backup=False):
            def go():
                if backup:
                    self._backup(p)
                self._link(p, target)
            return go

        if p.is_symlink():
            cur = os.readlink(p)
            if cur == target:
                return Step("keep", p, what, record=rec)
            mine = self.manifest["owned"].get(str(p), {})
            if mine.get("kind") == "link" and mine.get("target") == cur:
                return Step("update", p, f"{what} (was a link to {cur})", run(), record=rec)
            return Step("replace", p, f"{what} (now a link to {cur})", run(True), record=rec)
        if p.is_dir():
            return Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        if p.exists():
            return Step("replace", p, f"{what} (now a file not written by Agent Office)", run(True), record=rec)
        return Step("create", p, what, run(), record=rec)

    def legacy(self, p: Path, pattern, comment: str) -> Optional[Step]:
        """The tmux office's lines in one startup file, as a step that removes them."""
        if not p.exists():
            return None
        try:
            raw = p.read_bytes()
            lines = raw.decode().splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return None
        drop = set()
        for i, line in enumerate(lines):
            if pattern.match(line.rstrip("\n")):
                drop.add(i)
                # the installer wrote a blank line, its comment, then this line
                if i >= 1 and lines[i - 1].rstrip("\n") == comment:
                    drop.add(i - 1)
                    if i >= 2 and not lines[i - 2].strip():
                        drop.add(i - 2)
        if not drop:
            return None
        found = [f"line {i + 1}: {lines[i].rstrip()}" for i in sorted(drop)]
        if p.is_symlink():
            return Step("manual", p, f"the tmux office (0.x) function, loaded from a link to {os.path.realpath(p)}. "
                        "Links are never written through: remove these lines yourself", diff=found)
        keep = b"".join(l.encode() for i, l in enumerate(lines) if i not in drop)
        mode = p.stat().st_mode & 0o7777

        def go():
            self._backup(p)
            self._write(p, keep, mode)
        return Step("edit", p, "stop loading the tmux office (0.x) function", go, self._diff(raw, keep, p.name))

    def own_fm(self, p: Path) -> Optional[Step]:
        try:
            lines = p.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            return None
        found = [f"line {i + 1}: {line}" for i, line in enumerate(lines) if OWN_FM.match(line)]
        if not found:
            return None
        return Step("manual", p, "your own fm, which hides the fm command in zsh: "
                    "remove it yourself to use Agent Office's", diff=found)

    def want_plugin(self) -> Step:
        """The meter plugin, linked into herdr by herdr itself: `herdr plugin link`.

        The sidebar numbers and the preset's Shift+arrow both come from it. herdr keeps its own
        copy of the plugin's manifest in plugins.json, so a newer release is linked again, or
        herdr would not know its new actions. A plugin you disabled stays disabled.
        """
        root = C.REPO / "herdr"
        reg = C.herdr_dirs(self.env)[0] / "plugins.json"
        what = "the meter plugin (sidebar numbers, Shift+arrow), linked with `herdr plugin link`"

        def shape(d) -> tuple:
            acts = d.get("actions") if isinstance(d.get("actions"), list) else []
            return d.get("version"), sorted(str(a.get("id")) for a in acts if isinstance(a, dict))

        try:
            with open(root / "herdr-plugin.toml", "rb") as f:
                manifest = C.tomllib.load(f)
            entries = json.loads(reg.read_text()) if reg.exists() else []
            entry = next((e for e in entries if isinstance(e, dict) and e.get("plugin_id") == manifest.get("id")), None)
        except (OSError, ValueError, TypeError) as e:
            return Step("manual", reg, f"{what}: not read ({e}). Run `herdr plugin link {self.show(root)}`")

        def go(backup=False):
            if backup:
                self._backup(reg)
            try:
                got = subprocess.run(["herdr", "plugin", "link", str(root)], env=self.env, capture_output=True,
                                     text=True, stdin=subprocess.DEVNULL, timeout=60)
            except subprocess.TimeoutExpired:
                raise OSError(f"`herdr plugin link {root}` did not answer in 60 seconds") from None
            if got.returncode != 0:
                raise OSError(f"`herdr plugin link {root}` failed: {(got.stderr or got.stdout).strip()}")

        if entry is None:
            return Step("create", reg, what, go)
        there = Path(str(entry.get("plugin_root", "")))
        try:
            same = there.resolve() == root.resolve()
        except (OSError, RuntimeError):
            same = False
        if not same:
            return Step("replace", reg, what, lambda: go(backup=True),
                        diff=[f"herdr links {self.show(there)} now; this release is {self.show(root)}"])
        if shape(entry) == shape(manifest) or not entry.get("enabled", True):
            return Step("keep", reg, what)
        return Step("update", reg, what, go,
                    diff=[f"herdr has version {entry.get('version')}; this release is {manifest.get('version')}"])

    def want_nvim_plugin(self, plugin: dict) -> Step:
        """One of the editor pane's nvim plugins, checked out at its pinned commit. Only nvim in
        the editor pane loads it. One that was changed by hand is left alone."""
        p = C.nvim_pack_dir(self.env) / "pack" / "office" / "opt" / plugin["name"]
        record = {"kind": "nvim-plugin", "commit": plugin["commit"], "paths": plugin["paths"],
                  "sha256": plugin["sha256"]}
        what = (f"the editor pane's nvim plugin {plugin['name']} ({plugin['license']}) from {plugin['repo']} "
                f"at {plugin['commit'][:12]}, checked against its SHA-256")

        def fetch():
            try:
                V.fetch(plugin, p, self.env)
            except V.Failed as e:
                raise OSError(f"{plugin['name']}: {e}") from None

        if not (p.exists() or p.is_symlink()):
            return Step("create", p, what, fetch, record=record)
        rec = self.manifest["owned"].get(str(p), {})
        have = V.head(p, self.env) if p.is_dir() and not p.is_symlink() else None
        if rec.get("kind") != "nvim-plugin" or have is None:
            return Step("manual", p, f"{what}: something Agent Office did not check out is there; "
                        "move it, then run this again")
        if have != rec.get("commit") or V.tree_hash(p, rec.get("paths", [])) != rec.get("sha256"):
            return Step("manual", p, f"{what}: changed by hand since Agent Office checked it out, so it is "
                        f"left as it is. Delete {self.show(p)} and run this again for the pinned one")
        if have == plugin["commit"] and V.tree_hash(p, plugin["paths"]) == plugin["sha256"]:
            return Step("keep", p, what, record=record)
        return Step("update", p, what, fetch, record=record,
                    diff=[f"{have[:12]} -> {plugin['commit'][:12]}: read the change at "
                          f"{plugin['repo']}/compare/{have}...{plugin['commit']}"])

    # --- plan, ask, apply ---------------------------------------------------------------------

    def plan(self, cfg_text: Optional[bytes], herdr_text: str, meter_text: str,
             editor: Optional[dict] = None) -> list:
        steps = []
        cfg = C.config_path(self.env)
        if cfg_text is not None:
            # yours from the moment it exists: recorded so you can see it came from here, never updated
            steps.append(Step("create", cfg, "your config, a starter to edit",
                              lambda: self._write(cfg, cfg_text), record={"kind": "starter"}))
        herdr = self.state / "herdr"
        # herdr's own lines at the top stay: they are its record that you did its first-run setup
        try:
            own = C.herdr_split((herdr / "config.toml").read_text())[0]
        except (OSError, UnicodeDecodeError):
            own = ""
        steps.append(self.want_file(herdr / "config.toml", (own + herdr_text).encode(),
                                    "herdr config, generated from the preset and your [herdr] keys",
                                    ours=lambda b: b[len(own.encode()):]))
        for f in sorted(C.PRESET_SOUNDS.iterdir()):
            steps.append(self.want_file(herdr / "sounds" / f.name, f.read_bytes(), "the preset's sound"))
        steps.append(self.want_file(C.meter_path(self.env), meter_text.encode(),
                                    "meter settings, your [meter] keys, read by the meter plugin"))
        steps.append(self.want_link(self.home / ".local" / "bin" / "office",
                                    str(C.REPO / "bin" / "office"), "the office command"))
        steps.append(self.want_link(self.home / ".local" / "bin" / "fm",
                                    str(C.REPO / "bin" / "fm"), "the fm command"))
        steps.append(self.want_link(self.home / ".local" / "bin" / "officeoff-all",
                                    str(C.REPO / "bin" / "officeoff-all"), "the officeoff-all command"))
        steps.append(self.want_plugin())
        if editor and editor.get("enabled"):
            # only nvim with the office config loads them, but which editor runs is decided in
            # the pane, by your shell's $VISUAL and $EDITOR: so they are there whenever it is on
            steps += [self.want_nvim_plugin(p) for p in V.nvim_plugins().values()]
        # zsh reads ~/.zshenv first, and that is where ZDOTDIR is usually set for the rest
        dirs = [self.home, Path(self.env.get("ZDOTDIR") or self.home)]
        for path in dict.fromkeys(d / n for d in dirs for n in ZSH_STARTUP):
            steps.append(self.legacy(path, *LEGACY_ZSH))
            steps.append(self.own_fm(path))
        return [s for s in steps if s is not None]

    def print_plan(self, steps):
        todo = [s for s in steps if s.kind != "keep"]
        if not todo:
            self.say("Nothing to change. Everything is in place.")
            return
        for s in todo:
            tag = "  [backup first]" if s.asks else ""
            self.say(f"  {s.kind:<8} {self.show(s.path)}{tag}")
            self.say(f"           {s.what}")
            for line in s.diff:
                self.say(f"             {line}")

    def apply(self, steps):
        changed = False
        try:
            for s in steps:
                if s.run is not None and s.kind not in ("keep", "manual"):
                    s.run()
                    changed = True
                if s.record is not None and self.manifest["owned"].get(str(s.path)) != s.record:
                    self.manifest["owned"][str(s.path)] = s.record
                    changed = True
        finally:  # a step that fails must not leave the files written before it off the record
            if changed:
                self.manifest["repo"] = str(C.REPO)
                self._write(self.manifest_path, (json.dumps(self.manifest, indent=2) + "\n").encode())
        return changed


def behind(steps: list) -> list:
    """The steps of a plan that would change a file."""
    return [s for s in steps if s.kind not in ("keep", "manual")]


def ask(prompt: str) -> Optional[str]:
    """The line typed in answer on the terminal, or None when there is no terminal to ask on."""
    try:
        # unbuffered bytes: a terminal cannot seek, and Python refuses to open one for buffered
        # reading and writing, which would read as "no terminal" on every terminal there is
        with open("/dev/tty", "r+b", buffering=0) as tty:
            tty.write(prompt.encode())
            return tty.readline().decode(errors="replace").strip()
    except OSError:
        return None


def _confirm(prompt: str) -> bool:
    return (ask(prompt) or "").lower() in ("y", "yes")


def wanted(env) -> tuple:
    """What the config makes now: the starter when there is no config yet (else None), the herdr
    config, the meter settings and the [editor] keys. Raises ConfigError."""
    cfg_path = C.config_path(env)
    starter = None
    if cfg_path.exists() or cfg_path.is_symlink():  # a broken link is an error, not "no config"
        cfg = C.load(cfg_path)
    else:
        starter = C.STARTER.read_bytes()
        cfg = C.effective(C.tomllib.loads(starter.decode()), str(C.STARTER))
    return starter, C.herdr_config(cfg), C.meter_settings(cfg), cfg["editor"]


def run(args, env=None, out=sys.stdout, err=sys.stderr, outcome: Optional[dict] = None) -> int:
    """outcome, when given, gets "declined": True when the question was answered no."""
    check_only = yes = False
    for a in args:
        if a in ("--check", "-n", "--dry-run"):
            check_only = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a in ("-h", "--help"):
            print(USAGE, file=out)
            return 0
        elif a == "--theme":
            print("office install: --theme is the tmux office's iTerm2 look. "
                  "For the tmux office (0.x) run bin/install-tmux --theme.", file=err)
            return 2
        else:
            print(f"office install: unknown option {a}\n{USAGE}", file=err)
            return 2

    inst = Installer(env, out)
    cfg_path = C.config_path(inst.env)
    try:
        starter, herdr_text, meter_text, editor = wanted(inst.env)
    except C.ConfigError as e:
        print("office install: the config has problems. Nothing was changed.", file=err)
        for p in e.problems:
            print("  " + p.replace(str(inst.home), "~"), file=err)
        return 1
    ok, said = C.herdr_check(herdr_text, inst.env)
    if not ok and said.startswith("herdr is not installed"):
        print(f"office install: {said}. Nothing was changed.", file=err)
        return 1
    if not ok:
        print("office install: herdr does not accept the generated config. Nothing was changed.", file=err)
        for line in said.splitlines():
            print("  " + line, file=err)
        if "unknown config key" in said or "parse error" in said:
            print(f"  Look at the [herdr] keys in {inst.show(cfg_path)}.", file=err)
        return 1

    steps = inst.plan(starter, herdr_text, meter_text, editor)
    inst.say(f"office install{' --check' if check_only else ''}: config {inst.show(cfg_path)}")
    inst.print_plan(steps)
    asks = [s for s in steps if s.asks]
    manual = [s for s in steps if s.kind == "manual"]
    if check_only:
        return 0
    if asks and not yes:
        if not _confirm(f"Replace or edit {len(asks)} file(s) above, backing each up first? [y/N] "):
            if outcome is not None:
                outcome["declined"] = True
            print("office install: not confirmed. Nothing was changed. "
                  "Run it in a terminal to answer, or pass --yes.", file=err)
            return 1

    try:
        inst.apply(steps)
    except OSError as e:
        print(f"office install: {e}. Stopped there: run it again when that is fixed.", file=err)
        return 1
    done = [s for s in steps if s.kind not in ("keep", "manual")]
    if done:
        inst.say(f"Done. Backups and the list of files Agent Office owns: {inst.show(inst.state)}")
    inst.say("herdr accepts the generated config (herdr config check). Nothing was started.")
    if manual:
        inst.say(f"Left for you: {len(manual)} item(s) marked manual above.")
    bin_dir = str(inst.home / ".local" / "bin")
    if bin_dir not in inst.env.get("PATH", "").split(":"):
        inst.say(f"{inst.show(Path(bin_dir))} is not on your PATH. Add it in your shell's startup file:")
        inst.say('  export PATH="$HOME/.local/bin:$PATH"')
    if any(s.kind in ("edit", "manual") and s.path.name.startswith(".z") for s in steps):
        inst.say("A zsh that is already open still has the old office function. Open a new one.")
    return 0


USAGE = """\
usage: office install [--check] [--yes]

Check your config, then write what the office needs, showing every change first:
your config (a starter, only if there is none), herdr's config generated from the preset and
your [herdr] keys, the meter's settings from your [meter] keys, the office, fm and officeoff-all
commands in ~/.local/bin, the meter plugin linked into herdr (`herdr plugin link`), with [editor]
on the editor pane's nvim plugins at their pinned commits, and the line
that loads the tmux office's (0.x) function removed from your zsh startup files. Anything it
replaces or edits is backed up first. It starts nothing and never touches your own
~/.config/herdr/config.toml or ~/.tmux.conf. A running meter reads its new settings on its next
pass; a running herdr needs a restart (or `herdr server reload-config`) to load its new config.

  --check   show what it would do, change nothing
  --yes     do not ask before replacing or editing (backups are still made)"""
