"""office remote: can a phone reach the running office, and how. Read-only.

There is no office server to reach. A phone gets in the way a second terminal does: an SSH app
logs in to this machine over a private network (Tailscale is the one checked here), and
`office on` there attaches to the session that already runs. herdr takes more than one client,
so the terminal at the desk stays attached, and closing the phone's app only detaches it.

So this command turns nothing on. It never starts an SSH server, joins a network, opens a port
or writes a key: each of those is a choice the user makes in the tool that owns it. It checks
the three things the path needs and prints what to type on the phone, or what is missing.
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
    print(f"  office      {office}", file=out)
    print(f"  ssh         {'something answers' if ssh else 'nothing answers'} on port {SSH_PORT} "
          "of this machine", file=out)
    print(f"  tailscale   {net}", file=out)
    if todo:
        print("Not ready. To get there:", file=out)
        for t in todo:
            print(f"  - {t}", file=out)
        return 1
    here = shutil.which("office", path=env.get("PATH"))
    cmd = "office on" if here else f"{C.REPO / 'bin' / 'office'} on"
    print("Ready. On your phone, in an SSH app (Blink, Termius, or any other), on Tailscale:", file=out)
    print(f"  ssh {getpass.getuser()}@{name or addr}", file=out)
    print(f"  {cmd}", file=out)
    print("That attaches the phone to the running office, and the terminal here stays attached. "
          f"To leave, press {lifecycle._detach_key(cfg)}, or close the app: everything keeps running. "
          "office break detaches the phone too.", file=out)
    return 0
