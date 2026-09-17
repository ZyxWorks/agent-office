# Contributing

Pull requests are welcome. `main` is protected, so everything lands through
one, mine included.

## How to propose a change

1. Fork, branch off `main`.
2. Make the change, and **say how you verified it**. See below.
3. Open a PR against `main` describing what you saw before and after.

Small, obviously-correct fixes get merged quickly. Anything that changes the
layout model or adds a command is worth an issue first, so you do not build
something that turns out to be out of scope.

## What this project is

A tmux cockpit for running several coding-agent sessions at once. Around 2,100

lines of zsh and tmux config, nine probes that drive a real tmux server, and one
iTerm2 profile.

**In scope:** making that faster, clearer or harder to get wrong. Support for
agents other than Claude Code, provided it stays a variable and not a special
case.

**One action, one key.** No aliases, no "this still works if your fingers know
it": a second way to close a pane is a second row in every table and a key bar
that has to choose. A key that is replaced is removed, and `unbind`-ed by name
in `office.tmux.conf` so a long-running server drops it on the next reload.

**Out of scope:** a plugin system, a config file, a daemon, a package manager,
a dependency that does what twenty lines already do. If a feature needs
persistent state, it probably needs a rethink instead. `office off` kills the
tmux server, and everything has to survive that.

## The rules the code follows

- **zsh and tmux, nothing else at runtime.** `fzf`, `fd`, `git`, `micro` and
  `bat` are the only external commands, and each is either required at install
  or degrades to nothing.
- **`office.tmux.conf` sets no colours.** Not one. A user's theme has to
  survive installation. Anything visual belongs in `theme/`.
- **A key the office does not bind reaches the pane unchanged.** The office owns
  Shift-arrow and the Ctrl-Space table; every other key belongs to whatever is
  running in the pane, including the modified keys ASCII has no byte for
  (Shift-Enter, Ctrl-Enter). tmux swallows those by default, which is why
  `extended-keys always` is set — a person should not lose a keystroke that
  works in every other window just because this one has a layout. Same rule one
  layer up: the installer names the parent iTerm profile and writes **no**
  `Keyboard Map`, so a binding you add later is inherited rather than frozen out.
  Changing key handling means probing what every OTHER key now sends, not just
  the one you meant to fix.
- **Nothing destructive without a confirmation**, except `office clean --idle`,
  which exists to be unattended and says so.
- **Keybindings never print.** Output from a `run-shell` binding makes tmux
  force the active pane into view-mode, where every office key stops working. Use
  `_office_say`, which goes to the status line.
- **Anything shown on a pane border is untrusted.** Labels are stripped of `#`
  before storage, because tmux renders them through its format engine where
  `#(...)` runs a shell command.
- **Comments say why, not what.** The interesting comments in here are the ones
  recording a trap someone already fell into. Add to them.

## Verifying a change

There is no test suite, because almost everything here is a side effect on a
live tmux server. Instead, every change should come with the commands you ran
and what you saw. The pattern that works:

```sh
# build a throwaway office, look at it, tear it down
d=$(mktemp -d)/t; mkdir -p $d; git -C $d init -q
OFFICE_SOLO=1 _office_open "$d"; s=$(_office_sessname "$d"); sleep 4
tmux list-panes -t "=$s" -F '#{@office_num} #{pane_left},#{pane_top} #{@office_kind}' | sort -n
tmux kill-session -t "=$s"; rm -rf "${d:h}"
```

`OFFICE_SOLO=1` skips the always-on hooks. Always tear the session down, and
never test against an office you are working in.

Touched `_office_find`, `_office_fallback`, `_office_sessname` or anything else
that decides WHICH repo an office opens on? Run `bin/root-probe`. Most of it
needs no tmux at all -- those decisions are pure, so a throwaway `CODE_ROOT` with
three git repos in it stands in for what used to be provable only by opening an
office and reading the title. It pins the three ways the choice has been wrong:
an empty `OFFICE_DEFAULT` opening whatever sorted first instead of the repo you
are standing in, a name that does not resolve falling back to `$PWD` in silence,
and a dead `CODE_ROOT` blaming the name instead of itself. The last case does
need a server, on its own socket: two repos with ONE basename -- `~/work/api`
and `~/personal/api` -- must get an office each, `api` and `api-2`, each holding
the checkout it opened on in `@office_root`. Sharing the name meant the second
`office on` attached you to the first repo's office, with agents rooted in a
checkout you never asked for and nothing on screen saying so.

Touched anything about keys? Run `bin/key-probe`. It builds a throwaway office
on its own socket, attaches a REAL client on a pty and types raw bytes at it,
then checks both halves at once: a bound key moves you and never reaches the
pane, every other key reaches the pane byte for byte. The keys worth checking
are the twenty you did not mean to change. It exits non-zero if any moved.

`tmux send-keys` cannot stand in for that client: it writes to the pane's tty
and never consults a key table, so Shift-Left looks broken under send-keys and
is perfectly fine for a human.

Touched the mouse or copy mode? Run `bin/mouse-probe`. Same throwaway office and
same real client, but it writes raw SGR mouse bytes: a drag has to land on the
clipboard in every pane kind, and Escape and a click have to get you out of copy
mode. Two things it catches that reading the config does not. Cancelling copy
mode on a click must wait for the mouse *release* and must skip a selection
already in flight, or a double-click loses its word and strands the pane in the
hidden copy mode it opened. And a double-click cannot be read back for a full
second: tmux holds it for its own 500ms triple-click window before the binding
starts, so a check that looks sooner reports a working gesture as broken.

Touched the grid — adding, parking, unparking, moving or closing a pane, or
anything that reads `pane_left`, `pane_top` or a window size? Run
`bin/grid-probe`. It builds a throwaway office and drives the same calls the
menu items and key bindings make (`office new --agent N`, `--shell`, `--edit`,
`--back <window>` — `display-menu` cannot be made to draw headless, so the menu
itself is out of reach), then checks the geometry after every step: at most
three across, at most two rows, the top row filling first and taking the odd
pane (three panes is always "2 1", five is "3 2", never "2 3"), zoom dropped before anything is
measured, and the grid re-fitting itself after a close it did not initiate
through `office.zsh` (the config's `after-kill-pane` hook). Reading the code
does not tell you whether the layout string it built was actually valid; the
probe does — tmux silently refuses one whose checksum does not match, so a bug
here reads as "nothing happened" rather than an error.

Touched `bin/office-attn`, `@office_attn_gate` or a `pane-border-format`? Run
`bin/attn-probe`. It builds a throwaway office and puts fake agents in the desks
that move the way real ones do, then drives the real watcher. Two cases in it are
the whole reason the file is shaped the way it is, and neither is visible in the
code: **an idle agent pane is not perfectly still** (Claude Code rotates a hint
line under its input box, so "still" has to tolerate a line moving), and **an
agent that is thinking moves exactly one line** (its spinner, which that same
tolerance then eats — worth eighteen seconds of a border saying "your turn"
mid-task before it was measured). One case here rotates a line and must still
count as waiting; another animates one line at 10Hz and must never. It also
checks the gate by expanding the expression that ships rather than a copy of it.

Touched `bin/office-ctx`? Run `bin/ctx-probe`. No Claude Code and no API call
needed: that script reads exactly three things — the pane's process group,
`~/.claude/sessions/<pid>.json` and `~/.claude/projects/<slug>/<id>.jsonl` — so a
fake `$HOME` holding those two files is a complete stand-in, and the probe is the
written-down version of the layout it depends on. The bug it caught while being
written is the one to know about: the same token keys appear **twice** in a usage
record, once at the top level and again inside `iterations`, and treating a
top-level zero as "not filled in yet" let the second copy overwrite the first.
Every number came out about 20k high, which is exactly plausible enough to be
believed.

One thing that probe cannot do, and it is worth knowing before you write another:
**`display-message -p` expands formats with jobs switched off**, so a `#()` in
one is always empty there. Measured on 3.7b — five calls over five seconds and
the command never ran once. A drawn border does run it; a probe reading one back
does not.

Touched `OFFICE_AGENTS`, `_office_new` or the `Ctrl-Space n` menu? Run
`bin/agent-probe`. It builds a throwaway office and drives `office new`
directly — no real client: a named worktree opens agent 1, `--agent 2` (by
number) and `--agent <LABEL>` both split the right command and label out of the
array, and a bare `office new` opens nothing, because the menu needs a client
this probe deliberately does not attach.

Touched `_office_open`, the first pane's wait, the menu, or parking? Run
`bin/menu-probe`. It is the one that DOES attach a client, on a pty, and types
at it: the office opens as one pane whose menu draws by itself, `1` turns that
pane into the first agent, `Ctrl-Space n` then `s` adds a shell, `Ctrl-Space x`
parks it, and the next menu brings it back under `a`. Its rc file is a
throwaway `ZDOTDIR` pointed at this checkout, because every menu item runs
`zsh -ic`, and your own `~/.zshrc` may source a different copy of office.

**A probe must never reach your office.** `TMUX_TMPDIR` alone does not isolate
it: inside a desk, tmux talks to the server in `$TMUX` first. A probe run from a
desk on 2026-09-11 cleaned up with a bare `tmux kill-server` and killed the whole
live office. So every new probe either names its socket on every call (`tmux -L`,
as `key-probe` does) or runs `unset TMUX TMUX_PANE` right after exporting
`TMUX_TMPDIR`, as the zsh probes do.

CI runs all seven on every push, on **macOS and Ubuntu**, and the gap between them
is worth keeping: Ubuntu ships tmux 3.4 against macOS's 3.7b, and that alone
found two version-dependent bugs on its first run — `#{!:...}` silently inverting
a gate, and a probe asserting one Shift-Enter encoding when tmux picks it by
version. Prefer `#{==:x,0}` to `#{!:x}`. And check an option EXISTS on 3.4 before
reaching for it: `extended-keys-format` does not, so setting it would print
`invalid option` into every reload of the config that exists to make keys work.

Run `zsh -n office.zsh` before you push. It catches most of it.

## Reporting a bug

Include `tmux -V`, your terminal, and the output of:

```sh
office doctor
tmux list-panes -a -F '#{session_name} #{pane_id} #{@office_kind} #{pane_left},#{pane_top}'
tmux list-keys -T root | grep -E ' M-| C-S-|Mouse|Click'
```

If a key does nothing, that last one plus your terminal's name is usually the
whole answer. It covers the mouse too: a drag or a double-click that does not
copy shows up there as a missing or shadowed binding.
