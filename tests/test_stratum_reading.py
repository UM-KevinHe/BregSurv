"""A stratum or matched-set column the analyst NAMES reaches the declaration from prose
(2026-09-30, found by the simulation prompt search: the role reading had no field for it, so
"stratify by stratum" ran an unstratified cohort and a matched sample always cost a design
question), and another cohort's records in the analyst's own layout take their outcome columns
from the declaration when the reading cannot name them (the matched sample `set_id, cc_status,
Z1..Z20` was refused as `individual_roles_unnamed`).

Run: python mcp/test_stratum_reading.py      (needs Rscript for blocks C and D)
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    passed += bool(ok); failed += not ok
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))


def _write(path: Path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    from bregsurv_agent import boundary as B, fewshot, external as X
    from bregsurv_agent.declaration import complete, parse_reply

    print("A. the schema and the examples")
    props = B.ROLE_EXTRACTION_SCHEMA["properties"]
    check("stratum_column" in props and "null" in props["stratum_column"]["type"],
          "stratum_column is a nullable field of the reading")
    check("stratum_column" in B.ROLE_EXTRACTION_SCHEMA["required"], "and a required one")
    ex = fewshot.bank().items[:1]
    check('"stratum_column": null' in fewshot.render(ex), "an example renders it as null")
    check("stratum_column" in B._EXTRACT_SYSTEM, "the policy names the field")

    print("B. the backing check: quoted or nothing")
    cols = ["stratum", "time", "status"] + [f"Z{i}" for i in range(1, 21)]
    prof = {"columns": [{"name": c} for c in cols],
            "eligible": {"time": ["time"], "event": ["status"], "stratum": ["stratum"]}}
    msg = "Follow-up time is time and status = 1 is the event; please stratify by stratum."
    b, u, s = B.backed_roles(msg, prof, {"time_column": "time", "event_column": "status",
                                         "event_value": "1", "stratum_column": "stratum",
                                         "covariate_columns": None})
    check(b.get("stratum") == "stratum" and s.get("stratum") == "quoted", "a written stratum is quoted")
    b, u, s = B.backed_roles("Follow-up time is time and status is the event.", prof,
                             {"time_column": "time", "event_column": "status",
                              "stratum_column": "stratum", "covariate_columns": None})
    check("stratum" not in b and u.get("stratum") == "stratum",
          "a stratum the message does not write is dropped and logged", str(u))
    # 2026-09-30, prompt search strat_v3: the reading gave `stratum` the strata role AND listed it
    # as the only covariate; the run stopped on "the outcome is listed among the predictors"
    msg3 = ("We followed patients in several strata, recorded in the column stratum. The column "
            "time holds each patient's follow-up and status records whether the event happened (1) "
            "or not (0); every other column is a candidate predictor.")
    b, u, s = B.backed_roles(msg3, prof, {"time_column": "time", "event_column": "status",
                                          "stratum_column": "stratum",
                                          "covariate_columns": ["stratum"]})
    check(b.get("stratum") == "stratum" and "covariates" not in b,
          "a column read as the strata is not also taken as a predictor", str(b))
    check(u.get("covariates_named_as_role") == ["stratum"] and "covariates" not in u,
          "it is logged under its own key, not reported as a name the analyst did not write", str(u))
    b, u, s = B.backed_roles(msg3, prof, {"time_column": "time", "event_column": "status",
                                          "stratum_column": "stratum",
                                          "covariate_columns": ["stratum", "Z1", "Z2"]})
    check("covariates" not in b and u.get("covariates_named_as_role") == ["stratum"],
          "with unwritten columns listed too, the covariates still fall to the rule", str((b, u)))
    from bregsurv_agent.declaration import Declaration, _own_checks
    codes = [r["code"] for r in _own_checks(prof, Declaration(
        time_col="time", event_col="status", event_value="1", stratum_col="stratum",
        covariates=["Z1", "stratum"], source="reply", covariates_time_zero="yes"))]
    check("stratum_used_as_covariate" in codes and "outcome_used_as_covariate" not in codes,
          "the strata column typed as a predictor is refused as what it is", str(codes))
    import app as _app
    check(_app._ITEM_OF_REFUSAL.get(_app._refusal_family("stratum_used_as_covariate")) == "4",
          "and the refusal points at item 4")

    from bregsurv_agent.rbridge import _run_r, _find_rscript
    if not _find_rscript():
        print("  SKIP  C, D: no Rscript")
        return 0 if not failed else 1
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        import random
        rnd = random.Random(7)
        # a stratified cohort: 5 strata of 20
        rows = []
        for s_ in range(1, 6):
            for i in range(20):
                rows.append([s_, round(rnd.expovariate(1.0), 4), int(rnd.random() < 0.7)]
                            + [round(rnd.gauss(0, 1), 4) for _ in range(3)])
        coh = td / "coh.csv"
        _write(coh, ["stratum", "time", "status", "Z1", "Z2", "Z3"], rows)
        # a 1:5 matched sample: 40 sets of 6
        mrows = []
        for s_ in range(1, 41):
            for j in range(6):
                mrows.append([s_, int(j == 0)] + [round(rnd.gauss(0, 1), 4) for _ in range(3)])
        ncc = td / "ncc_train.csv"
        _write(ncc, ["set_id", "cc_status", "Z1", "Z2", "Z3"], mrows)
        ncc_ext = td / "ncc_external.csv"
        _write(ncc_ext, ["set_id", "cc_status", "Z1", "Z2", "Z3"], mrows[:120])

        print("C. the stratum reaches the declaration and fixes the design")
        pc = _run_r("profile_columns.R", {"data_path": str(coh), "data_expr": "coh"})
        comp = complete(pc, {"time": "time", "event": "status", "event_value": "1",
                             "stratum": "stratum", "covariates": "B", "time_zero": "yes"},
                        sources={"time": "quoted", "stratum": "quoted"})
        check(comp.ready and not comp.missing, "a quoted time and stratum ask nothing", str(comp.missing))
        d = parse_reply(pc, dict(comp.answers))
        check(d.stratum_col == "stratum" and d.time_col == "time", "a stratified cohort is declared")
        check("stratum" not in d.covariates and "time" not in d.covariates,
              "the stratum is not swept into the preset", str(d.covariates))
        pn = _run_r("profile_columns.R", {"data_path": str(ncc), "data_expr": "ncc_train"})
        comp = complete(pn, {"event": "cc_status", "event_value": "1", "stratum": "set_id",
                             "covariates": "B", "time_zero": "yes"},
                        sources={"stratum": "quoted", "event": "quoted"})
        check(comp.ready and not comp.missing, "a quoted matched set with no time asks nothing",
              str(comp.missing))
        d = parse_reply(pn, dict(comp.answers))
        check(d.time_col is None and d.stratum_col == "set_id", "a matched design is declared")

        print("D. a release in the cohort's layout takes its outcome from the declaration")
        tables = X.read_tables(str(ncc_ext), run_r=_run_r)
        prov = {"path": str(ncc_ext), "file": ncc_ext.name}
        asg = [{"table": tables[0].name, "role": "individual_level_data"}]
        obj = X.canonicalise(tables, asg, prov, cohort_columns=["set_id", "cc_status", "Z1", "Z2", "Z3"])
        dd = obj.individual_data
        check(obj.form == "individual_level_data" and dd.get("outcome_from_declaration")
              and dd.get("event_column") is None, "accepted, the outcome left to the declaration")
        check(any("taken from your declaration" in n for n in obj.notes), "and the card says so")
        try:
            X.canonicalise(tables, asg, prov, cohort_columns=["a", "b", "c", "d", "e"])
            refused = False
        except X.ExternalRefusal:
            refused = True
        check(refused, "a table in another layout with no named event is still refused")

        print("E. a set id read as the follow-up time reopens the design, sets irregular or not")
        irows = []
        for s_ in range(1, 61):
            k = 6 if s_ <= 40 else rnd.choice([2, 3, 4, 5])      # late sets short
            for j in range(k):
                irows.append([s_, int(j == 0)] + [round(rnd.gauss(0, 1), 4) for _ in range(3)])
        irr = td / "irr.csv"
        _write(irr, ["set_id", "cc_status", "Z1", "Z2", "Z3"], irows)
        pi_ = _run_r("profile_columns.R", {"data_path": str(irr), "data_expr": "irr"})
        sid = next(c for c in pi_["columns"] if c["name"] == "set_id")
        check(not sid.get("regular_sets") and "cc_status" in (sid.get("one_case_per_set") or []),
              "irregular sets: not regular, but one case in every set", str({k: sid.get(k) for k in ("regular_sets", "one_case_per_set")}))
        comp = complete(pi_, {"time": "set_id", "event": "cc_status", "event_value": "1",
                              "covariates": "B", "time_zero": "yes"},
                        sources={"time": "quoted", "event": "quoted"})
        check("0" in comp.missing and "1" in comp.missing, "the design question is asked", str(comp.missing))
        st = next(c for c in pc["columns"] if c["name"] == "stratum")
        check(not st.get("one_case_per_set"), "the strata of a cohort are not read as matched sets")
    print(f"\n{passed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
