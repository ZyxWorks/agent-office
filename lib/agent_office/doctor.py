"""office doctor: what is installed, who updates it, and whether this release is tested with it.

Read-only. It runs each component's own `--version`, asks `herdr integration status` (which reads
files), and reads the Firstmate checkout with git. It talks to no herdr server: what is running
is `office status` (planned). The components and tested versions are data, config/components.toml.

Every problem is listed and makes it exit 1. A version or owner it cannot find out is a problem
too: unknown is not healthy.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as C

MANIFEST = C.REPO / "config" / "components.toml"
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
It starts nothing and talks to no herdr server. Exit 0 only when it finds no problem: a version
or owner it cannot find out counts as a problem."""
