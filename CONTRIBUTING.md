# Contributing

Pull requests are welcome. `main` is protected, so everything lands through
one, mine included.

Working on the tmux office (0.x)? Its rules and probes are in
[docs/legacy-tmux/CONTRIBUTING.md](docs/legacy-tmux/CONTRIBUTING.md). It gets
no new features.

## How to propose a change

1. Fork, branch off `main`.
2. Make the change, and **say how you verified it**. See below.
3. Open a PR against `main` describing what you saw before and after.

Small, obviously-correct fixes get merged quickly. Anything that adds a
command, a component or a config key is worth an issue first, so you do not
build something that turns out to be out of scope.

## What this project is

A small, opinionated distribution of an agent developer setup: herdr, the
Agent Office preset and meter, Firstmate, treehouse, the kunchenguid tools and
the agent integrations, plus an optional workstation profile. One private
config file, one `office` command. The [README](README.md) is the contract:
components, commands, config, what stays private, platforms.

**In scope:**

- installing each component through its own installer or package manager,
- composing one `~/.config/agent-office/config.toml` into each tool's native
  config,
- a tested, compatible set of component versions,
- the daily lifecycle: install, on, break, off, off --all, update,
  status/doctor, `fm` and `fm restart`,
- the meter plugin and the herdr preset, which live in this repo.

**Out of scope:**

- **Rewriting or vendoring a component.** herdr, Firstmate, treehouse and the
  kunchenguid tools are maintained upstream. A missing feature there is an
  upstream issue, not a patch or a wrapper here.
- **A second copy of what a component owns.** No pane manager next to herdr's,
  no worker scheduler next to Firstmate's, no worktree allocator next to
  treehouse's, no second fleet database.
- **A daemon.** Lifecycle commands run and exit. The meter is a herdr plugin
  that herdr starts and stops.
- **Anything personal.** See the rules below.

## The rules the code follows

- **One config file.** A setting a user needs goes in `config.toml`, with a
  default in the release. Settings that belong to a component stay in that
  component's own config; Agent Office passes `[herdr]` keys through and does
  not mirror the rest. An unknown Agent Office key is an error.
- **No business process in code.** How work is done is a file a person can
  edit: a preset, a template, a config. Code is for mechanisms: installing,
  composing, checking, starting and stopping.
- **Nothing private in the package.** No accounts, credentials, machine names,
  hosts, personal paths, private apps or Firstmate operational content, in
  code, defaults, examples or test fixtures. Examples use placeholders, never a
  real machine's output.
- **Stop only what you own.** A stop acts on resources this installation
  recorded as its own. Never `pkill` by name, never stop a herdr session the
  office did not create, never delete worktrees or prune a pool: ask Firstmate
  and treehouse.
- **Show, then act.** Anything that stops work, overwrites a file or changes a
  user's setup lists what it will do first and keeps a backup. Stops that end
  work ask to confirm.
- **No remote shell pipelines.** Never `curl | sh`. Install from a component's
  published installer or package manager at a reviewed version.
- **Config values are data.** Nothing read from `config.toml` is ever
  evaluated as shell code.
- **Report honestly.** "Unknown" is not "healthy". "Updated on disk" is not
  "active". A command that did not verify what it promised exits non-zero.
- **Docs say what exists.** A command or key that is not built yet is marked
  `planned` everywhere it appears. Never describe it as working.
- **Comments say why, not what.** The useful comments record a trap someone
  already fell into.

## Keeping it private

"Nothing private in the package" is checked, not hoped for. `bin/leak-scan` runs in CI on every push and PR, next to gitleaks:

- **Public rules**, readable by anyone: a home path (`/Users/<name>/`, `/home/<name>/`), an email address that is not a placeholder (`@example.com`, `.invalid`, a GitHub noreply address), a private key, a secrets file (`.env`, `*.pem`, `*.key`).
- **Commit emails.** Every new commit's author and committer must be a GitHub noreply address (`<id>+<login>@users.noreply.github.com`). Set it once in your clone: `git config user.email <id>+<login>@users.noreply.github.com`. Older commits are not rewritten.
- **A private denylist** of words only the maintainer knows: names, handles, client and private repository names. It never enters the repository. CI reads it from the `LEAK_DENYLIST` secret; locally `bin/leak-scan` reads `~/.config/agent-office/leak-denylist` (or the file named by `$AGENT_OFFICE_LEAK_DENYLIST`). A hit prints the line number in that file, never the word, and a file name with a denylist word in it is never printed either. One entry per line; a tab after the word starts a comma-separated list of files where it is allowed.

Run it before a push with the hook in `.githooks`, which scans the files of each commit the push sends (as git has them, not as they are on disk) and every commit on the way: names, emails, messages, file names and added lines, merges included:

```sh
git config core.hooksPath .githooks
```

Touched `bin/leak-scan`? Run `bin/leak-scan-probe`. A finding gitleaks reports that you read and found harmless goes into `.gitleaksignore` with a comment saying why.

## Verifying a change

Every PR says what you ran and what you saw.

**Never test against a live office.** A test must not reach your running herdr
server, your Firstmate home or your worktree pool. Use a throwaway `$HOME`, a
dedicated herdr session or socket, and a throwaway pool. A test that stops
something must prove it stopped only its own targets.

Touched the meter (`herdr/`)? Run `herdr/meter-probe`. It needs no herdr
server: it drives the meter against a fake herdr and fake transcripts.

Touched the move key (`herdr/nav`, the preset's Shift+arrow)? Run
`herdr/nav-probe`: every step, against a fake herdr. Touched any key in
`preset/herdr/config.toml`? Run `preset/preset-probe`: it checks the key table
in `preset/README.md` and the sheet in `preset/keys.txt` against herdr itself.

Touched notifications (`herdr/notify`, `lib/agent_office/notify.py`, `[notify]`)?
Run `bin/notify-probe`, and on macOS once more as `/usr/bin/python3 bin/notify-probe`.
It needs no herdr server and no network: it drives both against a fake ntfy
on localhost.

Touched `office install`, `office tools`, `office doctor` or the config (`bin/office`, `lib/`,
`config/`)? Run `bin/install-probe`. Every case runs in a throwaway `$HOME`; it needs `herdr` on
your `PATH` but no herdr server. On macOS run it once more as
`/usr/bin/python3 bin/install-probe`: that Python is 3.9, which has no TOML
reader, so it proves the vendored one in `lib/vendor/`.

Touched `setup/` or the `[setup]` keys? Run `bin/setup-probe`, and on macOS once more as `/usr/bin/python3 bin/setup-probe`. It renders every template for a stand-in user, checks each value lands, and runs `bin/leak-scan` over the result. A new template needs its line in `setup/MANIFEST.toml`, or the probe fails.

Touched `office update` (`lib/agent_office/update.py`, or what it shares with
doctor, tools and install)? Run `bin/update-probe`, and on macOS once more as
`/usr/bin/python3 bin/update-probe`. Every case runs in a throwaway `$HOME`
with fake `brew`, `npm`, `herdr` and `curl` on `PATH` and local bare
repositories as the remotes: it needs `git`, no network and no herdr, and it
updates nothing on your machine.

Touched `fm` (`bin/fm`, `lib/agent_office/fm.py`)? Run `bin/fm-probe`. It needs
`herdr` on your `PATH` and starts a herdr server of its own, in a throwaway
`$HOME` under `/tmp`, with a stand-in for Firstmate; it stops that server at
the end.

Touched `office on`, `break`, `off` or `status` (`lib/agent_office/lifecycle.py`,
`bin/officeoff-all`), or `fm.py`, which they share? Run `bin/lifecycle-probe`, and on macOS once
more as `/usr/bin/python3 bin/lifecycle-probe`. It needs `herdr` and `jq` on your `PATH` and
starts herdr sessions of its own, in a throwaway `$HOME` under `/tmp`: two owned offices and a
foreign session, to prove a stop ends only what `office on` started. It stops them all at the end.

Touched the preset (`preset/`)? Run `preset/preset-probe`. For tab closing, also run
`python3 preset/close-tab-probe`: it types the shortcut on a real TUI in a throwaway session. It needs `herdr`
on your `PATH` but no herdr server: it asks herdr for its defaults and checks
the effective keys, the key table in `preset/README.md`, the `office keys`
sheet in `preset/keys.txt`, the Mac text keys and the files for private paths.

Lifecycle commands that start, stop or update herdr, Firstmate or treehouse
need an isolated lab run: a herdr session and Firstmate home made for the test,
at most two workers, torn down afterwards. `bin/lifecycle-probe` is that run
for on, break, off and status, with a stand-in for Firstmate. For anything it
does not cover (a real Firstmate, treehouse, an update), write down the lab
steps you used.

CI runs on macOS and Ubuntu. Keep both green; they catch different bugs.

## Reporting a bug

Include your OS, `herdr --version`, and for the meter the sidebar row and what
you expected it to show. Paste `office doctor` output: it shows your home
folder as `~`. Check it before posting anyway.
