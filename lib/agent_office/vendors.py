"""The optional skill packs and the editor pane's nvim plugins: other people's code, each at the
commit config/components.toml pins.

A pack or plugin is checked out from its upstream repository at the pinned commit, only the folders it
names (a sparse checkout), into a scratch folder beside its place. Its files are hashed and the
hash must be the one components.toml has before the folder is moved into place. A pin moves only
after the upstream change was read: a skill's files are instructions an agent follows, and a
plugin's are code nvim runs. Nothing in a pack is ever run by Agent Office, and a plugin runs only
inside the editor pane's nvim.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import config as C

MANIFEST = C.REPO / "config" / "components.toml"


class Failed(Exception):
    pass


# what points git at another repository than the one -C names: never passed on
_ELSEWHERE = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
              "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")


def _env(env) -> dict:
    """Your environment for git, proxy and certificate settings included, but bound to the pack's
    own repository and never asking for a password: an upstream that is gone fails at once."""
    env = {k: v for k, v in env.items() if k not in _ELSEWHERE}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def call(argv, env) -> str:
    """Run git to its end and give what it printed; Failed says why it did not work."""
    try:
        r = subprocess.run(argv, env=_env(env), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        raise Failed(f"`{' '.join(argv)}` did not run: {e}")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        raise Failed(f"`{' '.join(argv)}` failed (exit {r.returncode})" + "".join("\n      " + l for l in tail))
    return r.stdout


_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_PATH = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")


@functools.lru_cache(maxsize=None)
def _read(manifest: Path, table: str) -> dict:
    data = C.read_toml(manifest, str(manifest)).get(table, [])
    problems, out = [], {}
    for i, s in enumerate(data, 1):
        where = f"{manifest}: {table} {i}"
        for k in ("name", "repo", "license"):
            if not isinstance(s.get(k), str) or not s[k]:
                problems.append(f"{where}: needs {k}")
        if not _HEX40.fullmatch(str(s.get("commit", ""))):
            problems.append(f"{where}: commit must be a full commit hash")
        if not _HEX64.fullmatch(str(s.get("sha256", ""))):
            problems.append(f"{where}: sha256 must be 64 hex digits")
        paths = s.get("paths")
        if not isinstance(paths, list) or not paths or not all(
                isinstance(x, str) and _PATH.fullmatch(x) and ".." not in x.split("/") for x in paths):
            problems.append(f"{where}: paths must be a list of folders inside the repository, say [\"skills\"]")
        out[s.get("name")] = s
    if problems:
        raise C.ConfigError(problems)
    return out


def skills(manifest: Path = MANIFEST) -> dict:
    """{name: the [[skill]] entry} from components.toml, each checked. Raises C.ConfigError."""
    return _read(manifest, "skill")


def nvim_plugins(manifest: Path = MANIFEST) -> dict:
    """{name: the [[nvim_plugin]] entry} from components.toml, each checked. Raises C.ConfigError."""
    return _read(manifest, "nvim_plugin")


def tree_hash(root: Path, paths: list) -> str:
    """The SHA-256 of the files under paths in root: one line per file, its path and its own
    SHA-256, in path order. A link counts as its target's text. A missing path hashes as empty."""
    lines = []
    for top in paths:
        base = root / top
        found = [base] if base.is_file() or base.is_symlink() else sorted(base.rglob("*")) if base.is_dir() else []
        for p in found:
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                lines.append(f"{rel}\0link:{os.readlink(p)}\n")
            elif p.is_file():
                lines.append(f"{rel}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n")
    return hashlib.sha256("".join(sorted(lines)).encode()).hexdigest()


def head(root: Path, env) -> Optional[str]:
    """The commit a checkout is at, or None when it is no checkout."""
    if not (root / ".git").exists():
        return None
    try:
        return call(["git", "-C", str(root), "rev-parse", "HEAD"], env).strip()
    except Failed:
        return None


def fetch(skill: dict, dest: Path, env) -> None:
    """Check a skill or plugin out at its pinned commit and put it at dest, replacing what is there. Raises
    Failed, and leaves dest as it was, when git fails or the files are not the pinned ones."""
    tmp = dest.with_name(f".{dest.name}.agent-office-fetch")
    old = dest.with_name(f".{dest.name}.agent-office-old")
    for p in (tmp, old):
        shutil.rmtree(p, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    git = ["git", "-C", str(tmp), "-c", "core.hooksPath=/dev/null"]
    try:
        call(["git", "init", "-q", str(tmp)], env)
        call([*git, "remote", "add", "origin", skill["repo"]], env)
        # exactly the named folders: cone mode would also check out the files at the root
        call([*git, "sparse-checkout", "set", "--no-cone", "--", *(f"/{x}/" for x in skill["paths"])], env)
        # only the pinned commit, and its file contents only for the folders checked out
        call([*git, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", skill["commit"]], env)
        call([*git, "checkout", "-q", "--detach", "FETCH_HEAD"], env)
        if head(tmp, env) != skill["commit"]:
            raise Failed(f"{skill['repo']} gave another commit than {skill['commit'][:12]}")
        got = tree_hash(tmp, skill["paths"])
        if got != skill["sha256"]:
            raise Failed(f"{skill['name']} at {skill['commit'][:12]} is not the pinned files: SHA-256 {got}, "
                         f"components.toml has {skill['sha256']}")
        if dest.exists() or dest.is_symlink():
            dest.rename(old)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        if old.exists() and not dest.exists():
            old.rename(dest)
        raise
    shutil.rmtree(old, ignore_errors=True)
