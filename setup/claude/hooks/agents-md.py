#!/usr/bin/env python3
"""One instruction file per repo: AGENTS.md, with CLAUDE.md a symlink to it.

Claude Code reads CLAUDE.md, Codex reads AGENTS.md. Two real files drift apart,
so CLAUDE.md is only ever a link. This hook keeps it that way without a
sentence in every file saying so:

- creating a CLAUDE.md (by hand or via /init)   -> blocked, write AGENTS.md + link
- writing a real CLAUDE.md next to an AGENTS.md -> blocked, same fix
- editing through the symlink                   -> fine, it edits AGENTS.md
- a lone nested CLAUDE.md that already exists   -> left alone

Shipped by Agent Office (setup/claude/hooks/agents-md.py).
"""
import json
import os
import sys

try:
    call = json.load(sys.stdin)
except ValueError:
    sys.exit(0)

path = (call.get("tool_input") or {}).get("file_path") or ""
if os.path.basename(path) != "CLAUDE.md" or os.path.islink(path):
    sys.exit(0)

d = os.path.dirname(path) or "."
if os.path.exists(path) and not os.path.exists(os.path.join(d, "AGENTS.md")):
    sys.exit(0)

print(
    f"BLOCKED: {path} must be a symlink, not a file. Put the instructions in "
    f"{os.path.join(d, 'AGENTS.md')}, then run `ln -sf AGENTS.md CLAUDE.md` in {d}. "
    "Keep AGENTS.md short: only what almost every session needs.",
    file=sys.stderr,
)
sys.exit(2)
