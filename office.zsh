# agent-office — ONE command: `office`.
#
# https://github.com/ZyxWorks/agent-office
#
#   office on         walk in — open your office and start the day
#   office break      step out — detach; panes, sizes and agents all stay put
#   office off        go home — quit the office you are in, layout and all
#   office off --all  ...and every other office on the machine with it
#
#   office <repo>     open a different repo (fuzzy name, e.g. `office myproj`)
#   office pick       fuzzy-pick from all your repos
#   office solo       like `on`, but start nothing but the tabs
#
#   office new        one more pane: pick an agent, a shell or the editor  (^Sn)
#   office new --agent <a> [wt]   ...straight to that agent, in its OWN worktree
#   office task ...   another session, started on a task straight away
#   office desk       another session in THIS checkout, when you mean it
#   office hide/show  park the pane you are on / bring a parked one back (^Sx)
#   office cd [x]     walk the shell into another worktree; the editor follows
#
#   office doctor     what's running and what it costs in RAM (read-only)
#   office clean      pick panes to close and reclaim their RAM
#   office sweep      close offices you walked away from, and all they run
#   office update     pull the newest agent-office (never happens on its own)
#   office install    wire office into zsh + tmux again: ./install.sh [--theme]
#
# Bare `office` prints this. `ao` and `o` are the short aliases.
# Key bindings live in office.tmux.conf; `office help` lists every one of them.
# Configure with the OFFICE_* variables below; see the README.

_OFFICE_OWN_PGID=$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')
_OFFICE_HOME=${0:A:h}                  # where this package lives, for its helpers
zmodload -F zsh/stat b:zstat 2>/dev/null
# what was on disk when this shell loaded it — see office() for why.
_OFFICE_MTIME=$(zstat +mtime "$_OFFICE_HOME/office.zsh" 2>/dev/null)
CODE_ROOT="${CODE_ROOT:-$HOME/code}"
OFFICE_DEFAULT="${OFFICE_DEFAULT:-}"        # repo `office on` opens; empty = the one you are in
# What a session IS. Point it at any agent CLI and every desk becomes that.
OFFICE_SESSION_CMD="${OFFICE_SESSION_CMD:-claude}"
# How every desk ends. Quitting the agent leaves the pane on a prompt — nothing
# is lost and the pane is yours — but a border still labelled CLAUDE over a bare
# shell reads like a broken window to anyone new. One line says otherwise.
# printf, not print: this string is run by tmux's default shell, not by zsh.
_OFFICE_DESK_END="; printf '\n  session ended — the pane is a shell now. Ctrl-Space n opens a new one.\n'; exec zsh"
OFFICE_SESSION_LABEL="${OFFICE_SESSION_LABEL:-CLAUDE}"

# Desks on more than one provider: Claude, Codex, a local model. Each element
# is "LABEL command words...", the label first and the rest the pane command —
# see the README for the shape. Left unset, it is built from the two variables
# above, so an existing .zshrc sees no change at all: one agent, and Ctrl-Space
# n still offers it. `_office_menu` lists every entry, plus a shell and the editor.
typeset -ga OFFICE_AGENTS
(( ${#OFFICE_AGENTS} )) || OFFICE_AGENTS=("$OFFICE_SESSION_LABEL $OFFICE_SESSION_CMD")
# Agent 1 is also what every path older than OFFICE_AGENTS still runs — the
# startup desks, `office desk`, `office task`, the `sessions` refill — because
# all four of those read these two variables and nothing else. Re-deriving
# them here means setting OFFICE_AGENTS alone (without touching these two)
# still changes what those open, and nothing downstream had to learn a new
# variable.
OFFICE_SESSION_LABEL="${${(z)OFFICE_AGENTS[1]}[1]}"
OFFICE_SESSION_CMD="${(j: :)${(z)OFFICE_AGENTS[1]}[2,-1]}"
# Where `office new` looks for git worktrees. Claude Code's default location.
OFFICE_WORKTREE_DIR="${OFFICE_WORKTREE_DIR:-.claude/worktrees}"
# How long a desk has to sit completely still before its border says "your turn".
# Long enough that a pause between two tool calls is not an interruption, short
# enough that you are not the last to know. Raise it if your agent goes quiet
# mid-task without redrawing anything at all. See bin/office-attn.
OFFICE_ATTN_SECS="${OFFICE_ATTN_SECS:-20}"
# When a desk's context window stops being furniture and starts being a decision.
# Under the first mark the number is just there; over it, it goes to the theme's
# accent; over the second, to its alarm. Defaults suit a large window — set them
# to something like 120000 and 170000 for a 200k one, because "full" depends on
# the window your plan gets and nothing here can know that. See bin/office-ctx.
OFFICE_CTX_WARN="${OFFICE_CTX_WARN:-400000}"
OFFICE_CTX_ALARM="${OFFICE_CTX_ALARM:-600000}"

# ---------------------------------------------------------------- internals --
_office_sessname() { basename "$1" | tr ' .:' '___'; }
_office_root()     { git -C "${1:-$PWD}" rev-parse --show-toplevel 2>/dev/null || print -r -- "${1:-$PWD}"; }

# The name above is the repo's BASENAME, and two checkouts can share one:
# ~/code/work/api and ~/code/personal/api both want the session `api`. Then
# `office on` in the second one sees `has-session` succeed and attaches you to
# the FIRST one's office -- agents rooted in the wrong checkout, and nothing on
# screen saying so. So every office writes the root it opened on as
# `@office_root`, and a name already held by a DIFFERENT root steps aside to a
# suffix (`api-2`), the way `_office_free_wt` numbers desks.
#
# A session with NO `@office_root` is one this version did not create -- an
# office already running when the package was updated. It counts as a match:
# stepping aside from it would strand you in a second office on the repo you are
# already sat in, which is the very thing this exists to prevent.
_office_sessfor() {                    # <repo-path> -> the session name to use
  local dir=${1:A} base name held n=1
  base=$(_office_sessname "$dir"); name=$base
  while tmux has-session -t "=$name" 2>/dev/null; do
    held=$(tmux show -t "$name" -qv @office_root 2>/dev/null)
    [[ -z $held || $held == $dir ]] && break
    name=$base-$(( ++n ))
  done
  print -r -- "$name"
}

# Stand where the key was pressed. The bindings hand the pane's path in here
# instead of doing their own `cd`, because that pane can be standing in a
# directory that is GONE — a session worktree reaped by a sweep while its agent
# was still sat in it, which is the normal end of a desk's life. The bindings
# read `cd "<pane path>" && office …`, so the failed `cd` took the whole line
# with it and the key did NOTHING: not one broken key, EVERY office key in that
# pane, and silently, because a keybinding's output is muted on purpose. The
# nearest directory that is still there is inside the same repo, which is all
# any command here asks of $PWD.
_office_pane_cwd() {
  local d=${OFFICE_PANE_PATH:-}
  unset OFFICE_PANE_PATH
  [[ -n $d ]] || return 0
  until [[ -d $d ]]; do d=${d:h}; done   # :h of / is /, so this always lands
  cd "$d"
}

# WHICH office this pane is in. Ask tmux, never $PWD: deriving it from the
# directory meant one `cd` out of the repo (or into a different one) renamed the
# office out from under every helper — the editor stopped following the shell,
# and `office n`/`layout`/`show` quietly targeted a session that did not exist.
# Outside tmux there is no pane to ask, so the directory is still the answer.
# A menu item names its office outright (OFFICE_SESSION): it runs detached, with
# no pane of its own to ask, and "the current session" is a guess with two
# offices open.
_office_here() {
  local s=${OFFICE_SESSION:-}
  [[ -z $s && -n $TMUX ]] && s=$(tmux display -p -t "${TMUX_PANE:-}" '#{session_name}' 2>/dev/null)
  [[ -n $s ]] && print -r -- "$s" || _office_sessfor "$(_office_root "$PWD")"
}

# every git repo under $CODE_ROOT, agent worktrees excluded
_office_repos() {
  fd --type d --max-depth 4 --hidden --no-ignore '^\.git$' "$CODE_ROOT" 2>/dev/null \
    | sed 's|/\.git/*$||' | grep -v "/${OFFICE_WORKTREE_DIR}/" | sort -u
}

_office_find() {                       # <name> -> absolute repo path
  local q=$1 hit
  # An EMPTY name is not a search, it is the absence of one, and it must find nothing so the
  # caller can fall back to the repo you are standing in. Without this guard the substring pass
  # below runs `grep -i -- ""`, which matches every line and hands back whatever sorts first --
  # so `office on` with the documented default (OFFICE_DEFAULT empty, "the one you are in")
  # opened the alphabetically first repo under CODE_ROOT from anywhere. It only looked correct
  # while CODE_ROOT pointed at nothing and the search came back empty for the wrong reason.
  [[ -n $q ]] || return 1
  [[ -d $q ]] && { (cd "$q" && pwd); return }
  hit=$(_office_repos | grep -iE "/${q}$" | head -1)
  [[ -n $hit ]] || hit=$(_office_repos | grep -i -- "$q" | head -1)
  [[ -n $hit ]] && print -r -- "$hit"
}

# Where `office on` goes when the default did not resolve: the repo you are standing in. That is
# the right answer often enough to keep as the fallback -- and exactly why it has to SAY when it
# is one. A CODE_ROOT left pointing at a folder that has since been renamed finds nothing, so
# `office on` opened an office on $HOME, named after the home folder, with nothing on screen
# connecting the two. One line turns that from "all of it is broken" into a fixable sentence.
_office_fallback() {                   # <the name that was wanted> -> the dir to open instead
  local want=$1 here; here=$(_office_root "$PWD")
  if [[ -n $want ]]; then              # a name WAS asked for and did not resolve -- always say so
    if [[ ! -d $CODE_ROOT ]]; then
      print -u2 -P "%F{yellow}office: CODE_ROOT is not a folder:%f ${CODE_ROOT/#$HOME/~}"
      print -u2    "  set it to where you keep your repos:  export CODE_ROOT=~/your/repos"
    else
      print -u2 -P "%F{yellow}office: no repo called '$want' under%f ${CODE_ROOT/#$HOME/~}"
      print -u2    "  see what is there:  office pick"
    fi
    print -u2 "  opening ${here/#$HOME/~} instead."
  fi
  print -r -- "$here"
}

# attach. Plain tmux on purpose: ONE iTerm2 window, real splits inside it.
# (Control mode, -CC, turns every pane into a separate native iTerm2 tab, which
# is the opposite of a cockpit. It was behind an env var nobody ever set.)
_office_attach() {
  local s=$1
  if [[ -n $TMUX ]]; then tmux switch-client -t "=$s"
  else tmux attach-session -t "=$s"; fi
}

# A tmux server holds the config it read the day it started. Pull the package,
# move it, or edit a binding, and the server you walk back into is still on the
# old one — silently, which is worse than an error. Walking in is the moment to
# re-read it. ~/.tmux.conf and not office.tmux.conf: it sources the package AND
# the theme, in the order the theme needs (it overrides the pane border, so it
# has to come second). Same file `Ctrl-Space r` reloads.
_office_reload_conf() { tmux source-file ~/.tmux.conf 2>/dev/null }

# Two things the tmux config cannot work out for itself, handed over on the way
# in. Both are read by the "your turn" watcher on the pane borders.
#
#   @office_home       a tmux config has no way to know its own path, and the
#                      watcher is a file next to it. The one place that always
#                      knows is this file.
#   @office_attn_secs  because OFFICE_ATTN_SECS is an environment variable and
#   @office_ctx_warn   the watchers run as #() jobs, which tmux starts from the
#   @office_ctx_alarm  SERVER's environment — not the shell you exported them in.
#                      Same trap the theme's status-right documents. Pushing them
#                      into options is what makes an OFFICE_* variable in your
#                      .zshrc mean anything to a job inside the server.
_office_watch_setup() {
  tmux set -g @office_home "$_OFFICE_HOME" 2>/dev/null
  tmux set -g @office_attn_secs "$OFFICE_ATTN_SECS" 2>/dev/null
  tmux set -g @office_ctx_warn "$OFFICE_CTX_WARN" 2>/dev/null
  tmux set -g @office_ctx_alarm "$OFFICE_CTX_ALARM" 2>/dev/null
  return 0
}

# ZOOM LIES ABOUT GEOMETRY, and every layout answer in this file is geometry.
# While a pane is zoomed, tmux reports THAT pane at full-window coordinates:
# pane_left 0, pane_top 1, the whole width. The other panes keep their old
# numbers, so `_office_number` numbers by a position nothing is at. An older
# layout engine that trusted those numbers broke every pane out to the stash
# and rejoined them, all from a lie: zoom, unzoom, one shell left on screen.
#
# tmux was never going to keep the zoom anyway: its own resize-pane unzooms the
# window silently (check window_zoomed_flag after one). So drop it FIRST and on
# purpose. An office command that touches the room shows you the room.
_office_unzoom() {                     # <session>
  # A pane id, and nothing shorter. `resize-pane -t "=<session>"` is not a
  # target tmux accepts ("can't find pane"), and display-message -t "=session"
  # returns EMPTY for window flags — the same trap as window_height in
  # _office_grid. Both fail silently, which is a guard that guards
  # nothing. Ask for the panes instead: the ACTIVE pane of every zoomed window,
  # which is the only pane a window can be zoomed on.
  local p n=0
  for p in ${(f)"$(tmux list-panes -s -t "=$1" -F '#{pane_id}' \
                   -f '#{&&:#{pane_active},#{window_zoomed_flag}}' 2>/dev/null)"}; do
    # ++n, never n++: post-increment EVALUATES to the OLD value, so `(( n++ ))`
    # on the first pane is arithmetic-false, ends the && chain, and in a shell
    # with err_return set returns out of whatever called this.
    [[ -n $p ]] && tmux resize-pane -Z -t "$p" 2>/dev/null && (( ++n ))
  done
  # and SAY so. The zoom going away silently is the half of this the operator
  # actually felt: the room came back while he was looking at one pane, so the
  # next Ctrl-Space z — pressed to zoom OUT — zoomed IN on whatever pane the
  # command had just left him on, and the screen went down to that one pane.
  # A toggle is never wrong about the state. It was the state that moved.
  (( n )) && _office_say "unzoomed — Ctrl-Space z zooms again"
  return 0
}

# --- the grid ----------------------------------------------------------------
# An office starts as ONE pane that asks what it should be, and every pane after
# that is one more cell in a grid: at most three side by side, at most two
# stacked. Six in all. Past that a pane is a slit and not a place to work.
#
#   1 [A]      2 [A|B]      3 [A|B]      4 [A|B]      5 [A|B|C]      6 [A|B|C]
#                             [ C ]        [C|D]        [ D | E ]      [D|E|F]
#
# It fills the way you read: the top row first, then the row below. The top row
# holds the extra pane when the count is odd, so a third pane goes underneath
# rather than squeezing the first two (operator, 2026-09-17).
#
# tmux's own `tiled` is not this: it stacks before it goes sideways, so two panes
# come out one above the other. So the layout is written out whole, as the same
# string `list-windows -F '#{window_layout}'` prints, and handed to select-layout.
# The panes fill it in tmux's own pane order, which is the order they were added.
#
# Rebuilt on every add, park, unpark and close (the tmux config hooks the close),
# so a border you dragged snaps back the next time the office changes shape.
# ponytail: one fixed shape per count. A remembered custom split is the upgrade.
_OFFICE_MAX_PANES=6
_office_grid() {                       # <session>
  local s=$1 W H n m r c k=1 x y=0 cw rh body i ch csum=0
  local -a ids cells rows
  ids=(${(f)"$(tmux list-panes -t "=$s" -F '#{pane_id}' 2>/dev/null)"})
  n=$#ids
  read -r W H <<< "$(tmux list-windows -t "=$s" -F '#{window_width} #{window_height}' 2>/dev/null | head -1)"
  if (( n > 1 )) && [[ $W == <-> && $H == <-> ]]; then
    # two panes share one row; from three on, two rows, the top one holding the
    # odd pane out. An office left from an older version with more than six
    # still gets two rows, just wider ones.
    for m in $(( n <= 2 ? n : (n + 1) / 2 )) $(( n <= 2 ? 0 : n / 2 )); do
      (( m )) || continue
      (( rh = n <= 2 ? H : (y ? H - y : (H - 1) / 2) ))
      cells=(); x=0
      for (( c = 0; c < m; c++ )); do
        (( cw = c == m - 1 ? W - x : (W - (m - 1)) / m ))
        cells+=("${cw}x${rh},${x},${y},${ids[k]#%}"); (( ++k ))
        (( x += cw + 1 ))
      done
      (( m == 1 )) && rows+=("${cells[1]}") || rows+=("${W}x${rh},0,${y}{${(j:,:)cells}}")
      (( y += rh + 1 ))
    done
    (( n <= 2 )) && body="${W}x${H},0,0{${(j:,:)cells}}" || body="${W}x${H},0,0[${(j:,:)rows}]"
    # tmux refuses a layout whose checksum does not match: its own 16-bit
    # rotate-and-add over every character (layout_checksum in layout-custom.c).
    for (( i = 1; i <= $#body; i++ )); do
      printf -v ch '%d' "'${body[i]}"
      (( csum = ((csum >> 1) + ((csum & 1) << 15) + ch) & 0xffff ))
    done
    tmux select-layout -t "${ids[1]}" "$(printf '%04x' $csum),$body" 2>/dev/null
  fi
  _office_number "$s"
}

# --- the editor pane ---------------------------------------------------------
# Shipped, not assumed. This used to call a function that happened to exist on
# the author's machine, which meant the editor pane died with "command not
# found" for everybody else.
#
# $OFFICE_EDITOR, else $EDITOR, else the first of micro / nano / vi that is
# installed. micro first because it is the one you can drive with no manual:
# Ctrl-S saves, Ctrl-Q quits, arrows and the mouse behave.
_office_editor() {
  local e
  for e in $OFFICE_EDITOR $EDITOR micro nano vi; do
    # ${e%% *}, not ${${(z)e}[1]}: a nested substitution that produced ONE word
    # is a scalar, so [1] took the first CHARACTER. `EDITOR=micro` asked for `m`,
    # missed, and fell through to nano — which on macOS is a symlink to pico, no
    # colours, no mouse. `${e%% *}` keeps the point of it ("code -w" -> code).
    [[ -n $e ]] && command -v ${e%% *} >/dev/null && { print -r -- "$e"; return }
  done
  print -r -- vi
}

# fuzzy-pick a file and open it. Files you have changed come first: it is nearly
# always one of them. Returns non-zero when you cancel, which is what lets the
# editor pane loop until you actually want out.

# Where the shell pane is standing right now, or this shell's own directory when
# there is no office and no shell pane.
_office_shell_dir() {
  local s d
  s=$(_office_here)
  d=$(tmux list-panes -t "=$s" -F '#{@office_kind}|#{pane_current_path}' 2>/dev/null \
      | awk -F'|' '$1=="SHELL" {print $2; exit}')
  [[ -n $d && -d $d ]] && print -r -- "$d" || print -r -- "$PWD"
}

# When the shell pane moves, tell the editor. zsh fires chpwd on every `cd`, and
# office.zsh is already sourced in that pane, so the shell can announce it
# instead of the editor polling for it. The nudge is Ctrl-R, which is the
# editor's own reload key, and it is only sent when fzf is actually in the
# foreground there: pressing it into an open file would type into your file.
_office_editor_sync() {
  local s p
  [[ -n $TMUX ]] || return 0
  # Decided here, not at load: a pane sources this file before office has
  # finished labelling it, so asking at startup always said "not the shell".
  # And it has to be -t $TMUX_PANE: a bare `display -p` reports the ACTIVE pane,
  # which is whichever one you are looking at, never the one asking.
  [[ $(tmux display -p -t "$TMUX_PANE" '#{@office_kind}' 2>/dev/null) == SHELL ]] || return 0
  s=$(_office_here)
  local tty
  # NB: #{pane_current_command} says "zsh" here, because fzf is a child of the
  # loop rather than the pane's own process. Ask the pane's terminal instead.
  read -r p tty <<< "$(tmux list-panes -t "=$s" -F '#{pane_id} #{pane_tty} #{@office_kind}' 2>/dev/null \
      | awk '$3=="EDITOR" {print $1, $2; exit}')"
  [[ -n $p && -n $tty ]] || return 0
  # `-o comm=` is a bare name on macOS and a full path on some Linuxes, so match
  # the tail: an exact 'fzf' silently killed the nudge wherever it printed a path.
  ps -t "${tty#/dev/}" -o comm= 2>/dev/null | grep -qE '(^|/)fzf$' || return 0
  tmux send-keys -t "$p" C-r 2>/dev/null
  return 0
}

# Every interactive zsh inside tmux gets the hook; the function itself decides
# whether this pane is the office's shell. It costs one tmux query per `cd`.
if [[ -n $TMUX && -o interactive ]]; then
  autoload -Uz add-zsh-hook 2>/dev/null && add-zsh-hook chpwd _office_editor_sync
fi

# What the FILE EDITOR pane runs. Leaving the list (Esc, or quitting the editor
# twice) turns the pane into a shell and SAYS so: a border still reading FILE
# EDITOR over a bare prompt reads like a broken window. Ctrl-Space q closes it,
# Ctrl-Space n opens a new editor.
_office_editor_loop() {
  while _office_pick_file; do :; done
  # -t $TMUX_PANE, never a bare `set -p`: that writes to whichever pane you are
  # LOOKING at, which is how a CLAUDE pane got relabelled instead of this one.
  _office_label "$TMUX_PANE" "$(_office_strip_title "$PWD")" SHELL
  print -P "\n  %F{yellow}the file list is closed — this pane is a shell now.%f"
  exec zsh
}
# The pane sources the package itself, and does not hope the rc file did it.
# `zsh -ic _office_editor_loop` alone is a pane that dies the instant it opens for
# anybody whose ~/.zshrc does not happen to source office.zsh — a login shell that
# is not zsh, a ZDOTDIR that moved, an rc file that only loads office for login
# shells. And it dies SILENTLY: tmux closes a pane whose command exits, so the
# office simply comes up with the file list missing and nothing says why. It
# looked like the editor was never wired up.
#
# -i is still there, so your own rc runs and your own $EDITOR is found;
# re-sourcing is idempotent, which office() already relies on. Quoted, because
# the string is run by tmux's sh and the path can contain spaces.
_OFFICE_EDITOR_CMD="zsh -ic 'source \"$_OFFICE_HOME/office.zsh\"; _office_editor_loop'"

_office_pick_file() {                  # [dir]
  local target=${1:-} where
  if [[ -z $target || -d $target ]]; then
    # Follow the SHELL pane. tmux tracks a pane's working directory live, so
    # `cd` over there and the next time this list opens you are browsing that
    # directory. The list reopens every time you close a file, which is the
    # natural moment to resync and costs nothing.
    where=${target:-$(_office_shell_dir)}
    [[ -d $where ]] || where=$PWD
    # Plain, sorted, relative: a file list you can read like a tree, where
    # typing a folder name narrows to it. Paths are relative to the directory in
    # the prompt, so the list stays readable no matter how deep you are.
    # height 100 so a zoomed pane is actually full of files.
    #
    # It follows the shell LIVE. `focus` fires whenever the highlighted line
    # changes, so moving the cursor is enough to notice a `cd` next door, and
    # `transform` only emits a reload when the directory actually differs.
    # $seen holds the last directory it drew, because fzf bindings are separate
    # processes with nowhere else to keep it.
    local cwd=$_OFFICE_HOME/bin/office-cwd sess seen
    sess=$(_office_here)
    seen=$(mktemp) && print -rn -- "$where" > $seen
    local list='fd --type f --hidden --follow --exclude .git --exclude node_modules --strip-cwd-prefix 2>/dev/null || find . -type f -not -path "*/.git/*" | sed "s|^\./||"'
    # NB: {} stands alone in the preview. fzf single-quotes the substitution, so
    # "$dir/{}" becomes "$dir/'file'" and the quote splits it into two arguments.
    target=$( cd "$where" && eval "$list" | sort \
      | fzf --prompt="${where:t}/ > " --height=100% --reverse \
            --header="$where" \
            --preview "d=\$($cwd $sess); cd \"\${d:-$where}\" 2>/dev/null; bat --style=numbers --color=always --line-range :300 {} 2>/dev/null || cat {}" \
            --preview-window=right:55%:wrap \
            --bind "focus:transform:d=\$($cwd $sess); [ -z \"\$d\" ] || [ \"\$d\" = \"\$(cat $seen)\" ] || { printf %s \"\$d\" > $seen; printf 'reload(cd %s && $list | sort)+change-prompt(%s/ > )+change-header(%s)' \"\$d\" \"\${d##*/}\" \"\$d\"; }" \
            --bind "ctrl-r:transform:d=\$($cwd $sess); [ -n \"\$d\" ] && { printf %s \"\$d\" > $seen; printf 'reload(cd %s && $list | sort)+change-prompt(%s/ > )+change-header(%s)' \"\$d\" \"\${d##*/}\" \"\$d\"; }" ) || { rm -f $seen; return 1 }
    where=$(<$seen); rm -f $seen
    [[ -n $target ]] || return 1
    target="$where/$target"
  fi
  [[ -n $target ]] || return 1
  local -a ed; ed=(${(z)$(_office_editor)})
  # Put the keys where you need them: in the editor, while the file is open.
  # Nobody remembers how to get back out of an editor they use twice a week.
  if [[ ${ed[1]:t} == micro ]]; then
    # softwrap, because a pane is narrower than a file: prose and long lines
    # would otherwise run off the right edge and be read by scrolling sideways.
    # scrollbar, so a long file shows how long it is. Both are micro defaults-off.
    $ed -statusline true -softwrap true -scrollbar true \
        -statusformatr "^S save   ^Q back to the file list   ^Z undo   ^F find" \
        "$target"
  else
    $ed "$target"
  fi
}


# tmux numbers panes by their position in the LAYOUT TREE, and join-pane leaves
# that tree in an order the eye does not agree with: you get 4=EDITOR, 6=SHELL.
# Swapping cannot fix it (a swap moves the geometry too), and rebuilding the tree
# means breaking every pane out and back. So the border shows OUR number, taken
# straight from the geometry: along the top row, then along the row below.
# The key strip, written into a tmux option rather than polled by the status bar
# with #(). A polled job is always one interval behind the thing it describes.
# This is pushed, from the one function that already runs after every change.
#
# Five keys and nothing else: n adds a pane (or brings a parked one back — they
# are on the same list), x parks, q closes, z zooms, Shift-arrows move. Dim,
# except two things that want your eye: the prefix while it is HELD, and zoom
# while the window IS zoomed (every other pane is hidden then, so the way back
# has to say so itself). The parked count is there because a parked pane is the
# only kind you can lose: it is running, and nothing on screen shows it.
_OFFICE_BAR_OPEN='#[fg=#4e505a]'
_OFFICE_BAR_SHUT='#[fg=#9a9ca6]'
_OFFICE_BAR_BACK='#[fg=#f6f5f1]'
_OFFICE_BAR_SEP='#[fg=#3a3c44]'
_office_bar() {                        # <session>
  local out parked d="${_OFFICE_BAR_SEP} · #[default]${_OFFICE_BAR_OPEN}"
  parked=$(_office_parked "$1" | wc -l | tr -d ' ')
  out="#{?client_prefix,${_OFFICE_BAR_SHUT},${_OFFICE_BAR_OPEN}}^Space#[default] ${_OFFICE_BAR_SEP}│#[default] ${_OFFICE_BAR_OPEN}n new"
  (( parked )) && out+=" ${_OFFICE_BAR_SHUT}($parked parked)#[default]${_OFFICE_BAR_OPEN}"
  out+="${d}x park${d}q close${_OFFICE_BAR_SEP} · #[default]#{?window_zoomed_flag,${_OFFICE_BAR_BACK}z unzoom,${_OFFICE_BAR_OPEN}z zoom}#[default]"
  # Zoom is a FORMAT and not a pushed tone: ^Space z is plain tmux and fires
  # without office, so only tmux can answer it on every redraw. It needs the
  # theme's `#{E:` — through `#{@office_bar}` it comes out LITERAL (tmux 3.7b).
  out+="${_OFFICE_BAR_SEP} │ #[default]${_OFFICE_BAR_OPEN}⇧ ← ↑ ↓ →  move#{?#{>=:#{version},3.7}, · drag a title to reorder,}#[default]"
  # NB: no "=" prefix here. set-option takes a plain session name and rejects
  # the exact-match form that every other tmux command accepts.
  tmux set -t "$1" @office_bar "$out" 2>/dev/null
}

_office_number() {                     # <session>
  local r n=0
  for r in ${(f)"$(tmux list-panes -t "=$1" -F '#{pane_left}|#{pane_top}|#{pane_id}' 2>/dev/null \
        | sort -t'|' -k2,2n -k1,1n)"}; do
    tmux set -p -t "${${(s:|:)r}[3]}" @office_num $(( ++n )) 2>/dev/null
  done
  _office_bar "$1"                     # the strip is only ever as fresh as this
}

# --- staying current, without surprising you ---------------------------------
# `office on` fetches in the BACKGROUND and says nothing except when you are
# behind. It never pulls on its own: this package is the thing drawing your
# window, and changing it under you mid-session is how a morning gets ruined.
# `office update` is the deliberate act, and it refuses on a dirty tree rather
# than merging over your edits.
#
# It is also the ONLY thing here that touches the network, which is why it has an
# off switch. `OFFICE_UPDATE_CHECK=0` and the office never opens a socket at all
# — for an offline machine, a network that makes a `git fetch` hang, or simply
# not wanting a tool you start twenty times a day to talk to GitHub every time.
: ${OFFICE_UPDATE_CHECK:=1}
_office_update_check() {
  (( OFFICE_UPDATE_CHECK )) || return 0
  [[ -d $_OFFICE_HOME/.git ]] || return 0
  ( git -C "$_OFFICE_HOME" fetch --quiet origin 2>/dev/null & ) >/dev/null 2>&1
  local behind
  behind=$(git -C "$_OFFICE_HOME" rev-list --count HEAD..@{upstream} 2>/dev/null)
  (( behind > 0 )) && print -P "%F{240}  agent-office is $behind commit(s) behind — 'office update'%f"
  return 0
}

# --- taking out the bins, so nobody has to remember to ---------------------
# A parked pane is the only kind you can forget: it is invisible, and a parked
# session still holds half a gigabyte. Anything parked and untouched this
# long is reaped when you next walk in.
#
# Panes you can SEE are never touched automatically. Those are a decision, and a
# script that closes an agent you were coming back to is worse than a full disk.
: ${OFFICE_REAP_HOURS:=12}
_office_reap() {
  tmux has-session -t "=$_OFFICE_STASH" 2>/dev/null || return 0
  local now=$(date +%s) line w act pid n=0 mb=0
  for line in ${(f)"$(tmux list-windows -t "=$_OFFICE_STASH" -F '#{window_id}|#{window_activity}' 2>/dev/null)"}; do
    w=${${(s:|:)line}[1]}; act=${${(s:|:)line}[2]}
    [[ $act == <-> ]] || continue
    (( (now - act) / 3600 >= OFFICE_REAP_HOURS )) || continue
    pid=$(tmux list-panes -t "$w" -F '#{pane_pid}' 2>/dev/null | head -1)
    [[ -n $pid ]] && mb=$(( mb + $(_office_pane_mb "$pid") ))
    tmux kill-window -t "$w" 2>/dev/null && (( ++n ))
  done
  (( $(tmux list-windows -t "=$_OFFICE_STASH" 2>/dev/null | wc -l) )) \
    || tmux kill-session -t "=$_OFFICE_STASH" 2>/dev/null
  (( n )) && print -P "%F{240}  tidied up: $n pane(s) parked over ${OFFICE_REAP_HOURS}h closed, ~${mb}MB back%f"
  # Offices left running from another day are only reported, never closed for
  # you: one of them might be four agents mid-task. `office sweep` is one word.
  local -a stale; stale=(${(f)"$(_office_stale ${OFFICE_REAP_HOURS})"})
  if (( $#stale )); then
    local smb=0 l; for l in $stale; do smb=$(( smb + ${${(z)l}[3]} )); done
    print -P "%F{yellow}  ${#stale} office(s) left open from earlier, holding ~${smb}MB%f — close them with 'office sweep'"
  fi
  return 0
}

# --- walking into somebody else's checkout -----------------------------------
# `git checkout develop` in the main checkout answers "already used by worktree
# at .../desk-5" and stops. That is git being right: a branch lives in exactly
# ONE working tree, and an agent session is sat in that one. The old advice was
# to wait, or to close the agent, and both are wrong — what you wanted was never
# the branch, it was what is IN it, and that is already on disk one directory
# away.
#
# So `office cd` checks nothing out. It walks you to the worktree that already
# has the branch. Nothing collides because nothing is claimed: the agent keeps
# its worktree, you keep yours, and you can read, build and run in its tree
# while it works. The editor pane follows the SHELL pane's directory by itself
# (bin/office-cwd), so the file list arrives with you — which is the whole
# reason this is a verb here and not a line in somebody's .zshrc.
#
# ponytail: `git worktree list --porcelain` is the registry. Nothing is cached
# and no state is written: a worktree that was reaped a minute ago must not be
# on this list, and asking git costs one fork.
# `wt`, never `path`: in zsh `path` is the array tied to $PATH, so assigning a
# worktree to it inside the loop replaces the shell's PATH with one directory
# and everything after it is gone. Declaring it `local` does not save you.
_office_worktrees() {                  # -> "<branch>\t<path>", in git's own order
  local line wt
  git -C "$(_office_root "$PWD")" worktree list --porcelain 2>/dev/null | while IFS= read -r line; do
    case $line in
      (worktree\ *) wt=${line#worktree } ;;
      (branch\ *)   printf '%s\t%s\n' "${${line#branch }#refs/heads/}" "$wt" ;;
      (detached)    printf '%s\t%s\n' '(detached)' "$wt" ;;
    esac
  done
}

# --- making sure nothing outlives the office ---------------------------------
# tmux kill-server sends SIGHUP to each pane's children, which is enough for
# anything still attached to a terminal and not enough for anything that
# detached itself. Agent CLIs in particular leave host and daemon processes
# behind that no pane is the parent of, and they hold hundreds of megabytes.
#
# So: take the process GROUP of every pane before killing the server, then make
# sure those groups are gone afterwards. Our own group is excluded, because
# `office off` is nearly always run from inside the office it is closing.
_office_pane_groups() {                # [session]  (all offices when omitted)
  local p g
  local -a t; [[ -n $1 ]] && t=(-t "=$1") || t=(-a)
  for p in ${(f)"$(tmux list-panes $t -F '#{pane_pid}' 2>/dev/null)"}; do
    g=$(ps -o pgid= -p "$p" 2>/dev/null | tr -d ' ')
    [[ -n $g && $g != $_OFFICE_OWN_PGID && $g -gt 1 ]] && print -r -- "$g"
  done | sort -u
}

_office_kill_groups() {                # <pgid>...
  local g
  for g in "$@"; do kill -TERM -$g 2>/dev/null; done
  sleep 0.4
  for g in "$@"; do kill -KILL -$g 2>/dev/null; done
}

# Offices you walked away from. An office survives a closed terminal on purpose,
# which is the whole point of `office break`, and the cost is that one left over
# from days ago is still holding four agents and their memory with no window
# anywhere.
#
# Scoped to tmux sessions this tool created, and nothing else. An earlier
# version matched process NAMES, which swept in the desktop app, the tmux server
# and every unrelated shell: a broom that wide is a footgun, not a feature.
_office_stale() {                      # [hours] -> "<session> <idle-min> <MB>"
  local hours=${1:-12} now=$(date +%s) line name attached act mb pid
  # Digits or the default. `office sweep -y` used to hand the FLAG in here, and
  # zsh arithmetic reads "-y" as minus-an-unset-variable: threshold 0, every
  # detached office "stale", and the -y meant no question was asked before the
  # kill. One guard here covers every caller, OFFICE_REAP_HOURS included.
  [[ $hours == <-> ]] || hours=12
  for line in ${(f)"$(tmux list-sessions -F '#{session_name}|#{session_attached}|#{session_activity}' 2>/dev/null)"}; do
    name=${${(s:|:)line}[1]}; attached=${${(s:|:)line}[2]}; act=${${(s:|:)line}[3]}
    [[ $name == _* ]] && continue                  # the pane stash is not an office
    # ...and neither is a tmux session something else created. Every office has
    # @office_bar written on it by _office_number; a session without it is not
    # ours to report, and above all not ours for `office sweep` to kill.
    # A PLAIN name, no "=": show-options answers the exact-match form with
    # empty, silently — the same trap set-option documents in _office_bar — and
    # the name is straight out of list-sessions, so it is already exact.
    [[ -n $(tmux show -t "$name" -qv @office_bar 2>/dev/null) ]] || continue
    (( attached )) && continue                     # you are looking at this one
    [[ $act == <-> ]] || continue
    (( (now - act) / 3600 >= hours )) || continue
    mb=0
    for pid in ${(f)"$(tmux list-panes -t "=$name" -F '#{pane_pid}' 2>/dev/null)"}; do
      mb=$(( mb + $(_office_pane_mb "$pid") ))
    done
    print -r -- "$name $(( (now - act) / 60 )) $mb"
  done
}

# --- going home is a reset -----------------------------------------------------
# `office off` deliberately keeps NOTHING: not the pane sizes, not what you
# parked, not the shape you dragged things into. It is the fix-it-all, so
# whatever you broke fiddling with the layout, off and on gives you the default
# office back every time, with no saved state anywhere to explain it.
#
# `office break` is the other half: it detaches without stopping anything, and
# because the tmux server stays alive your layout survives exactly as it was.
# Two verbs, two behaviours, no configuration.

# label a pane. Borders carry IDENTITY only: which pane this is, what it is, and
# what it is doing. The keys all live on the status strip, in one place, because
# printing "^Space w" on a session was advertising a global action as if it
# belonged to that pane, and printing every key on every border is clutter.
#
# label a pane. An agent overwrites #{pane_title} with whatever it is doing,
# so the ROLE lives in a user option the app cannot touch, and the border shows
# both: "CLAUDE . rename the auth module".
#
# @office_kind is the STABLE identity (NEW, SHELL, EDITOR, CLAUDE) that
# everything matches on — the visible label carries a repo and a branch and moves.
# CLAUDE means "an agent desk" now, whichever OFFICE_AGENTS entry is actually
# running there — office-attn only ever needed "is this a session", never
# which one. NEW is the pane still asking what it should be.
_office_label() {                      # <pane> <label> [kind]
  # '#' is stripped: the label is rendered through tmux's format engine, where
  # #(...) runs a shell command. A branch name or an `office task` description
  # containing one would otherwise be executed every time the border redraws.
  tmux set -p -t "$1" @office_label "${2//\#/}" 2>/dev/null
  tmux set -p -t "$1" @office_kind "${3:-$2}" 2>/dev/null
}

# say something to the operator. A keybinding runs with no terminal attached, so
# a bare `print` becomes stray run-shell output — and tmux shows THAT by forcing
# the active pane into view-mode, where every office key stops working.
# The status line is the only safe place to talk from.
_office_say() {
  tmux display-message " office: $1" 2>/dev/null || print -u2 "office: $1"
}

# Is a session ALREADY running in this checkout? Two agents in one is the single
# way this layout bites: same branch, same files, each committing over the other,
# and nothing on screen says so — both borders read CLAUDE and both are right.
# It is a legitimate thing to want (one reading while one writes), so the callers
# say it and none of them block.
#
# :A on both sides, because tmux answers with the path symlinks resolve to while
# the caller's is whatever git printed. /tmp alone is enough to make two names
# for one directory look like two, and then this never fires in the exact case
# it exists for.
_office_desk_in() {                    # <session> <dir>
  local p want=${2:A}
  for p in ${(f)"$(tmux list-panes -t "=$1" -F "#{@office_kind}|#{pane_current_path}" 2>/dev/null)"}; do
    [[ $p == CLAUDE\|* && ${${p#CLAUDE|}:A} == $want ]] && return 0
  done
  return 1
}
_OFFICE_SHARED_MSG="2nd session in the same checkout — 'office new <name>' gives one its own worktree"

# the visible pane of a given kind, if it is on screen at all
_office_pane_of_kind() {               # <session> <kind>
  tmux list-panes -t "=$1" -F '#{pane_id}|#{@office_kind}' 2>/dev/null \
    | awk -F'|' -v k="$2" '$2==k {print $1; exit}'
}

# --- hiding a pane without killing it ----------------------------------------
# tmux cannot hide a pane, but it can move one to a window nobody is looking at.
# The stash is its own SESSION so no extra window ever shows up in the status
# bar, and the process inside keeps running the whole time.
_OFFICE_STASH=_stash
_office_stash_ensure() {
  tmux has-session -t "=$_OFFICE_STASH" 2>/dev/null \
    || tmux new-session -d -s "$_OFFICE_STASH" -n idle 'exec sleep 2147483647'
}

_office_hide() {                       # <pane-id>
  local kind sess
  kind=$(tmux display -p -t "$1" '#{@office_kind}' 2>/dev/null)
  sess=$(tmux display -p -t "$1" '#{session_name}' 2>/dev/null)
  [[ -n $kind && -n $sess ]] || return 1
  # the question pane has nothing running to keep: parking it would only put a
  # "back: NEW" on the list
  [[ $kind == NEW ]] && { _office_say "nothing to park here — pick what this pane is first"; return 0 }
  # again here, and not only in office(): the Ctrl-Space x binding hands a pane
  # id and no path, so _office_here can name a different office (or none). The
  # pane knows its own session; use that.
  _office_unzoom "$sess"
  _office_stash_ensure
  # Parking the LAST pane would take the window with it, and the session with the
  # window: the office would simply be gone. So the office gets a fresh "what
  # next?" pane first, and the parked one is on its list.
  (( $(tmux list-panes -t "=$sess" 2>/dev/null | wc -l) > 1 )) \
    || _office_label "$(tmux split-window -d -t "$1" -P -F '#{pane_id}' "$_OFFICE_WAIT_CMD")" NEW NEW
  # WHOSE it is travels on the pane, because the stash is ONE session for the
  # whole server: keyed by kind alone, parking the file editor in one office and
  # bringing one back in another handed you the first office's pane.
  tmux set -p -t "$1" @office_parked_from "$sess" 2>/dev/null
  tmux break-pane -d -s "$1" -t "=$_OFFICE_STASH:" -n "${(L)kind}-${(L)sess}-${1#\%}" 2>/dev/null || return 1
  # the placeholder only exists because a session needs one window; once a real
  # pane is parked it is just noise in `office doctor`.
  (( $(tmux list-windows -t "=$_OFFICE_STASH" 2>/dev/null | wc -l) > 1 )) \
    && tmux kill-window -t "=$_OFFICE_STASH:idle" 2>/dev/null
  _office_grid "$sess"
  return 0
}

# This office's parked panes: "<stash-window-id><TAB><label>", oldest first.
# A pane parked by an older office.zsh has no @office_parked_from, so its window
# NAME (<kind>-<office>-<n>) still answers for it — without that, a pane parked
# the day before an update would be running and unreachable.
_office_parked() {                     # <session>
  tmux list-panes -s -t "=$_OFFICE_STASH" -F $'#{window_id}\t#{@office_parked_from}\t#{window_name}\t#{@office_label}' 2>/dev/null \
    | awk -F'\t' -v s="$1" -v ls="${(L)1}" '$2==s || ($2=="" && $3 ~ "-" ls "-[0-9]+$") {print $1 "\t" ($4=="" ? $3 : $4)}'
}

# Bring a parked pane back into the grid. It takes the "what next?" pane's cell
# when there is one, and a new cell otherwise.
_office_unhide() {                     # <session> <stash-window-id>
  local s=$1 p ph
  p=$(tmux list-panes -t "$2" -F '#{pane_id}' 2>/dev/null | head -1)
  [[ -n $p ]] || return 1
  ph=$(_office_pane_of_kind "$s" NEW)
  if [[ -z $ph ]] && (( $(tmux list-panes -t "=$s" 2>/dev/null | wc -l) >= _OFFICE_MAX_PANES )); then
    _office_say "the office is full ($_OFFICE_MAX_PANES panes) — close one with Ctrl-Space q or park one with x"
    return 0
  fi
  tmux join-pane -d -s "$p" -t "$(_office_last_pane "$s")" 2>/dev/null || return 1
  tmux set -p -t "$p" -u @office_parked_from 2>/dev/null
  [[ -n $ph ]] && tmux kill-pane -t "$ph" 2>/dev/null
  _office_grid "$s"
  tmux select-pane -t "$p" 2>/dev/null
  return 0
}

# the pane tmux lists LAST, which is the one a new pane is split from: the new
# one lands after it in tmux's order, so the grid adds it at the end.
_office_last_pane() { tmux list-panes -t "=$1" -F '#{pane_id}' 2>/dev/null | tail -1 }

# a short label for the bottom strip: repo name + current branch
_office_strip_title() {
  local b; b=$(git -C "$1" branch --show-current 2>/dev/null)
  print -r -- "SHELL · $(basename "$1")${b:+ · $b}"
}

# The office. ONE window, and it starts as ONE pane that asks what it should be:
# an agent (every OFFICE_AGENTS entry), a shell, or the file editor. Ctrl-Space n
# asks the same question for every pane after it, up to the grid's six.
#
# The question is tmux's own menu, and a menu needs a CLIENT to draw on. The
# office is built before you are attached to it, and `office on` can spend
# seconds on OFFICE_ON_CMD in between, so the first pane waits for a client
# rather than asking into nothing.
_OFFICE_WAIT_CMD="zsh -ic 'source \"$_OFFICE_HOME/office.zsh\"; _office_wait'"
_office_wait() {
  local i
  for (( i = 0; i < 600; i++ )); do     # a minute, at most, for you to walk in
    [[ $(tmux display -p -t "$TMUX_PANE" '#{session_attached}' 2>/dev/null) == 0 ]] || break
    sleep 0.1
  done
  while :; do
    clear
    print -P "\n  %F{240}what should this pane be?  any key shows the list again.%f"
    # Attached is not yet READY: on a slow machine (Ubuntu CI, measured) the
    # first display-menu right after the attach is refused with "no current
    # client", and the pane then sat waiting for a key with no list on screen.
    # So a refused menu is asked again, for up to two seconds.
    if [[ $(tmux display -p -t "$TMUX_PANE" '#{session_attached}' 2>/dev/null) != 0 ]]; then
      for (( i = 0; i < 20; i++ )); do office new && break; sleep 0.1; done
    fi
    read -rsk 1 || break
  done
}

_office_open() {                       # <repo-path>
  local dir=$1 s
  s=$(_office_sessfor "$dir")
  if ! tmux has-session -t "=$s" 2>/dev/null; then
    local main
    main=$(tmux new-session -d -s "$s" -c "$dir" -n office -P -F '#{pane_id}' "$_OFFICE_WAIT_CMD")
    # what makes the name above answerable later: which checkout this office is
    # rooted in, on the session itself.
    tmux set -t "$s" @office_root "${dir:A}" 2>/dev/null
    [[ $s == $(_office_sessname "$dir") ]] \
      || _office_say "another repo already holds that name -- this office is \"$s\"."
    _office_label "$main" NEW NEW
  fi
  cd "$dir"
  _office_number "$s"                  # also writes the key strip
  _office_watch_setup                  # ...and what the borders need to watch
  _office_reap                         # walking in takes the bins out
  _office_update_check
  _office_always_on_up                 # restore whatever `office off` stopped
  _office_reload_conf                  # the server may be older than the config
  _office_attach "$s"
}

# Has this worktree's branch LANDED — is every change on it already in the branch
# the repo merges into?
#
# The obvious test is whether its commits are ancestors of the default branch,
# and that test is wrong for any repo that squash-merges: a squash rewrites the
# branch's commits into one new commit, so the originals stay un-ancestored
# forever and every branch that ever landed still reads as unfinished. Merging
# the branch in memory and asking whether the RESULT differs from the default
# branch's tree answers the content question instead, which is what "finished"
# actually means.
#
# Fail-safe in the do-not-reuse direction: an unreadable ref, a conflict, or a
# git older than 2.38 (no `merge-tree --write-tree`) all say no, and the caller
# makes a new worktree instead of walking an agent into someone else's branch.
_office_wt_landed() {                  # <root> <worktree>
  local root=$1 d=$2 base branch merged tree
  branch=$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null) || return 1
  [[ -n $branch && $branch != HEAD ]] || return 1          # detached: not ours to judge
  base=$(git -C "$root" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)
  base=${base#*/}
  [[ -n $base ]] || base=$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null)
  [[ -n $base && $base != $branch ]] || return 1
  [[ $(git -C "$root" rev-list --count "$base..$branch" 2>/dev/null) == 0 ]] && return 0
  merged=$(git -C "$root" merge-tree --write-tree "$base" "$branch" 2>/dev/null | head -1) || return 1
  tree=$(git -C "$root" rev-parse "$base^{tree}" 2>/dev/null)
  [[ -n $merged && $merged == $tree ]]
}

# Which worktree an unnamed extra desk gets. The first one nobody is sitting in
# and nobody left anything in, else a fresh desk-N. Reuse first, because a key
# you press several times a day that creates a directory every time is a key
# that fills your repo with them.
#
# "Left anything in" is the same two questions a session-worktree sweep asks
# before deleting one — uncommitted files, then unlanded commits — so a worktree
# this reuses is exactly a worktree such a sweep would consider finished. Same
# predicate, opposite verb.
_office_free_wt() {                    # <root> <session> -> a directory, or nothing
  local root=$1 s=$2 wt="$1/$OFFICE_WORKTREE_DIR" d n=2
  git -C "$root" rev-parse --git-dir >/dev/null 2>&1 || return 1
  for d in $wt/*(N/); do
    _office_desk_in "$s" "$d" && continue
    [[ -n $(git -C "$d" status --porcelain 2>/dev/null) ]] && continue
    _office_wt_landed "$root" "$d" || continue
    print -r -- "$d"; return 0
  done
  # A free NUMBER is a free directory and a free branch. Removing a worktree
  # leaves its branch behind — `git worktree remove` does, and so does anything
  # else that cleans checkouts up — so desk-2's directory can be gone while the
  # branch is not. Then `worktree add -b desk-2` fails on the branch, this
  # returns nothing, and the caller falls back to the shared checkout: the exact
  # collision the whole command exists to prevent, arriving quietly.
  while [[ -e $wt/desk-$n ]] || git -C "$root" show-ref --quiet --verify "refs/heads/desk-$n"; do
    (( ++n ))
  done
  git -C "$root" worktree add -b "desk-$n" "$wt/desk-$n" >/dev/null 2>&1 || return 1
  print -r -- "$wt/desk-$n"
}

# Agent <n> (1-based OFFICE_AGENTS index): its label, or its command. Split
# the way a shell would ((z)), so a command word that was itself quoted in the
# array survives instead of being torn apart by the re-join below.
_office_agent_label() { local -a w; w=(${(z)OFFICE_AGENTS[$1]}); print -r -- "${w[1]}" }
_office_agent_cmd()   { local -a w; w=(${(z)OFFICE_AGENTS[$1]}); print -r -- "${(j: :)w[2,-1]}" }

# "<label|index>" -> its 1-based OFFICE_AGENTS index, or fail (1). Numeric
# first, then a case-insensitive label match, because a label is what a person
# types — the menu's own items always pass the index instead.
_office_agent_index() {                # <label-or-index> -> index, or fail
  local q=$1 i
  [[ $q == <-> ]] && (( q >= 1 && q <= ${#OFFICE_AGENTS} )) && { print -r -- "$q"; return 0 }
  for (( i = 1; i <= ${#OFFICE_AGENTS}; i++ )); do
    [[ ${(L)$(_office_agent_label $i)} == ${(L)q} ]] && { print -r -- "$i"; return 0 }
  done
  return 1
}

# Is there room for one more pane? A "what next?" pane always has room: the
# answer takes its cell.
_office_room() {                       # <session>
  [[ -n $(_office_pane_of_kind "$1" NEW) ]] && return 0
  (( $(tmux list-panes -t "=$1" 2>/dev/null | wc -l) < _OFFICE_MAX_PANES )) && return 0
  _office_say "the office is full ($_OFFICE_MAX_PANES panes) — Ctrl-Space q closes one, x parks one"
  return 1
}

# The one question: what the next pane is. Parked panes first, because they are
# already running and a parked pane nobody can find is why they are on this list
# at all; then every OFFICE_AGENTS entry; then a shell and the file editor. Every
# item re-enters `office new` with the answer, which is also the typed door.
#
# One file editor at a time: it follows the SHELL pane's directory, and two lists
# following the same shell are one list twice.
#
# Needs a CLIENT to draw on: a run-shell binding has none of its own (it is
# detached), which is why `bind n` hands one down as OFFICE_CLIENT. From inside
# a pane there already is one, and -c is left off.
_office_menu() {                       # <session>
  local s=$1 dir=$PWD i n=${#OFFICE_AGENTS} line
  local client=$OFFICE_CLIENT; unset OFFICE_CLIENT
  # ponytail: $dir goes into a tmux command unescaped — fine for an ordinary
  # path; a quote or a '#' in one would need escaping, if that ever bites.
  local run="run-shell -b \"OFFICE_SESSION='$s' OFFICE_PANE_PATH='$dir' zsh -ic 'office new"
  local -a items menu_c keys=(a b c d f g h i j k)   # s and e are taken below
  for line in ${(f)"$(_office_parked "$s")"}; do
    (( $#items / 3 < $#keys )) || break
    items+=("back: ${${line#*$'\t'}//\#/}" "${keys[$#items / 3 + 1]}" "$run --back ${line%%$'\t'*}'\"")
  done
  (( $#items )) && items+=("")          # one empty name is a separator
  (( n > 9 )) && n=9                    # the keys are the digits 1-9, no more
  for (( i = 1; i <= n; i++ )); do
    items+=("$(_office_agent_label $i | tr -d '#')" "$i" "$run --agent $i'\"")
  done
  items+=("" "shell" s "$run --shell'\"")
  [[ -n $(_office_pane_of_kind "$s" EDITOR) ]] || items+=("file editor" e "$run --edit'\"")
  [[ -n $client ]] && menu_c=(-c "$client")
  # -M so a click picks an item: without it tmux lets only a menu opened FROM a
  # mouse binding take the mouse. -M is tmux 3.5+, and 3.4 refuses the whole
  # command, so it gets the menu without the click rather than no menu at all.
  tmux display-menu -M $menu_c -T "#[align=centre] open " -x P -y P $items 2>/dev/null \
    || tmux display-menu $menu_c -T "#[align=centre] open " -x P -y P $items 2>/dev/null
}

_office_new() {                        # [--agent <a> [wt] | --shell | --edit | --back <window>]
  local s root wt dir label agent=1
  s=$(_office_here)
  tmux has-session -t "=$s" 2>/dev/null \
    || { _office_say "no office open — run 'office on' first"; return 0 }
  # Asked before anything is created, so a full office never leaves a worktree
  # behind for a pane that never opened.
  _office_room "$s" || return 0
  case $1 in
    '')      _office_menu "$s"; return ;;   # its status: _office_wait retries a refused menu
    --back)  _office_unhide "$s" "$2" || _office_say "that pane is not parked any more"; return 0 ;;
    --shell) _office_add_pane "$(_office_strip_title "$PWD")" 'exec zsh' "$PWD" SHELL; return ;;
    --edit)  _office_add_pane "FILE EDITOR" "$_OFFICE_EDITOR_CMD" "$PWD" EDITOR; return ;;
    --agent) agent=$(_office_agent_index "$2") || { print -u2 "office: no such agent '$2'"; return 1 }
             shift 2 ;;
  esac
  # The office's own checkout, never the directory this was pressed in: pressed
  # from an agent that sits in desk-3, the repo root of $PWD is desk-3 itself, and
  # a worktree made from there nests inside it.
  root=$(tmux show -t "$s" -qv @office_root 2>/dev/null)
  [[ -d $root ]] || root=$(_office_root "$PWD")
  wt="$root/$OFFICE_WORKTREE_DIR"

  if [[ -z $1 ]]; then
    # The first agent works in the checkout itself. Every one after it gets its
    # OWN worktree — a free one, or a new desk-N — so two agents never commit
    # over each other on one branch. Nothing git could give (not a repo, no
    # commit yet) still opens the agent: a pick that does nothing reads as broken.
    _office_desk_in "$s" "$root" && dir=$(_office_free_wt "$root" "$s")
    [[ -n $dir ]] || dir=$root
  elif [[ -d $wt/$1 ]]; then dir="$wt/$1"
  elif [[ -d $1 ]];    then dir=$(cd "$1" && pwd)
  else
    # No worktree by that name yet, so make one. Creating is additive: a branch
    # and a directory, nothing touched in the checkout you are standing in.
    git -C "$root" rev-parse --git-dir >/dev/null 2>&1 \
      || { print -u2 "office: no directory '$1', and $root is not a git repo"; return 1 }
    dir="$wt/$1"
    # -b first (a new branch off HEAD, the usual case); without it when the
    # branch already exists and you are picking it up in a fresh checkout.
    git -C "$root" worktree add -b "$1" "$dir" 2>/dev/null \
      || git -C "$root" worktree add "$dir" "$1" \
      || { print -u2 "office: could not create worktree '$1'"; return 1 }
    print -r -- "office: new worktree $dir"
  fi
  label=$(_office_agent_label "$agent")
  [[ $dir == "$root" ]] || label+=" · ${dir:t}"
  _office_add_pane "$label" "$(_office_agent_cmd "$agent")$_OFFICE_DESK_END" "$dir" CLAUDE
}

# Add a pane running <command>: into the "what next?" pane's cell when there is
# one, else a new cell at the end of the grid.
_office_add_pane() {                   # <label> <command> [dir] [kind]
  local s newp dir=${3:-$PWD} kind=${4:-$1} shared=0
  s=$(_office_here)
  tmux has-session -t "=$s" 2>/dev/null \
    || { _office_say "no office open — run 'office on' first"; return 0 }
  _office_room "$s" || return 0
  # Two agents in one checkout is the single way this bites: same branch, same
  # files, and both borders right. Legitimate (one reads while one writes), so it
  # is said, never blocked. Asked BEFORE the pane exists, or it counts itself.
  [[ $kind == CLAUDE ]] && _office_desk_in "$s" "$dir" && shared=1
  newp=$(_office_pane_of_kind "$s" NEW)
  if [[ -n $newp ]]; then
    tmux respawn-pane -k -t "$newp" -c "$dir" "$2" 2>/dev/null || return 1
  else
    newp=$(tmux split-window -t "$(_office_last_pane "$s")" -c "$dir" -P -F '#{pane_id}' "$2") || return 1
  fi
  _office_label "$newp" "$1" "$kind"
  _office_grid "$s"
  tmux select-pane -t "$newp" 2>/dev/null
  (( shared )) && _office_say "$_OFFICE_SHARED_MSG"
  # not inside tmux and not on a terminal (a run-shell keybinding) — nothing to attach to
  [[ -n $TMUX || ! -t 1 ]] || _office_attach "$s"
}

# Drag a pane's title onto another pane and it moves there; the panes in between
# shift one place to make room. tmux has no "move to cell", so it is a row of
# neighbour swaps, and the grid is rebuilt around the new order. The mouse half
# lives in office.tmux.conf.
_office_move() {                       # <pane> <onto-pane>
  local s from to i
  local -a ids
  s=$(tmux display -p -t "$1" '#{session_name}' 2>/dev/null)
  [[ -n $s && $s == $(tmux display -p -t "$2" '#{session_name}' 2>/dev/null) ]] || return 1
  ids=(${(f)"$(tmux list-panes -t "=$s" -F '#{pane_id}' 2>/dev/null)"})
  from=${ids[(ie)$1]}; to=${ids[(ie)$2]}
  (( from <= $#ids && to <= $#ids && from != to )) || return 0
  if (( from < to )); then
    for (( i = from; i < to; i++ )); do tmux swap-pane -d -s "$1" -t "${ids[i+1]}" 2>/dev/null; done
  else
    for (( i = from; i > to; i-- )); do tmux swap-pane -d -s "$1" -t "${ids[i-1]}" 2>/dev/null; done
  fi
  _office_grid "$s"
  tmux select-pane -t "$1" 2>/dev/null
  return 0
}

# every tmux session that is an office (i.e. all of them)
# every tmux session that is an office. The pane stash (`_stash`) is not one:
# it holds panes you collapsed, and it must never show up as somewhere to go.
_office_sessions() { tmux list-sessions -F '#{session_name}' 2>/dev/null | grep -v '^_' }

# --- what is actually costing you memory -------------------------------------
# RSS of a pane, summed over its whole process group (the shell AND the agent
# / node / server running under it). ponytail: RSS double-counts shared pages,
# so treat it as a ranking signal, not an exact number.
_office_pane_mb() {
  local pgid; pgid=$(ps -o pgid= -p "$1" 2>/dev/null | tr -d ' ')
  [[ -n $pgid ]] || { print 0; return }
  ps -eo pgid=,rss= 2>/dev/null | awk -v g="$pgid" '$1==g {s+=$2} END {printf "%d", s/1024}'
}

# one line per PANE. Field 1 is the pane id (%7), so `clean` can act on a pick.
#   %4   CLAUDE 2                  670MB   idle  12m   myproj
_office_inventory() {
  local now=$(date +%s) id sess title pid act mb idle
  tmux list-panes -a -F '#{pane_id}|#{session_name}|#{@office_label}|#{pane_pid}|#{window_activity}|#{pane_current_command}' 2>/dev/null \
  | while IFS='|' read -r id sess title pid act cmd; do
      mb=$(_office_pane_mb "$pid")
      idle=$(( (now - act) / 60 ))
      [[ -z $title ]] && title=$cmd
      printf '%-5s %-26s %6sMB   idle %4sm   %s\n' "$id" "$title" "$mb" "$idle" "$sess"
    done
}

# total MB across every office
_office_total_mb() { _office_inventory | awk '{for(i=1;i<=NF;i++) if ($i ~ /MB$/) {gsub(/MB/,"",$i); s+=$i}} END {printf "%d", s+0}' }

# --- your own start and stop commands ----------------------------------------
# `office off` kills every process group its panes own, which covers everything
# you started inside the office. It cannot cover what you started OUTSIDE it: a
# launchd service, a systemd unit, a docker stack, a tunnel. Those survive any
# amount of killing inside tmux, and on macOS they are usually the reason the
# machine will not sleep.
#
# There is no way for this package to guess what yours is, so you name it once
# and `office on` / `office off` become the switch for it too:
#
#   OFFICE_ON_CMD          run when you walk in
#   OFFICE_OFF_CMD         run when you go home
#   OFFICE_RUNNING_CHECK   exits 0 when it is already up, so `office on` does
#                          not start it twice
#   OFFICE_ON_ALWAYS       set it when OFFICE_ON_CMD is safe to run twice
#
# (The older OFFICE_ALWAYS_ON_START / _STOP / _CHECK names still work.)
#
# OFFICE_ON_ALWAYS exists because "already up" and "already current" are not the
# same sentence. A start command that also UPDATES — pulls, rewrites its units,
# restarts its own processes on the new code — is exactly the one the running
# check skips, so walking in gives you back this morning's build and nothing on
# screen says why. Set OFFICE_ON_ALWAYS=1 and the check no longer gates the
# start; it keeps answering the other two questions honestly.
#
# It is a separate switch and not `OFFICE_RUNNING_CHECK=false` on purpose. That
# check is a STATUS predicate, read in three places: this skip, the up/down line
# in `office status`, and `office off`, which runs OFFICE_OFF_CMD only when the
# check says something is up. Lie to it and going home silently stops stopping
# your stack — the Mac never sleeps, and the one word that was supposed to end
# the day is the one that quietly does not.
#
# Empty by default, because the honest default is to touch nothing you did not
# ask for. Set them and going home really does mean everything is off.
: ${OFFICE_ON_CMD:=${OFFICE_ALWAYS_ON_START:-}}                # run by `office on`
: ${OFFICE_OFF_CMD:=${OFFICE_ALWAYS_ON_STOP:-}}                # run by `office off`
: ${OFFICE_RUNNING_CHECK:=${OFFICE_ALWAYS_ON_CHECK:-false}}    # exits 0 when it is up
: ${OFFICE_ON_ALWAYS:=0}                                       # 1 = run ON_CMD every walk-in
_office_always_on() { eval "$OFFICE_RUNNING_CHECK"; }

# walking in restores whatever going home stopped — `office on` is the exact
# undo of `office off`. Skip it with `office solo` (tabs only, nothing started).
_office_always_on_up() {
  [[ -n $OFFICE_SOLO || -z $OFFICE_ON_CMD ]] && return 0
  # same trap as _office_editor: a one-word OFFICE_ON_CMD would be tested one
  # character at a time and the stack would never come up.
  command -v ${OFFICE_ON_CMD%% *} >/dev/null || return 0
  (( OFFICE_ON_ALWAYS )) || { _office_always_on && return 0 }
  print -P "%F{green}==> $OFFICE_ON_CMD%f"
  eval "$OFFICE_ON_CMD"
}

_office_help() {
  local g="%F{green}" d="%F{240}" r="%f"
  print -P "${g}office${r} — your whole workday, in one command.${d}  (short alias: o)${r}\n"

  print -P "${g}YOUR DAY${r} ${d}— these three are 95%% of it${r}"
  print -P "  ${g}office on${r}      Start working. Opens your office, and starts whatever"
  print -P "                 ${d}else you told it to start (OFFICE_ON_CMD).${r}"
  print -P "                 ${d}Use it every morning, and to come back from a break.${r}"
  print -P "  ${g}office break${r}   Stepping away. Nothing stops — agents keep running,"
  print -P "                 ${d}the Mac stays busy. Lunch, a meeting, closing the laptop lid.${r}"
  print -P "  ${g}office off${r}     Done for the day. Quits the office you are IN and every"
  print -P "                 ${d}agent in it. Other offices keep running.${r}"
  print -P "  ${g}office off --all${r} ${d}...and every other office too${OFFICE_OFF_CMD:+, and runs '$OFFICE_OFF_CMD'}. Both ask first.${r}\n"

  print -P "${g}WHAT YOU GET${r} ${d}— ONE window, and it starts as one pane that asks what it is${r}"
  print -P "    ${d}┌──────────────┬──────────────┬──────────────┐${r}"
  print -P "    ${d}│${r} ${g}1 CLAUDE${r}     ${d}│${r} ${g}3 CODEX${r}      ${d}│${r} ${g}5 SHELL${r}      ${d}│${r}"
  print -P "    ${d}├──────────────┼──────────────┤              │${r}"
  print -P "    ${d}│${r} ${g}2 CLAUDE${r}     ${d}│${r} ${g}4 FILE EDITOR${r}${d}│${r}              ${d}│${r}"
  print -P "    ${d}└──────────────┴──────────────┴──────────────┘${r}"
  print -P "  ${d}Every pane is what you picked: any OFFICE_AGENTS entry, a shell, or the${r}"
  print -P "  ${d}file editor. Three across and two down at most, six in all, kept even.${r}\n"

  print -P "${g}THE KEYS${r} ${d}— that is all of them${r}"
  print -P "  ${g}Ctrl-Space n${r}   one more pane. A list: parked panes, your agents, shell, editor"
  print -P "  ${g}Ctrl-Space x${r}   park this pane. It keeps running; ^Space n brings it back"
  print -P "  ${g}Ctrl-Space q${r}   close this pane"
  print -P "  ${g}Ctrl-Space z${r}   zoom this pane, and back"
  print -P "  ${g}Shift-←↑↓→${r}     move between panes"
  print -P "  ${g}drag a title${r}   onto another pane to move it there; the rest shift along"
  print -P "  ${d}Drag across text to copy it, or double-click a word — it is on the${r}"
  print -P "  ${d}clipboard when you let go. A border shows what that pane is, and 'your${r}"
  print -P "  ${d}turn' when an agent is waiting on you.\n${r}"

  print -P "${g}RUNNING SEVERAL AGENTS${r} ${d}— the whole point of this setup${r}"
  print -P "  ${g}agents${r}         The first one works in the checkout. Every one after it gets"
  print -P "                 ${d}its OWN git worktree — a free one, or a new desk-N — so they${r}"
  print -P "                 ${d}never commit over each other. OFFICE_AGENTS lists what is offered.${r}"
  print -P "  ${g}your turn${r}      Which one is waiting on you: a desk that has not moved for"
  print -P "                 ${d}${OFFICE_ATTN_SECS}s says so on its own border, and how long it has been${r}"
  print -P "                 ${d}waiting. Nothing to press. OFFICE_ATTN_SECS changes the wait.${r}"
  print -P "  ${g}412k${r}           How full that desk's context window is, on its border. Quiet"
  print -P "                 ${d}below $(( OFFICE_CTX_WARN / 1000 ))k, then the accent, then the alarm at $(( OFFICE_CTX_ALARM / 1000 ))k.${r}"
  print -P "                 ${d}OFFICE_CTX_WARN / _ALARM move the marks. Claude Code only.${r}"
  print -P "  ${g}office new --agent A [X]${r}  Agent A (label or number), in worktree X if named."
  print -P "  ${g}office task X${r}  A new session already working on X."
  print -P "  ${g}office desk${r}    One more session in THIS checkout, when you mean it."
  print -P "  ${g}office show${r}    Pick a parked pane and bring it back.\n"

  print -P "${g}KEEPING IT LEAN${r} ${d}— nothing ever dies on its own, so check now and then${r}"
  print -P "  ${g}office doctor${r}  What is running and what it costs in RAM. Read-only,"
  print -P "                 ${d}nothing is touched. Every agent pane is 400-700MB.${r}"
  print -P "  ${g}office clean${r}   Added too many? This is the way out. Pick panes to close:"
  print -P "                 ${d}Tab marks, Enter closes them, Esc closes nothing. Heaviest${r}"
  print -P "                 ${d}first, and collapsed panes are in the list too — they still${r}"
  print -P "                 ${d}cost RAM. One at a time: Ctrl-Space q on the pane itself.${r}"
  print -P "  ${g}office list${r}    Same as doctor."
  print -P "  ${g}office update${r}  Pull the newest agent-office. Never happens on its own:"
  print -P "                 ${d}'office on' only tells you when you are behind.${r}"
  print -P "  ${g}office install${r} Wire office into zsh and tmux again. Safe to re-run;"
  print -P "                 ${d}starts nothing. Same as ./install.sh, and --theme works.${r}"
  print -P "  ${g}office cd${r} ${d}[x]${r}  Walk the shell into another worktree — yours, or the one an"
  print -P "                 ${d}agent is working in. Checks nothing out, so nothing collides;${r}"
  print -P "                 ${d}the file editor follows. 'office cd develop' when git says that${r}"
  print -P "                 ${d}branch is already used by another worktree.${r}"
  print -P "  ${g}office sweep${r}   Offices you walked away from, still holding memory with no"
  print -P "                 ${d}window anywhere. Lists them, asks, then closes them and${r}"
  print -P "                 ${d}everything inside. 'office sweep 2' for a 2-hour threshold.${r}"
  print -P "                 ${d}That is Claude Code's 'conversation moved to the background'${r}"
  print -P "                 ${d}screen, not the list. This restarts it. Nothing else is touched.${r}\n"

  print -P "${g}A DIFFERENT REPO${r}"
  print -P "  ${g}office <name>${r}  Open any repo by name — fuzzy, so 'proj' finds 'my-project'."
  print -P "  ${g}office pick${r}    Not sure of the name? Pick from every repo in $CODE_ROOT."
  print -P "  ${g}office solo${r}    Like 'on', but starts nothing — just the tabs."
  print -P "                 ${d}Use when you want the panes without the rest.${r}\n"

  print -P "${g}EDITING FILES${r} ${d}— no vim knowledge required${r}"
  print -P "  ${g}file editor${r}    ^Space n, then e. Fuzzy-pick a file and edit it in place;"
  print -P "                 ${d}the list follows the shell pane. Ctrl-S save · Ctrl-Q back to${r}"
  print -P "                 ${d}the list · Ctrl-Z undo · Ctrl-F find · the mouse works.\n${r}"

  print -P "${g}IF YOU FORGET ONE THING, REMEMBER THIS${r}"
  print -P "  Closing the window never kills anything. ${g}office on${r} always brings"
  print -P "  you back exactly where you were, panes and all. Only ${g}office off${r} ends things."
}

# ------------------------------------------------------------------ office ---
# office <on|break|off|repo|pick|new|solo|doctor|clean> — your whole workspace, one word.
office() {
  local cmd=${1:-help} dir
  _office_pane_cwd                     # a key press stands where its pane stood
  # A shell keeps running the copy of this file it sourced when it started. That
  # is how `office off; office on` right after an update gives you back the OLD
  # office, in an old shape, with the fix you just installed nowhere in it —
  # and nothing on screen says why. If the file on disk has moved since, load it
  # and run the new one. Re-sourcing is idempotent: every setting is a default,
  # and add-zsh-hook does not double up.
  local _m; _m=$(zstat +mtime "$_OFFICE_HOME/office.zsh" 2>/dev/null)
  if [[ -n $_m && -n $_OFFICE_MTIME && $_m != $_OFFICE_MTIME ]]; then
    source "$_OFFICE_HOME/office.zsh" && { office "$@"; return }
  fi
  # ONE place, because every verb that moves a pane comes through here — typed,
  # aliased, or fired by a key binding's run-shell. See _office_unzoom for what
  # a zoomed window does to the geometry underneath. The exemptions are the
  # verbs that only print, detach, or close the whole thing: those never read a
  # column, so taking the operator's zoom away for them would be rude.
  [[ $cmd == (help|-h|--help|list|ls|status|doctor|check|install|update|upgrade|sweep|stale|break|pause|bg|away|brb|off|out|end|quit|stop|home|cd|goto|hop) ]] \
    || _office_unzoom "$(_office_here)"
  case $cmd in
    on|up|in|back|work|resume)
      dir=$(_office_find "$OFFICE_DEFAULT") || true
      [[ -z $dir ]] && dir=$(_office_fallback "$OFFICE_DEFAULT")
      _office_open "$dir" ;;
    pick)
      # eza is nobody's install requirement, so it gets a fallback: without one
      # the preview pane was simply blank on the documented five-package setup.
      dir=$(_office_repos | sed "s|^$HOME/|~/|" \
            | fzf --prompt='repo> ' --height=60% --reverse \
                  --preview "d=\$(echo {} | sed \"s|^~|$HOME|\"); { eza -la --icons --git --color=always \"\$d\" || ls -la \"\$d\"; } 2>/dev/null | head -40") || return
      _office_open "${dir/#\~/$HOME}" ;;
    new|+)
      shift; _office_new "$@" ;;
    solo)
      OFFICE_SOLO=1 office on ;;
    desk|claude)
      _office_add_pane "$OFFICE_SESSION_LABEL" "$OFFICE_SESSION_CMD$_OFFICE_DESK_END" "$(_office_root "$PWD")" CLAUDE ;;
    task|do|go)
      shift
      (( $# )) || { print -u2 "usage: office task <what you want done>"; return 1 }
      _office_add_pane "$OFFICE_SESSION_LABEL · $*" "$OFFICE_SESSION_CMD ${(q)*}$_OFFICE_DESK_END" "$(_office_root "$PWD")" CLAUDE ;;
    install)
      # The verb every tool here shares (zyx, murmurflow): set it up, start nothing.
      # Here that is install.sh, which is idempotent. Without this arm the word fell
      # through to the fuzzy repo match below and looked for a repo called "install".
      zsh "$_OFFICE_HOME/install.sh" "${@[2,-1]}" ;;
    update|upgrade)
      [[ -d $_OFFICE_HOME/.git ]] || { print -u2 "office: $_OFFICE_HOME is not a git checkout"; return 1 }
      if [[ -n $(git -C "$_OFFICE_HOME" status --porcelain) ]]; then
        print -u2 "office: $_OFFICE_HOME has local changes. Commit or stash them first."
        git -C "$_OFFICE_HOME" status --short | sed 's/^/  /'
        return 1
      fi
      git -C "$_OFFICE_HOME" pull --ff-only || return 1
      _office_reload_conf
      # ...and here too, not only on the way in. A pull that moves the package
      # (or the first one that brings a watcher at all) leaves a running server
      # holding no @office_home, which turns the border readout off silently —
      # "I updated and the new thing does nothing", with nothing to see.
      _office_watch_setup
      print "updated. The next 'office' command in any shell runs the new version;"
      print "panes already open keep what they are running until you close them." ;;
    renumber|grid)
      _office_grid "$(_office_here)" ;;
    sweep|stale)
      # `office sweep [hours]` — offices nobody has looked at in that long, and
      # everything inside them. Default 12h, so yesterday's office is fair game
      # and the one you detached at lunch is not.
      local -a stale; stale=(${(f)"$(_office_stale ${2:-12})"})
      if (( ! $#stale )); then print "office: nothing stale. Every office is either open or recent."; return; fi
      local mb=0 line
      for line in $stale; do mb=$(( mb + ${${(z)line}[3]} )); done
      print -P "%F{yellow}${#stale} office(s) detached and idle, holding ~${mb}MB:%f"
      for line in $stale; do
        print "  ${${(z)line}[1]}  idle $(( ${${(z)line}[2]} / 60 ))h  ${${(z)line}[3]}MB"
      done
      if [[ $2 == (-y|--yes) || $3 == (-y|--yes) ]]; then :
      else
        print -n "close them, and everything running inside? [y/N] "; read -q _ans 2>/dev/null; print
        [[ $_ans == y ]] || { unset _ans; print "left alone."; return }
        unset _ans
      fi
      local -a groups
      for line in $stale; do
        groups+=(${(f)"$(_office_pane_groups "${${(z)line}[1]}")"})
        tmux kill-session -t "=${${(z)line}[1]}" 2>/dev/null
      done
      (( $#groups )) && _office_kill_groups ${(u)groups}
      print -P "swept ${#stale} office(s). %F{green}~${mb}MB%f back." ;;
    cd|goto|hop)
      # With a word: the first worktree whose branch or path contains it, so
      # `office cd develop` is the answer to the checkout git just refused.
      # Without one: pick from the list. Either way it only ever cds.
      local -a rows; rows=(${(f)"$(_office_worktrees)"})
      if (( ! $#rows )); then
        print -u2 "office: not in a git repo, so there is no worktree to hop to."; return 1
      fi
      local pick
      if [[ -n $2 ]]; then
        pick=${rows[(r)*${2}*]}
        if [[ -z $pick ]]; then
          print -u2 "office: no worktree matching '$2'. There is:"
          printf '  %s\n' ${rows//$'\t'/'  '} >&2
          return 1
        fi
      else
        pick=$(printf '%s\n' $rows | fzf --prompt='hop to> ' --height=40% --reverse \
                 --header='the branch, and the checkout it lives in. Nothing is checked out.') || return
      fi
      local dir=${pick##*$'\t'}
      # A worktree git still lists can be gone from disk — an agent session
      # reaped mid-sentence leaves exactly that. cd would fail with the shell's
      # own error, which says nothing about what happened.
      [[ -d $dir ]] || { print -u2 "office: '$dir' is not there any more (stale worktree)."; return 1 }
      cd "$dir" || return 1
      print -P "%F{green}${pick%%$'\t'*}%f  $dir"
      [[ -n $TMUX && $(tmux display -p '#{@office_kind}' 2>/dev/null) == SHELL ]] \
        || print -P "%F{240}  (the file editor follows the SHELL pane — run this there and it comes along)%f" ;;
    hide|park)
      _office_hide "${2:-$(tmux display -p '#{pane_id}')}" ;;
    show|restore|unpark)
      local s pick; s=$(_office_here)
      pick=$(_office_parked "$s" | fzf --prompt='bring back> ' --height=40% --reverse \
               --delimiter=$'\t' --with-nth=2) || return
      _office_unhide "$s" "${pick%%$'\t'*}" ;;
    break|pause|bg|away|brb)
      local -a live; live=(${(f)"$(_office_sessions)"})
      (( $#live )) || { print "office: nothing running"; return }
      print -P "%F{green}on a break%f — ${#live} office(s) and everything in them keep running:"
      printf '  %s\n' $live
      print -P "  back in with %F{green}office on%f"
      [[ -n $TMUX ]] && tmux detach-client ;;

    off|out|end|quit|stop|home)
      # `off` CLOSES THE OFFICE YOU ARE IN. It used to close every office on the
      # machine, and that blast radius is not something a one-word command gets
      # to have: an agent told to tidy up ran it and took four unrelated agent
      # sessions with it, mid-task, in windows nobody had asked about. The
      # confirmation was no help — it is one keypress, and `-y` skips it.
      #
      # `office off --all` is the old behaviour, spelled out. Same work, same
      # prompt; you just have to say the word that means "everything".
      local a all=0 yes=0
      for a in "${@[2,-1]}"; do
        case $a in (-a|--all) all=1 ;; (-y|--yes) yes=1 ;; esac
      done
      local -a live always; live=(${(f)"$(_office_sessions)"})
      _office_always_on && always=1
      if (( ! $#live )) && (( ! $#always )); then print "office: nothing running"; return; fi

      local -a doomed
      if (( all )); then
        doomed=($live)
      else
        # `_office_here` asks tmux which session this pane is in, and outside
        # tmux it answers with the office for the repo you are standing in.
        # Either way it can name one that is not running, so it is checked and
        # not trusted: "the office you are in", asked from outside every office,
        # is a question with no answer, and guessing one is how this broke.
        local here=$(_office_here)
        if [[ -z $here ]] || (( ! ${live[(I)$here]} )); then
          print -u2 "office: you are not in an office, so there is nothing here to close."
          print -u2 "        'office list' shows what is running, 'office off --all' closes all of it."
          return 1
        fi
        doomed=($here)
      fi

      # The always-on stack belongs to the MACHINE and not to one office, so it
      # only stops when the last office does. Stopping it while three offices
      # keep working is how the Mac goes to sleep on top of them.
      local last=0
      (( $#doomed >= $#live )) && last=1

      print "going home means:"
      (( $#doomed )) && { print "  quit ${#doomed} office(s) + every agent in them:"; printf '    %s\n' $doomed }
      (( $#doomed )) && print "  reset the layout to default: sizes, parked panes, all of it"
      (( $#doomed )) && print "  kill every process any pane started, detached ones included"
      (( $#doomed )) && (( ! last )) && print "  leave $(( $#live - $#doomed )) other office(s) running, untouched"
      (( $#always )) && (( last )) && print "  run '$OFFICE_OFF_CMD' (stops the always-on stack, Mac can sleep)"
      if (( ! yes )); then
        print -n "go home? [y/N] "; read -q _ans 2>/dev/null; print
        [[ $_ans == y ]] || { unset _ans; print "still here."; return }
        unset _ans
      fi
      (( $#always )) && (( last )) && { print -P "%F{green}==> $OFFICE_OFF_CMD%f"; eval "$OFFICE_OFF_CMD" }
      # Each office's process groups are taken BEFORE its session goes: a pane
      # that is gone has no pid left to ask. The whole-server kill is for --all
      # only — that is what also takes the stash session and anything else this
      # tool never named.
      local -a groups; local sess
      for sess in $doomed; do
        groups+=(${(f)"$(_office_pane_groups "$sess")"})
        (( all )) || tmux kill-session -t "=$sess" 2>/dev/null
      done
      (( all )) && tmux kill-server 2>/dev/null
      (( $#groups )) && _office_kill_groups ${(u)groups}
      print -P "%F{green}office closed. see you tomorrow.%f" ;;

    list|ls|status|doctor|check)
      local -a inv; inv=(${(f)"$(_office_inventory)"})
      if (( $#inv )); then
        print -P "%F{green}PANE  WHAT                          MEMORY   IDLE      OFFICE%f"
        printf '%s\n' $inv
        local total idle_mb
        total=$(_office_total_mb)
        idle_mb=$(printf '%s\n' $inv | awk '{m=0; for(i=1;i<=NF;i++){ if ($i ~ /MB$/){gsub(/MB/,"",$i); m=$i} if ($i ~ /^[0-9]+m$/){gsub(/m/,"",$i); if ($i+0>=60) s+=m} }} END {printf "%d", s+0}')
        print -P "\n${#inv} pane(s), %F{green}${total}MB%f total"
        (( idle_mb > 0 )) && print -P "  %F{yellow}${idle_mb}MB sitting in panes idle over an hour%f — reclaim with 'office clean'"
      else
        print "no offices running"
      fi
      _office_always_on \
        && print -P "always-on: %F{green}up%f (stop with '$OFFICE_OFF_CMD')" \
        || print "always-on: down (start with 'office on')" ;;

    clean|gc|tidy)
      local -a inv sel; inv=(${(f)"$(_office_inventory)"})
      (( $#inv )) || { print "office: nothing running"; return }
      # `office clean --idle [hours]` skips the picker and closes anything that
      # has sat untouched that long. For a cron or a shell alias, not for you.
      if [[ $2 == (--idle|-i) ]]; then
        local hrs=${3:-2} n=0 freed=0 line f
        for line in $inv; do
          [[ $line == *"idle "*[0-9]m* ]] || continue
          local mins=${${${line##*idle }%%m*}// /}
          (( mins >= hrs * 60 )) || continue
          for f in ${(z)line}; do [[ $f == *MB ]] && freed=$(( freed + ${f%MB} )); done
          tmux kill-pane -t "${line%% *}" 2>/dev/null && (( ++n ))
        done
        print "closed $n pane(s) idle over ${hrs}h, ~${freed}MB reclaimed."
        return
      fi
      # Heaviest first means sorting on the MB column, which is not at a fixed
      # field (titles carry spaces) or a fixed offset (titles overflow their
      # width). Decorate with the number, sort, strip. The old `sort -t M -k1
      # -nr` parsed "%4 CLAUDE…" as the number 0 for every line and fell back to
      # reverse-alphabetical, which only LOOKED sorted.
      sel=(${(f)"$(printf '%s\n' $inv \
            | awk '{m=0; for(i=1;i<=NF;i++) if ($i ~ /MB$/){m=$i; sub(/MB$/,"",m); break} printf "%09d\t%s\n", m, $0}' \
            | sort -rn | cut -f2- | fzf -m --height=60% --reverse \
            --header='Tab marks a pane to close, Enter closes them. Esc = close nothing.' \
            --prompt='close> ')"}) || return
      (( $#sel )) || { print "nothing closed."; return }
      local line target freed=0 f
      for line in $sel; do
        target=${line%% *}
        for f in ${(z)line}; do [[ $f == *MB ]] && freed=$(( freed + ${f%MB} )); done
        tmux kill-pane -t "$target" 2>/dev/null
      done
      print -P "closed ${#sel} pane(s), %F{green}~${freed}MB%f reclaimed."
      tmux list-sessions >/dev/null 2>&1 || print "  (that was the last one — no offices left)" ;;
    chat|talk|shell|sh|term|edit|editor|files|sessions|desks|layout|fix|repair)
      # retired verbs, answered rather than fuzzy-matched as a repo name
      print -u2 "office: '$cmd' is gone — Ctrl-Space n picks what any pane is (or: office new --shell / --edit)"
      return 1 ;;
    help|-h|--help)
      _office_help ;;
    *)
      dir=$(_office_find "$cmd")
      [[ -n $dir ]] || { print -u2 "office: no repo matching '$cmd' (try: office pick)"; return 1 }
      _office_open "$dir" ;;
  esac
}

alias o=office
alias ao=office
