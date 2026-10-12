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
not confirmed, nothing is stopped. Workers are Firstmate's: off lists the agents in the session,
refuses while one is working or waiting, and never touches a worktree or a pool.
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
from . import doctor, fm
from .install import _confirm, ask

START_SECONDS = 30
STOP_SECONDS = 30

USAGE = """\
usage: office on
       office break
       office off [--all] [--yes] [--force] [--timeout MINUTES]
       office status

office on      check the config and herdr, start the herdr session office.session against the
               generated herdr config (or use the one that runs), make sure one Firstmate runs
               in it, and attach. Run again, it focuses what is there. It starts no workers.
office break   detach the terminals office on and fm attached. Everything keeps running.
office off     stop this office: list what stops, ask, let Firstmate save its work (/stow), and
               only when the save is confirmed stop the herdr session and its meter. Only a
               session office on started is ever stopped. Repos, worktrees and pools are kept.
  --all        every office this installation started, not only the configured one
  --yes        do not ask before stopping. It never forces.
  --force      when the save fails or agents are still busy, offer to stop anyway: asked
               separately, on the terminal, by typing the session name. Unsaved work may be lost.
  --timeout    minutes to wait for Firstmate's save (default 30)
office status  read-only: what runs, what the office owns, the meter, pending restarts, and the
               result of the last office off. Exit 0 only when nothing is wrong or unknown."""


# --- records ----------------------------------------------------------------------------------


def record_path(session: str, env) -> Path:
    return C.state_dir(env) / "offices" / f"{session}.json"


def last_off_path(env) -> Path:
    return C.state_dir(env) / "last-off.json"


def _record(path: Path) -> dict | None:
    r = fm.read_json(path)
    ok = (r and r.get("session") == path.name[:-len(".json")] and isinstance(r.get("pid"), int)
          and all(isinstance(r.get(k), str) and r[k] for k in ("socket", "started"))
          and isinstance(r.get("firstmate"), dict))
    return r if ok else None


def records(env) -> list:
    """Every office this installation started and has not stopped, by session name."""
    d = C.state_dir(env) / "offices"
    found = [_record(p) for p in sorted(d.glob("*.json"))] if d.is_dir() else []
    return [r for r in found if r]


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
    gen = C.state_dir(env) / "herdr" / "config.toml"
    try:
        have = gen.read_text()
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
    fm.write_json(path, {
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
    client = None
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
            elif rec and _state(rec, o.herdr)[0] == "owned":
                print(f"office on: herdr session '{o.session}' is running.", file=out)
            else:
                print(f"office on: herdr session '{o.session}' is running, and office on did not start it. "
                      "Using it as it is, with the herdr config it started with. office off will leave "
                      "it running.", file=out)
            try:
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
    if client:
        fm.attach(client, env)
    return 0


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
        fm.write_json(fm.clients_path(session, env), {"schema": 1, "clients": left})
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
        self.others, self.panes = [], 0
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
        self.others = [a for a in agents if a.get("pane_id") != mine]
        self.meter = _meter(self.rec["socket"], self.env)

    def busy(self) -> list:
        return [a for a in self.others if a.get("agent_status") in ("working", "blocked")]


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


def _plan(t: Target, show, out):
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
    print(f"    other agents   {len(t.others) or 'none'}" + (", each ends with the session:" if t.others else ""), file=out)
    for a in t.others:
        print(f"      {_agent_line(a, show)}", file=out)
    print(f"    panes          {t.panes} in all, agents and terminals", file=out)
    print(f"    meter          {'pid ' + str(t.meter['pid']) if t.meter else 'none running for this session'}", file=out)
    n = len(fm.clients(t.session, t.env))
    if n:
        print(f"    terminals      {n} attached by office on or fm: they detach", file=out)
    if t.inside:
        print("    this pane      is in that session: it ends with it. The result is recorded first.", file=out)


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
        return {"result": "stopped", "detail": "no meter was running for it"}
    try:
        # the meter leaves by itself three passes after its server; this only spares the wait
        os.kill(meter["pid"], signal.SIGTERM)
    except OSError:
        pass
    for _ in range(40):
        if not _meter(rec["socket"], env):
            return {"result": "stopped", "detail": "its meter stopped too"}
        time.sleep(0.25)
    return {"result": "incomplete", "detail": f"the session stopped, but its meter (pid {meter['pid']}) survived"}


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
    os.waitpid(pid, 0)


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
        fm.write_json(self.path, self.data)

    def get(self, session: str) -> dict:
        got = fm.read_json(self.path) or {}
        return next((t for t in got.get("targets", []) if t.get("session") == session), {})


def _one(t: Target, run: Run, minutes: int, force: bool, out) -> tuple:
    """Stop one office, or say why not. Returns (result, detail)."""
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

    def busy():
        return [f"{len(t.busy())} agent(s) still working or waiting for an answer (pane "
                f"{', '.join(str(a.get('pane_id')) for a in t.busy())}): let them finish, or ask Firstmate "
                "to stop them"] if t.busy() else []

    why = ([t.block] if t.block else []) + busy()
    if why and not force:
        return "kept", _why(why) + ". Nothing was sent and nothing was stopped." + hint
    if t.first and not t.block:
        if t.o.harness != "claude":
            why.append("saving through /stow is built and tested for harness claude only; firstmate.harness "
                       f"is {t.o.harness}, so the save cannot be confirmed")
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
    _detached(lambda: run.set(t.session, **_stop(t.rec, t.env)))
    got = run.get(t.session)
    if got.get("result") in ("stopped", "incomplete"):
        return got["result"], got.get("detail", "")
    return "incomplete", "the stop recorded no result. See `office status`."


def off(args, env, out, err) -> int:
    everything = yes = force = False
    rest = []
    for a in args:
        if a == "--all":
            everything = True
        elif a in ("--yes", "-y"):
            yes = True
        elif a == "--force":
            force = True
        else:
            rest.append(a)
    who = "office off --all" if everything else "office off"
    try:
        minutes = fm.minutes_arg(rest, "office off, besides --all, --yes and --force,")
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
        if not recs:
            return _nothing(session, everything, env, out, err)
        ts = [Target(r, _office(r, cfg, env, "office off"), env) for r in recs]
        ts.sort(key=lambda t: t.inside)  # the session this command sits in goes last
        print(f"{who}: this stops" + (" every office this installation started" if everything else "") + ":", file=out)
        for t in ts:
            _plan(t, show, out)
        print("Kept: repos, worktrees, worktree pools and Firstmate's own records. Nothing is deleted.", file=out)
        if everything:
            _others(env, {t.session for t in ts if t.state != "stopped"}, out)
        if any(t.state == "owned" for t in ts) and not yes:
            out.flush()
            if not _confirm("Stop " + ("them" if everything and len(ts) > 1 else "it") + "? [y/N] "):
                print(f"{who}: not confirmed. Nothing was stopped. Run it in a terminal to answer, "
                      "or pass --yes.", file=err)
                return 1
        run = Run(env, everything)
        code = 0
        for t in ts:
            try:
                result, detail = _one(t, run, minutes, force, out)
            except KeyboardInterrupt:
                result, detail = "kept", ("cancelled. Nothing was stopped. A save already asked for keeps "
                                          "running in Firstmate.")
            run.set(t.session, result, detail)
            good = result in ("stopped", "already stopped")
            print(f"{who}: office '{t.session}': {result if good else result.upper()}: {detail}",
                  file=out if good else err)
            code = code if good else 1
        if code:
            print(f"{who}: incomplete. What still runs is listed above; `office status` shows it again.", file=err)
        return code
    finally:
        lock.close()


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


def _others(env, mine: set, out):
    """The running herdr sessions a stop-all leaves alone, named so the list shown is complete."""
    got = doctor._run(["herdr", "session", "list", "--json"], {k: v for k, v in env.items() if k != "HERDR_SOCKET_PATH"})
    try:
        names = [s.get("name") for s in json.loads(got or "").get("sessions", []) if s.get("running")]
    except (ValueError, AttributeError):
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
    mine = [r for r in records(env) if r["session"] != session]
    for r in mine:
        st = _state(r, fm.Herdr(r["session"], env))[0]
        said = {"owned": "running: `office off --all` stops it", "stopped": "not running any more",
                "foreign": "another server runs under its name: left alone", "unknown": "unknown"}[st]
        rep.fact(f"office '{r['session']}', also started here", said,
                 problems=["herdr does not say whether it runs"] if st == "unknown" else [])
    last = fm.read_json(last_off_path(env))
    for t in (last or {}).get("targets", []):
        good = t.get("result") in ("stopped", "already stopped")
        pending = t.get("result") == "stopping"
        # a stop that failed is history once the office runs again or is gone; one with no result is not
        rep.fact(f"last office off, '{t.get('session')}'",
                 f"{t.get('result')}, {doctor._ago(_now(), last.get('at'))} ago" + ("" if good else f": {t.get('detail')}"),
                 problems=["the stop began and recorded no result: check what still runs"] if pending else [])

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
    others = [x for x in agents if x.get("pane_id") != (a or {}).get("pane_id")]
    rep.fact("other agents", str(len(others)) if others else "none")
    for x in others:
        rep.fact("", _agent_line(x, rep.show))
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


def run(verb: str, args, env=None, out=sys.stdout, err=sys.stderr) -> int:
    env = dict(os.environ if env is None else env)
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE, file=out)
        return 0
    return {"on": on, "break": break_, "off": off, "status": status}[verb](args, env, out, err)
