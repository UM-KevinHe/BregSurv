"""Sessions -- past analyses, kept on this machine, reopened and continued.

A sibling of component 4 (Memory): same directory, same switches, same rule
that a failure here never fails an analysis. Deliberately NOT called "4b",
which already labels the planner's discrete grid (plan.py, guards.py).

A left-hand list of past analyses, a button that starts a new one, and a
session that can be reopened days later and carried on.

🔴 WHY THIS IS CHEAP HERE, AND THE LINE WORTH REUSING. The model is stateless:
every act is one constrained generation from `state.Session`
(`LM(pi_a, o_a(s_t))`), and no transcript is ever re-sent. So resuming is
**reloading a typed object**, not replaying or compressing a conversation --
the input to the next act is RECOMPUTED from the restored state and is
identical to what it would have been had the session never closed. **No model
call appears anywhere in this module**, and none is needed: there is nothing
to summarise, because nothing the model wrote was ever a premise.

A summary could not be the resume artifact even if we wanted one. `guards.audit`
checks a role marked `quoted` against the analyst's own words (`analyst_text`,
read out of the action log); a paraphrase would either fail that check or, if
the check were loosened to accept it, destroy the guarantee it exists for.
**So the analyst's own messages are stored verbatim, and `events.jsonl` is
load-bearing, not a convenience.**

Two files per session carry the state and one carries the chat:

  * `events.jsonl` -- the append-only typed action log, the source of truth;
  * `session.json` -- its fold, so opening a session is one read;
  * `messages.jsonl` -- the conversation as the person saw it, for the screen.

`rebuild()` recomputes the fold from the events, which is what makes the
duplication safe rather than two authorities.

🔴 RESUME RE-VERIFIES, IT DOES NOT TRUST. The cohort file is re-fingerprinted
on every open. Identical: full restore. Missing: read-only -- the chat and the
past artifacts open, nothing can be fitted. Changed: the verification is
DROPPED and the declaration comes back as a proposal whose every source
becomes `remembered`, the profile is taken again and the gate runs again. A
restored verification never survives a changed file, and C3 re-hashes the
configuration at dispatch anyway, so a resumed session cannot smuggle in a
configuration that was never verified.

Never written here: a row or a value of the cohort; the external RECORDS table
(an individual-level release is recorded by path and checksum, a coefficient
release by value, because published numbers are published); prompts; the
model's raw output (that already lives per run in `trace.json`); any key.

Off on a shared host (`DEPLOYMENT_MODE=demo`) and whenever
`BREGSURV_SESSIONS=off` -- the banner's promise is per deployment, and on a
public Space it promises that nothing is kept.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
import shutil
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import declaration as _decl_mod
from . import external as _ext_mod
from . import pipeline as _pipe_mod
from .state import Session

SCHEMA_VERSION = 1


# ---------------------------------------------------------------- utilities
def _now() -> str:
    # microseconds, not seconds: `updated` orders the sidebar, and three
    # sessions started inside one second sorted arbitrarily when it was coarser
    return _dt.datetime.now().isoformat(timespec="microseconds")


def _sid() -> str:
    """Sortable, collision-free, and no model involved in naming anything."""
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def _write_atomic(path: Path, text: str) -> None:
    """Temp file plus `os.replace`, the pattern `memory.Store._write` uses: an
    interrupted write leaves the previous snapshot intact rather than half of
    the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def _append_line(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_lines(path: Path) -> List[Any]:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    # one corrupt line is not a reason to lose the rest; an
                    # interrupted append is exactly how the last one gets cut
                    continue
    except OSError:
        pass
    return out


def _fields_of(cls) -> List[str]:
    return [f.name for f in fields(cls)]


def _only_known(cls, d: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys the dataclass no longer has, so a session written by an older
    build opens instead of raising on a field that has since been renamed."""
    known = set(_fields_of(cls))
    return {k: v for k, v in (d or {}).items() if k in known}


# ------------------------------------------------------- typed round-tripping
# 🔴 NO PICKLE. It is fragile across versions and it executes code from a file
# on disk; a persistence format must not be a code path. Every object below is
# a dataclass with declared fields, so an explicit dict is both safe and
# readable by a person opening the file to see what was kept.

def decl_to_dict(d: Any) -> Optional[Dict[str, Any]]:
    return None if d is None else asdict(d)


def decl_from_dict(d: Optional[Dict[str, Any]]) -> Any:
    if not d:
        return None
    return _decl_mod.Declaration(**_only_known(_decl_mod.Declaration, d))


def ver_to_dict(v: Any) -> Optional[Dict[str, Any]]:
    return None if v is None else asdict(v)


def ver_from_dict(d: Optional[Dict[str, Any]]) -> Any:
    if not d:
        return None
    return _decl_mod.Verification(**_only_known(_decl_mod.Verification, d))


def ext_to_dict(e: Any) -> Optional[Dict[str, Any]]:
    return None if e is None else e.as_dict()


def ext_from_dict(d: Optional[Dict[str, Any]]) -> Any:
    if not d:
        return None
    return _ext_mod.ExternalObject(**_only_known(_ext_mod.ExternalObject, d))


# `report` and `candidates` are deliberately NOT in run.json: they are already
# on disk as `report.md` and `candidates.json` in the same directory, and
# report.md is the authoritative text because `draw_km` edits it in place after
# the result object was built. Reading them back is correctness, not economy.
_RUN_FROM_ARTIFACTS = ("report", "candidates")


def run_to_dict(r: Any) -> Dict[str, Any]:
    d = {}
    for name in _fields_of(_pipe_mod.RunResult):
        if name in _RUN_FROM_ARTIFACTS:
            continue
        val = getattr(r, name)
        if name == "declaration":
            val = decl_to_dict(val)
        elif name == "verification":
            val = ver_to_dict(val)
        d[name] = val
    return d


def run_from_dict(d: Dict[str, Any], report: str,
                  candidates: Dict[str, Any]) -> Any:
    kw = _only_known(_pipe_mod.RunResult, d)
    kw["declaration"] = decl_from_dict(kw.get("declaration"))
    kw["verification"] = ver_from_dict(kw.get("verification"))
    kw["report"] = report
    kw["candidates"] = candidates
    return _pipe_mod.RunResult(**kw)


# Session fields that are NOT persisted, each for a stated reason.
_SESSION_SKIP = {
    # the per-run objects; they live in runs/<run_id>/ and are restored from there
    "result", "results",
    # paths of files this process created in a framework temp directory; a
    # resumed session re-resolves them (and `keep_data` copies the ones that
    # matter into the session's own directory)
    "temp",
}


def session_to_dict(session: Session) -> Dict[str, Any]:
    d: Dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    for name in _fields_of(Session):
        if name in _SESSION_SKIP:
            continue
        val = getattr(session, name)
        if name in ("declaration", "dict_decl"):
            val = decl_to_dict(val)
        elif name == "verification":
            val = ver_to_dict(val)
        elif name == "external":
            val = ext_to_dict(val)
        elif name == "externals":
            val = {k: ext_to_dict(v) for k, v in (val or {}).items()}
        d[name] = val
    return d


def session_from_dict(d: Dict[str, Any]) -> Session:
    kw = _only_known(Session, d)
    for name in _SESSION_SKIP:
        kw.pop(name, None)
    kw["declaration"] = decl_from_dict(kw.get("declaration"))
    kw["dict_decl"] = decl_from_dict(kw.get("dict_decl"))
    kw["verification"] = ver_from_dict(kw.get("verification"))
    kw["external"] = ext_from_dict(kw.get("external"))
    kw["externals"] = {k: ext_from_dict(v)
                       for k, v in (kw.get("externals") or {}).items()}
    # a release that reads but is not in `externals` would make the state line
    # disagree with itself; the active one is always a member
    if kw["external"] is not None and not kw["externals"]:
        prov = kw["external"].provenance or {}
        kw["externals"] = {str(prov.get("file") or prov.get("path") or "external"):
                           kw["external"]}
    return Session(**kw)


# ------------------------------------------------------------------- cards
@dataclass
class SessionCard:
    """One row of the sidebar. Everything in it is a fact already recorded."""
    sid: str
    title: str
    cohort: str
    design: str
    external: str
    n_runs: int
    selected: Optional[str]
    updated: str
    read_only: bool = False

    def line(self) -> str:
        """The second line of the row: what this analysis is, in few words."""
        bits = [self.design] if self.design else []
        if self.external and self.external != "none":
            bits.append(self.external)
        if self.selected:
            bits.append(f"selected: {self.selected}")
        elif self.n_runs:
            bits.append(f"{self.n_runs} run" + ("s" if self.n_runs != 1 else ""))
        return " · ".join(bits)


@dataclass
class LoadedSession:
    session: Optional[Session]
    messages: List[List[Any]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    read_only: bool = False
    data_changed: bool = False


def title_for(session: Session, selected: Optional[str] = None) -> str:
    """🔴 Deterministic, and no model names a session. The cohort file and the
    date identify it; the selected member is appended once a run exists, which
    is what the person actually looks for in a list of past analyses."""
    stem = Path(session.data_path).stem if session.data_path else "analysis"
    day = _dt.date.today().isoformat()
    return f"{stem} · {day}" + (f" · {selected}" if selected else "")


def _selected_of(session: Session) -> Optional[str]:
    res = getattr(session, "result", None)
    if res is None:
        return None
    sel = (getattr(res, "candidates", {}) or {}).get("selected") or {}
    return sel.get("label") or sel.get("key")


# ------------------------------------------------------------------- store
class SessionStore:
    """The per-user session directory. Every method is safe to call when the
    store is disabled, when the directory is missing, and when a file in it is
    unreadable.

    🔴 A PERSISTENCE FAILURE NEVER FAILS AN ANALYSIS. Every write is wrapped,
    returns a boolean and logs nothing to the screen -- the rule `memory.Store`
    already follows. Someone's analysis must not die because a disk was full.
    """

    def __init__(self, path: Optional[str] = None, enabled: Optional[bool] = None,
                 keep_data: Optional[bool] = None):
        env = os.environ.get("BREGSURV_SESSIONS", "").strip()
        if enabled is None:
            enabled = (os.environ.get("DEPLOYMENT_MODE", "local").lower() != "demo"
                       and env.lower() != "off")
        self.enabled = bool(enabled)
        if path:
            self.root = Path(path)
        elif env and env.lower() != "off":
            self.root = Path(env).expanduser()
        else:
            self.root = Path.home() / ".bregsurv" / "sessions"
        # 🔴 Decision 6:
        # the file a person uploaded is a copy a framework made in a temp
        # directory, so recording only its PATH means that in a day or two
        # every past analysis opens read-only -- the capability would exist and
        # never work. With `keep_data` the cohort, the release and the test
        # file are copied into `<sid>/data/`, under the person's own home, mode
        # 0600, beside `memory.json`, and the session fully resumes. Set
        # `BREGSURV_SESSIONS_KEEP_DATA=off` to record path and checksum only.
        if keep_data is None:
            keep_data = os.environ.get("BREGSURV_SESSIONS_KEEP_DATA", "").strip().lower() \
                not in ("off", "0", "no", "false")
        self.keep_data = bool(keep_data and self.enabled)

    # ---------------------------------------------------------- locations
    def dir(self, sid: str) -> Path:
        return self.root / sid

    def run_dir(self, sid: str, run_id: str) -> Path:
        return self.dir(sid) / "runs" / run_id

    def _snapshot(self, sid: str) -> Path:
        return self.dir(sid) / "session.json"

    def _events(self, sid: str) -> Path:
        return self.dir(sid) / "events.jsonl"

    def _messages(self, sid: str) -> Path:
        return self.dir(sid) / "messages.jsonl"

    def _index(self) -> Path:
        return self.root / "index.json"

    def _mkdir(self, sid: str) -> Path:
        d = self.dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(d, 0o700)
        except OSError:
            pass
        return d

    def describe(self) -> Dict[str, Any]:
        """For provenance and for the banner: where sessions live, or that they
        are not kept at all."""
        return {"enabled": self.enabled,
                "root": str(self.root) if self.enabled else None,
                "keep_data": self.keep_data}

    # -------------------------------------------------------------- create
    def new(self, session: Optional[Session] = None) -> Optional[str]:
        """Start a session directory and return its id, or None when off."""
        if not self.enabled:
            return None
        sid = _sid()
        try:
            self._mkdir(sid)
        except OSError:
            return None
        if session is not None:
            self.save(sid, session)
        return sid

    def adopt(self, session: Session) -> Tuple[Optional[str], Session]:
        """Give a freshly profiled session an id, copying its files in if
        `keep_data` is on. Returns (sid, session) -- the session may come back
        with its paths pointing into the session directory, which is what makes
        it reopenable later."""
        if not self.enabled or session is None or session.profile is None:
            return None, session
        sid = self.new()
        if sid is None:
            return None, session
        if self.keep_data:
            session = self._keep_files(sid, session)
        session = replace(session, sid=sid)
        self.save(sid, session)
        for a in session.actions:
            self.append_event(sid, a)
        return sid, session

    def _keep_files(self, sid: str, session: Session) -> Session:
        """Copy the cohort, the releases and the test file into `<sid>/data/`
        and point the session at the copies. The shipped example is left where
        it is -- it is not the person's data and it does not move."""
        here = Path(__file__).resolve().parent.parent / "demo"
        d = self.dir(sid) / "data"
        changes: Dict[str, Any] = {}

        def take(path: Optional[str]) -> Optional[str]:
            if not path:
                return None
            q = Path(path)
            if not q.exists() or q == here or here in q.parents:
                return path
            try:
                d.mkdir(parents=True, exist_ok=True)
                os.chmod(d, 0o700)
                dest = d / q.name
                if dest.resolve() == q.resolve():
                    return str(dest)
                shutil.copy2(q, dest)
                os.chmod(dest, 0o600)
                return str(dest)
            except OSError:
                return path

        # the copy keeps the file's own name, so `data_expr` -- which
        # run_candidates.R derives from the basename -- does not change; a
        # rename here would silently address a table that does not exist
        new_data = take(session.data_path)
        if new_data != session.data_path:
            changes["data_path"] = new_data
        new_test = take(session.test_data_path)
        if new_test != session.test_data_path:
            changes["test_data_path"] = new_test
        # a release is addressed by path only when it carries individual-level
        # records; a coefficient release already travels by value
        exts = {}
        for name, e in (session.externals or {}).items():
            if e is not None and getattr(e, "individual_data", None):
                p = take((e.individual_data or {}).get("path"))
                e = replace(e, individual_data=dict(e.individual_data, path=p))
            exts[name] = e
        if exts != dict(session.externals or {}):
            changes["externals"] = exts
            if session.external is not None:
                nm = session.external_name
                changes["external"] = exts.get(nm, session.external)
        return replace(session, **changes) if changes else session

    # ---------------------------------------------------------------- write
    def save(self, sid: Optional[str], session: Optional[Session]) -> bool:
        """Rewrite the snapshot and the index row. Called after every turn."""
        if not self.enabled or not sid or session is None:
            return False
        try:
            self._mkdir(sid)
            _write_atomic(self._snapshot(sid),
                          json.dumps(session_to_dict(session), indent=1,
                                     ensure_ascii=False, default=str))
            self._touch_index(sid, session)
            return True
        except Exception:
            return False

    def append_event(self, sid: Optional[str], action: Dict[str, Any]) -> bool:
        """One typed action. 🔴 This log is what `guards.audit` reads a `quoted`
        role back out of, so it is appended as it happened and never rewritten."""
        if not self.enabled or not sid or not isinstance(action, dict):
            return False
        try:
            _append_line(self._events(sid), {"at": _now(), **action})
            return True
        except Exception:
            return False

    def append_events(self, sid: Optional[str], actions: List[Dict[str, Any]],
                      since: int = 0) -> bool:
        """The actions a turn added, in order. `since` is how many the log
        already holds, so a turn appends only what is new."""
        ok = True
        for a in list(actions or [])[since:]:
            ok = self.append_event(sid, a) and ok
        return ok

    def sync_events(self, sid: Optional[str], actions: List[Dict[str, Any]]) -> bool:
        """Append whatever the turn added. The log's own length decides where
        to start, so nothing in the process has to remember a count and a
        restart mid-conversation cannot duplicate or skip a line."""
        if not self.enabled or not sid:
            return False
        try:
            have = len(_read_lines(self._events(sid)))
        except Exception:
            have = 0
        return self.append_events(sid, actions, since=have)

    def append_message(self, sid: Optional[str], user: Any, bot: Any) -> bool:
        """One exchange as the person saw it. Files in the chat arrive as
        tuples; they are stored as the path, which is what the screen needs."""
        if not self.enabled or not sid:
            return False
        try:
            _append_line(self._messages(sid), {"at": _now(),
                                               "user": _plain(user),
                                               "bot": _plain(bot)})
            return True
        except Exception:
            return False

    def save_messages(self, sid: Optional[str], history: List[Any]) -> bool:
        """Rewrite the conversation to match the screen. The chat is REPLACED
        rather than appended to because a turn may rewrite the last exchange
        (the technical cards become one plain summary once a result exists), so
        appending would keep a line the person no longer sees."""
        if not self.enabled or not sid:
            return False
        try:
            self._mkdir(sid)
            lines = "".join(json.dumps({"user": _plain(u), "bot": _plain(b)},
                                       ensure_ascii=False, default=str) + "\n"
                            for u, b in (history or []))
            _write_atomic(self._messages(sid), lines)
            return True
        except Exception:
            return False

    def save_run(self, sid: Optional[str], result: Any) -> Optional[Dict[str, Any]]:
        """Write a run's artifacts into `<sid>/runs/<run_id>/` instead of a
        temp directory, and the typed object beside them.

        🔴 THIS IS WHAT MAKES A PAST ANALYSIS SURVIVE AT ALL. The four
        artifacts are the product; written to `tempfile.mkdtemp` they are gone
        the moment the session is collected, so "reopen it next week" could
        show a report that no longer exists.

        `run_id` is the configuration's own hash plus an ordinal, so the
        directory name says which configuration produced it.
        """
        if not self.enabled or not sid or result is None:
            return None
        try:
            base = (getattr(result, "config_sha256", "") or "nohash")[:12]
            n = 1 + len([p for p in (self.dir(sid) / "runs").glob(f"{base}-*")
                         if p.is_dir()]) if (self.dir(sid) / "runs").exists() else 1
            run_id = f"{base}-{n}"
            d = self.run_dir(sid, run_id)
            d.mkdir(parents=True, exist_ok=True)
            paths = result.save(str(d))
            _write_atomic(d / "run.json",
                          json.dumps(run_to_dict(result), indent=1,
                                     ensure_ascii=False, default=str))
            for f in d.iterdir():
                try:
                    os.chmod(f, 0o600)
                except OSError:
                    pass
            return {"run_id": run_id, "dir": str(d), "paths": paths}
        except Exception:
            return None

    def load_run(self, sid: str, run_id: str) -> Optional[Any]:
        """The typed RunResult of a past run, rebuilt from its own directory."""
        d = self.run_dir(sid, run_id)
        try:
            meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
            report = (d / "report.md").read_text(encoding="utf-8")
            cands = json.loads((d / "candidates.json").read_text(encoding="utf-8"))
        except Exception:
            return None
        try:
            return run_from_dict(meta, report, cands)
        except Exception:
            return None

    def runs_of(self, sid: str) -> List[str]:
        """Run ids, oldest first -- the order `Session.results` is in."""
        d = self.dir(sid) / "runs"
        if not d.exists():
            return []
        out = [p for p in d.iterdir() if p.is_dir() and (p / "run.json").exists()]
        out.sort(key=lambda p: p.stat().st_mtime)
        return [p.name for p in out]

    # ----------------------------------------------------------------- read
    def load(self, sid: str) -> LoadedSession:
        """Reopen a session, re-verifying rather than trusting."""
        problems: List[str] = []
        if not self.enabled:
            return LoadedSession(None, problems=["sessions are not kept in this deployment"])
        try:
            raw = json.loads(self._snapshot(sid).read_text(encoding="utf-8"))
        except Exception:
            return LoadedSession(None, problems=["this analysis could not be read"],
                                 read_only=True)
        if int(raw.get("schema_version") or 0) > SCHEMA_VERSION:
            # 🔴 a newer schema opens READ-ONLY with a note rather than being
            # guessed at: a field this build does not know about may be the one
            # that made the run admissible
            return LoadedSession(None, read_only=True, problems=[
                "this analysis was saved by a newer version of BregSurv and is "
                "shown read-only"])
        try:
            session = session_from_dict(raw)
        except Exception as exc:
            return LoadedSession(None, read_only=True, problems=[
                f"this analysis could not be restored ({type(exc).__name__})"])
        session = replace(session, sid=sid)

        # the runs, oldest first, rebuilt from their own directories
        rids = self.runs_of(sid)
        results = [r for r in (self.load_run(sid, rid) for rid in rids)
                   if r is not None]
        if results:
            # `temp` is restored to the run DIRECTORIES, not to temp files: the
            # report PDF and a redrawn Kaplan-Meier curve are written beside
            # the artifacts of the last run (`session.temp[-1]`), so without
            # this a reopened analysis could show its result and not print it.
            # Nothing under the store root is ever purged (see app._purge).
            session = replace(session, results=results, result=results[-1],
                              temp=[str(self.run_dir(sid, r)) for r in rids])

        # --- the cohort file, re-fingerprinted ---------------------------
        read_only, changed = False, False
        path = session.data_path
        if not path or not Path(path).exists():
            read_only = True
            problems.append("the data file this analysis used is no longer on this "
                            "machine, so nothing further can be fitted; the "
                            "conversation and the results are here")
        else:
            try:
                now = _pipe_mod._fingerprint(path)["sha256"]
            except Exception:
                now = None
            if now and session.data_sha256 and now != session.data_sha256:
                changed = True
                read_only = True
                problems.append(
                    "the data file has changed since this analysis was saved, so "
                    "this analysis is shown as it was and nothing further can be "
                    "fitted from it; drop the new file into the message box to "
                    "analyse it")
                session = _as_proposal(session, now)

        # --- the action log, which a `quoted` role depends on ------------
        events = _read_lines(self._events(sid))
        if not events and session.declaration is not None:
            # 🔴 Decision 3: downgrade, do not fail closed. `guards.audit`
            # checks a `quoted` role against the analyst's own words; with the
            # log gone there are no words to check it against. Refusing to run
            # would leave a message nobody can act on, so the role keeps its
            # value and loses its backing -- it is re-asked like any role the
            # analyst has not justified.
            session = _downgrade_quoted(session)
            problems.append("the record of what you wrote in this analysis is "
                            "missing, so the roles you quoted are shown as "
                            "answers rather than quotations")

        msgs = [[m.get("user"), m.get("bot")] for m in _read_lines(self._messages(sid))]
        return LoadedSession(session, messages=msgs, problems=problems,
                             read_only=read_only, data_changed=changed)

    def list(self, limit: int = 50) -> List[SessionCard]:
        """The sidebar, newest first. Reads the index, and falls back to the
        directories themselves if the index is missing or stale -- the index is
        a cache, never the only record that a session exists."""
        if not self.enabled or not self.root.exists():
            return []
        idx = {}
        try:
            idx = json.loads(self._index().read_text(encoding="utf-8")).get("sessions", {})
        except Exception:
            idx = {}
        sids = [p.name for p in self.root.iterdir()
                if p.is_dir() and (p / "session.json").exists()]
        for sid in sids:
            if sid not in idx:
                row = self._row_from_disk(sid)
                if row:
                    idx[sid] = row
        rows = [(sid, r) for sid, r in idx.items() if sid in set(sids)]
        # the sid is itself sortable by creation time, so it breaks a tie in
        # `updated` rather than leaving the order to the dict
        rows.sort(key=lambda kv: (str(kv[1].get("updated") or ""), kv[0]), reverse=True)
        out = []
        for sid, r in rows[:limit]:
            out.append(SessionCard(
                sid=sid, title=str(r.get("title") or sid),
                cohort=str(r.get("cohort") or ""), design=str(r.get("design") or ""),
                external=str(r.get("external") or ""), n_runs=int(r.get("n_runs") or 0),
                selected=r.get("selected"), updated=str(r.get("updated") or ""),
                read_only=bool(r.get("read_only"))))
        return out

    def _row_from_disk(self, sid: str) -> Optional[Dict[str, Any]]:
        try:
            raw = json.loads(self._snapshot(sid).read_text(encoding="utf-8"))
        except Exception:
            return None
        s = None
        try:
            s = session_from_dict(raw)
        except Exception:
            pass
        n_runs = len(self.runs_of(sid))
        return {"title": (title_for(s) if s is not None else sid),
                "cohort": Path(str(raw.get("data_path") or "")).name,
                "design": _design_of(s) if s is not None else "",
                "external": (s.external_line() if s is not None else ""),
                "n_runs": n_runs, "selected": None,
                "updated": _dt.datetime.fromtimestamp(
                    self._snapshot(sid).stat().st_mtime).isoformat(timespec="seconds")}

    def _touch_index(self, sid: str, session: Session) -> None:
        d = {}
        try:
            d = json.loads(self._index().read_text(encoding="utf-8"))
        except Exception:
            d = {}
        sel = _selected_of(session)
        rows = d.setdefault("sessions", {})
        prev = rows.get(sid) or {}
        rows[sid] = {
            "title": prev.get("title") or title_for(session, sel),
            "cohort": Path(session.data_path).name if session.data_path else "",
            "design": _design_of(session),
            "external": session.external_line(),
            "n_runs": max(len(session.results), int(prev.get("n_runs") or 0)),
            "selected": sel or prev.get("selected"),
            "updated": _now(),
        }
        # the title gains the selected member once there is one, and then stays
        if sel and "·" in rows[sid]["title"] and sel not in rows[sid]["title"]:
            rows[sid]["title"] = title_for(session, sel)
        _write_atomic(self._index(), json.dumps(d, indent=1, ensure_ascii=False))

    # --------------------------------------------------------------- delete
    def delete(self, sid: str) -> bool:
        """🔴 Only when asked. Decision 2: unlimited retention plus an explicit
        delete -- removing someone's analysis to save disk is worse than the
        disk. `BREGSURV_SESSIONS_KEEP=<n>` exists and is unset by default."""
        if not self.enabled or not sid:
            return False
        try:
            d = self.dir(sid)
            if d.exists() and d.parent == self.root:
                shutil.rmtree(d, ignore_errors=True)
            idx = {}
            try:
                idx = json.loads(self._index().read_text(encoding="utf-8"))
            except Exception:
                idx = {}
            idx.get("sessions", {}).pop(sid, None)
            _write_atomic(self._index(), json.dumps(idx, indent=1, ensure_ascii=False))
            return True
        except Exception:
            return False

    def prune(self) -> int:
        """Apply `BREGSURV_SESSIONS_KEEP` if it is set. Unset means keep all."""
        keep = os.environ.get("BREGSURV_SESSIONS_KEEP", "").strip()
        if not self.enabled or not keep.isdigit():
            return 0
        rows = self.list(limit=10_000)
        gone = 0
        for card in rows[int(keep):]:
            gone += 1 if self.delete(card.sid) else 0
        return gone

    # -------------------------------------------------------------- rebuild
    def rebuild(self, sid: str) -> bool:
        """Recompute `session.json` from `events.jsonl`, which is what makes
        the snapshot a fold rather than a second authority. The events carry
        the transitions and the analyst's messages; the fields they do not
        carry are kept from the existing snapshot."""
        if not self.enabled:
            return False
        events = _read_lines(self._events(sid))
        if not events:
            return False
        try:
            raw = json.loads(self._snapshot(sid).read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        turns = sum(1 for e in events if e.get("turn"))
        questions = sum(1 for e in events if e.get("asked"))
        raw["actions"] = [{k: v for k, v in e.items() if k != "at"} for e in events]
        raw["turns"] = turns
        raw["questions"] = questions
        raw["schema_version"] = SCHEMA_VERSION
        try:
            _write_atomic(self._snapshot(sid),
                          json.dumps(raw, indent=1, ensure_ascii=False, default=str))
            return True
        except Exception:
            return False


# --------------------------------------------------------------- resume rules
def _design_of(session: Optional[Session]) -> str:
    d = getattr(session, "declaration", None)
    if d is not None:
        try:
            return str(d.design)
        except Exception:
            return ""
    return ""


def _plain(x: Any) -> Any:
    """What goes into messages.jsonl: text as text, a file as its path."""
    if isinstance(x, (tuple, list)) and x and isinstance(x[0], str):
        return {"file": x[0]}
    return x


def _as_proposal(session: Session, new_sha: str) -> Session:
    """🔴 THE DECLARATION SURVIVES A CHANGED FILE, THE VERIFICATION DOES NOT.

    What the analyst said about their columns is still worth showing -- it is
    why remembering is worth anything at all. What the harness checked against
    the old bytes is worthless, so the verification goes, every source becomes
    `remembered`, and the profile goes with it: nothing can be fitted from a
    profile taken of bytes that are no longer there.

    ⚠️ The session is then READ-ONLY and the analyst is told to drop the new
    file in, which starts a fresh analysis. Re-profiling in place and carrying
    the old declaration forward as a proposal is the better interaction and is
    deliberately NOT built: the release reached this session by value and its
    file is not recorded, so a re-profile would silently lose the linkage. A
    reopened analysis that quietly borrows from nothing is worse than one that
    says it cannot continue.
    """
    decl = session.declaration
    when = _dt.date.today().isoformat()
    if decl is not None:
        src = {k: f"remembered: you declared this for this file on {when}"
               for k in (decl.sources or {})}
        decl = replace(decl, sources=src)
    return replace(session, declaration=decl, verification=None,
                   result=None, results=[], data_sha256=new_sha,
                   profile=None)


def _downgrade_quoted(session: Session) -> Session:
    """A `quoted` source with no surviving message behind it becomes `asked`."""
    decl = session.declaration
    if decl is None:
        return session
    src = {k: ("asked" if str(v).startswith(("quoted", "described")) else v)
           for k, v in (decl.sources or {}).items()}
    return replace(session, declaration=replace(decl, sources=src),
                   verification=None)
