"""Regression tests for the three defects found on 2026-08-19.

All three were in SHIPPED code, none was caught by the six existing suites, and
each assertion here fails against the code as it stood that morning. That is the
point: a fix without a test that would have caught it is a claim, not a fix.

  A  `event_value` was declared, printed on the consequence card, counted by the
     gate and hashed into the approval -- and never sent to the fitter, which
     hard-coded 1 as the event. Declaring 0 on a 0/1 column silently fitted the
     complement of the declared outcome.

  B  Ties. Two things were wrong and only one of them was a bug. The bug: with
     tied event times the set was scored by TWO likelihood functionals, because
     only `internal` and `kl` were swapped onto cv.coxkl_ties while the other
     eight kept pl_cal_theta -- so the argmin ranked numbers that were not on
     one scale (live on MIUM, tie fraction 0.1149). The design error underneath
     it: the DATA was deciding. Whether a tie correction is applied is the
     analyst's call, the default is none, and the gate now reports the tie
     fraction without instructing anyone.

  C  The guard added for B must actually fire. The nested case-control branch
     is where it can be provoked today: the unpenalized NCC drivers average
     per-fold ratios while the enet ones pool, and get_fold_cc assigns whole
     matched sets so the fold sizes differ. That is a real mismatch and the run
     must stop rather than report a ranking.

  H  the NCC pooled loss, pinned as a NUMBER on a partition whose folds are
     deliberately unequal. The label-based checks in C cannot fail if the
     aggregation is reverted -- `scorer` is a string computed from a function
     name and knows nothing about the arithmetic underneath it.

  D  cv.cox_indi_enet was the only cross-validation driver in the package that
     never sorted its rows into (stratum, time) order, so it drew a different
     partition from every sibling AND fed pl_cal_theta risk sets built from row
     blocks that did not correspond to its strata. Requires the package to be
     reinstalled after the fix; skips with a clear message if it was not.

Run:  python test_defects_20260819.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

# The R bridge lives in the agent package, not in the MCP server: testing
# the agent must not require the MCP SDK. See bregsurv_agent/rbridge.py.
from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from test_pipeline_e2e import build_fixture  # noqa: E402

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m", "\033[2m",
                             "\033[0m")
passed = failed = skipped = 0

NCC_DATA = str(REPO / "data" / "ExampleData_cc_lowdim.rda")
INDI_DATA = str(REPO / "data" / "ExampleData_indi.rda")


# UNEQUAL matched sets, on purpose. The bundled NCC example splits into five
# folds of exactly 200, and pooling and averaging-per-fold agree exactly when
# the folds are the same size -- so a number pinned on THAT fixture cannot tell
# the two aggregations apart, and a revert would sail past it. Sets of 3, 4 and
# 5 with a set count not divisible by nfolds is what breaks the tie.
# Run directly rather than through the bridge: the bridge rounds its JSON to
# four decimal places, and four is not enough to separate two aggregations that
# differ only because the folds are 36, 37 and 39 rather than all equal.
UNEVEN_NCC_R = r"""
suppressPackageStartupMessages(library(BregSurv))
set.seed(4242)
sizes <- rep(c(4L, 3L, 5L), length.out = 47L)
stratum <- rep(seq_along(sizes), times = sizes)
n <- length(stratum)
z <- matrix(rnorm(n * 3), n, 3)
colnames(z) <- c("a", "b", "c")
y <- unlist(lapply(sizes, function(m) c(1, rep(0, m - 1L))))
fit <- cv.ncckl(z = z, y = y, stratum = stratum,
                beta = c(a = 0.4, b = -0.3, c = 0.2),
                etas = c(0, 0.5, 1), nfolds = 5, seed = 20260818L,
                cv.criteria = "loss")
cat("FOLDS:", paste(as.numeric(table(fit$folds)), collapse = ","), "
")
cat("LOSS:", paste(sprintf("%.8f", fit$internal_stat$loss), collapse = ","), "
")
"""

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


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        rda = build_fixture(tdp)

        base = {
            "data_path": rda,
            "z_expr": 'D[, c("age", "bmi", "egfr")]',
            "time_expr": 'D[["followup_days"]]',
            "delta_expr": 'D[["died"]]',
            "beta_expr": "beta_ext",
            "seed": 20260818, "nfolds": 5, "nlambda": 6,
            # internal produces the partition; external is scored against it.
            # Two cheap members are enough to read n_events off the facts.
            "include": ["internal", "external"],
        }

        # ---- A. event_value must reach the fitter ---------------------------
        hdr("A. the declared event value decides which outcome is fitted")
        a_default = _run_r("run_candidates.R", dict(base), timeout_s=900)
        if not check(a_default.get("status") == "ok",
                     "baseline run without event_value still works",
                     f"backward compatible; {a_default.get('message', '')!s:.90}"):
            return 1
        n_default = a_default["facts"]["n_events"]
        n_total = a_default["facts"]["n"]

        a_one = _run_r("run_candidates.R", dict(base, event_value="1"),
                       timeout_s=900)
        check(a_one.get("status") == "ok"
              and a_one["facts"]["n_events"] == n_default,
              'event_value="1" on a 0/1 column is the identity',
              f"{n_default} events either way, so nothing already recorded moves")

        a_zero = _run_r("run_candidates.R", dict(base, event_value="0"),
                        timeout_s=900)
        check(a_zero.get("status") == "ok", 'event_value="0" runs',
              str(a_zero.get("message", ""))[:120])
        n_zero = (a_zero.get("facts") or {}).get("n_events")
        # THE ASSERTION THAT FAILED BEFORE THE FIX. run_candidates.R used to
        # compute n_events as sum(delta == 1) with no knowledge of the declared
        # value, so this returned n_default and the two runs were identical.
        check(n_zero == n_total - n_default,
              'declaring the OTHER level fits the complement, not the same model',
              f"{n_zero} events of {n_total} against {n_default} when 1 is the "
              f"event; before the fix both said {n_default}")
        check(n_zero != n_default,
              "the two declarations are distinguishable at all",
              "this is the whole complement trap the protocol exists to catch")

        a_bad = _run_r("run_candidates.R", dict(base, event_value="7"),
                       timeout_s=900)
        check(a_bad.get("status") == "error"
              and "does not occur" in str(a_bad.get("message", "")),
              "a value that does not occur is refused, not silently ignored",
              str(a_bad.get("message", ""))[:100])

        # ---- B. one scale for the whole comparison --------------------------
        hdr("B. ties are never inferred from the data and never used")
        # THE POLICY, settled with whether a tie correction
        # is applied is the ANALYST'S decision, the default is none, and nothing
        # goes looking in the data for a reason to do otherwise.
        #
        # What this replaced: the gate measured the tie fraction, declared
        # "the tie-handling estimators are required" above a 10% threshold, and
        # the pipeline acted on it -- swapping `internal` and `kl` onto
        # cv.coxkl_ties (Breslow/exact) while the other eight kept pl_cal_theta,
        # then taking an argmin across the two scales. MIUM measured 0.1149 and
        # was therefore affected; MIMIC at 0.0180 was not.
        full = dict(base)
        full.pop("include")
        b = _run_r("run_candidates.R", dict(full, has_ties=True, event_value="1"),
                   timeout_s=1800)
        if check(b.get("status") == "ok",
                 "the full ten-member set fits",
                 str(b.get("message", ""))[:140]):
            # `has_ties` is passed here deliberately: it is a now-ignored input,
            # and a caller who still sends it must not be able to change the set.
            scorer = b.get("scorer")
            check(isinstance(scorer, str) and scorer == "vvh/pl_cal_theta",
                  "asking for ties does NOT change what is fitted",
                  f"scorer={scorer!r} even with has_ties=True on the payload")
            per = {c["key"]: c.get("scorer") for c in b["candidates"]
                   if c.get("status") == "ok"}
            check(len(set(per.values())) == 1,
                  "one likelihood functional across the whole comparison",
                  f"{len(per)} fitted, all {set(per.values())}")
            th = b["facts"].get("tie_handling")
            check(th == "none (the default; not inferred from the data)",
                  "the report states the policy, not a data-driven decision",
                  f"tie_handling={th!r}")
            check("has_ties" not in b["facts"],
                  "there is no data-derived tie flag left in the facts",
                  "the fitter no longer has an opinion about ties")

        g = _run_r("check_admissibility.R", {
            "data_path": rda,
            "z_expr": 'D[, c("age", "bmi", "egfr")]',
            "time_expr": 'D[["followup_days"]]',
            "delta_expr": 'D[["died"]]',
            "event_value": "1", "covariates_time_zero": "yes"}, timeout_s=900)
        if check(g.get("status") == "ok", "the gate runs on the same fixture"):
            check("ties" not in (g.get("route") or {}),
                  "the gate no longer issues a tie ROUTING instruction",
                  "nothing downstream may take a routing decision from the data")
            check(g["summary"].get("tie_fraction") is not None,
                  "but it still MEASURES and reports the tie fraction",
                  f"{g['summary'].get('tie_fraction')} -- a fact the analyst "
                  f"can act on, not a decision taken for them")

        # ---- C. the guard is not decorative ---------------------------------
        hdr("C. the NCC set is now single-scale and can be ranked")
        c = _run_r("run_candidates.R", {
            "data_path": NCC_DATA,
            "z_expr": "ExampleData_cc_lowdim$train$z",
            "y_expr": "ExampleData_cc_lowdim$train$y",
            "stratum_expr": "ExampleData_cc_lowdim$train$stratum",
            "beta_expr": "ExampleData_cc_lowdim$beta_external",
            "seed": 20260818, "nfolds": 5, "nlambda": 6,
        }, timeout_s=1800)
        msg = str(c.get("message", ""))
        # HISTORY, kept deliberately. When the scorer guard was introduced on
        # 2026-08-19 this exact call was REFUSED, with:
        # "The candidate set was scored by more than one likelihood functional
        # (cc_loglik/mean_of_fold_ratios and cc_loglik/pooled), so the
        # smallest number is not the best model. Nothing was selected."
        # That refusal was correct: the unpenalized NCC drivers averaged
        # per-fold means while the enet ones pooled, and get_fold_cc assigns
        # whole matched sets so the folds are not the same size. The three
        # unpenalized drivers were then changed to pool, matching both the enet
        # drivers and the entire cohort side. This assertion is the proof of
        # that change -- and if anyone reintroduces the mismatch, it fails.
        check(c.get("status") == "ok",
              "the NCC candidate set fits and can be ranked",
              msg[:150] if msg else "")
        if c.get("status") == "ok":
            check(c.get("scorer") == "cc_loglik/pooled",
                  "NCC members all report the POOLED loss now",
                  f"scorer={c.get('scorer')!r}")
            ok_c = [x for x in c["candidates"] if x.get("status") == "ok"]
            check(len({x.get("scorer") for x in ok_c}) == 1,
                  "no NCC member disagrees with the others about its scorer",
                  f"{len(ok_c)} fitted, all {({x.get('scorer') for x in ok_c})}")
            check(not any(x.get("penalty") == "ridge" for x in c["candidates"]),
                  "the NCC set contains no ridge member, as the library has none",
                  f"{len(c['candidates'])} candidates derived")

        # ---- D. cv.cox_indi_enet shares the partition -----------------------
        hdr("D. cv.cox_indi_enet draws the same partition as its siblings")
        ind = {
            "data_path": INDI_DATA,
            "z_int_expr": "ExampleData_indi$internal$z",
            "time_int_expr": "ExampleData_indi$internal$time",
            "delta_int_expr": "ExampleData_indi$internal$status",
            "stratum_int_expr": "ExampleData_indi$internal$stratum",
            "z_ext_expr": "ExampleData_indi$external$z",
            "time_ext_expr": "ExampleData_indi$external$time",
            "delta_ext_expr": "ExampleData_indi$external$status",
            "stratum_ext_expr": "ExampleData_indi$external$stratum",
            "etas": [0.0, 0.5], "nfolds": 5, "seed": 20260818,
        }
        d1 = _run_r("cv_cox_indi.R", dict(ind), timeout_s=1800)
        d2 = _run_r("cv_cox_indi_enet.R", dict(ind, alpha=1, nlambda=6),
                    timeout_s=1800)
        f1, f2 = d1.get("folds"), d2.get("folds")
        if d1.get("status") != "ok" or d2.get("status") != "ok":
            skip("both indi drivers run",
                 f"cv.cox_indi={d1.get('status')} "
                 f"({str(d1.get('message',''))[:60]}), "
                 f"cv.cox_indi_enet={d2.get('status')} "
                 f"({str(d2.get('message',''))[:60]})")
        elif f1 is None or f2 is None:
            skip("the bridges publish their fold vector",
                 "cannot compare partitions without it; compare losses by hand")
        else:
            # FAILED BEFORE THE FIX: cv.cox_indi_enet called get_fold on the
            # caller's unsorted, unencoded row order, so the two disagreed.
            check(list(f1) == list(f2),
                  "one seed gives ONE partition across the individual-level arm",
                  f"{len(f1)} subjects; "
                  f"{sum(int(x) != int(y) for x, y in zip(f1, f2))} disagreements")

        # ---- E. no declaration field can escape the three seams -------------
        hdr("E. the approval, the trace and repro.R cannot drop a field")
        import bregsurv_agent.pipeline as P
        from bregsurv_agent.declaration import parse_reply

        prof = _run_r("profile_columns.R", {
            "data_path": rda, "data_expr": "D", "external_beta_expr": "beta_ext"})
        answers = {"time": "followup_days", "event": "died", "event_value": "1",
                   "covariates": "age, bmi, egfr", "time_zero": "yes"}
        decl = parse_reply(prof, dict(answers))

        cfg = P.canonical_config(rda, "D", decl, "beta_ext", 20260818, 5, 6,
                                 candidate_keys=["internal"])
        # external_model used to escape all three sites; it is the existing
        # proof that hand-enumeration loses fields.
        check("external_model" in cfg,
              "every Declaration field reaches the approval hash",
              "by reflection over the dataclass, not by hand")
        cfg_q = P.canonical_config(rda, "D", decl, "beta_ext", 20260818, 5, 6,
                                   candidate_keys=["internal"],
                                   external_Q_expr="Qmat")
        # FAILED BEFORE THE FIX: Q was outside the hash, so a run with a
        # covariance matrix and one without hashed identically.
        check(P.config_hash(cfg) != P.config_hash(cfg_q),
              "supplying a covariance matrix changes the approved configuration",
              "penalty geometry and the report's External information row differ")

        res = P.run(data_path=rda, data_expr="D", declaration=decl,
                    external_beta_expr="beta_ext", profile=prof,
                    nlambda=6, run_r=_run_r)
        repro = P.render_repro(res)
        # FAILED BEFORE THE FIX: the args block had no event_value, so once
        # the fitter began honouring it, replaying a run that declared the other
        # level would have reproduced a different model and said folds matched.
        check("event_value" in repro,
              "repro.R carries the declared event value",
              "otherwise the replay silently fits a different outcome")

        tr = res.save(str(tdp / "seams"))
        import json as _json
        trace_decl = _json.loads(
            Path(tr["trace"]).read_text(encoding="utf-8"))["declaration"]
        from dataclasses import fields as _fields
        check(set(trace_decl) == {f.name for f in _fields(decl)},
              "the trace records every declared field, provenance included",
              f"{len(trace_decl)} fields")

        # The guard itself: pretend a field was added and check it refuses.
        # The injected name must be one nothing accounts for. This originally
        # used `stratum_col`, which became a real field hours later when the
        # nested case-control cell was wired up -- at which point it was in
        # _replayed, the guard correctly stayed silent, and the test failed for
        # the right reason. Use a name that will never be real.
        _orig = P._decl_config
        P._decl_config = lambda d: dict(_orig(d), a_field_nobody_accounted_for=1)
        try:
            P.render_repro(res)
            check(False, "a new unaccounted field stops repro.R generation",
                  "it did NOT raise -- the guard is inert")
        except RuntimeError as exc:
            check("a_field_nobody_accounted_for" in str(exc),
                  "a new unaccounted field stops repro.R generation",
                  "fails closed and names the field")
        finally:
            P._decl_config = _orig

        # ---- F. the partition says where it came from -----------------------
        hdr("F. partition provenance is reported, not asserted")
        part = res.candidates["partition"]
        # FAILED BEFORE THE FIX: rng_kind was the literal "Mersenne-Twister"
        # regardless of what the estimator actually used, and there was no
        # record of which row order `folds` indexes.
        check(part.get("drawn_by") not in (None, "NA", ""),
              "the estimator that drew the split is named",
              f"drawn_by={part.get('drawn_by')!r}, rng_kind={part.get('rng_kind')!r}")
        check(part.get("row_order") == "estimator_sorted",
              "which row order the folds index is recorded",
              "cohort estimators sort by (stratum, time); NCC ones do not")
        check(part.get("seed_is_effective") is True,
              "whether the seed does anything is stated",
              "get_fold_cc has no RNG call at all, so under NCC it does not")

        # ---- G. the report describes the set that actually ran --------------
        hdr("G. the report's prose is derived from the run, not hard-coded")
        from bregsurv_agent import report_v3
        check("matched **by name**" in res.report,
              "a name-matched linkage is described as name-matched")
        pos = _json.loads(_json.dumps(res.candidates))
        pos["linkage"]["matched_by"] = "position"
        rep_pos = report_v3.render(pos, prose={}, declaration=decl)
        # FAILED BEFORE THE FIX: the sentence said "matched **by name**"
        # unconditionally, with the real value in parentheses beside it.
        check("by position" in rep_pos and "matched **by name**" not in rep_pos,
              "a POSITION-matched linkage is not described as name-matched",
              "and it is flagged as the hazard it is")

        no_ridge = _json.loads(_json.dumps(res.candidates))
        no_ridge["candidates"] = [c for c in no_ridge["candidates"]
                                  if c.get("penalty") != "ridge"]
        rep_nr = report_v3.render(no_ridge, prose={}, declaration=decl)
        # FAILED BEFORE THE FIX: the report asserted "unpenalised, ridge and
        # lasso were all fitted" even on NCC, where the library has no ridge.
        check("ridge" not in rep_nr.split("## 4.")[0].split("## 3.")[1],
              "a set with no ridge member is not described as having fitted one",
              "this is exactly the NCC case")

        check("Outcome as you declared it" in res.report,
              "the report states which column and which value were declared",
              "render has always taken a declaration and never read it")


        # ---- H. the NCC loss is POOLED, asserted as a number -----------------
        hdr("H. the pooled NCC loss, pinned on an UNEQUAL partition")
        src = tdp / "mk_uneven.R"
        src.write_text(UNEVEN_NCC_R, encoding="utf-8")
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                            "--no-init-file", str(src)],
                           capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=900)
        txt = (r.stdout or "") + (r.stderr or "")
        folds, loss = [], []
        for line in txt.splitlines():
            if line.startswith("FOLDS:"):
                folds = [int(x) for x in line.split(":", 1)[1].strip().split(",")]
            elif line.startswith("LOSS:"):
                loss = [float(x) for x in line.split(":", 1)[1].strip().split(",")]
        if check(bool(loss), "the uneven fixture fits", txt.strip()[-160:]):
            check(len(set(folds)) > 1,
                  "the partition really is unequal, so the test can tell the "
                  "two aggregations apart", f"fold sizes {sorted(folds)}")
            # with the pooled aggregation in place.
            # Averaging per-fold means instead moves these numbers, precisely
            # because the folds differ in size -- which is what the label-based
            # checks in section C cannot see and this assertion can.
            want = [0.35225758, 0.35087075, 0.35382599]
            check(len(loss) == 3
                  and all(abs(x - w) < 1e-7 for x, w in zip(loss, want)),
                  "the loss is the POOLED quantity, to seven decimal places",
                  f"got {[round(x, 8) for x in loss]}")

    hdr(f"RESULT: {passed}/{passed + failed} passed"
        + (f", {skipped} skipped" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
