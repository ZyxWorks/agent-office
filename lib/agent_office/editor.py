"""office editor: an editor pane next to the focused agent, in that agent's worktree.

Off by default. prefix+i runs `office editor --pane <focused pane>`: herdr says which folder the
pane's foreground process (the agent) is in, the worktree is the git top level of that folder,
and a new pane split off the focused one runs `office editor <worktree>` there. That second run
starts the editor in the pane's own shell, so your shell's $VISUAL and $EDITOR are the ones it
sees, and replaces itself with the editor: quit the editor and the pane closes.

The editor is `[editor] command`, else $VISUAL, else $EDITOR, else nvim. It is split into words
and run directly, never through a shell. nvim gets the office's small config
(editor/nvim/init.lua) unless office_config is false: `nvim -u` that file, with its own
NVIM_APPNAME so its swap, undo and history files stay apart from your own nvim's. The two plugins
it uses are checked out by `office install` at the commits config/components.toml pins; nothing
here fetches anything.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as C
from . import vendors as V

USAGE = """\
usage: office editor [FOLDER]        the editor here, in FOLDER's worktree (default: this folder)
       office editor --pane PANE     a new pane next to PANE, in PANE's worktree, running it

Bound to prefix+i in the preset. Off until [editor] enabled = true in your config.
The editor is [editor] command, else $VISUAL, else $EDITOR, else nvim."""
INIT = C.REPO / "editor" / "nvim" / "init.lua"
NVIM_APPNAME = "agent-office-nvim"


def _herdr(env) -> str:
    return env.get("HERDR_BIN_PATH") or "herdr"


def _say(env, message: str, err):
    """One line on herdr's notification, and on stderr for a run from a shell."""
    print(f"editor: {message}", file=err)
    try:
        subprocess.run([_herdr(env), "notification", "show", "Editor", "--body", message, "--sound", "none"],
                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        pass  # outside herdr there is no notification; stderr said it


def worktree(folder: Path, env) -> Path:
    """The git top level folder is in, or folder itself outside a repository."""
    try:
        r = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"], env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return folder
    top = r.stdout.strip()
    return Path(top) if r.returncode == 0 and top else folder


def command(cfg: dict, env) -> list:
    """The editor's argv: the config's command, $VISUAL, $EDITOR or nvim, split like a shell would
    split words, but never run by one."""
    for text in (cfg.get("command"), env.get("VISUAL"), env.get("EDITOR")):
        if text and text.strip():
            try:
                argv = shlex.split(text)
            except ValueError:
                continue  # an unbalanced quote: not a command we can run as written
            if argv:
                return argv
    return ["nvim"]


def office_nvim(cfg: dict, argv: list) -> bool:
    return cfg.get("office_config", True) and Path(argv[0]).name == "nvim"


def missing_plugins(env) -> list:
    """The pinned nvim plugins that are not checked out at their pinned commit."""
    opt = C.nvim_pack_dir(env) / "pack" / "office" / "opt"
    return [name for name, p in V.nvim_plugins().items() if V.head(opt / name, env) != p["commit"]]


def launch(cfg: dict, env) -> tuple:
    """(argv, env) for the editor: the office config added when the editor is nvim."""
    argv = command(cfg, env)
    env = dict(env)
    if office_nvim(cfg, argv):
        argv = [argv[0], "-u", str(INIT), *argv[1:]]
        env["NVIM_APPNAME"] = NVIM_APPNAME
        env["AGENT_OFFICE_NVIM_PACK"] = str(C.nvim_pack_dir(env))
    return argv, env


def _hold(in_pane: bool):
    """The pane closes the moment a run in it exits: keep the reason on screen until it is read."""
    if in_pane:
        try:
            input("Press Enter to close this pane. ")
        except (EOFError, KeyboardInterrupt):
            pass


def _here(cfg: dict, folder: Path, env, err, in_pane: bool) -> int:
    def fail(message: str) -> int:
        print(f"editor: {message}", file=err)
        _hold(in_pane)
        return 1

    if not folder.is_dir():
        return fail(f"no folder at {folder}")
    root = worktree(folder, env)
    argv, env = launch(cfg, env)
    exe = shutil.which(argv[0], path=env.get("PATH", ""))
    if not exe:
        how = " (brew install neovim)" if argv[0] == "nvim" else ""
        return fail(f"{argv[0]} is not on PATH{how}")
    os.chdir(root)
    env["PWD"] = str(root)
    try:
        os.execve(exe, argv, env)
    except OSError as e:
        return fail(f"could not start {argv[0]}: {e.strerror}")
    return 1  # not reached: execve does not return


def _pane(cfg: dict, pane: str, env, err) -> int:
    """Split pane and run `office editor <its worktree>` in the new one."""
    h = _herdr(env)

    def herdr(*args) -> dict:
        r = subprocess.run([h, *args], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=10, check=False)
        try:
            data = json.loads(r.stdout) if r.stdout.strip() else {"result": {}}  # pane run says nothing
        except ValueError:
            data = {}
        if r.returncode != 0 or not isinstance(data, dict) or "result" not in data:
            why = (data.get("error") or {}).get("message") or (r.stderr or r.stdout).strip() or f"exit {r.returncode}"
            raise OSError(f"`herdr {' '.join(args[:2])}` failed: {why}")
        return data["result"]

    new = None
    try:
        info = herdr("pane", "get", pane).get("pane") or {}
        # the agent's folder, which can differ from the folder its pane's shell started in
        folder = info.get("foreground_cwd") or info.get("cwd")
        if not folder:
            raise OSError(f"herdr does not say which folder {pane} is in")
        root = worktree(Path(folder), env)
        new = herdr("pane", "split", pane, "--direction", cfg["split"], "--cwd", str(root),
                    "--focus").get("pane", {}).get("pane_id")
        if not new:
            raise OSError("herdr did not say which pane it made")
        # typed into the new pane's shell, so every word is quoted; exec: quitting closes the pane
        line = " ".join(shlex.quote(a) for a in
                        ["exec", str(C.REPO / "bin" / "office"), "editor", "--in-pane", str(root)])
        herdr("pane", "run", new, line)
    except (OSError, subprocess.SubprocessError) as e:
        _say(env, str(e), err)
        if new:
            try:
                herdr("pane", "close", new)  # the pane this made, and nothing else
            except (OSError, subprocess.SubprocessError):
                pass
        return 1
    try:
        herdr("pane", "rename", new, "editor")
    except (OSError, subprocess.SubprocessError):
        pass  # a label is a nicety; the editor is open
    argv = command(cfg, env)
    if office_nvim(cfg, argv):
        try:
            missing = missing_plugins(env)
        except C.ConfigError:
            missing = []
        if missing:
            _say(env, f"opened without {', '.join(missing)}: run `office install` to check them out", err)
    return 0


def run(args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    in_pane = args[:1] == ["--in-pane"]
    rest = args[1:] if in_pane else args
    pane = folder = None
    if rest[:1] in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    if not in_pane and rest[:1] == ["--pane"] and len(rest) == 2 and rest[1].strip():
        pane = rest[1]
    elif len(rest) <= 1 and not (rest and rest[0].startswith("-")):
        folder = Path(rest[0]) if rest else Path.cwd()
    else:
        print(USAGE, file=err)
        return 2
    path = C.config_path(env)
    try:
        cfg = C.load(path)["editor"]
    except C.ConfigError as e:
        print(f"editor: problems in {path}", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        _hold(in_pane)
        return 1
    if not cfg.get("enabled"):
        _say(env, "off. Turn it on with [editor] enabled = true in your config (README, \"Editor\")", err)
        _hold(in_pane)
        return 1
    if pane is not None:
        return _pane(cfg, pane, env, err)
    return _here(cfg, folder.absolute(), env, err, in_pane)
