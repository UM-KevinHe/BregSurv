#!/usr/bin/env python3
"""Components 5-7 (Tools / Actions / Planner-Orchestrator): the closed action
set, the deterministic plan of a turn, its phase rules and its model-call
budget. No model, no R, no GPU.

    python mcp/test_actions.py
"""
from __future__ import annotations

import sys
from itertools import combinations
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
    from bregsurv_agent import actions, intent
    from bregsurv_agent.actions import Act
    from bregsurv_agent.state import Phase, Session
    from bregsurv_agent.declaration import Declaration, Verification
    from bregsurv_agent.external import ExternalObject

    def I(kind):
        return intent.Intent(kind=kind, evidence="x", evidence_verified=True)

    prof = {"columns": [{"name": "t"}, {"name": "d"}, {"name": "age"}],
            "eligible": {"time": ["t"], "event": ["d"], "covariate": ["age"]}}
    base = Session().with_profile("/x.csv", "D", prof)
    ext = ExternalObject(form="coefficients", scale="log_hazard_ratio",
                         terms={"age": 0.1}, provenance={})
    with_file = Session().with_profile("/x.csv", "D", prof, external=ext)
    decl = Declaration(time_col="t", event_col="d", event_value="1", covariates=["age"],
                       source="reply", covariates_time_zero="yes")
    done = base.start_turn("m").with_declaration(decl, Verification(True, ["ok"])).with_result(object())

    # ------------------------------------------------------------ A. the set
    hdr("A. the action set is closed, typed, and says who proposes and who verifies")
    check(set(actions.SPECS) == set(Act), "every act has a spec, and only acts have specs")
    model_acts = {a for a, s in actions.SPECS.items() if s.needs_model}
    check(model_acts == {Act.TYPE_MESSAGE, Act.PROPOSE_ROLES, Act.NAME_PUBLISHED_MODEL,
                         Act.READ_RELEASE, Act.WRITE_REPORT, Act.EXPLAIN_RESULT,
                         Act.WORD_QUESTION, Act.PLAN_STEPS, Act.EXPLAIN_REFUSAL,
                         Act.PLAN_ANALYSIS, Act.REFINE_ANALYSIS, Act.EVALUATE_BY_SPLITS},
          "exactly twelve acts involve the model (V4 adds the planner's two and the split "
          "request reader), each logged under its schema name",
          str(sorted(a.value for a in model_acts)))
    check(all(s.verifier for s in actions.SPECS.values()),
          "every act names what verifies it")
    check({s.proposer.split(":")[1] for s in actions.SPECS.values() if s.needs_model}
          == {"intent", "role_extraction", "published_model", "external_roles",
              "report_prose", "explain", "ask", "plan_steps", "refusal",
              "analysis_plan", "next_step", "split_request"},
          "the model-facing proposers are the twelve policy names")
    rows = actions.registry_table()
    check(len(rows) == len(Act) and all(set(r) == {"act", "proposer", "verified by", "allowed in"}
                                        for r in rows),
          "registry_table() renders one row per act")

    # ------------------------------------------------------------ B. plan
    hdr("B. the plan is a deterministic function of phase and intents")
    ints = intent.dispatch_order([I("declare_roles"), I("describe_external")])
    check(actions.plan(base, ints) == [Act.NAME_PUBLISHED_MODEL, Act.PROPOSE_ROLES, Act.COMPLETE],
          "declare + describe, no file: name the model from the catalogue, propose roles, complete")
    check(actions.plan(with_file, ints) == [Act.SHOW_EXTERNAL, Act.PROPOSE_ROLES, Act.COMPLETE],
          "the same message with a file already read: show its card instead")
    check(actions.plan(base, [I("ask_about_result")]) == [Act.NO_RESULT_YET]
          and actions.plan(done, [I("ask_about_result")]) == [Act.EXPLAIN_RESULT],
          "a question about the result explains only when a result exists")
    check(actions.plan(base, [I("ask_about_method")]) == [Act.ANSWER_METHOD]
          and actions.plan(base, [I("out_of_scope")]) == [Act.REFUSE]
          and actions.plan(base, [I("other")]) == [Act.ASK],
          "method / out of scope / other map to their harness acts")
    check(actions.plan(done, intent.dispatch_order([I("edit_declaration"), I("ask_about_result")]))
          == [Act.PROPOSE_ROLES, Act.EXPLAIN_RESULT, Act.COMPLETE],
          "an edit after a result: propose, explain, complete -- one role proposal, not two")
    check(actions.plan(base, [I("declare_roles"), I("edit_declaration")])
          == [Act.PROPOSE_ROLES, Act.COMPLETE],
          "declare and edit in one message collapse to one proposal")
    check(actions.plan(base, []) == [], "no intents, no acts")
    # M2
    check(actions.plan(done, [I("multi_step"), I("declare_roles")]) == [Act.PLAN_STEPS],
          "a multi-step request: the model plans, nothing else runs on that turn")
    check(actions.plan(done, [I("select_external")]) == [Act.SELECT_EXTERNAL, Act.COMPLETE]
          and actions.plan(base, [I("select_external")]) == [Act.SELECT_EXTERNAL],
          "selecting a release re-runs the current declaration; with none declared it only selects")
    check(actions.plan(done, [I("compare_runs")]) == [Act.COMPARE_RUNS]
          and actions.plan(done, intent.dispatch_order([I("compare_runs"), I("edit_declaration")]))
          == [Act.PROPOSE_ROLES, Act.COMPLETE, Act.COMPARE_RUNS],
          "a comparison comes after the run the turn makes")
    check(actions.step_budget(5) == actions.MODEL_CALLS_PER_TURN + 10,
          "a multi-step turn's budget grows two calls per step")

    # ------------------------------------------------------------ C. rules
    hdr("C. phase rules and the model-call budget")
    check(actions.check(base, [Act.NAME_PUBLISHED_MODEL, Act.PROPOSE_ROLES, Act.COMPLETE]) == [],
          "a legal plan has no violations")
    check(any("explain_result is not allowed in phase profiled" in v
              for v in actions.check(base, [Act.EXPLAIN_RESULT])),
          "explaining before a result is a violation the check names")
    check(any("run_core is not allowed" in v for v in actions.check(base, [Act.RUN_CORE])),
          "the core cannot run before the declaration is verified")
    check(actions.check(Session(), [Act.PROPOSE_ROLES]) != [],
          "nothing model-facing runs with no cohort loaded")
    kinds = ["declare_roles", "edit_declaration", "describe_external", "ask_about_method",
             "ask_about_result", "out_of_scope", "other", "select_external", "compare_runs",
             "multi_step"]
    worst = 0
    for n in (1, 2, 3):
        for combo in combinations(kinds, n):
            for sess in (base, with_file, done):
                acts = actions.plan(sess, intent.dispatch_order([I(k) for k in combo]))
                worst = max(worst, actions.model_calls_in(acts))
                if actions.check(sess, acts):
                    # phase rules may legitimately forbid (e.g. explain before a result
                    # never appears in a plan); a budget violation must never
                    assert not any("budget" in v for v in actions.check(sess, acts)), combo
    check(worst <= actions.MODEL_CALLS_PER_TURN,
          f"no combination of up to three intents plans more than {actions.MODEL_CALLS_PER_TURN} "
          f"model calls (worst case {worst})")
    check(actions.model_calls_in([Act.SHOW_EXTERNAL, Act.PROPOSE_ROLES, Act.COMPLETE]) == 3,
          "intent + proposal + report = 3 on the ordinary prose path")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
