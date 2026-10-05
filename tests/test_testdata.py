"""The analyst's own test data: held-out performance
REPORTED, never selected on.

The rule this pins: the agent never draws a split. The
analyst may supply an ADDITIONAL file and name it as their test set; every
fitted member is then scored on it once by the library's own `test_eval`
(C-index, loss, IBS, tdAUC) with that member's Breslow baseline on the cohort,
the report carries the table, and the selection -- eta and lambda inside each
member, and the member itself -- is the cross-validated loss on the cohort
exactly as without the file.

What is checked, in order:
  A. without R -- the declaration's spec and its own checks (matched design,
     discrete row), the C3 hash by CONTENT of the test file, repro.R's args
     block and replay check, the report section and its references, the
     state line;
  B. with R -- the gate's test-data block (missing file, missing column,
     unusable covariate, no events, admissible with the card line), the
     pipeline on a hand-made 70/30 split of the demo cohort: every member
     carries the four numbers, the selection and every coefficient are
     IDENTICAL with and without the file, the four numbers of the selected
     member equal a direct R call of get_baseline_hazard + test_eval on the
     same rows, the artifacts, and repro.R's replay of the held-out table.

Run:  python mcp/test_testdata.py            (from the repository root)
"""
from __future__ import annotations

import csv
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent.rbridge import _run_r, _find_rscript, R_SCRIPTS  # noqa: E402
from bregsurv_agent import pipeline, report_v3, external as X  # noqa: E402
from bregsurv_agent.declaration import (Declaration, Verification, verify,  # noqa: E402
                                        _own_checks)
from bregsurv_agent.state import Session  # noqa: E402

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def hdr(t):
    print(f"\n{t}")


DEMO = REPO / "demo" / "kidney_cohort.csv"
DEMO_COEFS = REPO / "demo" / "registry_coefficients.csv"
COVS = ["age", "bmi", "egfr", "donor_age", "cold_ischemia"]


def decl(**kw) -> Declaration:
    base = dict(time_col="followup_days", event_col="died", event_value="1",
                covariates=list(COVS), source="reply", covariates_time_zero="yes")
    base.update(kw)
    return Declaration(**base)


def split_demo(td: Path, seed: int = 20260912, frac: float = 0.7):
    """A 70/30 split of the demo cohort, written as two csv files. The split is
    the TEST's, drawn once here; the agent never draws one."""
    with open(DEMO, newline="") as f:
        rows = list(csv.DictReader(f))
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    n_tr = int(frac * len(rows))
    tr = sorted(idx[:n_tr]); te = sorted(idx[n_tr:])
    names = list(rows[0].keys())

    def write(path, which):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=names)
            w.writeheader()
            for i in which:
                w.writerow(rows[i])
    p_tr = td / "mium_like_train.csv"; p_te = td / "mium_like_test.csv"
    write(p_tr, tr); write(p_te, te)
    return str(p_tr), str(p_te), [rows[i] for i in tr], [rows[i] for i in te]


def fake_result(with_test: bool):
    ho = {"cindex": 0.71, "loss": 5.9, "ibs": 0.17, "tdauc": 0.74, "seconds": 0.3,
          "baseline_available": True}
    cands = [
        {"key": "internal", "label": "Internal only", "borrowing": "none", "penalty": "none",
         "status": "ok", "loss": 6.7564, "eta": 0, "lambda": None, "n_nonzero": 5, "seconds": 1.0},
        {"key": "kl", "label": "Kullback-Leibler", "borrowing": "kl", "penalty": "none",
         "status": "ok", "loss": 6.6999, "eta": 20.2, "lambda": None, "n_nonzero": 5, "seconds": 1.2},
        {"key": "kl_lasso", "label": "Kullback-Leibler, lasso", "borrowing": "kl", "penalty": "lasso",
         "status": "failed", "loss": None, "eta": None, "lambda": None, "n_nonzero": None,
         "seconds": 0.1, "message": "did not converge"},
    ]
    if with_test:
        cands[0]["holdout"] = dict(ho, cindex=0.66)
        cands[1]["holdout"] = ho
    res = {
        "status": "ok",
        "facts": {"design": "full cohort", "external_form": "coefficients", "n": 182,
                  "n_events": 115, "p": 5, "p_covered": 5, "p_internal_only": 0,
                  "tie_handling": "none"},
        "partition": {"seed": 20260818, "nfolds": 5, "folds": [1, 2, 3, 4, 5] * 36 + [1, 2],
                      "rng_kind": "Mersenne-Twister", "drawn_by": "cv.coxkl",
                      "row_order": "estimator_sorted", "seed_is_effective": True},
        "criteria": "V&VH", "scorer": ["vvh/pl_cal_theta"],
        "candidates": cands,
        "selected": {"key": "kl", "label": "Kullback-Leibler", "loss": 6.6999, "eta": 20.2,
                     "lambda": None, "n_nonzero": 5,
                     "beta": {c: 0.1 for c in COVS},
                     "holdout": ho if with_test else None},
        "coefficients": [{"variable": c, "beta_external": 0.5, "beta_internal": 0.4,
                          "beta_selected": 0.45, "covered_by_external": True} for c in COVS],
        "linkage": {"matched_by": "name", "covered": COVS, "zero_padded": [], "dropped": ["hla_mismatch"],
                    "n_internal": 5, "n_external": 6},
    }
    if with_test:
        res["test_data"] = {"n": 78, "n_events": 49, "source": "mium_like_test.csv",
                            "criteria": ["CIndex", "loss", "IBS", "tdAUC"],
                            "baseline": "Breslow", "role": "reported only"}
    return res


def fake_profile():
    cols = [{"name": c, "type": "numeric", "can_be_time": False, "can_be_event": False,
             "can_be_covariate": True} for c in COVS]
    cols.append({"name": "followup_days", "type": "numeric", "can_be_time": True,
                 "can_be_event": False, "can_be_covariate": True})
    cols.append({"name": "died", "type": "numeric", "can_be_time": False,
                 "can_be_event": True, "can_be_covariate": False})
    return {"status": "ok", "n_rows": 182, "n_columns": 7, "columns": cols,
            "eligible": {"time": ["followup_days"], "event": ["died"], "covariate": COVS,
                         "stratum": []},
            "quarantined": [], "complementary_pairs": [], "external": {"matched": COVS, "unmatched": []},
            "dictionary": None}


def fake_run(res, d):
    return pipeline.RunResult(
        data_path=str(DEMO), data_expr="cohort", external_beta_expr=None, external_Q_expr=None,
        profile=fake_profile(), declaration=d, verification=Verification(True, []),
        candidates=res, report="",
        provenance={"generated_at": "now", "data": {"name": "x", "sha256": "0" * 64}, "nlambda": 50},
        config_sha256="f" * 64, seconds=1.0, external_beta_inline={c: 0.5 for c in COVS})


# ============================================================ A. without R
def part_a():
    hdr("A1. the declaration: spec, and its own checks")
    d = decl(test_data_path="/x/test.csv", test_data_expr="test")
    check(d.has_test_data and d.test_spec() == {
        "path": "/x/test.csv", "expr": "test", "time_col": "followup_days", "event_col": "died",
        "covariates": COVS, "stratum_col": None}, "test_spec() carries the declared names",
        json.dumps(d.test_spec()))
    check(not decl().has_test_data and decl().test_spec() is None, "no test file: no spec")
    bad = _own_checks(fake_profile(), Declaration(
        time_col=None, event_col="died", event_value="1", covariates=COVS, source="reply",
        stratum_col="site", test_data_expr="test", covariates_time_zero="yes"))
    check(any(b["code"] == "test_data_needs_cohort" for b in bad),
          "matched design + test file: refused by the declaration", "; ".join(b["code"] for b in bad))
    bad = _own_checks(fake_profile(), decl(test_data_expr="test", n_intervals=8, interval_width=7.0))
    check(any(b["code"] == "test_data_needs_cox_row" for b in bad),
          "discrete row + test file: refused by the declaration", "; ".join(b["code"] for b in bad))
    check(not [b for b in _own_checks(fake_profile(), d) if b["code"].startswith("test_data")],
          "cohort + test file: the declaration's own checks pass")

    hdr("A2. C3: the test file is hashed by CONTENT")
    with tempfile.TemporaryDirectory() as td_:
        td = Path(td_)
        t1 = td / "t1.csv"; t2 = td / "t2.csv"; t3 = td / "t3.csv"
        t1.write_text("a,b\n1,2\n"); t2.write_text("a,b\n1,2\n"); t3.write_text("a,b\n1,3\n")
        cfg = lambda p: pipeline.canonical_config(
            str(DEMO), "cohort", decl(test_data_path=str(p), test_data_expr="t"),
            None, 20260818, 5, 50, candidate_keys=["internal"])
        h1, h2, h3 = (pipeline.config_hash(cfg(p)) for p in (t1, t2, t3))
        # the path itself is a Declaration field and is hashed too, so two
        # paths never hash alike; what matters is that content is in as well
        c1 = json.loads(cfg(t1)); c3 = json.loads(cfg(t3))
        check(c1["test_data"]["sha256"] != c3["test_data"]["sha256"] and h1 != h3,
              "a changed test file changes the hash", c1["test_data"]["sha256"][:12])
        check(c1["test_data"]["sha256"] == json.loads(cfg(t2))["test_data"]["sha256"],
              "identical contents fingerprint alike")
        c0 = json.loads(pipeline.canonical_config(str(DEMO), "cohort", decl(), None, 20260818, 5, 50))
        check(c0["test_data"] is None and "test_data_path" not in c0 and c0["test_data_expr"] is None,
              "no test file: the content fingerprint is null in the hash (the path string is not hashed)")
        (td / "elsewhere").mkdir()
        t1b = td / "elsewhere" / "t1.csv"; t1b.write_text("a,b\n1,2\n")     # same name, same bytes, another directory
        c_moved = json.loads(pipeline.canonical_config(
            str(DEMO), "cohort", decl(test_data_path=str(t1b), test_data_expr="t"),
            None, 20260818, 5, 50, candidate_keys=["internal"]))
        check(c_moved == c1, "the same test file (name and bytes) in another directory hashes identically")
        check(h1 != pipeline.config_hash(pipeline.canonical_config(
            str(DEMO), "cohort", decl(), None, 20260818, 5, 50, candidate_keys=["internal"])),
            "with vs without the file: different hashes")

    hdr("A3. repro.R: the args block and the replay check")
    d = decl(test_data_path="/x/mium_like_test.csv", test_data_expr="mium_like_test")
    r = fake_run(fake_result(True), d)
    script = pipeline.render_repro(r)
    check('test_data   = list(path = "/x/mium_like_test.csv", expr = "mium_like_test", '
          'time_col = "followup_days", event_col = "died", covariates = list("age", "bmi", '
          '"egfr", "donor_age", "cold_ischemia"))' in script,
          "repro.R passes the test file by path, expression and column names")
    check("held-out numbers of the selected model REPRODUCED" in script
          and "expected_ho <- list(cindex = 0.71, loss = 5.9, ibs = 0.17, tdauc = 0.74)" in script,
          "repro.R checks the selected member's four numbers against the recorded ones")
    script0 = pipeline.render_repro(fake_run(fake_result(False), decl()))
    check("test_data" not in script0 and "expected_ho" not in script0,
          "without a test file repro.R is unchanged")
    d2 = decl(test_data_path="/x/t.csv", test_data_expr="t", stratum_col="site")
    check('stratum_col = "site"' in pipeline.render_repro(fake_run(fake_result(True), d2)),
          "a stratified cohort passes its stratum column to the test file too")

    hdr("A4. the report: the section and the closed references")
    refs = report_v3.build_references(fake_result(True))
    check(refs["test_n"] == 78 and refs["test_events"] == 49 and refs["test_cindex_selected"] == 0.71
          and refs["test_loss_selected"] == 5.9 and refs["test_ibs_selected"] == 0.17
          and refs["test_tdauc_selected"] == 0.74, "six held-out references, from the selected member")
    refs0 = report_v3.build_references(fake_result(False))
    check(not any(k.startswith("test_") for k in refs0),
          "no test file: no held-out reference exists to be named")
    rep = report_v3.render(fake_result(True), declaration=d)
    sec = rep.split("### Performance on your test data")[1].split("## 5.")[0] \
        if "### Performance on your test data" in rep else ""
    line_sel = next((ln for ln in sec.splitlines() if ln.startswith("| Kullback-Leibler **<-**")), "")
    line_int = next((ln for ln in sec.splitlines() if ln.startswith("| Internal only")), "")
    check(sec and all(x in line_sel for x in ("0.71", "5.9", "0.17", "0.74")) and "0.66" in line_int,
          "the section lists every scored member, the selected one marked", line_sel)
    check("78 subjects (49 events)" in rep and "did not read this table" in rep
          and "took no part in fitting" in rep, "the text says the selection did not read it")
    check("Kullback-Leibler, lasso" not in sec, "a failed member has no held-out row")
    rep0 = report_v3.render(fake_result(False), declaration=decl())
    check("Performance on your test data" not in rep0, "no test file: no section")
    prose = report_v3.resolve("On the test file the chosen model reached a C-index of "
                              "[test_cindex_selected] over [test_n] subjects.", refs)
    check("0.71" in prose and "78" in prose, "the prose resolves the held-out references")

    hdr("A5. the state line")
    s = Session().with_profile(str(DEMO), "cohort", fake_profile(),
                               test_data_path="/x/t.csv", test_data_expr="t")
    check("test data: supplied" in s.state_line(), "the model is told a test file exists",
          s.state_line())
    check("test data" not in Session().with_profile(str(DEMO), "cohort", fake_profile()).state_line(),
          "and not told when none is")
    check(s.to_provenance()["test_data"] is True, "provenance records it")


# ================================================================ B. with R
def part_b():
    with tempfile.TemporaryDirectory() as td_:
        td = Path(td_)
        p_tr, p_te, rows_tr, rows_te = split_demo(td)
        n_te_events = sum(int(r["died"]) for r in rows_te)
        print(DIM + f"split: {len(rows_tr)} train / {len(rows_te)} test "
              f"({n_te_events} test events)" + OFF)
        ext = X.read_external(str(DEMO_COEFS))
        beta = dict(ext.terms)

        hdr("B1. the profile and the gate")
        prof = _run_r("profile_columns.R", {"data_path": p_tr, "data_expr": "mium_like_train",
                                            "external_beta_inline": beta})
        check(prof.get("status") == "ok", "the training file profiled")
        d = decl(test_data_path=p_te, test_data_expr="mium_like_test")
        v = verify(prof, d, p_tr, "mium_like_train", run_r=_run_r)
        td_s = (v.gate or {}).get("summary", {}).get("test_data") or {}
        check(v.admissible, "cohort + test file: admissible", "; ".join(r["code"] for r in v.refusals))
        check(td_s.get("n_obs") == len(rows_te) and td_s.get("n_events") == n_te_events,
              "the gate counts the test rows and events", json.dumps(td_s))
        card = v.render()
        check(f"test data         mium_like_test.csv: {len(rows_te)} subjects, {n_te_events} events" in card
              and "never to choose the model" in card, "the card states the test file and its counts")
        # refusals
        v = verify(prof, decl(test_data_path=str(td / "nope.csv"), test_data_expr="nope"),
                   p_tr, "mium_like_train", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "test_data_missing_file" for r in v.refusals),
              "a missing test file: refused", "; ".join(r["code"] for r in v.refusals))
        with open(p_te, newline="") as f:
            te_rows = list(csv.DictReader(f))
        names = list(te_rows[0].keys())

        def write_variant(path, rows, drop=None, mutate=None):
            fn = [n for n in names if n != drop]
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fn, extrasaction="ignore")
                w.writeheader()
                for i, r in enumerate(rows):
                    r2 = dict(r)
                    if mutate:
                        mutate(i, r2)
                    w.writerow(r2)
        p_miss = td / "t_missing_col.csv"
        write_variant(p_miss, te_rows, drop="egfr")
        v = verify(prof, decl(test_data_path=str(p_miss), test_data_expr="t_missing_col"),
                   p_tr, "mium_like_train", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "test_data_missing_columns" for r in v.refusals)
              and any("egfr" in r["message"] for r in v.refusals),
              "a test file lacking a declared covariate: refused by name",
              "; ".join(r["code"] for r in v.refusals))
        p_na = td / "t_na.csv"
        write_variant(p_na, te_rows, mutate=lambda i, r: r.update(age="") if i == 3 else None)
        v = verify(prof, decl(test_data_path=str(p_na), test_data_expr="t_na"),
                   p_tr, "mium_like_train", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "test_data_covariate_unusable" for r in v.refusals),
              "a missing covariate value in the test file: refused",
              "; ".join(r["code"] for r in v.refusals))
        p_noev = td / "t_noev.csv"
        write_variant(p_noev, te_rows, mutate=lambda i, r: r.update(died="0"))
        v = verify(prof, decl(test_data_path=str(p_noev), test_data_expr="t_noev"),
                   p_tr, "mium_like_train", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "test_data_degenerate" for r in v.refusals),
              "a test file with no events: refused", "; ".join(r["code"] for r in v.refusals))
        p_t0 = td / "t_time0.csv"
        write_variant(p_t0, te_rows, mutate=lambda i, r: r.update(followup_days="0") if i == 0 else None)
        v = verify(prof, decl(test_data_path=str(p_t0), test_data_expr="t_time0"),
                   p_tr, "mium_like_train", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "test_data_time_invalid" for r in v.refusals),
              "a zero follow-up time in the test file: refused", "; ".join(r["code"] for r in v.refusals))

        hdr("B2. the pipeline: every member scored, the selection untouched")
        d = decl(test_data_path=p_te, test_data_expr="mium_like_test")
        rc = pipeline.resolve_config(p_tr, "mium_like_train", d, external_beta_inline=beta)
        rr = pipeline.run(p_tr, "mium_like_train", d, external_beta_inline=beta, profile=prof,
                          run_r=_run_r, approved_config_sha256=rc["sha256"],
                          external_provenance=ext.provenance)
        rows_ = {c["key"]: c for c in rr.candidates["candidates"]}
        ok = [k for k, c in rows_.items() if c["status"] == "ok"]
        check(len(ok) >= 8 and all(rows_[k].get("holdout") for k in ok),
              "every fitted member carries a held-out block", f"{len(ok)} ok of {len(rows_)}")
        four = ("cindex", "loss", "ibs", "tdauc")
        finite = all(isinstance(rows_[k]["holdout"].get(m), (int, float)) for k in ok for m in four)
        check(finite, "all four numbers are finite for every fitted member",
              "; ".join(f"{k}: " + ",".join(str(rows_[k]['holdout'].get(m)) for m in four) for k in ok[:3]))
        check(all(0 <= rows_[k]["holdout"]["cindex"] <= 1 and 0 <= rows_[k]["holdout"]["ibs"] <= 1
                  and 0 <= rows_[k]["holdout"]["tdauc"] <= 1 and rows_[k]["holdout"]["loss"] > 0
                  for k in ok), "the numbers are in range (C, IBS, AUC in [0,1]; loss > 0)")
        tdf = rr.candidates.get("test_data") or {}
        check(tdf.get("n") == len(rows_te) and tdf.get("n_events") == n_te_events
              and "reported only" in tdf.get("role", ""), "the facts name the test rows and their role")
        sel = rr.candidates["selected"]
        check(sel.get("holdout") and sel["holdout"] == rows_[sel["key"]]["holdout"],
              "the selected member's held-out block is the table's", sel["label"])
        # the selection is BLIND to the file: same losses, same winner, same coefficients
        d0 = decl()
        rc0 = pipeline.resolve_config(p_tr, "mium_like_train", d0, external_beta_inline=beta)
        rr0 = pipeline.run(p_tr, "mium_like_train", d0, external_beta_inline=beta, profile=prof,
                           run_r=_run_r, approved_config_sha256=rc0["sha256"])
        rows0 = {c["key"]: c for c in rr0.candidates["candidates"]}
        same_loss = all(rows0[k]["loss"] == rows_[k]["loss"] and rows0[k]["eta"] == rows_[k]["eta"]
                        and rows0[k]["lambda"] == rows_[k]["lambda"] for k in ok)
        check(same_loss and rr0.candidates["selected"]["key"] == sel["key"]
              and rr0.candidates["selected"]["beta"] == sel["beta"]
              and rr0.candidates["partition"]["folds"] == rr.candidates["partition"]["folds"],
              "with and without the file: identical losses, winner, coefficients, partition")
        check(rc["sha256"] != rc0["sha256"] and rr.config_sha256 == rc["sha256"],
              "the two runs have different approval hashes; the run's equals the verified one")
        check(not rows0[sel["key"]].get("holdout") and not rr0.candidates.get("test_data")
              and not rr0.candidates["selected"].get("holdout")
              and "Performance on your test data" not in rr0.report,
              "without the file: nothing held-out anywhere")

        hdr("B2b. the result cache: an identical configuration reuses the fit, a changed one does not")
        cache_dir = td / "run_cache"
        os.environ["BREGSURV_RUN_CACHE"] = str(cache_dir)
        try:
            t1 = time.time()
            rr_c1 = pipeline.run(p_tr, "mium_like_train", d, external_beta_inline=beta, profile=prof,
                                 run_r=_run_r, approved_config_sha256=rc["sha256"])
            s1 = time.time() - t1
            t2 = time.time()
            rr_c2 = pipeline.run(p_tr, "mium_like_train", d, external_beta_inline=beta, profile=prof,
                                 run_r=_run_r, approved_config_sha256=rc["sha256"])
            s2 = time.time() - t2
            pc1 = rr_c1.provenance.get("result_cache") or {}
            pc2 = rr_c2.provenance.get("result_cache") or {}
            check(pc1.get("hit") is False and pc2.get("hit") is True and pc1.get("key") == pc2.get("key"),
                  "first run fits and writes the cache; the second run hits it", f"{s1:.1f}s -> {s2:.1f}s")
            same = (rr_c2.candidates["candidates"] == rr_c1.candidates["candidates"]
                    and rr_c2.candidates["selected"] == rr_c1.candidates["selected"]
                    and rr_c2.candidates["partition"]["folds"] == rr_c1.candidates["partition"]["folds"])
            check(same and rr_c2.config_sha256 == rr_c1.config_sha256 == rr.config_sha256,
                  "the cached run is the fitted run: candidates, selection, partition, hash")
            check("Performance on your test data" in rr_c2.report
                  and all(rr_c2.candidates["selected"]["holdout"].get(m) == sel["holdout"].get(m) for m in four),
                  "the report is rendered afresh from the cached result")
            rr_c3 = pipeline.run(p_tr, "mium_like_train", decl(), external_beta_inline=beta, profile=prof,
                                 run_r=_run_r, approved_config_sha256=rc0["sha256"])
            check((rr_c3.provenance.get("result_cache") or {}).get("hit") is False
                  and len(list(cache_dir.glob("*.json"))) == 2,
                  "a different configuration (no test file) is a miss and its own entry")
        finally:
            os.environ.pop("BREGSURV_RUN_CACHE", None)

        hdr("B3. golden equality: the four numbers equal a direct library call on the same rows")
        gold_r = td / "golden.R"
        gold_r.write_text(f"""
suppressPackageStartupMessages({{ library(BregSurv); library(jsonlite) }})
tr <- read.csv({json.dumps(p_tr)}); te <- read.csv({json.dumps(p_te)})
cov <- c({', '.join(json.dumps(c) for c in COVS)})
b <- unlist(fromJSON({json.dumps(json.dumps(sel['beta']))}))[cov]
z_tr <- as.matrix(tr[, cov]); z_te <- as.matrix(te[, cov])
bh <- get_baseline_hazard(z = z_tr, delta = tr$died, time = tr$followup_days, beta = b)
ev <- function(crit, obj = NULL) test_eval(test_z = z_te, test_delta = te$died, test_time = te$followup_days,
                                           betahat = b, train_baseline_obj = obj, criteria = crit)
out <- list(cindex = ev("CIndex"), loss = ev("loss"), ibs = ev("IBS", bh), tdauc = ev("tdAUC"))
cat(toJSON(out, auto_unbox = TRUE, digits = 15))
""")
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file", str(gold_r)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)
        try:
            gold = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            gold = None
        check(gold is not None, "the golden script ran", (r.stdout + r.stderr)[-300:].replace("\n", " | "))
        if gold:
            diffs = {m: abs(float(gold[m]) - float(sel["holdout"][m])) for m in four}
            check(max(diffs.values()) <= 1e-9,
                  "selected member: C-index, loss, IBS, tdAUC equal the direct call to 1e-9",
                  json.dumps({m: f"{sel['holdout'][m]:.6f} vs {float(gold[m]):.6f}" for m in four}))

        hdr("B4. the artifacts and the replay")
        check("### Performance on your test data" in rr.report
              and f"{len(rows_te)} subjects ({n_te_events} events)" in rr.report
              and "mium_like_test.csv" in rr.report, "the report carries the section")
        out = td / "run"
        paths = rr.save(str(out))
        trace = json.loads(Path(paths["trace"]).read_text(encoding="utf-8"))
        check(trace["declaration"]["test_data_path"] == p_te
              and trace["provenance"]["test_data"]["sha256"] == pipeline._fingerprint(p_te)["sha256"],
              "the trace records the test file and its fingerprint")
        cands = json.loads(Path(paths["candidates"]).read_text(encoding="utf-8"))
        check(all(cands["selected"]["holdout"].get(m) == sel["holdout"].get(m) for m in four),
              "candidates.json carries the held-out numbers")
        script = Path(paths["repro"]).read_text(encoding="utf-8")
        check(f'test_data   = list(path = {json.dumps(p_te)}' in script, "repro.R names the test file")
        env = dict(os.environ, BREGSURV_R_SCRIPTS=str(R_SCRIPTS))
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                            paths["repro"], p_tr], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env, timeout=900)
        check(r.returncode == 0 and "fold assignment REPRODUCED" in r.stdout
              and "held-out numbers of the selected model REPRODUCED" in r.stdout,
              "repro.R replays the partition AND the held-out numbers",
              (r.stdout + r.stderr)[-400:].replace("\n", " | "))

        hdr("B5. the app: the third upload slot")
        try:
            import app  # noqa: F401
        except Exception as exc:
            print(DIM + f"  skipped: app.py not importable here ({type(exc).__name__}: {exc})" + OFF)
            return
        h, s, *_ = app.start_session(p_tr, str(DEMO_COEFS), test_uploaded=p_te)
        check(s is not None and s.test_data_path == p_te and s.test_data_expr == "mium_like_test",
              "start_session stores the test file on the session")
        check("mium_like_test.csv" in h[0][1] and "never to choose" in h[0][1],
              "the opening message says what the file is for")
        out2 = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) " + ", ".join(COVS) + "\n6) yes",
                                 h, s, "", "", "", False, False)
        h2, _, s2 = out2[0], out2[1], out2[2]
        check(s2.result is not None and s2.declaration.test_data_path == p_te,
              "a numbered reply runs with the test file attached to the declaration")
        if s2.result is not None:
            res = s2.result.candidates
            same4 = all(res["selected"]["holdout"].get(m) == sel["holdout"].get(m) for m in four)
            check(same4 and "Performance on your test data" in s2.result.report,
                  "the app's run carries the same held-out numbers and the section",
                  f"app: {res['selected']['key']} {json.dumps(res['selected'].get('holdout'))} | "
                  f"pipeline: {sel['key']} {json.dumps(sel['holdout'])} | "
                  f"section: {'Performance on your test data' in s2.result.report} | "
                  f"decl: {s2.declaration.covariates} ev={s2.declaration.event_value} "
                  f"test={s2.declaration.test_data_expr} sha={s2.result.config_sha256[:8]} vs {rr.config_sha256[:8]}")
            tbl = app._candidate_table(res)
            check("test C-index" in tbl.columns and "test tdAUC" in tbl.columns,
                  "the candidate table shows the four held-out columns")
        h3, s3, *_ = app.start_session()
        check(s3 is not None and not s3.test_data_expr and "Test data" not in h3[0][1],
              "the example cohort never has a test file")
        app._purge(s2)


def main() -> int:
    part_a()
    part_b()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
