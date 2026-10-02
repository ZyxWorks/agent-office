"""office notify: push one line to your phone through the provider in [notify].

Off by default, and the URL comes only from your own config.toml, so the package never knows
where your notifications go. Quiet mode lets "needs you" through and holds everything else: an
agent waiting on you is the one thing worth a buzz at any hour.

herdr/notify calls this when herdr reports an agent as blocked (waiting on a prompt, herdr's
"needs you"). Anything else that knows a PR is ready, Firstmate included, calls
`office notify pr-ready <url>`.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

from . import config as C

# kind -> (title, ntfy priority, ntfy tag). Titles are ASCII on purpose: ntfy reads its Title
# header as Latin-1, and a header that cannot encode fails the whole send.
KINDS = {
    "needs-you": ("Agent Office: needs you", "high", "bell"),
    "pr-ready": ("Agent Office: PR ready", "default", "white_check_mark"),
}
USAGE = "usage: office notify needs-you|pr-ready <message>"


def _ntfy(url: str, kind: str, message: str, timeout=10):
    title, priority, tag = KINDS[kind]
    req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST", headers={
        "Title": title, "Priority": priority, "Tags": tag, "Content-Type": "text/plain; charset=utf-8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def run(args, out=sys.stdout, err=sys.stderr) -> int:
    if len(args) < 2 or args[0] not in KINDS or not " ".join(args[1:]).strip():
        print(USAGE, file=err)
        return 2
    kind, message = args[0], " ".join(args[1:]).strip()
    path = C.config_path()
    try:
        cfg = C.load(path).get("notify", {})
    except C.ConfigError as e:
        print(f"notify: problems in {path}", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        return 1
    if not cfg.get("enabled"):
        print("notify: off (notify.enabled is false), nothing sent", file=out)
        return 0
    if cfg.get("quiet") and kind != "needs-you":
        print(f"notify: quiet, {kind} not sent", file=out)
        return 0
    try:
        _ntfy(cfg["url"], kind, message)
    except (urllib.error.URLError, OSError, ValueError) as e:
        # the URL is private: say what failed, never where it was going
        if isinstance(e, urllib.error.HTTPError):
            reason = f"HTTP {e.code}"
        elif isinstance(e, ValueError):
            reason = "bad URL"
        else:
            reason = getattr(e, "reason", e)
        print(f"notify: {kind} not sent: {reason}", file=err)
        return 1
    print(f"notify: {kind} sent", file=out)
    return 0
