"""fm: open the configured Firstmate, and restart it without losing its work.

One Firstmate per office: the herdr agent named `firstmate` in the configured herdr session
(office.session). herdr keeps live agent names unique within a session, so the name can never
match two agents, and fm checks that the agent it finds runs the configured harness in the
configured checkout (firstmate.code) before it touches it. An agent in that checkout under any
other name is refused, not guessed at: fm prints the one command that adopts it.

`fm [args]` focuses that agent, or starts it in a new tab of the session with the arguments
passed to the harness unchanged. `fm restart` asks it to /stow, reads the stow's answer, and
sends /clear only when Firstmate says the save worked. It resets the conversation, not the
process: launch-time wiring (hooks, model, flags) is read again only by a fresh start.

Every herdr call puts `--session` first: after a command's own `--`, a trailing one is handed
to the agent as its argument. Nothing here runs a shell: argv is always a list, and herdr quotes
the agent's arguments itself.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from . import config as C

NAME = "firstmate"
START_TIMEOUT_MS = 60_000
RESET_TIMEOUT_MS = 120_000
STOW_MINUTES = 30
MARK = "office-stow-"

USAGE = """\
usage: fm [--] [harness arguments...]
       fm restart [--timeout MINUTES]

fm opens the Firstmate this office runs: the herdr agent named firstmate in the herdr session
office.session, in firstmate.code. Running it again focuses it; arguments are passed to the
harness (firstmate.harness) unchanged when fm starts it. Start with `--` to pass an argument
fm would otherwise read itself, such as `fm -- restart`.

fm restart asks Firstmate to save its work (/stow), checks its answer, and only then starts a
fresh conversation (/clear). If the save fails, times out (default 30 minutes) or is cancelled
with Ctrl-C, nothing is reset. Launch-time wiring (hooks, model, flags) is read again only when
Firstmate itself starts again: quit it, then run fm."""


class Fail(Exception):
    """A message for the user; fm prints it and exits non-zero."""


class Herdr:
    def __init__(self, session: str, env: dict):
        self.session = session
        # herdr's own pane variables point at the session the caller sits in, which may be
        # another one; HERDR_SESSION and the leading --session name the office's
        self.env = {k: v for k, v in env.items() if k != "HERDR_SOCKET_PATH"}
        self.env["HERDR_SESSION"] = session

    def call(self, *args) -> dict:
        try:
            return json.loads(self.text(*args)).get("result", {})
        except ValueError:
            raise HerdrError("", f"herdr {args[0]} {args[1]} did not answer in JSON")

    def text(self, *args) -> str:
        # no timeout here: every wait passes herdr its own --timeout, and herdr enforces it
        try:
            r = subprocess.run(["herdr", "--session", self.session, *args], env=self.env,
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            raise Fail("herdr is not installed (https://herdr.dev)")
        if r.returncode != 0:
            try:
                e = json.loads(r.stderr)["error"]
                raise HerdrError(e.get("code", ""), e.get("message", ""))
            except (ValueError, KeyError, TypeError):
                raise HerdrError("", (r.stderr or r.stdout).strip())
        return r.stdout

    def server(self) -> dict:
        try:
            r = subprocess.run(["herdr", "--session", self.session, "status", "--json"], env=self.env,
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20)
        except FileNotFoundError:
            raise Fail("herdr is not installed (https://herdr.dev)")
        try:
            return json.loads(r.stdout).get("server") or {}
        except ValueError:
            return {}


class HerdrError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{message} ({code})" if code else message)
        self.code = code


class Office:
    def __init__(self, cfg: dict, env: dict):
        fm = cfg["firstmate"]
        self.env = env
        self.session = cfg["office"]["session"]
        self.harness = fm["harness"]
        self.code = C.expand(fm["code"], env)
        self.home = C.expand(fm["home"], env) if "home" in fm else None
        self.herdr = Herdr(self.session, env)

    def check_paths(self):
        if not self.code.is_dir():
            raise Fail(f"no Firstmate checkout at {self.code} (firstmate.code)")
        if self.home is not None and not self.home.is_dir():
            raise Fail(f"no Firstmate home at {self.home} (firstmate.home)")

    def running(self) -> dict:
        srv = self.herdr.server()
        if not srv.get("running"):
            raise Fail(f"herdr session '{self.session}' is not running. Start it with: "
                       f"herdr --session {self.session}")
        return srv

    def agent(self) -> dict | None:
        """The office's Firstmate, checked, or None when no agent has the name."""
        try:
            a = self.herdr.call("agent", "get", NAME).get("agent") or {}
        except HerdrError as e:
            if e.code in ("agent_not_found", "target_not_found", "not_found"):
                return None
            raise Fail(f"cannot read agent '{NAME}' in herdr session '{self.session}': {e}")
        cwd = a.get("cwd") or ""
        if a.get("agent") != self.harness or not _same(cwd, self.code):
            raise Fail(f"the agent named '{NAME}' in herdr session '{self.session}' (pane {a.get('pane_id')}) "
                       f"is {a.get('agent') or 'an unknown agent'} in {cwd or 'an unknown folder'}, not "
                       f"{self.harness} in {self.code}. fm leaves it alone: rename or quit it, then run fm.")
        return a

    def strays(self) -> list:
        """Agents in the Firstmate checkout that do not carry the name: never guessed at."""
        agents = self.herdr.call("agent", "list").get("agents", [])
        return [a for a in agents if a.get("name") != NAME
                and _same(a.get("foreground_cwd") or a.get("cwd") or "", self.code)]


def _same(a: str, b: Path) -> bool:
    try:
        return bool(a) and os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def _lock(env):
    """One fm at a time per office: two quick launches must not start two Firstmates."""
    d = C.state_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / "fm.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise Fail("another fm is running for this office (a start or a restart). "
                   "Let it finish, then try again.")
    return f


# --- fm [args] --------------------------------------------------------------------------------


def launch(o: Office, args: list, out) -> dict:
    """Focus the office's Firstmate, or start it. Returns the server status."""
    o.check_paths()
    srv = o.running()
    a = o.agent()
    if a:
        if args:
            raise Fail(f"Firstmate is already running (pane {a['pane_id']}), so these arguments "
                       "would not reach it. Quit it first, then run fm with them.")
        o.herdr.call("agent", "focus", NAME)
        print(f"fm: Firstmate is running in pane {a['pane_id']}; focused it.", file=out)
        return srv
    strays = o.strays()
    if strays:
        lines = "".join(f"\n  pane {s.get('pane_id')}: {s.get('agent')}"
                        + (f" named {s['name']}" if s.get("name") else "") for s in strays)
        raise Fail(f"an agent already runs in {o.code} without the name '{NAME}':{lines}\n"
                   "fm does not guess which one is Firstmate, and does not start a second. To make "
                   f"one of them the office's Firstmate:\n  herdr --session {o.session} agent rename "
                   f"<pane> {NAME}")
    where = ["--cwd", str(o.code), "--label", NAME, "--focus"]
    if o.home is not None:
        where += ["--env", f"FM_HOME={o.home}"]
    # a fresh session has no workspace, and a tab needs one
    if o.herdr.call("workspace", "list").get("workspaces"):
        made = o.herdr.call("tab", "create", *where)
    else:
        made = o.herdr.call("workspace", "create", *where)
    pane = made["root_pane"]["pane_id"]
    try:
        o.herdr.call("agent", "start", NAME, "--kind", o.harness, "--pane", pane,
                     "--timeout", str(START_TIMEOUT_MS), "--", *args)
    except HerdrError as e:
        if e.code == "agent_not_ready":
            print(f"fm: started Firstmate in pane {pane}. It is asking something before it is "
                  "ready (a folder trust question, say): answer it there.", file=out)
            return srv
        raise Fail(f"Firstmate did not start in pane {pane}: {e}. The pane is left open to read.")
    print(f"fm: started Firstmate in pane {pane}, herdr session '{o.session}'.", file=out)
    return srv


def _show(o: Office, srv: dict, out) -> list | None:
    """The attach to run when this terminal is not already looking at the office's session."""
    if o.env.get("HERDR_ENV") == "1":
        if o.env.get("HERDR_SOCKET_PATH") and _same(o.env["HERDR_SOCKET_PATH"], Path(srv.get("socket", ""))):
            return None
        print(f"fm: this pane is in another herdr session. To see Firstmate: herdr session attach "
              f"{o.session}", file=out)
        return None
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ["herdr", "session", "attach", o.session]
    print(f"fm: to see Firstmate: herdr session attach {o.session}", file=out)
    return None


# --- fm restart -------------------------------------------------------------------------------


def _request(nonce: str) -> str:
    # The answer line is asked for in two parts, so the prompt echoed on screen never contains it
    return (f"/stow When the pass and its completion receipt are done, end your reply with one line "
            f"on its own: the text {MARK} immediately followed by reset-safe-{nonce} if the receipt "
            f"says this session is safe to reset, or by not-safe-{nonce} if it does not.")


def restart(o: Office, args: list, out) -> int:
    minutes = STOW_MINUTES
    if args[:1] == ["--timeout"] and len(args) == 2 and args[1].isdigit() and 0 < int(args[1]) <= 1440:
        minutes = int(args[1])
    elif args:
        raise Usage("fm restart takes only --timeout MINUTES (1 to 1440)")
    if o.harness != "claude":
        raise Fail(f"fm restart is built and tested for harness claude only; firstmate.harness is "
                   f"{o.harness}. Ask Firstmate to /stow, check its receipt, then start a new session.")
    o.running()
    a = o.agent()
    if not a:
        raise Fail(f"no Firstmate is running in herdr session '{o.session}': nothing to restart. "
                   "Start it with: fm")
    pane = a["pane_id"]
    state = a.get("agent_status")
    if state == "blocked":
        raise Fail("Firstmate is waiting for an answer in its pane. Answer it, then run fm restart "
                   "again. Nothing was sent.")
    if state == "working":
        print("fm: Firstmate is busy; waiting for its turn to end.", file=out)
    try:
        if state not in ("idle", "done"):
            got = o.herdr.call("agent", "wait", NAME, "--timeout", str(minutes * 60_000))
            if (got.get("agent") or {}).get("agent_status") == "blocked":
                raise Fail("Firstmate stopped to ask something. Answer it in its pane, then run fm "
                           "restart again. Nothing was sent.")
        nonce = secrets.token_hex(6)
        print(f"fm: asking Firstmate to save its work (/stow), up to {minutes} minutes. "
              "Ctrl-C cancels; nothing is reset until the save is confirmed.", file=out)
        try:
            got = o.herdr.call("agent", "prompt", NAME, _request(nonce), "--wait",
                               "--timeout", str(minutes * 60_000))
        except HerdrError as e:
            if e.code == "timeout":
                raise Fail(f"the save did not finish within {minutes} minutes. Nothing was reset. "
                           "Firstmate may still be saving: watch its pane, then run fm restart again.")
            if e.code == "agent_prompt_stalled":
                raise Fail("Firstmate did not start the save. Nothing was reset.")
            raise Fail(f"could not ask Firstmate to save: {e}. Nothing was reset.")
        if (got.get("agent") or {}).get("agent_status") == "blocked":
            raise Fail("Firstmate stopped to ask something during the save. Nothing was reset. "
                       "Answer it in its pane, then run fm restart again.")
        text = o.herdr.text("agent", "read", NAME, "--source", "recent-unwrapped", "--lines", "400")
        if f"{MARK}not-safe-{nonce}" in text:
            raise Fail("Firstmate says this session is not safe to reset yet: read its receipt in "
                       "its pane. Nothing was reset.")
        if f"{MARK}reset-safe-{nonce}" not in text:
            raise Fail("Firstmate's answer has no result line, so fm cannot tell whether the save "
                       "worked. Nothing was reset: read its receipt in its pane.")
        print("fm: Firstmate saved its work and says it is safe to reset.", file=out)
    except KeyboardInterrupt:
        print("\nfm: cancelled. Nothing was reset. A save already asked for keeps running in "
              "Firstmate.", file=out)
        return 130
    # The save was confirmed for this agent: if another one holds the name now, reset nothing
    now = o.agent()
    if not now or now.get("pane_id") != pane:
        raise Fail("Firstmate changed while it was saving. Nothing was reset.")
    try:
        o.herdr.call("agent", "prompt", NAME, "/clear")
        o.herdr.call("agent", "wait", NAME, "--timeout", str(RESET_TIMEOUT_MS))
    except HerdrError as e:
        raise Fail(f"the save worked, but the reset did not: {e}. Check Firstmate's pane.")
    print("fm: sent /clear. Firstmate starts a fresh conversation and runs its startup again. "
          "This resets the conversation only: to reload launch-time wiring (hooks, model, flags), "
          "quit Firstmate and run fm.", file=out)
    return 0


class Usage(Exception):
    pass


def main(argv, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    if argv[:1] in (["-h"], ["--help"], ["help"]):
        print(USAGE, file=out)
        return 0
    restarting = argv[:1] == ["restart"]
    args = argv[1:] if restarting or argv[:1] == ["--"] else argv
    path = C.config_path(env)
    try:
        o = Office(C.load(path), env)
    except C.ConfigError as e:
        print(f"fm: problems in {path}:", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        return 1
    attach = None
    try:
        lock = _lock(env)
        try:
            if restarting:
                return restart(o, args, out)
            attach = _show(o, launch(o, args, out), out)
        finally:
            lock.close()
    except Usage as e:
        print(f"fm: {e}\n{USAGE}", file=err)
        return 2
    except (Fail, HerdrError) as e:
        print(f"fm: {e}", file=err)
        return 1
    if attach:
        os.execvpe(attach[0], attach, {k: v for k, v in env.items() if k != "HERDR_SOCKET_PATH"})
    return 0
