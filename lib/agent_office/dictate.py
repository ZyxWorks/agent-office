"""office dictate: push-to-talk dictation into the focused pane, on this machine only.

Off by default. One key press starts a recording, the next stops it: whisper.cpp turns it into
text on this machine and herdr types the text into the pane that has the focus then. herdr runs a
key's action once per press and has no key-up event, so "push to talk" is press, talk, press.

Nothing leaves the machine. sox's `rec` records from the default microphone into a file in the
state folder, `whisper-cli` reads that file with a model file you downloaded, and `herdr pane
send-text` types the words. No other program runs, this module imports nothing that talks to a
network, and there is no fallback to any service. The recording is deleted after it is read.

The text is typed, never submitted: there is no Enter, and a line break in the transcript becomes
a space, so a shell or an agent waits for you to read it first.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import config as C

USAGE = """\
usage: office dictate [--pane PANE]   start recording; run again to stop and type the text
       office dictate cancel           stop recording and throw it away

Bound to prefix+m in the preset. Off until [dictate] enabled = true in your config.
Without a pane (outside herdr, or no --pane) the text is printed instead of typed."""
# a recording that stopped at max_seconds and was never collected: past this, it is stale
STALE_SECONDS = 600


def _herdr(env) -> str:
    return env.get("HERDR_BIN_PATH") or "herdr"


def _say(env, message: str, err):
    """One line on herdr's notification, and on stderr for a run from a shell."""
    print(f"dictate: {message}", file=err)
    try:
        subprocess.run([_herdr(env), "notification", "show", "Dictation", "--body", message, "--sound", "none"],
                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        pass  # outside herdr there is no notification; stderr said it


def _paths(env) -> tuple[Path, Path, Path]:
    # one recording per herdr server: named herdr sessions each have their own socket
    key = hashlib.sha256(env.get("HERDR_SOCKET_PATH", "default").encode()).hexdigest()[:12]
    d = C.state_dir(env) / "dictate"
    return d / f"{key}.json", d / f"{key}.wav", d / f"{key}.log"


def _ours(pid, wav: Path) -> bool:
    """The recorder is still running. A recycled pid is not ours, so ask what it runs."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False  # someone else's process now
    try:
        args = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True,
                              timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return str(wav) in args


def _stop(pid, wav: Path):
    """SIGINT, which sox takes as "finish the file": the WAV header is written on the way out."""
    for sig, wait in ((signal.SIGINT, 5.0), (signal.SIGTERM, 2.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if not _ours(pid, wav):
                return
            time.sleep(0.05)


def _forget(*paths: Path):
    for p in paths:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def clean(out: str) -> str:
    """whisper-cli's text as one line to type: no [BLANK_AUDIO]-style marks, no control characters.

    A line break typed into a shell runs the line, so every line break becomes a space."""
    text = re.sub(r"\[[^\]]*\]", " ", out)
    text = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in text)
    return re.sub(r"\s+", " ", text).strip()


def _start(cfg, env, rec_json: Path, wav: Path, log: Path, err) -> int:
    rec_json.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(rec_json.parent, 0o700)  # what you said is private
    _forget(wav)
    limit = cfg["max_seconds"]
    argv = [shutil.which("rec", path=env.get("PATH", "")) or "rec", "-q", "-c", "1", "-r", "16000", "-b", "16",
            str(wav), "trim", "0", str(limit)]
    with open(log, "wb") as logf:
        try:
            # its own session: the key's action exits now, and the recorder must outlive it
            p = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=logf, start_new_session=True)
        except OSError as e:
            _say(env, f"could not start rec: {e.strerror}", err)
            return 1
    C.write_json(rec_json, {"schema": 1, "pid": p.pid, "wav": str(wav), "started": int(time.time())})
    time.sleep(0.3)
    if p.poll() is not None:
        # it gave up at once: no microphone, or no permission to use it
        why = [l for l in log.read_text(errors="replace").splitlines() if l.strip()]
        _forget(rec_json, wav)
        _say(env, "rec stopped at once" + (f": {why[-1].strip()}" if why else ""), err)
        return 1
    _say(env, f"recording. Press the key again to type it (stops by itself after {limit}s)", err)
    return 0


def _finish(cfg, env, rec_json: Path, wav: Path, log: Path, pane: str, out, err) -> int:
    _forget(rec_json, log)
    if not wav.exists() or wav.stat().st_size <= 44:  # 44 bytes is a WAV header and no sound
        _forget(wav)
        _say(env, "nothing was recorded", err)
        return 1
    _say(env, "transcribing on this machine", err)
    argv = [shutil.which("whisper-cli", path=env.get("PATH", "")) or "whisper-cli",
            "-m", str(C.expand(cfg["model"], env)), "-l", cfg["language"], "-nt", "-np", "-f", str(wav)]
    try:
        r = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=300, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        _say(env, f"whisper-cli did not run: {e}", err)
        return 1
    finally:
        _forget(wav)
    if r.returncode != 0:
        why = [l for l in r.stderr.splitlines() if l.strip()]
        _say(env, f"whisper-cli failed (exit {r.returncode})" + (f": {why[-1].strip()}" if why else ""), err)
        return 1
    text = clean(r.stdout)
    if not text:
        _say(env, "heard nothing to type", err)
        return 0
    if not pane:
        print(text, file=out)
        return 0
    try:
        sent = subprocess.run([_herdr(env), "pane", "send-text", pane, "--", text], env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        sent = None
        why = str(e)
    if sent is None or sent.returncode != 0:
        if sent is not None:
            why = (sent.stderr or sent.stdout).strip() or f"exit {sent.returncode}"
        _say(env, f"herdr did not type it into {pane}: {why}", err)
        print(text, file=out)  # the words are not lost
        return 1
    return 0


def _missing(cfg, env) -> list:
    path = env.get("PATH", "")
    missing = [f"{c} is not on PATH ({how})" for c, how in (("rec", "brew install sox"),
                                                            ("whisper-cli", "brew install whisper.cpp"))
               if not shutil.which(c, path=path)]
    model = C.expand(cfg["model"], env)
    if not model.is_file():
        missing.append(f"no model file at {cfg['model']} (README, \"Dictation\")")
    return missing


def run(args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    cancel = args[:1] == ["cancel"]
    rest = args[1:] if cancel else args
    pane = env.get("HERDR_ACTIVE_PANE_ID") or env.get("HERDR_PANE_ID") or ""
    if rest[:1] == ["--pane"] and len(rest) == 2 and rest[1].strip():
        pane = rest[1]
    elif rest:
        print(USAGE, file=err)
        return 2
    path = C.config_path(env)
    try:
        cfg = C.load(path)["dictate"]
    except C.ConfigError as e:
        print(f"dictate: problems in {path}", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        return 1
    rec_json, wav, log = _paths(env)
    rec = C.read_json(rec_json)
    running = rec is not None and _ours(rec.get("pid"), wav)
    if cancel:
        if rec is not None:
            if running:
                _stop(rec.get("pid"), wav)
            _forget(rec_json, wav, log)
            _say(env, "recording thrown away", err)
        else:
            _say(env, "no recording to throw away", err)
        return 0
    if not cfg.get("enabled"):
        _say(env, "off. Turn it on with [dictate] enabled = true in your config (README, \"Dictation\")", err)
        return 1
    missing = _missing(cfg, env)
    if missing:
        _say(env, "cannot start: " + "; ".join(missing), err)
        return 1
    if rec is not None:
        # running: stop it and type it. Already stopped, at max_seconds: type it too, unless it
        # was left so long ago that the press is meant to start a new one
        if running:
            _stop(rec.get("pid"), wav)
        started = rec.get("started") if isinstance(rec.get("started"), int) else 0
        if running or time.time() - started <= cfg["max_seconds"] + STALE_SECONDS:
            return _finish(cfg, env, rec_json, wav, log, pane, out, err)
        _forget(rec_json, wav)
    return _start(cfg, env, rec_json, wav, log, err)
