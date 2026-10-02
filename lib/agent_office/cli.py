"""The office command: the 1.0 verbs, and the tmux office (0.x) for every verb not built yet."""

from __future__ import annotations

import os
import shutil
import sys

from . import config as C
from . import install

VERSION = "1.0.0-dev"

HELP = """\
office: Agent Office, one command for the whole agent setup.

  office install [--check] [--yes]   check your config and write what the office needs,
                                     showing every change and backing up what it replaces
  office config check                check your config, and the herdr config made from it
  office config show                 print the config in effect: defaults, your file, preset
  office help | version

Your config: ~/.config/agent-office/config.toml. The rest of 1.0 (on, break, off, update,
status, doctor) is planned. Until each one lands, any other verb runs the tmux office (0.x)
from bin/office-tmux: see docs/legacy-tmux/README.md. Run that way it is a separate process,
so `office cd` cannot move your shell."""


def _config(args, out, err) -> int:
    path = C.config_path()
    sub = args[0] if args else ""
    if sub not in ("check", "show"):
        print("usage: office config check | office config show", file=err)
        return 2
    try:
        cfg = C.load(path)
        text = C.herdr_config(cfg)
    except C.ConfigError as e:
        print(f"config: problems in {path}", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        return 1
    if sub == "show":
        # dumps checks that what it prints reads back as the same config
        print(C.dumps(cfg, "config"), end="", file=out)
        return 0
    where = str(path) if path.exists() else f"{path} (not there yet: the defaults)"
    ok, said = C.herdr_check(text)
    if not ok:
        print(f"config: {where}: Agent Office keys ok; the herdr part is not:", file=err)
        for line in said.splitlines():
            print("  " + line, file=err)
        return 1
    print(f"config: ok ({where})", file=out)
    return 0


def _legacy(args, err) -> int:
    shim = C.REPO / "bin" / "office-tmux"
    if not (C.REPO / "office.zsh").exists() or not shutil.which("zsh"):
        print(f"office: '{args[0]}' is not built in Agent Office 1.0 yet. See `office help`.", file=err)
        return 2
    # zsh from PATH, not the shim's #!/bin/zsh: not every Linux has zsh in /bin.
    # -i as in the shim, so the tmux office reads your OFFICE_* settings from your rc
    os.execvp("zsh", ["zsh", "-i", str(shim), *args])
    return 1  # not reached


def main(argv, out=sys.stdout, err=sys.stderr) -> int:
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(HELP, file=out)
        return 0
    verb, rest = argv[0], argv[1:]
    if verb in ("version", "--version", "-V"):
        print(f"office {VERSION}", file=out)
        return 0
    if verb == "install":
        return install.run(rest, out=out, err=err)
    if verb == "config":
        return _config(rest, out, err)
    return _legacy(argv, err)
