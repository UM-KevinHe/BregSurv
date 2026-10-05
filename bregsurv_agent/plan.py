"""V4: the analysis plan -- what is fitted, and the harness's check of it (work items 1 and 2).

The planner (a language-model act, V4 item 4) decides WHAT is fitted: the likelihood row, the members, each
member's eta grid, covariate set, the external terms it does not borrow, whether an absent term is padded
with zero. Cross-validation still chooses the final model among what was fitted. Everything here is the
harness: it enumerates what the facts admit, prices a plan, and refuses a plan it cannot accept, by name.
It decides nothing about the analysis itself.

A plan is a plain dict, the object run_candidates.R reads:
    {"row": "cox" | "cox_ties" | "discrete",
     "ties": "breslow",                           (cox_ties only; BregSurv >= 1.3.0)
     "intervals": {"width", "n_intervals", "time_is_index"},  (discrete only, when the analyst left the
                                                  time scale open: the planner sets the grid, the gate
                                                  then checks the amended declaration)
     "members": [{"key": ..., "etas": [...] | "grid": {"from", "to", "points"}, "covariates": [...],
                  "mask": [...], "pad_absent": bool, "nlambda": int, "reason": "..."}],
     "reason": "..."}
`reason` fields are the planner's, recorded and shown in the report; they change nothing that is fitted.

Decisions behind the rules (master memory 3e, 2026-10-02): the protected core is the two do-not-borrow
endpoints; the budget is a hard limit on COST-WEIGHTED fits (wall-clock time is only a safety stop), so a
plan is the same on a fast machine and a slow one; no new library function, so the tie-corrected row holds
the target-only and Kullback-Leibler fits only.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROWS = ("cox", "cox_ties", "discrete")
# Breslow only: since BregSurv 1.3.0 every Cox-family estimator takes ties = "breslow", so the tie-corrected
# row holds the whole standard set; the exact correction exists for two members only and is rarely
# computable on a real cohort
TIES = ("breslow",)
DEFAULT_BUDGET = int(os.environ.get("BREGSURV_FIT_BUDGET", "20") or 20)
MAX_GRID = 100           # the default grids have 41 or 81 points; a plan moves the range, not the density
NETWORK_KEYS = ("internal_nn", "diskd")


def log_grid(lo: float, hi: float, points: int) -> List[float]:
    """`points` values from `lo` to `hi`, evenly spaced on the log scale (six significant digits),
    the same rule as the default grids in run_candidates.R; eta = 0 is added there."""
    if points == 1:
        return [float(f"{lo:.6g}")]
    a, b = math.log(lo), math.log(hi)
    return [float(f"{math.exp(a + i * (b - a) / (points - 1)):.6g}") for i in range(points)]


def base_key(key: str) -> str:
    """A tie-corrected member's standard-row key: `mahalanobis_lasso_ties` -> `mahalanobis_lasso`."""
    return key[:-len("_ties")] if key.endswith("_ties") else key


def cost(key: str) -> int:
    """Cost units of one member: the released-model endpoints fit nothing (0); a network member trains
    a neural network under nested cross-validation (5); a ridge or lasso member runs a lambda path at
    every eta (2); any other member (1)."""
    if key in ("external", "external_discrete"):
        return 0
    if key in NETWORK_KEYS:
        return 5
    key = base_key(key)
    if key.endswith("_ridge") or key.endswith("_lasso"):
        return 2
    return 1


def plan_cost(plan: Dict[str, Any]) -> int:
    return sum(cost(str(m.get("key"))) for m in plan.get("members") or [])


def admissible_keys(row: str, design: str, external_form: str, has_baseline: bool) -> List[str]:
    """The members the facts admit on `row`, in the library's order. For `cox` and `discrete` this is
    pipeline.derive_candidate_keys; the tie-corrected row exists for a full cohort with a coefficient
    release or none, and holds the two tie variants the library has plus the released model, which that
    row records as unavailable (no tie-corrected fixed-coefficient loss)."""
    from .pipeline import derive_candidate_keys
    ncc = "nested" in design.lower() or "case-control" in design.lower()
    if row == "cox":
        return derive_candidate_keys(design, external_form, discrete=False)
    if row == "discrete":
        return derive_candidate_keys(design, external_form, discrete=True, has_baseline=has_baseline)
    if row == "cox_ties":
        # the standard set on Breslow's likelihood (BregSurv >= 1.3.0); the released model keeps its key
        if ncc:
            return []
        return [k if k == "external" else k + "_ties"
                for k in derive_candidate_keys(design, external_form, discrete=False)]
    return []


def protected_core(row: str, keys: Iterable[str]) -> List[str]:
    """The two ways of not borrowing that every plan keeps: the target-only fit of the row, and the
    released model unchanged where the row has one (absent for a matched design's coefficient form,
    which has no fixed-coefficient loss, and for a row without a release)."""
    keys = list(keys)
    target = {"cox": "internal", "cox_ties": "internal_ties", "discrete": "internal_discrete"}.get(row)
    released = "external_discrete" if row == "discrete" else "external"
    return [k for k in (target, released) if k and k in keys]


def identity_metric(key: str, external_form: str) -> bool:
    """Members whose borrowing metric is the identity: the Euclidean members, and the Mahalanobis members
    when no covariance was released (their metric is then the identity on the covered terms). Padding an
    absent term with zero means something only for these."""
    base = base_key(key).split("_")[0]
    if base == "euclidean":
        return True
    return base == "mahalanobis" and "covariance" not in external_form.lower()


MAX_INTERVALS = 200


def validate(plan: Dict[str, Any], *, design: str, external_form: str, has_baseline: bool,
             covariates: List[str], covered: List[str], budget: int = DEFAULT_BUDGET,
             intervals_open: bool = False, ties_allowed: Tuple[str, ...] = TIES,
             mask_evidence_text: Optional[str] = None
             ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]], int]:
    """Check a plan and return (the plan in canonical form, problems, cost). The plan is refused when any
    problem is listed; the canonical form fixes member order (the library's), sorts and dedupes grids,
    keeps covariates and masks in the declaration's order, and drops settings that do not apply.
    Every problem names the member and the rule, so the planner can be told exactly what to change."""
    problems: List[Dict[str, str]] = []

    def bad(code: str, msg: str) -> None:
        problems.append({"code": code, "message": msg})

    row = str(plan.get("row") or "cox")
    if row not in ROWS:
        bad("row_unknown", f"row {row!r} is not one of {', '.join(ROWS)}")
        return None, problems, 0
    keys = admissible_keys(row, design, external_form, has_baseline)
    if not keys:
        bad("row_not_admissible", f"the {row} row does not exist for a {design} with {external_form}")
        return None, problems, 0
    out: Dict[str, Any] = {"row": row}
    if row == "cox_ties":
        t = str(plan.get("ties") or "breslow")
        if t not in TIES:
            bad("ties_unknown", f"ties {t!r} is not one of {', '.join(TIES)}")
        elif t not in ties_allowed:
            bad("exact_ties_infeasible", "the exact tie correction cannot be computed on this cohort: at "
                "some event time the tied events and their risk set give more arrangements than the "
                "library enumerates; use breslow")
        out["ties"] = t
    if plan.get("reason"):
        out["reason"] = str(plan["reason"])[:2000]
    # V4 item 4b: the discrete row's grid, when the analyst left the time scale open. The values are
    # checked for form here; the gate checks them against the data on the amended declaration.
    iv = plan.get("intervals")
    if iv is not None and row != "discrete":
        bad("intervals_not_applicable", "intervals belong to the discrete row only")
    elif row == "discrete" and intervals_open:
        if not iv:
            bad("intervals_missing", "the discrete row needs the intervals: a width in the time column's "
                                     "unit and their number, or the time column as an interval index")
        else:
            try:
                k = int(iv.get("n_intervals"))
            except (TypeError, ValueError):
                k = 0
            idx = bool(iv.get("time_is_index"))
            w = iv.get("width")
            try:
                w = None if idx else float(w)
            except (TypeError, ValueError):
                w = float("nan")
            if not 2 <= k <= MAX_INTERVALS:
                bad("intervals_invalid", f"the number of intervals must be between 2 and {MAX_INTERVALS}")
            elif not idx and not (w is not None and math.isfinite(w) and w > 0):
                bad("intervals_invalid", "the interval width must be a positive number in the time "
                                         "column's unit (or set time_is_index)")
            else:
                out["intervals"] = {"width": w, "n_intervals": k, "time_is_index": idx}
    elif iv:
        bad("intervals_declared", "the time scale was settled by the analyst; the intervals are not "
                                  "the plan's to set")

    seen: Dict[str, Dict[str, Any]] = {}
    for m in plan.get("members") or []:
        k = str(m.get("key") or "")
        if k not in keys:
            bad("member_not_admissible", f"{k!r} is not a member of the {row} row here (admissible: {', '.join(keys)})")
            continue
        if k in seen:
            bad("member_twice", f"{k!r} is listed twice")
            continue
        mm: Dict[str, Any] = {"key": k}
        internal = k.startswith("internal")
        fits_eta = not internal and k not in ("external", "external_discrete")
        etas_in = m.get("etas")
        if m.get("grid") is not None:
            # a grid given by its range: expanded here, kept beside the values it produced
            gs = m["grid"]
            try:
                lo, hi, npts = float(gs["from"]), float(gs["to"]), int(gs["points"])
            except (TypeError, ValueError, KeyError):
                lo = hi = float("nan"); npts = 0
            if not fits_eta:
                bad("grid_not_applicable", f"{k!r} has no borrowing weight to tune; it takes no eta grid")
                etas_in = None
            elif not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo < hi and 2 <= npts <= MAX_GRID):
                bad("grid_invalid", f"{k!r}: a grid range needs 0 < from < to and between 2 and "
                                    f"{MAX_GRID} points")
                etas_in = None
            elif etas_in is not None and sorted(float(x) for x in etas_in) != log_grid(lo, hi, npts):
                # the canonical form carries both, and they agree; anything else is two grids
                bad("grid_twice", f"{k!r}: give the grid either as values or as a range, not both")
                etas_in = None
            else:
                etas_in = log_grid(lo, hi, npts)
                mm["grid"] = {"from": lo, "to": hi, "points": npts}
        if etas_in is not None:
            if not fits_eta:
                bad("grid_not_applicable", f"{k!r} has no borrowing weight to tune; it takes no eta grid")
            else:
                try:
                    g = sorted({float(x) for x in etas_in})
                except (TypeError, ValueError):
                    g = []
                if not g or any((not math.isfinite(x)) or x < 0 for x in g):
                    bad("grid_invalid", f"{k!r}: the eta grid must be non-negative numbers")
                elif len(g) > MAX_GRID:
                    bad("grid_too_long", f"{k!r}: at most {MAX_GRID} eta values")
                else:
                    mm["etas"] = g
        if m.get("covariates") is not None and k not in ("external", "external_discrete"):
            want = [str(c) for c in m["covariates"]]
            extra = [c for c in want if c not in covariates]
            if extra:
                bad("covariate_not_declared", f"{k!r}: {', '.join(extra)} is not a declared covariate")
            kept = [c for c in covariates if c in want]
            if not kept:
                bad("no_covariate", f"{k!r} keeps no covariate")
            elif kept != covariates:
                mm["covariates"] = kept
        if m.get("mask"):
            if not fits_eta or k in NETWORK_KEYS or row == "discrete":
                bad("mask_not_applicable", f"{k!r} does not borrow term by term, so it takes no mask")
            else:
                want = [str(c) for c in m["mask"]]
                extra = [c for c in want if c not in covered]
                if extra:
                    bad("mask_not_covered", f"{k!r}: {', '.join(extra)} is not a term the release covers")
                kept = [c for c in covered if c in want]
                if kept and len(kept) == len(covered):
                    bad("mask_everything", f"{k!r}: the mask leaves nothing to borrow")
                if kept:
                    mm["mask"] = kept
                    # a term is left out of the borrowing (any family) only on evidence
                    # from OUTSIDE the data -- the analyst saying the variable is defined, measured or coded
                    # differently from the release -- never on a statistical disagreement in this cohort.
                    # The evidence is the analyst's own words, copied verbatim, and must name every masked term.
                    from .textmatch import mentions, phrase_in
                    ev = str(m.get("mask_evidence") or "").strip()
                    if not ev or not mask_evidence_text or not phrase_in(mask_evidence_text, ev):
                        bad("mask_without_evidence",
                            f"{k!r}: a term is left out of the borrowing only when the analyst says the variable "
                            "differs from the release (defined, measured or coded differently); copy those words "
                            "into mask_evidence, or drop the mask")
                    else:
                        unnamed = [c for c in kept if not mentions(ev, c, covered)]
                        if unnamed:
                            bad("mask_evidence_does_not_name",
                                f"{k!r}: the evidence does not name {', '.join(unnamed)}")
                        else:
                            mm["mask_evidence"] = ev
        if m.get("pad_absent"):
            if not identity_metric(k, external_form):
                bad("pad_not_applicable",
                    f"{k!r}: zero-padding an absent term applies to an identity-metric member only")
            else:
                mm["pad_absent"] = True
        if m.get("nlambda") is not None and (base_key(k).endswith("_ridge") or base_key(k).endswith("_lasso")):
            try:
                nl = int(m["nlambda"])
            except (TypeError, ValueError):
                nl = -1
            if not 10 <= nl <= 200:
                bad("nlambda_invalid", f"{k!r}: nlambda must be between 10 and 200")
            else:
                mm["nlambda"] = nl
        if m.get("reason"):
            mm["reason"] = str(m["reason"])[:1000]
        seen[k] = mm

    for k in protected_core(row, keys):
        if k not in seen:
            bad("protected_member_missing",
                f"{k!r} must be in every plan on this row: it is one of the two ways of not borrowing")
    members = [seen[k] for k in keys if k in seen]
    out["members"] = members
    c = plan_cost(out)
    if c > budget:
        bad("over_budget", f"the plan costs {c} units and the budget is {budget} "
                           f"(units: endpoints 0, plain members 1, ridge or lasso 2, networks 5)")
    return (out if not problems else None), problems, c


def default_plan(row: str, design: str, external_form: str, has_baseline: bool) -> Dict[str, Any]:
    """Every admissible member on its default grid: what V3 fits. Used for the ablation "the planner's
    decisions replaced by fixed defaults" and when no planner is configured."""
    return {"row": row, "members": [{"key": k} for k in admissible_keys(row, design, external_form, has_baseline)],
            "reason": "fixed default: every admissible member on its default grid"}
