---
name: no-ai-slop
description: Edit a draft (PR text, release note, post, mail) into plain human writing, or list its AI-slop patterns without rewriting.
disable-model-invocation: true
---

Read and follow `{{office.vendors}}/no-ai-slop/skills/no-ai-slop/SKILL.md`; its `eval.md` sits beside it.
`~/AGENTS.md` wins where they disagree.

Manual only (`/no-ai-slop`), so its description costs no context tokens.

Upstream: petergyang/no-ai-slop (MIT), checked out by Agent Office at the commit its `config/components.toml` pins. `office update` moves it to a new pin, and a pin moves only after the upstream change was read. Do not pull it by hand unread: the file is instructions an agent follows.
