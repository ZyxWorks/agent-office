"""office tools: install the tools the office uses that are missing, each one through its owner.

The tools and how each installs are data, config/components.toml, the same list office doctor
checks. A tool you already have is adopted as it is: never replaced, updated or moved, whatever
its version. office doctor says when that version is not the pinned one.

How a missing tool is installed:

- a GitHub release: the owner's asset at the pinned version, downloaded to a scratch folder and
  checked against the SHA-256 in the manifest before anything is unpacked, then put where the
  owner's own installer puts it, so the tool's own `update` keeps working. Nothing downloaded is
  ever run by a shell, and nothing is installed with sudo.
- npm: `npm install -g --ignore-scripts <package>@<pin>`, so no package's install scripts run.
- Homebrew: `brew install`. Homebrew owns those versions.

Every command is an argument list, never a shell line. Each install is checked afterwards: the
command must be on PATH (or where it went) and report the pinned version.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config as C
from . import doctor
from .install import _confirm

MANIFEST = doctor.MANIFEST
MAX_DOWNLOAD = 100_000_000  # bytes; the largest pinned asset is under 30 MB
_ARCH = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}


def platform_key() -> str:
    return f"{platform.system().lower()}-{_ARCH.get(platform.machine().lower(), platform.machine())}"


def fetch(url: str, dest: Path, env) -> None:
    """Download url to dest: https only, bounded. curl, as an argument list, never piped anywhere."""
    subprocess.run(["curl", "-fsSL", "--proto", "=https", "--max-filesize", str(MAX_DOWNLOAD),
                    "-o", str(dest), url], env=env, check=True, stdin=subprocess.DEVNULL,
                   capture_output=True, timeout=600)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _node_version(env) -> Optional[tuple]:
    out = doctor._run(["node", "--version"], env)
    return _vtuple(out.strip().lstrip("v")) if out else None


def _vtuple(v: str) -> tuple:
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


class Failed(Exception):
    pass


@dataclass
class Step:
    kind: str                 # install | manual
    name: str
    what: str
    run: Optional[Callable[[], str]] = None   # returns where it went, raises Failed


class Tools:
    def __init__(self, env, out, plat: str):
        self.env = env
        self.out = out
        self.plat = plat
        self.home = C.home(env)
        self.path = env.get("PATH", "")

    def show(self, p) -> str:
        s, h = str(p), str(self.home)
        return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s

    def which(self, cmd: str) -> Optional[str]:
        return shutil.which(cmd, path=self.path)

    # --- the plan, one step per missing tool --------------------------------------------------

    def step(self, c: dict) -> Step:
        name, cmd, pin = c["name"], c["command"], c.get("pin")
        if "release" in c:
            return self._release(c)
        if "npm" in c:
            if not self.which("npm") or not self.which("node"):
                return Step("manual", name, f"needs Node {c['node']} or newer with npm; install Node, "
                            "then run this again")
            have = _node_version(self.env)
            if have is None or have < _vtuple(c["node"]):
                got = ".".join(map(str, have)) if have else "an unknown version"
                return Step("manual", name, f"needs Node {c['node']} or newer; this Node is {got}")
            argv = ["npm", "install", "-g", "--ignore-scripts", f"{c['npm']}@{pin}"]
            return Step("install", f"{name} {pin}", " ".join(argv), lambda: self._command(argv, c))
        if "brew" in c or "cask" in c:
            cask = "cask" in c
            if cask and not self.plat.startswith("darwin"):
                return Step("manual", name, "a macOS app from Homebrew; install it with your system's own way")
            if not self.which("brew"):
                return Step("manual", name, f"install `{c.get('brew') or c['cask']}` with your package manager "
                            "(there is no Homebrew here)")
            argv = ["brew", "install", *(["--cask", c["cask"]] if cask else [c["brew"]])]
            return Step("install", name, " ".join(argv), lambda: self._command(argv, c))
        return Step("manual", name, f"office tools does not install {cmd}")

    def _release(self, c: dict) -> Step:
        name, cmd, pin, rel = c["name"], c["command"], c["pin"], c["release"]
        asset = rel.get(self.plat)
        if asset is None:
            return Step("manual", name, f"no pinned release for {self.plat}; install it the way its "
                        "own docs say")
        dest = C.expand(rel["dir"], self.env) / cmd
        link = C.expand(rel["link"], self.env) / cmd if "link" in rel else None
        for p in filter(None, (dest, link)):
            if p.exists() or p.is_symlink():
                return Step("manual", name, f"{self.show(p)} is there but not on PATH: add "
                            f"{self.show(p.parent)} to PATH")
        where = f"{self.show(dest)}" + (f", linked from {self.show(link)}" if link else "")
        return Step("install", f"{name} {pin}",
                    f"the release asset {asset['asset']}, SHA-256 checked, to {where}",
                    lambda: self._install_release(c, asset, dest, link))

    # --- doing it -----------------------------------------------------------------------------

    def _install_release(self, c, asset, dest: Path, link: Optional[Path]) -> str:
        cmd = c["command"]
        with tempfile.TemporaryDirectory(prefix="agent-office-tools.") as tmp:
            got = Path(tmp) / asset["asset"]
            try:
                fetch(c["release"]["url"] + asset["asset"], got, self.env)
            except (OSError, subprocess.SubprocessError) as e:
                raise Failed(f"download failed: {getattr(e, 'stderr', '') or e}".strip())
            sha = _sha256(got)
            if sha != asset["sha256"]:
                raise Failed(f"{asset['asset']} is not the pinned file: SHA-256 {sha}, "
                             f"expected {asset['sha256']}. Nothing was installed.")
            data = _unpack(got, cmd)
        # beside the target and renamed over it, executable before it appears
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = dest.with_name(f".{cmd}.agent-office.tmp")
        tmp_dest.write_bytes(data)
        os.chmod(tmp_dest, 0o755)
        os.replace(tmp_dest, dest)
        if link is not None:
            link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(dest, link)
        self._verify(c, str(dest))
        return self.show(link or dest)

    def _command(self, argv, c) -> str:
        try:
            r = subprocess.run(argv, env=self.env, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=1800)
        except (OSError, subprocess.SubprocessError) as e:
            raise Failed(f"`{' '.join(argv)}` did not run: {e}")
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-5:]
            raise Failed(f"`{' '.join(argv)}` failed (exit {r.returncode})" +
                         "".join("\n      " + line for line in tail))
        found = self.which(c["command"])
        if not found:
            raise Failed(f"installed, but {c['command']} is not on PATH. Add the folder "
                         f"{argv[0]} installs programs to, then run office doctor")
        self._verify(c, found)
        return self.show(found)

    def _verify(self, c, path: str):
        pin = c.get("pin")
        ver = doctor.version(path, self.env, c.get("version_args"))
        if pin and ver != pin:
            raise Failed(f"installed, but `{c['command']} --version` says {ver or 'nothing'}, not {pin}")


def _unpack(archive: Path, cmd: str) -> bytes:
    """The program from a release asset: the file itself, or the one regular file named cmd
    at the top of a .tar.gz. Only read, never extracted to disk, so no path in it is followed."""
    if not archive.name.endswith((".tar.gz", ".tgz")):
        return archive.read_bytes()
    try:
        with tarfile.open(archive, "r:gz") as tar:
            m = next((m for m in tar.getmembers() if m.isfile() and m.name in (cmd, "./" + cmd)), None)
            if m is None:
                raise Failed(f"{archive.name} has no {cmd} at its top")
            return tar.extractfile(m).read()
    except tarfile.TarError as e:
        raise Failed(f"{archive.name} is not a readable archive: {e}")


def run(args, env=None, out=sys.stdout, err=sys.stderr, manifest: Path = MANIFEST,
        plat: Optional[str] = None) -> int:
    check_only = yes = workstation = False
    for a in args:
        if a in ("--check", "-n", "--dry-run"):
            check_only = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--workstation":
            workstation = True
        elif a in ("-h", "--help"):
            print(USAGE, file=out)
            return 0
        else:
            print(f"office tools: unknown option {a}\n{USAGE}", file=err)
            return 2
    env = dict(os.environ if env is None else env)
    try:
        comps = C.read_toml(manifest, str(manifest)).get("component", [])
    except C.ConfigError as e:
        print("\n".join(["office tools: cannot read the tool list", *e.problems]), file=err)
        return 1
    t = Tools(env, out, plat or platform_key())
    wanted = [c for c in comps if workstation or c.get("profile") != "workstation"]
    have = [c for c in wanted if t.which(c["command"])]
    steps = [t.step(c) for c in wanted if not t.which(c["command"])]

    scope = "the agent toolkit" + (" and the workstation tools" if workstation else "")
    print(f"office tools{' --check' if check_only else ''}: {scope}, {len(have)} of {len(wanted)} "
          "already installed and left as they are.", file=out)
    if not steps:
        print("Nothing to install. office doctor checks the versions and who updates each.", file=out)
        return 0
    width = max(len(s.name) for s in steps)
    for s in steps:
        print(f"  {s.kind:<8} {s.name.ljust(width)}  {s.what}", file=out)
    todo = [s for s in steps if s.kind == "install"]
    manual = [s for s in steps if s.kind == "manual"]
    if check_only:
        return 0
    if todo and not yes and not _confirm(f"Install {len(todo)} tool(s) above? [y/N] "):
        print("office tools: not confirmed. Nothing was installed. "
              "Run it in a terminal to answer, or pass --yes.", file=err)
        return 1

    failed = 0
    for s in todo:
        try:
            where = s.run()
            print(f"  ok       {s.name.ljust(width)}  {where}", file=out)
        except (Failed, OSError) as e:
            failed += 1
            print(f"  FAILED   {s.name.ljust(width)}  {e}", file=out)
    if manual:
        print(f"Left for you: {len(manual)} tool(s) marked manual above.", file=out)
    if failed:
        print(f"{failed} install(s) failed.", file=out)
    print("Run office doctor to check every version and who updates each tool.", file=out)
    return 1 if failed or manual else 0


USAGE = """\
usage: office tools [--check] [--yes] [--workstation]

Install the tools the office uses that are missing: herdr, treehouse, no-mistakes, jq, gh and
the agent CLIs (gh-axi, chrome-devtools-axi and -mcp, lavish-axi, quota-axi, tasks-axi, gnhf,
backpass, acpx). Each at a pinned version that was read before it was trusted, through its own
owner: the owner's GitHub release checked against a pinned SHA-256, npm with --ignore-scripts,
or Homebrew. Never a script piped into a shell, never sudo. A tool you have is left as it is.
The list is config/components.toml; office doctor checks the result.

  --check         show what it would install, install nothing
  --yes           do not ask first
  --workstation   also the generic command-line tools: git, ripgrep, fd, fzf, bat, eza, delta,
                  lazygit, neovim, micro, starship, zoxide, tmux, WezTerm and more (Homebrew)"""
