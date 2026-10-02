"""One config in, herdr's native config out.

The user's ~/.config/agent-office/config.toml overrides config/defaults.toml. Agent Office's own
keys are checked here and an unknown one is an error; [herdr] is merged over the preset and
passed through, and herdr itself checks it (`herdr config check`), because herdr is the only
thing that knows its keys.

Values are data: nothing read here is ever handed to a shell. A path may start with ~/ and that
is the only expansion; "$HOME" or "$(...)" stay literal characters.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11: the same parser, vendored (lib/vendor/tomli, MIT)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))
    import tomli as tomllib

REPO = Path(__file__).resolve().parents[2]
DEFAULTS = REPO / "config" / "defaults.toml"
STARTER = REPO / "config" / "config.toml"
PRESET = REPO / "preset" / "herdr" / "config.toml"
PRESET_SOUNDS = REPO / "preset" / "herdr" / "sounds"
SCHEMA = 1


class ConfigError(Exception):
    """Every problem found, one per line, so a user fixes them all in one go."""

    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = list(problems)


def home(env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("HOME") or Path.home())


def _xdg(env, var, fallback) -> Path:
    # XDG says a relative value is invalid and must be ignored
    v = env.get(var, "")
    return Path(v) if v.startswith("/") else home(env) / fallback


def config_path(env=None) -> Path:
    env = os.environ if env is None else env
    return _xdg(env, "XDG_CONFIG_HOME", ".config") / "agent-office" / "config.toml"


def state_dir(env=None) -> Path:
    env = os.environ if env is None else env
    return _xdg(env, "XDG_STATE_HOME", ".local/state") / "agent-office"


def herdr_dirs(env=None) -> tuple[Path, Path]:
    """herdr's own config and state folders: its plugins.json, and each plugin's state folder."""
    env = os.environ if env is None else env
    return _xdg(env, "XDG_CONFIG_HOME", ".config") / "herdr", _xdg(env, "XDG_STATE_HOME", ".local/state") / "herdr"


def expand(p: str, env=None) -> Path:
    """A config path as a real path: a leading ~/ is your home, nothing else is expanded."""
    return home(env) / p[2:] if p == "~" or p.startswith("~/") else Path(p)


# --- the keys Agent Office owns -------------------------------------------------------------


def _text(v):
    if not isinstance(v, str) or not v.strip():
        return "must be a non-empty string"
    if any(ord(c) < 32 or ord(c) == 127 for c in v):
        return "must not contain control characters"
    return None


def _path(v):
    err = _text(v)
    if err:
        return err
    if not (v.startswith("/") or v == "~" or v.startswith("~/")):
        return "must be an absolute path or start with ~/"
    return None


def _session(v):
    # a herdr session name ends up in a socket path and on the command line: keep it plain
    if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", v):
        return "must be 1-64 letters, digits, '.', '_' or '-', starting with a letter or digit"
    return None


def _one_of(*allowed):
    def check(v):
        return None if v in allowed else "must be one of: " + ", ".join(f'"{a}"' for a in allowed)
    return check


def _boolean(v):
    return None if isinstance(v, bool) else "must be true or false"


def _int_in(lo, hi):
    def check(v):
        # bool is an int in Python; `true` is not a number of seconds
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return f"must be a whole number from {lo} to {hi}"
        return None
    return check


KEYS = {
    "office": {"session": _session},
    "firstmate": {
        "source": _text,
        "code": _path,
        "home": _path,
        "harness": _one_of("claude", "codex"),
    },
    "treehouse": {"root": _path},
    "meter": {
        "enabled": _boolean,
        "interval_seconds": _int_in(5, 3600),
        "warn_tokens": _int_in(1000, 100_000_000),
        "alarm_tokens": _int_in(1000, 100_000_000),
    },
}


def _check(data, where):
    problems = []
    for key, value in data.items():
        if key == "schema":
            if isinstance(value, bool) or value != SCHEMA:
                problems.append(f"{where}: schema must be {SCHEMA}")
        elif key == "herdr":
            if not isinstance(value, dict):
                problems.append(f"{where}: herdr must be a table, [herdr]")
        elif key in KEYS:
            if not isinstance(value, dict):
                problems.append(f"{where}: {key} must be a table, [{key}]")
                continue
            for sub, v in value.items():
                check = KEYS[key].get(sub)
                if check is None:
                    problems.append(f"{where}: unknown key {key}.{sub}")
                else:
                    err = check(v)
                    if err:
                        problems.append(f"{where}: {key}.{sub} {err}")
        else:
            problems.append(f"{where}: unknown key {key}")
    return problems


def read_toml(path: Path, where: str) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError([f"{where}: not valid TOML: {e}"])
    except OSError as e:
        raise ConfigError([f"{where}: cannot read: {e.strerror}"])


def merge(base: dict, over: dict) -> dict:
    """A table merges key by key; any other value, arrays included, replaces the base's."""
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def effective(user: dict | None, where: str) -> dict:
    """Defaults, then the user's file over them. Raises ConfigError listing every problem."""
    defaults = read_toml(DEFAULTS, str(DEFAULTS))
    problems = _check(defaults, str(DEFAULTS))
    if user is not None:
        if "schema" not in user:
            problems.append(f"{where}: schema is missing: the first line must be schema = {SCHEMA}")
        problems += _check(user, where)
    out = merge(defaults, {k: v for k, v in (user or {}).items() if k != "herdr"})
    meter = out.get("meter", {})
    if not problems and meter.get("warn_tokens", 0) >= meter.get("alarm_tokens", 0):
        problems.append(f"{where}: meter.warn_tokens must be below meter.alarm_tokens")
    if problems:
        raise ConfigError(problems)
    out["herdr"] = merge(read_toml(PRESET, str(PRESET)), (user or {}).get("herdr", {}))
    return out


def load(path: Path) -> dict:
    """The effective config for the file at path; a missing file means the defaults."""
    if not path.exists() and not path.is_symlink():
        return effective(None, str(path))
    return effective(read_toml(path, str(path)), str(path))


# --- writing TOML -----------------------------------------------------------------------------
# The standard library reads TOML but does not write it. herdr's config needs only plain values,
# arrays and tables, so this writes exactly those and refuses the rest rather than guess.

_BARE = re.compile(r"[A-Za-z0-9_-]+")
_ESC = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _quote(s: str) -> str:
    return '"' + "".join(
        _ESC.get(c) or (f"\\u{ord(c):04x}" if ord(c) < 32 or ord(c) == 127 else c) for c in s
    ) + '"'


def _key(k: str) -> str:
    return k if _BARE.fullmatch(k) else _quote(k)


def _value(v, where) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return repr(v)
    if isinstance(v, str):
        return _quote(v)
    if isinstance(v, list):
        return "[" + ", ".join(_value(x, where) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ " + ", ".join(f"{_key(k)} = {_value(x, where + '.' + k)}" for k, x in v.items()) + " }"
    raise ConfigError([f"{where}: a {type(v).__name__} value is not supported in [herdr]"])


def dumps(data: dict, where: str = "herdr") -> str:
    lines = []

    def table(d, path):
        plain = [(k, v) for k, v in d.items() if not isinstance(v, dict)]
        subs = [(k, v) for k, v in d.items() if isinstance(v, dict)]
        if path and (plain or not subs):
            lines.extend(["", "[" + ".".join(_key(p) for p in path) + "]"])
        for k, v in plain:
            lines.append(f"{_key(k)} = {_value(v, '.'.join([where, *path, k]))}")
        for k, v in subs:
            table(v, path + [k])

    table(data, [])
    text = "\n".join(lines).lstrip("\n") + "\n"
    if tomllib.loads(text) != data:  # a writer bug must not reach herdr as a silent change
        raise ConfigError([f"{where}: the generated TOML does not read back the same (a bug)"])
    return text


HEADER = """\
# Generated by Agent Office. Do not edit: `office install` regenerates it, and asks before it
# replaces a file that was changed by hand. Edit ~/.config/agent-office/config.toml instead:
# its [herdr] keys are merged over the Agent Office preset (preset/herdr/config.toml).

"""


def herdr_config(cfg: dict) -> str:
    return HEADER + dumps(cfg["herdr"])


def meter_path(env=None) -> Path:
    """Where the meter plugin reads its settings: herdr/meter looks in the same place."""
    return state_dir(env) / "meter.json"


def meter_settings(cfg: dict) -> str:
    """[meter] as the meter reads it. JSON, because the meter is sh and jq has no TOML."""
    m = cfg["meter"]
    keys = ("enabled", "interval_seconds", "warn_tokens", "alarm_tokens")
    return json.dumps({"schema": 1, **{k: m[k] for k in keys}}, indent=2) + "\n"


def herdr_check(text: str) -> tuple[bool, str]:
    """Ask herdr itself. It reads the file and talks to no server.

    The file sits in a scratch folder with the preset's sounds next to it, because herdr
    resolves a relative sound path from the config's own folder, as it will where it is written.
    """
    with tempfile.TemporaryDirectory(prefix="agent-office-check.") as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text(text)
        sounds = Path(tmp) / "sounds"
        sounds.mkdir()
        for f in PRESET_SOUNDS.iterdir():
            (sounds / f.name).write_bytes(f.read_bytes())
        env = dict(os.environ, HERDR_CONFIG_PATH=str(cfg))
        try:
            got = subprocess.run(["herdr", "config", "check"], env=env, capture_output=True, text=True)
        except FileNotFoundError:
            return False, "herdr is not installed, so its config cannot be checked (https://herdr.dev)"
        out = (got.stdout + got.stderr).strip()
        return got.returncode == 0, out.replace(str(cfg), "<generated config>")
