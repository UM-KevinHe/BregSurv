"""E2E test for the start_analysis wizard.

Covers:
  * State-machine progression (Q1 → Q5 → DONE)
  * Skip-ahead (all params at once → DONE immediately)
  * Fallbacks: NCC + ridge, indi + ridge, ties + regularization
  * Out-of-scope: external_info=none → recommend `survival` package
  * i18n: en vs zh — verify question text differs
  * Tool resolution: each leaf maps to the correct MCP tool name
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import server  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}{('  — ' + detail) if detail else ''}")
    return ok


def test_step_by_step_cox_kl_base_fit() -> bool:
    print("\n--- Test 1: step-by-step Cox + KL + base + fit → fit_coxkl ---")
    results = []

    r = server.start_analysis()
    results.append(_check("Q1 fresh call returns step Q1_study_design",
                          r.get("step") == "Q1_study_design"))

    r = server.start_analysis(study_design="cohort")
    results.append(_check("Q2 cohort branch returns step Q2_has_ties",
                          r.get("step") == "Q2_has_ties"))

    r = server.start_analysis(study_design="cohort", has_ties=False)
    results.append(_check("Q3 returned",
                          r.get("step") == "Q3_external_info"))

    r = server.start_analysis(study_design="cohort", has_ties=False,
                              external_info="beta_only")
    results.append(_check("Q4 returned",
                          r.get("step") == "Q4_regularization"))

    r = server.start_analysis(study_design="cohort", has_ties=False,
                              external_info="beta_only", regularization="none")
    results.append(_check("Q5 returned",
                          r.get("step") == "Q5_output_type"))

    r = server.start_analysis(study_design="cohort", has_ties=False,
                              external_info="beta_only", regularization="none",
                              output_type="fit")
    results.append(_check("DONE step",
                          r.get("step") == "DONE",
                          f"got step={r.get('step')}"))
    results.append(_check("recommended_mcp_tool == fit_coxkl",
                          r.get("recommended_mcp_tool") == "fit_coxkl",
                          f"got {r.get('recommended_mcp_tool')}"))

    return all(results)


def test_cox_ties_only_base() -> bool:
    print("\n--- Test 2: Cox + ties + KL → fit_coxkl_ties (only base, no _enet/_ridge) ---")
    r = server.start_analysis(study_design="cohort", has_ties=True,
                              external_info="beta_only", regularization="none",
                              output_type="fit")
    return _check("recommended_mcp_tool == fit_coxkl_ties",
                  r.get("recommended_mcp_tool") == "fit_coxkl_ties",
                  f"got {r.get('recommended_mcp_tool')}")


def test_ties_regularization_fallback() -> bool:
    print("\n--- Test 3: Cox + ties + enet → fallback (ties don't support regularization) ---")
    r = server.start_analysis(study_design="cohort", has_ties=True,
                              external_info="beta_only", regularization="enet")
    ok1 = _check("step is fallback_required",
                 r.get("step") == "Q4_ties_regularized_unavailable")
    ok2 = _check("user_facing_message is present",
                 isinstance(r.get("user_facing_message"), str)
                 and len(r["user_facing_message"]) > 20)
    ok3 = _check("only 'none' offered as next regularization",
                 [o["key"] for o in r.get("options", [])] == ["none"])
    return ok1 and ok2 and ok3


def test_ncc_ridge_fallback() -> bool:
    print("\n--- Test 4: NCC + ridge → fallback (NCC has no ridge) ---")
    r = server.start_analysis(study_design="ncc", external_info="beta_only",
                              regularization="ridge")
    ok1 = _check("step is fallback_required",
                 r.get("step") == "Q4_NCC_ridge_unavailable")
    ok2 = _check("offers none + enet (not ridge)",
                 sorted([o["key"] for o in r.get("options", [])]) == ["enet", "none"])
    return ok1 and ok2


def test_indi_ridge_fallback() -> bool:
    print("\n--- Test 5: Cox + indi + ridge → fallback (indi has no ridge) ---")
    r = server.start_analysis(study_design="cohort", has_ties=False,
                              external_info="individual_data",
                              regularization="ridge")
    return _check("step is Q4_indi_ridge_unavailable",
                  r.get("step") == "Q4_indi_ridge_unavailable",
                  f"got {r.get('step')}")


def test_skip_ahead_all_at_once() -> bool:
    print("\n--- Test 6: skip-ahead all 5 answers → DONE immediately ---")
    r = server.start_analysis(
        study_design="ncc",
        external_info="individual_data",
        regularization="enet",
        output_type="cv",
    )
    ok1 = _check("DONE step", r.get("step") == "DONE")
    ok2 = _check("recommended_mcp_tool == cv_ncc_indi_enet",
                 r.get("recommended_mcp_tool") == "cv_ncc_indi_enet",
                 f"got {r.get('recommended_mcp_tool')}")
    return ok1 and ok2


def test_out_of_scope_no_external() -> bool:
    print("\n--- Test 7: external_info=none → out_of_scope (recommend survival package) ---")
    r = server.start_analysis(study_design="cohort", has_ties=False,
                              external_info="none")
    ok1 = _check("recommendation_type == out_of_scope",
                 r.get("recommendation_type") == "out_of_scope")
    ok2 = _check("no recommended_mcp_tool field",
                 "recommended_mcp_tool" not in r)
    msg = r.get("user_facing_message", "")
    ok3 = _check("user_facing_message mentions `survival`",
                 "survival" in msg.lower(),
                 f"msg starts: {msg[:80]!r}")
    return ok1 and ok2 and ok3


def test_localization_zh() -> bool:
    print("\n--- Test 8: user_language=zh returns Chinese strings ---")
    r_en = server.start_analysis(user_language="en")
    r_zh = server.start_analysis(user_language="zh")
    ok1 = _check("en and zh questions differ",
                 r_en.get("question") != r_zh.get("question"))
    # Check Chinese contains a Chinese character
    has_chinese = any("一" <= ch <= "鿿" for ch in (r_zh.get("question") or ""))
    ok2 = _check("zh question contains Chinese chars",
                 has_chinese,
                 f"zh question: {r_zh.get('question')!r}")
    return ok1 and ok2


def test_complete_lookup_table() -> bool:
    """Verify all 16 supported (study_design, external_info, regularization, output_type)
    combinations resolve to a real MCP tool that exists in server.py."""
    print("\n--- Test 9: every supported state combo resolves to an existing MCP tool ---")
    cases = [
        # Cox no-ties × KL/MDTL/indi × {none, enet, ridge} × {fit, cv}
        ("cohort", False, "beta_only",       "none",  "fit",  "fit_coxkl"),
        ("cohort", False, "beta_only",       "none",  "cv",   "cv_coxkl"),
        ("cohort", False, "beta_only",       "enet",  "fit",  "fit_coxkl_enet"),
        ("cohort", False, "beta_only",       "enet",  "cv",   "cv_coxkl_enet"),
        ("cohort", False, "beta_only",       "ridge", "fit",  "fit_coxkl_ridge"),
        ("cohort", False, "beta_only",       "ridge", "cv",   "cv_coxkl_ridge"),
        ("cohort", False, "beta_and_vcov",   "none",  "fit",  "fit_cox_MDTL"),
        ("cohort", False, "beta_and_vcov",   "none",  "cv",   "cv_cox_MDTL"),
        ("cohort", False, "beta_and_vcov",   "enet",  "fit",  "fit_cox_MDTL_enet"),
        ("cohort", False, "beta_and_vcov",   "ridge", "cv",   "cv_cox_MDTL_ridge"),
        ("cohort", False, "individual_data", "none",  "fit",  "fit_cox_indi"),
        ("cohort", False, "individual_data", "enet",  "cv",   "cv_cox_indi_enet"),
        # Cox ties (only base ties-aware)
        ("cohort", True,  "beta_only",       "none",  "fit",  "fit_coxkl_ties"),
        ("cohort", True,  "beta_only",       "none",  "cv",   "cv_coxkl_ties"),
        # NCC × KL/MDTL/indi × {none, enet} × {fit, cv}
        ("ncc",    None,  "beta_only",       "none",  "fit",  "fit_ncckl"),
        ("ncc",    None,  "beta_only",       "enet",  "cv",   "cv_ncckl_enet"),
        ("ncc",    None,  "beta_and_vcov",   "none",  "cv",   "cv_ncc_MDTL"),
        ("ncc",    None,  "beta_and_vcov",   "enet",  "fit",  "fit_ncc_MDTL_enet"),
        ("ncc",    None,  "individual_data", "none",  "fit",  "fit_ncc_indi"),
        ("ncc",    None,  "individual_data", "enet",  "cv",   "cv_ncc_indi_enet"),
    ]
    results = []
    for sd, ti, ei, rg, ot, expected in cases:
        kw = dict(study_design=sd, external_info=ei, regularization=rg, output_type=ot)
        if ti is not None:
            kw["has_ties"] = ti
        r = server.start_analysis(**kw)
        got = r.get("recommended_mcp_tool")
        ok = (got == expected) and hasattr(server, expected)
        results.append(_check(f"{sd}/{ti}/{ei}/{rg}/{ot} → {expected}", ok,
                              "" if ok else f"got {got!r}, exists={hasattr(server, expected)}"))
    return all(results)


def main() -> int:
    print("=" * 72)
    print("start_analysis wizard — E2E verification")
    print("=" * 72)

    tests = [
        test_step_by_step_cox_kl_base_fit,
        test_cox_ties_only_base,
        test_ties_regularization_fallback,
        test_ncc_ridge_fallback,
        test_indi_ridge_fallback,
        test_skip_ahead_all_at_once,
        test_out_of_scope_no_external,
        test_localization_zh,
        test_complete_lookup_table,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 72}\nRESULT: {passed}/{total} test groups passed\n{'=' * 72}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
