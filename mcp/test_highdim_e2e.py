"""End-to-end test driver for the highdim MCP tools (chunked roll-out).

As each chunk lands, append cases here. Re-run the whole file to make sure
prior chunks still pass. Uses small etas (2-3 values) and small nlambda
(10-20) because ridge is slow on the example data.

Chunk 1 (Cox KL ridge):   fit_coxkl_ridge   + cv_coxkl_ridge
Chunk 2 (Cox MDTL ridge): fit_cox_MDTL_ridge + cv_cox_MDTL_ridge

For each chunk, also verify the new notice/plot-hint fields:
  * `_notice_speed_slow`     — every ridge tool, on success
  * `_notice_eta_default`    — fit_*_ridge ONLY when eta omitted
  * `_followup_offer_plot`   — every cv_* tool
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

# We test through the FastMCP-decorated Python tool functions (not the bare
# _run_r) because notice attachment lives in the Python layer.
import server  # noqa: E402

DATA_HIGHDIM    = str(REPO / "data" / "ExampleData_highdim.rda")
DATA_INDI       = str(REPO / "data" / "ExampleData_indi.rda")
DATA_CC_HIGHDIM = str(REPO / "data" / "ExampleData_cc_highdim.rda")
DATA_CC_INDI    = str(REPO / "data" / "ExampleData_cc_indi.rda")

ETAS_SMALL = [0.0, 0.5]   # 2 etas only — ridge cv is slow
NLAMBDA_SMALL = 10        # 10 lambdas instead of default 100


def _fmt_keys(d: dict, keys: list[str]) -> str:
    parts = []
    for k in keys:
        v = d.get(k, "<missing>")
        if isinstance(v, list):
            v = f"len={len(v)}"
        elif isinstance(v, dict):
            v = "{" + ",".join(f"{kk}=..." for kk in v.keys()) + "}"
        elif isinstance(v, str) and len(v) > 40:
            v = repr(v[:37] + "...")
        parts.append(f"{k}={v}")
    return "  ".join(parts)


def run_call(name: str, fn, kwargs: dict, expect: str,
             ok_keys: list[str] | None = None,
             must_have_fields: list[str] | None = None,
             must_not_have_fields: list[str] | None = None,
             err_must_contain: list[str] | None = None) -> bool:
    print(f"\n[{name}]")
    res = fn(**kwargs)
    status = res.get("status")
    if expect == "ok":
        if status != "ok":
            print(f"  FAIL  status={status}  message={res.get('message')!r}")
            if "stderr" in res:
                print(f"        stderr: {res['stderr'][:600]}")
            return False
        for fld in (must_have_fields or []):
            if fld not in res:
                print(f"  FAIL  expected field {fld!r} missing from result")
                return False
        for fld in (must_not_have_fields or []):
            if fld in res:
                print(f"  FAIL  field {fld!r} should NOT be in result but is present")
                return False
        print(f"  PASS  {_fmt_keys(res, ok_keys or [])}")
        if must_have_fields:
            print(f"        notices present: {sorted(set(must_have_fields) & set(res.keys()))}")
        return True
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
    print("Highdim MCP tools — Chunks 1+2+3+4 (Cox ridge + Cox enet + NCC enet)")
    print(f"data: {DATA_HIGHDIM}")
    print(f"etas grid: {ETAS_SMALL}   nlambda: {NLAMBDA_SMALL}")
    print("=" * 72)

    results = []

    base = dict(
        data_path=DATA_HIGHDIM,
        z_expr="ExampleData_highdim$train$z",
        time_expr="ExampleData_highdim$train$time",
        delta_expr="ExampleData_highdim$train$status",
        stratum_expr="ExampleData_highdim$train$stratum",
        beta_expr="ExampleData_highdim$beta_external",
    )

    # ----- Chunk 1: Cox KL ridge ------------------------------------------
    print("\n" + "-" * 72 + "\n  CHUNK 1: Cox KL ridge\n" + "-" * 72)

    results.append(run_call(
        "1.1 fit_coxkl_ridge (eta=0.5 explicit, with notices check)",
        server.fit_coxkl_ridge,
        dict(base, eta=0.5, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "lambda", "beta", "n_lambda", "external_via"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "1.2 fit_coxkl_ridge (eta omitted -> default 0 + notice)",
        server.fit_coxkl_ridge,
        dict(base, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    results.append(run_call(
        "1.3 cv_coxkl_ridge (V&VH, nfolds=3)",
        server.cv_coxkl_ridge,
        dict(base, etas=ETAS_SMALL, cv_criteria="V&VH",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "etas", "cv_metric", "best_lambda_per_eta",
                 "best", "beta_best_per_eta"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "1.4 cv_coxkl_ridge with NCC 'loss' (must reject)",
        server.cv_coxkl_ridge,
        dict(base, etas=ETAS_SMALL, cv_criteria="loss",
             nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["Cox-family", "loss"],
    ))

    # ----- Chunk 2: Cox MDTL ridge ----------------------------------------
    print("\n" + "-" * 72 + "\n  CHUNK 2: Cox MDTL ridge\n" + "-" * 72)

    base_mdtl = {k: v for k, v in base.items() if k != "stratum_expr"}
    base_mdtl["stratum_expr"] = base["stratum_expr"]

    results.append(run_call(
        "2.1 fit_cox_MDTL_ridge (eta=0.5 explicit, identity Q)",
        server.fit_cox_MDTL_ridge,
        dict(base_mdtl, eta=0.5, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "lambda", "beta", "n_lambda", "vcov_used"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "2.2 fit_cox_MDTL_ridge (eta omitted -> default 0 + notice)",
        server.fit_cox_MDTL_ridge,
        dict(base_mdtl, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    # vcov_inline: identity 50x50 to verify the inline vcov path
    identity50 = [[1.0 if i == j else 0.0 for j in range(50)] for i in range(50)]
    results.append(run_call(
        "2.3 fit_cox_MDTL_ridge with vcov_inline (50x50 identity)",
        server.fit_cox_MDTL_ridge,
        dict(base_mdtl, eta=0.5, nlambda=NLAMBDA_SMALL, vcov_inline=identity50),
        expect="ok",
        ok_keys=["vcov_used"],
    ))

    results.append(run_call(
        "2.4 cv_cox_MDTL_ridge (V&VH, nfolds=3, identity Q)",
        server.cv_cox_MDTL_ridge,
        dict(base_mdtl, etas=ETAS_SMALL, cv_criteria="V&VH",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "etas", "cv_metric", "best_lambda_per_eta",
                 "best", "beta_best_per_eta", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "2.5 cv_cox_MDTL_ridge with NCC 'loss' (must reject)",
        server.cv_cox_MDTL_ridge,
        dict(base_mdtl, etas=ETAS_SMALL, cv_criteria="loss",
             nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["Cox-family", "loss"],
    ))

    # ----- Chunk 3: Cox enet (KL, MDTL, indi) -----------------------------
    print("\n" + "-" * 72 + "\n  CHUNK 3: Cox enet (KL, MDTL, indi)\n" + "-" * 72)

    # KL enet (uses ExampleData_highdim p=50)
    results.append(run_call(
        "3.1 fit_coxkl_enet (eta=0.5, alpha=1.0)",
        server.fit_coxkl_enet,
        dict(base, eta=0.5, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "alpha", "lambda", "beta", "n_lambda", "external_via"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "3.2 fit_coxkl_enet (eta omitted -> default 0 + notice)",
        server.fit_coxkl_enet,
        dict(base, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "alpha"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    results.append(run_call(
        "3.3 cv_coxkl_enet (V&VH)",
        server.cv_coxkl_enet,
        dict(base, etas=ETAS_SMALL, alpha=1.0, cv_criteria="V&VH",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best", "beta_best_per_eta"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "3.4 cv_coxkl_enet with NCC 'loss' (must reject)",
        server.cv_coxkl_enet,
        dict(base, etas=ETAS_SMALL, cv_criteria="loss", nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["Cox-family", "loss"],
    ))

    # MDTL enet (uses ExampleData_highdim p=50)
    results.append(run_call(
        "3.5 fit_cox_MDTL_enet (eta=0.5, identity Q)",
        server.fit_cox_MDTL_enet,
        dict(base_mdtl, eta=0.5, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "alpha", "lambda", "beta", "vcov_used"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "3.6 fit_cox_MDTL_enet (eta omitted -> default 0 + notice)",
        server.fit_cox_MDTL_enet,
        dict(base_mdtl, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    results.append(run_call(
        "3.7 cv_cox_MDTL_enet (V&VH, identity Q)",
        server.cv_cox_MDTL_enet,
        dict(base_mdtl, etas=ETAS_SMALL, alpha=1.0, cv_criteria="V&VH",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "3.8 cv_cox_MDTL_enet with NCC 'AUC' (must reject)",
        server.cv_cox_MDTL_enet,
        dict(base_mdtl, etas=ETAS_SMALL, cv_criteria="AUC", nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["Cox-family", "AUC"],
    ))

    # indi enet — uses ExampleData_indi (p=10, internal n=500, external n=2000)
    base_indi = dict(
        data_path=DATA_INDI,
        z_int_expr="ExampleData_indi$internal$z",
        time_int_expr="ExampleData_indi$internal$time",
        delta_int_expr="ExampleData_indi$internal$status",
        z_ext_expr="ExampleData_indi$external$z",
        time_ext_expr="ExampleData_indi$external$time",
        delta_ext_expr="ExampleData_indi$external$status",
        stratum_int_expr="ExampleData_indi$internal$stratum",
        stratum_ext_expr="ExampleData_indi$external$stratum",
    )

    results.append(run_call(
        "3.9 fit_cox_indi_enet (etas plural, alpha=1.0)",
        server.fit_cox_indi_enet,
        dict(base_indi, etas=ETAS_SMALL, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["etas", "alpha", "beta_per_eta", "lambda_per_eta",
                 "n_obs_int", "n_obs_ext", "n_covariates", "n_etas",
                 "n_lambda_per_eta"],
        must_have_fields=["_notice_speed_slow"],
        # indi is plural-etas required => no eta-default policy
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "3.10 cv_cox_indi_enet (V&VH)",
        server.cv_cox_indi_enet,
        dict(base_indi, etas=ETAS_SMALL, alpha=1.0, cv_criteria="V&VH",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best",
                 "n_obs_int", "n_obs_ext"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "3.11 cv_cox_indi_enet with NCC 'Brier' (must reject)",
        server.cv_cox_indi_enet,
        dict(base_indi, etas=ETAS_SMALL, cv_criteria="Brier", nfolds=3,
             nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["Cox-family", "Brier"],
    ))

    # ----- Chunk 4: NCC enet (KL, MDTL, indi) -----------------------------
    print("\n" + "-" * 72 + "\n  CHUNK 4: NCC enet (KL, MDTL, indi)\n" + "-" * 72)

    # KL + MDTL NCC enet use ExampleData_cc_highdim (p=20, 1:5 matched)
    base_ncc = dict(
        data_path=DATA_CC_HIGHDIM,
        z_expr="ExampleData_cc_highdim$train$z",
        y_expr="ExampleData_cc_highdim$train$y",
        stratum_expr="ExampleData_cc_highdim$train$stratum",
        beta_expr="ExampleData_cc_highdim$beta_external",
    )

    # NCC KL enet
    results.append(run_call(
        "4.1 fit_ncckl_enet (eta=0.5, alpha=1.0)",
        server.fit_ncckl_enet,
        dict(base_ncc, eta=0.5, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "alpha", "lambda", "beta", "n_obs", "n_strata",
                 "n_covariates", "n_lambda", "external_via"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "4.2 fit_ncckl_enet (eta omitted -> default 0 + notice)",
        server.fit_ncckl_enet,
        dict(base_ncc, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    results.append(run_call(
        "4.3 cv_ncckl_enet (loss, nfolds=3)",
        server.cv_ncckl_enet,
        dict(base_ncc, etas=ETAS_SMALL, alpha=1.0, cv_criteria="loss",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best", "beta_best_per_eta",
                 "n_obs", "n_strata"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "4.4 cv_ncckl_enet with Cox 'V&VH' (must reject)",
        server.cv_ncckl_enet,
        dict(base_ncc, etas=ETAS_SMALL, cv_criteria="V&VH", nfolds=3,
             nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["NCC-family", "V&VH"],
    ))

    # NCC MDTL enet
    results.append(run_call(
        "4.5 fit_ncc_MDTL_enet (eta=0.5, identity Q)",
        server.fit_ncc_MDTL_enet,
        dict(base_ncc, eta=0.5, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "alpha", "lambda", "beta", "n_strata", "vcov_used"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "4.6 fit_ncc_MDTL_enet (eta omitted -> default 0 + notice)",
        server.fit_ncc_MDTL_enet,
        dict(base_ncc, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["eta", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_notice_eta_default"],
    ))

    results.append(run_call(
        "4.7 cv_ncc_MDTL_enet (loss, identity Q)",
        server.cv_ncc_MDTL_enet,
        dict(base_ncc, etas=ETAS_SMALL, alpha=1.0, cv_criteria="loss",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best", "n_strata", "vcov_used"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "4.8 cv_ncc_MDTL_enet with Cox 'CIndex_pooled' (must reject)",
        server.cv_ncc_MDTL_enet,
        dict(base_ncc, etas=ETAS_SMALL, cv_criteria="CIndex_pooled",
             nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["NCC-family", "CIndex_pooled"],
    ))

    # NCC indi enet — uses ExampleData_cc_indi (p=6 low-dim, dual cohort 1:4)
    base_ncc_indi = dict(
        data_path=DATA_CC_INDI,
        z_int_expr="ExampleData_cc_indi$internal$z",
        y_int_expr="ExampleData_cc_indi$internal$y",
        stratum_int_expr="ExampleData_cc_indi$internal$stratum",
        z_ext_expr="ExampleData_cc_indi$external$z",
        y_ext_expr="ExampleData_cc_indi$external$y",
        stratum_ext_expr="ExampleData_cc_indi$external$stratum",
    )

    results.append(run_call(
        "4.9 fit_ncc_indi_enet (etas plural, alpha=1.0)",
        server.fit_ncc_indi_enet,
        dict(base_ncc_indi, etas=ETAS_SMALL, alpha=1.0, nlambda=NLAMBDA_SMALL),
        expect="ok",
        ok_keys=["etas", "alpha", "beta_per_eta", "lambda_per_eta",
                 "n_obs_int", "n_obs_ext", "n_strata_int", "n_strata_ext",
                 "n_covariates", "n_etas", "n_lambda_per_eta"],
        must_have_fields=["_notice_speed_slow"],
        must_not_have_fields=["_notice_eta_default"],
    ))

    results.append(run_call(
        "4.10 cv_ncc_indi_enet (loss)",
        server.cv_ncc_indi_enet,
        dict(base_ncc_indi, etas=ETAS_SMALL, alpha=1.0, cv_criteria="loss",
             nfolds=3, nlambda=NLAMBDA_SMALL, seed=42),
        expect="ok",
        ok_keys=["criteria", "alpha", "etas", "cv_metric",
                 "best_lambda_per_eta", "best",
                 "n_obs_int", "n_obs_ext", "n_strata_int", "n_strata_ext"],
        must_have_fields=["_notice_speed_slow", "_followup_offer_plot"],
    ))

    results.append(run_call(
        "4.11 cv_ncc_indi_enet with Cox 'LinPred' (must reject)",
        server.cv_ncc_indi_enet,
        dict(base_ncc_indi, etas=ETAS_SMALL, cv_criteria="LinPred",
             nfolds=3, nlambda=NLAMBDA_SMALL),
        expect="error",
        err_must_contain=["NCC-family", "LinPred"],
    ))

    print("\n" + "=" * 72)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} passed")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
