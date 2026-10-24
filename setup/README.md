# The agent working setup

Agent Office ships the office (herdr, the meter, `office` and `fm`) and, in this folder, the way agents work in it: the rules every agent reads, Claude Code's settings and hooks, Firstmate's model picks and captain starter, and the no-mistakes and gnhf settings. Each file here is a template. Your own values come from the `[setup]` keys in `~/.config/agent-office/config.toml` (every key and its default: `config/defaults.toml`).

`office setup` writes these into your home. It shows every change first, backs up what it changes, and records what it wrote in `~/.local/state/agent-office/setup-manifest.json`. `office setup --check` only plans. `office setup --remove` takes out what it put in, where that is still as it was put in; your starter files stay.

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

## The kinds: what is yours and what is Agent Office's

- **block**: Agent Office owns only the text between `<!-- agent-office:begin v1 -->` and `<!-- agent-office:end -->`. Every line outside the markers is yours, so your own private rules go there.
- **json**: Agent Office owns only the keys its template has. A list it owns (permission entries, hooks) merges by value: your own entries and hooks stay.
- **yaml**: Agent Office owns only the top-level keys its template has. Every other key is yours.
- **owned**: a whole file. It is replaced only while it is still exactly what Agent Office wrote last; a file you changed gets the new version next to it as `<file>.agent-office-new`.
- **starter**: written once when it is not there, and never again. It is yours from then on.
- **link**: a symbolic link, made only when nothing is there.
- **flags**: one empty file per name; Firstmate reads them as switches.

A target that is a link, or sits in a folder that is a link (a `~/.claude` linked into a dotfiles repo, say), is never written through: `office setup` shows what to put there and leaves it to you. The Firstmate files wait until the Firstmate home is there.

## Placeholders

A template says `{{setup.machine.test_workers}}` where a value goes, or `{{setup.gates.quick|the repo's quick checks}}` for words to use while the key is unset. Names are config keys: `setup.*`, `firstmate.code`, `firstmate.home` (its checkout when unset) and `firstmate.harness`. `setup.repos.protected` is the integration and release branch, named once when they are the same. A path in a target is rendered from your home and your config, never written into a template.

The shipped `[setup.models.*]` defaults are Claude model ids, so they apply only while `firstmate.harness` is `claude`. With `codex`, set `setup.models.default` and `setup.models.mechanical` (model and effort) in your own config.toml; until then the setup refuses to render. gnhf's config is not written with `codex` either: it has no codex permission override here, so gnhf's default would skip permissions. Set `agentArgsOverride.codex` yourself in `~/.gnhf/config.yml`.

## Nothing private

A template names no person, no account and no path of anyone's machine. `bin/setup-probe` renders every template for a stand-in user and runs `bin/leak-scan` over the result; `bin/setup-home-probe` runs `office setup` in throwaway homes. CI runs both on every push (CONTRIBUTING.md, "Keeping it private").
