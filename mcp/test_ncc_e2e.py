"""End-to-end test driver for the 6 NCC MCP tools.

Bypasses FastMCP and shells the R dispatchers directly via server._run_r,
which is exactly what the live MCP tools do at runtime. Tests:

  Happy path (6 tools):
    1. fit_ncckl                — KL  on ExampleData_cc_lowdim
    2. fit_ncc_MDTL             — MDTL on ExampleData_cc_lowdim
    3. fit_ncc_indi             — indi on ExampleData_cc_indi
    4. cv_ncckl                 — KL  CV on ExampleData_cc_lowdim
    5. cv_ncc_MDTL              — MDTL CV on ExampleData_cc_lowdim
    6. cv_ncc_indi              — indi CV on ExampleData_cc_indi

  Whitelist (3 tools):
    7. cv_ncckl     with cv_criteria="V&VH"  -> must error
    8. cv_ncc_MDTL  with cv_criteria="V&VH"  -> must error
    9. cv_ncc_indi  with cv_criteria="V&VH"  -> must error

Prints pass/fail for each, with extracted key fields on success and the
structured error message on failure. Exits non-zero if any test fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from server import _run_r  # noqa: E402

DATA_LOWDIM = str(REPO / "data" / "ExampleData_cc_lowdim.rda")
DATA_INDI   = str(REPO / "data" / "ExampleData_cc_indi.rda")

ETAS_SHORT = [0.0, 0.5, 1.0]


def _fmt_keys(d: dict, keys: list[str]) -> str:
    parts = []
    for k in keys:
        v = d.get(k, "<missing>")
        if isinstance(v, list):
            v = f"len={len(v)}"
        parts.append(f"{k}={v}")
    return "  ".join(parts)


def run_case(name: str, script: str, payload: dict, expect: str,
             ok_keys: list[str] | None = None,
             err_must_contain: list[str] | None = None) -> bool:
    """Run one R dispatcher and print pass/fail.

    expect:  "ok"    -> result.status == "ok" required
             "error" -> result.status == "error" required (and any
                        err_must_contain substrings must appear in message)
    """
    print(f"\n[{name}]  -> r_scripts/{script}")
    res = _run_r(script, payload, timeout_s=300)
    status = res.get("status")
    if expect == "ok":
        if status == "ok":
            print(f"  PASS  {_fmt_keys(res, ok_keys or [])}")
            return True
        print(f"  FAIL  status={status}  message={res.get('message')!r}")
        if "stderr" in res:
            print(f"        stderr: {res['stderr'][:600]}")
        return False
    else:
        if status != "error":
            print(f"  FAIL  expected error, got status={status}")
            return False
        msg = str(res.get("message", ""))
        for sub in (err_must_contain or []):
            if sub not in msg:
                print(f"  FAIL  error message missing {sub!r}: {msg!r}")
                return False
        print(f"  PASS  rejected as expected: {msg[:120]}")
        return True


def main() -> int:
    print("=" * 72)
    print("NCC MCP tools — E2E verification")
    print(f"data lowdim: {DATA_LOWDIM}")
    print(f"data indi:   {DATA_INDI}")
    print("=" * 72)

    results = []

    # ----- Happy path: lowdim (KL + MDTL) ----------------------------------
    base_lowdim = {
        "data_path":    DATA_LOWDIM,
        "z_expr":       "ExampleData_cc_lowdim$train$z",
        "y_expr":       "ExampleData_cc_lowdim$train$y",
        "stratum_expr": "ExampleData_cc_lowdim$train$stratum",
        "beta_expr":    "ExampleData_cc_lowdim$beta_external",
        "etas":         ETAS_SHORT,
    }

    results.append(run_case(
        "1. fit_ncckl",
        "fit_ncckl.R",
        dict(base_lowdim, method="breslow"),
        expect="ok",
        ok_keys=["eta", "beta", "likelihood", "n_obs", "n_strata",
                 "n_covariates", "n_etas", "method", "external_via"],
    ))

    results.append(run_case(
        "2. fit_ncc_MDTL (identity Q)",
        "fit_ncc_MDTL.R",
        base_lowdim,
        expect="ok",
        ok_keys=["eta", "beta", "likelihood", "n_obs", "n_strata",
                 "n_covariates", "n_etas", "vcov_used"],
    ))

    # ----- Happy path: indi -------------------------------------------------
    base_indi = {
        "data_path":        DATA_INDI,
        "z_int_expr":       "ExampleData_cc_indi$internal$z",
        "y_int_expr":       "ExampleData_cc_indi$internal$y",
        "stratum_int_expr": "ExampleData_cc_indi$internal$stratum",
        "z_ext_expr":       "ExampleData_cc_indi$external$z",
        "y_ext_expr":       "ExampleData_cc_indi$external$y",
        "stratum_ext_expr": "ExampleData_cc_indi$external$stratum",
        "etas":             ETAS_SHORT,
    }

    results.append(run_case(
        "3. fit_ncc_indi",
        "fit_ncc_indi.R",
        base_indi,
        expect="ok",
        ok_keys=["eta", "beta", "n_obs_int", "n_obs_ext",
                 "n_strata_int", "n_strata_ext", "n_covariates", "n_etas"],
    ))

    # ----- CV happy path ---------------------------------------------------
    results.append(run_case(
        "4. cv_ncckl (loss, nfolds=3)",
        "cv_ncckl.R",
        dict(base_lowdim, cv_criteria="loss", nfolds=3, seed=42),
        expect="ok",
        ok_keys=["criteria", "nfolds", "etas", "cv_metric", "best",
                 "n_obs", "n_strata", "n_covariates", "n_etas"],
    ))

    results.append(run_case(
        "5. cv_ncc_MDTL (loss, nfolds=3)",
        "cv_ncc_MDTL.R",
        dict(base_lowdim, cv_criteria="loss", nfolds=3, seed=42),
        expect="ok",
        ok_keys=["criteria", "nfolds", "etas", "cv_metric", "best",
                 "n_obs", "n_strata", "n_covariates", "n_etas", "vcov_used"],
    ))

    results.append(run_case(
        "6. cv_ncc_indi (loss, nfolds=3)",
        "cv_ncc_indi.R",
        dict(base_indi, cv_criteria="loss", nfolds=3, seed=42),
        expect="ok",
        ok_keys=["criteria", "nfolds", "etas", "cv_metric", "best",
                 "n_obs_int", "n_obs_ext", "n_covariates", "n_etas"],
    ))

    # ----- CV criteria whitelist (the API landmine) ------------------------
    results.append(run_case(
        "7. cv_ncckl with V&VH (must reject)",
        "cv_ncckl.R",
        dict(base_lowdim, cv_criteria="V&VH", nfolds=3),
        expect="error",
        err_must_contain=["NCC-family", "V&VH"],
    ))

    results.append(run_case(
        "8. cv_ncc_MDTL with V&VH (must reject)",
        "cv_ncc_MDTL.R",
        dict(base_lowdim, cv_criteria="V&VH", nfolds=3),
        expect="error",
        err_must_contain=["NCC-family", "V&VH"],
    ))

    results.append(run_case(
        "9. cv_ncc_indi with V&VH (must reject)",
        "cv_ncc_indi.R",
        dict(base_indi, cv_criteria="V&VH", nfolds=3),
        expect="error",
        err_must_contain=["NCC-family", "V&VH"],
    ))

    # ----- Alternative NCC criteria (AUC / Brier / CIndex) ------------------
    for crit in ("AUC", "Brier", "CIndex"):
        results.append(run_case(
            f"10. cv_ncckl with {crit}",
            "cv_ncckl.R",
            dict(base_lowdim, cv_criteria=crit, nfolds=3, seed=42),
            expect="ok",
            ok_keys=["criteria", "cv_metric", "best"],
        ))

    # ----- beta_inline path (alternative to beta_expr) ----------------------
    beta_ext_inline = [0.85, -0.85, 0.85, -0.85, 0.85, -0.85]
    base_lowdim_inline = {k: v for k, v in base_lowdim.items() if k != "beta_expr"}
    base_lowdim_inline["beta_inline"] = beta_ext_inline
    results.append(run_case(
        "13. fit_ncckl with beta_inline",
        "fit_ncckl.R",
        dict(base_lowdim_inline, method="breslow"),
        expect="ok",
        ok_keys=["external_via", "n_covariates"],
    ))

    # ----- vcov_inline path for MDTL ---------------------------------------
    identity6 = [[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)]
    results.append(run_case(
        "14. fit_ncc_MDTL with vcov_inline",
        "fit_ncc_MDTL.R",
        dict(base_lowdim, vcov_inline=identity6),
        expect="ok",
        ok_keys=["vcov_used", "n_covariates"],
    ))

    # ----- Mutual exclusion: beta_expr + beta_inline both supplied ---------
    results.append(run_case(
        "15. fit_ncckl with both beta_expr and beta_inline (must reject)",
        "fit_ncckl.R",
        dict(base_lowdim, beta_inline=beta_ext_inline),
        expect="error",
        err_must_contain=["only one"],
    ))

    print("\n" + "=" * 72)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} passed")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
