#!/usr/bin/env python3
""" -- retrieved few-shot examples for boundary 1: the bank, the
retrieval, the prompt, the record, and the one safety property (an example's
column name can never reach a declaration). No model, no R, no GPU.

    python mcp/test_fewshot.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "eval"))

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


class _Cap:
    """A client that records the request and answers with a fixed object."""
    base_url = "http://localhost:1/v1"
    seen: dict = {}
    answer: dict = {}

    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                _Cap.seen = kw

                class _M:
                    content = json.dumps(_Cap.answer)

                class _C:
                    finish_reason = "stop"; message = _M()

                class _R:
                    choices = [_C()]; usage = None
                return _R()


def main() -> int:
    from bregsurv_agent import boundary, fewshot, guards, policy, report_v3, textmatch
    from profiles import ALL_PROFILES
    from bank_profiles import BANK_PROFILES
    from verify_corpus import check_item, profile_of
    from merge_bank import check_spans

    # ------------------------------------------------------------ A. the bank
    hdr("A. the bank: verified, disjoint from the corpus, schema-shaped")
    b = fewshot.bank()
    check(b.n >= 250, f"the bank holds at least 250 items ({b.n})")
    r1 = [it for it in b.items if "expect" in it]          # round 1: generated + rewritten
    r2 = [it for it in b.items if "expect" not in it]      # round 2: by error category
    check(len(r1) == 300 and len(r2) > 100, f"round 1 {len(r1)}, round 2 {len(r2)} items")
    bad = 0
    for it in r1:
        ok, problems = check_item(it)
        problems = problems + check_spans(it, it["request"], it["spans"])
        bad += bool(problems)
    check(bad == 0, "every bank item passes the corpus rule and the span rules", f"{bad} failing")
    test_cols = {c.lower() for p in ALL_PROFILES.values() for c in p["columns"]}
    bank_cols = {c.lower() for p in BANK_PROFILES.values() for c in p["columns"]}
    check(not (test_cols & bank_cols), "no bank column name is a corpus column name",
          str(sorted(test_cols & bank_cols)))
    keys = ("reasoning", "time_column", "time_evidence", "event_column", "event_evidence",
            "event_value", "event_value_evidence", "covariate_columns")
    check(all(set(it["example"]) == set(keys) for it in r1),
          "every round-1 example has exactly the schema's fields")
    check(all(set(it["example"]) == set(keys) | {"stratum_column"} for it in r2),
          "every round-2 example has the schema's fields with the strata column")
    ev_ok = all(all((it["example"][k] is None) or (it["example"][k].lower() in it["request"].lower())
                    for k in ("time_evidence", "event_evidence", "event_value_evidence"))
                for it in b.items)
    check(ev_ok, "every evidence field of every example is a verbatim span of its request")
    check(all(len(it["example"]["reasoning"]) > 20 for it in b.items),
          "every example carries a reasoning line")
    desc = [it for it in r1 if it["axes"]["reference"] == "described"]
    resolved = [it for it in desc if it["example"]["time_column"] or it["example"]["event_column"]]
    left = [it for it in desc
            if (it["spans"].get("time") and it["example"]["time_column"] is None)
            or (it["spans"].get("event") and it["example"]["event_column"] is None)]
    check(resolved and left,
          f"described examples show both a resolution ({len(resolved)}) and an honest null ({len(left)})")
    ghost = [it for it in r1 if it["axes"]["perturbation"] == "ghost_column"]
    check(ghost and all("hla_mismatch" in (it["example"]["covariate_columns"] or []) for it in ghost),
          "ghost-column examples quote the absent column as written")
    renal = sum(1 for it in b.items if it["profile"] != "heart_failure")
    check(renal >= 0.7 * b.n, f"the bank leans to kidney and transplant layouts ({renal}/{b.n})")

    # -------------------------------------------------------- B. retrieval
    hdr("B. retrieval: masked BM25, diverse, exclusions honoured, deterministic")
    os.environ["BREGSURV_RETRIEVAL"] = "bm25"   # the hybrid ranking is tested in test_retrieval
    m = fewshot.mask("Follow-up time is in months_followed and death_flag marks the outcome, 3 cohorts",
                     BANK_PROFILES["tx_center_ehr"]["columns"])
    check("months_followed" not in m and "death_flag" not in m and "colname" in m and "num" in m,
          "column names and digits are masked before scoring", m)
    m2 = fewshot.mask("adjust for CAN AGE AT LISTING and can-bmi", BANK_PROFILES["srtr_waitlist"]["columns"])
    check(m2.count("colname") == 2, "the three accepted spellings of a name are masked", m2)
    cols = [c["name"] for c in {"columns": [{"name": n} for n in ALL_PROFILES["kidney"]["columns"]]}["columns"]]
    q = "Follow-up time is in followup_days. Died marks the outcome. Please adjust for age, bmi and egfr."
    ex = b.retrieve(q, cols, k=5)
    check(len(ex) == 5 and all(e.get("_score", 0) > 0 for e in ex), "five scored examples come back")
    check(len({e["template_id"] for e in ex}) == 5, "at most one example per template")
    check(all(not textmatch.names_mentioned(e["request"], cols) for e in ex),
          "no retrieved example names a column of the analyst's file, even as a plain word")
    wide = [c for c in ALL_PROFILES["wide"]["columns"]]      # time, status, age, sex, id ...
    exw = b.retrieve("Follow-up time is in time and status marks the outcome.", wide, k=5)
    check(len(exw) == 5 and all(not textmatch.names_mentioned(e["request"], wide) for e in exw),
          "a file whose columns are ordinary words still gets five examples that avoid them")
    ex2 = b.retrieve(q, cols, k=5)
    check([e["id"] for e in ex] == [e["id"] for e in ex2], "retrieval is deterministic")
    suffix = fewshot.template_suffix(ex[0]["template_id"])
    ex3 = b.retrieve(q, cols, k=5, exclude_template=suffix)
    check(all(fewshot.template_suffix(e["template_id"]) != suffix for e in ex3),
          "exclude_template removes every item of that template", suffix)
    ex4 = b.retrieve(q, cols, k=5, exclude_ids=[e["id"] for e in ex])
    check(not ({e["id"] for e in ex4} & {e["id"] for e in ex}), "exclude_ids is honoured")
    check(len(b.retrieve(q, cols, k=2)) == 2, "k is honoured")
    check(b.retrieve("", cols) == [] and fewshot.template_suffix("a.b.c.d") == "b.c.d",
          "an empty query retrieves nothing; the template suffix drops the profile")
    # a described request should pull described examples up
    qd = "We know how long each patient was followed and whether they reached the endpoint."
    exd = b.retrieve(qd, cols, k=5)
    check(any(e.get("axes", {}).get("reference") == "described" or e.get("category") == "RE" for e in exd),
          "a descriptive request retrieves at least one described example",
          str([e.get("axes", {}).get("reference", e.get("category")) for e in exd]))

    # --------------------------------------------------------- C. the prompt
    hdr("C. the prompt and the record")
    prof = {"columns": [{"name": n} for n in ALL_PROFILES["kidney"]["columns"]]}
    os.environ["BREGSURV_FEWSHOT"] = "off"
    check(boundary.examples_for(q, prof) == (None, None), "BREGSURV_FEWSHOT=off turns the examples off (the ablation arm)")
    os.environ.pop("BREGSURV_FEWSHOT", None)
    check(boundary.examples_for(q, prof)[0] is not None and fewshot.enabled(),
          "few-shot is ON by default (3d.11: measured 2026-09-12, the rule was met on both models)")
    os.environ["BREGSURV_FEWSHOT"] = "on"
    exs, rec = boundary.examples_for(q, prof)
    check(exs is not None and len(exs) == fewshot.DEFAULT_K and rec["k"] == fewshot.DEFAULT_K
          and rec["ids"] == [e["id"] for e in exs] and rec["bank_sha256"] == b.sha256[:16],
          "with it on, examples_for retrieves k and records their ids and the bank hash")
    os.environ["BREGSURV_FEWSHOT"] = "3"
    exs3, rec3 = boundary.examples_for(q, prof)
    check(len(exs3) == 3 and rec3["k"] == 3, "BREGSURV_FEWSHOT=<k> sets k")
    _Cap.answer = {"reasoning": "q", "time_column": "followup_days", "time_evidence": "Follow-up time is in followup_days",
                   "event_column": "died", "event_evidence": "Died marks the outcome",
                   "event_value": None, "event_value_evidence": None,
                   "covariate_columns": ["age", "bmi", "egfr"]}
    boundary.call_log(clear=True)
    out = boundary.extract_roles(_Cap(), "m", q, prof, examples=exs3, few_shot=rec3)
    user = _Cap.seen["messages"][1]["content"]
    check("Worked examples" in user and user.count("Example ") == 3 and user.rstrip().endswith(q),
          "the examples sit between the column list and the request, which comes last")
    check("never copy a name from them" in user, "the block states the rule the policy states")
    check(boundary.CALLS[-1].get("few_shot", {}).get("ids") == rec3["ids"],
          "the call record carries the examples shown")
    boundary.call_log(clear=True)
    boundary.extract_roles(_Cap(), "m", q, prof)
    check("Worked examples" not in _Cap.seen["messages"][1]["content"]
          and "few_shot" not in boundary.CALLS[-1],
          "without examples the prompt and the record are unchanged")
    check("examples" in policy.load("role_extraction") and "never copy a name" in policy.load("role_extraction"),
          "the role-extraction policy explains the examples")
    os.environ.pop("BREGSURV_FEWSHOT", None)

    # ---------------------------------------------------------- D. safety
    hdr("D. an example's column name can never reach a declaration")
    ex_col = next(c for e in exs3 for c in b.columns_of(e) if c not in cols)
    guess = {"reasoning": "q", "time_column": ex_col, "time_evidence": "Follow-up time is in " + ex_col,
             "event_column": "died", "event_evidence": "Died marks the outcome",
             "event_value": None, "event_value_evidence": None,
             "covariate_columns": ["age", ex_col]}
    prof_e = dict(prof, eligible={"time": ["followup_days"], "event": ["died"],
                                  "covariate": ["age", "bmi", "egfr"]})
    backed, unbacked, how = boundary.backed_roles(q, prof_e, guess)
    check(backed.get("time") is None and unbacked.get("time") == ex_col
          and ex_col in (unbacked.get("covariates") or []) and backed.get("covariates") == "age",
          f"a copied example name ({ex_col}) is dropped for the time role and from the covariates",
          f"{backed} {unbacked}")
    from bregsurv_agent.state import Session
    from bregsurv_agent.declaration import Declaration, Verification
    s = Session().with_profile("/x.csv", "D", prof_e).start_turn(q)
    d = Declaration(time_col="followup_days", event_col="died", event_value="1",
                    covariates=["age"], source="model_extraction", covariates_time_zero="yes")
    d.sources = {"time": "quoted", "event": "quoted", "event_value": "reply",
                 "covariates": "quoted", "time_zero": "checkbox"}
    s = s.with_declaration(d, Verification(True, ["ok"]))
    check(guards.audit(s) == [], "the audit passes on the backed declaration", str(guards.audit(s)))
    d2 = Declaration(time_col=ex_col, event_col="died", event_value="1",
                     covariates=["age"], source="model_extraction", covariates_time_zero="yes")
    d2.sources = dict(d.sources)
    s2 = Session().with_profile("/x.csv", "D", prof_e).start_turn(q).with_declaration(d2, Verification(True, ["ok"]))
    check(any("quoted" in v for v in guards.audit(s2)),
          "and refuses a declaration that marks an example's name as quoted")

    # ---------------------------------------------------------- E. report
    hdr("E. report section 7 discloses the examples")
    prov = {"model": {"calls": [{"name": "role_extraction", "prompt_tokens": 1400, "completion_tokens": 90,
                                 "few_shot": rec3}], "served_model": "m"}}
    text = report_v3.render_model_use(prov)
    check("worked example" in text and rec3["ids"][0] in text and "checked against" in text,
          "the report names the examples shown and restates the backing check")
    check("worked example" not in report_v3.render_model_use(
              {"model": {"calls": [{"name": "role_extraction", "prompt_tokens": 800}], "served_model": "m"}}),
          "and says nothing about examples when none were shown")
    os.environ["BREGSURV_FEWSHOT"] = "off"
    check(fewshot.describe().get("enabled") is False and fewshot.describe().get("switch") == "off",
          "describe() reports off, and the switch, when off")
    os.environ.pop("BREGSURV_FEWSHOT", None)
    check(fewshot.describe().get("enabled") is True and fewshot.describe().get("k") == fewshot.DEFAULT_K,
          "describe() reports on by default, with k")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
