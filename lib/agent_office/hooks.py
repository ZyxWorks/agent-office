"""[hooks]: your own commands, run when the office walks in (office on) and goes home (office off).

Each hook is a list of words, an argv: the first word is the program, a leading ~/ in it is your
home, and every other word reaches it as one argument, exactly as written. Nothing is ever run by
a shell, so a `;`, a `$(...)` or a `|` in a word is only text. A hook that fails, or does not
finish within TIMEOUT, does not stop the lifecycle: the command goes on, names the hook, and exits
1. The last result of each kind is kept in hooks.json under the state folder, and office status
shows it.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from pathlib import Path

from . import config as C

TIMEOUT = 600
KINDS = {"on": "walk-in hooks", "off": "go-home hooks"}


def path(env) -> Path:
    return C.state_dir(env) / "hooks.json"


def argv(hook: list, env) -> list:
    return [str(C.expand(hook[0], env)), *hook[1:]]


def show(hook: list) -> str:
    """The hook as you would type it: a word with a space or a sign in it is quoted, a plain
    ~/path is not, so it reads like your config."""
    return " ".join(w if re.fullmatch(r"[\w@%+=:,./~-]+", w) else shlex.quote(w) for w in hook)


def run(hooks: list, kind: str, env, out=None, nonce: str = "") -> list:
    """Run each hook in order, and record the results in hooks.json. Returns the ones that failed,
    as lines that name them. `out` gets each hook's own output; None when nobody can read it."""
    results, failed = [], []
    for hook in hooks:
        said, tail = None, ""
        if out is not None:
            print(f"office {kind}: running {show(hook)}", file=out)
            out.flush()
        try:
            r = subprocess.run(argv(hook, env), env=env, capture_output=True, text=True, errors="replace",
                               stdin=subprocess.DEVNULL, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            said = f"did not finish within {TIMEOUT} seconds and was stopped"
        except OSError as e:
            said = f"did not start: {e.strerror or e}"
        else:
            tail = (r.stdout + r.stderr).strip()
            if r.returncode != 0:
                said = f"exited {r.returncode}"
        if out is not None and tail:
            print("\n".join("  " + line for line in tail.splitlines()), file=out)
        results.append({"hook": hook, "result": "ok" if said is None else "failed",
                        "detail": said or "", "output": tail[-400:]})
        if said is not None:
            failed.append(f"{KINDS[kind][:-1]} `{show(hook)}` {said}")
    if hooks:
        data = C.read_json(path(env)) or {"schema": 1}
        data[kind] = {"at": int(time.time()), "nonce": nonce, "results": results}
        C.write_json(path(env), data)
    return failed


def last(env, kind: str) -> dict | None:
    got = (C.read_json(path(env)) or {}).get(kind)
    return got if isinstance(got, dict) else None


def failures(rec: dict | None) -> list:
    return [f"`{show(r.get('hook') or [])}` {r.get('detail')}" for r in (rec or {}).get("results", [])
            if r.get("result") != "ok"]
