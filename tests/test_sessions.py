#!/usr/bin/env python3
"""Sessions (persistence and resume): the typed round trip, the
store, the three file states of a resume, the `quoted` downgrade, the run
directory replacing `tempfile.mkdtemp`, and the sidebar.

No model anywhere -- persistence involves none, which is the point. Sections F
and G need gradio and Rscript (they run the app end to end on a COPY of the
demo cohort with the store pointed at a temp directory) and are skipped
without them.

    python mcp/test_sessions.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  -- {note}" if note else ""))


def hdr(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def _decl(**kw):
    from bregsurv_agent.declaration import Declaration
    base = dict(time_col="followup_days", event_col="died", event_value="1",
                covariates=["age", "bmi"], source="reply",
                covariates_time_zero="yes",
                sources={"time": "quoted: followup_days",
                         "event": "quoted: died",
                         "event_value": "inferred: the only other level",
                         "covariates": "described: adjust for age and bmi",
                         "time_zero": "checkbox"})
    base.update(kw)
    return Declaration(**base)


def _ver(admissible=True):
    from bregsurv_agent.declaration import Verification
    return Verification(admissible=admissible, card=["  patients  260", "  events  164"],
                        refusals=[] if admissible else [{"code": "degenerate_outcome",
                                                         "message": "no events", "detail": None}],
                        advisories=[], gate={"summary": {"n": 260}})


def _ext():
    from bregsurv_agent.external import ExternalObject
    return ExternalObject(form="coefficients", scale="log_hazard_ratio",
                          terms={"age": 0.03, "bmi": -0.01},
                          provenance={"file": "registry_coefficients.csv",
                                      "format": "csv", "n_tables": 1},
                          linkage={"matched": ["age", "bmi"], "unmatched": []})


def _session(data_path, sha):
    from bregsurv_agent.state import Session
    s = Session().with_profile(
        data_path, "cohort", {"n_rows": 260, "n_columns": 12,
                              "columns": [{"name": "followup_days"}, {"name": "died"},
                                          {"name": "age"}, {"name": "bmi"}]},
        external=_ext(), data_sha256=sha)
    s = s.start_turn("followup_days is the time, died is the event, adjust for age and bmi")
    s = s.with_declaration(_decl(), _ver())
    return s


def main() -> int:
    from bregsurv_agent import sessions
    from bregsurv_agent.state import Phase, Session

    work = Path(tempfile.mkdtemp(prefix="bregsurv_sessions_test_"))
    data = work / "cohort.csv"
    data.write_text("followup_days,died,age,bmi\n10,1,50,25\n20,0,60,30\n", encoding="utf-8")
    from bregsurv_agent import pipeline
    sha = pipeline._fingerprint(str(data))["sha256"]

    try:
        # -------------------------------------------- A. the typed round trip
        hdr("A. every persisted object round-trips through plain JSON")
        d = _decl()
        back = sessions.decl_from_dict(json.loads(json.dumps(sessions.decl_to_dict(d))))
        check(back == d, "Declaration round-trips", str(back)[:120])
        v = _ver()
        check(sessions.ver_from_dict(json.loads(json.dumps(sessions.ver_to_dict(v)))) == v,
              "Verification round-trips")
        e = _ext()
        back = sessions.ext_from_dict(json.loads(json.dumps(sessions.ext_to_dict(e))))
        check(back == e, "ExternalObject round-trips")
        s = _session(str(data), sha)
        raw = json.loads(json.dumps(sessions.session_to_dict(s), default=str))
        s2 = sessions.session_from_dict(raw)
        check(s2.declaration == s.declaration and s2.verification == s.verification
              and s2.external == s.external and s2.profile == s.profile
              and s2.actions == s.actions and s2.turns == s.turns,
              "Session round-trips field by field")
        check(s2.phase is Phase.VERIFIED, "the restored phase is DERIVED and agrees",
              str(s2.phase))
        check("pickle" not in Path(sessions.__file__).read_text(encoding="utf-8").lower()
              .replace("no pickle", "").replace("not be a code path", ""),
              "no pickle anywhere in the module")
        # a field this build does not know about must not stop a session opening
        raw_future = dict(raw, some_future_field="x")
        try:
            sessions.session_from_dict(raw_future)
            check(True, "an unknown field is dropped rather than raising")
        except Exception as exc:
            check(False, "an unknown field is dropped rather than raising", repr(exc))

        # ------------------------------------------------- B. the store, basics
        hdr("B. the store: create, save, list, load, delete")
        root = work / "store"
        st = sessions.SessionStore(path=str(root), enabled=True, keep_data=False)
        sid, s = st.adopt(s)
        check(sid is not None and s.sid == sid, "adopt returns an id and stamps the session", str(sid))
        check((root / sid / "session.json").exists(), "session.json written")
        check((root / sid / "events.jsonl").exists(), "events.jsonl written")
        check(oct(os.stat(root / sid).st_mode)[-3:] == "700", "the session directory is 0700",
              oct(os.stat(root / sid).st_mode)[-3:])
        check(oct(os.stat(root / sid / "session.json").st_mode)[-3:] == "600",
              "session.json is 0600")
        st.save_messages(sid, [["hello", "I have loaded your cohort."],
                               [None, ("/nonexistent/km_curve.png",)]])
        cards = st.list()
        check(len(cards) == 1 and cards[0].sid == sid, "list() returns the one session")
        check(cards[0].title.startswith("cohort ·"),
              "the title is deterministic, cohort file then date", cards[0].title)
        check("full cohort" in cards[0].design, "the card carries the design", cards[0].design)
        L = st.load(sid)
        check(L.session is not None and not L.read_only and not L.problems,
              "an unchanged file restores fully", str(L.problems))
        check(L.session.declaration == s.declaration,
              "the declaration comes back exactly")
        check([m[0] for m in L.messages] == ["hello", None],
              "the conversation comes back", str(L.messages))
        check(L.messages[1][1] == {"file": "/nonexistent/km_curve.png"},
              "a file in the chat is stored as its path", str(L.messages[1][1]))

        # the ordering and the limit
        others = []
        for i in range(3):
            s_i = _session(str(data), sha)
            sid_i, s_i = st.adopt(s_i)
            others.append(sid_i)
        cards = st.list(limit=2)
        check(len(cards) == 2, "list() honours the limit", str(len(cards)))
        check(cards[0].sid == others[-1], "newest first", f"{cards[0].sid} vs {others[-1]}")
        check(len({sid, *others}) == 4, "ids do not collide under rapid creation")
        for sid_i in others:
            st.delete(sid_i)
        check(len(st.list()) == 1 and not (root / others[0]).exists(),
              "delete removes the directory and the index row")

        # -------------------------------------- C. the three states of a resume
        hdr("C. resume RE-VERIFIES: identical, missing, changed")
        # (i) identical -- covered in B.
        # (ii) the file is gone
        moved = work / "cohort_moved.csv"
        shutil.move(str(data), str(moved))
        L = st.load(sid)
        check(L.read_only and any("no longer on this machine" in p for p in L.problems),
              "a missing data file opens READ-ONLY with a reason", str(L.problems))
        check(L.session is not None and L.session.declaration is not None,
              "and the conversation and the declaration are still there")
        shutil.move(str(moved), str(data))
        # (iii) the bytes changed
        data.write_text("followup_days,died,age,bmi\n10,1,50,25\n30,1,70,22\n", encoding="utf-8")
        new_sha = pipeline._fingerprint(str(data))["sha256"]
        L = st.load(sid)
        check(L.data_changed and any("has changed" in p for p in L.problems),
              "a changed data file is reported", str(L.problems))
        check(L.read_only, "and the session is read-only, so the stale "
                           "verification can never reach a fit")
        check(L.session.verification is None,
              "🔴 the restored VERIFICATION is dropped")
        check(L.session.declaration is not None,
              "the declaration survives as a proposal")
        check(all(str(v).startswith("remembered:") for v in L.session.declaration.sources.values()),
              "every source became `remembered`", str(L.session.declaration.sources))
        check(L.session.profile is None and L.session.phase is Phase.EMPTY,
              "the profile is dropped, so the gate must run again",
              str(L.session.phase))
        check(L.session.data_sha256 == new_sha, "the new fingerprint is the one recorded")

        # ------------------------------------------ D. the `quoted` downgrade
        hdr("D. a `quoted` role never survives without the message that backs it")
        data.write_text("followup_days,died,age,bmi\n10,1,50,25\n20,0,60,30\n", encoding="utf-8")
        s3 = _session(str(data), sha)
        sid3, s3 = st.adopt(s3)
        (root / sid3 / "events.jsonl").unlink()
        L = st.load(sid3)
        src = L.session.declaration.sources
        check(src["time"] == "asked" and src["event"] == "asked",
              "a `quoted` source is downgraded to `asked`", str(src))
        check(src["covariates"] == "asked", "so is `described`", str(src))
        check(src["event_value"].startswith("inferred"),
              "an `inferred` source is untouched -- the data backs it, not a message")
        check(L.session.verification is None,
              "the verification is dropped with it, so the gate runs again")
        check(any("missing" in p for p in L.problems), "and the analyst is told",
              str(L.problems))

        # ------------------------------------------- E. the switches and rebuild
        hdr("E. demo writes nothing; a corrupt snapshot opens read-only; rebuild")
        saved_env = dict(os.environ)
        try:
            os.environ["DEPLOYMENT_MODE"] = "demo"
            off = sessions.SessionStore(path=str(work / "never"))
            check(not off.enabled, "DEPLOYMENT_MODE=demo turns the store OFF")
            check(off.new() is None and off.save("x", s) is False and off.list() == [],
                  "and every method is a safe no-op")
            check(not (work / "never").exists(), "🔴 a demo deployment writes NOTHING")
            os.environ["DEPLOYMENT_MODE"] = "local"
            os.environ["BREGSURV_SESSIONS"] = "off"
            check(not sessions.SessionStore().enabled, "BREGSURV_SESSIONS=off turns it off")
            os.environ["BREGSURV_SESSIONS"] = str(work / "elsewhere")
            check(sessions.SessionStore().root == work / "elsewhere",
                  "a path in BREGSURV_SESSIONS overrides the location")
        finally:
            os.environ.clear(); os.environ.update(saved_env)

        bad = st.dir(sid3) / "session.json"
        good = bad.read_text(encoding="utf-8")
        bad.write_text("{not json", encoding="utf-8")
        L = st.load(sid3)
        check(L.session is None and L.read_only and L.problems,
              "a corrupt snapshot opens read-only instead of raising")
        bad.write_text(json.dumps(dict(json.loads(good), schema_version=999)), encoding="utf-8")
        L = st.load(sid3)
        check(L.read_only and any("newer version" in p for p in L.problems),
              "a newer schema_version opens read-only rather than being guessed at",
              str(L.problems))
        bad.write_text(good, encoding="utf-8")

        # an interrupted write leaves the previous snapshot intact
        stale = st.dir(sid) / "session.json.tmp"
        stale.write_text("{half", encoding="utf-8")
        check(st.load(sid).session is not None,
              "a leftover .tmp does not shadow the snapshot")
        stale.unlink()

        # rebuild: the snapshot is a FOLD of the events, not a second authority
        s4 = _session(str(data), sha)
        sid4, s4 = st.adopt(s4)
        s4 = s4.start_turn("and use the registry coefficients")
        st.sync_events(sid4, s4.actions)
        st.save(sid4, s4)
        n_before = len(json.loads(st._snapshot(sid4).read_text())["actions"])
        st._snapshot(sid4).write_text(
            json.dumps(dict(json.loads(st._snapshot(sid4).read_text()), actions=[], turns=0)),
            encoding="utf-8")
        check(st.rebuild(sid4), "rebuild() runs")
        got = json.loads(st._snapshot(sid4).read_text())
        check(len(got["actions"]) == n_before and got["turns"] == 2,
              "the fold is recomputed from events.jsonl",
              f"{len(got['actions'])} actions, {got['turns']} turns")
        check([a.get("message") for a in got["actions"] if a.get("message")]
              == [a.get("message") for a in s4.actions if a.get("message")],
              "including the analyst's own words, verbatim")

        # keep_data: the file travels with the session
        st2 = sessions.SessionStore(path=str(work / "store2"), enabled=True, keep_data=True)
        s5 = _session(str(data), sha)
        sid5, s5 = st2.adopt(s5)
        check(Path(s5.data_path).parent == st2.dir(sid5) / "data",
              "with keep_data the cohort is copied into the session", s5.data_path)
        check(Path(s5.data_path).name == Path(str(data)).name,
              "under its own name, so data_expr still addresses the table")
        check(st2.load(sid5).session is not None and not st2.load(sid5).read_only,
              "so the session resumes even once the original upload is gone")

        # ------------------------------------------------- F. the app, end to end
        hdr("F. the demo: the sidebar, the run directory, the purge")
        try:
            import gradio  # noqa: F401
            from bregsurv_agent.rbridge import _find_rscript
            have_app = _find_rscript() is not None
        except Exception:
            have_app = False
        if not have_app:
            print("  SKIP  sections F and G need gradio and Rscript")
        else:
            saved_env = dict(os.environ)
            appwork = Path(tempfile.mkdtemp(prefix="bregsurv_app_sessions_"))
            try:
                os.environ["DEPLOYMENT_MODE"] = "local"
                os.environ["BREGSURV_SESSIONS"] = str(appwork / "sessions")
                os.environ["BREGSURV_MEMORY"] = "off"
                os.environ.pop("OPENAI_API_KEY", None)
                for m in [k for k in list(sys.modules) if k == "app"]:
                    del sys.modules[m]
                import app as A
                check(A.STORE.enabled and A.STORE.root == appwork / "sessions",
                      "the app's store reads the environment", str(A.STORE.root))
                check("~/.bregsurv/sessions" in A._banner(),
                      "the local banner says where analyses are kept")

                cohort = appwork / "my_cohort.csv"
                shutil.copy(A.DEMO_COHORT, cohort)
                h, sess, *_ = A.start_session(str(cohort), str(A.DEMO_COEFS))
                check(sess is not None and sess.sid is None,
                      "profiling alone does NOT create a stored session")
                sess = A._adopt(sess)
                check(sess.sid is not None, "the first message adopts it", str(sess.sid))
                check(Path(sess.data_path).parent == A.STORE.dir(sess.sid) / "data",
                      "and the uploaded cohort is kept with it", sess.data_path)
                A._persist(sess, [["my request", "my reply"]])
                cards = A.STORE.list()
                check(len(cards) == 1 and cards[0].sid == sess.sid,
                      "it appears in the sidebar")
                lab = A._card_label(cards[0])
                check("my_cohort" in lab and len(lab) <= 66,
                      "the row is labelled by the cohort file and fits the column", lab)
                ups = A._sidebar()
                check(len(ups) == 2 * A.MAX_CARDS, "the sidebar returns one update per control")
                check(ups[0]["visible"] is True and ups[1]["visible"] is False,
                      "the first row is shown and the rest hidden")

                # the purge must not touch what the store is keeping
                sess_t = replace(sess, temp=list(sess.temp)
                                 + [str(A.STORE.dir(sess.sid) / "data" / cohort.name)])
                A._purge(sess_t)
                check(Path(sess.data_path).exists(),
                      "🔴 _purge leaves everything under the store root alone")

                # reopening: the conversation and the state, no model
                n_calls = len(A.boundary.CALLS)
                out = A.open_session(0)
                hist, _box, restored = out[0], out[1], out[2]
                check(len(A.boundary.CALLS) == n_calls,
                      "🔴 reopening a session calls NO model")
                check(restored is not None and restored.sid == sess.sid,
                      "the session is the one that was clicked")
                check(hist["value"][0][0] == "my request",
                      "the conversation is back on the screen", str(hist["value"])[:120])

                # a fit is refused outright once the file is gone, in words.
                # A fully declared session, so the refusal under test is the
                # file guard and not the "tell me the columns first" one.
                gone = _session(str(appwork / "vanished.csv"), "nosuchsha")
                h2, *_ = A.run_analysis(gone, True, "", "", "", [])
                check("no longer on this machine" in h2[-1][1],
                      "a fit on a vanished file is refused in plain words, not by R",
                      str(h2[-1][1])[:100])

                # the two-click delete
                sb = A.delete_session(0, None)
                check(sb[-1] == sess.sid and sb[A.MAX_CARDS]["value"] == "Delete?",
                      "one click arms the row", str(sb[A.MAX_CARDS]))
                check(len(A.STORE.list()) == 1, "and deletes nothing")
                sb = A.delete_session(0, sess.sid)
                check(len(A.STORE.list()) == 0 and sb[-1] is None,
                      "the second click deletes it")

                # 🔴 a refresh DISARMS: repainting the labels without clearing
                # arm_state would leave the row reading as unarmed while the
                # next single click deleted it
                rs = A._sidebar_reset()
                check(len(rs) == 2 * A.MAX_CARDS + 1 and rs[-1] is None,
                      "a sidebar refresh resets the armed row as well as its label",
                      str(len(rs)))
                check(all(u["value"] != "Delete?" for u in rs[A.MAX_CARDS:2 * A.MAX_CARDS]
                          if isinstance(u, dict) and "value" in u),
                      "and no row is left showing Delete?")

                # the handlers' return lengths match the outputs they are bound
                # to. A mismatch breaks the page only when the control is
                # clicked, which no other assertion here would reach.
                fns = {str(getattr(f, "name", "") or getattr(getattr(f, "fn", None), "__name__", "")): f
                       for f in getattr(A.demo, "fns", {}).values()}
                arities = []
                for f in getattr(A.demo, "fns", {}).values():
                    nm = getattr(getattr(f, "fn", None), "__name__", "")
                    outs = len(getattr(f, "outputs", []) or [])
                    if nm in ("_sidebar_reset", "<lambda>", "open_session", "delete_session"):
                        arities.append((nm, outs))
                want = {2 * A.MAX_CARDS + 1, 6 + 2 * A.MAX_CARDS + 1}
                check(arities and all(o in want or o <= 6 for _, o in arities),
                      "every sidebar binding's output count is one the handler returns",
                      str(arities))
                check(len(A.open_session(99)) == 6 + 2 * A.MAX_CARDS + 1,
                      "open_session returns the full width even when the row is empty",
                      str(len(A.open_session(99))))
                check(len(A.delete_session(99, None)) == 2 * A.MAX_CARDS + 1,
                      "delete_session too")
            finally:
                os.environ.clear(); os.environ.update(saved_env)
                shutil.rmtree(appwork, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
