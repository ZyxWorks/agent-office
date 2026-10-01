# The Agent Office preset

`works today`, set up by hand. The planned `office install` will write it for
you.

The daily look and keys of the office:

| file | what it is |
|---|---|
| [`herdr/config.toml`](herdr/config.toml) | herdr keys, sidebar rows, theme and sounds |
| [`herdr/sounds/silent.mp3`](herdr/sounds/silent.mp3) | a tenth of a second of silence, the "agent finished" sound |
| [`wezterm/wezterm.lua`](wezterm/wezterm.lua) | optional: WezTerm colours, Mac text keys, and a window that opens into herdr |
| [`preset-probe`](preset-probe) | checks all of the above against herdr and WezTerm themselves |

What it gives you:

- **Keys** from the tmux office, so muscle memory carries over (table below).
- **Sidebar**: herdr's own state icon and state word stay. Between them the
  [meter](../herdr) adds context size and how long the agent has waited on you:
  `claude · 412k▲ · 47m · idle`. Without the meter those two stay blank.
- **Sound**: only "needs you" plays. A worker finishing is routine, so that
  sound is silent.
- **Theme**: monochrome. Amber means "this needs you", red means "act on this".
- **Onboarding** is left alone: a new herdr user still gets herdr's first-run
  setup.

## Set it up

You need herdr 0.9.1 or newer. If you have no `~/.config/herdr/config.toml` yet:

```sh
mkdir -p ~/.config/herdr/sounds
cp ~/agent-office/preset/herdr/config.toml ~/.config/herdr/config.toml
cp ~/agent-office/preset/herdr/sounds/silent.mp3 ~/.config/herdr/sounds/
herdr config check              # must print: config: ok
herdr server reload-config      # a running herdr picks it up
```

Already have a config? Back it up, then copy in the sections you want.
`done_path` is relative to the config file, so `sounds/silent.mp3` must sit
next to it. Run `herdr config check` after.

For `$ctx` and `$turn`, set up the meter: see
[Getting started](../GETTING-STARTED.md#today-the-meter-by-hand). The preset
already has the sidebar rows, so skip that step there.

## Keys

The prefix is `ctrl+space`: press Ctrl+Space, let go, then the key. herdr's own
default is Ctrl+B, but Ctrl+B is "back one character" in the shell and in the
agents' prompts.

On macOS, Ctrl+Space can be taken by "Select the previous input source". If the
prefix does nothing, turn that off in System Settings, Keyboard, Keyboard
Shortcuts, Input Sources.

| what | keys | herdr action |
|---|---|---|
| jump to the pane on the left | `shift+left` `prefix+left` | `focus_pane_left` |
| jump to the pane on the right | `shift+right` `prefix+right` | `focus_pane_right` |
| jump to the pane above | `shift+up` `prefix+up` | `focus_pane_up` |
| jump to the pane below | `shift+down` `prefix+down` | `focus_pane_down` |
| swap with the pane on the left | `prefix+shift+left` | `swap_pane_left` |
| swap with the pane on the right | `prefix+shift+right` | `swap_pane_right` |
| swap with the pane above | `prefix+shift+up` | `swap_pane_up` |
| swap with the pane below | `prefix+shift+down` | `swap_pane_down` |
| new pane to the right | `prefix+n` | `split_vertical` |
| new pane below | `prefix+minus` | `split_horizontal` |
| close the pane | `prefix+q` | `close_pane` |
| zoom the pane, and back | `prefix+z` | `zoom` |
| new tab | `prefix+c` | `new_tab` |
| next tab | `prefix+space` | `next_tab` |
| previous tab | `prefix+p` | `previous_tab` |
| tab by number | `prefix+1..9` | `switch_tab` |
| copy mode | `prefix+enter` | `copy_mode` |
| leave herdr, everything keeps running | `prefix+d` | `detach` |
| show or hide the sidebar | `prefix+b` | `toggle_sidebar` |
| all keys | `prefix+?` | `help` |

These are the keys herdr really uses: the preset's, plus herdr's defaults for
everything the preset leaves alone. `preset/preset-probe` checks this table
against the herdr you have. `preset/preset-probe --list` prints every key.

## Mac text keys

WezTerm has no Mac text keys of its own (iTerm2 calls them "Natural Text
Editing"). The WezTerm example adds them. Each one sends the readline key that
Claude Code, Codex and zsh all read:

| key | does | sends |
|---|---|---|
| Cmd+Left | line start | Ctrl+A |
| Cmd+Right | line end | Ctrl+E |
| Option+Left | one word back | Alt+B |
| Option+Right | one word forward | Alt+F |
| Cmd+Backspace | delete to line start | Ctrl+U |
| Option+Backspace | delete one word back | Ctrl+W |

herdr only acts on keys it has a binding for. The preset binds none of these, so
they go through herdr to the agent. `preset/preset-probe` checks both sides:
what WezTerm sends, and that herdr leaves it alone.

Another terminal? Map the same keys to the same bytes there.

## The WezTerm example

Optional. The office runs in any terminal. Copy
[`wezterm/wezterm.lua`](wezterm/wezterm.lua) to `~/.config/wezterm/wezterm.lua`,
or take the parts you want into your own. It sets the colours, turns off the
terminal bell (herdr plays the one sound that matters), dims windows without
focus, adds the Mac text keys, and opens every new window or tab straight into herdr,
falling back to your shell if herdr is missing or you detach. Font, size and
transparency stay yours: examples are commented out in the file.

## Check it

```sh
preset/preset-probe
```

It needs `herdr` and `python3`. It reads files and asks herdr for its defaults.
It never talks to a running herdr. When WezTerm and ffmpeg are installed it also
reads WezTerm's real key table and measures that the sound is silent; without
them it says it skipped those checks.
