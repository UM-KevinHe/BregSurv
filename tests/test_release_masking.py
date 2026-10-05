"""The Mahalanobis family takes the release as it stands (found 2026-09-28).

run_candidates.R used to hand the Mahalanobis estimators `beta_full`: every column
named, with zeros on the ones the release never mentioned. align_beta_Q masks its
metric by NAME, so the masked identity became a full identity and every uncovered
coefficient was pulled toward 0 with weight eta. This suite pins the fix and the
companion one (a released covariance adds the Mahalanobis metric beside the
Euclidean one rather than replacing it):

  A. coefficients alone: the dispatcher's Mahalanobis members equal the library
     called directly with the release as it stands, and differ from the padded call
     (so the check can fail);
  B. coefficients with covariance: the derived set has 13 members, the dispatcher
     fits the same 13, and its Euclidean members equal the library at Q = NULL.

Demo cohort: 8 covariates; the release covers 5 of them and names one the cohort
lacks (hla_mismatch), which the linkage drops.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from bregsurv_agent.rbridge import _run_r, _find_rscript          # noqa: E402
from bregsurv_agent.declaration import Declaration                  # noqa: E402
from bregsurv_agent.pipeline import derive_candidate_keys           # noqa: E402

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
passed = failed = 0


def check(label, ok, note=""):
    global passed, failed
    if ok:
        passed += 1; print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1; print(f"  {RED}FAIL{OFF}  {label}   {note}")


DATA = REPO / "demo" / "kidney_cohort.csv"
COVS = ["age", "bmi", "egfr", "hgb", "albumin", "dialysis_yrs", "donor_age", "cold_ischemia"]
RELEASE = {"age": 0.55, "bmi": -0.3, "egfr": -0.45, "donor_age": 0.28,
           "cold_ischemia": 0.12, "hla_mismatch": 0.2}
COVERED = [v for v in RELEASE if v in COVS]
SEED = 20260818

# the direct library call, on the same file and the same grids as run_candidates.R
DIRECT_R = r'''
suppressPackageStartupMessages(library(BregSurv))
a <- commandArgs(TRUE); inp <- jsonlite::fromJSON(a[1])
D <- read.csv(inp$data); z <- as.matrix(D[, inp$covs]); storage.mode(z) <- "double"
log_eta <- function(hi, n, lo = 0.01) c(0, exp(seq(log(lo), log(hi), length.out = n)))
b <- unlist(inp$beta)
Q <- if (length(inp$Q)) { m <- if (is.matrix(inp$Q)) inp$Q else do.call(rbind, inp$Q); m <- as.matrix(m); storage.mode(m) <- "double"; dimnames(m) <- list(names(b), names(b)); m } else NULL
out <- list()
for (k in inp$members) {
  f <- switch(k,
    none  = cv.cox_MDTL(z = z, delta = D$died, time = D$followup_days, beta = b, Q = Q,
                        etas = log_eta(1e6, 81), nfolds = 5, seed = inp$seed, cv.criteria = "V&VH"),
    lasso = cv.cox_MDTL_enet(z = z, delta = D$died, time = D$followup_days, beta = b, Q = Q,
                             etas = log_eta(1e3, 41), alpha = 1, nfolds = 5, nlambda = 50,
                             lambda.min.ratio = 1e-9, seed = inp$seed, cv.criteria = "V&VH"))
  out[[k]] <- as.list(setNames(as.numeric(f$best$best_beta), colnames(z)))   # a named vector serialises as an array
}
cat(jsonlite::toJSON(out, digits = NA, auto_unbox = TRUE))
'''


def direct(beta, members, Q=None):
    with tempfile.TemporaryDirectory() as td:
        rs = Path(td) / "d.R"; rs.write_text(DIRECT_R)
        js = Path(td) / "in.json"
        js.write_text(json.dumps({"data": str(DATA), "covs": COVS, "beta": beta,
                                  "members": members, "Q": Q or [], "seed": SEED}))
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore", str(rs), str(js)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800)
        if r.returncode != 0:
            print(r.stderr[-2000:]); raise SystemExit("direct call failed")
        return json.loads(r.stdout.strip().splitlines()[-1])


def dispatch(include, beta_inline, Q_inline=None):
    d = Declaration(time_col="followup_days", event_col="died", event_value="1",
                    covariates=COVS, source="reply", covariates_time_zero="yes")
    payload = {"data_path": str(DATA), **d.as_exprs("kidney_cohort"), "seed": SEED,
               "nfolds": 5, "nlambda": 50, "event_value": "1", "include": include,
               "beta_inline": beta_inline}
    if Q_inline is not None:
        payload["Q_inline"] = Q_inline
    res = _run_r("run_candidates.R", payload, timeout_s=3600)
    if res.get("status") != "ok":
        raise SystemExit(f"dispatcher failed: {res.get('message')}")
    return {c["key"]: c for c in res["candidates"]}, res


def maxdiff(a, b):
    return max(abs(a[k] - b[k]) for k in COVS)


def main():
    print("A. coefficients alone: the Mahalanobis members take the release as it stands")
    got, _ = dispatch(["mahalanobis", "mahalanobis_lasso"], RELEASE)
    covered = {k: RELEASE[k] for k in COVERED}
    padded = {k: RELEASE.get(k, 0.0) for k in COVS}
    ref = direct(covered, ["none", "lasso"])
    bad = direct(padded, ["none", "lasso"])
    for key, m in (("mahalanobis", "none"), ("mahalanobis_lasso", "lasso")):
        b = got[key].get("beta") or {}
        check(f"{key}: dispatcher == library with the release as it stands",
              b and maxdiff(b, ref[m]) < 1e-8, f"max |diff| {maxdiff(b, ref[m]):.2e}" if b else "no beta")
        check(f"{key}: the padded call is a different fit (the check can fail)",
              maxdiff(ref[m], bad[m]) > 1e-4, f"max |padded - as given| {maxdiff(ref[m], bad[m]):.3f}")

    print("B. coefficients with covariance: Euclidean and Mahalanobis both in the set")
    keys = derive_candidate_keys("full cohort", "coefficients and covariance")
    check("derived set has 13 members", len(keys) == 13, str(keys))
    check("derived set holds all three Euclidean members",
          {"euclidean", "euclidean_ridge", "euclidean_lasso"} <= set(keys))
    keys_a = derive_candidate_keys("full cohort", "coefficients alone")
    check("coefficients alone: still 10 members, no Euclidean key", len(keys_a) == 10
          and not any(k.startswith("euclidean") for k in keys_a), str(keys_a))
    keys_n = derive_candidate_keys("nested case-control", "coefficients and covariance")
    check("matched design with covariance: Euclidean without ridge",
          "euclidean" in keys_n and "euclidean_lasso" in keys_n and "euclidean_ridge" not in keys_n,
          str(keys_n))
    names = list(RELEASE)
    Qrows = [[(1.5 + i) if i == j else 0.2 for j in range(len(names))] for i in range(len(names))]
    got, res = dispatch(None, RELEASE, Qrows)
    check("dispatcher fits exactly the derived 13", sorted(got) == sorted(keys),
          f"fitted {sorted(got)}")
    check("dispatcher reports the form as coefficients and covariance",
          (res.get("facts") or {}).get("external_form") == "coefficients and covariance",
          str((res.get("facts") or {}).get("external_form")))
    for key, m in (("euclidean", "none"), ("euclidean_lasso", "lasso")):
        b = (got.get(key) or {}).get("beta") or {}
        check(f"{key}: dispatcher == library at Q = NULL",
              b and maxdiff(b, ref[m]) < 1e-8, f"max |diff| {maxdiff(b, ref[m]):.2e}" if b else "no beta")
    Qc = [[Qrows[names.index(r)][names.index(c)] for c in COVERED] for r in COVERED]
    refQ = direct(covered, ["none"], Qc)
    b = (got.get("mahalanobis") or {}).get("beta") or {}
    check("mahalanobis: dispatcher == library with the released metric",
          b and maxdiff(b, refQ["none"]) < 1e-8, f"max |diff| {maxdiff(b, refQ['none']):.2e}" if b else "no beta")
    # the two members are different computations; their fits coincide only at the two
    # ends of the grid: eta = 0 (both the target-only fit) and the grid top, where any
    # positive-definite metric pins the covered coefficients and leaves the rest free
    be = (got.get("euclidean") or {}).get("beta") or {}
    em, ee = (got.get("mahalanobis") or {}).get("eta"), (got.get("euclidean") or {}).get("eta")
    ends = lambda e: e is not None and (e == 0 or e >= 1e6 * (1 - 1e-9))
    check("the two metrics differ unless both selected an end of the grid",
          bool(b and be) and (maxdiff(b, be) > 1e-6 or (ends(em) and ends(ee))),
          f"max |diff| {maxdiff(b, be):.2e}, eta {em} / {ee}" if b and be else "missing beta")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
