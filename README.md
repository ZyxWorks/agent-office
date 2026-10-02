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
> second kind is real. What is real today: the herdr meter plugin, the herdr
> preset, the config file, `office install`, which writes it all in place
> but starts nothing, `office tools`, which installs the tools that are
> missing, `office doctor`, which reports what is installed, and `fm` and
> `fm restart`. Every other `office` verb is still the tmux office (0.x).
> See [the tmux office (legacy)](#the-tmux-office-legacy) if you use that.

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
| Agent Office herdr preset | keys, sidebar, theme and a silent "done" sound, so the daily look is the default look, plus an optional WezTerm example with Mac text keys | this repo ([`preset/`](preset), works today by hand) |
| Agent Office meter | a herdr plugin that shows how full each agent's context window is, and its transcript age, in the sidebar | this repo ([`herdr/`](herdr), works today) |
| [Firstmate](https://github.com/kunchenguid/firstmate) | supervises coding agents: dispatch, status, review, cleanup | Firstmate upstream |
| [treehouse](https://github.com/kunchenguid/treehouse) | a pool of pre-warmed git worktrees, one per worker | treehouse upstream |
| kunchenguid tools | `no-mistakes`, `gh-axi`, `chrome-devtools-axi`, `lavish-axi`, `quota-axi`, `tasks-axi`, `gnhf`, `backpass` | [their upstreams](https://github.com/kunchenguid) |
| other agent tools | `chrome-devtools-mcp` (Chrome's DevTools for agents, which `chrome-devtools-axi` drives), `acpx` (the Agent Client Protocol from the command line), `gh` (`gh-axi` drives GitHub through it) | their upstreams |
| agent integrations | the skills the setup uses and herdr's Claude Code and Codex integrations | upstream tools; this repo wires them (planned) |

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

`works today`: `office install` writes a starter the first time and checks the
file on every run. The keys, with the release defaults
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

What each part does today:

| keys | today |
|---|---|
| `schema` | required, must be `1` |
| `[herdr]` | merged over the [preset](preset) into the generated herdr config. herdr itself checks it |
| `[office]`, `[firstmate]`, `[treehouse]`, `[meter]` | checked (an unknown key or a wrong type is an error). `office install` writes `[meter]` where the meter plugin reads it on every pass. `office doctor` reports `[firstmate]`, `treehouse.root` and the settings the running meter uses. `fm` uses `office.session` and `[firstmate]` except `source`. Nothing else uses them yet: `office on` is planned |

The generated herdr config is written to
`~/.local/state/agent-office/herdr/config.toml`, next to the preset's sound. It
is not `~/.config/herdr/config.toml`, which `office install` never touches: a
herdr you start yourself keeps your own config. `office on` (planned) is what
will start herdr against the generated one.

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
| `office install` | check the config, write the generated herdr config and the `office` command, stop loading the tmux office's shell function; show every change first and back up what it replaces. Starts nothing. `--check` only plans. | works today |
| `office tools` | install the tools the office uses that are missing, at pinned versions, each through its owner. A tool you have is left as it is. Shows the list and asks first. `--check` only plans; `--workstation` adds the optional workstation tools. | works today |
| `office config check` / `office config show` | check the config, and the herdr config made from it / print the config in effect | works today |
| `office on` | attach to or create the configured herdr session, and make sure one Firstmate is running for the configured home. Running it again focuses what is there. | planned |
| `office break` | detach only. Firstmate, the workers and the terminals keep running. | planned |
| `office off` | stop this office: show what will stop, let Firstmate persist and drain its workers, then stop the owned session and its meter. Repos and worktree pools are kept. | planned |
| `office off --all` / `officeoff-all` | stop every office this installation owns, after showing the targets and asking to confirm. Two spellings, one implementation. | planned |
| `office update` | update every component (the CLI, preset, meter, config, herdr, treehouse, Firstmate and the kunchenguid tools) to a tested set, each through its own updater. `--check` only plans. | planned |
| `office doctor` | read-only: each component's installed version, who updates it (a package manager or the tool itself), and whether this release is tested with that version; herdr's integration for your harness; your Firstmate source, checkout, revision and home; the herdr config and meter, installed and, while the office session runs, active. Changes nothing. Unknown is never reported as healthy: it exits 1 on any problem. | works today |
| `office status` | read-only: what is running, what the office owns, meter health, pending updates and restarts. | planned |
| `fm [args]` | open or focus the configured Firstmate, with your arguments passed through unchanged. Needs the herdr session running; `office on` (planned) will start it. | works today |
| `fm restart` | make Firstmate save its work, check that the save worked, then reset it. If the save fails, nothing is reset. Harness `claude` only. | works today |
| `office keys` | print one screen of every office key: the herdr preset's keys and the Mac text keys. Read-only. | works today |

Today, `office install`, `office config`, `office keys`, `office tools`, `office doctor`, `office help`,
`office version`, `fm` and `fm restart` are 1.0. Every other verb still runs the tmux office, documented in the
[legacy README](docs/legacy-tmux/README.md), until its 1.0 version lands. The
1.0 commands replace them; they are not additions to them. The tmux office's own
`doctor`, what runs and its RAM, is still there as `office list`.

### What `office doctor` checks

The components and the versions this release is tested with are data, in
[`config/components.toml`](config/components.toml). A version is listed there
only with the run that verified it. Today that is herdr 0.9.1, which CI pins.
No treehouse version or Firstmate revision is verified yet, so `office doctor`
reports both as not tested and exits 1 until a lab run adds them.

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
| GitHub release | herdr, treehouse, no-mistakes | the owner's release asset at the pinned version, checked against the SHA-256 in the manifest before it is unpacked, put where the owner's own installer puts it (`~/.local/bin`; no-mistakes in `~/.no-mistakes/bin`, linked from `~/.local/bin`). Its own `update` command owns it from then on. |
| npm | the kunchenguid tools, `chrome-devtools-mcp`, `acpx` | `npm install -g --ignore-scripts <package>@<pin>`: no package's install scripts run. Needs Node 22.19 or newer. |
| Homebrew | `jq`, `gh`, the workstation tools | `brew install`. Homebrew owns those versions. Without Homebrew it tells you which package to install with your own package manager. |

It never pipes a downloaded script into a shell, never uses sudo, and never
replaces, updates or moves a tool you already have, whatever its version:
`office doctor` tells you when that version is not the pinned one. After each
install it checks the tool reports the pinned version, and it exits 1 if one
failed or is left for you. It does not install Node, a harness (Claude Code,
Codex) or Firstmate, and it starts nothing.

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

### What `office install` writes

| path | what | when it exists already |
|---|---|---|
| `~/.config/agent-office/config.toml` | your config, from a starter | never touched again: it is yours |
| `~/.local/state/agent-office/herdr/` | the generated herdr config and the preset's sound | updated if Agent Office wrote it and nobody changed it since; otherwise shown, backed up, asked |
| `~/.local/state/agent-office/meter.json` | your `[meter]` keys, which the meter plugin reads on every pass | the same |
| `~/.local/bin/office`, `~/.local/bin/fm` | links to `bin/office` and `bin/fm` in your checkout | the same: replaced only after a backup and a yes |
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

**macOS and Linux.** Those are the only platforms 1.0 will claim, and only once
the new stack has been tested there. Windows, including WSL2, is not supported
by 1.0: the tmux office ran there, but the herdr-first stack has not been
tested there, so it is not claimed.

## What works today

Seven things are real right now:

1. **The herdr meter plugin**, in [`herdr/`](herdr). It shows each agent's
   context size, and its transcript age, in herdr's sidebar next to herdr's
   own state. Setup by hand is in [Getting started](GETTING-STARTED.md#today-the-meter-by-hand).
   It supports Claude Code, Codex, and Claude Code run against a local Ollama
   model; any agent it cannot identify stays blank rather than guessing. Codex
   is matched by the session id herdr's Codex integration reports; without it,
   by directory, and two Codex agents in one directory show `?` rather than a
   number that may be the other's. `herdr/meter-probe` tests it without a herdr
   server.
2. **The herdr preset**, in [`preset/`](preset): the office's keys, sidebar,
   theme and silent "done" sound as a herdr `config.toml`, and an optional
   WezTerm example with Mac text keys (Cmd and Option arrows). You copy it in
   by hand; [its README](preset/README.md) lists every key, and `office keys`
   prints them on one screen.
   `preset/preset-probe` checks it against herdr itself.
3. **The config and `office install`**: one `config.toml`, checked, and the
   herdr config generated from it, written without overwriting anything you
   made. See [What `office install` writes](#what-office-install-writes).
   `bin/install-probe` tests it in throwaway homes.
4. **`office doctor`**: what is installed, who updates it and whether this
   release is tested with it. See [What `office doctor` checks](#what-office-doctor-checks).
5. **`office tools`**: every tool of the office that is missing, installed at
   a pinned version through its owner. See
   [What `office tools` installs](#what-office-tools-installs).
6. **`fm` and `fm restart`**: open the office's Firstmate, and restart it
   only after it has saved its work. See [How `fm` finds Firstmate](#how-fm-finds-firstmate).
   `bin/fm-probe` tests it against a throwaway herdr session.
7. **The tmux office (0.x)**, documented in
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
