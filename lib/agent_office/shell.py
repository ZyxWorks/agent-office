"""Whether your zsh hides the office or fm command, asked of zsh itself. Read-only.

zsh finds a function or an alias before any command on PATH, so a shell that defines `office` or
`fm` never reaches Agent Office's. A text scan of the startup files cannot see every way a shell
defines one: a file that another file sources, a path built at run time, a quote at the end of
the line. So this starts the zsh you would get in a new terminal, an interactive login shell with
your own HOME and ZDOTDIR, and asks it with `whence -w`. zsh's source trace says which files it
read, so a function can be traced back to the line that loaded it.

Nothing here edits a file. `office install` still removes the one loader line it knows, the tmux
office's (install.LEGACY_ZSH); everything else is your own code, and you are told where it is.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

NAMES = ("office", "fm")
SECONDS = 20
MARK = "@@agent-office-whence@@"
# One line per name: the name, what whence -w says it is, and for a function the file zsh read it from
_ASK = (f"print -r -- {MARK}\n"
        "for n in " + " ".join(NAMES) + "; do\n"
        "  print -r -- \"$n\t$(whence -w -- $n)\t${functions_source[$n]-}\"\n"
        "done\n")
_TRACE = re.compile(r"^\+(.+):\d+> <sourcetrace>$")


class Unknown(Exception):
    """zsh did not answer, so whether a name is hidden is not known."""


@dataclass
class Shadow:
    name: str
    kind: str                                    # function | alias
    where: Optional[Path]                        # the file that defines it, when zsh or a scan says
    line: Optional[int] = None                   # its definition's line in that file
    text: str = ""
    loader: Optional[tuple] = None               # (file, line number, line) that loaded `where`

    def place(self, show) -> str:
        """Where it comes from, as one phrase: "~/.zshrc line 3", "~/x/office.zsh, loaded by ..."."""
        if self.where is None:
            said = "a file zsh does not name"
        else:
            said = show(self.where) + (f" line {self.line}" if self.line else "")
        if self.loader:
            said += f", loaded by {show(self.loader[0])} line {self.loader[1]}"
        return said


def _definition(name: str, kind: str):
    if kind == "alias":
        return re.compile(rf"^\s*alias\s+(-\S+\s+)*{name}=")
    return re.compile(rf"^\s*(function\s+{name}\b|{name}\s*\(\s*\))")


def _find(path: Path, pattern) -> tuple:
    """The first line of path that matches: (number, text), or (None, "")."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None, ""
    for i, line in enumerate(lines):
        if pattern.search(line):
            return i + 1, line.strip()
    return None, ""


def _loader(where: Path, read: list) -> Optional[tuple]:
    """The line in an earlier startup file that sources `where`. The path on that line may be built
    at run time (`${commands[office]:A:h:h}/office.zsh`), so it is matched by the file's name."""
    if where not in read:
        return None
    pattern = re.compile(rf"^\s*(source|\.)\s+.*{re.escape(where.name)}[\"']?\s*(;.*|#.*)?$")
    for f in reversed(read[:read.index(where)]):
        n, text = _find(f, pattern)
        if n:
            return f, n, text
    return None


def shadows(env) -> Optional[list]:
    """Each of office and fm that your zsh defines as a function or an alias, with where it comes from.
    None when there is no zsh. Raises Unknown when zsh did not answer."""
    zsh = shutil.which("zsh", path=env.get("PATH", ""))
    if not zsh:
        return None
    # no terminal: a startup file that waits for input or takes the terminal over cannot hang this
    try:
        r = subprocess.run([zsh, "-o", "sourcetrace", "-l", "-i", "-c", _ASK], env=env, cwd=env.get("HOME") or "/",
                           capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
                           start_new_session=True, timeout=SECONDS)
    except subprocess.TimeoutExpired:
        raise Unknown(f"zsh did not answer within {SECONDS} seconds")
    except OSError as e:
        raise Unknown(f"zsh did not start: {e}")
    if MARK not in r.stdout:
        raise Unknown(f"zsh did not run `whence` (exit {r.returncode})")
    read = []
    for line in r.stderr.splitlines():
        m = _TRACE.match(line)
        if m and Path(m.group(1)) not in read:
            read.append(Path(m.group(1)))
    found = []
    for line in r.stdout.split(MARK, 1)[1].splitlines():
        name, _, rest = line.partition("\t")
        said, _, source = rest.partition("\t")
        kind = said.rpartition(": ")[2].strip()
        if name not in NAMES or kind not in ("function", "alias"):
            continue
        pattern = _definition(name, kind)
        where = Path(source) if source and source.startswith("/") else None
        if where is None:  # an alias, or a zsh without $functions_source: the file that defines it
            where = next((f for f in reversed(read) if _find(f, pattern)[0]), None)
        n, text = _find(where, pattern) if where else (None, "")
        found.append(Shadow(name, kind, where, n, text, _loader(where, read) if where else None))
    return found


def problem(s: Shadow, show, fixed_by_install: bool = False) -> str:
    """One line for a hidden name: what hides it, where, and the fix."""
    from .install import LEGACY_ZSH
    what = "a shell function" if s.kind == "function" else "an alias"
    if fixed_by_install:
        fix = "`office install` removes that line (the tmux office's loader); then open a new shell"
    elif s.loader and LEGACY_ZSH[0].match(s.loader[2].rstrip("\"'")):
        fix = (f"remove line {s.loader[1]} of {show(s.loader[0])}, which loads the tmux office (0.x), "
               "then open a new shell")
    elif s.where is not None:
        fix = f"remove it from {show(s.where)}, then open a new shell"
    else:
        fix = f"find it with `whence -v {s.name}` in zsh, remove it, then open a new shell"
    return f"{what} from {s.place(show)}, hides the {s.name} command in every zsh: {fix}"
