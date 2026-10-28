"""office setup: write the agent working setup (setup/) into your home, showing every change first.

setup/MANIFEST.toml says what goes where; lib/agent_office/setup.py fills the templates in from
your [setup] keys. This module decides, for each target, what a write would do to what is there
now, and does it. Every write is recorded in the state folder's setup-manifest.json: the hash of
a whole file, the hash of a Markdown block, the keys and list entries put into a JSON file, the
top-level keys put into a YAML file. That record is how a later run tells what Agent Office
wrote from what you changed:

- what is still exactly as Agent Office wrote it is updated without asking,
- a change of yours inside what Agent Office owns is shown, backed up and asked about first,
- a whole file you changed is never replaced: the new version lands beside it as
  <file>.agent-office-new,
- a key, list entry or YAML key it put in that you took out stays out: the record says you
  removed it, until `office setup --reset-key <file>:<key>` takes that off again,
- everything outside what Agent Office owns (your lines around its block, your own keys, your
  own hooks and permission entries) is never touched,
- a link is never written through: a target that is a link (into a dotfiles repo, say) is left
  alone and you are told what to change in it yourself.

`office setup --remove` takes out what the record says Agent Office put in, as long as it is
still what it put in. Your starter files (data/captain.md) stay: they were yours from the start.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from . import config as C
from . import install
from . import setup as S

BEGIN = "<!-- agent-office:begin v1 -->"
END = "<!-- agent-office:end -->"
_BEGIN_ANY = re.compile(r"^<!-- agent-office:begin v\d+ -->$")
_YAML_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:")
NEW = ".agent-office-new"


def _sha(data) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


# --- Markdown blocks ------------------------------------------------------------------------------


def find_block(text: str):
    """(start, end) line indexes of the block's begin and end marker lines, None when there is
    no block, or a string saying what is wrong with the markers."""
    lines = text.splitlines()
    begins = [i for i, l in enumerate(lines) if _BEGIN_ANY.match(l.strip())]
    ends = [i for i, l in enumerate(lines) if l.strip() == END]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        return f"{len(begins)} begin and {len(ends)} end markers, not one pair in order"
    return begins[0], ends[0]


def block_body(text: str, at) -> str:
    lines = text.splitlines()
    return "\n".join(lines[at[0] + 1:at[1]]) + "\n"


def with_block(text: Optional[str], body: str, at) -> str:
    """text with the block's body set to body: in place, or added at the end."""
    block = f"{BEGIN}\n{body.rstrip(chr(10))}\n{END}\n"
    if not text:
        return block
    lines = text.splitlines(keepends=True)
    if at is None:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block
    return "".join(lines[:at[0]]) + block + "".join(lines[at[1] + 1:])


def without_block(text: str, at) -> str:
    lines = text.splitlines(keepends=True)
    before, after = lines[:at[0]], lines[at[1] + 1:]
    while before and not before[-1].strip():  # the blank line with_block put before it
        before.pop()
    out = "".join(before)
    rest = "".join(after)
    if out and rest:
        out += "\n"
    return out + rest


# --- JSON keys --------------------------------------------------------------------------------------


def flatten(frag: dict, path=()):
    """A fragment as (sets, adds): sets are (path, value) for every value that is not a table or
    a list; adds are (path, item) for every item of every list."""
    sets, adds = [], []
    for k, v in frag.items():
        p = (*path, k)
        if isinstance(v, dict):
            s, a = flatten(v, p)
            sets += s
            adds += a
        elif isinstance(v, list):
            adds += [(p, x) for x in v]
        else:
            sets.append((p, v))
    return sets, adds


_MISSING = object()


def _get(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return _MISSING
        d = d[k]
    return d


def _parent(d, path, conflicts):
    """The table that holds path's last key, made as needed. A value of yours where a table has
    to be is a conflict, and the table replaces it."""
    for i, k in enumerate(path[:-1]):
        if not isinstance(d.get(k), dict):
            if k in d:
                conflicts.append(f"{'.'.join(path[:i + 1])}: yours is not a table; Agent Office's is")
            d[k] = {}
        d = d[k]
    return d


def entry_name(p, x) -> str:
    return f"{'.'.join(p)} entry {json.dumps(x, ensure_ascii=False)}"


def merge_json(cur: dict, frag: dict, prev: dict):
    """(new, record, conflicts, left out). prev is what the last run put in, from the record.

    What the last run put in and this one does not is taken out again, where it is still as
    it was put in. A value this run sets over one of yours (one that is neither missing nor
    what the last run put there) is a conflict: the caller asks before writing it. A key or an
    entry an earlier run put in that you took out stays out, on the record as removed by you;
    left out names those this run found gone for the first time.
    """
    out = copy.deepcopy(cur)
    sets, adds = flatten(frag)
    prev_sets = [(tuple(p), v) for p, v in prev.get("set", [])]
    prev_adds = [(tuple(p), x) for p, x in prev.get("added", [])]
    gone = prev.get("removed", {})
    gone_sets = {tuple(p) for p in gone.get("set", [])}
    gone_adds = [(tuple(p), x) for p, x in gone.get("added", [])]
    removed_sets, removed_adds, left_out = [], [], []
    conflicts = []
    new_paths = {p for p, _ in sets}
    emptied = []
    for p, v in prev_sets:
        if p not in new_paths and _get(out, p) == v:
            del _get(out, p[:-1])[p[-1]]
            emptied.append(p[:-1])
    for p, x in prev_adds:
        if (p, x) not in adds:
            lst = _get(out, p)
            if isinstance(lst, list) and x in lst:
                lst.remove(x)
                emptied.append(p)
    # a table or list that taking those out left empty goes too, up to the first that is not
    for p in sorted(set(emptied), key=len, reverse=True):
        while p and _get(out, p) in ({}, []):
            del _get(out, p[:-1])[p[-1]]
            p = p[:-1]
    # Only what this run puts in, or an earlier one did, goes on the record: a value or an entry
    # that was yours already stays yours, and --remove leaves it.
    was = dict(prev_sets)
    my_sets, my_adds = [], []
    for p, v in sets:
        now = _get(out, p)
        if now is _MISSING and (p in was or p in gone_sets):
            removed_sets.append(p)
            if p not in gone_sets:
                left_out.append(".".join(p))
            continue
        if now == v and p not in was:
            continue
        if now is not _MISSING and now != v and (p not in was or was[p] != now):
            conflicts.append(f"{'.'.join(p)}: yours is {json.dumps(now)}, Agent Office's is {json.dumps(v)}")
        _parent(out, p, conflicts)[p[-1]] = v
        my_sets.append((p, v))
    for p, x in adds:
        now = _get(out, p)
        if not (isinstance(now, list) and x in now) and ((p, x) in prev_adds or (p, x) in gone_adds):
            removed_adds.append((p, x))
            if (p, x) not in gone_adds:
                left_out.append(entry_name(p, x))
            continue
        holder = _parent(out, p, conflicts)
        lst = holder.get(p[-1])
        if not isinstance(lst, list):
            if lst is not None:
                conflicts.append(f"{'.'.join(p)}: yours is not a list; Agent Office's is")
            lst = holder[p[-1]] = []
        if x not in lst:
            lst.append(x)
            my_adds.append((p, x))
        elif (p, x) in prev_adds:
            my_adds.append((p, x))
    record = {"kind": "json", "set": [[list(p), v] for p, v in my_sets],
              "added": [[list(p), x] for p, x in my_adds]}
    if removed_sets or removed_adds:
        record["removed"] = {"set": [list(p) for p in removed_sets],
                             "added": [[list(p), x] for p, x in removed_adds]}
    return out, record, conflicts, left_out


def json_text(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def combine(fragments) -> dict:
    """Several fragments for one file as one: tables merge, lists add up."""
    out = {}

    def into(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                into(a[k], v)
            elif isinstance(v, list) and isinstance(a.get(k), list):
                a[k] = a[k] + [x for x in v if x not in a[k]]
            else:
                a[k] = copy.deepcopy(v)

    for f in fragments:
        into(out, f)
    return out


# --- YAML top-level keys ------------------------------------------------------------------------------
# Only top-level keys, by their lines: no YAML parser in the standard library, and none needed. A
# key's block is its line and every line after it that is indented, blank, or a comment that is
# indented, up to the next line at the left edge. Trailing blank lines are not part of it.


def yaml_blocks(text: str):
    """(header, {key: block text}, order, spans): spans maps a key to its (start, end) lines."""
    lines = text.splitlines(keepends=True)
    spans, order = {}, []
    i = 0
    while i < len(lines):
        m = _YAML_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][0] in " \t"):
            j += 1
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        if m.group(1) not in spans:
            spans[m.group(1)] = (i, j)
            order.append(m.group(1))
        i = j
    first = min((s for s, _ in spans.values()), default=len(lines))
    header = "".join(lines[:first])
    return header, {k: "".join(lines[s:e]) for k, (s, e) in spans.items()}, order, spans


def merge_yaml(cur: Optional[str], frag: str, prev: dict):
    """(new text, record, conflicts, left out), as merge_json, for top-level keys."""
    fheader, fblocks, forder, _ = yaml_blocks(frag)
    record = {"kind": "yaml", "blocks": {k: _sha(fblocks[k]) for k in forder}, "header": fheader}
    if cur is None:
        return frag, record, [], []
    # the header comment is on the record only while a run of Agent Office wrote it
    record["header"] = prev["header"] if prev.get("header") and prev["header"] in cur else ""
    lines = cur.splitlines(keepends=True)
    _, blocks, _, spans = yaml_blocks(cur)
    was = prev.get("blocks", {})
    gone = prev.get("removed", [])
    removed = [k for k in forder if k not in blocks and (k in was or k in gone)]
    for k in removed:
        del record["blocks"][k]
    if removed:
        record["removed"] = removed
    left_out = [k for k in removed if k not in gone]
    forder = [k for k in forder if k not in removed]
    conflicts, replace = [], {}
    for k, sha in was.items():  # a key the last run wrote that this one does not
        if k not in fblocks and k in blocks and _sha(blocks[k]) == sha:
            replace[k] = ""
    for k in forder:
        if k in blocks:
            if blocks[k] == fblocks[k] and k not in was:
                del record["blocks"][k]  # yours already, the same: it stays yours
                continue
            if blocks[k] != fblocks[k] and was.get(k) != _sha(blocks[k]):
                conflicts.append(f"{k}: yours differs from Agent Office's")
            replace[k] = fblocks[k]
    out = []
    i = 0
    starts = {spans[k][0]: k for k in replace}
    while i < len(lines):
        if i in starts:
            k = starts[i]
            out.append(replace[k])
            i = spans[k][1]
            continue
        out.append(lines[i])
        i += 1
    text = "".join(out)
    missing = [k for k in forder if k not in blocks]
    if missing:
        add = "".join(fblocks[k] for k in missing)
        if not any(k in blocks for k in forder) and not record["header"]:
            add = fheader + add  # the template's comment says where the keys came from
            record["header"] = fheader
        text = text + ("" if text.endswith("\n") or not text else "\n") + ("\n" if text.strip() else "") + add
    return text, record, conflicts, left_out


def yaml_without(cur: str, prev: dict) -> str:
    _, blocks, _, spans = yaml_blocks(cur)
    lines = cur.splitlines(keepends=True)
    drop = set()
    for k, sha in prev.get("blocks", {}).items():
        if k in blocks and _sha(blocks[k]) == sha:
            drop.update(range(*spans[k]))
    out = "".join(l for i, l in enumerate(lines) if i not in drop)
    header = prev.get("header") or ""
    if header and header in out:  # the comment Agent Office wrote above its keys
        out = out.replace(header, "", 1)
    if out == cur:
        return cur
    return out.rstrip("\n") + "\n" if out.strip() else ""


# --- the plan -------------------------------------------------------------------------------------


class Setup(install.Installer):
    """office install's machinery (steps, backups, the plan print, apply), with its own record."""

    def __init__(self, env=None, out=sys.stdout):
        super().__init__(env, out)
        self.manifest_path = self.state / "setup-manifest.json"
        self.manifest = self._read_manifest()

    def prev(self, p: Path) -> dict:
        return self.manifest["owned"].get(str(p), {})

    def _where_link(self, p: Path, itself=True) -> Optional[str]:
        """The link in p's way, if p or a folder above it inside your home is one: never written through.
        itself=False looks at the folders only, for a target that is meant to be a link."""
        if itself and p.is_symlink():
            return f"{self.show(p)} is a link to {os.readlink(p)}"
        for d in p.parents:
            if d == self.home or self.home not in d.parents:
                break
            if d.is_symlink():
                return f"its folder {self.show(d)} is a link to {os.readlink(d)}"
        return None

    def _edit_step(self, p, cur: Optional[str], new: str, what: str, record: dict, asks: bool, mode=None):
        data = new.encode()

        def go():
            if cur is not None:
                self._backup(p)
            self._write(p, data, mode)
        if cur is None:
            return install.Step("create", p, what, go, record=record)
        if cur == new:
            return install.Step("keep", p, what, record=record)
        return install.Step("edit" if asks else "update", p, what, go, self._diff(cur.encode(), data, p.name), record)

    def _read(self, p: Path) -> Optional[str]:
        return p.read_text(encoding="utf-8") if p.exists() else None

    def want_block(self, p: Path, body: str, what: str):
        link = self._where_link(p)
        if link:
            return install.Step("manual", p, f"{what}: {link}. Links are never written through: put the "
                                "block below between its markers yourself, in the file it links to",
                                diff=[BEGIN, *body.splitlines(), END])
        if p.is_dir():
            return install.Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        cur = self._read(p)
        record = {"kind": "block", "sha256": _sha(body)}
        at = find_block(cur) if cur else None
        if isinstance(at, str):
            return install.Step("manual", p, f"{what}: its Agent Office markers are broken ({at}). "
                                f"Leave one {BEGIN} and one {END}, then run this again")
        if at is None:
            # added to a file of yours: asked, because the file is yours
            return self._edit_step(p, cur, with_block(cur, body, None), what, record, asks=cur is not None)
        old = block_body(cur, at)
        mine = old == body or self.prev(p).get("sha256") == _sha(old)
        why = "" if mine else " (the block was changed by hand)"
        return self._edit_step(p, cur, with_block(cur, body, at), what + why, record, asks=not mine)

    def _left_out(self, step, p: Path, left_out: list):
        """step, telling which of what an earlier run put in you took out: it stays out."""
        if left_out and step.kind == "keep":
            step.kind = "left-out"
        step.diff = [*(f"you removed {k} in {self.show(p)}: left out" for k in left_out), *step.diff]
        return step

    def want_json(self, p: Path, frag: dict, what: str):
        new_empty, record, _, _ = merge_json({}, frag, {})
        link = self._where_link(p)
        if link:
            return install.Step("manual", p, f"{what}: {link}. Links are never written through: add these "
                                "keys to the file it links to yourself", diff=json_text(frag).splitlines())
        if p.is_dir():
            return install.Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        cur = self._read(p)
        if cur is None:
            return self._edit_step(p, None, json_text(new_empty), what, record, asks=False)
        try:
            data = json.loads(cur) if cur.strip() else {}
        except ValueError as e:
            return install.Step("manual", p, f"{what}: it is not valid JSON ({e}); fix it, then run this again")
        if not isinstance(data, dict):
            return install.Step("manual", p, f"{what}: it is JSON but not an object; fix it, then run this again")
        new, record, conflicts, left_out = merge_json(data, frag, self.prev(p))
        if new == data:
            return self._left_out(install.Step("keep", p, what, record=record), p, left_out)
        step = self._edit_step(p, cur, json_text(new), what, record, asks=bool(conflicts))
        step.diff = [*conflicts, *step.diff]
        return self._left_out(step, p, left_out)

    def want_yaml(self, p: Path, frag: str, what: str):
        link = self._where_link(p)
        if link:
            return install.Step("manual", p, f"{what}: {link}. Links are never written through: set these "
                                "keys in the file it links to yourself", diff=frag.splitlines())
        if p.is_dir():
            return install.Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        cur = self._read(p)
        new, record, conflicts, left_out = merge_yaml(cur, frag, self.prev(p))
        step = self._edit_step(p, cur, new, what, record, asks=bool(conflicts))
        step.diff = [*conflicts, *step.diff]
        return self._left_out(step, p, left_out)

    def want_owned(self, p: Path, text: str, what: str, mode: Optional[int]):
        data = text.encode()
        record = {"kind": "file", "sha256": _sha(data)}
        link = self._where_link(p)
        if link:
            return install.Step("manual", p, f"{what}: {link}. Links are never written through")
        if p.is_dir():
            return install.Step("manual", p, f"{what}: a folder is in the way; move it, then run this again")
        if not p.exists():
            return install.Step("create", p, what, lambda: self._write(p, data, mode), record=record)
        cur = p.read_bytes()
        cur_mode = p.stat().st_mode & 0o7777
        if cur == data:
            if mode is not None and cur_mode != mode:
                return install.Step("update", p, f"{what} (its mode)", lambda: os.chmod(p, mode), record=record)
            return install.Step("keep", p, what, record=record)
        if self.prev(p).get("sha256") == _sha(cur):
            return install.Step("update", p, what, lambda: self._write(p, data, mode),
                                self._diff(cur, data, p.name), record)
        beside = p.with_name(p.name + NEW)
        why = "changed by hand" if self.prev(p) else "not written by Agent Office"
        # yours is never replaced: the new version goes beside it, and the record stays as it was
        return install.Step("beside", beside, f"{what}: {self.show(p)} is {why}, so the new version "
                            "goes beside it; compare the two and keep what you want",
                            lambda: self._write(beside, data, mode), self._diff(cur, data, p.name))

    def want_starter(self, p: Path, text: str, what: str):
        if p.exists() or p.is_symlink():
            return install.Step("keep", p, f"{what} (yours: never written again)")
        return install.Step("create", p, f"{what}, a starter to edit; never written again",
                            lambda: self._write(p, text.encode()), record={"kind": "starter"})

    def want_symlink(self, p: Path, to: Path, what: str):
        if p.is_symlink() and os.readlink(p) == str(to):
            return install.Step("keep", p, what, record={"kind": "link", "target": str(to)})
        if p.exists() or p.is_symlink():
            return install.Step("manual", p, f"{what}: something is already there, and a link is made only "
                                f"when nothing is. To share one file, move what is in {self.show(p)} into "
                                f"{self.show(to)} and run this again")
        return install.Step("create", p, f"{what}, a link to {self.show(to)}", lambda: self._link(p, str(to)),
                            record={"kind": "link", "target": str(to)})

    def want_flag(self, p: Path, what: str):
        if p.exists() or p.is_symlink():
            return install.Step("keep", p, what)
        return install.Step("create", p, what, lambda: self._write(p, b""), record={"kind": "flag"})

    def plan(self, cfg: dict) -> list:
        items = S.plan(cfg, self.env)
        fm_home = Path(S.values(cfg, self.env)["firstmate.home"])
        steps, json_frags = [], {}
        for it in items:
            if it["kind"] == "json":
                json_frags.setdefault(it["target"], []).append(json.loads(it["content"]))
        seen_json, fm_noted = set(), False
        for it in items:
            p, kind = it["target"], it["kind"]
            what = WHAT.get(kind, kind)
            if kind == "skip":                  # not written for this harness; why says what to do
                steps.append(install.Step("manual", p, f"not written: {it['why']}"))
                continue
            link = self._where_link(p, itself=kind != "link") if kind in ("link", "starter", "flags") else None
            if link:
                steps.append(install.Step("manual", p, f"{what}: {link}. Links are never written through"))
                continue
            if (p == fm_home or fm_home in p.parents) and not fm_home.is_dir():
                if fm_noted:                    # one line for all of Firstmate, not one per file
                    continue
                fm_noted = True
                steps.append(install.Step("manual", p, f"Firstmate's home {self.show(fm_home)} is not there yet: "
                                          "these are written once it is. Run office setup again then"))
                continue
            if kind == "block":
                steps.append(self.want_block(p, it["content"], what))
            elif kind == "json":
                if p not in seen_json:
                    seen_json.add(p)
                    steps.append(self.want_json(p, combine(json_frags[p]), what))
            elif kind == "yaml":
                steps.append(self.want_yaml(p, it["content"], what))
            elif kind == "owned":
                steps.append(self.want_owned(p, it["content"], what, it.get("mode")))
            elif kind == "starter":
                steps.append(self.want_starter(p, it["content"], what))
            elif kind == "link":
                steps.append(self.want_symlink(p, it["to"], what))
            elif kind == "flags":
                steps += [self.want_flag(p / n, f"the {n} switch, an empty file") for n in it["names"]]
        # what an earlier run wrote that no template wants now (a theme turned off, say)
        wanted = {str(s.path) for s in steps} | {str(it["target"]) for it in items}
        steps += [s for s in self.unwanted(exclude=wanted) if s is not None]
        return steps

    # --- taking it out again ------------------------------------------------------------------

    def unwanted(self, exclude=()) -> list:
        """Steps that take out what the record says an earlier run put in, path by path."""
        steps = []
        for path, rec in sorted(self.manifest["owned"].items()):
            if path in exclude:
                continue
            steps.append(self.take_out(Path(path), rec))
        return steps

    def _forget(self, p: Path, what: str, kind="keep") -> install.Step:
        return install.Step(kind, p, what, record={"forget": True})

    def take_out(self, p: Path, rec: dict) -> Optional[install.Step]:
        kind = rec.get("kind")
        if kind == "starter":
            return self._forget(p, "yours from the start: it stays")
        if not (p.exists() or p.is_symlink()):
            return self._forget(p, "already gone")
        link = self._where_link(p, itself=kind != "link")
        if link:
            return install.Step("manual", p, f"{link}. Links are never written through: take out what "
                                "Agent Office put in yourself")

        def remove():
            self._backup(p)
            p.unlink()

        if kind == "link":
            if p.is_symlink() and os.readlink(p) == rec.get("target"):
                return install.Step("remove", p, "a link Agent Office made", lambda: p.unlink(),
                                    record={"forget": True})
            return self._forget(p, "no longer the link Agent Office made: left alone")
        if kind == "flag":
            if p.is_file() and p.stat().st_size == 0:
                return install.Step("remove", p, "a switch Agent Office made", lambda: p.unlink(),
                                    record={"forget": True})
            return self._forget(p, "no longer empty: left alone")
        if kind == "file":
            if _sha(p.read_bytes()) == rec.get("sha256"):
                return install.Step("remove", p, "a file Agent Office wrote, unchanged", remove,
                                    record={"forget": True})
            return self._forget(p, "changed by hand since Agent Office wrote it: left alone")
        cur = p.read_text(encoding="utf-8")
        if kind == "block":
            at = find_block(cur)
            if not isinstance(at, tuple):
                return self._forget(p, "no Agent Office block in it any more")
            new = without_block(cur, at)
            asks = _sha(block_body(cur, at)) != rec.get("sha256")
            what = "take out the Agent Office block" + (" (changed by hand)" if asks else "")
        elif kind == "json":
            try:
                data = json.loads(cur)
            except ValueError:
                return install.Step("manual", p, "not valid JSON: take out Agent Office's keys yourself")
            new_data = merge_json(data, {}, rec)[0]
            if new_data == data:
                return self._forget(p, "nothing of Agent Office's left in it")
            new, asks, what = json_text(new_data), False, "take out the keys Agent Office put in"
        elif kind == "yaml":
            new, asks, what = yaml_without(cur, rec), False, "take out the keys Agent Office put in"
        else:
            return None
        if new == cur:
            return self._forget(p, "nothing of Agent Office's left in it")
        if not new.strip():
            return install.Step("edit" if asks else "remove", p, what + "; nothing else is in it, so it goes",
                                remove, self._diff(cur.encode(), b"", p.name), {"forget": True})

        def go():
            self._backup(p)
            self._write(p, new.encode(), p.stat().st_mode & 0o7777)
        return install.Step("edit" if asks else "update", p, what, go,
                            self._diff(cur.encode(), new.encode(), p.name), {"forget": True})

    def reset_key(self, spec: str) -> list:
        """Takes what spec names (<file>:<key path or entry>) off the record of what you removed, so
        the next run puts it in again. The names of what it took off; none when nothing matched."""
        name, sep, key = spec.partition(":")
        if not sep or not name or not key:
            return []
        p = self.home / name[2:] if name.startswith("~/") else Path(os.path.abspath(name))
        rec = self.manifest["owned"].get(str(p), {})
        gone = rec.get("removed")
        back = []
        if rec.get("kind") == "json" and gone:
            for path in list(gone["set"]):
                if ".".join(path) == key:
                    gone["set"].remove(path)
                    back.append(key)
            for path, x in list(gone["added"]):
                if key in (".".join(path), x, json.dumps(x, ensure_ascii=False)):
                    gone["added"].remove([path, x])
                    back.append(entry_name(path, x))
            if not gone["set"] and not gone["added"]:
                del rec["removed"]
        elif rec.get("kind") == "yaml" and key in (gone or []):
            gone.remove(key)
            back.append(key)
            if not gone:
                del rec["removed"]
        if back:
            self._write(self.manifest_path, (json.dumps(self.manifest, indent=2) + "\n").encode())
        return [f"{k} in {self.show(p)}" for k in back]

    def removed_by_you(self) -> list:
        """<file>:<key or entry> for everything on the record as removed by you."""
        out = []
        for path, rec in sorted(self.manifest["owned"].items()):
            gone = rec.get("removed")
            if not gone:
                continue
            f = self.show(Path(path))
            if rec.get("kind") == "json":
                out += [f"{f}:{'.'.join(k)}" for k in gone["set"]]
                out += [f"{f}:{x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}"
                        for _, x in gone["added"]]
            else:
                out += [f"{f}:{k}" for k in gone]
        return out

    def apply(self, steps):
        # a step whose record is {"forget": True} takes its path off the record once it has run
        for s in steps:
            if s.record == {"forget": True}:
                s.record = None
                run = s.run

                def go(run=run, path=str(s.path)):
                    if run is not None:
                        run()
                    self.manifest["owned"].pop(path, None)
                s.run = go
                if s.kind == "keep":
                    s.kind = "forget"
        return super().apply(steps)


WHAT = {
    "block": "Agent Office's block of rules; your lines around it stay",
    "json": "Agent Office's keys; your own keys, hooks and entries stay",
    "yaml": "Agent Office's top-level keys; your own keys stay",
    "owned": "a file Agent Office keeps up to date",
    "starter": "a starter",
    "link": "one rules file for every agent",
    "flags": "a Firstmate switch",
}


def run(args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    check_only = yes = remove = False
    resets = []
    it = iter(args)
    for a in it:
        if a in ("--check", "-n", "--dry-run"):
            check_only = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--remove":
            remove = True
        elif a == "--reset-key":
            spec = next(it, None)
            if spec is None:
                print(f"office setup: --reset-key needs <file>:<key path or entry>\n{USAGE}", file=err)
                return 2
            resets.append(spec)
        elif a in ("-h", "--help"):
            print(USAGE, file=out)
            return 0
        else:
            print(f"office setup: unknown option {a}\n{USAGE}", file=err)
            return 2
    if resets and (check_only or remove):
        print(f"office setup: --reset-key goes on its own, not with --check or --remove\n{USAGE}", file=err)
        return 2

    st = Setup(env, out)
    if resets:
        for spec in resets:
            back = st.reset_key(spec)
            if not back:
                print(f"office setup: nothing you removed matches {spec}.", file=err)
                listed = st.removed_by_you()
                print("  On the record as removed by you:" if listed else "  Nothing is on the record as "
                      "removed by you.", file=err)
                for line in listed:
                    print(f"    {line}", file=err)
                return 1
            for b in back:
                st.say(f"{b}: back on the record; the next office setup puts it in again")
        return 0
    cfg_path = C.config_path(st.env)
    try:
        cfg = C.load(cfg_path)
        steps = st.unwanted() if remove else st.plan(cfg)
    except C.ConfigError as e:
        print("office setup: the config or a template has problems. Nothing was changed.", file=err)
        for p in e.problems:
            print("  " + p.replace(str(st.home), "~"), file=err)
        return 1
    except (OSError, UnicodeDecodeError) as e:
        print(f"office setup: {e}. Nothing was changed.", file=err)
        return 1

    verb = "office setup --remove" if remove else "office setup"
    st.say(f"{verb}{' --check' if check_only else ''}: config {st.show(cfg_path)}")
    st.print_plan(steps)
    asks = [s for s in steps if s.asks]
    manual = [s for s in steps if s.kind == "manual"]
    if check_only:
        return 0
    if asks and not yes:
        if not install._confirm(f"Change {len(asks)} file(s) of yours above, backing each up first? [y/N] "):
            print(f"{verb}: not confirmed. Nothing was changed. Run it in a terminal to answer, or pass --yes.",
                  file=err)
            return 1
    try:
        st.apply(steps)
    except OSError as e:
        print(f"{verb}: {e}. Stopped there: run it again when that is fixed.", file=err)
        return 1
    if any(s.kind not in ("keep", "manual") for s in steps):
        st.say(f"Done. Backups and the list of what Agent Office wrote: {st.show(st.state)}")
    if manual:
        st.say(f"Left for you: {len(manual)} item(s) marked manual above.")
    if not remove and any(s.kind == "beside" for s in steps):
        st.say(f"A file you changed got the new version beside it ({NEW}): compare, keep what you want, "
               f"delete the {NEW} file.")
    return 0


USAGE = """\
usage: office setup [--check] [--yes] [--remove] [--reset-key <file>:<key>]

Write the agent working setup into your home: the agent rules (~/AGENTS.md, linked as
~/.claude/CLAUDE.md and ~/.codex/AGENTS.md), the review and release process, Claude Code's
settings and hooks, Firstmate's model picks and switches, and the no-mistakes and gnhf settings.
Every value comes from the [setup] keys in your config; setup/README.md lists every file.

Agent Office owns only what it put in: a marked block in a Markdown file, its own keys in a JSON
or YAML file, and its own whole files. Your lines, keys, hooks and entries stay. A change of
yours to what it owns is shown, backed up and asked about first; a whole file you changed is
never replaced (the new version goes beside it as <file>.agent-office-new). A link is never
written through. A key or entry Agent Office put in that you took out stays out: the run says
"you removed <key> in <file>: left out" once and records it.

  --check    show what it would do, change nothing
  --yes      do not ask before changing a file of yours (backups are still made)
  --remove   take out what Agent Office put in, where it is still as it was put in
  --reset-key <file>:<key path or entry>
             let the next run put back a key or entry you took out, for example
             --reset-key "~/.claude/settings.json:Bash(gh-axi:*)" (deleting the
             file's entry in the setup manifest does it for the whole file)"""
