"""The web UI's state machine, driven exactly as Gradio drives it.

WHY THIS EXISTS RATHER THAN A BROWSER TEST. The classic Gradio failure is a
handler that returns a different number of values than its `outputs=` list
expects. It imports cleanly, it renders cleanly, and it fails the first time a
user presses the button -- which in this app is after the analysis has already
run. Nothing short of executing the handler catches it, and executing the
handler needs no browser.

What is checked here is the wiring and the STATE MACHINE, not the statistics.
The shape changed on 2026-09-11 (decide, run, disclose -- no approval step):

  * the arity of every handler against the `outputs=` list it is bound to;
  * that step 1 posts the question and fits nothing;
  * that a complete numbered reply runs AT ONCE: card, then report, artifacts;
  * that a declaration the gate REFUSES fits nothing;
  * that what the analyst leaves out is filled only where the data leaves one
    possibility, and the report says so -- and that the time-zero answer is
    never filled: it is asked, or it is the checkbox;
  * that a column the file lacks goes back to the analyst;
  * that the model is not required anywhere in that path, that the M1
    evidence check is deterministic, and -- with a fake model -- that the
    prose path runs in one turn and M4 answers under boundary 2's rules.

Run:  python test_app_v3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m", "\033[2m",
                             "\033[0m")
passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")
    return ok


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def _n_outputs(app, fn_name: str) -> int:
    """How many components the Blocks graph binds this handler's output to.

    Read off `demo.fns`, which holds the registered BlockFunctions. The config
    dict's `dependencies` do not carry the Python function's name in this
    Gradio version, so matching on it silently found nothing -- and a check that
    silently finds nothing is not a check.
    """
    for f in app.demo.fns.values():
        if getattr(getattr(f, "fn", None), "__name__", None) == fn_name:
            return len(f.outputs or [])
    return -1


def main() -> int:
    import app
    from bregsurv_agent import intent

    hdr("0. the demo data ships with the app")
    check(app.DEMO_COHORT.exists() and app.DEMO_COEFS.exists(),
          "the demo cohort and its registry model are present",
          f"{app.DEMO_COHORT.name}, {app.DEMO_COEFS.name}")

    # ---- step 1 ---------------------------------------------------------
    hdr("1. read the data -> the question is posted, nothing is fitted, no model")
    out1 = app.start_session()
    check(len(out1) == 10, "start_session returns ten values (chat, session, eight result slots)",
          f"got {len(out1)}")
    history, session, *results = out1
    check(session is not None and session.profile is not None,
          "the profile is carried in session state",
          f"{session['profile']['n_rows']} rows" if session else "no session")
    text = (history[0][1] if history else "")
    check("FOLLOW-UP TIME" not in text and "in your own words" in text,
          "the opening is plain language (the numbered form is asked only when needed)")
    check("hla_mismatch" in text,
          "the predictor the cohort does not have is disclosed up front",
          "the registry model names it; this file has no such column")
    check(all(r is None for r in results),
          "nothing is fitted from step 1 alone")

    # ---- step 2: complete reply -> runs at once --------------------------
    hdr("2. a complete numbered reply -> card -> the run, with no approval step")
    reply = "1) followup_days\n2) died\n3) 1\n4) A\n6) yes"
    out2 = app.submit_answer(reply, history, session, "", "", "")
    check(len(out2) == 11, "submit_answer returns eleven values (the tenth is repro_diskd.py, "
          "empty off the discrete-time row; the eleventh the files of an evaluation by "
          "repeated splits, empty unless asked for)", f"got {len(out2)}")
    history, _, session, cand_df, coef_df, rep, trc, rpr, cjs, *_ = out2
    _km = Path(rep).parent / "km_curve.png"
    check(_km.is_file() and (Path(rep).parent / "km_curve.pdf").is_file(),
          "a full-cohort run draws the Kaplan-Meier estimate of the target cohort (PNG and PDF)")
    check("km_curve.png" in Path(rep).read_text(), "the report points to the Kaplan-Meier figure")
    _r = session.result.draw_km(Path(rep).parent, group_col="site")
    check(bool(_r) and _r.get("status") == "ok" and _r.get("grouped_by") == "site"
          and "by `site`" in Path(rep).read_text() and Path(rep).read_text().count("km_curve.png") == 1,
          "a requested grouping redraws the curve by that column in place of the default one", str(_r))
    _r = session.result.draw_km(Path(rep).parent, group_col="age")
    check(bool(_r) and _r.get("grouping") == "median" and "split at its median" in Path(rep).read_text(),
          "a numeric column with many values is split at its median", str(_r))
    card = history[-2][1]
    check("events            49 of 90 (54%)" in card,
          "the card states the consequence as a number the analyst can refute",
          "an inverted event column would read 46% here")
    check("Running every admissible method now" in card,
          "and the run starts on the same turn")
    check("## 1. The data" in history[-1][1],
          "the report is posted into the conversation")
    check(cand_df is not None and len(cand_df) == 10,
          "all ten admissible methods are shown, not just the winner",
          f"{0 if cand_df is None else len(cand_df)} rows")
    check(cand_df is not None and (cand_df[""] == "<-").sum() == 1,
          "exactly one is marked as selected")
    check(coef_df is not None and len(coef_df) == 5,
          "the selected model is shown variable by variable",
          f"{0 if coef_df is None else len(coef_df)} rows")
    for name, p in (("report.md", rep), ("trace.json", trc),
                    ("repro.R", rpr), ("candidates.json", cjs)):
        check(p and Path(p).exists() and Path(p).stat().st_size > 0,
              f"{name} is offered for download",
              f"{Path(p).stat().st_size} bytes" if p else "missing")
    import json as _json
    trace = _json.loads(Path(trc).read_text(encoding="utf-8"))
    check(trace.get("config_sha256") and session["result"].config_sha256
          == trace["config_sha256"],
          "C3: the hash bound at verify time is the hash that ran",
          trace.get("config_sha256", "")[:12])
    check(trace["declaration"].get("sources", {}).get("time") == "reply",
          "each role's source travels into trace.json",
          str(trace["declaration"].get("sources")))
    check(any(a.get("route") == "numbered_reply"
              for a in (trace.get("provenance", {}).get("model", {})
                        .get("actions") or [])),
          "the action log records how the message was routed")

    # ---- 3. refusal --------------------------------------------------------
    hdr("3. a refused declaration fits nothing")
    bad = "1) followup_days\n2) died\n3) 1\n4) age, bmi, died\n6) yes"
    h2, _, s2, *r2 = app.submit_answer(bad, [], session, "", "", "")
    check(all(r is None for r in r2),
          "declaring the outcome as its own predictor cannot be run")
    check("outcome" in h2[-1][1].lower() and "Nothing was fitted" in h2[-1][1],
          "and the analyst is told which mistake it was")

    # ---- 4. what is filled, and what is never filled ------------------------
    hdr("4. gaps: filled where the data leaves one possibility; time zero never")
    fresh = session.restart()
    h3, _, s3, *r3 = app.submit_answer("1) followup_days\n2) died", [], fresh,
                                       "", "", "")
    check(all(r is None for r in r3) and "6) Was every covariate" in h3[-1][1],
          "with time zero unanswered, the ONLY question asked is time zero",
          "everything else was settled")
    check("1) FOLLOW-UP" not in h3[-1][1] and "2) EVENT" not in h3[-1][1]
          and "4) COVARIATES" not in h3[-1][1],
          "questions already settled are not asked again")
    check(s3["pending"].get("event_value") == "1"
          and "inferred" in s3["pending_sources"].get("event_value", ""),
          "the event value was inferred from a 0/1 column",
          s3["pending_sources"].get("event_value"))
    check(s3["pending"].get("covariates") == "B"
          and "inferred" in s3["pending_sources"].get("covariates", ""),
          "the covariate set defaulted to every usable numeric column",
          s3["pending_sources"].get("covariates"))
    check("<- reply" in h3[-1][1] and "<- inferred" in h3[-1][1],
          "what was settled so far is shown with its source")

    # the checkbox answers time zero, and the run goes ahead
    h4, _, s4, cand4, *r4 = app.submit_answer("1) followup_days\n2) died", [],
                                              fresh, "", "", "",
                                              write_prose=False, tz_known=True)
    check(cand4 is not None and len(cand4) == 10,
          "with the checkbox ticked the same two answers run to a report",
          f"{0 if cand4 is None else len(cand4)} candidates")
    report4 = h4[-1][1]
    check("How each role was settled" in report4
          and "inferred: the column is 0/1" in report4
          and "you said every covariate was recorded" in report4,
          "the report discloses every inference and the checkbox",
          "this table replaces the approval step")
    d4 = s4["declaration"]
    check(sorted(d4.covariates) == sorted(
              n for n in session["profile"]["eligible"]["covariate"]
              if n not in ("followup_days", "died")),
          "the defaulted covariate set excludes the outcome columns",
          ", ".join(d4.covariates))

    # ---- 5. a column the file lacks goes back to the analyst ---------------
    hdr("5. a contradiction with the file is the one gap that is asked back")
    h5, _, s5, *r5 = app.submit_answer("1) followup_days\n2) death\n6) yes",
                                       [], fresh, "", "", "")
    check(all(r is None for r in r5) and "no column called 'death'" in h5[-1][1],
          "a ghost column is refused by name, nothing is fitted")
    # 2026-10-01: once corrected, the report says what became of the name the file lacks
    h5b, _, s5b, *r5b = app.submit_answer("1) followup_days\n2) died\n6) yes", h5, s5, "", "", "")
    rep5b = h5b[-1][1]
    check(s5b["declaration"] is not None and "You also named `death`" in rep5b
          and any(n.startswith("named but not a column of the file: 'death'") for n in s5b["declaration"].notes),
          "a column the analyst named that the file lacks is disclosed in the report after the correction",
          rep5b[rep5b.find("You also"):][:160] if "You also" in rep5b else rep5b[:160])

    # ---- 6. prose without a model ------------------------------------------
    hdr("6. prose with no endpoint is refused with instructions, not guessed")
    h6, _, _, *r6 = app.submit_answer("time is followup_days and died is the "
                                      "event", [], fresh, "", "", "")
    check(all(r is None for r in r6) and "no model endpoint" in h6[-1][1],
          "the numbered format is offered instead")

    # ---- 7. M1's harness half is deterministic ----------------------------
    hdr("7. intent validation: evidence must be in the message")
    msg = "Please plot the survival curves by sex."
    raw = {"reasoning": "x", "intents": [
        {"kind": "out_of_scope", "evidence": "plot the survival curves",
         "external_form": None, "out_of_scope_reason": "figure_requested"},
        {"kind": "declare_roles", "evidence": "adjust for age",
         "external_form": None, "out_of_scope_reason": None}]}
    got = intent.validate(msg, raw)
    check(got[0].kind == "out_of_scope" and got[0].evidence_verified,
          "a quoted phrase that is in the message is verified")
    check(got[1].kind == "declare_roles" and not got[1].evidence_verified,
          "a phrase that is NOT in the message is marked unverified")
    raw2 = {"reasoning": "x", "intents": [
        {"kind": "out_of_scope", "evidence": "run a Cox model",
         "external_form": None, "out_of_scope_reason": "other"}]}
    got2 = intent.validate(msg, raw2)
    check(got2[0].kind == "other" and got2[0].demoted_from == "out_of_scope",
          "a refusal on words the analyst did not write is demoted to `other`",
          "a refusal must never rest on an unverifiable quote")
    check("figure" in intent.refusal(got[0]).lower()
          and 'You wrote "plot the survival curves"' in intent.refusal(got[0]),
          "the refusal quotes the analyst and names the reason")
    check([i.kind for i in intent.dispatch_order(got)]
          == ["declare_roles", "out_of_scope"],
          "dispatch order is fixed by the harness, not by the model")
    # the phase rule: a question about a result cannot exist before a result
    msg_v = "Please analyse my transplant data and tell me what predicts survival."
    raw_v = {"reasoning": "x", "intents": [
        {"kind": "ask_about_result", "evidence": "tell me what predicts survival",
         "external_form": None, "out_of_scope_reason": None},
        {"kind": "other", "evidence": "Please analyse my transplant data",
         "external_form": None, "out_of_scope_reason": None}]}
    got_v = intent.validate(msg_v, raw_v, result_present=False)
    check([i.kind for i in got_v] == ["other"] and got_v[0].demoted_from == "ask_about_result",
          "with no result, `ask_about_result` is demoted to `other` on the record, and not duplicated",
          str([i.as_dict() for i in got_v]))
    got_p = intent.validate(msg_v, raw_v, result_present=True)
    check([i.kind for i in got_p] == ["ask_about_result", "other"],
          "with a result present the same typing stands")
    check([i.kind for i in intent.validate(msg_v, raw_v)] == ["ask_about_result", "other"],
          "and without the state given, nothing is demoted (the plan's phase rule still applies)")
    # duplicates are dropped before the cap: a repeated kind cannot crowd out another
    msg_d = "time is t, event is d, adjust for x, use the registry file, and evaluate on 20 random splits."
    raw_d = {"reasoning": "x", "intents": [
        {"kind": "declare_roles", "evidence": "time is t"},
        {"kind": "declare_roles", "evidence": "event is d"},
        {"kind": "declare_roles", "evidence": "adjust for x"},
        {"kind": "describe_external", "evidence": "use the registry file"},
        {"kind": "other", "evidence": "evaluate on 20 random splits"}]}
    got_d = [i.kind for i in intent.validate(msg_d, raw_d)]
    check(got_d == ["declare_roles", "describe_external", "other"],
          "a kind repeated by the model is dropped before the cap, so later kinds survive", str(got_d))
    raw_m = {"reasoning": "x", "intents": [{"kind": k, "evidence": "time is t"} for k in
             ("declare_roles", "describe_external", "ask_about_method", "other", "multi_step", "compare_runs")]}
    check(len(intent.validate(msg_d, raw_m)) == intent.MAX_INTENTS,
          "at most MAX_INTENTS distinct kinds are kept")
    check(intent.schema_for([])["properties"]["intents"]["maxItems"] == intent.MAX_INTENTS_RAW,
          "the grammar bound is MAX_INTENTS_RAW")
    sl = intent.state_line(s3)
    check("declaration: partial (time, event, event_value, covariates" in sl,
          "the state line shows the partial declaration", sl)

    # ---- 7b. the prose path, end to end, with a fake model ----------------
    hdr("7b. prose -> M1 -> extraction -> complete -> run -> explain, fake model")
    import json as _j

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

    class _Fake:
        """Answers by the schema name; the M1/explain payloads are swapped by
        the test between turns."""
        base_url = "http://localhost:1/v1"
        intent_out = None
        explain_out = None
        extract_out = None
        ask_out = None
        refusal_out = None

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
                        out = _Fake.intent_out
                    elif name == "role_extraction":
                        out = _Fake.extract_out or {
                               "reasoning": "q", "time_column": "followup_days",
                               "event_column": "died", "event_value": "1",
                               "covariate_columns": ["age", "bmi", "egfr",
                                                     "donor_age", "cold_ischemia"]}
                    elif name == "explain":
                        out = _Fake.explain_out
                    elif name == "ask":
                        out = _Fake.ask_out or {"reasoning": "q", "question": ""}
                    elif name == "refusal":
                        out = _Fake.refusal_out or {"reasoning": "q", "explanation": ""}
                    else:
                        out = {"reasoning": "q",
                               "data": "The cohort has [n] subjects.",
                               "linkage": "Linkage covered [p_covered].",
                               "candidates": "Every admissible candidate was fitted.",
                               "comparison": "The lowest loss was [loss_best].",
                               "selected": "The selected model is [selected_label]."}
                    c = _Comp()
                    c.choices[0].message.content = _j.dumps(out)
                    return c

    app._client = lambda endpoint, api_key: _Fake()
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Follow-up is in followup_days",
         "external_form": None, "out_of_scope_reason": None},
        {"kind": "describe_external",
         "evidence": "published coefficients from a larger registry model",
         "external_form": "coefficients", "out_of_scope_reason": None}]}
    h7, s7, *_ = app.start_session()
    out7 = app.submit_answer(app.EXAMPLE_QUERY, h7, s7, "http://localhost:1/v1",
                             "fake", "", write_prose=True, tz_known=True)
    h7, _, s7, cand7, *_ = out7
    check(cand7 is not None and len(cand7) == 10 and s7.get("result") is not None,
          "the example request runs to a report in ONE turn",
          f"{len(h7)} chat turns")
    check("<- quoted" in h7[-2][1] and "you said every covariate" in h7[-2][1],
          "the card credits the request and the checkbox")
    check("external information I have read" in h7[-2][1],
          "the external-information intent is acknowledged before the run")
    calls = [c["name"] for c in s7["result"].provenance["model"]["calls"]]
    check(calls == ["intent", "role_extraction", "report_prose"],
          "three model calls, in order, in the provenance", str(calls))
    check(all(c.get("first_key") == "reasoning"
              for c in s7["result"].provenance["model"]["calls"]),
          "M3: every call record carries the first key the model emitted")
    # components 5-7: the turn was planned before it ran, and stayed in budget
    plans = [a["plan"] for a in s7.actions if a.get("plan")]
    check(plans == [["show_external", "propose_roles", "complete"]],
          "the turn's plan is logged: show the file's card, propose roles, complete",
          str(plans))
    turns = [a for a in s7.actions if a.get("route") == "turn_calls"]
    check(turns and all(t["model_calls"] <= t["budget"] for t in turns)
          and turns[-1]["model_calls"] == 2,
          "model calls this turn (intent + extraction) are counted against the budget",
          str(turns))

    # a question about the result -> explain, resolved from the closed set
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "ask_about_result", "evidence": "why was",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.explain_out = {"reasoning": "loss_best vs loss_internal",
                         "answer": "It kept [selected_label] because it did best "
                                   "when part of the patients was set aside."}
    h8, _, s8, *r8 = app.submit_answer("why was that model chosen?", h7, s7,
                                       "http://localhost:1/v1", "fake", "")
    a8 = h8[-1][1]
    refs8 = __import__("bregsurv_agent.report_v3", fromlist=["x"]) \
        .build_references(s7["result"].candidates)
    check(all(r is None for r in r8) and "[selected_label]" not in a8
          and "did best" in a8 and len(refs8) > 0,
          "M4: the answer's references were resolved by the harness, no refit",
          a8[:100])
    check(s8["model_calls"] and s8["model_calls"][-1]["name"] == "explain",
          "the explain call is logged in the session")
    # the reference set of a run holds only quantities that HAVE a value in it
    # (report rubric, 2026-09-15: "[n_intervals]" on a continuous-time run
    # rendered "not available"), and no runtime
    check("n_intervals" not in refs8 and "runtime_seconds" not in refs8
          and all(v is not None for v in refs8.values()),
          "references without a value in this run are not offered", str(sorted(refs8))[:120])
    R3 = __import__("bregsurv_agent.report_v3", fromlist=["x"])
    try:
        R3.resolve("over [n_intervals] intervals", refs8)
        check(False, "a draft naming an unoffered reference is an unknown reference", "it resolved")
    except R3.UnknownReference:
        check(True, "a draft naming an unoffered reference is an unknown reference")
    check(R3.not_prose("[n], [event_rate]") and R3.not_prose("[selected_label], [selected_borrowing], a lasso penalty}")
          and R3.not_prose("The cohort holds [n] subjects with [n_events] events.") is None,
          "a section that is a bare list of references, or ends in a stray brace, is not prose")
    dup = R3.resolve("incorporated [selected_borrowing] borrowing and used [selected_penalty] penalty.", refs8)
    check("borrowing borrowing" not in dup and "penalty penalty" not in dup,
          "a label's own last word written again after the reference is not doubled", dup)

    # a draft that writes a digit itself is dropped, not repaired
    _Fake.explain_out = {"reasoning": "x",
                         "answer": "It was chosen because its loss was 6.68."}
    h9, _, _, *_ = app.submit_answer("why was that model chosen?", h8, s8,
                                     "http://localhost:1/v1", "fake", "")
    check("could not put that into words" in h9[-1][1] and "6.68" not in h9[-1][1],
          "a draft with a bare number is dropped and the analyst told why")

    # out of scope -> the refusal catalogue, quoting the analyst
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "out_of_scope", "evidence": "plot the survival curves",
         "external_form": None, "out_of_scope_reason": "figure_requested"}]}
    h10, _, _, *r10 = app.submit_answer("Can you plot the survival curves by "
                                        "site?", h8, s8,
                                        "http://localhost:1/v1", "fake", "")
    check(all(r is None for r in r10) and 'You wrote "plot the survival curves"'
          in h10[-1][1] and "draws no figures" in h10[-1][1],
          "an out-of-scope request gets the catalogue text, nothing is fitted")

    # ---- 7c. component 2/9: a name the analyst did not write is not quoted
    hdr("7c. a model guess that the message does not back is dropped, not fitted")
    # the message names the time column, the value and three predictors, and
    # does NOT name the event column; the fake model guesses `died` (a real
    # column) and adds `site` (a real column the analyst never mentioned)
    msg_c = ("We have a kidney cohort. Time is followup_days and death is coded "
             "1. Please adjust for age, bmi and egfr.")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Time is followup_days",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days",
                         "event_column": "died", "event_value": "1",
                         "covariate_columns": ["age", "bmi", "egfr", "site"]}
    hc, sc, *_ = app.start_session()
    outc = app.submit_answer(msg_c, hc, sc, "http://localhost:1/v1", "fake",
                             "", write_prose=False, tz_known=True)
    hc, _, sc, candc, *_ = outc
    decl_c = sc.get("declaration")
    check(decl_c is not None and candc is not None,
          "the run still completes in one turn",
          "the dropped roles were settled by rule, not asked, on this file")
    srcs = (decl_c.sources or {}) if decl_c is not None else {}
    check(decl_c is not None and decl_c.event_col == "died"
          and srcs.get("event", "").startswith("inferred"),
          "the guessed event column is NOT `quoted`: the harness re-derived it by rule",
          str(srcs.get("event")))
    check(decl_c is not None and "site" not in decl_c.covariates
          and set(decl_c.covariates) == {"age", "bmi", "egfr"}
          and srcs.get("covariates") == "quoted",
          "the unmentioned covariate is dropped; the three the analyst wrote stay quoted",
          str(decl_c.covariates if decl_c else None))
    check(srcs.get("time") == "quoted" and srcs.get("event_value") == "quoted",
          "names and values the analyst wrote are quoted")
    acts = [a for a in (sc.get("actions") or []) if a.get("route") == "unbacked_names"]
    check(len(acts) == 1 and acts[0]["dropped"].get("event") == "died"
          and acts[0]["dropped"].get("covariates") == ["site"],
          "the drop is in the typed action log, per role", str(acts))
    # decision (b) revised: a role the message DESCRIBES is resolved by the model,
    # accepted with its verbatim phrase, and disclosed as `described`
    msg_d = ("Time is followup_days. The outcome is death during follow-up, coded 1. "
             "Please adjust for age, bmi and egfr.")
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days",
                         "time_evidence": "Time is followup_days",
                         "event_column": "died", "event_evidence": "death during follow-up",
                         "event_value": "1", "event_value_evidence": "coded 1",
                         "covariate_columns": ["age", "bmi", "egfr"]}
    hd, sd, *_ = app.start_session()
    hd, _, sd, candd, *_ = app.submit_answer(msg_d, hd, sd, "http://localhost:1/v1", "fake",
                                             "", write_prose=False, tz_known=True)
    sd_src = (sd.declaration.sources or {}) if sd.declaration else {}
    check(candd is not None and sd.declaration.event_col == "died"
          and sd_src.get("event") == 'described: "death during follow-up"',
          "a described event column is resolved by the model and disclosed with its phrase",
          str(sd_src))
    check("described:" in hd[-2][1], "the card shows the phrase the column was read from")

    # the model words the lead-in of a question the harness still has to ask
    msg_q = "Please fit the survival model adjusting for age and bmi."   # no time, no event
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "adjusting for age and bmi",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": None, "time_evidence": None,
                         "event_column": None, "event_evidence": None,
                         "event_value": None, "event_value_evidence": None,
                         "covariate_columns": ["age", "bmi"]}
    _Fake.ask_out = {"reasoning": "q", "question": "I read age and bmi as the predictors. "
                     "Your message does not say which column records the follow-up time, "
                     "and the file has more than one that could."}
    hq, sq, *_ = app.start_session()
    hq, _, sq, *rq = app.submit_answer(msg_q, hq, sq, "http://localhost:1/v1", "fake",
                                       "", write_prose=False, tz_known=True)
    check(all(r is None for r in rq) and "I read age and bmi as the predictors" in hq[-1][1]
          and "1) FOLLOW-UP TIME" in hq[-1][1],
          "the worded lead-in precedes the harness's numbered list, nothing fitted",
          hq[-1][1][:120])
    check(any(a.get("route") == "word_question" and a.get("used") for a in sq.actions)
          and sq.model_calls[-1]["name"] == "ask",
          "the wording call is logged and counted")
    _Fake.ask_out = {"reasoning": "q", "question": "Which of the 2 columns, followup_days "
                     "or observation_window, is the follow-up time?"}
    hq2, sq2, *_ = app.start_session()
    hq2, _, sq2, *_ = app.submit_answer(msg_q, hq2, sq2, "http://localhost:1/v1", "fake",
                                        "", write_prose=False, tz_known=True)
    check("observation_window" not in hq2[-1][1] and "1) FOLLOW-UP TIME" in hq2[-1][1]
          and any(a.get("route") == "word_question" and not a.get("used") for a in sq2.actions),
          "a draft that names a column the file lacks (or writes a digit) is dropped; the list still asks")
    _Fake.ask_out = None

    # ---- 7d. 2026-09-13: a refusal names the item; a failed reader ends in the form
    hdr("7d. a refused value names its item; a model failure falls back to the numbered form")
    # the model returns the analyst's whole phrase as the event value (Qwen2.5 did,
    # 19 times in the MIUM run); the refusal must say which item to correct
    msg_v = ("Time is followup_days and died is 1 if they died, 0 if not. "
             "Please adjust for age, bmi and egfr.")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Time is followup_days",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days",
                         "event_column": "died", "event_value": "1 if they died, 0 if not",
                         "covariate_columns": ["age", "bmi", "egfr"]}
    hv, sv, *_ = app.start_session()
    hv, _, sv, *rv = app.submit_answer(msg_v, hv, sv, "http://localhost:1/v1", "fake",
                                       "", write_prose=False, tz_known=True)
    check(all(r is None for r in rv) and "I could not use that" in hv[-1][1]
          and "item 3, the value that means the event occurred" in hv[-1][1],
          "the refusal of a phrase-as-value names item 3", hv[-1][1][-120:])
    hv, _, sv, candv, *_ = app.submit_answer("3) 1", hv, sv, "http://localhost:1/v1", "fake",
                                             "", write_prose=False, tz_known=True)
    check(candv is not None and sv.declaration is not None and sv.declaration.event_value == "1",
          "one numbered correction later the analysis runs")
    _Fake.extract_out = None
    # the reader raises (a thinking model that spent its allowance and returned no JSON)
    _create = _Fake.chat.completions.create

    def _boom(**kw):
        if kw["response_format"]["json_schema"]["name"] == "role_extraction":
            raise ValueError("role_extraction: the model's output was not valid JSON "
                             "(finish_reason=length, completion_tokens=3200, max_tokens=3200)")
        return _create(**kw)
    _Fake.chat.completions.create = staticmethod(_boom)
    hb, sb, *_ = app.start_session()
    hb, _, sb, *rb = app.submit_answer(msg_v, hb, sb, "http://localhost:1/v1", "fake",
                                       "", write_prose=False, tz_known=True)
    _Fake.chat.completions.create = staticmethod(_create)
    check(all(r is None for r in rb) and "I could not read that" in hb[-1][1]
          and "1) FOLLOW-UP TIME" in hb[-1][1] and "3) WHICH VALUE" in hb[-1][1]
          and any(a.get("route") == "model_failure" for a in sb.actions),
          "a reader failure ends the turn with the numbered form and a logged action",
          hb[-1][1][:100])
    hb, _, sb, candb, *_ = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, bmi, egfr",
                                             hb, sb, "http://localhost:1/v1", "fake",
                                             "", write_prose=False, tz_known=True)
    check(candb is not None, "and the numbered reply runs the analysis without the model")

    # ---- 7e. 2026-09-13: a message that names the file's columns declares roles, whatever M1 typed
    hdr("7e. M1 misses declare_roles on a message that names columns: the rule adds it")
    msg_m = ("Time is followup_days and died is 1 if the patient died. Please adjust for age, bmi "
             "and egfr, using the published coefficients from the registry.")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "describe_external", "evidence": "the published coefficients from the registry",
         "external_form": "coefficients", "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days", "event_column": "died",
                         "event_value": "1", "covariate_columns": ["age", "bmi", "egfr"]}
    hm, sm, *_ = app.start_session()
    hm, _, sm, candm, *_ = app.submit_answer(msg_m, hm, sm, "http://localhost:1/v1", "fake", "",
                                             write_prose=False, tz_known=True)
    check(candm is not None and sm.declaration is not None and sm.declaration.covariates == ["age", "bmi", "egfr"]
          and any(a.get("route") == "declare_roles_by_rule" for a in sm.actions),
          "the analysis runs and the added intent is logged as a rule", str([a for a in sm.actions if a.get("route") == "declare_roles_by_rule"])[:120])
    # an out-of-scope ASIDE typed alone (hard set H071, 2026-09-15): the roles the
    # message writes outside the refused span still declare; the aside is declined
    msg_o = ("Time is followup_days and died is 1 if the patient died; adjust for age, bmi and "
             "egfr. Also, could you draw a Kaplan-Meier curve by site for the slides?")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "out_of_scope", "evidence": "could you draw a Kaplan-Meier curve by site",
         "external_form": None, "out_of_scope_reason": "figure_requested"}]}
    ho, so, *_ = app.start_session()
    ho, _, so, cando, *_ = app.submit_answer(msg_o, ho, so, "http://localhost:1/v1", "fake", "",
                                             write_prose=False, tz_known=True)
    texto = "\n".join(t for _, t in ho if t)
    check(cando is not None and so.declaration is not None and so.declaration.covariates == ["age", "bmi", "egfr"]
          and "draws no figures" in texto,
          "the analysis runs and the aside is declined in the same reply",
          (ho[-1][1][:120] if cando is None else "ran"))
    # the out-of-scope request that IS the message: refused, nothing fitted
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "out_of_scope", "evidence": "fit competing risks on followup_days and died with age as the covariate",
         "external_form": None, "out_of_scope_reason": "competing_risks"}]}
    hq, sq, *_ = app.start_session()
    hq, _, sq, candq, *_ = app.submit_answer("Please fit competing risks on followup_days and died with age as the covariate.",
                                             hq, sq, "http://localhost:1/v1", "fake", "", write_prose=False, tz_known=True)
    check(candq is None and sq.declaration is None and "Competing risks" in hq[-1][1],
          "an out-of-scope request that names columns inside its own span is refused, not analysed")
    _Fake.extract_out = None
    # a message naming no column is left alone (an external card, no fit)
    hn, sn, *_ = app.start_session()
    hn, _, sn, candn, *_ = app.submit_answer("We have published coefficients from the registry to lean on.",
                                             hn, sn, "http://localhost:1/v1", "fake", "", write_prose=False, tz_known=True)
    check(candn is None and not any(a.get("route") == "declare_roles_by_rule" for a in sn.actions),
          "a message that names no column gets no declaration intent from the rule")

    # a refusal explained by the model in plain words; advice or an alien name is dropped
    msg_r = ("Time is followup_days, the outcome is died coded 1, and please adjust for "
             "age, bmi and followup_days.")     # the outcome's own time as a covariate -> refused
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Time is followup_days",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days",
                         "time_evidence": "Time is followup_days",
                         "event_column": "died", "event_evidence": "the outcome is died",
                         "event_value": "1", "event_value_evidence": "coded 1",
                         "covariate_columns": ["age", "bmi", "followup_days"]}
    _Fake.refusal_out = {"reasoning": "q", "explanation": "The follow-up time column, followup_days, "
                         "was also listed among the covariates, and a model cannot use its own "
                         "outcome as a predictor, so nothing was fitted."}
    hr, sr, *_ = app.start_session()
    hr, _, sr, *rr = app.submit_answer(msg_r, hr, sr, "http://localhost:1/v1", "fake",
                                       "", write_prose=False, tz_known=True)
    check(all(r is None for r in rr) and sr.declaration is not None and not sr.verification.admissible
          and "cannot use its own outcome as a predictor" in hr[-1][1]
          and "Nothing was fitted" in hr[-1][1],
          "a refused declaration is explained in the model's words above the harness's refusal",
          hr[-1][1][-300:])
    check("Reply by number to correct it: item 4, the covariates." in hr[-1][1],
          "the gate's refusal names the numbered item to correct (2026-09-13)")
    _Fake.refusal_out = {"reasoning": "q", "explanation": "Drop followup_days from the 3 covariates "
                         "and use survival_months instead."}
    hr2, sr2, *_ = app.start_session()
    hr2, _, sr2, *_ = app.submit_answer(msg_r, hr2, sr2, "http://localhost:1/v1", "fake",
                                        "", write_prose=False, tz_known=True)
    check("survival_months" not in hr2[-1][1] and "Nothing was fitted" in hr2[-1][1]
          and any(a.get("route") == "explain_refusal" and not a.get("used") for a in sr2.actions),
          "a draft with a digit or an alien column name is dropped; the harness's refusal stands")
    _Fake.refusal_out = None

    # a ghost column the analyst DID write is backed, so it is still asked back by name
    _Fake.extract_out = {"reasoning": "q", "time_column": "followup_days",
                         "event_column": "hla_mismatch", "event_value": None,
                         "covariate_columns": None}
    hg, sg, *_ = app.start_session()
    hg, _, sg, *rg = app.submit_answer(
        "Time is followup_days and the event column is hla_mismatch.", hg, sg,
        "http://localhost:1/v1", "fake", "", write_prose=False, tz_known=True)
    check(all(r is None for r in rg) and "hla_mismatch" in hg[-1][1],
          "a ghost column the analyst wrote is refused BY NAME, not silently dropped",
          hg[-1][1][:120])
    _Fake.extract_out = None

    # ---- 7e. several messages (rubric task H070, 2026-10-01) ---------------
    hdr("7e. a later message edits the declaration already run; selecting the file keeps the edit")
    url = "http://localhost:1/v1"
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Follow-up is in followup_days",
         "external_form": None, "out_of_scope_reason": None}]}
    he, se, *_ = app.start_session()
    he, _, se, ce, *_ = app.submit_answer(app.EXAMPLE_QUERY, he, se, url, "fake", "",
                                          write_prose=False, tz_known=True)
    check(ce is not None and se.get("result") is not None, "turn 1 runs")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Adjust for age and bmi only",
         "external_form": None, "out_of_scope_reason": None}]}
    _Fake.extract_out = {"reasoning": "q", "time_column": None, "event_column": None,
                         "event_value": None, "covariate_columns": ["age", "bmi"]}
    he, _, se, ce, *_ = app.submit_answer("Adjust for age and bmi only.", he, se, url, "fake",
                                          "", write_prose=False, tz_known=True)
    check(ce is not None and list(se["declaration"].covariates) == ["age", "bmi"]
          and "I still need" not in he[-1][1],
          "a covariate edit typed declare_roles re-runs on the current declaration",
          str(getattr(se["declaration"], "covariates", None)))
    _Fake.extract_out = None
    name = next(iter(se.externals))
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "select_external", "evidence": "use the registry coefficients",
         "external_name": name, "external_form": None, "out_of_scope_reason": None}]}
    he, _, se, ce, *_ = app.submit_answer("Please use the registry coefficients.", he, se, url,
                                          "fake", "", write_prose=False, tz_known=True)
    check(list(se["declaration"].covariates) == ["age", "bmi"],
          "selecting the external file keeps the edited covariates",
          str(getattr(se["declaration"], "covariates", None)))

    # ---- 7f. an open question survives a later message; a value stated for
    # a column the file lacks is not carried to the corrected column
    # (rubric tasks H063 and H045, 2026-10-02) ------------------------------
    hdr("7f. the event value is asked again, never filled, after these two turns")
    def _say(text, ev_span, extract):
        _Fake.intent_out = {"reasoning": "q", "intents": [
            {"kind": "declare_roles", "evidence": ev_span,
             "external_form": None, "out_of_scope_reason": None}]}
        _Fake.extract_out = extract
    hf, sf, *_ = app.start_session()
    # a code the column does not hold (died is 0/1): asked, and the question must survive
    m1 = ("The outcome column is died, coded 2 for death and 1 otherwise; "
          "follow-up is followup_days.")
    _say(m1, "follow-up is followup_days", {
        "reasoning": "q", "time_column": "followup_days", "event_column": "died",
        "event_value": "1", "covariate_columns": []})
    hf, _, sf, cf, *_ = app.submit_answer(m1, hf, sf, url, "fake", "", write_prose=False, tz_known=True)
    check(cf is None and "3)" in hf[-1][1], "a contradicted coding is asked (item 3)")
    m2 = "Adjust for age and bmi only."
    _say(m2, "Adjust for age and bmi only", {
        "reasoning": "q", "time_column": None, "event_column": None,
        "event_value": "1", "covariate_columns": ["age", "bmi"]})
    hf, _, sf, cf, *_ = app.submit_answer(m2, hf, sf, url, "fake", "", write_prose=False, tz_known=True)
    check(cf is None and "3)" in hf[-1][1] and sf.get("result") is None,
          "a later message that does not answer it leaves item 3 open (H063)",
          hf[-1][1][-200:].replace(chr(10), " | "))
    hf, _, sf, cf, *_ = app.submit_answer("3) 0", hf, sf, url, "fake", "", write_prose=False, tz_known=True)
    check(cf is not None and str(sf["declaration"].event_value) == "0"
          and list(sf["declaration"].covariates) == ["age", "bmi"],
          "the reply settles it and the covariates of message 2 stand",
          f"{getattr(sf.get('declaration'), 'event_value', None)}")

    hk, sk, *_ = app.start_session()
    m4 = ("The outcome column is died, coded 1 for alive at last contact and 0 for death; "
          "follow-up is followup_days. Adjust for age and bmi.")
    _say(m4, "follow-up is followup_days", {
        "reasoning": "q", "time_column": "followup_days", "event_column": "died",
        "event_value": "1", "covariate_columns": ["age", "bmi"]})
    hk, _, sk, ck, *_ = app.submit_answer(m4, hk, sk, url, "fake", "", write_prose=False, tz_known=True)
    check(ck is not None and str(sk["declaration"].event_value) == "0"
          and sk["declaration"].sources.get("event_value", "").startswith("quoted (")
          and sk.questions == 0,
          "a code the analyst labels as the event is used, with no question (H009/H063/H093)",
          f"{getattr(sk.get('declaration'), 'event_value', None)} q={sk.questions}")

    hg, sg, *_ = app.start_session()
    m3 = "Follow-up is followup_days and the event column is dead (1 = death). Adjust for age and bmi."
    _say(m3, "Follow-up is followup_days", {
        "reasoning": "q", "time_column": "followup_days", "event_column": "dead",
        "event_value": "1", "covariate_columns": ["age", "bmi"]})
    hg, _, sg, cg, *_ = app.submit_answer(m3, hg, sg, url, "fake", "", write_prose=False, tz_known=True)
    check(cg is None and "no column called 'dead'" in hg[-1][1], "a ghost event column is refused by name")
    hg, _, sg, cg, *_ = app.submit_answer("2) died", hg, sg, url, "fake", "", write_prose=False, tz_known=True)
    check(cg is None and "which value of `died`" in hg[-1][1] and "3)" in hg[-1][1],
          "the value stated for `dead` is not carried to `died`: asked (H045)",
          hg[-1][1][:200].replace(chr(10), " | "))
    hg, _, sg, cg, *_ = app.submit_answer("3) 1", hg, sg, url, "fake", "", write_prose=False, tz_known=True)
    check(cg is not None and str(sg["declaration"].event_value) == "1"
          and sg["declaration"].sources.get("event_value") == "reply",
          "the reply settles the value and the run goes ahead")
    _Fake.extract_out = None

    # ---- arity against the graph ----------------------------------------
    hdr("8. every handler's arity matches the outputs it is bound to")
    # : a seventh result slot, repro_diskd.py (the discrete-time row's
    # Python replay), so every handler bound to the results grew by one
    # V4: an eighth, the files of an evaluation by repeated splits
    for fn, ret in (("show_pending", 5), ("example_pending", 5),
                    ("chat_turn_ui", 6), ("reset_ui", 6)):
        n = _n_outputs(app, fn)
        check(n == ret, f"{fn} -> {ret} outputs", f"graph says {n}")
    check(_n_outputs(app, "run_analysis") == -1,
          "run_analysis is no longer bound to any control",
          "there is no Run button; submit_answer calls it")

    # ---- 9. the banner's promise is kept -------------------------------
    hdr("9. session cleanup actually deletes, and never the shipped example")
    import shutil as _sh
    import tempfile as _tf
    fake = Path(_tf.mkdtemp(prefix="bregsurv_fake_"))
    (fake / "uploaded.csv").write_text("a,b" + chr(10) + "1,2" + chr(10),
                                       encoding="utf-8")
    from bregsurv_agent.state import Session as _Session
    sess = _Session(temp=[str(fake / "uploaded.csv"), str(fake),
                          str(app.DEMO_COHORT), str(app.DEMO_COEFS)])
    app._purge(sess)
    check(not (fake / "uploaded.csv").exists() and not fake.exists(),
          "an uploaded file and its run directory are removed",
          "the demo banner promises this in as many words")
    check(app.DEMO_COHORT.exists() and app.DEMO_COEFS.exists(),
          "the shipped example is NEVER deleted",
          "removing it would break the next visitor, not protect this one")
    _sh.rmtree(fake, ignore_errors=True)

    st = [b for b in app.demo.blocks.values()
          if type(b).__name__ == "State"]
    check(any(getattr(b, "delete_callback", None) is app._purge for b in st),
          "the purge is bound to the session state's delete_callback",
          "which is what fires on page close and on timeout")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
