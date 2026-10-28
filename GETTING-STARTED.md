# Getting started

From nothing to a running office, then the keys and the daily commands. Using
the tmux office (0.x)? Its guide is
[docs/legacy-tmux/GETTING-STARTED.md](docs/legacy-tmux/GETTING-STARTED.md).

## 1. The words you need

| word | what it is |
|---|---|
| **herdr** | the terminal workspace. It holds sessions, tabs and panes, keeps them running when you close the window, and knows whether each agent is working, idle, done or blocked |
| **pane** | one terminal inside herdr. An agent, a shell, anything |
| **Firstmate** | an agent that supervises other agents. You tell it what you want; it starts workers, watches them and reports back |
| **worker** | a coding agent Firstmate started for one task |
| **treehouse** | hands each worker its own git worktree from a pool, so workers never step on each other or on you |
| **meter** | the Agent Office herdr plugin that shows how full each agent's context window is, how long since it last wrote to its transcript, the quota left on its provider, and its git branch and open PR |

## 2. What you need first

- macOS or Linux. Windows and WSL2 are not supported by 1.0.
- A coding agent you have installed and signed in to yourself, such as Claude
  Code or Codex. Agent Office never installs or signs in to one for you.
- git.
- Node 22.19 or newer with npm, for the Node-based agent tools.

Everything else is what `office tools` and `office install` are for.

## 3. Install

Four steps. Each one shows what it will do and asks before it does it.

```sh
git clone https://github.com/ZyxWorks/agent-office.git ~/agent-office
~/agent-office/bin/office tools
~/agent-office/install.sh
herdr integration install claude     # or: codex
```

**`office tools`** installs each tool you lack at a pinned version, through its
owner: herdr, treehouse and no-mistakes from their GitHub releases, checked
against a pinned SHA-256; the Node-based tools with `npm install -g
--ignore-scripts`; `jq` and `gh` with Homebrew. A tool you already have is left
as it is. `office tools --workstation` adds the optional
[workstation tools](README.md#workstation-profile-optional).
[The README](README.md#what-office-tools-installs) has the details.

**`install.sh`** is `office install`. It writes a starter
`~/.config/agent-office/config.toml`, generates herdr's config from the preset
and your `[herdr]` keys, links the meter plugin into herdr, puts `office`, `fm`
and `officeoff-all` in `~/.local/bin`, and stops your zsh loading the tmux
office's `office` function if you had it. It backs up anything it replaces.
`--check` shows the plan and changes nothing. It starts nothing, and it never
touches your own `~/.config/herdr/config.toml`.
[The README](README.md#what-office-install-writes) lists every file.

If `~/.local/bin` is not on your `PATH`, it prints the line to add to your
shell's startup file. Add it and open a new terminal.

**`herdr integration install`** lets herdr learn each agent's session id. The
meter needs it to find the right transcript.

**Firstmate** is the one thing you clone yourself, from
[its repo](https://github.com/kunchenguid/firstmate). Follow its README, then
tell the office where it is:

```toml
# ~/.config/agent-office/config.toml
[firstmate]
code = "/path/to/firstmate"
```

Run `office doctor` to see what is installed and what is missing. It reports
Firstmate and treehouse as not tested, because no revision of either is on this
release's tested list, and exits 1. Those two lines are expected.

## 4. Open the office

```sh
office on
```

Run it in a plain terminal window, not inside herdr. It starts the office's
herdr session, starts one Firstmate in it, and puts you in front of it.

The first time, herdr shows its own first-run setup. Go through it or press
Esc. While it is open it takes every key, so the office's keys do nothing until
it is closed. It does not come back.

Talk to Firstmate like any agent: say what you want done. It starts workers,
each in its own treehouse worktree. You see every agent in the sidebar on the
left, with its state and, from the meter, its context size, how long since
it last wrote to its transcript, the quota left, and its branch and open PR:

```
 ○ api
   claude · 412k▲ · 47m · idle
   89% · #109 · fix/login
```

## 5. Move without a mouse

One key walks the whole office: **Shift+arrow**, with no prefix.

- Left and right: the pane on that side. From the last pane, the tab before or
  after.
- Up and down: the pane on that side. From the last pane, the space above or
  below.

Everything else starts with the prefix, `ctrl+space`: press it, let go, then
the key. A small letter is for a space, the same letter with Shift is for a tab.

| you want | keys |
|---|---|
| a new space / a new tab | `ctrl+space` `n` / `ctrl+space` `shift+n` (for a tab herdr asks for a name: type one, or press Enter) |
| close the space / the tab | `ctrl+space` `c` / `ctrl+space` `shift+c` |
| rename the space / the tab | `ctrl+space` `r` / `ctrl+space` `shift+r` |
| a new pane on the right / below | `ctrl+space` `v` / `ctrl+space` `minus` |
| go to an agent by name | `ctrl+space` `g` |
| settings | `ctrl+space` `s` |
| every key | `ctrl+space` `?`, or `office keys` in a shell |

[The preset's README](preset/README.md#keys) has every key and why.

## 6. The day

| you want to | command |
|---|---|
| walk away, leave it all running | `office break` |
| come back | `office on` |
| jump to Firstmate | `fm` |
| give Firstmate a fresh conversation, work saved first | `fm restart` |
| see what is running | `office status` |
| see what is installed, who updates it and whether it is tested | `office doctor` |
| update everything to the versions this release names | `office update` |
| go home, office stops | `office off` |
| stop every office on this machine that Agent Office owns | `office off --all` |

`office off` stops only a session `office on` started, and only after
Firstmate confirmed it saved its work. If Firstmate does not confirm, nothing
stops, and `office off` says why. `office break` detaches the terminals
`office on` and `fm` attached; in a herdr you attached yourself, press
`ctrl+space` then `d`.
[The README](README.md#how-office-on-break-off-and-status-work) has the rules.

Your settings live in one file, `~/.config/agent-office/config.toml`. The
[README](README.md#one-config) shows its shape. After you change it, run
`office install` again: it shows the difference and writes the new herdr
config.

## 7. When something is off

| you see | do this |
|---|---|
| `ctrl+space` does nothing, on macOS | macOS has it for "Select the previous input source". Turn that off in System Settings, Keyboard, Keyboard Shortcuts, Input Sources |
| no key does anything, right after `office on` | herdr's first-run setup is open. Close it with Esc |
| the keys are herdr's defaults (`ctrl+b`), not the office's | you attached with `herdr session attach` yourself. herdr reads its keys in the window, so use `office on` or `fm`, which give it the office's config |
| `office on` says the generated herdr config is older | you changed your config or updated the checkout. Run `office install`, then `office on` |
| `office on` says this pane is in another herdr session | you ran it inside herdr. Run it in a plain terminal window |
| the sidebar shows no numbers | run `herdr integration install claude` (or `codex`), then `office doctor`: it says what the meter runs with |
| `office off` stops nothing | it says why: Firstmate did not confirm its save, or an agent is still working. `office status` shows it again |

`office doctor` and `office status` change nothing, and their output is safe to
read at any time.

## The meter in detail

```
 ○ api
   claude · 412k▲ · 47m · idle
   89% · #109 · fix/login
```

`47m` is transcript age: how long since the agent last wrote to its
transcript, shown while herdr says it is idle, done or blocked. Past an hour it
shows whole hours, `2h`. It is a hint that a desk has sat a while. It is not
proof of how long the agent has waited on you, and it knows nothing about a
provider's prompt cache or billing.

One ▲ (amber) past 200k tokens, two ▲▲ (red) past 600k. For smaller windows the
marks appear sooner: amber past 50%, red past 75%. The worse of size and fill
wins.

The limits and the pass interval come from the `[meter]` keys of your Agent
Office config: `office install` writes them to
`~/.local/state/agent-office/meter.json`, and the meter reads that file again
on every pass, so a change reaches a running meter without a restart. Without
that file, `METER_EVERY`, `METER_WARN` and `METER_ALARM` in the herdr server's
environment set them. A variable exported after the server started never
reaches it. `office doctor` shows what the running meter uses.

Codex panes are matched by the session id that herdr's Codex integration
reports (`herdr integration install codex`). Without it the meter guesses by
directory, and two Codex panes in one directory show `?` instead of a number
that may belong to the other one.

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

The third row is the quota left and where the agent works. `89%` is what [quota-axi](https://github.com/kunchenguid/quota-axi) says is left on the pane's provider (Claude or Codex), on pace to last until the limit resets. `41%▼2h` (amber) means it is projected to run out in about two hours, `0%▼▼` (red) that it is out now. A Claude session on a model with its own limit (Fable has a weekly one) shows that model's figure. `#109` is the open pull request for the branch checked out where the agent runs, as `gh pr view` finds it there, and `fix/login` is that branch. quota-axi and gh ask a server, so the meter asks them in the background at most once every five minutes (once per branch for gh) and shows the last answer. Anything it does not know stays blank: no quota-axi or gh, a stale or unreadable quota reading, two accounts for one provider, a detached HEAD, no open PR.

### Apply meter updates without restarting Herdr

After updating the linked checkout, replace only the running meter. The refresh
plugin action (`herdr plugin action invoke refresh --plugin agent-office.meter`)
runs `meter once`; it updates tokens immediately but does not replace the loop.
Run this in a shell with the same transcript paths as the original meter. Adjust `meter_root` and `session` for your installation:

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

`office doctor` tells the installed meter from the running one: when the
version or folder it runs differs from what is installed, replace it as above.

Verified on Herdr 0.9.1 in a named isolated session: refresh retained the PID,
kill plus the start hook produced a new PID, the server stayed running, and
teardown verified that the default session was unchanged.

## Phone notifications

Off by default. `office install` links the meter plugin, and with it herdr runs
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

## The preset and the meter in a herdr of your own

You do not need `office on` to use them. In a herdr you run yourself:

```sh
herdr integration install claude
herdr plugin link ~/agent-office/herdr
```

Then copy the preset, or the parts you want, into your own
`~/.config/herdr/config.toml`: [the preset's README](preset/README.md#set-it-up-by-hand)
has the steps. Its `[ui.sidebar.agents]` rows are what show `$ctx` and `$turn`.
The meter starts with the next herdr server.
