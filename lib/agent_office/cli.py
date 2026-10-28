"""The office command: the 1.0 verbs, and the tmux office (0.x) for every verb not built yet."""

from __future__ import annotations

import os
import shutil
import sys

from . import config as C
from . import doctor, install, lifecycle, tools
from . import notify
from . import setup_all
from . import update

VERSION = "1.0.0-dev"

HELP = """\
office: Agent Office, one command for the whole agent setup.

  office install [--check] [--yes]   check your config and write what the office needs,
                                     showing every change and backing up what it replaces
  office setup [--check] [--yes]     the whole setup in one run, on a new machine the one
                                     line after the clone: a few questions, tools, Firstmate,
                                     install, herdr's integration, the agent working setup,
                                     doctor. Shows every change first
  office setup agents [--check] [--yes] [--remove] [--reset-key <file>:<key>]
                                     only the agent working setup (rules, Claude Code settings
                                     and hooks, Firstmate, no-mistakes, gnhf) from your
                                     [setup] keys, showing every change first
  office config check                check your config, and the herdr config made from it
  office config show                 print the config in effect: defaults, your file, preset
  office keys                        one screen of every office key (preset/keys.txt)
  office notify needs-you|pr-ready <message>
                                     push one line to your phone, if [notify] is on
  office tools [--check] [--yes]     install the missing tools the office uses, at pinned
               [--workstation]       versions, each through its owner; --workstation adds
                                     generic command-line tools
  office doctor                      read-only: each component's version, who updates it, and
                                     whether this release is tested with it
  office on                          start the office's herdr session and its Firstmate, or
                                     focus them, and attach. Starts no workers
  office break                       detach the terminals office on and fm attached; everything
                                     keeps running
  office off [--all] [--yes] [--stop-workers] [--force] [--timeout MINUTES]
                                     stop this office (--all: every office this installation
                                     started) after showing what stops and asking; Firstmate
                                     saves first, and a failed save stops nothing. A busy
                                     worker refuses it, or --stop-workers has Firstmate stop it
                                     first. A session office on did not start is never stopped
  office status                      read-only: what runs, what the office owns, the meter,
                                     pending restarts, the last office off
  office update [--check] [--yes]    bring every component to the versions this release is
                                     tested with, each through its owner; restarts nothing
  office help | version

Also `fm`: open the office's Firstmate, and `fm restart` (see `fm --help`), and
`officeoff-all`, the same as `office off --all`.

Your config: ~/.config/agent-office/config.toml. Any other verb runs the tmux office (0.x)
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
    if verb == "setup":
        return setup_all.run(rest, out=out, err=err)
    if verb == "tools":
        return tools.run(rest, out=out, err=err)
    if verb == "doctor":
        return doctor.run(rest, out=out, err=err)
    if verb == "update":
        return update.run(rest, out=out, err=err)
    if verb == "config":
        return _config(rest, out, err)
    if verb in ("on", "break", "off", "status"):
        return lifecycle.run(verb, rest, out=out, err=err)
    if verb == "notify":
        return notify.run(rest, out=out, err=err)
    if verb == "keys":
        # a text file, so changing a key means editing preset/keys.txt; preset-probe checks it
        print((C.REPO / "preset" / "keys.txt").read_text(), end="", file=out)
        return 0
    return _legacy(argv, err)
