#!/usr/bin/env python3
"""Components 8, 9 and 11: the method notes and their retrieval (no model),
the guard audit that a run must pass, and the report section that discloses
every model call. Section D runs the app with a fake model and needs R and
gradio; it is skipped without them.

    python mcp/test_guards.py
"""
from __future__ import annotations

import json
import re
import sys
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


def main() -> int:
    from bregsurv_agent import guards, knowledge, report_v3, intent
    from bregsurv_agent.state import Session
    from bregsurv_agent.declaration import Declaration, Verification

    # ------------------------------------------------------------ A. knowledge
    hdr("A. method notes: hand-written, digit-free, retrieved by keyword, no model")
    ns = knowledge.notes()
    check(len(ns) >= 7 and len({n.id for n in ns}) == len(ns), f"{len(ns)} notes with unique ids")
    check(all(n.keywords and n.body for n in ns), "every note has keywords and a body")
    check(not any(re.search(r"\d", n.body) for n in ns),
          "no note body contains a digit (the same rule as the model's prose)")
    got = [n.id for n in knowledge.retrieve("Why was that model chosen? What is the held-out loss?")]
    check(got and got[0] == "cross-validation", "a selection question retrieves the cross-validation note", str(got))
    got = [n.id for n in knowledge.retrieve("What does the weight eta mean and how is it tuned?")]
    check(got and got[0] == "how-much-to-borrow", "a question about the weight retrieves how-much-to-borrow", str(got))
    got = [n.id for n in knowledge.retrieve("Can it handle competing risks or draw a plot?")]
    check(got and got[0] == "what-is-not-done", "scope questions retrieve what-is-not-done", str(got))
    check(knowledge.retrieve("hello there") == [], "no keyword, no note")
    check(knowledge.answer_method("hello there", "FALLBACK") == "FALLBACK",
          "with no match the fixed fallback is returned")
    ans = knowledge.answer_method("how is the amount to borrow decided?", "FALLBACK")
    check("How much to borrow" in ans and "no language model wrote" in ans,
          "a match renders the note verbatim with its provenance line")
    d = knowledge.describe()
    check(d["n_notes"] == len(ns) and d["sha256"].startswith("sha256:"),
          "describe(): count and file hash for provenance")

    # ------------------------------------------------------------ B. the audit
    hdr("B. the guard audit: the five invariants, from the session alone")
    prof = {"columns": [{"name": c} for c in ("t", "d", "age", "bmi")],
            "eligible": {"time": ["t"], "event": ["d"], "covariate": ["age", "bmi"]}}
    decl = Declaration(time_col="t", event_col="d", event_value="1", covariates=["age", "bmi"],
                       source="model_extraction", covariates_time_zero="yes",
                       sources={"time": "quoted", "event": "quoted", "event_value": "quoted",
                                "covariates": "quoted",
                                "time_zero": "checkbox: every covariate known at the start of follow-up"})
    ok_v = Verification(True, ["ok"])
    good = (Session().with_profile("/x.csv", "D", prof)
            .start_turn("Time is t, the event is d coded 1; adjust for age and bmi.")
            .log(route="intent", plan=["propose_roles", "complete"])
            .take_calls([{"name": "intent", "raw_text": "{}"}, {"name": "role_extraction", "raw_text": "{}"}])
            .log(route="turn_calls", model_calls=2, budget=5)
            .with_declaration(decl, ok_v))
    check(guards.audit(good) == [], "a coherent session with every quoted name written passes", str(guards.audit(good)))
    liar = replace(good, declaration=replace(decl, covariates=["age", "bmi", "egfr"],
                                             sources=dict(decl.sources)))
    v = guards.audit(liar)
    check(any("quoted but the analyst never wrote 'egfr'" in x for x in v),
          "a quoted covariate the analyst never wrote is caught", str(v))
    desc_ok = replace(good, declaration=replace(decl, sources=dict(
        decl.sources, time='described: "Time is t"')))
    check(guards.audit(desc_ok) == [], "a described role whose phrase the analyst wrote passes")
    desc_bad = replace(good, declaration=replace(decl, sources=dict(
        decl.sources, time='described: "the observation window"')))
    check(any("described from a phrase the analyst never wrote" in x for x in guards.audit(desc_bad)),
          "a described role with a phrase the analyst never wrote is caught")
    odd = replace(good, declaration=replace(decl, sources=dict(decl.sources, time="guessed")))
    check(any("unrecognised source" in x for x in guards.audit(odd)), "an unrecognised source is caught")
    nosrc = replace(good, declaration=replace(decl, sources={}))
    check(any("without a recorded source" in x for x in guards.audit(nosrc)),
          "a role without a source is caught (model_extraction path)")
    badcall = replace(good, model_calls=good.model_calls + [{"name": "free_chat", "raw_text": "x"}])
    check(any("not one of the policies" in x for x in guards.audit(badcall)),
          "a model call outside the policies is caught")
    noraw = replace(good, model_calls=[{"name": "intent"}])
    check(any("no raw output recorded" in x for x in guards.audit(noraw)),
          "a call without its raw output is caught")
    over = good.log(route="turn_calls", model_calls=9, budget=5)
    check(any("budget" in x for x in guards.audit(over)), "a turn over budget is caught")
    alien = good.log(route="intent", plan=["fetch_the_internet"])
    check(any("not in the action set" in x for x in guards.audit(alien)), "an act outside the set is caught")
    incoherent = replace(good, result=object(), verification=Verification(False, ["no"]))
    check(any(x.startswith("state:") for x in guards.audit(incoherent)),
          "state incoherence (a result on a refused declaration) is caught")

    # ------------------------------------------------------------ C. section 7
    hdr("C. the report discloses every model call")
    sec = report_v3.render_model_use({})
    check(sec.startswith("## 7. How the language model was used") and "No language model was used" in sec,
          "with no model: one line saying so")
    sec = report_v3.render_model_use({"model": {
        "served_model": "qwen2.5-7b-awq", "weights_fingerprint": "sha256:abc",
        "peak_prompt_tokens": 476, "max_model_len": 32768,
        "policies": {"intent": {"sha256": "sha256:0011"}, "report_prose": {"sha256": "sha256:2233"}},
        "calls": [{"name": "intent", "prompt_tokens": 476, "completion_tokens": 278},
                  {"name": "report_prose", "prompt_tokens": 400, "completion_tokens": 272}]}})
    check("called 2 time(s)" in sec and "| 1 | typing the message | 476 | 278 | sha256:0011 |" in sec
          and "| 2 | writing the connective prose of this report | 400 | 272 | sha256:2233 |" in sec
          and "Peak prompt: 476 tokens of a 32768-token window" in sec and "qwen2.5-7b-awq (sha256:abc)" in sec,
          "with calls: one row per call with its purpose, tokens and policy hash; peak and model", sec[:200])

    # ------------------------------------------------------------ D. the app
    hdr("D. through the app: notes for a method question; the audit passes a real run and refuses a tampered one")
    try:
        import app
        from bregsurv_agent.rbridge import _find_rscript
        have = _find_rscript() is not None
    except Exception as exc:  # pragma: no cover
        app = None; have = False
        print(f"  SKIP  app import failed ({type(exc).__name__})")
    if app is not None and have:
        # a numbered run: no model at all -> section 7 says so, the audit passes
        h, s, *_ = app.start_session()
        h1, _, s1, cand, *_ = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) A\n6) yes",
                                                h, s, "", "", "")
        check(cand is not None and "## 7. How the language model was used" in s1.result.report
              and "No language model was used" in s1.result.report,
              "a numbered run's report carries section 7 and says no model was used")
        check((s1.result.provenance.get("session") or {}).get("guard_violations") == [],
              "provenance records an empty audit")
        # a method question with a fake model typing it -> the notes, no explain call
        class _Msg:
            content = None

        class _Choice:
            finish_reason = "stop"

            def __init__(self):
                self.message = _Msg()

        class _Usage:
            prompt_tokens = 300
            completion_tokens = 40

        class _Comp:
            def __init__(self):
                self.choices = [_Choice()]
                self.usage = _Usage()

        class _Fake:
            base_url = "http://localhost:1/v1"

            class models:
                @staticmethod
                def list():
                    class R:
                        data = []
                    return R()

            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        out = {"reasoning": "q", "intents": [
                            {"kind": "ask_about_method", "evidence": "how is the amount to borrow decided",
                             "external_form": None, "out_of_scope_reason": None}]}
                        c = _Comp()
                        c.choices[0].message.content = json.dumps(out)
                        return c

        app._client = lambda endpoint, api_key: _Fake()
        h2, _, s2, *r2 = app.submit_answer("Can you tell me how is the amount to borrow decided?",
                                           h1, s1, "http://localhost:1/v1", "fake", "")
        check(all(r is None for r in r2) and "How much to borrow" in h2[-1][1]
              and "no language model wrote" in h2[-1][1],
              "a method question is answered from the notes, nothing fitted", h2[-1][1][:120])
        notes_logged = [a for a in s2.actions if a.get("route") == "method_notes"]
        check(notes_logged and "how-much-to-borrow" in notes_logged[-1]["notes"],
              "the notes shown are in the action log")
        # tamper: mark a covariate quoted that the analyst never wrote -> refused
        # a FRESH session (the earlier one's log holds the numbered reply, which
        # names every column, so the audit would rightly find them written)
        _, s0, *_ = app.start_session()
        s3 = s0.start_turn("please run it again")   # names no column
        from bregsurv_agent.declaration import parse_reply, verify, complete
        comp = complete(s3.profile, {"time": "followup_days", "event": "died", "event_value": "1",
                                     "covariates": "A", "time_zero": "yes"}, None)
        decl3 = parse_reply(s3.profile, dict(comp.answers))
        decl3.sources = {"time": "quoted", "event": "reply", "event_value": "reply",
                         "covariates": "reply", "time_zero": "reply"}   # time 'quoted' but never written
        v3 = verify(s3.profile, decl3, s3.data_path, s3.data_expr, run_r=app._run_r)
        s3 = s3.with_declaration(decl3, v3)
        h3, _, s3b, cand3, *_ = app.run_analysis(s3, False, "", "", "", [])
        check(cand3 is None and "harness's own audit" in h3[-1][1]
              and "never wrote 'followup_days'" in h3[-1][1],
              "a session whose sources lie is refused before anything is fitted", h3[-1][1][:160])
        check(any(a.get("route") == "guard_audit" for a in s3b.actions),
              "the refusal is in the action log")
    else:
        print("  SKIP  section D needs gradio and Rscript")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
