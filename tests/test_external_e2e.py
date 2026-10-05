"""M5: external information in every shape analysts have, read into one shape.

What is checked, without a model:

  * the READ step: csv, json (three shapes), xlsx (two sheets), rds (an R
    list) all come back as tables with column facts and no rows;
  * the ASSIGN step's harness half: a column the model names that is not in
    the table is caught, and the object is refused for the right reason;
  * the VERIFY step: every refusal code fires on the fixture built to fire it
    (an interval that does not bracket, a per-level table, a singular
    covariance, mismatched names, a broken cumulative hazard, a file with no
    coefficient table), and every accepted fixture yields the expected form,
    term count and conversion record;
  * the two conversions the design allows -- a hazard ratio logged, a
    covariance inverted -- are exact and recorded;
  * end to end: the app reads a coefficients+covariance file, the run's form is
    "coefficients and covariance", the precision matrix is in the C3 hash and
    in repro.R, and repro.R replays the run; the individual-level path is
    refused by name when the external cohort's columns do not line up;
  * the private SRTR release files, when present (`BREGSURV_PRIVATE_FIXTURES`
    or ../real_data/external_fixtures), read as expected; SKIPPED otherwise.

The model's own assignments are measured live in gl_boundary_check.py.

Run:  python test_external_e2e.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent import external as X  # noqa: E402
from bregsurv_agent.rbridge import _find_rscript, _run_r  # noqa: E402

FIX = REPO / "eval" / "fixtures" / "external"
PRIV = Path(os.environ.get("BREGSURV_PRIVATE_FIXTURES",
                           str(REPO.parent / "real_data" / "external_fixtures")))

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m", "\033[2m",
                             "\033[0m")
passed = failed = skipped = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")
    return ok


def skip(label, note=""):
    global skipped
    skipped += 1
    print(f"  {YEL}SKIP{OFF}  {label}   {DIM}{note}{OFF}")


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def refused(path, **kw):
    """Read through the heuristic; return the refusal codes, or None."""
    try:
        X.read_external(str(path), run_r=_run_r, **kw)
        return None
    except X.ExternalRefusal as exc:
        return [r["code"] for r in exc.reasons]


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="bregsurv_m5_"))

    # ---- 1. READ ----------------------------------------------------------
    hdr("1. read: every supported shape comes back as tables, never rows")
    t = X.read_tables(str(FIX / "paper_table_hr_ci.csv"))
    check(len(t) == 1 and [c["name"] for c in t[0].columns]
          == ["Variable", "HR", "95% CI lower", "95% CI upper", "p-value"],
          "a csv is one table with its headers", str([c["name"] for c in t[0].columns]))
    s = X.summarize(t)
    check("HR" in s and "min" in s and "1.66" not in s.split("\n")[0]
          and all(str(v) not in s for v in ("0.76", "1.30")),
          "the summary shows names, types and ranges -- not the rows",
          s.splitlines()[2][:70])
    t = X.read_tables(str(FIX / "coefs_and_vcov.json"))
    check(len(t) == 2 and {x.name for x in t}
          == {"coefs_and_vcov.coefficients", "coefs_and_vcov.vcov"},
          "a json with records and a dict-of-dicts gives two tables",
          str([x.name for x in t]))
    t = X.read_tables(str(FIX / "coefs_dict.json"))
    check(len(t) == 1 and [c["name"] for c in t[0].columns] == ["name", "value"],
          "a json dictionary of numbers is a two-column table")

    # xlsx: two sheets, written here (needs openpyxl, which the app venv has)
    xlsx = td / "coefs_and_vcov.xlsx"
    try:
        import pandas as pd
        obj = json.loads((FIX / "coefs_and_vcov.json").read_text())
        names = [r["name"] for r in obj["coefficients"]]
        with pd.ExcelWriter(xlsx) as w:
            pd.DataFrame(obj["coefficients"]).to_excel(w, "coefficients", index=False)
            vc = pd.DataFrame([[obj["vcov"][a][b] for b in names] for a in names],
                              columns=names)
            vc.insert(0, "variable", names)
            vc.to_excel(w, "vcov", index=False)
        t = X.read_tables(str(xlsx))
        check(len(t) == 2 and all(":" in x.name for x in t),
              "an xlsx gives one table per sheet", str([x.name for x in t]))
    except ImportError as exc:
        skip("xlsx read (openpyxl not installed)", str(exc)[:60])
        xlsx = None

    # rds: an R list with a named vector and a matrix, written by Rscript
    rds = td / "coefs_and_vcov.rds"
    rscript = _find_rscript()
    r = subprocess.run([rscript, "-e",
                        f'b <- c(age=0.51, bmi=-0.27, egfr=-0.42); '
                        f'V <- diag(c(0.0064, 0.01, 0.0081)); dimnames(V) <- list(names(b), names(b)); '
                        f'saveRDS(list(beta=b, vcov=V), "{rds.as_posix()}")'],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if rds.exists():
        t = X.read_tables(str(rds), run_r=_run_r)
        kinds = {x.name.split(":")[-1]: x.source for x in t}
        check(len(t) == 2 and "coefs_and_vcov$beta" in kinds
              and "coefs_and_vcov$vcov" in kinds,
              "an rds holding an R list gives its vector and its matrix",
              str(kinds))
    else:
        skip("rds read (Rscript could not write the fixture)", r.stderr[-120:])
        rds = None

    for name, code in (("notes_only.pdf", "unsupported_format"),):
        p = td / name
        p.write_bytes(b"%PDF-1.4 fake")
        check(refused(p) == [code], f"{name}: refused as {code}")

    # ---- 2. ASSIGN, the harness half -------------------------------------
    hdr("2. assignment: a column the model names must exist")
    tabs = X.read_tables(str(FIX / "paper_table_hr_ci.csv"))
    raw = {"reasoning": "x", "tables": [{
        "table": tabs[0].name, "role": "coefficients", "name_column": "Variable",
        "coefficient_column": "hazard_ratio",      # not a column of this table
        "coefficient_scale": "hazard_ratio", "se_column": None,
        "ci_lower_column": "95% CI lower", "ci_upper_column": "95% CI upper",
        "time_column": None, "hazard_column": None,
        "cumulative_hazard_column": None, "event_column": None,
        "event_value": None}]}
    asg, issues = X.check_assignment(tabs, raw)
    check(issues and issues[0]["code"] == "unknown_column"
          and asg[0]["coefficient_column"] is None,
          "an invented column name is recorded as an issue and nulled",
          issues[0]["message"][:80])
    try:
        X.canonicalise(tabs, asg, {"file": "x"})
        check(False, "and the object is refused for the right reason")
    except X.ExternalRefusal as exc:
        check(exc.reasons[0]["code"] == "coefficient_columns_unnamed",
              "and the object is refused for the right reason",
              exc.reasons[0]["code"])
    raw2 = {"reasoning": "x", "tables": [{"table": "no_such_table",
                                           "role": "coefficients"}]}
    asg2, issues2 = X.check_assignment(tabs, raw2)
    check(issues2[0]["code"] == "unknown_table" and asg2[0]["role"] == "ignore",
          "an invented table is dropped and the real one falls to `ignore`")

    # ---- 3. VERIFY on every fixture ---------------------------------------
    hdr("3. verify: accepted shapes and every refusal code")
    o = X.read_external(str(FIX / "coefs_two_columns.csv"), run_r=_run_r)
    check(o.form == "coefficients" and len(o.terms) == 6
          and o.provenance["converted_from"] is None
          and o.provenance["assigned_by"] == "heuristic",
          "two columns -> 6 log-scale coefficients (the demo shape)")
    o = X.read_external(str(FIX / "paper_table_hr_ci.csv"), run_r=_run_r)
    import math
    check(o.form == "coefficients" and o.provenance["converted_from"] == "hazard_ratio"
          and abs(o.terms["age"] - math.log(1.66)) < 1e-12
          and o.provenance["coefficient_column"] == "HR",
          "a paper's HR table -> logged, conversion recorded",
          f"age {o.terms['age']:.4f} = log(1.66)")
    check(refused(FIX / "bad_ci.csv") == ["ci_does_not_bracket"],
          "an interval that does not bracket its estimate is refused")
    check(refused(FIX / "per_level.csv") == ["names_not_unique"],
          "a per-level table is refused: one row per variable",
          "the SRTR 2026 shape; the analyst reduces it first")
    o = X.read_external(str(FIX / "coefs_and_vcov.json"), run_r=_run_r)
    check(o.form == "coefficients_with_covariance" and o.Q is not None
          and o.Q_from.startswith("inverse of the published covariance")
          and "shrunk 10% toward the identity" in o.Q_from
          and o.se and abs(o.se["age"] - 0.08) < 1e-12,
          "coefficients + covariance (json) -> precision by inversion, conditioned, se recorded",
          f"Q {len(o.Q)}x{len(o.Q)}; {o.Q_from}")
    import numpy as np
    obj = json.loads((FIX / "coefs_and_vcov.json").read_text())
    V = np.array([[obj["vcov"][a][b] for b in o.terms] for a in o.terms])
    Qi = np.linalg.inv(V)
    Qc = (1 - X.Q_SHRINK) * Qi / np.mean(np.diag(Qi)) + X.Q_SHRINK * np.eye(len(V))
    mc = o.provenance.get("matrix_conditioning") or {}
    check(np.allclose(np.array(o.Q), Qc, atol=1e-9)
          and abs(mc.get("mean_diagonal_final", 0) - 1.0) < 1e-9
          and mc.get("kappa_final", np.inf) <= mc.get("kappa_raw", 0) + 1e-9,
          "Q is the inverse covariance scaled to unit mean diagonal and shrunk 10% toward I "
          "(the MIUM/SRTR convention), recorded in the provenance",
          f"kappa {mc.get('kappa_raw', 0):.3g} -> {mc.get('kappa_final', 0):.3g}")
    check(refused(FIX / "vcov_singular.json") == ["covariance_singular"],
          "a singular covariance is refused, with the advice to supply Q")
    check(refused(FIX / "vcov_names_mismatch.json") == ["matrix_names_mismatch"],
          "a covariance whose names differ from the coefficients is refused")
    o = X.read_external(str(FIX / "coefs_dict.json"), run_r=_run_r)
    check(o.form == "coefficients" and len(o.terms) == 5,
          "a json dictionary -> 5 coefficients")
    # baseline hazard alone has no coefficients: refused for want of them;
    # with a coefficient table alongside it is recorded
    check(refused(FIX / "baseline_hazard.csv") == ["no_coefficient_table"],
          "a baseline hazard on its own has nothing to borrow coefficients from")
    tabs = (X.read_tables(str(FIX / "coefs_two_columns.csv"))
            + X.read_tables(str(FIX / "baseline_hazard.csv")))
    asg, _ = X.check_assignment(tabs, X.heuristic_assignment(tabs))
    o = X.canonicalise(tabs, asg, {"file": "two files"})
    check(o.form == "coefficients_with_baseline_hazard" and o.baseline_hazard
          and len(o.baseline_hazard["time"]) == 30
          and abs(o.baseline_hazard["cumhaz"][-1] - sum(o.baseline_hazard["hazard"])) < 1e-9,
          "coefficients + baseline hazard -> recorded, running sum verified")
    tabs = (X.read_tables(str(FIX / "coefs_two_columns.csv"))
            + X.read_tables(str(FIX / "bad_cumhaz.csv")))
    asg, _ = X.check_assignment(tabs, X.heuristic_assignment(tabs))
    try:
        X.canonicalise(tabs, asg, {"file": "x"})
        check(False, "a cumulative hazard that is not the running sum is refused")
    except X.ExternalRefusal as exc:
        check([r["code"] for r in exc.reasons] == ["cumhaz_not_running_sum"],
              "a cumulative hazard that is not the running sum is refused",
              exc.reasons[0]["message"][-40:])
    check(refused(FIX / "notes_only.csv") == ["no_coefficient_table"],
          "a file with no coefficient table is refused")
    if xlsx:
        o = X.read_external(str(xlsx), run_r=_run_r)
        check(o.form == "coefficients_with_covariance" and len(o.terms) == 5,
              "the xlsx (coefficients sheet + vcov sheet) reads the same way")
    if rds:
        o = X.read_external(str(rds), run_r=_run_r)
        # V = diag(0.0064, 0.01, 0.0081): the raw inverse is diag(156.25, 100, 123.46),
        # scaled to unit mean diagonal and shrunk 10 % toward I (the product's
        # convention, )
        import numpy as _np
        _Qi = _np.diag([1 / 0.0064, 1 / 0.01, 1 / 0.0081])
        _Qc = (1 - X.Q_SHRINK) * _Qi / _np.mean(_np.diag(_Qi)) + X.Q_SHRINK * _np.eye(3)
        check(o.form == "coefficients_with_covariance" and len(o.terms) == 3
              and abs(o.Q[0][0] - _Qc[0, 0]) < 1e-9,
              "the rds (named vector + matrix) reads the same way",
              f"Q[age,age] = {o.Q[0][0]:.4f} = conditioned 1/0.0064")
    # individual-level data needs an assignment (no header the heuristic knows)
    tabs = X.read_tables(str(FIX / "individual_external.csv"))
    asg = [{"table": tabs[0].name, "role": "individual_level_data",
            "time_column": "followup_days", "event_column": "died",
            "event_value": None, **{k: None for k in (
                "name_column", "coefficient_column", "coefficient_scale",
                "se_column", "ci_lower_column", "ci_upper_column",
                "hazard_column", "cumulative_hazard_column")}}]
    asg, _ = X.check_assignment(tabs, {"tables": asg})
    o = X.canonicalise(tabs, asg, {"file": "individual_external.csv",
                                   "path": str(FIX / "individual_external.csv")},
                       cohort_columns=["age", "bmi", "egfr", "nonesuch"])
    check(o.form == "individual_level_data" and o.individual_data["event_value"] == "1"
          and o.linkage["unmatched"] == ["nonesuch"],
          "another cohort's rows -> individual-level, event value 1 on 0/1, "
          "linkage disclosed")
    card = "\n".join(o.card())
    check("external cohort" in card and "not in your data: nonesuch" in card,
          "the card says what was read and what is missing")

    # a registry cohort covering a SUBSET of the target's covariates (the public benchmarks,
    # 2026-09-21): recognised by the rule when it carries the target's outcome columns by name
    # and at least half of its columns; not recognised when the outcome names differ
    import tempfile as _tf
    _d = _tf.mkdtemp()
    _rows = ["age,size2,size3,grade3,nodes,hormon,chemo,rfstime,status"] + \
            [f"{50+i},{i%2},0,{i%3==0:d},{i%5},{i%2},{(i+1)%2},{300+10*i},{i%2}" for i in range(30)]
    (Path(_d) / "registry_records.csv").write_text("\n".join(_rows) + "\n")
    _tabs = X.read_tables(str(Path(_d) / "registry_records.csv"))
    _cohort = ["age", "meno", "size2", "size3", "grade3", "nodes", "pgr", "er", "hormon", "rfstime", "status"]
    _asg = X.heuristic_assignment(_tabs, cohort_columns=_cohort, cohort_outcome=("rfstime", "status"))
    check(_asg["tables"][0]["role"] == "individual_level_data",
          "records sharing the outcome columns and 8 of 11 columns are another cohort's rows (no model)")
    _rows3 = ["size_cm,grade,node_stage,os_months,death"] + [f"{1+i%4},{1+i%3},{1+i%3},{10+3*i},{i%2}" for i in range(30)]
    (Path(_d) / "npi_records.csv").write_text("\n".join(_rows3) + "\n")
    _asg3 = X.heuristic_assignment(X.read_tables(str(Path(_d) / "npi_records.csv")),
                                   cohort_columns=["size_cm", "grade", "node_stage", "age", "er_pos", "pr_pos", "her2_pos",
                                                   "chemo", "hormone", "radio", "meno_post", "mastectomy", "os_months", "death"],
                                   cohort_outcome=("os_months", "death"))
    check(_asg3["tables"][0]["role"] == "individual_level_data",
          "a release laid out like ours that covers only 3 of 12 covariates is still another cohort's rows")
    _rows4 = ["size_cm,grade,node_stage,extra_col,os_months,death"] + [f"{1+i%4},{1+i%3},{1+i%3},{i},{10+3*i},{i%2}" for i in range(30)]
    (Path(_d) / "npi_records_extra.csv").write_text("\n".join(_rows4) + "\n")
    _asg4 = X.heuristic_assignment(X.read_tables(str(Path(_d) / "npi_records_extra.csv")),
                                   cohort_columns=["size_cm", "grade", "node_stage", "age", "os_months", "death"],
                                   cohort_outcome=("os_months", "death"))
    check(_asg4["tables"][0]["role"] == "individual_level_data",
          "an external-only column (a term the target lacks) does not break the recognition when most columns are ours")
    _asg2 = X.heuristic_assignment(_tabs, cohort_columns=_cohort, cohort_outcome=("time_to_event", "died"))
    check(_asg2["tables"][0]["role"] == "ignore",
          "the same table without the outcome names is not (73 % shared, below the 80 % rule)")

    # ---- 4. end to end through the app ------------------------------------
    hdr("4. end to end: coefficients + covariance through the app, and repro.R")
    try:
        import app
    except ImportError as exc:
        skip("app import (gradio not installed here)", str(exc)[:60])
        app = None
    if app is not None:
        h, s, *_ = app.start_session(str(app.DEMO_COHORT),
                                     str(FIX / "coefs_and_vcov.json"))
        check(s.get("external") is not None
              and s["external"].form == "coefficients_with_covariance",
              "the upload is read at load time",
              (h[0][1].split("external information")[1][:80]
               if "external information" in h[0][1] else h[0][1][:80]))
        check("their covariance" in h[0][1]
              and "inverse" in (s["external"].Q_from or ""),
              "the opening message states the conversion")
        out = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) A\n6) yes",
                                h, s, "", "", "")
        h2, _, s2, cand, coef, rep, trc, rpr, cjs, *_ = out
        res = s2.get("result")
        check(res is not None and res.candidates["facts"]["external_form"]
              == "coefficients and covariance",
              "the run's external form is coefficients and covariance",
              str(res.candidates["facts"]["external_form"]) if res else "no result")
        trace = json.loads(Path(trc).read_text(encoding="utf-8"))
        check(trace["provenance"].get("external", {}).get("matrix_role") == "covariance"
              and trace["provenance"]["external"]["sha256"],
              "trace.json carries the external provenance (file hash, roles)")
        check('"external_Q_inline":[[' in
              __import__("bregsurv_agent.pipeline", fromlist=["x"]).canonical_config(
                  s2["data_path"], s2["data_expr"], s2["declaration"], None,
                  20260818, 5, 50, external_beta_inline=s2["external"].terms,
                  external_Q_inline=s2["external"].Q),
              "the precision matrix is inside the C3 configuration hash")
        rtxt = Path(rpr).read_text(encoding="utf-8")
        check("Q_inline    = list(c(" in rtxt and "beta_inline = list(" in rtxt,
              "repro.R carries beta AND Q by value, as named/ordered R lists")
        rtext = Path(rep).read_text(encoding="utf-8")
        check("inverted to the precision matrix" in rtext
              and "Read from `coefs_and_vcov.json`" in rtext,
              "the report's section 2 discloses the source and the inversion")
        r = subprocess.run([rscript, "--no-save", "--no-restore",
                            "--no-init-file", rpr, s2["data_path"]],
                           capture_output=True, text=True,
                           stdin=subprocess.DEVNULL,
                           env=dict(os.environ,
                                    BREGSURV_R_SCRIPTS=str(REPO / "mcp" / "r_scripts")),
                           timeout=900)
        check("REPRODUCED" in r.stdout and r.returncode == 0,
              "repro.R replays the covariance run and reproduces the split",
              [l for l in r.stdout.splitlines() if "REPRODUCED" in l or "differ" in l][:1]
              or r.stderr[-200:])

        # the individual-level path: refused by name when columns do not line up
        h, s, *_ = app.start_session(str(app.DEMO_COHORT),
                                     str(FIX / "individual_external.csv"))
        check(s.get("external") is None and s.get("external_refusal"),
              "without a model, another cohort's rows cannot be typed -> refused, "
              "the cohort still loads", (s.get("external_refusal") or [{}])[0].get("code"))
        # pretend the model typed it (the assignment above) and declare a
        # covariate the external cohort lacks
        tabs = X.read_tables(str(FIX / "individual_external.csv"))
        o = X.canonicalise(tabs, asg, {"file": "individual_external.csv",
                                       "path": str(FIX / "individual_external.csv")})
        s = s.with_external(o)
        out = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, bmi, egfr\n6) yes",
                                h, s, "", "", "")
        h3, _, s3, cand3, *_ = out
        check(cand3 is not None and s3.get("result") is not None
              and "individual" in s3["result"].candidates["facts"]["external_form"],
              "matching columns -> the individual-level cell runs",
              str(s3["result"].candidates["facts"]["external_form"]) if s3.get("result") else h3[-1][1][:120])
        # now a declaration naming a column the external cohort lacks
        bad_ext = X.ExternalObject(**{**o.as_dict(), "individual_data":
                                      dict(o.individual_data, columns=[
                                          c for c in o.individual_data["columns"]
                                          if c != "egfr"])})
        s = s.restart().with_external(bad_ext)
        out = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, bmi, egfr\n6) yes",
                                h, s, "", "", "")
        h4, _, s4, cand4, *_ = out
        check(cand4 is None and "does not line up" in h4[-1][1]
              and "it lacks egfr" in h4[-1][1],
              "a covariate the external cohort lacks is refused by name, no rename")

    # ---- 5. the private SRTR release files --------------------------------
    hdr("5. the SRTR release files as published (private fixtures)")
    srtr = PRIV / "srtr"
    if not srtr.exists():
        skip("private fixtures not present", str(srtr))
    else:
        exp = json.loads((srtr / "expected.json").read_text())
        o = X.read_external(str(srtr / "srtr_kiddadgs1y_202105_coef.csv"), run_r=_run_r)
        e = exp["srtr_kiddadgs1y_202105_coef.csv"]
        check(o.form == e["form"] and len(o.terms) == e["n_terms"]
              and o.provenance["name_column"] == e["name_column"]
              and o.provenance["coefficient_column"] == e["coefficient_column"]
              and o.provenance["converted_from"] is None,
              "the 2021 release table: 30 per-variable coefficients, extras ignored",
              f"{len(o.terms)} terms from {o.provenance['name_column']}/{o.provenance['coefficient_column']}")
        tabs = (X.read_tables(str(srtr / "srtr_kiddadgs1y_202105_coef.csv"))
                + X.read_tables(str(srtr / "kiddadgs1y_202105_baseline_hazard.csv")))
        asg, _ = X.check_assignment(tabs, X.heuristic_assignment(tabs))
        o = X.canonicalise(tabs, asg, {"file": "srtr 2021"})
        bh = o.baseline_hazard
        check(o.form == "coefficients_with_baseline_hazard" and bh
              and len(bh["time"]) == exp["kiddadgs1y_202105_baseline_hazard.csv"]["n_times"],
              "the 2021 baseline hazard: cumulative hazard is the running sum",
              f"{len(bh['time'])} daily time points" if bh else "")
        check(refused(srtr / "kiddadps1y_202607_coefficients.csv") == ["names_not_unique"],
              "the 2026 per-level release table is refused: reduce it first",
              "predictor / level / coefficient")

    hdr(f"RESULT: {passed}/{passed + failed} passed"
        + (f", {skipped} skipped" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
