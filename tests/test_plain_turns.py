"""The chat page's plain wording of a turn that stops before a result, and the
plain reply that removes a column the file lacks (fake model, needs R).

    python test_plain_turns.py
"""
from __future__ import annotations
import json as _j
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1; print(f"  PASS  {label}")
    else:
        failed += 1; print(f"  FAIL  {label}   {note}")


REQ = ("Follow-up is in followup_days, and died is 1 when the patient died. Please adjust for age, bmi, egfr, "
       "hgb, albumin, dialysis_yrs, donor_age, cold_ischemia and hla_mismatch_count. The attached registry "
       "coefficients come from a larger study; borrow from them if that helps. All of these were recorded at transplant.")
COVS = ["age", "bmi", "egfr", "hgb", "albumin", "dialysis_yrs", "donor_age", "cold_ischemia"]


class _Fake:
    base_url = "http://localhost:1/v1"
    intent_out = None

    class models:
        @staticmethod
        def list():
            return types.SimpleNamespace(data=[])

    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                name = kw["response_format"]["json_schema"]["name"]
                if name == "intent":
                    out = _Fake.intent_out
                elif name == "role_extraction":
                    out = {"reasoning": "quoted", "time_column": "followup_days",
                           "time_evidence": "Follow-up is in followup_days", "event_column": "died",
                           "event_evidence": "died is 1 when the patient died", "event_value": "1",
                           "event_value_evidence": "died is 1", "stratum_column": None,
                           "covariate_columns": COVS + ["hla_mismatch_count"]}
                elif name == "ask":
                    out = {"reasoning": "q", "question": ""}
                elif name == "refusal":
                    out = {"reasoning": "q", "explanation": ""}
                else:
                    out = {"reasoning": "q", "data": "The cohort has [n] subjects.",
                           "linkage": "Linkage covered [p_covered].",
                           "candidates": "Every admissible candidate was fitted.",
                           "comparison": "The lowest loss was [loss_best].",
                           "selected": "The selected model is [selected_label]."}
                msg = types.SimpleNamespace(content=_j.dumps(out), model_extra={})
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                    usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=10))


def main() -> int:
    import os
    os.environ["BREGSURV_PLANNER"] = "off"
    import app
    app._client = lambda endpoint, api_key: _Fake()
    app.DEFAULT_ENDPOINT = "http://localhost:1/v1"
    print("\n== a request naming a column the file lacks")
    h, s, *_ = app.start_session()
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "declare_roles", "evidence": "Follow-up is in followup_days",
         "external_form": None, "out_of_scope_reason": None},
        {"kind": "describe_external", "evidence": "The attached registry coefficients come from a larger study",
         "external_form": "coefficients", "out_of_scope_reason": None}]}
    h1, _, s1, ui = app.chat_turn({"text": REQ}, h, s, {})
    last = h1[-1][1]
    check(s1.result is None, "nothing is fitted while a named column is missing")
    check("no column called `hla_mismatch_count`" in last and "leave it out" in last,
          "the agent asks about the missing column in plain words", last[:200])
    check("```" not in last and "Reply by number" not in last and "preset letter" not in last,
          "the question carries no release card, numbered list or preset letter", last[:300])
    print("\n== the analyst answers in plain words")
    _Fake.intent_out = {"reasoning": "q", "intents": [
        {"kind": "edit_declaration", "evidence": "Leave that one out",
         "external_form": None, "out_of_scope_reason": None}]}
    h2, _, s2, ui = app.chat_turn({"text": "Leave that one out; use the other eight."}, h1, s1, ui)
    check(s2.result is not None, "the plain reply removes the column and the analysis runs",
          str(h2[-1][1])[:300])
    if s2.result is not None:
        cov = list(s2.result.declaration.covariates)
        check(cov == COVS, "the covariates are the eight the file has", str(cov))
        check(any("hla_mismatch_count" in str(x) for x in (s2.result.declaration.notes or [])),
              "the declaration says what became of the missing column")
    print("\n== a reply without a drop word does not remove anything")
    from bregsurv_agent.state import Session  # noqa: F401
    check(app._drop_missing_reply("use albumin instead", s1, dict(s1.pending)) == {},
          "only a reply that says to leave it out removes the column")
    print(f"\nRESULT: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
