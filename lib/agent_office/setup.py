"""The agent working setup: setup/'s templates, filled in from your config.

setup/MANIFEST.toml lists every template, where it goes and how it is written (setup/README.md).
This module only reads and renders; it writes nothing. A placeholder is {{name}} or
{{name|words for when it is unset}}, where name is a config key: setup.*, firstmate.code,
firstmate.home or firstmate.harness. An unknown name, or an unset one with no words, is an
error, so a typo in a template never reaches a user's file as literal braces.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import config as C

SETUP = C.REPO / "setup"
MANIFEST = SETUP / "MANIFEST.toml"
KINDS = {
    "block": ("source", "target"),
    "json": ("source", "target"),
    "yaml": ("source", "target"),
    "owned": ("source", "target"),
    "starter": ("source", "target"),
    "link": ("target", "to"),
    "flags": ("target", "from"),
}
OPTIONAL = ("when", "mode", "harness", "why")

PLACEHOLDER = re.compile(r"\{\{([a-z_.]+)(?:\|([^{}]*))?\}\}")
# a value put into YAML must stay one plain scalar, whatever it is
_YAML_PLAIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:\[\]-]*")


def _leaves(spec, prefix):
    for k, v in spec.items():
        if isinstance(v, dict):
            yield from _leaves(v, f"{prefix}.{k}")
        else:
            yield f"{prefix}.{k}"


# Every name a template may use. setup.repos.protected is computed: the branches nobody pushes to.
NAMES = frozenset([*_leaves(C.KEYS["setup"], "setup"), "setup.repos.protected",
                   "firstmate.code", "firstmate.home", "firstmate.harness"])


def _text(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def values(cfg: dict, env=None) -> dict:
    """{name: text} for every placeholder name that has a value in this config."""
    out = {}

    def walk(d, prefix):
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v, f"{prefix}.{k}")
            else:
                out[f"{prefix}.{k}"] = _text(v)

    walk(cfg["setup"], "setup")
    fm = cfg["firstmate"]
    code = C.expand(fm["code"], env)
    out["firstmate.code"] = str(code)
    out["firstmate.home"] = str(C.expand(fm["home"], env)) if fm.get("home") else str(code)
    out["firstmate.harness"] = fm["harness"]
    repos = cfg["setup"]["repos"]
    branches = list(dict.fromkeys([repos["integration_branch"], repos["release_branch"]]))
    out["setup.repos.protected"] = " or ".join(branches)
    return out


def render(text: str, vals: dict, where: str, yaml: bool = False) -> str:
    problems = []

    def one(m):
        name, fallback = m.group(1), m.group(2)
        if name not in NAMES:
            problems.append(f"{where}: unknown placeholder {{{{{name}}}}}")
            return m.group(0)
        if name in vals:
            v = vals[name]
            if yaml and not _YAML_PLAIN.fullmatch(v):
                problems.append(f"{where}: {name} = {v!r} is not one plain word, so it cannot go into YAML")
            return v
        if fallback is not None:
            return fallback
        problems.append(f"{where}: {name} is unset and {{{{{name}}}}} has no words for that")
        return m.group(0)

    out = PLACEHOLDER.sub(one, text)
    if problems:
        raise C.ConfigError(problems)
    return out


def render_json(text: str, vals: dict, where: str) -> str:
    """JSON is parsed first and only its strings are filled in, so a value can never break it."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise C.ConfigError([f"{where}: not valid JSON: {e}"])

    def walk(v):
        if isinstance(v, str):
            return render(v, vals, where)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {render(k, vals, where): walk(x) for k, x in v.items()}
        return v

    return json.dumps(walk(data), indent=2, ensure_ascii=False) + "\n"


def manifest() -> list:
    """The entries of setup/MANIFEST.toml, checked. Raises ConfigError listing every problem."""
    data = C.read_toml(MANIFEST, str(MANIFEST))
    problems = []
    if data.get("schema") != 1:
        problems.append(f"{MANIFEST}: schema must be 1")
    entries = data.get("file", [])
    for i, e in enumerate(entries, 1):
        where = f"{MANIFEST}: file {i}"
        need = KINDS.get(e.get("kind"))
        if need is None:
            problems.append(f"{where}: kind must be one of: {', '.join(KINDS)}")
            continue
        for k in need:
            if not isinstance(e.get(k), str) or not e[k]:
                problems.append(f"{where}: {e['kind']} needs {k}")
        for k in e:
            if k != "kind" and k not in need and k not in OPTIONAL:
                problems.append(f"{where}: unknown key {k}")
        if "source" in e and isinstance(e["source"], str) and not (SETUP / e["source"]).is_file():
            problems.append(f"{where}: no template setup/{e['source']}")
        if "when" in e and e["when"] not in NAMES:
            problems.append(f"{where}: when names no config key: {e['when']}")
        if "from" in e and e["from"] not in NAMES:
            problems.append(f"{where}: from names no config key: {e['from']}")
        if "harness" in e and e["harness"] not in ("claude", "codex"):
            problems.append(f"{where}: harness must be claude or codex")
        if ("harness" in e) != isinstance(e.get("why"), str):
            problems.append(f"{where}: harness and why go together: why says what to do on another harness")
        if "mode" in e and not re.fullmatch(r"[0-7]{3}", str(e["mode"])):
            problems.append(f"{where}: mode must be three octal digits, say \"755\"")
    if problems:
        raise C.ConfigError(problems)
    return entries


def _target(t: str, vals: dict, where: str, env) -> Path:
    p = render(t, vals, where)
    if not (p.startswith("/") or p == "~" or p.startswith("~/")):
        raise C.ConfigError([f"{where}: target {p} is not an absolute path"])
    return C.expand(p, env)


def plan(cfg: dict, env=None) -> list:
    """Every write `office setup` would make for this config, in manifest order.

    Each item is a dict: kind, target (a Path), and by kind content (the rendered text), to (the
    link's target, a Path), names (the flag files) and mode (an int, for owned files). An entry
    for another harness is kind "skip" with why: it is not written, and why says what to do.
    """
    harness = cfg["firstmate"]["harness"]
    models = cfg["setup"]["models"]
    missing = [f"setup.models.{m}.{k}" for m in ("default", "mechanical") for k in ("model", "effort")
               if k not in models.get(m, {})]
    if harness != "claude" and missing:
        raise C.ConfigError([f"firstmate.harness is {harness}, and the shipped models are Claude's: "
                             f"set {', '.join(missing)} in your config.toml to {harness}'s model ids and efforts"])
    vals = values(cfg, env)
    out = []
    for e in manifest():
        where = f"setup/{e.get('source') or e['target']}"
        when = e.get("when")
        if when and vals.get(when) != "true":
            continue
        item = {"kind": e["kind"], "target": _target(e["target"], vals, where, env)}
        if e.get("harness", harness) != harness:
            out.append({"kind": "skip", "target": item["target"], "why": render(e["why"], vals, where)})
            continue
        if "source" in e:
            text = (SETUP / e["source"]).read_text(encoding="utf-8")
            if "{{" not in text:
                item["content"] = text  # nothing to fill in: the file ships byte for byte
            elif e["kind"] == "json" or e["source"].endswith(".json"):
                item["content"] = render_json(text, vals, where)
            else:
                item["content"] = render(text, vals, where, yaml=e["kind"] == "yaml")
        if "to" in e:
            item["to"] = _target(e["to"], vals, where, env)
        if "from" in e:
            v = cfg
            for part in e["from"].split("."):
                v = v.get(part, {}) if isinstance(v, dict) else {}
            if not isinstance(v, list):
                raise C.ConfigError([f"{where}: from {e['from']} is not a list"])
            item["names"] = list(v)
        if "mode" in e:
            item["mode"] = int(str(e["mode"]), 8)
        out.append(item)
    return out


def templates() -> list:
    """Every file under setup/ but the manifest, the README and Python's caches: what setup-probe
    holds to the list."""
    skip = {MANIFEST, SETUP / "README.md"}
    return sorted(str(p.relative_to(SETUP)) for p in SETUP.rglob("*")
                  if p.is_file() and p not in skip and "__pycache__" not in p.parts)
