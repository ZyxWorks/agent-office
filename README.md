# Agent Office

**A whole agent developer setup, out of one box.**

[![CI](https://github.com/ZyxWorks/agent-office/actions/workflows/ci.yml/badge.svg)](https://github.com/ZyxWorks/agent-office/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-c9903f)](LICENSE)
![Platform: macOS and Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-6a6c77)

Agent Office is a small, opinionated distribution of the tools one developer
uses every day to run several coding agents at once: **herdr** for the
terminal, **Firstmate** to supervise the agents, **treehouse** for their git
worktrees, the **kunchenguid tools** around them, and a context **meter** and
visual preset that make it all readable at a glance. One private config file.
One `office` command to install, start, stop and update the lot.

> **Status: in transition.** This README is the contract for Agent Office 1.0,
> the herdr-first version. Most of it is **planned** and does not exist yet.
> Every command below is marked `planned` or `works today`, and only the
> second kind is real. The code in this repository today is still the tmux
> office (0.x) plus the herdr meter plugin. See
> [the tmux office (legacy)](#the-tmux-office-legacy) if you use that.

[The product page](https://zyxworks.github.io/agent-office/) ·
[Getting started](GETTING-STARTED.md) ·
[Contributing](CONTRIBUTING.md)

## Why

Running three or four coding agents at once is normal now. The tools for it
exist, and they are good: herdr runs the panes and knows each agent's state,
Firstmate supervises a fleet of workers, treehouse hands each one a warm git
worktree. But each is its own install, its own config and its own update, and
wiring them together into a daily setup lived in one person's dotfiles.

Agent Office packages that wiring, so anyone can have the same setup with one
install and one config, and so the wiring gets tested instead of copied.

It does **not** rewrite any of those tools. Each one stays independently
maintained upstream. Agent Office owns only:

- **installation**: getting every component onto the machine through its own
  installer or package manager,
- **config composition**: one file in, the native config of each tool out,
- **compatibility**: a tested set of versions that work together,
- **the daily experience**: start, break, stop and update, as one command each.

## What is in the box

Two profiles. `core` is the office. `workstation` is optional.

### Core profile

| component | what it does | owner |
|---|---|---|
| [herdr](https://herdr.dev) | terminal sessions, panes, tabs, and each agent's native state (working, idle, done, blocked) | herdr upstream |
| Agent Office herdr preset | keys, sidebar, theme and a silent "done" sound, so the daily look is the default look | this repo (planned) |
| Agent Office meter | a herdr plugin that shows how full each agent's context window is, and how long it has waited on you, in the sidebar | this repo ([`herdr/`](herdr), works today) |
| [Firstmate](https://github.com/kunchenguid/firstmate) | supervises coding agents: dispatch, status, review, cleanup | Firstmate upstream |
| [treehouse](https://github.com/kunchenguid/treehouse) | a pool of pre-warmed git worktrees, one per worker | treehouse upstream |
| kunchenguid tools | `no-mistakes`, `gh-axi`, `chrome-devtools-axi`, `lavish-axi`, `quota-axi`, `tasks-axi`, `gnhf` | [their upstreams](https://github.com/kunchenguid) |
| agent integrations | the skills the setup uses, herdr's Claude Code and Codex integrations, and a pinned Node version for the Node-based tools | upstream tools; this repo wires them (planned) |

`jq` is also required: the meter reads transcripts with it.

### Workstation profile (optional)

Generic command-line tools that make the terminal pleasant but that the office
does not need to run, such as `ripgrep`, `fd`, `fzf`, `bat` and an editor.
Installed only when you ask for this profile. The exact list is settled by the
installer work and will be printed by `office install` before it installs
anything.

Agent Office never installs or signs you in to an agent itself. Claude Code,
Codex and any other harness are installed and authenticated by you, through
their own setup.

## One config

All of it is driven by one private file:

```
~/.config/agent-office/config.toml
```

**Planned.** It does not exist yet. The shape, as a contract and not as keys
you can use today:

```toml
schema = 1

[office]
session = "office"                    # the herdr session this office owns

[firstmate]
source = "<public-upstream-or-your-fork>"
code = "<local-code-checkout>"
home = "<private-operational-home>"
harness = "claude"

[treehouse]
# root = "<local-pool-root>"          # optional; treehouse's own default otherwise

[meter]
enabled = true
interval_seconds = 30
warn_tokens = 200000
alarm_tokens = 600000

[herdr.ui]                            # passed through to herdr as-is
agent_panel_sort = "spaces"
```

The rules the config follows:

- **Defaults ship with the release; your file only overrides.** An unknown
  Agent Office key is an error. Keys under `[herdr]` pass through to herdr
  unchanged, so tuning herdr needs no second file.
- **The generated herdr config is output, not a second source.** Agent Office
  writes it and launches herdr against it. You edit `config.toml`.
- **One config controls the integration, not every internal setting.**
  Firstmate's projects, routing and preferences stay in Firstmate's own files.
  Per-repo worktree preparation stays in treehouse's own config.
- **Values are data.** Nothing in the file is ever run as shell code.

## Commands

| command | what it does | status |
|---|---|---|
| `office install` | check what is installed, install what is missing through each tool's own installer, write the config, show every change and backup. Starts nothing. | planned |
| `office on` | attach to or create the configured herdr session, and make sure one Firstmate is running for the configured home. Running it again focuses what is there. | planned |
| `office break` | detach only. Firstmate, the workers and the terminals keep running. | planned |
| `office off` | stop this office: show what will stop, let Firstmate persist and drain its workers, then stop the owned session and its meter. Repos and worktree pools are kept. | planned |
| `office off --all` / `officeoff-all` | stop every office this installation owns, after showing the targets and asking to confirm. Two spellings, one implementation. | planned |
| `office update` | update every component (the CLI, preset, meter, config, herdr, treehouse, Firstmate and the kunchenguid tools) to a tested set, each through its own updater. `--check` only plans. | planned |
| `office status` / `office doctor` | read-only: installed and running versions, what the office owns, meter and integration health, Firstmate readiness, pending updates. Unknown is never reported as healthy. | planned |
| `fm [args]` | open or focus the configured Firstmate, with your arguments passed through unchanged. | planned |
| `fm restart` | make Firstmate save its work, check that the save worked, then reset it. If the save fails, nothing is reset. | planned |

Today, `office` on your `PATH` is still the tmux office, and its commands are
documented in the [legacy README](docs/legacy-tmux/README.md). The 1.0
commands above replace them; they are not additions to them.

### What the commands promise

- **Ownership, not process names.** `office off --all` stops only what this
  installation started and recorded. It never stops every `claude`, `codex` or
  herdr process on the machine, never runs a blanket `pkill`, and never stops a
  herdr session it does not own.
- **Show, then act.** Anything that stops work first lists exactly what it will
  stop. If Firstmate cannot save or drain, the stop halts and says why.
- **Firstmate owns its workers; treehouse owns its pools.** Agent Office asks
  them to stop and clean up. It never deletes worktrees or empties a pool
  itself.
- **Update does not overclaim.** `office update` reports each component as
  updated, unchanged, skipped, failed, or updated on disk but not yet active.
  It succeeds only when everything it promised is verified.
- **No remote shell pipelines.** Components are installed from their own
  published installers or package managers, at reviewed versions.

## What stays private

The public package holds nothing personal. These live only in your own
`config.toml`, your dotfiles, or the tool that owns them:

- your accounts, credentials and tokens (they stay in each provider's own
  store or keychain),
- machine names, SSH hosts and private servers,
- your paths: code root, repos, Firstmate home, worktree pools,
- your Firstmate operational content: backlog, projects, preferences, state,
- private apps and personal automation.

Examples in this repo use placeholders, never a real machine's output.
`office doctor` (planned) output is meant to be pasted into an issue, so it
redacts local paths and identities by default.

## Platforms

**macOS and Linux.** Those are the only platforms 1.0 will claim, and only once
the new stack has been tested there. Windows, including WSL2, is not supported
by 1.0: the tmux office ran there, but the herdr-first stack has not been
tested there, so it is not claimed.

## What works today

Two things are real right now:

1. **The herdr meter plugin**, in [`herdr/`](herdr). It shows each agent's
   context size, and how long it has waited on you, in herdr's sidebar next to
   herdr's own state. Setup by hand is in [Getting started](GETTING-STARTED.md#today-the-meter-by-hand).
   It supports Claude Code, Codex, and Claude Code run against a local Ollama
   model; any agent it cannot identify stays blank rather than guessing. Two
   Codex agents in the same directory can show the same number, because Codex
   is matched by directory. `herdr/meter-probe` tests it without a herdr
   server.
2. **The tmux office (0.x)**, documented in
   [docs/legacy-tmux](docs/legacy-tmux/README.md).

## The tmux office (legacy)

Agent Office 0.x was a tmux cockpit: `office on`, a six-pane grid, iTerm2
profile, "your turn" on each pane border. It is retired, through a major
version change, not deleted.

- **1.0 is the herdr-first version.** The version number says the break.
- **The last tmux release stays available.** Before any 1.0 code lands on
  `main`, the last tmux commit is tagged as the final `0.x` release (planned;
  this README will name the exact tag). Its docs travel with it:
  [README](docs/legacy-tmux/README.md),
  [Getting started](docs/legacy-tmux/GETTING-STARTED.md),
  [Contributing](docs/legacy-tmux/CONTRIBUTING.md).
- **Staying on tmux.** Check out that tag in your clone. The tmux
  `office update` pulls the branch you are on, so on `main` it would pull 1.0.
  On the tag it refuses to update, which is what you want.
- **Moving to 1.0.** `office install` (planned) finds the old `office` shell
  function and the old `.zshrc` and `.tmux.conf` lines, shows them, backs them
  up and replaces them. It never overwrites a config it did not write without
  showing the difference first. Your tmux sessions are not touched.

The legacy tmux office gets no new features. Fixes are unlikely.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). It says what is in scope, and how to
test without touching a live office.

## Licence

MIT. See [LICENSE](LICENSE).

---

Made by [Zyx](https://zyxworks.com). Firstmate, treehouse and the kunchenguid
tools are by [kunchenguid](https://github.com/kunchenguid). herdr is by its own
authors at [herdr.dev](https://herdr.dev).
