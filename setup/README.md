# The agent working setup

Agent Office ships the office (herdr, the meter, `office` and `fm`) and, in this folder, the way agents work in it: the rules every agent reads, Claude Code's settings and hooks, Firstmate's model picks and captain starter, and the no-mistakes and gnhf settings. Each file here is a template. Your own values come from the `[setup]` keys in `~/.config/agent-office/config.toml` (every key and its default: `config/defaults.toml`).

`office setup agents` writes these into your home. It shows every change first, backs up what it changes, and records what it wrote in `~/.local/state/agent-office/setup-manifest.json`. `office setup agents --check` only plans. `office setup agents --remove` takes out what it put in, where that is still as it was put in; your starter files stay. Once it has written the setup, `office update` keeps it current with your config and each new release, and `office doctor` says whether it is in place or behind. Where it replaced a JSON key or a top-level YAML key of yours (after the question or `--yes`), it records your old value and `--remove` puts that value back; a key you changed again since then stays as you left it, and a key that was not there before is taken out.

A JSON key, a JSON list entry or a top-level YAML key that Agent Office put in and you took out stays out. The next run says `you removed <key or entry> in <file>: left out` once, records it in the setup manifest as removed by you, and leaves it out from then on. To get it back, run `office setup agents --reset-key <file>:<key path or entry>` (for example `office setup agents --reset-key "~/.claude/settings.json:permissions.defaultMode"` or `office setup agents --reset-key "~/.claude/settings.json:Bash(gh-axi:*)"`), or delete the file's entry in the setup manifest; the next `office setup agents` puts it in again. A key that is new in a template is always added.

## What goes where

`MANIFEST.toml` lists every template, its target and its kind. Only what it lists ships.

| template | target | kind |
|---|---|---|
| `agents/AGENTS.md` | `~/AGENTS.md`, linked as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` | block, links |
| `agents/release-process.md` | `~/.agents/release-process.md` | block |
| `claude/settings.json` | `~/.claude/settings.json` | json |
| `claude/hooks/agents-md.py` | `~/.claude/hooks/` | owned |
| `claude/hooks/text-check.mjs`, `text-check.json` | `~/.claude/hooks/` | owned |
| `claude/themes/office.json`, `claude/theme.json` | `~/.claude/themes/`, `~/.claude/settings.json` | owned, json; only with `setup.claude.theme = true` |
| `firstmate/crew-dispatch.json`, `startup-memory-budget`, `supervision-host` | the Firstmate home's `config/` | owned |
| `setup.firstmate.flags` | the Firstmate home's `config/`, one empty file each | flags |
| `firstmate/captain.md` | the Firstmate home's `data/captain.md` | starter |
| `no-mistakes/config.yaml` | `~/.no-mistakes/config.yaml` | yaml |
| `gnhf/config.yml` | `~/.gnhf/config.yml` | yaml, Claude only |
| `skills/<name>/SKILL.md` and the skill pack it points at | `~/.agents/skills/<name>/`, linked as `~/.claude/skills/<name>`; the pack in `~/.local/share/agent-office/vendors/` | owned, link, vendor; only with its `setup.skills` key true |

## The kinds: what is yours and what is Agent Office's

- **block**: Agent Office owns only the text between `<!-- agent-office:begin v1 -->` and `<!-- agent-office:end -->`. Every line outside the markers is yours, so your own private rules go there.
- **json**: Agent Office owns only the keys its template has. A list it owns (permission entries, hooks) merges by value: your own entries and hooks stay.
- **yaml**: Agent Office owns only the top-level keys its template has. Every other key is yours.
- **owned**: a whole file. It is replaced only while it is still exactly what Agent Office wrote last; a file you changed gets the new version next to it as `<file>.agent-office-new`, once for each new version: the next runs leave your file to you, also after you delete the `.agent-office-new` one.
- **starter**: written once when it is not there, and never again. It is yours from then on.
- **link**: a symbolic link, made only when nothing is there.
- **flags**: one empty file per name; Firstmate reads them as switches.
- **vendor**: a skill pack from its upstream repository, at the commit `config/components.toml` pins, only the folders it names. Its files must hash to the pinned SHA-256 before it is put in place. It is moved to a new pin only while it is still as it was checked out; a pack you changed is left as it is.

A target that is a link, or sits in a folder that is a link (a `~/.claude` linked into a dotfiles repo, say), is never written through: `office setup agents` shows what to put there and leaves it to you. The Firstmate files wait until the Firstmate home is there.

## Optional skill packs

Three skill packs from other authors are off by default. Turn one on in your config.toml, then run `office setup agents`:

| key | skill | upstream (MIT) |
|---|---|---|
| `setup.skills.no_ai_slop` | `/no-ai-slop`: a draft edited into plain human writing. Manual only | petergyang/no-ai-slop, its `skills/no-ai-slop` |
| `setup.skills.marketing` | `marketing`: 50 marketing playbooks, the agent picks one or two | coreyhaines31/marketingskills, its `skills/` (not its `tools/`) |
| `setup.skills.brag_slim` | `brag-slim`: a short launch video of a project or a website | latent-spaces/brag, its `skills/brag-slim` |

Each pack is pinned to one commit and one SHA-256 in `config/components.toml`, and a pin moves only after the upstream change was read: the files are instructions your agent follows. `office update` moves a pack to a new pin and shows where to read the change; `office doctor` says when one is behind. Agent Office never runs anything in a pack. Turning a key off takes the pack out again, unless you changed it.

## Placeholders

A template says `{{setup.machine.test_workers}}` where a value goes, or `{{setup.gates.quick|the repo's quick checks}}` for words to use while the key is unset. Names are config keys: `setup.*`, `firstmate.code`, `firstmate.home` (its checkout when unset) and `firstmate.harness`, and `office.vendors`, where the skill packs are checked out. `setup.repos.protected` is the integration and release branch, named once when they are the same. A path in a target is rendered from your home and your config, never written into a template.

The shipped `[setup.models.*]` defaults are Claude model ids, so they apply only while `firstmate.harness` is `claude`. With `codex`, set `setup.models.default` and `setup.models.mechanical` (model and effort) in your own config.toml; until then the setup refuses to render. gnhf's config is not written with `codex` either: it has no codex permission override here, so gnhf's default would skip permissions. Set `agentArgsOverride.codex` yourself in `~/.gnhf/config.yml`.

## Nothing private

A template names no person, no account and no path of anyone's machine. `bin/setup-probe` renders every template for a stand-in user and runs `bin/leak-scan` over the result; `bin/setup-home-probe` runs `office setup agents` in throwaway homes. CI runs both on every push (CONTRIBUTING.md, "Keeping it private").
