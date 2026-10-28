"""The optional skill packs: other people's skills, each at the commit config/components.toml pins.

A pack is checked out from its upstream repository at the pinned commit, only the folders it
names (a sparse checkout), into a scratch folder beside its place. Its files are hashed and the
hash must be the one components.toml has before the folder is moved into place. A pin moves only
after the upstream change was read: the files are instructions an agent follows. Nothing in a
pack is ever run by Agent Office.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import config as C

MANIFEST = C.REPO / "config" / "components.toml"


class Failed(Exception):
    pass


def call(argv, env) -> str:
    """Run git to its end and give what it printed; Failed says why it did not work."""
    try:
        r = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        raise Failed(f"`{' '.join(argv)}` did not run: {e}")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        raise Failed(f"`{' '.join(argv)}` failed (exit {r.returncode})" + "".join("\n      " + l for l in tail))
    return r.stdout


def skills(manifest: Path = MANIFEST) -> dict:
    """{name: the [[skill]] entry} from components.toml."""
    return {s["name"]: s for s in C.read_toml(manifest, str(manifest)).get("skill", [])}


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
    """Check skill out at its pinned commit and put it at dest, replacing what is there. Raises
    Failed, and leaves dest as it was, when git fails or the files are not the pinned ones."""
    env = {k: v for k, v in env.items() if not k.startswith("GIT_")}
    tmp = dest.with_name(f".{dest.name}.agent-office-fetch")
    old = dest.with_name(f".{dest.name}.agent-office-old")
    for p in (tmp, old):
        shutil.rmtree(p, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    git = ["git", "-C", str(tmp), "-c", "core.hooksPath=/dev/null"]
    try:
        call(["git", "init", "-q", str(tmp)], env)
        call([*git, "remote", "add", "origin", skill["repo"]], env)
        call([*git, "sparse-checkout", "set", "--cone", "--", *skill["paths"]], env)
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
