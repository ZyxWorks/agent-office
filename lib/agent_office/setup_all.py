"""office setup: the whole agent setup in one run, the one line after the clone.

  git clone https://github.com/ZyxWorks/agent-office ~/agent-office && ~/agent-office/bin/office setup

The steps, in order, each through the command that owns it, so running that one command later
does the same thing:

1. the first-run questions, only while there is no config yet and there is a terminal to ask on:
   which coding agent Firstmate runs on (only among the ones installed), where Firstmate's code
   and home go, whether to write the agent working setup, and how many test workers and
   subagents. The answers go into a new ~/.config/agent-office/config.toml, which is yours,
2. office tools: the missing tools, at their pins, each through its owner,
3. Firstmate: a clone of firstmate.source into firstmate.code, at the newest revision this
   release is tested with, when nothing is there yet. A checkout that is there is left as it is,
4. office install,
5. office setup agents: the agent working setup, unless setup.enabled is false,
6. herdr's integration for your harness (`herdr integration install <harness>`), when it is not
   current and the harness is installed and has its folder (~/.claude, ~/.codex),
7. office doctor: the report. It is read only, and its problems do not fail the run.

Each step shows what it changes before it changes it and asks before it installs anything or
changes a file of yours; --yes asks nothing. It never asks for a token, an account, a name or an
email address. Signing in to a coding agent is yours to do. Nothing fetched from the network is
run by a shell, and nothing runs with sudo.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from . import config as C
from . import doctor, install, setup_home, tools

HARNESSES = ("claude", "codex")
NAMES = {"claude": "Claude Code", "codex": "Codex"}


def has_terminal() -> bool:
    try:
        with open("/dev/tty", "r+b", buffering=0):
            return True
    except OSError:
        return False


class Run:
    def __init__(self, env, out, err, check_only: bool, yes: bool, ask: Callable[[str], Optional[str]]):
        self.env, self.out, self.err = env, out, err
        self.check_only, self.yes, self.ask = check_only, yes, ask
        self.home = C.home(env)
        self.results = []  # (step, "ok" | "left for you" | "skipped" | "failed")

    def show(self, p) -> str:
        s = str(p)
        h = str(self.home)
        return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s

    def say(self, line=""):
        print(line, file=self.out)

    def which(self, cmd: str) -> Optional[str]:
        return shutil.which(cmd, path=self.env.get("PATH", ""))

    def done(self, step: str, state: str):
        self.results.append((step, state))

    def confirm(self, prompt: str) -> bool:
        return self.yes or (self.ask(prompt) or "").lower() in ("y", "yes")

    # --- 1. the first-run questions ------------------------------------------------------------

    def _pick(self, prompt: str, default: str, valid: Callable[[str], Optional[str]]) -> Optional[str]:
        """The answer, the default on an empty one, None when there is no terminal. A wrong answer
        is said why and asked again."""
        while True:
            got = self.ask(f"{prompt} [{default}] ")
            if got is None:
                return None
            got = got or default
            why = valid(got)
            if why is None:
                return got
            self.say(f"  {why}")

    def questions(self) -> Optional[dict]:
        """The config the answers make, as TOML tables {table: {key: value}}, or None when there is
        no terminal to ask on."""
        self.say("No config yet, so four questions first. Enter keeps the answer in brackets.")
        have = [h for h in HARNESSES if self.which(h)]
        if len(have) == 2:
            harness = self._pick("(1/4) Which coding agent does Firstmate run on, claude or codex?", "claude",
                                 lambda a: None if a in HARNESSES else "Answer claude or codex.")
            if harness is None:
                return None
        elif have:
            harness = have[0]
            self.say(f"(1/4) Firstmate runs on {NAMES[harness]}, the coding agent you have installed.")
        else:
            harness = "claude"
            self.say("(1/4) Neither Claude Code nor Codex is installed. Firstmate runs on Claude Code: install "
                     "it and sign in yourself, then run office setup again.")

        def a_path(a):
            return None if a.startswith(("~/", "/")) else "Answer a path that starts with ~/ or /."
        code = self._pick("(2/4) Where does Firstmate's code go?", "~/firstmate", a_path)
        if code is None:
            return None
        fm_home = self._pick("      And its private home, where it keeps its notes and state?", code, a_path)
        if fm_home is None:
            return None

        def yes_no(a):
            return None if a.lower() in ("y", "yes", "n", "no") else "Answer y or n."
        write = self._pick("(3/4) Write the agent working setup too: agent rules (~/AGENTS.md), Claude Code "
                           "settings and hooks, Firstmate, no-mistakes and gnhf settings? Every change is "
                           "shown first. y/n", "y", yes_no)
        if write is None:
            return None
        enabled = write.lower() in ("y", "yes")
        answers = {"firstmate": {"code": code, "harness": harness}, "setup": {"enabled": enabled}}
        if fm_home != code:
            answers["firstmate"]["home"] = fm_home
        if harness != "claude" and enabled:
            self.say(f"      The shipped models are Claude's. Set [setup.models.default] and [setup.models.mechanical] "
                     f"to {NAMES[harness]} models in your config, or the agent working setup is not written.")
        if enabled:
            def count(lo, hi):
                return lambda a: (None if a.isdigit() and lo <= int(a) <= hi
                                  else f"Answer a whole number from {lo} to {hi}.")
            workers = self._pick("(4/4) How many workers may one test run use?", "2", count(1, 256))
            if workers is None:
                return None
            subagents = self._pick("      How many subagents may one agent start?", "3", count(0, 64))
            if subagents is None:
                return None
            answers["setup.machine"] = {"test_workers": int(workers), "max_subagents": int(subagents)}
        return answers

    def write_config(self, answers: dict) -> bool:
        lines = ["", "# Your answers to the first `office setup`. Change them any time, then run office setup again."]
        for table, keys in answers.items():
            lines += ["", f"[{table}]"]
            for k, v in keys.items():
                val = ("true" if v else "false") if isinstance(v, bool) else (str(v) if isinstance(v, int) else C._quote(v))
                lines.append(f"{k} = {val}")
        text = C.STARTER.read_text() + "\n".join(lines) + "\n"
        path = C.config_path(self.env)
        try:
            C.effective(C.tomllib.loads(text), str(path))
        except C.ConfigError as e:
            print("office setup: the answers do not make a valid config. Nothing was written.", file=self.err)
            for p in e.problems:
                print("  " + p, file=self.err)
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.say(f"Wrote your config, {self.show(path)}. It is yours: office setup never writes it again.")
        return True

    # --- 3. Firstmate --------------------------------------------------------------------------

    def firstmate(self, cfg: dict) -> str:
        fm = cfg["firstmate"]
        code = C.expand(fm["code"], self.env)
        if (code / ".git").exists():
            self.say(f"Firstmate is there already, {self.show(code)}: left as it is. office update moves it.")
            return "ok"
        if code.exists() and not (code.is_dir() and not any(code.iterdir())):
            self.say(f"Something else is at {self.show(code)}, so Firstmate is not cloned. Move it, or set "
                     "firstmate.code in your config to another folder, then run office setup again.")
            return "left for you"
        try:
            tested = C.read_toml(doctor.MANIFEST, str(doctor.MANIFEST)).get("firstmate", {}).get("tested", [])
        except C.ConfigError as e:
            print("\n".join(["office setup: cannot read the component list", *e.problems]), file=self.err)
            return "failed"
        source = fm["source"]
        at = (f"at {tested[-1][:12]}, the newest revision this release is tested with" if tested else
              "at its newest commit: no Firstmate revision is tested with this release yet, so office "
              "doctor reports it as not tested")
        self.say(f"  clone    {source} into {self.show(code)}, {at}")
        if self.check_only:
            return "ok"
        if not self.which("git"):
            self.say("git is not installed, so Firstmate is not cloned. Install git, then run office setup again.")
            return "failed"
        if not self.confirm("Clone Firstmate? [y/N] "):
            self.say("Firstmate is not cloned: not confirmed. Run it in a terminal to answer, or pass --yes.")
            return "skipped"
        try:
            tools.call(["git", "clone", "--quiet", "--", source, str(code)], self.env)
            if tested:
                tools.call(["git", "-C", str(code), "reset", "--quiet", "--hard", tested[-1]], self.env)
        except (tools.Failed, OSError) as e:
            self.say(f"  FAILED   the clone: {e}")
            return "failed"
        self.say(f"  ok       Firstmate in {self.show(code)}")
        return "ok"

    # --- 5. herdr's integration ----------------------------------------------------------------

    def integration(self, cfg: dict) -> str:
        harness = cfg["firstmate"]["harness"]
        if not self.which(harness):
            self.say(f"{NAMES[harness]} is not installed. Install it and sign in yourself, then run "
                     f"`herdr integration install {harness}` (or office setup again).")
            return "left for you"
        if not self.which("herdr"):
            self.say("herdr is not installed, so its integration is not either: see office tools above.")
            return "failed"
        # herdr puts its hooks in the agent's own folder, and refuses while there is none
        if not (self.home / f".{harness}").is_dir() and not self.check_only:
            self.say(f"~/.{harness} is not there yet: start {NAMES[harness]} once and sign in, then run "
                     f"`herdr integration install {harness}` (or office setup again).")
            return "left for you"
        state = doctor.integration_state(harness, self.env)
        if state is not None and state.startswith("current"):
            self.say(f"herdr's {harness} integration is current.")
            return "ok"
        self.say(f"  install  herdr's {harness} integration ({state or 'not reported'}): herdr learns each "
                 "agent's session, so the meter can read its size. herdr writes its hooks into the agent's "
                 "settings")
        if self.check_only:
            return "ok"
        if not self.confirm(f"Install herdr's {harness} integration? [y/N] "):
            self.say("Not installed: not confirmed. Run it in a terminal to answer, or pass --yes.")
            return "skipped"
        try:
            tools.call(["herdr", "integration", "install", harness], self.env)
        except (tools.Failed, OSError) as e:
            self.say(f"  FAILED   herdr integration install {harness}: {e}")
            return "failed"
        self.say(f"  ok       herdr's {harness} integration")
        return "ok"


def run(args, env=None, out=sys.stdout, err=sys.stderr, ask=install.ask) -> int:
    if args[:1] == ["agents"]:
        return setup_home.run(args[1:], env=env, out=out, err=err)
    check_only = yes = False
    for a in args:
        if a in ("--check", "-n", "--dry-run"):
            check_only = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a in ("-h", "--help"):
            print(USAGE, file=out)
            return 0
        else:
            print(f"office setup: unknown option {a}\n{USAGE}", file=err)
            return 2
    if env is None:
        env = os.environ
    env = dict(env)
    if not (check_only or yes or has_terminal()):
        print("office setup: there is no terminal to ask on. Run it in a terminal, or pass --yes.", file=err)
        return 2
    r = Run(env, out, err, check_only, yes, ask)
    # the release tools and the office commands go here; the later steps look herdr up on this PATH
    local_bin = str(r.home / ".local" / "bin")
    on_path = local_bin in env.get("PATH", "").split(os.pathsep)
    if not on_path:
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
        os.environ["PATH"] = env["PATH"]
    flags = ["--check"] if check_only else (["--yes"] if yes else [])

    cfg_path = C.config_path(env)
    r.say(f"office setup{' --check' if check_only else ''}: Agent Office at {r.show(C.REPO)}")
    if not (cfg_path.exists() or cfg_path.is_symlink()) and not (check_only or yes):
        r.say("")
        answers = r.questions()
        if answers is None:
            print("office setup: there is no terminal to ask on. Run it in a terminal, or pass --yes.", file=err)
            return 2
        if not r.write_config(answers):
            return 1
    try:
        cfg = C.load(cfg_path)
    except C.ConfigError as e:
        print("office setup: the config has problems. Nothing was changed.", file=err)
        for p in e.problems:
            print("  " + p.replace(str(r.home), "~"), file=err)
        return 1

    steps = iter(range(1, 7))

    def step(title):
        r.say(f"\n{next(steps)}. {title}")

    step("office tools: the tools the office uses")
    r.done("office tools", "ok" if tools.run(flags, env=env, out=out, err=err) == 0 else "failed")

    step("Firstmate")
    r.done("Firstmate", r.firstmate(cfg))

    step("office install: your config, herdr's config, the meter, the office commands")
    if check_only and not r.which("herdr"):
        r.say("office install checks its config with herdr, so it plans once herdr is installed.")
        r.done("office install", "ok")
    else:
        r.done("office install", "ok" if install.run(flags, env=env, out=out, err=err) == 0 else "failed")

    step("office setup agents: the agent working setup")
    if cfg["setup"]["enabled"]:
        r.done("office setup agents",
               "ok" if setup_home.run(flags, env=env, out=out, err=err) == 0 else "failed")
    else:
        r.say("Left out: setup.enabled is false in your config.")
        r.done("office setup agents", "skipped")

    step("herdr's integration")
    r.done("herdr integration", r.integration(cfg))

    if not check_only:
        step("office doctor")
        doctor.run([], env=env, out=out, err=err)

    failed = [s for s, state in r.results if state == "failed"]
    if not check_only:
        r.say("")
        for name, state in r.results:
            r.say(f"  {state:<13} {name}")
    if failed:
        r.say(f"office setup: {len(failed)} step(s) failed. Fix what they say above, then run office setup again: "
              "what is done stays done.")
        return 1
    if check_only:
        r.say("office setup --check: nothing was changed.")
        return 0
    if not on_path:
        r.say(f"{r.show(Path(local_bin))} is not on your PATH, and the office and fm commands are there. Add it "
              "in your shell's startup file, then open a new shell:")
        r.say('  export PATH="$HOME/.local/bin:$PATH"')
    r.say("Done. Start the office with `office on`.")
    return 0


USAGE = """\
usage: office setup [--check] [--yes]
       office setup agents [--check] [--yes] [--remove] [--reset-key <file>:<key>]

The whole agent setup in one run: on a new machine, the one line after the clone. In order:

  1. four questions, only while you have no config yet: which coding agent Firstmate runs on,
     where Firstmate's code and home go, whether to write the agent working setup, and how many
     test workers and subagents. The answers go into ~/.config/agent-office/config.toml
  2. office tools: the missing tools, at their pins
  3. Firstmate cloned into firstmate.code at a tested revision, when nothing is there yet
  4. office install: your config, herdr's config, the meter, the office and fm commands
  5. office setup agents: the agent working setup, unless setup.enabled is false
  6. herdr's integration for your coding agent, when that agent is installed
  7. office doctor: the report

Every step shows what it changes first and asks before it installs anything or changes a file of
yours. Run it again any time: a step that has nothing to do says so. It never asks for a token, an
account, a name or an email address; signing in to a coding agent is yours to do.

  --check   show what each step would do, change nothing (and ask nothing)
  --yes     ask nothing: the defaults for the questions, yes to every step (backups are still made)

office setup agents writes only the agent working setup: see `office setup agents --help`."""
