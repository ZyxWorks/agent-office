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
| **meter** | the Agent Office herdr plugin that shows how full each agent's context window is |

## 2. What you need first

- macOS or Linux. Windows and WSL2 are not supported by 1.0.
- A coding agent you have installed and signed in to yourself, such as Claude
  Code or Codex. Agent Office never installs or signs in to one for you.
- git.

Everything else is what `office install` is for.

## 3. The 1.0 flow (planned)

None of these commands exist yet. This is what they will do.

```sh
office install      # planned: check, install what is missing, write the config
office on           # planned: open the office and its Firstmate
```

`office install` looks at what you already have, installs the rest of the
[core profile](README.md#core-profile) through each tool's own installer, and
writes `~/.config/agent-office/config.toml`. It shows every file it will
change and backs it up first. It starts nothing.

Ask it for the workstation profile too (planned) and it also offers the
optional [workstation tools](README.md#workstation-profile-optional).

`office on` opens the office herdr session and one Firstmate inside it. Talk to
Firstmate like any agent: say what you want done. It starts workers, each in a
treehouse worktree, and you see them in herdr's sidebar with their state and,
from the meter, their context size.

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

The meter starts with the next herdr server. Stopping the server stops
everything running in it, so restart herdr when no work is running there.

Then add `$ctx` to the agent rows in `~/.config/herdr/config.toml`:

```toml
[ui.sidebar.agents]
rows = [
  ["state_icon", "machine", "workspace", "tab"],
  ["agent",
   { token = "$ctx", dim = true, rules = [{ contains = "▲▲", fg = "#f55", bold = true, dim = false }, { contains = "▲", fg = "#fc0", dim = false }] }],
]
```

```
 ○ agent-office
   claude · 412k▲
```

One ▲ past 400k tokens, two past 600k. Change those with `METER_WARN` and
`METER_ALARM` in the environment the herdr server starts in. herdr's own state
icon still says whether the agent is working, idle, done or blocked.

Firstmate and treehouse install from their own repos today:
[Firstmate](https://github.com/kunchenguid/firstmate),
[treehouse](https://github.com/kunchenguid/treehouse). Follow their READMEs.
Wiring them into one office is what 1.0 adds.
