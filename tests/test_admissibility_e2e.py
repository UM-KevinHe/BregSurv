"""End-to-end test driver for the admissibility gate (C1's poisoned-fixture suite).

This is a DETERMINISTIC unit test with a 100% pass bar, not an LLM eval. The
language model is not involved anywhere in it: the gate is a precondition on the
data, and its verdict is not a matter of judgement.

Two things are asserted for every poisoned fixture:

  1. the gate refuses it, with the SPECIFIC refusal code expected -- refusing
     for the wrong reason is a failure, not a pass;
  2. without the gate the fit would have returned a number anyway. That second
     column is the whole argument for the gate's existence, so the suite prints
     it rather than assuming the reader believes it.

The clean controls must NOT be refused. Over-refusal is the failure mode that
would make the gate unusable on real data, so it is tested as hard as
under-refusal.

Run:  python test_admissibility_e2e.py
Exits non-zero if any case fails.
"""
from __future__ import annotations

import json
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

# fixture name -> (refusal code expected, or None for a clean control)
COHORT_CASES = [
    ("clean",          None,                       "clean control"),
    ("clean_recoded",  None,                       "1/2 coding, event_value=2"),
    ("competing",      "competing_risks",          "a third of events are another cause"),
    ("event_factor",   "event_column_is_factor",   "status stored as a factor"),
    ("all_events",     "degenerate_outcome",       "every subject an event"),
    ("no_events",      "degenerate_outcome",       "no subject an event"),
    ("event_na",       "event_has_missing",        "event indicator missing"),
    ("time_na",        "time_has_missing",         "follow-up time missing"),
    ("time_zero",      "time_not_positive",        "zero follow-up time"),
    ("time_negative",  "time_not_positive",        "negative follow-up time"),
    ("time_character", "time_not_numeric",         "time column is character"),
    ("cov_factor",     "covariate_not_numeric",    "a covariate is a factor"),
    ("cov_na",         "covariate_missing_values", "a covariate has NAs"),
    ("cov_constant",   None,                       "constant covariate: advisory only"),
    ("time_infinite",  "time_not_finite",          "infinite follow-up time"),
    ("cov_infinite",   "covariate_not_finite",     "infinite covariate value"),
    ("duplicated_rows", None,                      "duplicated rows: advisory, the analyst's call"),
    ("collinear_cov",  None,                       "collinear covariate: advisory, the penalties handle it"),
    ("heavy_ties",     None,                       "heavy ties: routing, not refusal"),
]

NCC_CASES = [
    ("clean",        None,                     "clean control"),
    ("y_factor",     "event_column_is_factor",  "case indicator is a factor"),
    ("y_degenerate", "degenerate_outcome",      "every subject a case"),
]

# fixtures whose declaration, not whose data, is the problem
DECLARATION_CASES = [
    ("clean", {},                                    "time_zero_undeclared",
     "the time-zero question was not answered"),
    ("clean", {"covariates_time_zero": "unsure"},    "time_zero_undeclared",
     "answered 'unsure'"),
    ("clean", {"covariates_time_zero": "no"},        "time_varying_covariates",
     "a covariate changes after baseline"),
]

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
passed = failed = 0


def check(ok: bool, label: str, note: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def build_fixtures(path: Path) -> None:
    r = subprocess.run(
        [_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
         str(HERE / "poison_fixtures.R"), str(path)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit("could not build fixtures")
    print(DIM + r.stdout.strip() + OFF)


def would_have_run(payload: dict) -> str:
    """Did the estimator return a number for this input? The gate's raison d'etre."""
    res = _run_r("fit_coxkl.R", payload)
    if res.get("status") != "ok":
        return "fit errors: " + res.get("message", "")[:34]
    beta = res.get("beta")
    try:
        first = [row[0] for row in beta][:3]
        if any(v is None for v in first):
            return "fit returns all-NA coefficients"
        return "fit RETURNS A NUMBER: " + " ".join(f"{v:+.4f}" for v in first)
    except Exception:
        return "fit returns something"


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        fx = Path(td) / "PoisonFixtures.rda"
        build_fixtures(fx)
        dp = str(fx)

        print("\n" + "=" * 78)
        print("COHORT fixtures")
        print("=" * 78)
        for name, code, note in COHORT_CASES:
            base = {
                "data_path": dp,
                "z_expr": f"POISON${name}$z",
                "time_expr": f"POISON${name}$time",
                "delta_expr": f"POISON${name}$delta",
                "covariates_time_zero": "yes",
            }
            if name == "clean_recoded":
                base["event_value"] = 2
            g = _run_r("check_admissibility.R", dict(base))
            if g.get("status") != "ok":
                check(False, f"{name:<15}", "gate itself errored: "
                      + str(g.get("message"))[:60])
                continue
            got = [r["code"] for r in g["refusals"]]
            if code is None:
                check(g["admissible"], f"{name:<15} admissible",
                      f"{note}; refusals={got or 'none'}")
                if name == "heavy_ties":
                    adv = [a["code"] for a in g["advisories"]]
                    # Policy change 2026-08-19: heavy ties are DISCLOSED,
                    # never routed. Whether a tie correction is applied is the
                    # analyst's decision and the default is none, so the gate
                    # measures the fraction and says so without instructing
                    # anyone. It used to emit route$ties and the pipeline acted
                    # on it, swapping two of ten candidates onto a different
                    # likelihood and then ranking across the two scales.
                    check("tied_event_times" in adv
                          and "ties" not in (g.get("route") or {}),
                          f"{'':<15} discloses ties, does NOT route on them",
                          f"tie_fraction={g['summary']['tie_fraction']}, "
                          f"route carries no instruction")
                if name == "duplicated_rows":
                    adv = [a["code"] for a in g["advisories"]]
                    check("duplicate_rows" in adv,
                          f"{'':<15} advises on the duplicated rows",
                          f"advisories={adv}")
                if name == "collinear_cov":
                    adv = [a["code"] for a in g["advisories"]]
                    check("rank_deficient" in adv,
                          f"{'':<15} advises on the rank deficiency",
                          f"advisories={adv}")
                if name == "cov_constant":
                    adv = [a["code"] for a in g["advisories"]]
                    check("covariate_constant" in adv,
                          f"{'':<15} advises on the constant column",
                          f"advisories={adv}")
                if name == "clean_recoded":
                    adv = [a["code"] for a in g["advisories"]]
                    s = g["summary"]
                    # the advisory has to fire, and event_value=2 has to have
                    # been honoured: counting the wrong level would give either
                    # every subject or none
                    check("event_recoded" in adv and 0 < s["n_events"] < s["n_obs"],
                          f"{'':<15} flags the non-0/1 coding",
                          f"advisories={adv}; "
                          f"n_events={s['n_events']} of {s['n_obs']}")
            else:
                fit = would_have_run({k: v for k, v in base.items()
                                      if k.endswith("_expr") or k == "data_path"}
                                     | {"beta_expr": "bex", "etas": [5.0]})
                check(not g["admissible"] and code in got,
                      f"{name:<15} refused [{code}]",
                      f"{note} | without the gate: {fit}")

        print("\n" + "=" * 78)
        print("NESTED CASE-CONTROL fixtures")
        print("=" * 78)
        for name, code, note in NCC_CASES:
            g = _run_r("check_admissibility.R", {
                "data_path": dp,
                "z_expr": f"NCC${name}$z",
                "y_expr": f"NCC${name}$y",
                "stratum_expr": f"NCC${name}$stratum",
                "covariates_time_zero": "yes",
            })
            if g.get("status") != "ok":
                check(False, f"{name:<15}", "gate errored: "
                      + str(g.get("message"))[:60])
                continue
            got = [r["code"] for r in g["refusals"]]
            if code is None:
                check(g["admissible"], f"{name:<15} admissible",
                      f"{note}; design={g['summary']['design']}")
            else:
                check(not g["admissible"] and code in got,
                      f"{name:<15} refused [{code}]", f"{note}; got={got}")

        print("\n" + "=" * 78)
        print("DECLARATION, not data -- the gate must fail CLOSED")
        print("=" * 78)
        for name, extra, code, note in DECLARATION_CASES:
            g = _run_r("check_admissibility.R", {
                "data_path": dp,
                "z_expr": f"POISON${name}$z",
                "time_expr": f"POISON${name}$time",
                "delta_expr": f"POISON${name}$delta",
            } | extra)
            got = [r["code"] for r in g.get("refusals", [])]
            check(g.get("status") == "ok" and not g.get("admissible")
                  and code in got, f"{code:<24} refused", note)

        print("\n" + "=" * 78)
        print(f"RESULT: {passed}/{passed + failed} passed")
        print("=" * 78)
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
