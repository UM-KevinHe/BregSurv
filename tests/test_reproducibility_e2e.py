"""End-to-end test driver for A4: the cross-validation run is reproducible, and
``repro.R`` CHECKS that rather than claiming it.

What A4 was about, measured on 2026-08-18 against ExampleData_lowdim: the fold
assignment is drawn with ``sample``, and the dispatcher left the seed at NULL
when the caller omitted it. Over 30 unseeded rounds the recommended estimator
FLIPPED -- Kullback-Leibler won 8 and Mahalanobis 22 -- because the run-to-run
wobble in the cross-validated loss (0.035) was four times the gap between the two
candidates (0.009). Under V3 that loss is the selection criterion, so the agent's
recommendation itself was not reproducible.

Separately, ``set.seed(seed)`` inherits the ambient RNG *kind*: the same seed in a
session left in "L'Ecuyer-CMRG" by future/future.apply produces a different split.
So the seed alone is not a sufficient record.

Run:  python test_reproducibility_e2e.py
Exits non-zero if any case fails.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

# The R bridge lives in the agent package, not in the MCP server: testing
# the agent must not require the MCP SDK. See bregsurv_agent/rbridge.py.
from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from bregsurv_agent.rbridge import DEFAULT_CV_SEED  # noqa: E402
from bregsurv_agent import pipeline  # noqa: E402
from bregsurv_agent.declaration import parse_reply  # noqa: E402
from test_pipeline_e2e import build_fixture  # noqa: E402

DATA = str(REPO / "data" / "ExampleData_lowdim.rda")
BASE = {
    "data_path": DATA,
    "z_expr": "ExampleData_lowdim$train$z",
    "time_expr": "ExampleData_lowdim$train$time",
    "delta_expr": "ExampleData_lowdim$train$status",
    "beta_expr": "ExampleData_lowdim$beta_external_good",
    "etas": [0.0, 0.5, 2.0],
    "nfolds": 3,
}
NCC_DATA = str(REPO / "data" / "ExampleData_cc_lowdim.rda")
NCC_BASE = {
    "data_path": NCC_DATA,
    "z_expr": "ExampleData_cc_lowdim$train$z",
    "y_expr": "ExampleData_cc_lowdim$train$y",
    "stratum_expr": "ExampleData_cc_lowdim$train$stratum",
    "beta_expr": "ExampleData_cc_lowdim$beta_external",
    "etas": [0.0, 0.5, 2.0],
    "nfolds": 3,
    "cv_criteria": "loss",
}

COHORT_TOOLS = ["cv_coxkl", "cv_coxkl_ties", "cv_cox_MDTL"]
SLOW_TOOLS = [("cv_coxkl_ridge", {"nlambda": 5}),
              ("cv_cox_MDTL_ridge", {"nlambda": 5})]
NCC_TOOLS = ["cv_ncckl", "cv_ncc_MDTL"]

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m",
                             "\033[2m", "\033[0m")
passed = failed = skipped = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def skip(label, note=""):
    global skipped
    skipped += 1
    print(f"  {YEL}SKIP{OFF}  {label}   {DIM}{note}{OFF}")


def losses(res):
    m = res.get("cv_metric") or {}
    v = m.get("values")
    return [round(x, 12) for x in v] if v else None


# ---------------------------------------------------------------- 1. constants
def test_constant_agreement():
    print("\n" + "=" * 78)
    print("1. the Python and R defaults must be the same number")
    print("=" * 78)
    pat = re.compile(r"DEFAULT_CV_SEED <- (\d+)L?")
    found = {}
    for p in sorted((REPO / "mcp" / "r_scripts").glob("cv_*.R")):
        m = pat.search(p.read_text(encoding="utf-8"))
        found[p.name] = int(m.group(1)) if m else None
    missing = [k for k, v in found.items() if v is None]
    check(not missing, "every cv_*.R declares DEFAULT_CV_SEED",
          f"{len(found) - len(missing)}/{len(found)} files"
          + (f"; missing in {missing}" if missing else ""))
    vals = {v for v in found.values() if v is not None}
    check(vals == {DEFAULT_CV_SEED},
          "R default equals bregsurv_agent.tools.DEFAULT_CV_SEED",
          f"python={DEFAULT_CV_SEED}, R={sorted(vals)}")


# ------------------------------------------------------- 2. determinism + provenance
def test_determinism():
    print("\n" + "=" * 78)
    print("2. an unseeded call is now deterministic, and says what pinned it")
    print("=" * 78)
    # The two designs differ by construction and the test has to say so.
    # get_fold (cohort) draws with sample, so the seed controls the split and
    # an unseeded run was non-reproducible. get_fold_cc (nested case-control)
    # uses NO randomness at all -- it greedily balances events across folds at
    # the stratum level -- so NCC cross-validation was always reproducible and
    # its loss must be INVARIANT to the seed. Asserting that invariance pins the
    # design fact down: if get_fold_cc ever became random, this fails.
    cases = ([(t, BASE, {}, "cohort") for t in COHORT_TOOLS]
             + [(t, BASE, extra, "cohort") for t, extra in SLOW_TOOLS]
             + [(t, NCC_BASE, {}, "ncc") for t in NCC_TOOLS])
    fold_support = None
    for tool, base, extra, design in cases:
        a = _run_r(f"{tool}.R", dict(base) | extra)
        b = _run_r(f"{tool}.R", dict(base) | extra)
        if a.get("status") != "ok":
            check(False, f"{tool:<20} runs", a.get("message", "")[:60])
            continue
        la, lb = losses(a), losses(b)
        check(la is not None and la == lb,
              f"{tool:<20} two unseeded runs identical",
              f"seed={a.get('seed')} source={a.get('seed_source')}")
        check(a.get("seed") == DEFAULT_CV_SEED
              and a.get("seed_source") == "bridge_default",
              f"{tool:<20} records the default it applied",
              f"seed={a.get('seed')}, source={a.get('seed_source')}")
        c = _run_r(f"{tool}.R", dict(base) | extra | {"seed": 4242})
        recorded = c.get("seed") == 4242 and c.get("seed_source") == "caller"
        if design == "cohort":
            check(recorded and losses(c) != la,
                  f"{tool:<20} the seed is recorded AND controls the split",
                  f"seed={c.get('seed')}, source={c.get('seed_source')}, "
                  f"loss changed={losses(c) != la}")
        else:
            check(recorded and losses(c) == la,
                  f"{tool:<20} seed recorded; split seed-invariant by design",
                  "get_fold_cc is deterministic, so NCC never had this defect")
        if fold_support is None:
            fold_support = isinstance(a.get("folds"), list)
    return bool(fold_support)


# ----------------------------------------------------------- 3. the RNG-kind record
def test_rng_kind(fold_support):
    print("\n" + "=" * 78)
    print("3. the RNG kind and the fold assignment travel with the result")
    print("=" * 78)
    r = _run_r("cv_coxkl.R", dict(BASE))
    if fold_support:
        check(r.get("rng_kind") == "Mersenne-Twister",
              "rng_kind is recorded and pinned", f"rng_kind={r.get('rng_kind')}")
        f = r.get("folds")
        check(isinstance(f, list) and len(f) == r.get("n_obs")
              and set(f) == set(range(1, r["nfolds"] + 1)),
              "the fold assignment is returned",
              f"{len(f)} subjects across {len(set(f))} folds")
    else:
        skip("rng_kind / folds returned by the estimator library",
             "the INSTALLED BregSurv predates this change -- run "
             "devtools::install(); the dispatcher correctly reports absence "
             "rather than inventing a value")
        check(r.get("folds") is None and r.get("rng_kind") is None,
              "absence is reported, not fabricated",
              f"folds={r.get('folds')}, rng_kind={r.get('rng_kind')}")


# --------------------------------------------------- 4. repro.R fails closed
def test_repro():
    """The fold check has to be able to STOP, or it is decoration.

    This is ported from the V2 suite, which exercised the same property
    against the generator that was retired on 2026-08-19. The happy path -- a
    replay that reproduces -- is covered by test_pipeline_e2e and
    test_family_cells. What neither covers is the failing path, and a guard
    whose failure branch is never executed is a comment: it will be the line
    someone cites as proof the replay matched.
    """
    print("\n" + "=" * 78)
    print("4. repro.R STOPS when the recorded split is not reproduced")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        rda = build_fixture(tdp)
        prof = _run_r("profile_columns.R", {
            "data_path": rda, "data_expr": "D", "external_beta_expr": "beta_ext"})
        decl = parse_reply(prof, {"time": "followup_days", "event": "died",
                                  "event_value": "1",
                                  "covariates": "age, bmi, egfr",
                                  "time_zero": "yes"})
        res = pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                           external_beta_expr="beta_ext", profile=prof,
                           nlambda=6, run_r=_run_r)
        paths = res.save(str(tdp / "run"))
        script = Path(paths["repro"])
        env = dict(os.environ, BREGSURV_R_SCRIPTS=str(REPO / "mcp" / "r_scripts"))

        def _run(path):
            return subprocess.run(
                [_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                 str(path), rda], capture_output=True, text=True, env=env,
                stdin=subprocess.DEVNULL, timeout=1800)

        r_ok = _run(script)
        check("fold assignment REPRODUCED" in (r_ok.stdout + r_ok.stderr),
              "an untouched repro.R reproduces the split", "the baseline")

        # move ONE subject to another fold and nothing else
        text = script.read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("expected <- c("))
        nums = line[len("expected <- c("):-1].split(", ")
        nums[0] = str((int(nums[0]) % 5) + 1)
        moved = script.with_name("repro_moved.R")
        moved.write_text(
            text.replace(line, "expected <- c(" + ", ".join(nums) + ")"),
            encoding="utf-8")
        r_bad = _run(moved)
        out = r_bad.stdout + r_bad.stderr
        check(r_bad.returncode != 0 and "differs from the" in out,
              "one subject in the wrong fold STOPS the replay",
              "and it says the losses below are not the ones reported")
        check("fold assignment REPRODUCED" not in out,
              "and it does not claim reproduction on the way out")



def main():
    test_constant_agreement()
    fold_support = test_determinism()
    test_rng_kind(fold_support)
    test_repro()
    print("\n" + "=" * 78)
    print(f"RESULT: {passed}/{passed + failed} passed"
          + (f", {skipped} skipped (need devtools::install)" if skipped else ""))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
