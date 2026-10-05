"""What the admissibility gate is worth, measured by removing it.

`test_admissibility_e2e.py` proves the gate refuses the right things. That is
only half the question, and the less interesting half: a gate that refuses
everything would also pass it. The question a reader actually has is **what
happens if you take the gate away**, and it is answered here by fitting each
poisoned dataset directly, with no gate in the path, and recording what comes
back.

THE ANSWER IS NOT "IT CRASHES". Most of these datasets produce a coefficient
vector. Several produce one that sits within a hair of the coefficients the
CLEAN data gives, so there is nothing in the output -- no warning, no NA, no
implausible magnitude -- to tell an analyst that the follow-up times were
negative, or missing, or infinite, or stored as text. That is the failure this
whole apparatus exists to prevent, and it is silent by nature: an analysis that
crashes gets fixed, an analysis that quietly answers the wrong question gets
published.

The three outcomes are counted separately because they are not equally bad:

  RETURNS A NUMBER   the worst. Nothing indicates a problem.
  ACTIONABLE ERROR   loud, and the message names what to fix.
  OPAQUE ERROR       loud, but "Hessian solve failed." tells an analyst
                     nothing they can act on, and sends them looking at the
                     model rather than at the data.

No language model is involved anywhere in this file.

Run:  python test_gate_ablation.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from test_admissibility_e2e import COHORT_CASES, build_fixtures  # noqa: E402

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m", "\033[2m",
                             "\033[0m")
passed = failed = 0

_OPAQUE = ("Hessian solve failed", "solution not found", "singular")


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")
    return ok


def _fit(dp: str, name: str) -> Tuple[str, Optional[List[float]], str]:
    """Fit with NO gate in the path. Returns (outcome, coefficients, message)."""
    res = _run_r("fit_coxkl.R", {
        "data_path": dp,
        "z_expr": f"POISON${name}$z",
        "time_expr": f"POISON${name}$time",
        "delta_expr": f"POISON${name}$delta",
        "beta_expr": "bex", "etas": [5.0]})
    if res.get("status") != "ok":
        msg = str(res.get("message", ""))[:90]
        kind = "opaque error" if any(o in msg for o in _OPAQUE) else "actionable error"
        return kind, None, msg
    try:
        beta = [float(row[0]) for row in res["beta"]]
    except Exception:
        return "returns something", None, ""
    if not beta or any(b != b for b in beta):          # NaN
        return "all-NA coefficients", None, ""
    return "RETURNS A NUMBER", beta, ""


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        fx = Path(td) / "PoisonFixtures.rda"
        build_fixtures(fx)
        dp = str(fx)

        print("\n" + "=" * 78)
        print("THE GATE REMOVED: what each refused dataset returns instead")
        print("=" * 78)

        _, clean, _ = _fit(dp, "clean")
        if clean is None:
            print("could not fit the clean control; nothing to compare against")
            return 1
        print(f"{DIM}  clean control fits to "
              f"{' '.join(f'{b:+.4f}' for b in clean[:3])} ...{OFF}\n")

        refused = [(n, c, note) for n, c, note in COHORT_CASES if c]
        rows: List[Dict[str, Any]] = []
        for name, code, note in refused:
            kind, beta, msg = _fit(dp, name)
            drift = (max(abs(a - b) for a, b in zip(beta, clean))
                     if beta else None)
            rows.append({"name": name, "code": code, "note": note,
                         "kind": kind, "beta": beta, "drift": drift,
                         "msg": msg})
            tag = (f"{RED}{kind}{OFF}" if kind == "RETURNS A NUMBER"
                   else f"{YEL}{kind}{OFF}")
            extra = (f"max |coef - clean| = {drift:.4f}" if drift is not None
                     else msg)
            print(f"  {name:<16} [{code:<26}] {tag:<34} {DIM}{extra}{OFF}")

        # ---- the headline ------------------------------------------------
        numbers = [r for r in rows if r["kind"] == "RETURNS A NUMBER"]
        opaque = [r for r in rows if r["kind"] == "opaque error"]
        actionable = [r for r in rows if r["kind"] == "actionable error"]
        indistinguishable = [r for r in numbers
                             if r["drift"] is not None and r["drift"] < 0.05]

        print("\n" + "=" * 78)
        print("WHAT THE GATE IS WORTH")
        print("=" * 78)
        print(f"  of {len(rows)} datasets the gate refuses, without it:")
        print(f"    {len(numbers):>2}  return a coefficient vector and no warning")
        print(f"    {len(actionable):>2}  fail with a message naming what to fix")
        print(f"    {len(opaque):>2}  fail with a message an analyst cannot act on")
        print(f"\n  of the {len(numbers)} that return numbers, {len(indistinguishable)} "
              f"land within 0.05 of the clean fit:")
        for r in indistinguishable:
            print(f"    {r['name']:<16} {r['note']}")
        print(f"\n  {DIM}Nothing in those outputs indicates a problem. No warning,")
        print(f"  no NA, no implausible magnitude -- the numbers look like an")
        print(f"  ordinary analysis of data that is not ordinary.{OFF}")

        # ---- assertions --------------------------------------------------
        print("\n" + "=" * 78)
        print("assertions")
        print("=" * 78)
        check(len(numbers) > 0,
              "removing the gate lets poisoned data through as numbers",
              f"{len(numbers)} of {len(rows)} -- if this were 0 the gate would "
              f"be redundant and should be deleted")
        check(len(indistinguishable) > 0,
              "and some of those numbers are indistinguishable from a good fit",
              f"{len(indistinguishable)} within 0.05 of the clean coefficients")
        check(len(opaque) > 0,
              "the loud failures are not all actionable either",
              f"{len(opaque)} say only things like 'Hessian solve failed.'")

        # The two that should worry a reader most: a time column that is
        # negative and one that is text both fit, and fit to nearly the same
        # place. Pinned so a future change cannot quietly make this test vacuous.
        by_name = {r["name"]: r for r in rows}
        for nm in ("time_negative", "time_character"):
            r = by_name.get(nm)
            check(r is not None and r["kind"] == "RETURNS A NUMBER",
                  f"{nm}: fits and returns coefficients with the gate removed",
                  (f"max |coef - clean| = {r['drift']:.4f}"
                   if r and r["drift"] is not None else "did not fit"))

    print("\n" + "=" * 78)
    print(f"RESULT: {passed}/{passed + failed} passed")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
