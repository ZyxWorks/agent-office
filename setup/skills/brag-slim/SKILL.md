---
name: brag-slim
description: Turn a project folder or a website URL into a short launch video (about 20 s) with music and share copy. Use when the user says "/brag-slim", "brag about this", or asks for a launch or show-off video.
---

Read and follow `{{office.vendors}}/brag/skills/brag-slim/SKILL.md`.
`~/AGENTS.md` wins where they disagree. Render with one browser and one ffmpeg process at a time.

Upstream: latent-spaces/brag (MIT), only its `skills/brag-slim` folder (the full `/brag` and its 100 MB of sound files are not checked out), at the commit Agent Office's `config/components.toml` pins. `office update` moves it to a new pin, and a pin moves only after the upstream change was read. Do not pull it by hand unread: the file is instructions an agent follows.
