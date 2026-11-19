"""office remote: can a phone reach the running office, and how. Read-only.

There is no office server to reach. A phone gets in two ways, and this checks both:

- Remote Control, first: Claude Code's own phone path. Firstmate started with
  `--remote-control <name>` (firstmate.remote_control) registers a session that the Claude app
  lists under that name, with push notifications. Only Firstmate carries it: one entry on the
  phone, not one per worker. It needs a Claude Code that has the flag, a claude.ai sign-in (an
  API key cannot), and the running Firstmate started with it.
- SSH, the fallback: a terminal app logs in to this machine over a private network (Tailscale is
  the one checked here), and `office on` there attaches to the session that already runs. herdr
  takes more than one client, so the terminal at the desk stays attached.

So this command turns nothing on. It never starts an SSH server, joins a network, opens a port,
writes a key or signs in: each of those is a choice the user makes in the tool that owns it. It
checks what each path needs and prints what to do on the phone, or what is missing.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import socket
import subprocess
import sys

from . import config as C
from . import fm
from . import lifecycle

SSH_PORT = 22
# The Mac App Store and standalone Tailscale apps put their CLI inside the app, not on PATH
TAILSCALE_APP = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
USAGE = "usage: office remote    read-only: can your phone reach the running office, and how"
RC_FLAG = "--remote-control"


def _claude(env, *args) -> str | None:
    """What `claude <args>` prints, or None when it does not run or fails."""
    exe = shutil.which("claude", path=env.get("PATH"))
    if exe is None:
        return None
    try:
        r = subprocess.run([exe, *args], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _rc_name(argv: list) -> str | None:
    """The Remote Control name in a harness argv: "" when the flag has no name, None without it."""
    for i, a in enumerate(argv):
        if a == RC_FLAG:
            nxt = argv[i + 1] if i + 1 < len(argv) else ""
            return "" if nxt.startswith("-") else nxt
        if a.startswith(RC_FLAG + "="):
            return a[len(RC_FLAG) + 1:]
    return None


def remote_control(cfg: dict, env, running) -> tuple:
    """The Remote Control path: ([(label, value)], [what is missing]), and the name when it is ready."""
    name = cfg["firstmate"].get("remote_control") or None
    if not name:
        return [("setting", "off (firstmate.remote_control)")], [
            'Set firstmate.remote_control = "firstmate" in your config.toml, quit Firstmate and run fm: '
            "Firstmate then starts with Remote Control, and the Claude app on your phone lists it."], None
    facts, todo = [("setting", f'firstmate.remote_control = "{name}"')], []
    helped = _claude(env, "--help")
    if helped is None:
        facts.append(("claude", "did not answer `claude --help`"))
        todo.append("Install Claude Code here (`office tools`), or check that `claude --help` runs.")
    elif RC_FLAG not in helped:
        facts.append(("claude", f"has no {RC_FLAG}: too old"))
        todo.append("Update Claude Code (`claude update`): this version has no Remote Control.")
    else:
        facts.append(("claude", f"has {RC_FLAG}"))
    try:
        auth = json.loads(_claude(env, "auth", "status", "--json") or "")
    except ValueError:
        auth = None
    if not isinstance(auth, dict):
        facts.append(("sign-in", "unknown: `claude auth status` did not answer"))
        todo.append("Check `claude auth status`: Remote Control needs a claude.ai sign-in.")
    elif not auth.get("loggedIn"):
        facts.append(("sign-in", "not signed in"))
        todo.append("Sign in with your claude.ai account: `claude auth login`.")
    elif auth.get("authMethod") != "claude.ai":
        facts.append(("sign-in", f"{auth.get('authMethod') or 'unknown'}, not a claude.ai account"))
        todo.append("Remote Control needs a claude.ai account, not an API key: `claude auth login`.")
    else:
        facts.append(("sign-in", "a claude.ai account"))
    on = None
    if running is True:
        o = fm.Office(cfg, env, "office remote")
        try:
            a = o.agent()
            got = o.herdr.call("pane", "process-info", "--pane", a["pane_id"]) if a else {}
        except (fm.Fail, fm.HerdrError) as e:
            facts.append(("firstmate", "unknown"))
            todo.append(f"herdr did not say how Firstmate runs: {e}")
        else:
            procs = (got.get("process_info") or {}).get("foreground_processes") or []
            names = [n for n in (_rc_name(p.get("argv") or []) for p in procs if isinstance(p, dict)) if n is not None]
            if not a:
                facts.append(("firstmate", "not running"))
                todo.append("Start Firstmate with `fm` (or `office on`): it starts with Remote Control.")
            elif not names:
                facts.append(("firstmate", f"pane {a['pane_id']}, started without {RC_FLAG}"))
                todo.append("Firstmate started before Remote Control was set: quit it in its pane, then run `fm`.")
            else:
                on = names[0] or name
                facts.append(("firstmate", f"pane {a['pane_id']}, Remote Control on as `{on}`"))
    elif running is False:
        facts.append(("firstmate", "the office is not running"))
        todo.append("Start the office at this machine with `office on`: Firstmate starts with Remote Control.")
    else:
        facts.append(("firstmate", "unknown: herdr did not say whether the office runs"))
        todo.append("Check that herdr works here: whether Firstmate runs with Remote Control is unknown.")
    return facts, todo, (on if not todo else None)


def _ssh(port: int) -> bool:
    """Whether something answers on the SSH port of this machine. A listener is all a check from
    the inside can see: it cannot prove the phone's network reaches it."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _tailscale(env) -> tuple:
    """(state, name, address): state is None when there is no tailscale command."""
    exe = shutil.which("tailscale", path=env.get("PATH")) or (
        TAILSCALE_APP if os.access(TAILSCALE_APP, os.X_OK) else None)
    if exe is None:
        return None, "", ""
    try:
        r = subprocess.run([exe, "status", "--json"], env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown", "", ""
    # A CLI older than its daemon prints a version warning on stdout before the JSON
    text = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else ""
    try:
        st = json.loads(text)
    except ValueError:
        return "unknown", "", ""
    me = st.get("Self") or {}
    ips = me.get("TailscaleIPs") or []
    return str(st.get("BackendState") or "unknown"), str(me.get("DNSName") or "").rstrip("."), \
        str(ips[0]) if ips else ""


def run(args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    if args:
        print(USAGE, file=err)
        return 2
    cfg = lifecycle._load(env, "office remote", err)
    if cfg is None:
        return 1
    session = cfg["office"]["session"]
    mac = sys.platform == "darwin"
    todo = []

    try:
        running = fm.Herdr(session, env).server().get("running")
    except fm.Fail as e:
        running = None
        todo.append(str(e))
    if running is True:
        office = f"herdr session '{session}' is running"
    elif running is None:
        office = "unknown"
        if not todo:
            todo.append(f"herdr did not say whether session '{session}' runs (`herdr --session {session} "
                        "status`): check that herdr works here.")
    else:
        office = f"herdr session '{session}' is not running"
        # A server takes the environment of the shell that starts it and hands it to every agent.
        # Started from an SSH login, that is the SSH session's, and on macOS an agent there may
        # not reach the login keychain its sign-in is in.
        todo.append("Start the office at this machine with `office on`, not from the phone: "
                    "the phone only attaches to it.")

    rc_facts, rc_todo, rc = remote_control(cfg, env, running)

    ssh = _ssh(SSH_PORT)
    if not ssh:
        todo.append(
            ("Turn on Remote Login in System Settings > General > Sharing, and under its (i) allow "
             "only your own user. " if mac else "Install and start the OpenSSH server (openssh-server). ")
            + f"That listens on port {SSH_PORT} on every network this machine joins: use key "
            "sign-in, and never forward that port to the internet.")

    state, name, addr = _tailscale(env)
    if state is None:
        net = "no tailscale command"
        todo.append("Install Tailscale on this machine and on your phone, signed in to the same "
                    "account (https://tailscale.com/download). office remote checks only Tailscale; "
                    "another private network works the same, but it cannot check one.")
    elif state != "Running" or not (name or addr):
        net = f"Tailscale is {state}" if state != "Running" else "Tailscale gave no name for this machine"
        todo.append("Connect Tailscale on this machine (`tailscale up`, or its menu bar app), and on your phone.")
    else:
        net = f"running: this machine is {name or addr}" + (f" ({addr})" if name and addr else "")

    print("office remote: read-only. It turns nothing on and opens no port.", file=out)
    print("Remote Control, in the Claude app (the first way):", file=out)
    for label, value in rc_facts:
        print(f"  {label.ljust(10)}  {value}", file=out)
    if rc:
        print(f"Remote Control is ready. On your phone: open the Claude app, go to Code, and open `{rc}`.", file=out)
        print("  For pushes when Firstmate needs you: in Firstmate, run /config and turn on "
              "\"Push when Claude decides\".", file=out)
    elif cfg["firstmate"].get("remote_control"):
        print("Remote Control is not ready. To get there:", file=out)
    for t in rc_todo:
        print(f"  - {t}", file=out)
    print(file=out)
    print("SSH, from a terminal app (the fallback):", file=out)
    print(f"  office      {office}", file=out)
    print(f"  ssh         {'something answers' if ssh else 'nothing answers'} on port {SSH_PORT} "
          "of this machine", file=out)
    print(f"  tailscale   {net}", file=out)
    if todo:
        print("Not ready. To get there:", file=out)
        for t in todo:
            print(f"  - {t}", file=out)
        return 0 if rc else 1
    here = shutil.which("office", path=env.get("PATH"))
    cmd = "office on" if here else f"{C.REPO / 'bin' / 'office'} on"
    print("Ready. On your phone, in an SSH app (Blink, Termius, or any other), on Tailscale:", file=out)
    print(f"  ssh {getpass.getuser()}@{name or addr}", file=out)
    print(f"  {cmd}", file=out)
    print("That attaches the phone to the running office, and the terminal here stays attached. "
          f"To leave, press {lifecycle._detach_key(cfg)}, or close the app: everything keeps running. "
          "office break detaches the phone too.", file=out)
    return 0
