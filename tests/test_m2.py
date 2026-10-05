#!/usr/bin/env python3
"""M2: several steps, several external releases, comparisons -- the multi-step
periphery over the same verified core. Sections C and D run the app with a
fake model (needs R and gradio) and are skipped without them.

    python mcp/test_m2.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
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
    from bregsurv_agent import boundary, intent, policy

    # ------------------------------------------------------------ A. M1 + the step validator
    hdr("A. the harness half: M1's new kinds, the step schema and validator")
    sch = intent.schema_for(["one_year.csv", "three_year.csv"])
    en = sch["properties"]["intents"]["items"]["properties"]["external_name"]
    check(en["anyOf"][0]["enum"] == ["one_year.csv", "three_year.csv"],
          "M1's external_name is an enum of the loaded releases")
    check(intent.schema_for([])["properties"]["intents"]["items"]["properties"]["external_name"]
          == {"type": "null"}, "with nothing loaded it is null-only")
    msg = ("Run it once with the one-year model and once with the three-year model, "
           "then tell me what changed.")
    raw = {"reasoning": "q", "steps": [
        {"act": "select_external", "external": "one_year.csv", "evidence": "once with the one-year model"},
        {"act": "run", "external": None, "evidence": "once with the one-year model"},
        {"act": "select_external", "external": "three_year.csv", "evidence": "once with the three-year model"},
        {"act": "run", "external": "three_year.csv", "evidence": "once with the three-year model"},
        {"act": "compare_runs", "external": None, "evidence": "tell me what changed"}]}
    steps = boundary.validate_steps(msg, raw, ["one_year.csv", "three_year.csv"], 0)
    check([s["act"] for s in steps] == ["select_external", "run", "select_external", "run", "compare_runs"]
          and steps[3]["external"] is None,
          "a well-formed plan is kept; a stray file name on a run step is cleared", str(steps))
    bad = dict(raw, steps=raw["steps"][:1] + [{"act": "run", "external": None, "evidence": "words not in the message"}] + raw["steps"][2:])
    check([s["act"] for s in boundary.validate_steps(msg, bad, ["one_year.csv", "three_year.csv"], 0)]
          == ["select_external"],
          "the list is cut at the first step whose evidence is not in the message")
    check(boundary.validate_steps(msg, {"reasoning": "q", "steps": [
              {"act": "compare_runs", "external": None, "evidence": "tell me what changed"}]},
              ["one_year.csv"], 1) == [],
          "a comparison with fewer than two runs by then is cut")
    check(boundary.validate_steps(msg, {"reasoning": "q", "steps": [
              {"act": "select_external", "external": "five_year.csv", "evidence": "once with the one-year model"}]},
              ["one_year.csv"], 0) == [],
          "a file name that is not loaded is cut")
    check(boundary.validate_steps(msg, {"reasoning": "q", "steps": [
              {"act": "fetch_data", "external": None, "evidence": "Run it"}]}, [], 0) == [],
          "an act outside the enum is cut")
    # a loaded file named on a run step is a selection the model did not spell
    # out (the 2026-09-11 Qwen2.5 plan: run(A), run(B), compare)
    terse = boundary.validate_steps(msg, {"reasoning": "q", "steps": [
        {"act": "run", "external": "one_year.csv", "evidence": "once with the one-year model"},
        {"act": "run", "external": "three_year.csv", "evidence": "once with the three-year model"},
        {"act": "compare_runs", "external": None, "evidence": "tell me what changed"}]},
        ["one_year.csv", "three_year.csv"], 0)
    check([(t["act"], t["external"]) for t in terse]
          == [("select_external", "one_year.csv"), ("run", None),
              ("select_external", "three_year.csv"), ("run", None), ("compare_runs", None)],
          "run(A), run(B), compare expands to select A, run, select B, run, compare", str(terse))
    check(boundary.validate_steps(msg, {"reasoning": "q", "steps": [
              {"act": "run", "external": "five_year.csv", "evidence": "once with the one-year model"}]},
              ["one_year.csv"], 0) == [],
          "a run naming a file that is not loaded is cut")
    check(len(boundary.validate_steps(msg, {"reasoning": "q", "steps": [
              {"act": "run", "external": f, "evidence": "once with the one-year model"}
              for f in ["one_year.csv", "three_year.csv"] * 3]},
              ["one_year.csv", "three_year.csv"], 0)) == boundary.MAX_STEPS,
          "the expansion never exceeds MAX_STEPS")
    check(boundary.advice_problem("The event column takes three values; the library fits one event type, so nothing was fitted.") is None
          and boundary.advice_problem("Please specify only two levels in this column to proceed.") is not None
          and boundary.advice_problem("You could recode the column.") is not None,
          "a refusal explanation that advises is dropped; one that only explains is not")
    check("plan_steps" in policy.NAMES and "select A, run, select B, run, compare" in policy.load("plan_steps"),
          "the planning policy exists and names the canonical sequence")
    its = intent.validate(msg, {"reasoning": "q", "intents": [
        {"kind": "multi_step", "evidence": "Run it once with the one-year model",
         "external_form": None, "external_name": None, "out_of_scope_reason": None},
        {"kind": "select_external", "evidence": "the one-year model",
         "external_form": None, "external_name": "one_year.csv", "out_of_scope_reason": None}]})
    check([i.kind for i in intent.dispatch_order(its)] == ["multi_step", "select_external"]
          and its[1].external_name == "one_year.csv",
          "M1 validates the new kinds and keeps external_name on select_external")

    # the thinking allowance: the hidden reasoning must not eat the JSON's budget
    import os as _os

    class _Cap:
        seen: dict = {}
        base_url = "x"

        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    _Cap.seen = kw

                    class _M:
                        content = '{"reasoning": "q", "explanation": "no"}'

                    class _C:
                        finish_reason = "stop"; message = _M()

                    class _R:
                        choices = [_C()]; usage = None
                    return _R()

    for mode, extra in (("on", boundary.THINKING_ALLOWANCE), ("off", 0), ("", 0)):
        _os.environ["BREGSURV_THINKING"] = mode
        boundary._chat(_Cap(), "m", "s", "u", boundary.REFUSAL_SCHEMA, "refusal", max_tokens=350)
        got = _Cap.seen["max_tokens"]
        check(got == 350 + extra and boundary.CALLS[-1]["thinking_allowance"] == extra,
              f"BREGSURV_THINKING={mode!r}: max_tokens {got} (allowance {extra}) on the record")
    _os.environ.pop("BREGSURV_THINKING", None)
    boundary.call_log(clear=True)

    # ------------------------------------------------------------ B. compare, by the harness
    hdr("B. compare_runs: the harness compares two fitted objects")
    try:
        import app
        from bregsurv_agent.rbridge import _find_rscript
        have = _find_rscript() is not None
    except Exception as exc:  # pragma: no cover
        app = None; have = False
        print(f"  SKIP  app import failed ({type(exc).__name__})")
    if app is None or not have:
        print("  SKIP  sections B-D need gradio and Rscript")
        hdr(f"RESULT: {passed}/{passed + failed} passed")
        return 1 if failed else 0

    from bregsurv_agent import compare
    h, s, *_ = app.start_session()
    h1, _, s1, c1, *_ = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, bmi, egfr\n6) yes",
                                          h, s, "", "", "")
    check(c1 is not None, "run 1 (age, bmi, egfr)")
    h2, _, s2, c2, *_ = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, egfr\n6) yes",
                                          h1, s1, "", "", "")
    check(c2 is not None and len(s2.results) == 2, "run 2 (age, egfr); two results kept")
    cmp = compare.compare_runs(s2.results[0], s2.results[1], "run 1", "run 2")
    check("covariates" in cmp["text"] and "bmi" in cmp["text"] and not cmp["same_partition"],
          "the configuration difference (bmi dropped) is named and the losses declared not comparable")
    check(all(r["loss_a"] is not None or r["status_a"] != "ok" for r in cmp["candidates"])
          and cmp["selected"]["a"]["label"] and cmp["selected"]["b"]["label"],
          "every candidate's loss from both runs, and each run's selection")
    refs = compare.references(s2.results[0], s2.results[1])
    check("loss_best_a" in refs and "loss_best_b" in refs and "loss_best_delta" in refs
          and "same_selection" in refs, "the closed reference set for an explanation suffixes both runs")
    check("| bmi |" in cmp["text"], "coefficients side by side, variable by variable")

    # ------------------------------------------------------------ C. a second release, the same session
    hdr("C. add_external: a second release in the same session, selected by name")
    work = Path(tempfile.mkdtemp(prefix="bregsurv_m2_"))
    second = work / "three_year_model.csv"
    second.write_text("variable,coefficient\nage,0.3\negfr,-0.5\nbmi,-0.1\n", encoding="utf-8")
    hc, sc = app.add_external(str(second), s2, h2, "", "", "")
    check(len(sc.externals) == 2 and sc.external_name == "three_year_model.csv"
          and "Loaded external files" in hc[-1][1],
          "the second file is read, listed, and active", str(list(sc.externals)))
    first = list(sc.externals)[0]
    sc2 = sc.select_external(first)
    check(sc2.external_name == first, "select_external switches back by name")

    # ------------------------------------------------------------ D. the multi-step turn, fake model
    hdr("D. 'run with each and compare': M1 multi_step -> M2 plan -> five steps -> comparison")

    class _Msg:
        content = None

    class _Choice:
        finish_reason = "stop"

        def __init__(self):
            self.message = _Msg()

    class _Usage:
        prompt_tokens = 300
        completion_tokens = 60

    class _Comp:
        def __init__(self):
            self.choices = [_Choice()]
            self.usage = _Usage()

    names = list(sc.externals)
    msg_m = (f"Run the analysis once with {names[0]} and once with {names[1]}, "
             "then tell me what changed.")

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
                    name = kw["response_format"]["json_schema"]["name"]
                    if name == "intent":
                        out = {"reasoning": "q", "intents": [
                            {"kind": "multi_step", "evidence": f"once with {names[0]} and once with {names[1]}",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None}]}
                    elif name == "plan_steps":
                        out = {"reasoning": "q", "steps": [
                            {"act": "select_external", "external": names[0], "evidence": f"once with {names[0]}"},
                            {"act": "run", "external": None, "evidence": f"once with {names[0]}"},
                            {"act": "select_external", "external": names[1], "evidence": f"once with {names[1]}"},
                            {"act": "run", "external": None, "evidence": f"once with {names[1]}"},
                            {"act": "compare_runs", "external": None, "evidence": "tell me what changed"}]}
                    else:
                        out = {"reasoning": "q"}
                    c = _Comp()
                    c.choices[0].message.content = json.dumps(out)
                    return c

    app._client = lambda endpoint, api_key: _Fake()
    n0 = len(sc.results)
    hm, _, sm, cm, *_ = app.submit_answer(msg_m, hc, sc, "http://localhost:1/v1", "fake",
                                          "", write_prose=False, tz_known=True)
    check(len(sm.results) == n0 + 2 and cm is not None,
          "two more runs were made, one per release", f"{len(sm.results)} results")
    used = [a for a in sm.actions if a.get("route") == "plan_steps"]
    check(used and [st["act"] for st in used[-1]["accepted"]]
          == ["select_external", "run", "select_external", "run", "compare_runs"],
          "the plan is logged: proposed, accepted")
    text = "\n".join(t for _, t in hm if t)
    check("Plan: select_external" in text and "## Comparison:" in text and "Step 5" in text,
          "the plan, each step and the final comparison are in the chat")
    ext_a = (sm.results[-2].provenance.get("external") or {}).get("file")
    ext_b = (sm.results[-1].provenance.get("external") or {}).get("file")
    check(ext_a == names[0] and ext_b == names[1],
          "each run's provenance names the release it used", f"{ext_a} / {ext_b}")
    tc = [a for a in sm.actions if a.get("route") == "turn_calls"]
    check(tc and tc[-1].get("steps") == 5 and tc[-1]["model_calls"] <= tc[-1]["budget"],
          "the turn's calls stayed within the step budget", str(tc[-1]))
    from bregsurv_agent import guards
    check(guards.audit(sm) == [], "the audit passes after the multi-step turn", str(guards.audit(sm)))

    # a plain follow-up: select one release by name and re-run the current declaration
    class _Fake2(_Fake):
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    name = kw["response_format"]["json_schema"]["name"]
                    out = {"reasoning": "q", "intents": [
                        {"kind": "select_external", "evidence": f"use {names[1]}",
                         "external_form": None, "external_name": names[1], "out_of_scope_reason": None}]}
                    if name != "intent":
                        out = {"reasoning": "q"}
                    c = _Comp()
                    c.choices[0].message.content = json.dumps(out)
                    return c
    app._client = lambda endpoint, api_key: _Fake2()
    hs, _, ss, cs, *_ = app.submit_answer(f"Please use {names[1]} from now on.", hm, sm,
                                          "http://localhost:1/v1", "fake", "", write_prose=False, tz_known=True)
    check(cs is not None and len(ss.results) == len(sm.results) + 1 and ss.external_name == names[1],
          "select_external re-runs the current declaration on the named release")

    # ------------------------------------------------------------ E. a run step on a FRESH session
    # The case-1 request under Qwen3 (job 61023996): the message names every role
    # and the file, the model types it multi_step and plans select_external ->
    # edit_and_run. The step must read the roles from the message, not stop at
    # "there is no declaration yet".
    hdr("E. a run step on a fresh session reads the roles from the message")
    h0, s0, *_ = app.start_session()
    ext_name = s0.external_name
    msg_e = ("Follow-up time is in followup_days, and died is 1 if the patient died. Please "
             "fit a survival model adjusting for age, bmi and egfr, using the published "
             f"coefficients in {ext_name}.")

    class _Fake3(_Fake):
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    name = kw["response_format"]["json_schema"]["name"]
                    if name == "intent":
                        out = {"reasoning": "q", "intents": [
                            {"kind": "multi_step", "evidence": f"using the published coefficients in {ext_name}",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None}]}
                    elif name == "plan_steps":
                        out = {"reasoning": "q", "steps": [
                            {"act": "select_external", "external": ext_name, "evidence": f"in {ext_name}"},
                            {"act": "edit_and_run", "external": None, "evidence": "fit a survival model"}]}
                    elif name == "role_extraction":
                        out = {"reasoning": "q", "time_column": "followup_days",
                               "time_evidence": "Follow-up time is in followup_days",
                               "event_column": "died", "event_evidence": "died is 1 if the patient died",
                               "event_value": "1", "event_value_evidence": "died is 1",
                               "covariate_columns": ["age", "bmi", "egfr"]}
                    else:
                        out = {"reasoning": "q"}
                    c = _Comp()
                    c.choices[0].message.content = json.dumps(out)
                    return c
    app._client = lambda endpoint, api_key: _Fake3()
    he, _, se, ce, *_ = app.submit_answer(msg_e, h0, s0, "http://localhost:1/v1", "fake", "",
                                          write_prose=False, tz_known=True)
    text_e = "\n".join(t for _, t in he if t)
    check(ce is not None and len(se.results) == 1 and se.declaration is not None
          and se.declaration.covariates == ["age", "bmi", "egfr"],
          "the run happened from the message's own roles", text_e[-200:].replace("\n", " | "))
    check("no declaration yet" not in text_e, "the dead end is gone")

    hdr("F. an empty plan falls back to one analysis when the message names roles")
    # the thinking arm on MIUM: M1 typed `multi_step` + `declare_roles`, and the
    # plan_steps call spent its budget and returned {} -- the turn used to end with "I could not
    # turn that into steps". Now the other intents are planned as an ordinary turn.
    h0, s0, *_ = app.start_session()

    class _Fake4(_Fake3):
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    name = kw["response_format"]["json_schema"]["name"]
                    if name == "intent":
                        out = {"reasoning": "q", "intents": [
                            {"kind": "multi_step", "evidence": "fit a survival model",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None},
                            {"kind": "declare_roles", "evidence": "Follow-up time is in followup_days",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None}]}
                    elif name == "plan_steps":
                        out = {}                       # the budget-exhausted answer, verbatim
                    elif name == "role_extraction":
                        out = {"reasoning": "q", "time_column": "followup_days",
                               "time_evidence": "Follow-up time is in followup_days",
                               "event_column": "died", "event_evidence": "died is 1 if the patient died",
                               "event_value": "1", "event_value_evidence": "died is 1",
                               "covariate_columns": ["age", "bmi", "egfr"]}
                    else:
                        out = {"reasoning": "q"}
                    c = _Comp()
                    c.choices[0].message.content = json.dumps(out)
                    return c
    app._client = lambda endpoint, api_key: _Fake4()
    hf, _, sf, cf, *_ = app.submit_answer(msg_e, h0, s0, "http://localhost:1/v1", "fake", "",
                                          write_prose=False, tz_known=True)
    text_f = "\n".join(t for _, t in hf if t)
    check(cf is not None and len(sf.results) == 1 and sf.declaration is not None
          and sf.declaration.covariates == ["age", "bmi", "egfr"],
          "the run happened through the fallback acts", text_f[-200:].replace("\n", " | "))
    check("treating it as one analysis" in text_f and "could not turn that into steps" not in text_f,
          "the analyst is told the plan was replaced, not dead-ended")
    fb = [a for a in sf.actions if a.get("route") == "plan_steps_fallback"]
    check(bool(fb) and "propose_roles" in fb[-1].get("acts", []), "the fallback is logged with its acts")
    tc = [a for a in sf.actions if a.get("route") == "turn_calls"]
    check(tc and tc[-1]["model_calls"] <= tc[-1]["budget"], "still inside the per-turn budget",
          str(tc[-1]) if tc else "no turn_calls record")

    hdr("G. a plan that only selects a file, for a message that declares roles, runs")
    # Qwen2.5 on MIUM P068: M1 typed `multi_step` + `declare_roles`, the plan was
    # "select_external" and nothing else, and the turn ended with a selection and no fit
    h0, s0, *_ = app.start_session()

    class _Fake5(_Fake4):
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    name = kw["response_format"]["json_schema"]["name"]
                    if name == "plan_steps":
                        out = {"reasoning": "q", "steps": [
                            {"act": "select_external", "external": ext_name, "evidence": f"in {ext_name}"}]}
                        c = _Comp()
                        c.choices[0].message.content = json.dumps(out)
                        return c
                    return _Fake4.chat.completions.create(**kw)
    app._client = lambda endpoint, api_key: _Fake5()
    hg, _, sg, cg, *_ = app.submit_answer(msg_e, h0, s0, "http://localhost:1/v1", "fake", "",
                                          write_prose=False, tz_known=True)
    text_g = "\n".join(t for _, t in hg if t)
    check(cg is not None and len(sg.results) == 1 and sg.declaration is not None
          and sg.declaration.covariates == ["age", "bmi", "egfr"],
          "the run the message asks for follows the selection", text_g[-200:].replace("\n", " | "))
    pl = [a for a in sg.actions if a.get("route") == "plan_steps"]
    check(pl and [st["act"] for st in pl[-1]["accepted"]] == ["select_external", "run"]
          and pl[-1]["accepted"][-1].get("added_by", "").startswith("harness"),
          "the accepted plan records the run as added by the harness", str(pl[-1]["accepted"]) if pl else "")
    shutil.rmtree(work, ignore_errors=True)

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
