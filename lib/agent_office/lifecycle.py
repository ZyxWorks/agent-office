"""office on, break, off and status: start one office, leave it, stop it, and look at it.

Ownership is the whole idea. `office on` starts the herdr server for office.session itself, as a
headless `herdr --session <name> server` against the generated herdr config, and writes a record
of that server under the state folder (offices/<session>.json): its pid, when that process
started, its socket, and the Firstmate it was started for. A pid alone can be recycled, so pid
and start time together are what name the server. `office off` stops a session only while the
server running under that name is the recorded one. A session with no record, or with another
server behind the name, was started by someone else and is left running.

What herdr 0.9.1 gives, and what it does not (its --help is the contract):

- `herdr session stop <name>` stops one named session and answers when it is down. That is the
  only stop used here: never `herdr server stop`, which follows the caller's own pane variables,
  and never a signal to a process found by its name.
- No command or API call detaches a client. So `office break` detaches the clients `fm` and
  `office on` attached, which they recorded before they became one: it sends each the hangup a
  closing terminal window sends, which herdr documents as leaving everything running.
- A server stop ends every pane in it, the one `office off` was typed in too. So the stop runs in
  a helper process outside every session, and the result is written to last-off.json before
  anything is printed: a pane that ends with its session loses no result.

Firstmate saves through the same /stow contract `fm restart` uses (fm.stow); when the save is
not confirmed, nothing is stopped. Workers are Firstmate's, so their drain is too: a worker is
an agent whose pane a task record in Firstmate's home (state/<task>.meta, herdr_session and
herdr_pane_id) names. off refuses while one is working or waiting, or, with --stop-workers,
stops each through Firstmate's own control plane (`bin/fm-control.sh <task> exit`), which keeps
its pane, worktree, uncommitted changes and task record, and only then asks Firstmate to save:
the save then records the stopped workers, so its next session picks them up. Any other agent
in the session is not Firstmate's to stop, and still refuses the stop while it is busy. Nothing
here touches a worktree or a pool.
"""

from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import config as C
from . import doctor, fm, hooks
from .install import _confirm, ask

START_SECONDS = 30
STOP_SECONDS = 30
WORKER_EXIT_SECONDS = 300

USAGE = """\
usage: office on
       office break
       office off [--all] [--yes] [--stop-workers] [--force] [--timeout MINUTES]
       office status

office on      check the config and herdr, start the herdr session office.session against the
               generated herdr config (or use the one that runs), make sure one Firstmate runs
               in it, and attach. When it started the session or Firstmate, it first runs the
               walk-in hooks (hooks.on). Run again, it focuses what is there, and runs no hook.
               It starts no workers.
office break   detach the terminals office on and fm attached. Everything keeps running.
office off     stop this office: list what stops, ask, let Firstmate save its work (/stow), and
               only when the save is confirmed stop the herdr session and its meter. Only a
               session office on started is ever stopped. Repos, worktrees and pools are kept.
               Once office.session has stopped, it runs the go-home hooks (hooks.off).
  --all        every office this installation started, not only the configured one
  --yes        do not ask before stopping. It never forces.
  --stop-workers
               a Firstmate worker still working or waiting: have Firstmate stop it first
               (bin/fm-control.sh <task> exit), keeping its worktree and task record, instead
               of refusing the stop. Firstmate then saves, so it picks the task up next time.
  --force      when the save fails or agents are still busy, offer to stop anyway: asked
               separately, on the terminal, by typing the session name. Unsaved work may be lost.
  --timeout    minutes to wait for Firstmate's save (default 30)
office status  read-only: what runs, what the office owns, its agents by state, the meter, pending
               restarts, the other herdr sessions, an Agent Office update the last fetch saw,
               and the last office off and hooks. Exit 0 only when nothing is wrong or unknown.

A hook that fails does not stop office on or office off: it is named, and the command exits 1."""


# --- records ----------------------------------------------------------------------------------


def record_path(session: str, env) -> Path:
    return C.state_dir(env) / "offices" / f"{session}.json"


def last_off_path(env) -> Path:
    return C.state_dir(env) / "last-off.json"


def _record(path: Path) -> dict | None:
    r = C.read_json(path)
    ok = (r and r.get("session") == path.name[:-len(".json")] and isinstance(r.get("pid"), int)
          and all(isinstance(r.get(k), str) and r[k] for k in ("socket", "started"))
          and isinstance(r.get("firstmate"), dict))
    return r if ok else None


def records(env) -> list:
    """Every office this installation started and has not stopped, by session name."""
    d = C.state_dir(env) / "offices"
    found = [_record(p) for p in sorted(d.glob("*.json"))] if d.is_dir() else []
    return [r for r in found if r]


def broken(env, session: str | None = None) -> list:
    """The record files that do not read as one office on wrote (all of them, or this session's).
    Each may name a server this installation started, so a stop reports it as not done instead of
    passing over it as if there were nothing to stop."""
    d = C.state_dir(env) / "offices"
    paths = [record_path(session, env)] if session else sorted(d.glob("*.json")) if d.is_dir() else []
    return [p for p in paths if (p.exists() or p.is_symlink()) and not _record(p)]


def _broken_detail(p: Path, show) -> str:
    return (f"its record {show(p)} does not read as one office on wrote, so whether the server under that name "
            "is one this installation started cannot be proven. Nothing was stopped and the record is kept: "
            "look at it, then remove it")


def _forget(session: str, env):
    for p in (record_path(session, env), fm.clients_path(session, env)):
        try:
            p.unlink()
        except OSError:
            pass


def _office(rec: dict, cfg: dict, env, who: str) -> fm.Office:
    """The office a record names. The configured one follows the config as it is now, as fm does;
    any other is known only by what its record kept."""
    if rec["session"] == cfg["office"]["session"]:
        return fm.Office(cfg, env, who)
    return fm.Office({"office": {"session": rec["session"]}, "firstmate": rec["firstmate"]}, env, who)


def _state(rec: dict, herdr: fm.Herdr) -> tuple:
    """Whether the recorded server is the one behind the session name now.

    owned: it runs and answers. stopped: neither the process nor a server. foreign: a server
    answers under the name, but not the one office on started. unknown: herdr did not say, or
    the recorded process lives without answering."""
    srv = herdr.server()
    alive = fm.born(rec["pid"]) == rec["started"]
    if not isinstance(srv.get("running"), bool):
        return "unknown", srv
    if not srv["running"]:
        return ("unknown" if alive else "stopped"), srv
    if alive and fm._same(srv.get("socket") or "", Path(rec["socket"])):
        return "owned", srv
    return "foreign", srv


def _unsettled(session, at, env) -> bool:
    """Whether a stop that recorded no result still leaves open what runs under the session name."""
    if not isinstance(session, str) or not session:
        return True
    rec = _record(record_path(session, env))
    if rec:
        # an office on after that stop wrote this record: the stop is history
        return not (isinstance(at, int) and isinstance(rec.get("at"), int) and rec["at"] >= at)
    return fm.Herdr(session, env).server().get("running") is not False


def _now() -> int:
    return int(datetime.datetime.now().timestamp())


def _inside(env, socket: str) -> bool:
    """Whether this command runs in a pane of the session behind this socket."""
    return env.get("HERDR_ENV") == "1" and fm._same(env.get("HERDR_SOCKET_PATH") or "", Path(socket))


def _load(env, who, err):
    path = C.config_path(env)
    try:
        return C.load(path)
    except C.ConfigError as e:
        print(f"{who}: problems in {path}:", file=err)
        for p in e.problems:
            print("  " + p, file=err)
        return None


# --- office on --------------------------------------------------------------------------------


def _preflight(cfg: dict, o: fm.Office, env, out) -> Path:
    """What must hold before anything starts. Returns the generated herdr config."""
    gen = C.herdr_config_path(env)
    try:
        have = C.herdr_split(gen.read_text())[1]
    except (OSError, UnicodeDecodeError):
        have = None
    if have is None:
        raise fm.Fail(f"no generated herdr config at {gen}. Run `office install` first.")
    if have != C.herdr_config(cfg):
        raise fm.Fail(f"the generated herdr config at {gen} is older than your config or this release. "
                      "Run `office install`, then office on again.")
    ver = doctor.version("herdr", env)
    if ver is None:
        raise fm.Fail("`herdr --version` gave no version: is herdr installed? (`office tools` installs it)")
    comps = C.read_toml(doctor.MANIFEST, str(doctor.MANIFEST)).get("component", [])
    tested = next((c.get("tested") or [] for c in comps if c.get("name") == "herdr"), [])
    if ver not in tested:
        print(f"office on: herdr {ver} is not a version this release is tested with "
              f"(tested: {', '.join(tested) or 'none yet'}). `office doctor` has the details.", file=out)
    o.check_paths()
    return gen


def _start(o: fm.Office, gen: Path, cfg: dict, env, out):
    """Start the session's server, and record it as this installation's before anything else."""
    # A server hands its environment to every pane. The caller's own herdr pane variables would
    # point each of them at the session office on was typed in.
    senv = {k: v for k, v in env.items() if not k.startswith("HERDR_")}
    senv["HERDR_CONFIG_PATH"] = str(gen)
    try:
        proc = subprocess.Popen(["herdr", "--session", o.session, "server"], env=senv, cwd=str(C.home(env)),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except FileNotFoundError:
        raise fm.Fail("herdr is not installed (https://herdr.dev)")
    path = record_path(o.session, env)
    srv = {}
    for _ in range(START_SECONDS * 4):
        srv = o.herdr.server()
        if srv.get("running") or proc.poll() is not None:
            break
        time.sleep(0.25)
    started = fm.born(proc.pid)
    if not srv.get("running") or proc.poll() is not None or not started:
        if proc.poll() is None:
            proc.terminate()  # the process this call started and nothing else: it never answered
        raise fm.Fail(f"herdr did not start session '{o.session}'. Its log, if it wrote one, is "
                      "herdr-server.log in the session's folder (`herdr session list` shows it).")
    C.write_json(path, {
        "schema": 1, "session": o.session, "socket": srv.get("socket") or "", "pid": proc.pid,
        "started": started, "at": _now(), "herdr_config": str(gen),
        "firstmate": {k: v for k, v in cfg["firstmate"].items() if k != "source"},
    })
    if not _record(path):
        o.herdr.stop()
        raise fm.Fail(f"could not record the session in {path}, so it was stopped again: "
                      "a session office on cannot prove it started is one office off would never stop.")
    print(f"office on: started herdr session '{o.session}' with the generated herdr config.", file=out)


def on(args, env, out, err) -> int:
    if args:
        print(f"office on: takes no arguments. To pass arguments to Firstmate, start it with fm.\n{USAGE}", file=err)
        return 2
    cfg = _load(env, "office on", err)
    if cfg is None:
        return 1
    o = fm.Office(cfg, env, "office on")
    client, walked_in = None, False
    try:
        gen = _preflight(cfg, o, env, out)
        lock = fm._lock(env)
        try:
            srv = o.herdr.server()
            rec = _record(record_path(o.session, env))
            if not isinstance(srv.get("running"), bool):
                raise fm.Fail(f"herdr did not say whether session '{o.session}' runs (`herdr --session "
                              f"{o.session} status`). Nothing was started.")
            if not srv["running"]:
                if rec and fm.born(rec["pid"]) == rec["started"]:
                    raise fm.Fail(f"the server office on started for '{o.session}' (pid {rec['pid']}) still "
                                  "runs but does not answer. Nothing was started: see `office status`.")
                _forget(o.session, env)
                _start(o, gen, cfg, env, out)
                walked_in = True
            elif rec and _state(rec, o.herdr)[0] == "owned":
                print(f"office on: herdr session '{o.session}' is running.", file=out)
            else:
                print(f"office on: herdr session '{o.session}' is running, and office on did not start it. "
                      "Using it as it is, with the herdr config it started with. office off will leave "
                      "it running.", file=out)
            try:
                # the walk-in is a start of the office or of Firstmate, not every new window's attach
                walked_in = walked_in or o.agent() is None
                client = fm._show(o, fm.launch(o, [], out), out)
            except (fm.Fail, fm.HerdrError) as e:
                raise fm.Fail(f"{e}\nThe herdr session '{o.session}' is running. Once that is fixed, "
                              "run office on again.")
            if client:
                fm.note_client(o)
        finally:
            lock.close()
    except (fm.Fail, fm.HerdrError, C.ConfigError) as e:
        print(f"office on: {e}", file=err)
        return 1
    # after the lock: a hook may take minutes, and must not hold up an fm in another terminal
    failed = hooks.run(cfg["hooks"]["on"], "on", env, out) if walked_in else []
    for f in failed:
        print(f"office on: {f}. The office runs; `office status` shows it.", file=err)
    if client:
        out.flush()
        fm.attach(client, env)  # the office is up: a failed hook is reported above, not a reason to stay out
    return 1 if failed else 0


# --- office break -----------------------------------------------------------------------------


def _detach_key(cfg: dict) -> str:
    keys = cfg["herdr"].get("keys") or {}
    key, prefix = keys.get("detach"), keys.get("prefix")
    if not isinstance(key, str) or not isinstance(prefix, str):
        return "its detach key (`office keys`)"
    return key.replace("prefix+", prefix + " then ")


def break_(args, env, out, err) -> int:
    if args:
        print(f"office break: takes no arguments\n{USAGE}", file=err)
        return 2
    cfg = _load(env, "office break", err)
    if cfg is None:
        return 1
    session = cfg["office"]["session"]
    mine = fm.clients(session, env)
    for c in mine:
        try:
            # what a closing terminal window sends: the client leaves, the server and panes stay
            os.kill(c["pid"], signal.SIGHUP)
        except OSError:
            pass
    left = mine
    for _ in range(40):
        left = [c for c in left if fm.born(c["pid"]) == c["started"]]
        if not left:
            break
        time.sleep(0.25)
    if mine:
        C.write_json(fm.clients_path(session, env), {"schema": 1, "clients": left})
    srv = fm.Herdr(session, env).server()
    if left:
        print(f"office break: {len(left)} of {len(mine)} terminal(s) did not detach (pid "
              f"{', '.join(str(c['pid']) for c in left)}). Detach there with {_detach_key(cfg)}.", file=err)
        return 1
    if mine and srv.get("running") is not True:
        print(f"office break: detached, but herdr no longer says session '{session}' runs. "
              "See `office status`.", file=err)
        return 1
    if mine:
        print(f"office break: detached {len(mine)} terminal(s) from herdr session '{session}'. "
              "Firstmate, the workers and every pane keep running. Come back with: office on", file=out)
        return 0
    if srv.get("running") is False:
        print(f"office break: herdr session '{session}' is not running, so nothing is attached.", file=out)
        return 0
    print(f"office break: no terminal attached by office on or fm to herdr session '{session}'. herdr has "
          f"no command that detaches one it attached itself: there, press {_detach_key(cfg)}. "
          "Nothing was stopped.", file=out)
    return 0


# --- office off -------------------------------------------------------------------------------


class Target:
    """One recorded office, and what a stop of it would end."""

    def __init__(self, rec: dict, o: fm.Office, env):
        self.rec, self.o, self.env, self.session = rec, o, env, rec["session"]
        self.state, self.srv = _state(rec, o.herdr)
        self.inside = _inside(env, rec["socket"])
        self.first = self.block = self.meter = None
        self.workers, self.others, self.panes = [], [], 0
        if self.state == "owned":
            self.look()

    def look(self):
        self.first = self.block = None
        try:
            self.first = self.o.agent()
        except fm.Fail as e:
            self.block = str(e)
        try:
            agents = self.o.herdr.call("agent", "list").get("agents", [])
            self.panes = len(self.o.herdr.call("pane", "list").get("panes", []))
        except fm.HerdrError as e:
            agents, self.block = [], f"herdr did not list what runs in session '{self.session}': {e}"
        mine = (self.first or {}).get("pane_id")
        tasks = _tasks(self.o, self.session)

        def task(a):
            # a record outlives its server, and a new server reuses pane ids: the agent in that
            # pane is the task's only while it runs in the task's worktree
            got = tasks.get(a.get("pane_id"))
            return got[0] if got and _in(a.get("foreground_cwd") or a.get("cwd") or "", got[1]) else None

        rest = [a for a in agents if a.get("pane_id") != mine]
        self.workers = [dict(a, task=task(a)) for a in rest if task(a)]
        self.others = [a for a in rest if not task(a)]
        self.meter = _meter(self.rec["socket"], self.env)

    def busy(self, agents=None) -> list:
        return [a for a in (self.workers + self.others if agents is None else agents)
                if a.get("agent_status") in ("working", "blocked")]


def _home(o: fm.Office) -> Path:
    return o.code if o.home is None else o.home


def _tasks(o: fm.Office, session: str) -> dict:
    """Firstmate's own tasks in this session, by pane: {pane id: (task id, worktree)}. Its records
    say which pane each task runs in, so a worker is never guessed from its folder or its name."""
    found = {}
    for meta in sorted((_home(o) / "state").glob("*.meta")):
        rec = {}
        try:
            for line in meta.read_text(errors="replace").splitlines():
                k, eq, v = line.partition("=")
                if eq:
                    rec[k] = v  # the last one wins, as Firstmate's own fm_meta_get reads it
        except OSError:
            continue
        if (rec.get("backend") == "herdr" and rec.get("herdr_session") == session and rec.get("herdr_pane_id")
                and rec.get("worktree")):
            found[rec["herdr_pane_id"]] = (meta.stem, rec["worktree"])
    return found


def _in(cwd: str, worktree: str) -> bool:
    if not cwd:
        return False
    a, b = os.path.realpath(cwd), os.path.realpath(worktree)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def _exit_workers(o: fm.Office, tasks: list) -> dict:
    """Ask Firstmate's control plane to stop these tasks' agents, all at once, so the wait is one
    timeout and not one per worker. Returns {task: None when it says it did, else why not}."""
    exe = o.code / "bin" / "fm-control.sh"
    if not os.access(exe, os.X_OK):
        return {t: f"the Firstmate checkout has no {exe}, so its worker {t} cannot be stopped through Firstmate"
                for t in tasks}
    # the office's session, never the one the caller's own pane variables point at
    env = {k: v for k, v in o.env.items() if k not in ("HERDR_SOCKET_PATH", "HERDR_PANE_ID")}
    env.update(FM_HOME=str(_home(o)), HERDR_SESSION=o.session)
    said, runs = {}, {}
    for t in tasks:
        try:
            # a session of its own: a Ctrl-C on office off must not cut a stop off half way
            runs[t] = subprocess.Popen([str(exe), t, "exit"], cwd=str(o.code), env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       start_new_session=True)
        except OSError as e:
            said[t] = f"could not run {exe}: {e}"
    end = time.time() + WORKER_EXIT_SECONDS
    for t, r in runs.items():
        try:
            got, why = r.communicate(timeout=max(1, end - time.time()))
        except subprocess.TimeoutExpired:
            said[t] = (f"Firstmate did not stop its worker {t} within {WORKER_EXIT_SECONDS // 60} minutes; "
                       "its stop may still be running")
            continue
        lines = (why.strip() or got.strip()).splitlines()
        said[t] = None if r.returncode == 0 else (
            f"Firstmate did not stop its worker {t}: {lines[-1] if lines else f'exit {r.returncode}'}")
    return said


def _meter(socket: str, env) -> dict | None:
    """The meter running for the server on this socket, proven by what its process is."""
    run = doctor._record(C.herdr_dirs(env)[1] / "plugins" / doctor.METER_ID, ".json", socket)
    if not run or not isinstance(run.get("pid"), int) or not run.get("root"):
        return None
    try:
        r = subprocess.run(["ps", "-p", str(run["pid"]), "-o", "args="], env={"PATH": os.defpath, "LC_ALL": "C"},
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    # a recycled pid is not our meter: its command line has to be the meter the record names
    return run if str(Path(run["root"]) / "meter") in r.stdout else None


def _agent_line(a: dict, show) -> str:
    name = f"  named {a['name']}" if a.get("name") else ""
    return (f"pane {a.get('pane_id')}  {a.get('agent') or 'agent'}  {a.get('agent_status') or 'unknown'}  "
            f"{show(a.get('cwd') or '?')}{name}")


def _plan(t: Target, show, out, stop_workers: bool, home: list = ()):
    o, rec = t.o, t.rec
    if t.state == "stopped":
        print(f"  office '{t.session}': not running any more. Only its record is cleared.", file=out)
        return
    if t.state == "foreign":
        print(f"  office '{t.session}': a herdr session of that name runs, but it is not the server office on "
              "started. Left running.", file=out)
        return
    if t.state == "unknown":
        print(f"  office '{t.session}': herdr does not say whether it runs. Nothing is stopped.", file=out)
        return
    print(f"  office '{t.session}'", file=out)
    print(f"    herdr session  {t.session}, started by office on {doctor._ago(_now(), rec.get('at'))} ago "
          f"(server pid {rec['pid']}): the server and every pane in it", file=out)
    where = f"{o.harness} in {show(o.code)}" + (f", home {show(o.home)}" if o.home is not None else "")
    if t.first:
        print(f"    Firstmate      {where}: pane {t.first['pane_id']}, {t.first.get('agent_status') or 'unknown'}. "
              "Asked to save its work first (/stow)", file=out)
    elif not t.block:
        print(f"    Firstmate      {where}: not running, so there is nothing to save", file=out)
    if t.block:
        print(f"    Firstmate      cannot be asked to save: {t.block}", file=out)
    print(f"    workers        {len(t.workers) or 'none'}" + (
        ", Firstmate's tasks: each ends with the session, its worktree and task record are kept" +
        (". One still busy is stopped through Firstmate first (fm-control.sh <task> exit)" if stop_workers else "")
        + ":" if t.workers else ""), file=out)
    for a in t.workers:
        print(f"      task {a['task']}  {_agent_line(a, show)}", file=out)
    print(f"    other agents   {len(t.others) or 'none'}" + (", not Firstmate's, each ends with the session:"
                                                              if t.others else ""), file=out)
    for a in t.others:
        print(f"      {_agent_line(a, show)}", file=out)
    print(f"    panes          {t.panes} in all, agents and terminals", file=out)
    print(f"    meter          {'pid ' + str(t.meter['pid']) if t.meter else 'none running for this session'}", file=out)
    n = len(fm.clients(t.session, t.env))
    if n:
        print(f"    terminals      {n} attached by office on or fm: they detach", file=out)
    if t.inside:
        print("    this pane      is in that session: it ends with it. The result is recorded first.", file=out)
    if home:
        print(f"    go-home hooks  {len(home)}, run in order once the session has stopped (hooks.off):", file=out)
        for h in home:
            print(f"      {hooks.show(h)}", file=out)


def _stop(rec: dict, env) -> dict:
    """Stop the recorded server, its meter, and nothing else. Runs in the helper process."""
    herdr = fm.Herdr(rec["session"], env)
    state, _ = _state(rec, herdr)
    if state != "owned":
        return {"result": "incomplete", "detail": "the session changed just before the stop: it no longer "
                "runs the server office on started. Nothing was stopped."}
    meter = _meter(rec["socket"], env)
    said = ""
    try:
        herdr.stop()
    except (fm.Fail, fm.HerdrError) as e:
        said = f": {e}"
    for _ in range(STOP_SECONDS * 4):
        if fm.born(rec["pid"]) != rec["started"] and herdr.server().get("running") is False:
            break
        time.sleep(0.25)
    else:
        return {"result": "incomplete", "detail": f"the session's server (pid {rec['pid']}) survived "
                f"`herdr session stop {rec['session']}`{said}. Its record is kept."}
    _forget(rec["session"], env)
    if not meter:
        return {"result": "stopped", "detail": "no meter was running for it", "gone": True}
    try:
        # the meter leaves by itself three passes after its server; this only spares the wait
        os.kill(meter["pid"], signal.SIGTERM)
    except OSError:
        pass
    for _ in range(40):
        if not _meter(rec["socket"], env):
            return {"result": "stopped", "detail": "its meter stopped too", "gone": True}
        time.sleep(0.25)
    return {"result": "incomplete", "detail": f"the session stopped, but its meter (pid {meter['pid']}) survived",
            "gone": True}


def _detached(work) -> None:
    """Run work() in a process that no session's end reaches, and wait for it. A server stop
    hangs up every pane in it, this command included when it was typed in one."""
    for f in (sys.stdout, sys.stderr):
        f.flush()
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
            work()
        finally:
            os._exit(0)
    # the helper cannot be called back, so Ctrl-C must not make this side say "nothing was stopped"
    old = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        os.waitpid(pid, 0)
    finally:
        signal.signal(signal.SIGINT, old)


def _why(why: list) -> str:
    return "; ".join(w.rstrip(".") for w in why)


class Run:
    """The durable result of one office off: last-off.json, rewritten after every step."""

    def __init__(self, env, everything: bool):
        self.path = last_off_path(env)
        self.data = {"schema": 1, "at": _now(), "all": everything, "targets": []}

    def set(self, session: str, result: str, detail: str):
        self.data["targets"] = [t for t in self.data["targets"] if t["session"] != session]
        self.data["targets"].append({"session": session, "result": result, "detail": detail})
        C.write_json(self.path, self.data)

    def get(self, session: str) -> dict:
        got = C.read_json(self.path) or {}
        return next((t for t in got.get("targets", []) if t.get("session") == session), {})


def _claude_only(o: fm.Office) -> str:
    return ("saving through /stow is built and tested for harness claude only; firstmate.harness "
            f"is {o.harness}, so the save cannot be confirmed")


def _one(t: Target, run: Run, minutes: int, force: bool, stop_workers: bool, out,
         home: list = (), nonce: str = "") -> tuple:
    """Stop one office, or say why not. Returns (result, detail). Once it has stopped, the
    helper that stopped it runs the go-home hooks `home`, so they run even when this pane ends."""
    if t.state == "stopped":
        _forget(t.session, t.env)
        return "already stopped", "its record is cleared"
    if t.state == "foreign":
        if fm.born(t.rec["pid"]) != t.rec["started"]:
            _forget(t.session, t.env)  # the server it names is gone: the record proves nothing now
        return "left", ("a herdr session of that name runs, but not the server office on started. "
                        f"To stop it yourself: herdr session stop {t.session}")
    if t.state == "unknown":
        return "incomplete", (f"herdr does not say whether it runs, or its server (pid {t.rec['pid']}) "
                              "does not answer. Nothing was stopped.")
    if t.inside and t.first and t.env.get("HERDR_PANE_ID") == t.first.get("pane_id"):
        return "kept", ("this is Firstmate's own pane, and Firstmate cannot save while it waits for this "
                        "command. Run office off from another pane or terminal. Nothing was stopped.")
    hint = "" if force else " `office off --force` offers to stop anyway."

    def busy(workers=True):
        w, o = t.busy(t.workers) if workers else [], t.busy(t.others)
        return ([f"{len(w)} of Firstmate's workers still working or waiting for an answer (task "
                 f"{', '.join(a['task'] for a in w)}): let them finish, or run `office off --stop-workers` "
                 "to have Firstmate stop them, keeping their worktrees"] if w else []) + (
                [f"{len(o)} other agent(s), not Firstmate's, still working or waiting for an answer (pane "
                 f"{', '.join(str(a.get('pane_id')) for a in o)}): let them finish, or stop them yourself"]
                if o else [])

    # with --stop-workers a busy worker is not a reason to refuse: Firstmate stops it below
    why = ([t.block] if t.block else []) + busy(not stop_workers)
    if why and not force:
        return "kept", _why(why) + ". Nothing was sent and nothing was stopped." + hint
    drain = t.busy(t.workers) if stop_workers else []
    if drain:
        # every reason the save could not happen is checked first: a worker is never stopped for a
        # save that was never going to be asked for
        if t.first and t.o.harness != "claude":
            why.append(_claude_only(t.o))
        here = t.env.get("HERDR_PANE_ID") if t.inside else None
        if any(a.get("pane_id") == here for a in drain):
            why.append(f"this pane ({here}) is one of the workers --stop-workers would stop, so it would end "
                       "this command. Run office off from another pane or terminal")
        if why and not force:
            return "kept", _why(why) + ". No worker was stopped and nothing was stopped." + hint
        if not why:
            # before the save, so the save records them as stopped and the next session picks them up
            print(f"office off: asking Firstmate to stop {len(drain)} busy worker(s) in '{t.session}' "
                  f"(fm-control.sh <task> exit): task {', '.join(a['task'] for a in drain)}.", file=out)
            out.flush()
            first = (t.first or {}).get("pane_id")
            for task, failed in _exit_workers(t.o, [a["task"] for a in drain]).items():
                if failed:
                    why.append(failed)
                else:
                    print(f"office off: Firstmate stopped worker {task}; its worktree and task record are kept.",
                          file=out)
            t.look()
            if first and (t.first or {}).get("pane_id") != first and not t.block:
                t.block = "Firstmate changed while its workers were stopped"
            why += ([t.block] if t.block else []) + busy()
            if why and not force:
                return "kept", (_why(why) + ". Workers Firstmate did stop keep their worktrees and task records; "
                                "the session was not stopped." + hint)
    if t.first and not t.block:
        if t.o.harness != "claude":
            if _claude_only(t.o) not in why:
                why.append(_claude_only(t.o))
        else:
            try:
                fm.stow(t.o, t.first, minutes, out, "Nothing was stopped", "run office off again")
            except (fm.Fail, fm.HerdrError) as e:
                why.append(str(e))
            else:
                t.look()  # a worker may have started while Firstmate saved
                why += ([t.block] if t.block else []) + busy()
    if why:
        if not force:
            said = _why(why) + "."
            return "kept", said + ("" if "Nothing was stopped" in said else " Nothing was stopped.") + hint
        print(f"\nWARNING: office '{t.session}' is not safe to stop:", file=out)
        for w in why:
            print(f"  {w}", file=out)
        print("Stopping it now ends every pane in it. Conversations that were not saved may be lost. Repos, "
              "worktrees, pools and Firstmate's task records are kept, so the work itself can be picked up.", file=out)
        out.flush()
        if ask(f"Type the session name ({t.session}) to stop it anyway: ") != t.session:
            return "kept", ("the forced stop was not confirmed on a terminal (--yes never forces). "
                            "Nothing was stopped.")
    run.set(t.session, "stopping", "the stop began and recorded no result")
    if t.inside:
        print(f"office off: stopping '{t.session}' from inside it. If this pane ends before the result is "
              f"printed, `office status` shows it ({run.path}).", file=out)

    if home:
        print(f"office off: once '{t.session}' has stopped, {len(home)} go-home hook(s) run, up to "
              f"{hooks.TIMEOUT // 60} minutes each.", file=out)

    def work():
        got = _stop(t.rec, t.env)
        gone = got.pop("gone", False)
        run.set(t.session, **got)
        if gone and home:
            # the session is gone: its pane variables name nothing a hook should follow
            henv = {k: v for k, v in t.env.items() if k not in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_PANE_ID")}
            hooks.run(list(home), "off", henv, None, nonce)

    _detached(work)
    got = run.get(t.session)
    if got.get("result") in ("stopped", "incomplete"):
        return got["result"], got.get("detail", "")
    return "incomplete", "the stop recorded no result. See `office status`."


def off(args, env, out, err) -> int:
    everything = yes = force = stop_workers = False
    rest = []
    for a in args:
        if a == "--all":
            everything = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--force":
            force = True
        elif a == "--stop-workers":
            stop_workers = True
        else:
            rest.append(a)
    who = "office off --all" if everything else "office off"
    try:
        minutes = fm.minutes_arg(rest, "office off, besides --all, --yes, --stop-workers and --force,")
    except fm.Usage as e:
        print(f"office off: {e}\n{USAGE}", file=err)
        return 2
    cfg = _load(env, who, err)
    if cfg is None:
        return 1
    show = doctor.Report(env).show
    session = cfg["office"]["session"]
    try:
        lock = fm._lock(env)
    except fm.Fail as e:
        print(f"{who}: {e}", file=err)
        return 1
    try:
        recs = records(env) if everything else [r for r in [_record(record_path(session, env))] if r]
        bad = broken(env, None if everything else session)
        if not recs and not bad:
            return _nothing(session, everything, env, out, err)
        ts = [Target(r, _office(r, cfg, env, "office off"), env) for r in recs]
        ts.sort(key=lambda t: t.inside)  # the session this command sits in goes last
        home = cfg["hooks"]["off"]
        nonce = os.urandom(8).hex()

        def home_of(t):
            return home if t.session == session and t.state == "owned" else []
        print(f"{who}: this stops" + (" every office this installation started" if everything else "") + ":", file=out)
        for t in ts:
            _plan(t, show, out, stop_workers, home_of(t))
        for p in bad:
            print(f"  office '{p.stem}': its record {show(p)} cannot be read. Nothing is stopped.", file=out)
        print("Kept: repos, worktrees, worktree pools and Firstmate's own records. Nothing is deleted.", file=out)
        if everything:
            _others(env, {t.session for t in ts if t.state != "stopped"} | {p.stem for p in bad}, out)
        if any(t.state == "owned" for t in ts) and not yes:
            out.flush()
            if not _confirm("Stop " + ("them" if everything and len(ts) > 1 else "it") + "? [y/N] "):
                print(f"{who}: not confirmed. Nothing was stopped. Run it in a terminal to answer, "
                      "or pass --yes.", file=err)
                return 1
        run = Run(env, everything)
        code = hook_failed = 0
        for p in bad:
            run.set(p.stem, "incomplete", _broken_detail(p, show))
            print(f"{who}: office '{p.stem}': INCOMPLETE: {_broken_detail(p, show)}.", file=err)
            code = 1
        cancelled = False
        for t in ts:
            if cancelled:  # Ctrl-C ends the whole command, not one office of it
                result, detail = "kept", "cancelled before its turn. Nothing was stopped."
            else:
                try:
                    result, detail = _one(t, run, minutes, force, stop_workers, out, home_of(t), nonce)
                except KeyboardInterrupt:
                    cancelled = True
                    result, detail = "kept", ("cancelled. The session was not stopped. A save or a worker stop "
                                              "already asked for keeps running in Firstmate.")
            run.set(t.session, result, detail)
            good = result in ("stopped", "already stopped")
            print(f"{who}: office '{t.session}': {result if good else result.upper()}: {detail}",
                  file=out if good else err)
            code = code if good else 1
            if result in ("stopped", "incomplete") and home_of(t):
                hook_failed = _went_home(who, nonce, env, out, err)
        if hook_failed and not code:
            print(f"{who}: the office stopped, but a go-home hook failed (named above).", file=err)
            return 1
        if code:
            print(f"{who}: incomplete. What still runs is listed above; `office status` shows it again.", file=err)
        return code
    finally:
        lock.close()


def _went_home(who: str, nonce: str, env, out, err) -> int:
    """Report the go-home hooks the stop's helper ran: 1 when one failed or they did not run."""
    rec = hooks.last(env, "off")
    if not rec or rec.get("nonce") != nonce:
        print(f"{who}: the go-home hooks did not run: the session's server did not stop, or they recorded "
              f"no result ({hooks.path(env)}).", file=err)
        return 1
    for r in rec.get("results", []):
        if r.get("result") == "ok":
            print(f"{who}: go-home hook `{hooks.show(r.get('hook') or [])}` ran.", file=out)
    failed = hooks.failures(rec)
    for f in failed:
        print(f"{who}: go-home hook {f}. The session did stop.", file=err)
    return 1 if failed else 0


def _nothing(session: str, everything: bool, env, out, err) -> int:
    if everything:
        print("office off --all: this installation has no office it started and has not stopped. "
              "Nothing to stop.", file=out)
        _others(env, set(), out)
        return 0
    running = fm.Herdr(session, env).server().get("running")
    if running is False:
        print(f"office off: office '{session}' is not running. Nothing to stop.", file=out)
        return 0
    if running is True:
        print(f"office off: herdr session '{session}' is running, but office on did not start it: there is "
              f"no record of it in {C.state_dir(env) / 'offices'}. It is left running. To stop it "
              f"yourself: herdr session stop {session}", file=err)
        return 1
    print(f"office off: herdr did not say whether session '{session}' runs. Nothing was stopped.", file=err)
    return 1


def _sessions(env) -> list | None:
    """The names of the herdr sessions that run, or None when herdr does not list them."""
    got = doctor._run(["herdr", "session", "list", "--json"], {k: v for k, v in env.items() if k != "HERDR_SOCKET_PATH"})
    try:
        return [s.get("name") for s in json.loads(got or "").get("sessions", []) if s.get("running")]
    except (ValueError, AttributeError):
        return None


def _others(env, mine: set, out):
    """The running herdr sessions a stop-all leaves alone, named so the list shown is complete."""
    names = _sessions(env)
    if names is None:
        print("Other herdr sessions: herdr did not list them. None is touched.", file=out)
        return
    left = [n for n in names if n not in mine]
    if left:
        print(f"Left running, not started by office on: {', '.join(left)}", file=out)


# --- office status ----------------------------------------------------------------------------


def status(args, env, out, err) -> int:
    if args:
        print(f"office status: takes no arguments\n{USAGE}", file=err)
        return 2
    cfg = _load(env, "office status", err)
    if cfg is None:
        return 1
    o = fm.Office(cfg, env, "office status")
    rep = doctor.Report(env)
    session = o.session
    rep.active(cfg, session)  # the session, the herdr config it started with, and its meter
    srv = o.herdr.server()
    running = srv.get("running")
    rec = _record(record_path(session, env))
    state = _state(rec, o.herdr)[0] if rec else None
    name = "started by"
    if state == "owned":
        rep.fact(name, f"office on, {doctor._ago(_now(), rec.get('at'))} ago (server pid {rec['pid']}): office off stops it")
    elif state == "stopped":
        rep.fact(name, "office on, but that server is gone: office on starts a new one")
    elif state == "foreign" or (rec is None and running is True):
        rep.fact(name, "not office on, so office off leaves it running (`herdr session stop "
                       f"{session}` stops it)")
    elif state == "unknown":
        rep.fact(name, "unknown", problems=[f"office on recorded a server (pid {rec['pid']}), and herdr does not "
                                             "say whether it still serves the session"])
    if running is True:
        _running(o, rep, srv, env)
    for p in broken(env):
        rep.fact(f"office '{p.stem}', record", "unreadable", problems=[_broken_detail(p, rep.show) + "."])
    mine = [r for r in records(env) if r["session"] != session]
    for r in mine:
        st = _state(r, fm.Herdr(r["session"], env))[0]
        said = {"owned": "running: `office off --all` stops it", "stopped": "not running any more",
                "foreign": "another server runs under its name: left alone", "unknown": "unknown"}[st]
        rep.fact(f"office '{r['session']}', also started here", said,
                 problems=["herdr does not say whether it runs"] if st == "unknown" else [])
    _foreign(rep, env, {session} | {r["session"] for r in mine})
    last = C.read_json(last_off_path(env))
    for t in (last or {}).get("targets", []):
        good = t.get("result") in ("stopped", "already stopped")
        # a stop that failed is history once the office runs again or is gone. One with no result
        # is a problem until that is seen: started again since, or nothing under its name any more
        pending = t.get("result") == "stopping" and _unsettled(t.get("session"), last.get("at"), env)
        rep.fact(f"last office off, '{t.get('session')}'",
                 f"{t.get('result')}, {doctor._ago(_now(), last.get('at'))} ago" + ("" if good else f": {t.get('detail')}"),
                 problems=["the stop began and recorded no result: check what still runs"] if pending else [])
    for kind in hooks.KINDS:
        _hooks_fact(rep, cfg, kind, env)
    _update(rep, env)

    print("office status: read-only. Your home folder is shown as ~.", file=out)
    print(f"office '{session}' (office.session)", file=out)
    width = max(len(n) for n, _ in rep.facts)
    for n, value in rep.facts:
        print(f"  {n.ljust(width)}  {value}", file=out)
    print(file=out)
    if not rep.problems:
        print("No problems.", file=out)
        return 0
    print(f"{len(rep.problems)} problem(s):", file=out)
    for p in rep.problems:
        print("  " + p, file=out)
    return 1


def _running(o: fm.Office, rep, srv: dict, env):
    where = f"{o.harness} in {rep.show(o.code)}"
    try:
        a = o.agent()
        agents = o.herdr.call("agent", "list").get("agents", [])
    except (fm.Fail, fm.HerdrError) as e:
        rep.fact("firstmate", "unknown", problems=[str(e)])
        return
    if a:
        rep.fact("firstmate", f"{where}: pane {a['pane_id']}, {a.get('agent_status') or 'unknown'}",
                 problems=[] if a.get("agent_status") in ("idle", "working", "done", "blocked")
                 else ["herdr does not know its state"])
    else:
        rep.fact("firstmate", f"not running ({where}): fm starts it")
    rep.fact("agents", _by_state(agents))
    others = [x for x in agents if x.get("pane_id") != (a or {}).get("pane_id")]
    rep.fact("other agents", str(len(others)) if others else "none")
    for x in others:
        rep.fact("", _agent_line(x, rep.show))
    _restored(o, rep, agents)
    n = len(fm.clients(o.session, env))
    rep.fact("terminals", f"{n} attached by office on or fm: office break detaches them" if n
             else "none attached by office on or fm (herdr does not report the ones it attached itself)")
    stale = [k for k in ("restart_needed", "server_binary_stale") if srv.get(k)]
    if stale:
        rep.fact("restart pending", "yes", problems=[
            f"herdr says its running server is older than the installed herdr ({', '.join(stale)}): "
            "it runs the new one after a restart of the session"])
    elif all(isinstance(srv.get(k), bool) for k in ("restart_needed", "server_binary_stale")):
        rep.fact("restart pending", "none that herdr reports")
    else:
        rep.fact("restart pending", "unknown", problems=["herdr did not say whether its server needs a restart"])


def bare_resume(argv: list, harness: str) -> bool:
    """Whether a process is the harness started with nothing but a resume: what herdr runs for an
    agent pane after a server restart (`claude --resume <id>`), without the flags it started with.
    The harness may run under an interpreter, so its own argv entry is found by name."""
    at = next((i for i, x in enumerate(argv) if os.path.basename(x) == harness), None)
    if at is None:
        return False
    rest = argv[at + 1:]
    return (len(rest) == 2 and rest[0] in ("--resume", "-r")) or (len(rest) == 1 and rest[0].startswith("--resume="))


def _restored(o: fm.Office, rep, agents: list):
    """Firstmate's workers that a herdr restart left without their launch contract.

    After a server restart herdr either resumes an agent pane as a bare `claude --resume <id>`
    ([session] resume_agents_on_restore, herdr's default) or, with that off as the preset sets it,
    brings the pane back as a shell that still holds the agent's session id. A bare resume runs
    without the permission mode, folders, system prompt, effort and settings Firstmate started it
    with; a shell is a husk. Both are Firstmate's to start again with its own flags. Only panes a
    task record names count, and only while their folder is the task's worktree: a new server can
    reuse a pane id."""
    tasks = _tasks(o, o.session)
    if not tasks:
        return
    try:
        panes = {p.get("pane_id"): p for p in o.herdr.call("pane", "list").get("panes", [])}
    except fm.HerdrError as e:
        rep.fact("workers after a restart", "unknown", problems=[f"herdr did not list the panes: {e}"])
        return
    by_pane = {x.get("pane_id"): x for x in agents}
    bad = 0
    for pane, (task, worktree) in sorted(tasks.items()):
        p = panes.get(pane)
        if not p or not _in(p.get("foreground_cwd") or p.get("cwd") or "", worktree):
            continue  # gone, or a pane id a new server gave to something else: not this task's
        name = f"worker {task}"
        if pane not in by_pane:
            bad += 1
            rep.fact(name, f"pane {pane}: a husk, no agent runs in it", problems=[
                f"no agent runs in pane {pane}, as after a herdr restart: a husk. Firstmate has to "
                "start it again, with its own flags and `--resume` with the session id herdr kept"])
            continue
        kind = by_pane[pane].get("agent")
        if kind != "claude":
            continue  # a bare resume is measured for Claude only; the worker's own harness, not Firstmate's
        try:
            procs = o.herdr.call("pane", "process-info", "--pane", pane).get("process_info", {})
        except fm.HerdrError as e:
            bad += 1  # not checked, so no all-clear line
            rep.fact(name, f"pane {pane}: unknown", problems=[f"herdr did not say what runs in it: {e}"])
            continue
        argv = next((x.get("argv") or [] for x in procs.get("foreground_processes") or []
                     if bare_resume(x.get("argv") or [], kind)), None)
        if argv is not None:
            bad += 1
            rep.fact(name, f"pane {pane}: {' '.join(argv)}", problems=[
                f"pane {pane} runs as a bare `claude --resume`: herdr restored it without the flags "
                "Firstmate started it with. Set [session] resume_agents_on_restore = false (the "
                "office preset does), and let Firstmate start it again"])
    if not bad:
        rep.fact("workers after a restart", f"{len(tasks)} task record(s) here: no husk, no bare resume")


def _by_state(agents: list) -> str:
    """ "3: 1 working, 2 idle" """
    if not agents:
        return "none"
    n = {}
    for x in agents:
        k = x.get("agent_status") or "unknown"
        n[k] = n.get(k, 0) + 1
    return f"{len(agents)}: " + ", ".join(f"{v} {k}" for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0])))


def _foreign(rep, env, mine: set):
    """One line per other herdr session that runs: what else this machine runs, beside the office."""
    names = _sessions(env)
    if names is None:
        rep.fact("other sessions", "unknown", problems=["herdr did not list its sessions (`herdr session list`)"])
        return
    for name in [n for n in names if n and n not in mine]:
        try:
            agents = fm.Herdr(name, env).call("agent", "list").get("agents", [])
        except (fm.Fail, fm.HerdrError):
            said = "running, its agents unknown"
        else:
            said = f"{len(agents)} agent{'' if len(agents) == 1 else 's'}"
        rep.fact(f"session '{name}'", f"{said}, not this office's: office off leaves it running")


def _hooks_fact(rep, cfg: dict, kind: str, env):
    rec, have = hooks.last(env, kind), cfg["hooks"][kind]
    if not rec and not have:
        return
    name = f"{hooks.KINDS[kind]} ({len(have)})"
    if not rec:
        rep.fact(name, "have not run yet")
        return
    failed = hooks.failures(rec)
    ran = len(rec.get("results", []))
    said = f"{ran} ran {doctor._ago(_now(), rec.get('at'))} ago: " + (
        f"{len(failed)} failed" if failed else "all ok")
    rep.fact(name, said, problems=[f"last run: {f}" for f in failed])


def _update(rep, env):
    """Agent Office against origin as this checkout last fetched it. No network call, so it never
    says "up to date": only how HEAD stands to that fetch, and how old the fetch is."""
    if C.REPO.resolve() != C.release_dir(env).resolve():
        return  # a development checkout: office update never moves it
    git = ["git", "-C", str(C.REPO)]

    def sha(ref):
        got = doctor._run([*git, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], env)
        return got.strip() if got else None

    head = sha("HEAD")
    tip = next((t for t in (sha(r) for r in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main")) if t), None)
    if not head or not tip:
        rep.fact("agent office", "unknown", problems=["no fetched origin to compare this release with: `office update --check` asks origin"])
        return
    short = {c: (doctor._run([*git, "rev-parse", "--short", c], env) or c[:7]).strip() for c in (head, tip)}
    gitdir = doctor._run([*git, "rev-parse", "--absolute-git-dir"], env)
    try:
        fetched = int(Path(gitdir.strip(), "FETCH_HEAD").stat().st_mtime) if gitdir else None
    except OSError:
        fetched = None
    when = f"fetched {doctor._ago(_now(), fetched)} ago" if fetched else "fetched at an unknown time"

    def ancestor(a, b):
        return doctor._run([*git, "merge-base", "--is-ancestor", a, b], env) is not None
    if head == tip:
        said = f"`{short[head]}`, the same as origin when last {when}: `office update --check` asks origin for newer"
    elif ancestor(head, tip):
        said = (f"Agent Office update available (`{short[head]}` to `{short[tip]}`), from origin as last {when}: "
                "`office update` installs it")
    elif ancestor(tip, head):
        said = f"`{short[head]}`, ahead of origin as last {when} (`{short[tip]}`)"
    else:
        said = f"`{short[head]}` has diverged from origin as last {when} (`{short[tip]}`): `office update --check` says more"
    rep.fact("agent office", said)


def run(verb: str, args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    return {"on": on, "break": break_, "off": off, "status": status}[verb](args, env, out, err)
