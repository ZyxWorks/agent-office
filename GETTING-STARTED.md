# Getting started

For anyone moving from a desktop AI app to the terminal for the first time.
No prior tmux, no prior vim, nothing assumed. Twenty minutes, once.

> Landed here first? The [product page](https://zyxworks.github.io/agent-office/)
> is the two-minute version, the [README](README.md) is the reference, and
> [the rest of our tools](https://zyxworks.com/open-source) are one page over.

---

## 1. Why the terminal at all

In the desktop app you have one conversation, and it asks permission to touch
your files. In the terminal your agent *is* in your project: it reads the repo,
edits files, runs the tests, and you watch it happen.

It also opens a door the desktop app does not: once you are here, the agents you
build are terminal programs too, and you can talk to them in the same window
without building a web app first.

The catch is that one agent working alone leaves you waiting. So people run
three or four at once, on different parts of the work. That is the moment the
terminal stops being pleasant: four windows, no idea which one needs you, and a
layout you rebuild every morning.

`agent-office` is one command that puts them all on one screen, in the same
place, every time.

---

## 2. The words you need

Five, and then you know the vocabulary.

| word | what it is |
|---|---|
| **terminal** | the app you type commands into. iTerm2, Terminal.app, Windows Terminal |
| **shell** | the program *inside* it that runs your commands. Usually zsh or bash |
| **tmux** | splits one terminal window into several, and keeps them running when you close it |
| **pane** | one of those splits. A pane is just a shell, with something running in it |
| **session** | in this tool, one running agent, living in one pane |

The important one is **tmux**. Without it, closing your terminal kills whatever
was running. With it, everything survives: you close the window, walk away,
come back, and your agents are still working. That is the whole reason it is
here.

---

## 3. Your first office

```sh
office on
```

```
  what should this pane be?  any key shows the list again.

    ›  CLAUDE
       shell
       file editor
```

One pane, asking. Press any key and pick from the list: your agent, a plain
shell, or the file editor. Pick your agent first, then press **Ctrl+Space,
then `n`** twice more and pick shell, then file editor:

```
┌──────────────┬──────────────┬──────────────┐
│ 1 CLAUDE     │ 2 SHELL      │ 3 FILE EDITOR│
│              │              │              │
│              │              │              │
└──────────────┴──────────────┴──────────────┘
```

Three panes. That is the whole tool.

**1. The agent.** Your agent, running in your project. Type here the same way
you type in the desktop app. Paste an image, drag a file in, ask it to change
something. This is where you spend your time, which is why it gets equal space
with everything else.

**2. The shell.** An ordinary command line, already in your project. For
`git status`, `npm test`, `ls`. You use it to *check* the agent's work: it says
it fixed the tests, so you run them.

**3. The file editor.** A file browser that follows the shell pane, so the two
work together: `cd` in the shell to aim, browse and open in the editor. For
reading what the agent did, or a quick manual fix.

Running an agent of your own and want to talk to it the same way? See
[the README](README.md#bringing-your-own-agent) when you get there — it is just
one more line, not a different kind of pane.

---

## 4. Moving around

**Click a pane with your mouse.** It works, and it is the honest answer for
your first day.

The keyboard version is **Shift and an arrow key**. Left, right, up, down,
exactly where you would expect. Only that. Do not learn more yet.

(One exception: while you have a **file open** in the editor, Shift+arrow
selects text, as it should. `Ctrl+Q` closes the file and you can move again, or
`Ctrl+Space` and an arrow leaves straight away. The file list itself moves
normally.)

One thing worth knowing early: **Ctrl+Space, then `z`** blows the current pane
up to fill the whole window, and again to put it back. When the agent is writing
a lot and the pane feels cramped, that is the key.

**To copy something out, drag across it.** Let go and it is on your clipboard,
in the shell and in the file editor both. No Cmd+C, no copy mode, nothing to
press after it.

**And if a pane stops taking what you type, click in it.** Scrolling back puts a
pane in tmux's copy mode, where the arrows move a cursor through history instead
of your cursor on the line. A click puts you back at the live prompt, and so
does Escape.

That second one is the pattern for everything that is not movement: **press
Ctrl+Space, let go, then press a letter.** It is two keystrokes rather than a
three-finger chord, and unlike a chord it works in every terminal on every
operating system with nothing to set up.

---

## 5. The editor, and how to get out of it

This is the part that catches everyone, including people who have used
terminals for years.

Press **Ctrl+Space, then `n`**, and pick **file editor** from the list. You get
a list of files with a search box. Type a few letters to filter, arrow up and
down, **Enter** to open one.

**It follows the shell pane.** Whatever directory the shell is standing in is
what the editor shows, listed the way a file tree reads. `cd src` in the shell,
and the editor is showing `src`. The directory is printed above the list.

To find something, just type part of its name or its folder: the list narrows as
you type. `Ctrl+Space z` zooms the pane so the list fills the screen.

Now you are inside a file, and here is the bit nobody remembers:

| key | |
|---|---|
| **Ctrl+S** | save |
| **Ctrl+Q** | close the file, back to the file list |
| **Ctrl+Z** | undo |
| **Ctrl+F** | find |
| **Esc** (at the file list) | leave the file list. The pane becomes an ordinary shell, and says so |

**The editor shows these keys along its bottom edge while a file is open**, so
you do not have to remember them. Look down.

The path out is always the same: `Ctrl+Q` gets you back to the list, `Esc`
leaves the list. To bring the editor back, **Ctrl+Space, then `n`**, and pick
**file editor** again — it is only offered while none is open, so it is always
right there in the menu when you need it.

**Nothing you do in here can lose the pane.** Leave the list and it says so, in
the pane, and the same `Ctrl+Space n` that opens every pane brings it back.

> **If your editor looks nothing like this** and shows no help at the bottom,
> your `$EDITOR` points somewhere else: vim, or macOS's `nano`, which is really
> `pico` — no colours, no mouse, no visible way out. `brew install micro` and
> `export OFFICE_EDITOR=micro` in your `.zshrc` gives you the pane above. If you
> chose vim on purpose, you already know how to quit.

---

## 6. Running more than one agent

**Ctrl+Space, then `n`** asks the same question again: pick your agent (or
another one, if you have more than one set up) and it takes the next cell in
the grid — up to six panes total, three across at most — and each one is a
separate conversation working on a separate thing.

Each one also gets **its own checkout** — a git worktree under
`.claude/worktrees/`, made for it if there is not a free one already. Without
that, two agents edit the same files on the same branch and commit over each
other, and nothing on screen tells you: both panes say CLAUDE and both are
right. Merge a worktree's branch when you are happy with it, the way you would
any branch.

This is the actual point of the tool. One agent refactoring while another writes
tests, and you moving between them.

When one is finished, **Ctrl+Space, then `q`** closes that pane. It asks first.

---

## 7. The three commands worth memorising

| | |
|---|---|
| `office on` | start work. Opens everything, exactly as you left it |
| `office break` | stepping away. Detaches, and **everything keeps running**, exactly as you left it |
| `office off` | done for the day. Closes the office you are **in**, and **resets its layout**. Asks first |
| `office off --all` | ...and every other office on the machine with it. Asks first |

**Closing your terminal window does not stop anything.** It is the same as
`office break`. Your agents keep working, and `office on` brings you back to
the same panes in the same places. Only `office off` actually ends things — and it
ends the office you are in, not the four others you left working. That is what
`--all` is for, and it is a word you have to type.

And `office off` is your escape hatch: it throws the layout away too, so if you
have dragged panes into a mess or something looks wrong, off and on gives you a
clean default office back. You cannot break it permanently.

That is the mental shift from a desktop app: the work is not tied to the window
you are looking at.

---

## 8. Every key, once you want them

Not for day one. Come back to this.

| | |
|---|---|
| `⇧←↑↓→` | move between panes |

And `Ctrl+Space`, then:

| | |
|---|---|
| `n` | one more pane: pick from the menu — parked panes, every agent, shell, file editor |
| `x` | park this pane: hidden, still running. `n`'s menu brings it back |
| `q` | close this pane for good. A menu opens: click **close it**, or press `c`. Enter, Escape or `k` keeps it |
| `z` | zoom this pane full screen, and back |

And the mouse, with no key at all:

| | |
|---|---|
| drag a pane's title onto another pane | it moves there, the rest shift along |
| drag across text | it is on the clipboard when you let go, nothing to press |
| double-click a word | the same, for one word |
| click in a pane that scrolled | back at the live prompt, typing again (Escape does it too) |

Each pane's top border shows its number and what it is, and the bar along the
bottom carries the keys, including how many panes are parked right now.

And the thing you actually wanted from several agents at once: a desk that has
stopped and is waiting on you says **your turn** on its own border, with how long
it has been waiting. You never have to read every pane to find the one that
finished. Nothing to press, and nothing to set up.

That number keeps counting all night, so a desk you left at midnight says
`your turn 8h12m` when you sit down, and not just `your turn`.

If Shift+arrow ever does not move you, you have a file open in the editor, where
it selects text instead. **Ctrl+Space then an arrow** always moves, from
anywhere, including from inside a file.

---

## 9. When something looks stuck

Nothing here ever needs a restart of anything.

| what you see | what to do |
|---|---|
| a pane is frozen and its keys do nothing | it is in scroll mode. Press `q` |
| git says a branch is "already used by worktree" | `office cd <branch>` — go to it instead of checking it out |
| the panes are in silly positions | they re-fit on the next pane you add, park, unpark or close |
| you closed something and cannot get it back | `Ctrl+Space n`, or `office show` |
| you have no idea what is running | `office doctor` |
| genuinely wedged | `office off`, then `office on`. Resets everything |

`office doctor` is worth running once now, just to see it. It lists every pane
and what it costs in memory. Agents are heavy, roughly half a gigabyte each,
which is the real reason to close ones you have finished with.

---

## 10. What to do next

1. `office on`
2. Ask the agent in pane 1 something small about your project. "What does this
   repo do?" is a fine start.
3. When it changes a file, look at it: `Ctrl+Space n`, pick **file editor**,
   find the file, read it, `Ctrl+Q`, `Esc`.
4. Run your tests in the shell pane.
5. `Ctrl+Space n`, and give the second agent something unrelated.

That is the loop. Everything else in the [README](README.md) is detail you can
pick up when you want it.
