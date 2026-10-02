# Getting started

> **Status: in transition.** Agent Office 1.0 is herdr-first, and most of it is
> **planned**. This guide shows the 1.0 flow as a contract, marked `planned`,
> and the one piece you can set up today, marked `works today`. Using the tmux
> office? Its guide is [docs/legacy-tmux/GETTING-STARTED.md](docs/legacy-tmux/GETTING-STARTED.md).

## 1. The words you need

| word | what it is |
|---|---|
| **herdr** | the terminal workspace. It holds sessions, tabs and panes, keeps them running when you close the window, and knows whether each agent is working, idle, done or blocked |
| **pane** | one terminal inside herdr. An agent, a shell, anything |
| **Firstmate** | an agent that supervises other agents. You tell it what you want; it starts workers, watches them and reports back |
| **worker** | a coding agent Firstmate started for one task |
| **treehouse** | hands each worker its own git worktree from a pool, so workers never step on each other or on you |
| **meter** | the Agent Office herdr plugin that shows how full each agent's context window is and how long it has waited on you |

## 2. What you need first

- macOS or Linux. Windows and WSL2 are not supported by 1.0.
- A coding agent you have installed and signed in to yourself, such as Claude
  Code or Codex. Agent Office never installs or signs in to one for you.
- git.

Everything else is what `office install` is for.

## 3. The 1.0 flow

`office install` works today, in part. `office on` is planned.

```sh
git clone https://github.com/ZyxWorks/agent-office.git ~/agent-office
~/agent-office/install.sh   # works today: the config, herdr's config, the office command
office on                   # planned: open the office and its Firstmate
```

`office install` checks `~/.config/agent-office/config.toml` (and writes a
starter the first time), generates herdr's config from the preset and your
`[herdr]` keys, puts `office` on your `PATH` in `~/.local/bin`, and stops your
zsh loading the tmux office's `office` function if you had it. It shows every
change first, backs up anything it replaces and asks before it does. `--check`
shows the plan and changes nothing. It starts nothing, and it never touches
`~/.config/herdr`. [The README](README.md#what-office-install-writes) lists
every file.

Planned for `office install`: looking at what you already have and installing
the rest of the [core profile](README.md#core-profile) through each tool's own
installer. Until then, install herdr, Firstmate and treehouse yourself (below).

Ask it for the workstation profile too (planned) and it also offers the
optional [workstation tools](README.md#workstation-profile-optional).

`office on` opens the office herdr session and one Firstmate inside it. Talk to
Firstmate like any agent: say what you want done. It starts workers, each in a
treehouse worktree, and you see them in herdr's sidebar with their state and,
from the meter, their context size and how long they have waited on you.

The rest of the day:

| you want to | command | status |
|---|---|---|
| walk away, leave it all running | `office break` | planned |
| come back | `office on` | planned |
| jump to Firstmate | `fm` | planned |
| give Firstmate a fresh conversation, work saved first | `fm restart` | planned |
| see what is installed, running and healthy | `office status` | planned |
| update everything to a tested set | `office update` | planned |
| go home, office stops | `office off` | planned |
| stop every office on this machine that Agent Office owns | `office off --all` | planned |

Your settings live in one file, `~/.config/agent-office/config.toml`. The
[README](README.md#one-config) shows its shape.

## Today: the meter by hand

`works today`. The meter plugin in [`herdr/`](herdr) needs herdr 0.9.0 or
newer and `jq`.

```sh
git clone https://github.com/ZyxWorks/agent-office.git ~/agent-office
herdr integration install claude              # herdr learns each pane's session id
herdr plugin link ~/agent-office/herdr
```

The meter starts with the next herdr server. To start or replace it without
restarting Herdr, use the steps below.

Then put `$turn` and `$ctx` in the agent rows in `~/.config/herdr/config.toml`
(the [preset](#today-the-preset-by-hand) already has them, in its own colours):

```toml
[ui.sidebar.agents]
rows = [
  ["state_icon", "machine", "workspace", "tab"],
  ["state_text",
   { token = "$turn", rules = [{ contains = "h", fg = "#f55", bold = true }] },
   { token = "$ctx", fg = "#6c6", rules = [{ contains = "▲▲", fg = "#f55", bold = true, dim = false }, { contains = "▲", fg = "#fc0", dim = false }] }],
]
```

```
 ○ agent-office
   idle · 47m · 412k▲
```

`47m` is how long the agent has waited on you (idle, done or blocked). Past an
hour it shows whole hours in red, `2h`: the prompt cache has gone cold, so
waking the agent costs about as much as its context size. One ▲ (amber) past
200k tokens, two ▲▲ (red) past 600k. For smaller windows the marks appear sooner:
amber past 50%, red past 75%. The worse of cost and fill wins. `METER_WARN` and
`METER_ALARM` override the absolute limits in the meter's environment.

The meter reads Claude's assistant model and Codex's latest `turn_context` model
(with `session_meta` as a fallback). Edit [`herdr/model-windows.tsv`](herdr/model-windows.tsv)
for your selected model's window. Entries are literal model ids or prefixes;
the longest match wins. Unknown models use 1M. Plans, providers and configured
window limits can differ from the defaults in the table; adjust the matching
entry for your setup. This table cannot distinguish two sessions using the same
model id with different window limits.

`$model` is the short model label, for example `opus-5.5` or `gpt-6.1-sol`.
Put it on a separate row to keep the default 26-column sidebar readable:

```toml
["$model"], # add inside ui.sidebar.agents.rows
```

### Apply meter updates without restarting Herdr

After updating the linked checkout, replace only the running meter. The refresh
plugin action (`herdr plugin action invoke refresh --plugin agent-office.meter`)
runs `meter once`; it updates tokens immediately but does not replace the loop.
Run this in a shell with the same transcript paths and any `METER_*` overrides
as the original meter. Adjust `meter_root` and `session` for your installation:

```sh
(
set -eu
meter_root="$HOME/agent-office/herdr"
session=default
HERDR_SOCKET_PATH=$(herdr status --json --session "$session" | jq -er '.server.socket')
HERDR_BIN_PATH=$(command -v herdr)
export HERDR_SOCKET_PATH HERDR_BIN_PATH
export HERDR_PLUGIN_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/herdr/plugins/agent-office.meter"
key=$(printf %s "$HERDR_SOCKET_PATH" | cksum | cut -d' ' -f1)
pidf="$HERDR_PLUGIN_STATE_DIR/meter.$key.pid"
pid=$(cat "$pidf")
# Refuse to signal a recycled PID; wait for the old process before running start.
if ps -p "$pid" -o args= | grep -qF "$meter_root/meter"; then
  kill "$pid"
  for attempt in 1 2 3 4 5; do
    ps -p "$pid" -o args= | grep -qF "$meter_root/meter" || break
    sleep 1
  done
fi
if ps -p "$pid" -o args= | grep -qF "$meter_root/meter"; then
  echo 'meter still exiting; do not start another copy' >&2
else
  sh "$meter_root/start"
fi
)
```

For a first manual start there is no PID file: skip the PID/kill block and run
`sh "$meter_root/start"` with the environment above. The hook needs the plugin
state directory to exist, which `herdr plugin link` creates.

Verified on Herdr 0.9.1 in a named isolated session: refresh retained the PID,
kill plus the start hook produced a new PID, the server stayed running, and
teardown verified that the default session was unchanged.

## Today: phone notifications

`works today`, off by default. With the meter plugin linked (above), herdr runs
`herdr/notify` on every agent status change. When an agent turns blocked,
herdr's "needs you", it pushes one line through [ntfy](https://ntfy.sh):

```
Agent Office: needs you
claude is waiting on you in api
```

Install the ntfy app on your phone and subscribe to a topic. On ntfy.sh anyone
who knows a topic can read it, so make it long and random, or use your own
server. Then turn it on in `~/.config/agent-office/config.toml`:

```toml
[notify]
enabled = true
url = "https://ntfy.sh/<a-long-random-topic>"
quiet = false                         # true: only "needs you" gets through
```

Try it with `office notify needs-you "hello"`. A PR is not a herdr event, so
whatever knows a PR is ready calls `office notify pr-ready <url>` itself;
quiet mode holds those. The URL stays in your file: no default ships, and a
failed send never prints it.

## Today: the preset by hand

`works today`. The office's herdr keys, sidebar, theme and silent "done"
sound, and an optional WezTerm example with Mac text keys, are in
[`preset/`](preset). [Its README](preset/README.md) has the copy steps and
every key. `office keys` prints them all on one screen.

## Today: Firstmate and treehouse

Firstmate and treehouse install from their own repos today:
[Firstmate](https://github.com/kunchenguid/firstmate),
[treehouse](https://github.com/kunchenguid/treehouse). Follow their READMEs.
Wiring them into one office is what 1.0 adds.
