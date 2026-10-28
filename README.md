<picture><source media="(prefers-color-scheme: dark)" srcset="docs/logo/mark-on-dark.svg"><img src="docs/logo/mark-on-light.svg" width="72" height="72" alt="Agent Office logo"></picture>

# Agent Office

**A whole agent developer setup, out of one box.**

[![CI](https://github.com/ZyxWorks/agent-office/actions/workflows/ci.yml/badge.svg)](https://github.com/ZyxWorks/agent-office/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-FFD23C)](LICENSE)
![Platform: macOS and Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-6a6c77)

Agent Office is a small, opinionated distribution of the tools one developer
uses every day to run several coding agents at once: **herdr** for the
terminal, **Firstmate** to supervise the agents, **treehouse** for their git
worktrees, the **kunchenguid tools** around them, and a context **meter** and
visual preset that make it all readable at a glance. One private config file.
One `office` command to install, start, stop and update the lot.

[The product page](https://zyxworks.github.io/agent-office/) ·
[Getting started](GETTING-STARTED.md) ·
[Every key](preset/README.md#keys) ·
[Contributing](CONTRIBUTING.md)

```
 spaces                          │  1   2   +
 ○ api                           │┌───────────────────────┐┌──────────────────────┐
   main                          ││ Firstmate             ││ a worker             │
 · website                       ││                       ││                      │
   main                          ││                       ││                      │
─────────────────────────────────││                       ││                      │
 agents                          ││                       ││                      │
 ○ api                           ││                       ││                      │
   firstmate · 88k · 3m · idle   ││                       ││                      │
   89% · main                    ││                       ││                      │
 ● api                           ││                       ││                      │
   claude · 412k▲ · blocked      ││                       ││                      │
   89% · #109 · fix/login        │└───────────────────────┘└──────────────────────┘
```

On the left you see every agent: its state from herdr, and from the Agent
Office meter how full its context is, how long it has been quiet, how much of
your plan's quota is left, and the branch and open pull request it works on. Amber
means "this needs you". Shift+arrow walks you there. No mouse.

## Quick start

You need macOS or Linux, git, Node 22.19 or newer, and a coding agent you
installed and signed in to yourself (Claude Code or Codex).

```sh
git clone https://github.com/ZyxWorks/agent-office ~/agent-office && ~/agent-office/bin/office setup
```

It asks four questions, installs the tools you lack, clones [Firstmate](https://github.com/kunchenguid/firstmate), writes the office and the agent working setup, and checks the result. Every step shows what it changes first and asks before it installs anything or changes a file of yours. It never asks for a token, an account, a name or an email address. Run it again any time: a step with nothing to do says so.

Then:

```sh
office on       # open the office and its Firstmate
office break    # walk away. Everything keeps running
office on       # come back
office off      # go home. Firstmate saves its work first, then the office stops
```

[Getting started](GETTING-STARTED.md) has every step, and what to do when one
fails.

## Status

Agent Office 1.0 is the herdr-first version. Every command in this README works
today, and each has a probe that CI runs on macOS and Linux.

- **Tested versions.** herdr 0.9.1 is the version this release is verified
  with. `office doctor` and `office update` report a Firstmate revision or
  treehouse version with no tested run as not tested and exit 1. The office
  starts and runs either way.
- **`office off` and workers.** It refuses while an agent is still working or
  waiting, and names it.
- **The tmux office (0.x)** still answers the verbs 1.0 has no version of. See
  [the tmux office (legacy)](#the-tmux-office-legacy).

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
| Agent Office herdr preset | keys for an office with no mouse, sidebar, theme and a silent "done" sound, plus an optional WezTerm example with Mac text keys | this repo ([`preset/`](preset)) |
| Agent Office meter | a herdr plugin that shows how full each agent's context window is, its transcript age, the quota left on its provider, and its git branch and open PR, in the sidebar. It also carries the Shift+arrow keys | this repo ([`herdr/`](herdr)) |
| [Firstmate](https://github.com/kunchenguid/firstmate) | supervises coding agents: dispatch, status, review, cleanup | Firstmate upstream |
| [treehouse](https://github.com/kunchenguid/treehouse) | a pool of pre-warmed git worktrees, one per worker | treehouse upstream |
| kunchenguid tools | `no-mistakes`, `gh-axi`, `chrome-devtools-axi`, `lavish-axi`, `quota-axi`, `tasks-axi`, `gnhf`, `backpass` | [their upstreams](https://github.com/kunchenguid) |
| other agent tools | `chrome-devtools-mcp` (Chrome's DevTools for agents, which `chrome-devtools-axi` drives), `acpx` (the Agent Client Protocol from the command line), `gh` (`gh-axi` drives GitHub through it) | their upstreams |
| agent integrations | herdr's Claude Code and Codex integrations. Installing the agent tools' skills is planned | upstream tools. You run `herdr integration install claude` (or `codex`) once; `office doctor` checks it |

`jq` is also required: the meter reads transcripts with it. The `office`
command needs `python3`, 3.8 or newer; the one macOS ships is enough. The
Node-based tools need Node 22.19 or newer with npm, which you install yourself
(with [fnm](https://github.com/Schniz/fnm), say). `office tools` installs every
tool in this table that is missing: see
[What `office tools` installs](#what-office-tools-installs).

### Workstation profile (optional)

Generic command-line tools that make the terminal pleasant but that the office
does not need to run: `git`, `fnm`, `ripgrep`, `fd`, `fzf`, `bat`, `eza`,
`tree`, `git-delta`, `lazygit`, `zoxide`, `starship`, `micro`, `neovim`,
`btop`, `htop`, `shellcheck`, `shfmt`, `uv`, `wget`, `tmux` and WezTerm, all
from Homebrew. `office tools --workstation` installs the ones you lack, after
showing the list. Nothing personal is in it: no apps, accounts, fonts or
editor extensions. Those stay in your own dotfiles.

Agent Office never installs or signs you in to an agent itself. Claude Code,
Codex and any other harness are installed and authenticated by you, through
their own setup.

## One config

All of it is driven by one private file:

```
~/.config/agent-office/config.toml
```

`office install` writes a starter the first time and checks the file on every
run. The keys, with the release defaults
([`config/defaults.toml`](config/defaults.toml)):

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

What each part does:

| keys | what it does |
|---|---|
| `schema` | required, must be `1` |
| `[herdr]` | merged over the [preset](preset) into the generated herdr config. herdr itself checks it |
| `[notify]` | phone notifications, off by default: `enabled`, `provider` (`"ntfy"`), `url` (your server and topic, which only your file holds) and `quiet`. Used by `office notify` and the meter plugin's hook |
| `[setup]` | the agent working setup: test workers and subagents, models, the cold-cache minutes, branches, gate commands, review and captain preferences, Firstmate's switches, the Claude Code theme. Checked like the rest. `office setup` fills [setup/](setup)'s templates in from it |
| `[office]`, `[firstmate]`, `[treehouse]`, `[meter]` | checked (an unknown key or a wrong type is an error). `office install` writes `[meter]` where the meter plugin reads it on every pass. `office doctor` reports `[firstmate]`, `treehouse.root` and the settings the running meter uses. `fm`, `office on`, `office off` and `office status` use `office.session` and `[firstmate]` except `source`. `treehouse.root` is only reported |

The generated herdr config is written to
`~/.local/state/agent-office/herdr/config.toml`, next to the preset's sound. It
is not `~/.config/herdr/config.toml`, which `office install` never touches: a
herdr you start yourself keeps your own config. `office on` is what starts
herdr against the generated one, and gives it to the window it opens, because
herdr reads its keys there.

herdr writes one line into the config it runs with: `onboarding = false`, once
you have been through its first-run setup. Agent Office keeps that line and
does not count it as a change by hand.

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

| command | what it does |
|---|---|
| `office install` | check the config, write the generated herdr config and the `office` command, link the meter plugin into herdr, stop loading the tmux office's shell function; show every change first and back up what it replaces. Starts nothing. `--check` only plans. |
| `office setup` | the whole setup in one run, the one line after the clone: four questions while you have no config yet (your coding agent, where Firstmate goes, whether to write the agent working setup, test workers and subagents), then `office tools`, Firstmate cloned at a tested revision, `office install`, `office setup agents`, herdr's integration for your coding agent, and `office doctor`. Each step shows its changes first and asks before it installs anything or changes a file of yours. `--check` only plans; `--yes` asks nothing. |
| `office setup agents` | write the agent working setup into your home from your `[setup]` keys: the agent rules (`~/AGENTS.md`, linked as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`), the review and release process, Claude Code's settings and hooks, Firstmate's model picks and switches, the no-mistakes and gnhf settings. Agent Office owns only what it puts in: a marked block, its own keys, its own files; yours stay. Shows every change first; asks before changing what you changed, and backs it up. `--check` only plans; `--remove` takes out what it put in. See [setup/README.md](setup/README.md). |
| `office tools` | install the tools the office uses that are missing, at pinned versions, each through its owner. A tool you have is left as it is. Shows the list and asks first. `--check` only plans; `--workstation` adds the optional workstation tools. |
| `office config check` / `office config show` | check the config, and the herdr config made from it / print the config in effect |
| `office on` | check the config, the generated herdr config and herdr's version; create the configured herdr session against the generated config, or use the one that runs; make sure one Firstmate is running for the configured home; attach. Running it again focuses what is there. Starts no workers. |
| `office break` | detach only: the terminals `office on` and `fm` attached. Firstmate, the workers and the terminals keep running. herdr has no detach command, so a herdr you attached yourself detaches with its key, which `office break` prints. |
| `office off` | stop this office: show what will stop, ask, let Firstmate save its work, and only when the save is confirmed stop the owned session and its meter. A session `office on` did not start is left running. It refuses while an agent in the session is working or waiting; asking Firstmate to drain its workers is planned. `--force`, confirmed separately on the terminal, stops when the save fails. Repos and worktree pools are kept. |
| `office off --all` / `officeoff-all` | stop every office this installation owns, after showing the targets and asking to confirm. Two spellings, one implementation. Anything left running makes it exit non-zero. |
| `office update` | move every component (this checkout with its CLI, preset and meter, the generated config, the agent working setup, herdr, treehouse, no-mistakes, the npm tools and Firstmate) to the version this release names, each through its owner. Shows the plan and asks first; restarts nothing. Reports each as updated, unchanged, skipped, failed, or updated on disk but not yet active, and exits 0 only when all are updated or unchanged. `--check` only plans: it changes nothing. |
| `office doctor` | read-only: each component's installed version, who updates it (a package manager or the tool itself), and whether this release is tested with that version; herdr's integration for your harness; your Firstmate source, checkout, revision and home; the herdr config and meter, installed and, while the office session runs, active; the agent working setup that `office setup agents` wrote, in place or behind. Changes nothing. Unknown is never reported as healthy: it exits 1 on any problem. |
| `office status` | read-only: what is running, what the office owns, meter health, pending restarts, and the result of the last `office off`. Unknown is never reported as healthy: it exits 1 on any problem. Pending updates are planned, with `office update`. |
| `fm [args]` | open or focus the configured Firstmate, with your arguments passed through unchanged. Needs the herdr session running; `office on` starts it. |
| `fm restart` | make Firstmate save its work, check that the save worked, then reset it. If the save fails, nothing is reset. Harness `claude` only. |
| `office keys` | print one screen of every office key: the herdr preset's keys and the Mac text keys. Read-only. Inside the office, `ctrl+space` then `?` shows herdr's own list. |
| `office notify needs-you\|pr-ready <message>` | push one line to your phone through `[notify]`. Off by default; quiet mode holds everything but `needs-you`. The meter plugin calls it when an agent turns blocked; anything that knows a PR is ready can call `pr-ready`. |

`office install`, `office setup`, `office config`, `office keys`, `office notify`, `office tools`, `office doctor`, `office update`, `office help`,
`office version`, `office on`, `office break`, `office off`, `office status`, `officeoff-all`, `fm` and `fm restart` are 1.0. Every other verb still runs the tmux office, documented in the
[legacy README](docs/legacy-tmux/README.md), until its 1.0 version lands. The
1.0 commands replace them; they are not additions to them. The tmux office's own
`doctor`, what runs and its RAM, is still there as `office list`.

### What `office doctor` checks

The components and the versions this release is tested with are data, in
[`config/components.toml`](config/components.toml). A version is listed there
only with the run that verified it. Today that is herdr 0.9.1, which CI pins.
A treehouse version or Firstmate revision with no run behind it is reported by
`office doctor` as not tested, with exit 1, until a lab run adds it.

A tool with a `pin` but no tested versions, such as each npm tool, is checked
against its pin: the version that was read before it was trusted. Another
version is a problem until the pin moves. Of the optional workstation tools,
`office doctor` checks the ones you have and does not miss the rest.

Who updates a program is read from where it is installed: Homebrew, npm,
Nix or the system's packages, or the tool itself when it has its own update
command. Anything else is reported as an unknown owner, which is a problem.

Installed is not active, so for the herdr config and the meter it shows both:

- **installed**: whether the generated herdr config and the meter settings
  still match your config (if not, run `office install`), and which meter
  folder herdr links.
- **active**, only while the office's herdr session (`office.session`) runs:
  the config that session started with, and the version, settings and last
  pass of the meter running in it. herdr reports neither, so they come from
  the meter plugin's own records in herdr's plugin state folder. A generated
  config that changed after the session started counts as not active: herdr
  does not report a `herdr server reload-config`, so only a restart is proof.
  The one thing it asks herdr is whether that session's server runs.

### What `office tools` installs

The same list, [`config/components.toml`](config/components.toml), says how
each tool installs. Always through the tool's own owner, so its usual update
path keeps working:

| kind | tools | how |
|---|---|---|
| GitHub release | herdr, treehouse, no-mistakes | the owner's release asset at the pinned version, checked against the SHA-256 in the manifest before it is unpacked, put where the owner's own installer puts it (`~/.local/bin`; no-mistakes in `~/.no-mistakes/bin`, linked from `~/.local/bin`). Its own `update` command keeps working there. |
| npm | the kunchenguid tools, `chrome-devtools-mcp`, `acpx` | `npm install -g --ignore-scripts <package>@<pin>`: no package's install scripts run. Needs Node 22.19 or newer. |
| Homebrew | `jq`, `gh`, the workstation tools | `brew install`. Homebrew owns those versions. Without Homebrew it tells you which package to install with your own package manager. |

It never pipes a downloaded script into a shell, never uses sudo, and never
replaces, updates or moves a tool you already have, whatever its version:
`office doctor` tells you when that version is not the pinned one. After each
install it checks the tool reports the pinned version, and it exits 1 if one
failed or is left for you. It does not install Node, a harness (Claude Code,
Codex) or Firstmate, and it starts nothing.

### What `office update` does

It moves each component to the version this release names in
[`config/components.toml`](config/components.toml), never to "the latest". It
shows the plan, asks, and then works through it one component at a time:

| component | target | what runs |
|---|---|---|
| this checkout (the CLI, preset and meter) | the tip of the branch it follows | `git fetch`, then `git merge --ff-only`. Never a merge commit, a rebase or a reset. When it moved, the new release's `office update` takes over, so the rest follows the new release's list. |
| a tool npm owns | its pin | `npm install -g --ignore-scripts <package>@<pin>` |
| a tool Homebrew owns | its pin or tested version | `brew info` first; `brew upgrade` only if Homebrew has exactly that version, otherwise skipped |
| herdr, treehouse, no-mistakes, where `office tools` puts them | its pin or tested version | the owner's release asset at that version, SHA-256 checked, put over the program |
| a tool Nix or the system's packages own, or that sits somewhere else | | skipped: it tells you to update it there |
| Firstmate | the newest tested revision | Firstmate's own updater when the checkout has one and its `origin` is at a tested revision; otherwise `git fetch` and `git merge --ff-only` to that revision |
| the generated herdr config, meter settings and links | your config | `office install --yes`, with its backups |
| the agent working setup, once `office setup agents` has written it | your config and this release's templates | `office setup agents --yes`, with its backups. A whole file you changed is never replaced: the new version goes beside it once, and then it is yours to compare. A block or key of Agent Office's that you changed is put back after the plan's one question, backed up first. A key you took out stays out. Off with `setup.enabled = false` |

A self-updating tool's own `update` command is not run: herdr's, treehouse's
and no-mistakes' each take no version and go to the latest release, which is
not the one this release names, and herdr's can hand over a running server.
The pinned release asset is installed instead, exactly as `office tools` does,
and only over a program that sits where `office tools` puts it.

A component with no pinned or tested version, such as `jq`, `gh` and the
workstation tools, is left to its owner. So is your harness (Claude Code,
Codex). A tool that is not installed is `office tools`' job. Nothing is ever
downgraded.

Before anything changes, each component is checked, and a blocker skips that
one component and says why: a checkout with uncommitted changes, one that has
diverged from its remote or follows none, a remote that did not answer, a
Firstmate checkout whose remote is not your `firstmate.source`, a tool with an
unknown owner, a version that cannot be read. While no Firstmate revision is
tested, Firstmate is skipped, and `office update` exits 1 for the same reason
`office doctor` does.

After each update it reads the version again, and only the target counts:

- **updated**: it is at the target now. **unchanged**: it already was.
- **skipped**: a blocker, nothing was changed. **failed**: the owner's command
  failed or left another version.
- **updated on disk but not yet active**: the new version is installed, but
  what is running is still the old one. This is said for the running herdr
  server, a generated config or meter the running session has not loaded, a
  Firstmate that was updated while it runs, and the no-mistakes daemon.
  `office update` prints the restart to run and never runs it: it stops,
  restarts or reloads no server, no Firstmate and no daemon.

It exits 0 only when every component is updated or unchanged, and 1 otherwise.
One component's failure does not hide the others' results, and running it
again does only what is left. There is no rollback: a component that was
updated stays updated.

Only one runs at a time (a lock in `~/.local/state/agent-office/`). Its
progress is recorded there in `update.json`, so a run that was killed or lost
its terminal is reported by `office update --check` and picked up by the next
`office update`. `--check` asks each remote for its tip with `git ls-remote`.
It changes no checkout, installs nothing and writes no record. To read a commit
it does not have yet, it fetches only that commit into a temporary folder and
removes the folder again.

`office update --check` shows one plan for all components, taken from one release. When this checkout will move, the `Targets:` line names the release it moves to, and every target comes from that release's `components.toml`. When it cannot read that release, the line says the targets are this release's. For each component the plan shows its owner, its target and what runs. Under it, it shows:

- for this checkout: the `cli:` version change, the `preset:` files that change, and the `meter:` version change.
- for a checkout with uncommitted changes: how many files are dirty, and which of them the update changes too, so they conflict.
- for Firstmate: the `secondmates:` it has registered in `data/secondmates.md`, read with Firstmate's own parser. It says which of them Firstmate's own updater moves, and that this check reaches no remote host.
- for the generated config: each file `office install` changes, with its diff. When this checkout moves, it is planned again from the new release.
- for each restart: whether the office session runs now, and on which herdr.

### How `fm` finds Firstmate

The office's Firstmate is the herdr agent named `firstmate` in the herdr
session `office.session`. herdr never gives two live agents one name, so `fm`
cannot pick the wrong one of two. Before it touches that agent, `fm` checks it
runs your `firstmate.harness` in your `firstmate.code`; anything else is
refused and left alone. `fm` also never adopts an agent in that checkout that
is not named `firstmate`: it prints the one `herdr agent rename` command that
adopts it, for you to run.

- **`fm [args]`** focuses that agent, or starts it in a new tab of the session,
  in `firstmate.code` with `FM_HOME` set to `firstmate.home` when you set one.
  Your arguments go to the harness unchanged, as separate arguments. A running
  Firstmate never gets them silently dropped: `fm` refuses instead. `fm --
  restart` passes the word `restart` itself. In a terminal outside herdr, `fm`
  then attaches to the session; inside another herdr session it prints the
  attach command instead of nesting.
- **`fm restart`** waits for Firstmate's turn to end, asks it to `/stow` and to
  end its receipt with a result line, and reads that line back. Only a
  "safe to reset" answer is followed by `/clear`. A missing line, a "not safe",
  a question on screen, a timeout (`--timeout MINUTES`, 30 by default) or
  Ctrl-C resets nothing, says so and exits non-zero. It runs in the foreground,
  so you see every outcome. `/clear` resets the conversation; Firstmate's
  launch-time wiring (hooks, model, flags) is read again only when it starts
  again: quit it, then run `fm`.

One `fm` runs at a time per office: a second one, a start or a restart, is
refused while the first runs.

### How `office on`, `break`, `off` and `status` work

**Ownership is a record, not a name.** `office on` starts the herdr server for
`office.session` itself and writes
`~/.local/state/agent-office/offices/<session>.json`: that server's process id,
when the process started, its socket, and the Firstmate it was started for.
`office off` stops a session only while the server behind the name is that
recorded process. A session with no record, or with another server behind the
name, is somebody else's: `office off` says so, leaves it running and exits 1.

- **`office on`** first checks that the config is valid, that the generated
  herdr config is the one your config makes now (if not: `office install`),
  that herdr reports a version, and that the Firstmate checkout and home
  exist. A herdr version this release is not tested with is a warning, and
  `office doctor` has the details. Then it starts the session, or uses the one
  that runs. A session it did not start is used as it is, with the config it
  started with, and stays not owned. Firstmate is started or focused by the
  same code as `fm`, and in a terminal outside herdr it attaches. It never
  starts a worker.
- **`office break`** detaches and stops nothing. herdr 0.9.1 has no command
  that detaches a client, so `office on` and `fm` record the client they
  become, and `office break` sends exactly those the hangup a closing terminal
  window sends. A herdr you attached yourself is not on that record: for it,
  `office break` prints the detach key.
- **`office off`** lists what stops: the session and its server, Firstmate with
  its checkout and home, every other agent in the session, the pane count, the
  meter, the attached terminals. It asks, then asks Firstmate to save through
  the same `/stow` contract as `fm restart`, and stops the session with
  `herdr session stop` only when Firstmate answers that the save worked. A
  failed, unclear, timed out or cancelled save stops nothing. So does an agent
  in the session that is still working or waiting for an answer: `office off`
  refuses and names it. After the session it stops that session's meter,
  checks both are gone, and clears the record. It never deletes a worktree,
  empties a pool or touches a repo.
- **`--force`** is for a save that cannot be confirmed. The save is still tried
  first. If it fails, `office off --force` warns that unsaved conversations may
  be lost and asks again, on the terminal, for the session name typed out.
  `--yes` answers only the first question: without a terminal, nothing is
  forced. A forced stop is the same `herdr session stop` of the same owned
  session, nothing wider.
- **`office off --all`** and **`officeoff-all`** do this for every recorded
  office, and name the running herdr sessions they leave alone. Each office is
  reported as stopped, already stopped, left, kept or incomplete; anything but
  the first two makes the exit code 1.
- **Typed inside the office.** Stopping a session ends every pane in it, the
  one you typed `office off` in too. The stop runs in a helper outside every
  session, and the result is written to
  `~/.local/state/agent-office/last-off.json` before it is printed, so
  `office status` shows it afterwards. Firstmate cannot run `office off` from
  its own pane: it could not save while it waits for the command, so that is
  refused.
- **`office status`** shows whether the session runs, who started it, the herdr
  config it started with and the meter (the same checks as `office doctor`),
  Firstmate and the other agents with their state, the terminals attached by
  `office on` or `fm`, whether herdr says its server needs a restart, other
  offices this installation started, and the last `office off`.

A session `office on` did not start is stopped by its owner only. After `herdr update --handoff` replaces a running server,
the record no longer names the process, and `office off` leaves that session
running: stop it with `herdr session stop <name>`.

### What `office install` writes

| path | what | when it exists already |
|---|---|---|
| `~/.config/agent-office/config.toml` | your config, from a starter | never touched again: it is yours |
| `~/.local/state/agent-office/herdr/` | the generated herdr config and the preset's sound | updated if Agent Office wrote it and nobody changed it since; otherwise shown, backed up, asked |
| `~/.local/state/agent-office/meter.json` | your `[meter]` keys, which the meter plugin reads on every pass | the same |
| `~/.config/herdr/plugins.json` | the meter plugin's entry, written by herdr itself: `office install` runs `herdr plugin link` on the `herdr/` folder of your checkout. The sidebar numbers and Shift+arrow come from that plugin | linked again when this release has a newer plugin. A link to another folder is shown, backed up, asked. A plugin you disabled stays disabled |
| `~/.local/bin/office`, `~/.local/bin/fm`, `~/.local/bin/officeoff-all` | links to `bin/office`, `bin/fm` and `bin/officeoff-all` in your checkout | the same: replaced only after a backup and a yes |
| `~/.zshrc` and the other zsh startup files | the line that loads the tmux office's `office` function removed: zsh finds a function before any command, so it would hide the 1.0 one | shown as a diff, backed up, asked. A file that is a link (into a dotfiles repo, say) is never written through: you get the exact lines to remove. A function or alias of your own named `fm` hides `fm` the same way: it is pointed out, never removed |

`~/.tmux.conf` keeps its tmux office lines for now: the verbs 1.0 has not built
yet still run the tmux office, which needs them. Run that way, from
`bin/office-tmux`, it is a separate process, so `office cd` cannot move your
shell.

Backups go to `~/.local/state/agent-office/backups/<time>/`, and
`~/.local/state/agent-office/manifest.json` lists every file Agent Office
owns. `--yes` skips the question, never the backup. Without a terminal to
ask on and without `--yes`, it changes nothing. `./install.sh` in the checkout
is the same as `office install`.

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
`office doctor` output is meant to be pasted into an issue, so it shows your
home folder as `~`. It does print your configured Firstmate source and any
path outside your home: read it before you post it.

## Platforms

**macOS and Linux.** Windows, including WSL2, is not supported.

## No mouse needed

The prefix is `ctrl+space`: press it, let go, then the key.

| keys | what it does |
|---|---|
| `shift+arrow` (no prefix) | left and right: the pane on that side, then the tab before or after. Up and down: the pane on that side, then the space above or below |
| `ctrl+space` `n` / `shift+n` | new space / new tab. For a tab herdr asks for a name: type one, or press Enter |
| `ctrl+space` `c` / `shift+c` | close space / close tab (both ask first) |
| `ctrl+space` `r` / `shift+r` | rename space / rename tab |
| `ctrl+space` `v` / `minus` | new pane on the right / below |
| `ctrl+space` `g` | go to an agent |
| `ctrl+space` `s` | settings |
| `ctrl+space` `d` | leave herdr. Everything keeps running |

The same letter does the same thing one level down: plain for a space, with
Shift for a tab. `office keys` prints them all on one screen, and
[the preset's README](preset/README.md#keys) explains each.

## How it is tested

Every part has a probe, a script that runs it in a throwaway home and checks
what it did. CI runs them all on every pull request. None of them touches your
own herdr, config or office.

| part | probe | against |
|---|---|---|
| the meter plugin: context size and transcript age for Claude Code, Codex, and Claude Code on a local Ollama model; quota runway, git branch and open PR. An agent it cannot identify, or a reading it does not have, stays blank, never guessed | `herdr/meter-probe` | recorded transcripts, a fake quota-axi and gh, no herdr server |
| Shift+arrow | `herdr/nav-probe` | a stand-in herdr |
| the preset: keys, sidebar, theme, sound, the WezTerm example | `preset/preset-probe` | herdr and WezTerm themselves |
| the config, `office install`, `office doctor`, `office tools` | `bin/install-probe` | throwaway homes, a real herdr, stand-in installers |
| `office update` | `bin/update-probe` | throwaway homes, stand-in owners |
| `fm` and `fm restart` | `bin/fm-probe` | a throwaway herdr session, a stand-in agent |
| `office on`, `break`, `off`, `off --all`, `status` | `bin/lifecycle-probe` | throwaway herdr sessions, a stand-in agent |
| phone notifications | `bin/notify-probe` | a stand-in ntfy server |
| nothing private ships | `bin/leak-scan-probe` | throwaway git repositories |
| the agent setup: `setup/`'s templates and the `[setup]` keys | `bin/setup-probe` | a stand-in user, rendered in memory, then `bin/leak-scan` |
| `office setup agents`, `--check`, `--remove` | `bin/setup-home-probe` | throwaway homes with files of "yours" |
| `office setup`, the one-line install | `bin/setup-all-probe` | throwaway homes, stand-in tools, a local Firstmate, a real herdr, the questions on a terminal |

CI also runs `office tools` for real, on a Linux and a macOS machine that have
none of the pinned tools: `office setup --yes`, so the GitHub release downloads with their SHA-256, the
npm installs, the Firstmate clone, `office install`, `office setup agents` and `office doctor`. That run proves the
pins and hashes in `config/components.toml` still exist.

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
  On the tag it refuses to update, which is what you want. Until the tag
  exists, the tmux installer on `main` is `bin/install-tmux [--theme]`;
  `./install.sh` is now the 1.0 installer.
- **Moving to 1.0.** `office install` (works today) finds the line that loads
  the old `office` shell function and the old `office` link, shows them, backs
  them up and replaces them, after you say yes. It never overwrites a file it
  did not write without showing the difference first. Your tmux sessions and
  `.tmux.conf` are not touched; the `.tmux.conf` lines go when the tmux office
  is retired. A zsh that is already open keeps the old function until you open
  a new one.

The legacy tmux office receives no further changes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). It says what is in scope, and how to
test without touching a live office.

## Licence

MIT. See [LICENSE](LICENSE).

---

Made by [Zyx](https://zyxworks.com). Firstmate, treehouse and the kunchenguid
tools are by [kunchenguid](https://github.com/kunchenguid). herdr is by its own
authors at [herdr.dev](https://herdr.dev).
