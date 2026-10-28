"""office open: jump to a project's herdr space in the office session, or make one.

The projects are the ones Firstmate has registered (data/projects.md in its home, each cloned in
projects/<name>) and every git checkout directly inside an [open] root. The registry is only
read: Firstmate owns it, and its own commands add and remove projects.

A space is the project's when herdr shows it with the project's name as its label and one of
its panes is in the project's folder. The label alone is not enough: a space you named by hand
can sit anywhere. Nothing is ever closed or renamed: a space that does not match is left alone,
and a new one is made beside it.

With no project named, fzf picks one. A name that is exactly one project's opens it without a
picker, so a key binding or a script can name it.
"""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
from pathlib import Path

from . import config as C
from . import fm

USAGE = """\
usage: office open [<project> | <folder>]
       office open --list

office open jumps to the project's space in the office's herdr session, or makes one there with
its first pane in the project, and attaches when this terminal is outside herdr. With no
project named, fzf picks one; a name that matches several does the same, typed in. A folder
(`office open .`, `office open ~/code/x`) opens that folder.

The projects: the ones Firstmate has registered (data/projects.md in firstmate.home) that are
cloned, and every git checkout directly inside a folder in open.roots. --list prints them.
Inside the office, prefix+f opens the same picker in a popup."""

# `- <name> [<mode> ...] - <desc>` or the legacy `- <name> - <desc>`: Firstmate's own format,
# read the way bin/fm-project-mode.sh reads it (the name ends at the first " [" or " - ")
_ENTRY = re.compile(r"- (.+?)(?: \[| - )")


class Project:
    def __init__(self, name: str, path: Path, kind: str):
        self.name, self.path, self.kind = name, path, kind


def _registered(home: Path) -> tuple[list, list]:
    """Firstmate's projects, and the names it registers that have no clone yet."""
    try:
        lines = (home / "data" / "projects.md").read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return [], []
    got, missing = [], []
    for line in lines:
        m = _ENTRY.match(line)
        name = m.group(1).strip() if m else ""
        if not name or "/" in name or name.startswith("."):
            continue
        path = home / "projects" / name
        if path.is_dir():
            got.append(Project(name, path, "firstmate"))
        else:
            missing.append(name)
    return got, missing


def _in_roots(roots: list) -> list:
    got = []
    for root in roots:
        try:
            kids = sorted(root.iterdir())
        except OSError:
            continue
        got += [Project(k.name, k, "root") for k in kids
                if not k.name.startswith(".") and k.is_dir() and (k / ".git").exists()]
    return got


def projects(cfg: dict, env) -> tuple[list, list]:
    """Every project to pick from, registered ones first, one per folder; and the registered
    names with no clone."""
    fmc = cfg["firstmate"]
    home = C.expand(fmc.get("home") or fmc["code"], env)
    mine, missing = _registered(home)
    seen, out = set(), []
    for p in mine + _in_roots([C.expand(r, env) for r in cfg["open"]["roots"]]):
        real = os.path.realpath(p.path)
        if real not in seen:
            seen.add(real)
            out.append(p)
    return out, missing


def _tilde(p: Path, env) -> str:
    h = str(C.home(env))
    s = str(p)
    return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s


def _lines(found: list, env) -> list:
    w = max(len(p.name) for p in found)
    return [f"{p.name:<{w}}  {p.kind:<9}  {_tilde(p.path, env)}" for p in found]


def _pick(found: list, query: str, env) -> Project | None:
    """fzf over found. None when the picker was cancelled; Fail when nothing matches."""
    rows = [f"{i}\t{line}" for i, line in enumerate(_lines(found, env))]
    try:
        r = subprocess.run(["fzf", "--delimiter=\t", "--with-nth=2..", "--prompt=open> ",
                            "--height=~60%", "--layout=reverse", "--select-1", "--exit-0",
                            "--query", query], input="\n".join(rows) + "\n",
                           stdout=subprocess.PIPE, text=True, env=env)
    except FileNotFoundError:
        raise fm.Fail("fzf is not installed, so there is no picker: name the project "
                      "(`office open --list` shows them), or install fzf (`office tools --workstation`).")
    if r.returncode == 130:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        raise fm.Fail(f"no project matches '{query}'. `office open --list` shows them.")
    return found[int(r.stdout.split("\t", 1)[0])]


def _here(env) -> Path:
    """The folder this runs in as the shell names it: $PWD keeps a linked folder's own name,
    where the operating system's answer has every link resolved."""
    pwd = env.get("PWD", "")
    try:
        if pwd.startswith("/") and os.path.samefile(pwd, "."):
            return Path(pwd)
    except OSError:
        pass
    return Path(os.getcwd())


def choose(found: list, missing: list, arg: str | None, env) -> Project | None:
    if arg is not None and (arg in (".", "..") or "/" in arg or arg.startswith("~")):
        path = C.expand(arg, env) if arg.startswith("~") else Path(arg)
        if not path.is_absolute():
            path = _here(env) / path
        path = Path(os.path.normpath(path))
        if not path.is_dir():
            raise fm.Fail(f"no folder at {path}")
        return Project(path.name or str(path), path, "folder")
    if arg is not None:
        exact = [p for p in found if p.name == arg]
        if len(exact) == 1:
            return exact[0]
        if not exact and arg in missing:
            raise fm.Fail(f"Firstmate registers '{arg}' but has no clone of it in its projects/ folder "
                          "yet. Ask Firstmate to set it up, then run office open again.")
    if not found:
        raise fm.Fail("no projects to open: Firstmate has registered none that are cloned, and "
                      "open.roots names no folder with git checkouts in it. See `office open --help`.")
    if sys.stdin.isatty():
        return _pick(found, arg or "", env)
    # no terminal for a picker: only a unique match opens
    near = [p for p in found if arg and arg.lower() in p.name.lower()]
    if len(near) == 1:
        return near[0]
    shown = "\n".join("  " + line for line in _lines(near or found, env))
    what = f"'{arg}' matches {len(near)} projects" if near else \
        (f"no project matches '{arg}'" if arg else "no project named and no terminal for the picker")
    raise fm.Fail(f"{what}:\n{shown}")


def _inside(path: Path, cwd: str) -> bool:
    if not cwd:
        return False
    try:
        a, b = os.path.realpath(cwd), os.path.realpath(path)
    except OSError:
        return False
    return a == b or a.startswith(b.rstrip("/") + "/")


def space(h: fm.Herdr, p: Project) -> dict | None:
    """The project's space in the session: its label is the name and a pane of it is in the
    folder. The first one herdr numbers, when there are two."""
    spaces = [w for w in h.call("workspace", "list").get("workspaces", []) if w.get("label") == p.name]
    if not spaces:
        return None
    panes = h.call("pane", "list").get("panes", [])
    held = {x.get("workspace_id") for x in panes
            if _inside(p.path, x.get("cwd") or "") or _inside(p.path, x.get("foreground_cwd") or "")}
    mine = [w for w in spaces if w.get("workspace_id") in held]
    return min(mine, key=lambda w: w.get("number") or 0) if mine else None


def _lock(env):
    """Two quick presses of the key must make one space, not two: the second waits."""
    d = C.state_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / "open.lock", "w")
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def go(o: fm.Office, p: Project, env, out) -> dict:
    srv = o.running()
    lock = _lock(env)
    try:
        w = space(o.herdr, p)
        if w:
            o.herdr.call("workspace", "focus", w["workspace_id"])
            print(f"office open: {p.name}: went to its space ({w['workspace_id']}).", file=out)
        else:
            made = o.herdr.call("workspace", "create", "--cwd", str(p.path), "--label", p.name, "--focus")
            wid = (made.get("workspace") or {}).get("workspace_id", "?")
            print(f"office open: {p.name}: made a space for it ({wid}) in {_tilde(p.path, env)}.", file=out)
    finally:
        lock.close()
    return srv


def run(args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    listing = args[:1] == ["--list"]
    rest = args[1:] if listing else args
    if len(rest) > (0 if listing else 1) or (rest and rest[0].startswith("-")):
        print(f"office open: takes one project, or --list\n{USAGE}", file=err)
        return 2
    path = C.config_path(env)
    try:
        cfg = C.load(path)
    except C.ConfigError as e:
        print(f"office open: problems in {path}:", file=err)
        for x in e.problems:
            print("  " + x, file=err)
        return 1
    found, missing = projects(cfg, env)
    if listing:
        for line in _lines(found, env) if found else []:
            print(line, file=out)
        for name in missing:
            print(f"{name}  (registered with Firstmate, not cloned yet)", file=out)
        return 0
    o = fm.Office(cfg, env, "office open")
    client = None
    try:
        p = choose(found, missing, rest[0] if rest else None, env)
        if p is None:
            return 130
        client = fm._show(o, go(o, p, env, out), out, "the project")
        if client:
            fm.note_client(o)
    except (fm.Fail, fm.HerdrError) as e:
        print(f"office open: {e}", file=err)
        return 1
    if client:
        fm.attach(client, env)
    return 0
