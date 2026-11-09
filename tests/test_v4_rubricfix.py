"""Regression tests for defects found in V4 by grading its reports.

No model anywhere (a fake OpenAI-shaped client where a call is made). Block A needs no R;
block B uses R (the profiler, the admissibility gate, the release reader).

  D3   a covariate stored as text under "every other column" enters the declaration and the
       gate refuses it by name (it used to be left out of the fit silently);
  S7   a later message that adds or removes predictors edits the settled set (it used to
       replace it with the names the message wrote);
  E4   one variable on several release rows, one per level, against the cohort's indicator
       columns <variable>_<level>, is read as one coefficient per indicator;
  R3   the report and its prose facts: a refused file is not "no external model was
       supplied"; a release term set aside because it was not chosen is not "a predictor your
       data does not contain"; a precision matrix is not a covariance; "no covariance was
       published" is not printed beside a covariance; under a matched design no event rate
       and no time scale; what happens to an uncovered predictor depends on the recommended
       method; "the table shows what borrowing did" only when something was borrowed;
  R4   the planner's free-text reasons are not printed in the report (they stay in the trace);
  R2   a penalty weight of zero is stated;
  M2   the two-release plan whose step evidence is split by a loaded file name is accepted,
       invented evidence is not (ported from the dev copy).

Run: python mcp/test_v4_rubricfix.py
"""
from __future__ import annotations

import csv
import json
import random
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


def hdr(t):
    print(f"\n== {t}")


class _Fake:
    def __init__(self, reply):
        self.reply, self.user = reply, None
        self.chat = self; self.completions = self

    def create(self, **kw):
        self.user = kw["messages"][-1]["content"]
        msg = type("M", (), {"content": json.dumps(self.reply), "model_extra": {}})()
        ch = type("C", (), {"message": msg, "finish_reason": "stop"})()
        use = type("U", (), {"prompt_tokens": 100, "completion_tokens": 20})()
        return type("R", (), {"choices": [ch], "usage": use, "model": "fake"})()


def _res(design="full cohort", form="coefficients alone", sel="mahalanobis_lasso",
         zero_padded=(), dropped=(), ctx=None, lam=0.01):
    lab = {"internal": "Internal only", "internal_lasso": "Internal only, lasso",
           "kl": "Kullback-Leibler", "mahalanobis_lasso": "Mahalanobis, lasso",
           "mahalanobis_ridge": "Mahalanobis, ridge", "external": "External model, unchanged"}
    bor = {"internal": "none", "internal_lasso": "none", "kl": "kl",
           "mahalanobis_lasso": "mahalanobis", "mahalanobis_ridge": "mahalanobis",
           "external": "external"}
    pen = {"internal": "none", "internal_lasso": "lasso", "kl": "none",
           "mahalanobis_lasso": "lasso", "mahalanobis_ridge": "ridge", "external": "none"}
    keys = (["internal", "internal_lasso"] if form == "none"
            else ["internal", sel, "external"] if sel not in ("internal", "external")
            else ["internal", "kl", "external"])
    if sel not in keys:
        keys.append(sel)
    cands = []
    for i, k in enumerate(keys):
        c = {"key": k, "label": lab[k], "status": "ok", "loss": 7.0 + 0.1 * i,
             "eta": (2.0 if bor[k] not in ("none", "external") else None),
             "lambda": (lam if pen[k] != "none" else None), "n_nonzero": 5,
             "borrowing": bor[k], "penalty": pen[k]}
        cands.append(c)
    s = dict(next(c for c in cands if c["key"] == sel))
    s["loss"] = 6.9
    zp = list(zero_padded)
    covered = [f"x{i}" for i in range(1, 6 - len(zp))]
    res = {"facts": {"design": design, "external_form": form, "n": 400, "n_events": 120,
                     "p": len(covered) + len(zp), "p_covered": len(covered),
                     "p_internal_only": len(zp)},
           "candidates": cands, "selected": s, "criteria": "V&VH",
           "partition": {"nfolds": 5, "seed": 20260818},
           "linkage": {"covered": covered, "zero_padded": zp, "dropped": list(dropped),
                       "matched_by": "name"},
           "coefficients": [{"variable": v, "beta_external": 0.1, "covered_by_external": v in covered,
                             "beta_internal": 0.2, "beta_selected": 0.15}
                            for v in covered + zp]}
    if ctx is not None:
        res["report_context"] = ctx
    return res


def block_a():
    from bregsurv_agent import report_v3 as R, boundary as B, external as X
    from bregsurv_agent import prose_examples as PE
    from bregsurv_agent.declaration import complete, text_columns

    hdr("A1. D3: a text covariate under 'every other column' enters the declaration")
    prof = {"columns": [
        {"name": "age", "type": "numeric", "can_be_covariate": True, "n_distinct": 50},
        {"name": "bmi", "type": "numeric", "can_be_covariate": True, "n_distinct": 50},
        {"name": "sex", "type": "character", "can_be_covariate": False, "can_be_event": True,
         "n_distinct": 2, "values": ["F", "M"]},
        {"name": "pid", "type": "character", "can_be_covariate": False, "n_distinct": 100,
         "quarantine": "one distinct value per subject: looks like an identifier"},
        {"name": "visit_date", "type": "Date", "can_be_covariate": False, "can_be_time": True,
         "n_distinct": 90},
        {"name": "status", "type": "character", "can_be_covariate": False, "can_be_event": True,
         "n_distinct": 2, "values": ["Alive", "Dead"]},
        {"name": "days", "type": "integer", "can_be_covariate": True, "can_be_time": True,
         "n_distinct": 80},
        {"name": "died", "type": "integer", "can_be_covariate": True, "can_be_event": True,
         "n_distinct": 2, "values": ["0", "1"]}],
        "eligible": {"time": ["days", "visit_date"], "event": ["sex", "status", "died"],
                     "covariate": ["age", "bmi", "days", "died"], "stratum": []}}
    check(text_columns(prof, ["days", "died", "status"]) == ["sex"],
          "text_columns: sex only (not the id, not the date, not the outcome)",
          str(text_columns(prof, ["days", "died", "status"])))
    comp = complete(prof, {"time": "days", "event": "died", "event_value": "1",
                           "time_zero": "yes"})
    check(comp.answers.get("covariates") == "B plus sex, status",
          "complete(): the inferred set is preset B plus the text column", str(comp.answers))
    check("stores as text" in comp.sources.get("covariates", ""),
          "the source names the text column", comp.sources.get("covariates", ""))
    comp2 = complete({**prof, "columns": [c for c in prof["columns"] if c["name"] not in ("sex", "status")]},
                     {"time": "days", "event": "died", "event_value": "1", "time_zero": "yes"})
    check(comp2.answers.get("covariates") == "B",
          "without a text column the inferred set is unchanged (preset B)", str(comp2.answers))
    msg = "Time is days, event is died (1 = death). Please adjust for sex and all the other columns."
    b, u, s = B.backed_roles(msg, prof, {"time_column": "days", "event_column": "died",
                                         "event_value": "1",
                                         "covariate_columns": ["age", "bmi", "sex"]})
    check(b.get("covariates") == "B plus sex, status",
          "rest phrase: the every-column rule carries the text column", str(b))

    hdr("A2. S7: a later message edits the settled predictor set")
    prof7 = {"columns": [{"name": n} for n in ("age", "egfr", "sodium", "smoker", "prior_mi",
                                                 "days", "death")],
             "eligible": {"time": ["days"], "event": ["death"],
                          "covariate": ["age", "egfr", "sodium", "smoker", "prior_mi"]}}
    msg7 = "Please also add smoker and prior_mi to the covariates."
    full = {"covariate_columns": ["age", "egfr", "sodium", "smoker", "prior_mi"]}
    b0, _, _ = B.backed_roles(msg7, prof7, full)
    check(b0.get("covariates") == "smoker, prior_mi",
          "without the settled set only the written names are backed (the old behaviour)", str(b0))
    b1, u1, s1 = B.backed_roles(msg7, prof7, full, ["age", "egfr", "sodium"])
    check(b1.get("covariates") == "age, egfr, sodium, smoker, prior_mi"
          and s1.get("covariates", "").startswith("quoted ("),
          "with the settled set the complete set after the change is backed", str((b1, s1)))
    b2, _, _ = B.backed_roles("Drop sodium.", prof7, {"covariate_columns": ["age", "egfr"]},
                              ["age", "egfr", "sodium"])
    check(b2.get("covariates") == "age, egfr", "a removal: the rest of the settled set stays", str(b2))
    b3, u3, _ = B.backed_roles("Drop sodium.", prof7, {"covariate_columns": ["age", "egfr", "bnp"]},
                               ["age", "egfr", "sodium"])
    check("bnp" not in str(b3.get("covariates")), "a name neither written nor settled is still dropped", str(b3))
    fk = _Fake({"reasoning": "the message adds smoker and prior_mi to the declared six",
                "time_column": None, "time_evidence": None, "event_column": None,
                "event_evidence": None, "event_value": None, "event_value_evidence": None,
                "stratum_column": None,
                "covariate_columns": ["age", "egfr", "sodium", "smoker", "prior_mi"]})
    B.extract_roles(fk, "fake", msg7, prof7,
                    current={"time": "days", "event": "death", "event_value": "1",
                             "covariates": ["age", "egfr", "sodium"]})
    check(fk.user and "Already declared" in fk.user and "age, egfr, sodium" in fk.user
          and "COMPLETE predictor set" in fk.user,
          "the role reading is shown the settled roles when a message may edit them", (fk.user or "")[:200])
    fk2 = _Fake(fk.reply)
    B.extract_roles(fk2, "fake", msg7, prof7)
    check("Already declared" not in (fk2.user or ""), "a first message gets no settled block")

    hdr("A3. external: card and refusal wording")
    ext = X.ExternalObject(form="coefficients_with_covariance", scale="log_hazard_ratio",
                           terms={"a": 0.1, "b": 0.2},
                           provenance={"file": "r.json", "format": "json", "n_tables": 2},
                           Q=[[1.0, 0.0], [0.0, 1.0]], Q_from="inverse of the published covariance",
                           se={"a": 0.1, "b": 0.1})
    card = "\n".join(ext.card())
    check("no covariance was published" not in card and "the matrix above carries them" in card,
          "with a covariance, the SE line does not say none was published", card)
    ext2 = X.ExternalObject(form="coefficients", scale="log_hazard_ratio", terms={"a": 0.1},
                            provenance={"file": "r.csv", "format": "csv", "n_tables": 1},
                            se={"a": 0.1})
    check("no covariance was published" in "\n".join(ext2.card()),
          "without one it still says so")

    hdr("A4. report: a refused release, a matched design, the linkage, the planner")
    rr = {"release_refused": {"file": "external_scores.csv",
                              "reasons": ["table 'external_scores' holds 400 rows ..."]}}
    r_ref = _res(form="none", sel="internal_lasso", ctx=rr)
    rep = R.render(r_ref)
    check("could not be used" in rep and "external_scores.csv" in rep
          and "No external model was supplied" not in rep,
          "a refused file is named, with its reason, and not called absent")
    check("what borrowing actually did" not in rep and "nothing was borrowed" in rep,
          "section 5 does not claim borrowing for a cohort-alone fit")
    check("two ways of **not** borrowing" not in rep,
          "section 3 does not claim the external model unchanged was in the set")
    refs = R.build_references(r_ref)
    facts = " ".join(R.prose_facts(r_ref, refs))
    check("could not be used" in facts and not R.check_no_digits(facts),
          "the prose facts say the file could not be used, with no digit", facts[:300])
    check(PE.features_of(r_ref, refs)["refused"] == 1
          and all("No external information was supplied" not in json.dumps(e["sections"])
                  for e in PE.nearest(PE.features_of(r_ref, refs), 2)),
          "the nearest prose examples for a refused file do not say none was supplied")
    check(all(not R.check_no_digits(json.dumps(e["sections"]) + " ".join(e["facts"]))
              and "pulled toward" not in json.dumps(e["sections"]) for e in PE.bank()),
          "every prose example is digit-free and never says each coefficient is pulled")

    r_nf = _res(form="none", sel="internal_lasso")
    rep_nf = R.render(r_nf)
    check("No external model was supplied" in rep_nf and "two ways of **not** borrowing" not in rep_nf,
          "no external file at all: as before, minus the false 'two ways' sentence")

    r_cc = _res(design="nested case-control")
    refs_cc = R.build_references(r_cc)
    check("event_rate" not in refs_cc and "outcome_scale" not in refs_cc,
          "matched design: no event rate and no time scale are offered", str(sorted(refs_cc)))
    check(R.resolve("an event rate of [event_rate] percent", {"event_rate": 20.0}) == "an event rate of 20%",
          "'[event_rate] percent' renders one percent sign")

    ctx_d = {"dropped_in_file": ["htn", "dm"], "dropped_absent": [], "selected_pad_absent": False}
    r_d = _res(dropped=["htn", "dm"], ctx=ctx_d)
    rep_d = R.render(r_d)
    check("not among your predictors" in rep_d and "your data does not contain" not in rep_d,
          "a release term not chosen is not called absent from the data")
    fd = " ".join(R.prose_facts(r_d, R.build_references(r_d)))
    check("never say that it lacks them" in fd, "and the prose writer is told so")
    ctx_a = {"dropped_in_file": [], "dropped_absent": ["hla"], "selected_pad_absent": False}
    check("your data does not contain" in R.render(_res(dropped=["hla"], ctx=ctx_a)),
          "a release term the file lacks is still called absent")

    r_p = _res(form="coefficients and covariance", ctx={"matrix_role": "precision"})
    check(R.form_words(r_p) == "coefficients and precision matrix"
          and "coefficients and precision matrix" in R.render(r_p)
          and R.build_references(r_p)["external_form"] == "coefficients and precision matrix",
          "a released precision matrix is not called a covariance")

    check("drawn toward zero" in R.render(_res(sel="kl", zero_padded=["z1"]))
          and "receives no borrowing" not in R.render(_res(sel="kl", zero_padded=["z1"])),
          "KL recommended: an uncovered predictor is drawn toward zero as the weight grows")
    check("does not act" in R.render(_res(zero_padded=["z1"], ctx={"selected_pad_absent": False})),
          "masked Mahalanobis: an uncovered predictor is estimated from the data")
    check("padded with zero" in R.render(_res(zero_padded=["z1"], ctx={"selected_pad_absent": True})),
          "zero-padded Mahalanobis: the report says so")
    check("For a variable your data has" not in R.render(_res()),
          "full coverage: no sentence about uncovered predictors")

    check("penalty weight of **0**" in R.render(_res(sel="mahalanobis_ridge", lam=0.0)),
          "a ridge weight of zero is stated")
    check(R._fmt(61040.3) == "61040", "a large value is printed whole, not in e-notation", R._fmt(61040.3))

    plan = {"row": "cox", "reason": "the plan is optimal and robust",
            "members": [{"key": "internal", "reason": "a benchmark"},
                        {"key": "mahalanobis_lasso", "reason": "has the lowest cross-validated loss"},
                        {"key": "external", "reason": "the release is already well calibrated"}]}
    steps = [{"step": "fit", "members": ["internal", "mahalanobis_lasso", "external"], "units": 3},
             {"step": "next", "action": "finish", "reason": "no refinement would change the winner"}]
    rp = R.render(_res(), plan=plan, plan_steps=steps, n_admissible=10)
    check(all(w not in rp for w in ("optimal", "has the lowest cross-validated loss", "well calibrated",
                                     "no refinement would change", "a benchmark")),
          "the planner's words are not in the report")
    check("trace.json" in rp and "Of the **10** admissible methods, **3** were fitted" in rp,
          "the report says where they are kept and what was fitted")

    hdr("A5. M2: step evidence split by a loaded file name (ported from the dev copy)")
    msg = ("Run the analysis once with each of them, kp_release_KP.json and kp_release_US.json, "
           "and then compare the two runs.")
    exts = ["kp_release_KP.json", "kp_release_US.json"]
    ok = B.validate_steps(msg, {"steps": [
        {"act": "select_external", "external": "kp_release_KP.json",
         "evidence": "once with kp_release_KP.json"},
        {"act": "run", "external": None, "evidence": "Run the analysis"}]}, exts, 0)
    check(len(ok) >= 2 and ok[0]["act"] == "select_external",
          "'once with kp_release_KP.json' is accepted", str(ok))
    bad = B.validate_steps(msg, {"steps": [
        {"act": "select_external", "external": "kp_release_KP.json",
         "evidence": "use the Kaiser file first with kp_release_KP.json"},
        {"act": "run", "external": None, "evidence": "Run the analysis"}]}, exts, 0)
    check(len(bad) == 0, "invented evidence is rejected (the plan is cut at that step)", str(bad))


def _write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def block_b():
    from bregsurv_agent.rbridge import _run_r
    from bregsurv_agent import external as X
    from bregsurv_agent.declaration import parse_reply, verify, complete

    random.seed(7)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        coh = tdp / "cohort.csv"
        rows = []
        for i in range(150):
            rows.append([round(random.gauss(0, 1), 4), round(random.gauss(0, 1), 4),
                         random.choice(["F", "M"]), random.randint(5, 900), random.randint(0, 1)])
        _write(coh, ["age", "bmi", "sex", "followup_days", "died"], rows)
        prof = _run_r("profile_columns.R", {"data_path": str(coh), "data_expr": "cohort"})

        hdr("B1. D3 end to end: the gate refuses the text covariate by name")
        comp = complete(prof, {"time": "followup_days", "event": "died", "event_value": "1",
                               "time_zero": "yes"})
        d = parse_reply(prof, comp.answers)
        check("sex" in d.covariates, "the declaration carries sex", str(d.covariates))
        v = verify(prof, d, str(coh), "cohort", run_r=_run_r)
        codes = [r.get("code") for r in v.refusals]
        check(not v.admissible and "covariate_not_numeric" in codes
              and "sex" in json.dumps(v.refusals),
              "covariate_not_numeric, naming sex", str(codes))
        d2 = parse_reply(prof, {"time": "followup_days", "event": "died", "event_value": "1",
                                "covariates": "age, sex", "time_zero": "yes"})
        v2 = verify(prof, d2, str(coh), "cohort", run_r=_run_r)
        check(not v2.admissible and "covariate_not_numeric" in [r.get("code") for r in v2.refusals],
              "a text covariate named explicitly is refused by name too")
        d3 = parse_reply(prof, {"time": "followup_days", "event": "died", "event_value": "1",
                                "covariates": "B", "time_zero": "yes"})
        check("sex" not in d3.covariates, "an explicit '4) B' still means the numeric columns")

        hdr("B2. E4: per-level release rows matched to indicator columns")
        rel = tdp / "external_coefficients.csv"
        _write(rel, ["variable", "level", "coefficient"],
               [["age", "", 0.4], ["bmi", "", -0.2], ["grp", "B", 0.3], ["grp", "C", -0.1]])
        cohort_cols = ["age", "bmi", "grp_B", "grp_C", "followup_days", "died"]
        obj = X.read_external(str(rel), run_r=_run_r, cohort_columns=cohort_cols)
        check(set(obj.terms) == {"age", "bmi", "grp_B", "grp_C"} and abs(obj.terms["grp_B"] - 0.3) < 1e-12,
              "levels B and C become grp_B and grp_C", str(obj.terms))
        check(obj.provenance.get("per_level") and any("grp_B" in n for n in obj.notes),
              "the mapping is recorded and disclosed", str(obj.notes))
        try:
            X.read_external(str(rel), run_r=_run_r)
            check(False, "without the cohort's columns the per-level table is still refused")
        except X.ExternalRefusal as exc:
            check("names_not_unique" in [r["code"] for r in exc.reasons],
                  "without the cohort's columns the per-level table is still refused")
        try:
            X.read_external(str(rel), run_r=_run_r,
                            cohort_columns=["age", "bmi", "grp_B", "followup_days", "died"])
            check(False, "a level with no indicator column in the cohort is refused")
        except X.ExternalRefusal as exc:
            check("names_not_unique" in [r["code"] for r in exc.reasons],
                  "a level with no indicator column in the cohort is refused")

        hdr("B3. E3: a per-subject score file is refused without being called a coefficient table")
        sc = tdp / "external_scores.csv"
        _write(sc, ["patient_id", "risk_score"], [[f"P{i:04d}", round(random.random(), 3)]
                                                   for i in range(50)])
        try:
            X.read_external(str(sc), run_r=_run_r, cohort_columns=cohort_cols)
            check(False, "the score file is refused")
        except X.ExternalRefusal as exc:
            m = json.dumps(exc.reasons)
            check("no_term_matches_cohort" in m and "not a table of coefficients" in m,
                  "refused, and described as not a coefficient table", m[:300])


def main() -> int:
    block_a()
    if "--no-r" not in sys.argv:
        block_b()
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
