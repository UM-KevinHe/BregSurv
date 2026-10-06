"""V4 work item 4 -- the analyst loop: the language model plans what is fitted, the harness bounds it.

The loop, for one verified declaration:

  observe   the harness renders the task: the declaration's facts, the transfer-diagnostics card
            (`diagnose_transfer.R`, training data only), what each row admits with its cost and
            default grid, the budget, the analyst's own words, and the playbook notes whose
            situation the facts trigger (`knowledge/tl_playbook.md`)
  plan      `analysis_plan`, one constrained call with thinking on: the row, the members, each
            member's grid range, covariate subset, mask and padding, each with a reason
  verify    `plan.validate` -- admissibility, the protected core, the budget. A refused plan goes
            back to the planner WITH the harness's problems, by name (the verifier is the
            feedback); after `MAX_TRIES` refusals the fixed default plan is fitted and the
            fallback is recorded
  fit       `pipeline.fit_plan` on the one partition, no report, no test file
  observe   the fitted table: every member's cross-validated loss, selected weight and where it
            sits on its grid, the budget left
  next      `next_step`, one constrained call with thinking on: finish, or refine -- add members or
            refit members with new settings. Verified the same way; a refinement is priced by the
            members it changes, and the members it does not change are reused, not refitted
  ...       at most `MAX_REFINEMENTS` refinements, then the loop ends whatever the planner says

The final result is `pipeline.run` on the final plan with every fitted row reused: one candidate
table, one partition, one argmin by cross-validation, the report, and a repro.R that refits the
final plan with no model. The planner never sees a held-out number on the analyst's test file (the
intermediate fits do not read it), never chooses the final model, never writes a number into the
report, and every decision it makes is recorded with its reason and what it cost.

What stays fixed whatever the planner says: the declaration (roles, design, release), the partition,
the cross-validation criterion, the two do-not-borrow endpoints, and the budget.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import ablation
from . import plan as P

MAX_REFINEMENTS = int(os.environ.get("BREGSURV_MAX_REFINEMENTS", "2") or 0)
MAX_TRIES = 3                 # per decision: the first proposal, then two with the harness's problems
PLAN_MAX_TOKENS = 1800        # the visible JSON; a thinking call gets its own allowance on top
STEP_MAX_TOKENS = 1400
MAX_CALLS = MAX_TRIES * (1 + MAX_REFINEMENTS)   # the loop can never make more model calls than this

PLAYBOOK_PATH = Path(__file__).resolve().parent / "knowledge" / "tl_playbook.md"

# the default grids of run_candidates.R (`log_eta`): (from, to, points), log spaced; eta = 0 is
# always added there. Mirrored here only to describe them to the planner; test_v4_loop checks the
# two agree.
DEFAULT_GRIDS: Dict[str, Tuple[float, float, int]] = {
    "kl": (0.01, 200.0, 81), "kl_ridge": (0.01, 200.0, 41), "kl_lasso": (0.01, 200.0, 41),
    "mahalanobis": (0.01, 1e6, 81), "euclidean": (0.01, 1e6, 81),
    "mahalanobis_ridge": (0.01, 1e6, 41), "euclidean_ridge": (0.01, 1e6, 41),
    "mahalanobis_lasso": (0.01, 1e3, 41), "euclidean_lasso": (0.01, 1e3, 41),
    "indi": (0.01, 200.0, 81), "indi_lasso": (0.01, 200.0, 41),
}
DISCRETE_GRID = "0, 1, 5, 10, 20, 50, 100 (fixed values)"


def member_label(key: str, has_Q: bool) -> str:
    """What a member is, in a line, for the planner."""
    if key.endswith("_ties"):     # the tie-corrected row: the standard member on Breslow's likelihood
        return member_label(P.base_key(key), has_Q) + ", Breslow ties"
    pen = (", ridge path" if key.endswith("_ridge") else ", lasso path" if key.endswith("_lasso")
           else "")
    base = key.split("_")[0]
    if key == "external":
        return "the released model unchanged (nothing is fitted; protected)"
    if key == "external_discrete":
        return "the released model's interval hazards unchanged (nothing is fitted; protected)"
    if key in ("internal", "internal_discrete"):
        return "target only, no penalty (protected)"
    if key.startswith("internal_") and key not in ("internal_nn",):
        return "target only" + pen
    if key == "internal_nn":
        return "target only, a neural network on the intervals"
    if key == "diskd":
        return "a neural network distilled toward the released interval hazards"
    if key == "discretekl":
        return "Kullback-Leibler borrowing on the interval likelihood"
    if base == "kl":
        return "Kullback-Leibler borrowing (pulls the fit's risk scores toward the release's)" + pen
    if base == "euclidean":
        return "coefficient-space borrowing, identity metric on the covered terms" + pen
    if base == "mahalanobis":
        return ("coefficient-space borrowing, the released precision as metric" if has_Q
                else "coefficient-space borrowing, identity metric on the covered terms") + pen
    if base == "indi":
        return "borrowing the other cohort's records (composite likelihood)" + pen
    return key


# ------------------------------------------------------------------------------------- the options
@dataclass
class Options:
    """What the planner may choose from, all of it fixed by the verified declaration."""
    design: str
    external_form: str
    has_baseline: bool
    has_Q: bool
    covariates: List[str]
    covered: List[str]
    rows: Dict[str, List[str]]          # row -> admissible keys, in the library's order
    budget: int
    intervals_open: bool = False        # 4b: the planner may choose the discrete row and set its grid
    ties_allowed: Tuple[str, ...] = P.TIES   # set from the card: `exact` only where it can be computed

    @property
    def all_keys(self) -> List[str]:
        out: List[str] = []
        for ks in self.rows.values():
            out += [k for k in ks if k not in out]
        return out


def options_for(declaration: Any, ext_kw: Dict[str, Any], budget: int = P.DEFAULT_BUDGET) -> Options:
    from .pipeline import resolve_config
    # records are fitted into a coefficient vector with its covariance (run_candidates.R), so the
    # Mahalanobis members there use a precision matrix as their metric
    has_Q = bool(ext_kw.get("external_Q_inline") or ext_kw.get("external_Q_expr")
                 or declaration.external_data_expr)
    design = declaration.design
    form = ("individual-level data" if declaration.external_data_expr
            else "none" if not (ext_kw.get("external_beta_inline") or ext_kw.get("external_beta_expr"))
            else "coefficients and covariance" if has_Q else "coefficients alone")
    base = ext_kw.get("external_baseline_inline") or {}
    has_baseline = bool(base.get("time"))
    covs = list(declaration.covariates or [])
    covered = [c for c in (ext_kw.get("external_beta_inline") or {}) if c in covs]
    open_ = False
    if declaration.discrete:
        # the analyst declared discrete intervals: their statement settles the row
        rows = {"discrete": P.admissible_keys("discrete", design, form, has_baseline)}
    else:
        rows = {}
        for r in ("cox", "cox_ties"):
            ks = P.admissible_keys(r, design, form, has_baseline)
            if ks:
                rows[r] = ks
        # 4b (ruling 2026-10-02: the time scale is judged from the data): the discrete row is offered
        # unless the analyst settled the time scale (a reply, a quote, a remembered answer -- not the
        # harness's continuous default), the design is matched, or a test file was given (the
        # discrete row has no held-out scorer)
        # -- and only where it is an analysis of the release or there is no release: without a baseline
        # hazard a grouped-time model borrows nothing, so choosing it would be choosing not to borrow
        src = str((getattr(declaration, "sources", None) or {}).get("discrete", "") or "")
        settled = bool(src) and not src.startswith("default:")
        matched = "nested" in design or "case-control" in design
        if (declaration.time_col and not matched and not settled
                and not getattr(declaration, "has_test_data", False)
                and (has_baseline or form == "none")):
            ks = P.admissible_keys("discrete", design, form, has_baseline)
            if ks:
                rows["discrete"] = ks
                open_ = True
    return Options(design=design, external_form=form, has_baseline=has_baseline, has_Q=has_Q,
                   covariates=covs, covered=covered, rows=rows, budget=budget, intervals_open=open_)


def amend_declaration(declaration: Any, plan: Dict[str, Any]) -> Any:
    """The declaration the plan's row runs on: unchanged unless the planner chose the discrete row and set
    its intervals, in which case a copy carries them, with the source naming the planner. The gate
    checks the copy before anything is fitted on it."""
    iv = plan.get("intervals") if plan else None
    if not iv or plan.get("row") != "discrete":
        return declaration
    import copy
    d = copy.deepcopy(declaration)
    d.n_intervals = int(iv["n_intervals"])
    d.time_is_interval_index = bool(iv.get("time_is_index"))
    d.interval_width = None if d.time_is_interval_index else float(iv["width"])
    d.sources = dict(d.sources or {})
    d.sources["discrete"] = ("planned: " + " ".join(str(plan.get("reason") or "the planner chose "
                                                         "discrete intervals").split()))[:300]
    return d


# ----------------------------------------------------------------------------------- situations
def _lost_on_ties(opts: Options) -> str:
    """What choosing the tie-corrected row gives up: since BregSurv 1.3.0, nothing -- every member of the
    standard row has its Breslow version, and the released model is scored on Breslow's likelihood too."""
    return "the same members as the standard row, every one fitted and scored on Breslow's likelihood"


def ties_allowed(card: Dict[str, Any]) -> Tuple[str, ...]:
    """Breslow only (plan.TIES): the exact correction is no longer offered."""
    return P.TIES


def situations(card: Dict[str, Any], opts: Options, rows: Optional[List[Dict[str, Any]]] = None
               ) -> List[str]:
    """Which playbook notes apply, computed from the facts. Deterministic; no model."""
    f = card.get("facts") or {}
    out = card.get("outcome") or {}
    ext = card.get("external") or {}
    s = ["always"]
    epp = f.get("events_per_parameter")
    if isinstance(epp, (int, float)):
        if epp < 2:
            s.append("few_events")
        elif epp >= 20:
            s.append("many_events")
    cal = ext.get("calibration") or {}
    slope = cal.get("slope")
    lr, lt = ext.get("cv_loss_released_unchanged"), ext.get("cv_loss_target_only_ridge")
    worse = isinstance(lr, (int, float)) and isinstance(lt, (int, float)) and lr > lt
    if (isinstance(slope, (int, float)) and slope < 0.5) or worse:
        s.append("weak_release")
    elif isinstance(slope, (int, float)) and 0.7 <= slope <= 1.3 and not worse \
            and isinstance(lr, (int, float)):
        s.append("strong_release")
    het = ext.get("heterogeneity") or {}
    terms = [t for t in (card.get("terms") or []) if isinstance(t.get("difference_per_sd"), (int, float))]
    if len(terms) >= 4:
        # a few terms disagree strongly AND the rest agree (a fact for the planner; it is NOT evidence for a
        # mask, which needs the analyst's words -- plan.validate)
        big = [t for t in terms if abs(t["difference_per_sd"]) >= 0.5]
        rest = sorted(abs(t["difference_per_sd"]) for t in terms if abs(t["difference_per_sd"]) < 0.5)
        rest_med = rest[len(rest) // 2] if rest else 1.0
        if 0 < len(big) <= max(1, len(terms) // 4) and rest_med < 0.15:
            s.append("concentrated_heterogeneity")
    if (ext.get("n_internal_only") or 0) > 0 and opts.external_form == "coefficients alone":
        s.append("absent_terms")
    if opts.has_Q:
        s.append("covariance_released")
    tf = out.get("tie_fraction")
    if isinstance(tf, (int, float)) and "cox_ties" in opts.rows:
        s.append("tied_times" if tf >= 0.1 else "few_ties")
    tg = out.get("time_grid") or {}
    if tg.get("coarse") and not opts.rows.get("discrete"):
        s.append("coarse_time")
    if "individual" in opts.external_form:
        s.append("records")
    if "nested" in opts.design or "case-control" in opts.design:
        s.append("matched")
    if rows and any(r.get("eta_at_grid_max") or _at_low_end(r) for r in rows
                    if r.get("status") == "ok"):
        s.append("grid_edge")
    return s


def _at_low_end(r: Dict[str, Any]) -> bool:
    k = str(r.get("key") or "")
    if k.startswith("internal") or k.startswith("external") or r.get("eta") in (None, ""):
        return False
    try:
        return float(r["eta"]) == 0.0
    except (TypeError, ValueError):
        return False


def playbook(names: List[str]) -> List[Tuple[str, str]]:
    """The playbook notes whose `when:` trigger is in `names`, in file order: (id, body)."""
    text = PLAYBOOK_PATH.read_text(encoding="utf-8")
    out = []
    for block in text.split("\n## ")[1:]:
        lines = block.strip().split("\n")
        nid = lines[0].strip()
        when = next((ln[len("when:"):].strip() for ln in lines[1:] if ln.startswith("when:")), "")
        body = " ".join(ln.strip() for ln in lines[1:] if not ln.startswith("when:")).strip()
        if when in names:
            out.append((nid, body))
    return out


# ----------------------------------------------------------------------------- the observations
def _num(x: Any, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return str(x)
    try:
        return f"{float(x):.{digits}g}"
    except (TypeError, ValueError):
        return str(x)


def _grid_text(key: str, entry: Optional[Dict[str, Any]] = None) -> str:
    if entry and entry.get("grid"):
        g = entry["grid"]
        return f"{g['points']} points, {_num(g['from'])} to {_num(g['to'])} (your range)"
    if entry and entry.get("etas"):
        e = entry["etas"]
        return f"{len(e)} values, {_num(min(e))} to {_num(max(e))} (your values)"
    if key == "discretekl":
        return DISCRETE_GRID
    if P.base_key(key) in DEFAULT_GRIDS:
        lo, hi, n = DEFAULT_GRIDS[P.base_key(key)]
        return f"{n} points, {_num(lo)} to {_num(hi)} (default)"
    return "none (no borrowing weight)"


def _absent_evidence(ext: Dict[str, Any], words: str) -> List[str]:
    """What bears on padding the uncovered covariates with zero, gathered for the planner to weigh. Padding asserts the release estimated those effects as zero,
    which holds when its authors considered the variables and left them out, not when they never had them."""
    from .textmatch import mentions
    import re
    names = list(ext.get("internal_only") or [])
    if not names:
        return []
    est = {a.get("term"): a for a in ext.get("absent") or []}
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", words or "") if x.strip()]
    out = ["  evidence on the uncovered covariates, for deciding whether to pad them with zero "
           "(padding states the release estimated their effects as zero):",
           "    the release file lists none of them, with or without a coefficient"]
    for v in names:
        a = est.get(v) or {}
        bit = (f"target-only estimate {_num(a.get('beta_target_only'), 3)} "
               f"({_num(a.get('effect_per_sd'), 3)} per standard deviation)" if a else "no target-only estimate")
        said = [x for x in sentences if mentions(x, v, names)]
        bit += ("; the analyst wrote: \"" + said[0][:200] + "\"") if said else "; the analyst says nothing about it"
        out.append(f"    {v}: {bit}")
    return out


def render_task(declaration: Any, card: Dict[str, Any], opts: Options, words: str) -> str:
    """Everything the planner sees about the task, as text. Digits are allowed here: the planner
    reads numbers and writes settings, and nothing it writes reaches the report as a number."""
    f = card.get("facts") or {}
    out = card.get("outcome") or {}
    ext = card.get("external") or {}
    L: List[str] = ["THE ANALYSIS (verified; you do not change it)"]
    if declaration.time_col:
        L.append(f"design: {opts.design}; follow-up time '{declaration.time_col}'; event "
                 f"'{declaration.event_col}' = {declaration.event_value}"
                 + (f"; strata '{declaration.stratum_col}'" if declaration.stratum_col else ""))
    else:
        L.append(f"design: {opts.design}; matched sets '{declaration.stratum_col}'; case indicator "
                 f"'{declaration.event_col}' = {declaration.event_value}")
    if declaration.discrete:
        L.append("time scale: discrete intervals, declared by the analyst")
    L.append(f"cohort: {f.get('n')} subjects, {f.get('n_events')} events, {f.get('p')} covariates "
             f"({_num(f.get('events_per_parameter'), 3)} events per covariate)")
    L.append("covariates: " + ", ".join(opts.covariates))
    if opts.external_form == "none":
        L.append("external information: none")
    else:
        L.append(f"external information: {opts.external_form}; covers {ext.get('n_covered')} of "
                 f"{f.get('p')} covariates")
        if ext.get("internal_only"):
            L.append("  covariates the release does not cover: " + ", ".join(ext["internal_only"]))
            L.extend(_absent_evidence(ext, words))
        if ext.get("released_not_in_cohort"):
            L.append("  released terms with no column here (dropped): "
                     + ", ".join(ext["released_not_in_cohort"]))
    L.append("")
    if ablation.on("no_diagnostics"):
        card = {"outcome": {}, "external": {}, "terms": [], "records": {}, "baseline": {}, "notes": []}
        out, ext = {}, {}
    else:
        L.append("TRANSFER DIAGNOSTICS (training data only)")
    cal = ext.get("calibration") or {}
    if cal:
        L.append(f"the release's risk score on this cohort: calibration slope {_num(cal.get('slope'), 3)} "
                 f"(standard error {_num(cal.get('slope_se'), 2)}), concordance "
                 f"{_num(cal.get('cindex_on_internal'), 3)}")
    if ext.get("cv_loss_released_unchanged") is not None:
        L.append(f"cross-validated loss (lower is better): released model unchanged "
                 f"{_num(ext.get('cv_loss_released_unchanged'), 6)}; target-only ridge fit "
                 f"{_num(ext.get('cv_loss_target_only_ridge'), 6)}")
    het = ext.get("heterogeneity") or {}
    if het:
        L.append(f"target-only ridge minus release, per standard deviation of the covariate: median "
                 f"absolute difference {_num(het.get('median_abs_difference_per_sd'), 3)}; signs "
                 f"disagree on {het.get('n_sign_disagreements')} of {ext.get('n_covered')} terms")
    terms = card.get("terms") or []
    if terms:
        L.append("per term: term | release | target-only ridge | difference per SD | same sign")
        for t in terms:
            L.append(f"  {t.get('term')} | {_num(t.get('beta_release'))} | "
                     f"{_num(t.get('beta_target_only'))} | {_num(t.get('difference_per_sd'), 3)} | "
                     f"{'yes' if t.get('same_sign') else 'no'}")
    mx = ext.get("matrix") or {}
    if mx.get("condition_number") is not None:
        L.append(f"released covariance: condition number {_num(mx.get('condition_number'), 3)}")
    rec = card.get("records") or {}
    if rec.get("n_external"):
        L.append(f"external records: {rec.get('n_external')} subjects, {rec.get('n_events_external')} "
                 f"events; largest standardised mean difference "
                 f"{_num(rec.get('max_abs_standardised_mean_difference'), 3)}")
    if out.get("tie_fraction") is not None:
        L.append(f"tied event times: {_num(out.get('tie_fraction'), 3)} of events share a time with "
                 f"another ({out.get('n_distinct_event_times')} distinct event times)")
    tg = out.get("time_grid") or {}
    if tg:
        L.append(f"follow-up time: {tg.get('n_distinct')} distinct values"
                 + (f", on a step of {_num(tg.get('step'))}" if tg.get("integer_valued") else "")
                 + (f", from {_num(tg.get('min'))} to {_num(tg.get('max'))}" if tg.get("max") is not None else "")
                 + ("; coarse, as grouped follow-up is" if tg.get("coarse") else ""))
    bl = card.get("baseline") or {}
    if bl.get("available"):
        L.append(f"the release carries a baseline hazard up to time {_num(bl.get('last_time'))}"
                 + ("" if bl.get("covers_internal_follow_up") else
                    ", which does not cover all of this cohort's follow-up"))
    if out.get("n_sets"):
        L.append(f"matched sets: {out.get('n_sets')}, median size {out.get('median_set_size')}")
    for n in card.get("notes") or []:
        L.append(f"note: {n}")
    L.append("")
    L.append("WHAT CAN BE FITTED (cost in units; the default grid is used unless you give a range)")
    for row, keys in opts.rows.items():
        L.append(f"row '{row}':" + {
            "cox": " the standard partial likelihood",
            "cox_ties": (" Breslow's tie-corrected partial likelihood (set `ties` to breslow): "
                         + _lost_on_ties(opts)),
            "discrete": (" the grouped-time likelihood on intervals YOU set (`intervals`: a width in the "
                         "time column's unit and the number K of intervals, or time_is_index when the "
                         "column already holds 1..K); follow-up beyond K intervals is censored at K; its "
                         "losses are never compared with the other rows'" if opts.intervals_open
                         else " the grouped-time likelihood on the declared intervals")}.get(row, ""))
        for k in keys:
            L.append(f"  {k}: {member_label(k, opts.has_Q)}; cost {P.cost(k)}; grid {_grid_text(k)}")
    L.append(f"budget: {opts.budget} units for the whole analysis, every fit counted, a refit of a "
             f"member counted again. Always in the plan: "
             + ", ".join(P.protected_core(next(iter(opts.rows)), next(iter(opts.rows.values())))) + ".")
    L.append("")
    L.append("THE ANALYST'S WORDS")
    L.append(words.strip()[-3000:] if words and words.strip() else "(the analyst said nothing about the method)")
    return "\n".join(L)


def render_notes(names: List[str]) -> str:
    if ablation.on("no_playbook"):
        return ""
    notes = playbook(names)
    if not notes:
        return ""
    return "NOTES FROM THE PLAYBOOK\n" + "\n".join(f"- [{nid}] {body}" for nid, body in notes)


def render_problems(problems: List[Dict[str, str]]) -> str:
    if not problems:
        return ""
    return ("YOUR LAST PROPOSAL WAS REFUSED BY THE HARNESS, for these reasons; propose again:\n"
            + "\n".join(f"- {p['code']}: {p['message']}" for p in problems))


def render_results(cur: Dict[str, Any], rows: List[Dict[str, Any]], spent: int, budget: int,
                   step: int, history: List[str]) -> str:
    """The fitted table as the planner sees it: no held-out number, no coefficient."""
    entries = {m["key"]: m for m in cur.get("members") or []}
    L = [f"THE PLAN SO FAR (row '{cur.get('row', 'cox')}'"
         + (f", {cur.get('ties')} ties" if cur.get("ties") else "") + ")"]
    for k, m in entries.items():
        bits = [f"grid {_grid_text(k, m)}"] if (not k.startswith("internal")
                                                and not k.startswith("external")) else []
        if m.get("covariates"):
            bits.append(f"{len(m['covariates'])} of the covariates")
        if m.get("mask"):
            bits.append("does not borrow " + ", ".join(m["mask"]))
        if m.get("pad_absent"):
            bits.append("absent terms padded with zero")
        L.append(f"  {k}" + (": " + "; ".join(bits) if bits else ""))
    for h in history:
        L.append(f"earlier decision: {h}")
    L.append("")
    L.append("RESULTS (cross-validated loss on one shared partition; lower is better)")
    L.append("member | status | loss | selected weight eta | where on its grid | lambda | non-zero")
    best = None
    for r in rows:
        k = r.get("key")
        if r.get("status") != "ok":
            L.append(f"  {k} | {r.get('status')} | - | - | - | - | - "
                     + (f"({str(r.get('message') or '')[:120]})" if r.get("message") else ""))
            continue
        where = "-"
        if not str(k).startswith(("internal", "external")) and r.get("eta") is not None:
            if r.get("eta_at_grid_max"):
                where = "TOP of its grid"
            elif _at_low_end(r):
                where = "zero: no borrowing chosen"
            else:
                where = "inside"
        L.append(f"  {k} | ok | {_num(r.get('loss'), 7)} | {_num(r.get('eta'))} | {where} | "
                 f"{_num(r.get('lambda'))} | {r.get('n_nonzero')}")
        if isinstance(r.get("loss"), (int, float)) and (best is None or r["loss"] < best[1]):
            best = (k, r["loss"])
    if best:
        L.append(f"lowest so far: {best[0]}")
    L.append("")
    L.append(f"budget: {spent} of {budget} units spent; {budget - spent} left. Refinement "
             f"{step} of at most {MAX_REFINEMENTS}.")
    return "\n".join(L)


# ------------------------------------------------------------------------------------- schemas
# Length caps on the visible text fields. Rubric trial 2026-10-03 (F07_1): with thinking on, Qwen3-8B
# wrote 15-20k characters into the visible `reasoning` field, every planning call ended at the token limit
# with invalid JSON, three attempts failed (about 16 minutes) and the plan fell back to the default. The
# thinking is the place to deliberate; the visible fields are a short record of it.
REASONING_MAX = 2000
REASON_MAX = 600
MEMBER_REASON_MAX = 300
def _member_schema(opts: Options, keys: Optional[List[str]] = None) -> Dict[str, Any]:
    keys = list(keys or opts.all_keys)
    # maxItems bound both lists: rubric trial 2026-10-03 (F07_1) looped on a covariate list
    # ("cold_ischemia", "hla_mismatch", ...) until every planning call hit its token limit.
    covs = {"anyOf": [{"type": "array", "maxItems": max(1, len(opts.covariates)),
                       "items": {"type": "string", "enum": opts.covariates}},
                      {"type": "null"}]}
    mask = ({"anyOf": [{"type": "array", "maxItems": max(1, len(opts.covered) - 1),
                        "items": {"type": "string", "enum": opts.covered}},
                       {"type": "null"}]} if opts.covered else {"type": "null"})
    grid = {"anyOf": [{"type": "object", "additionalProperties": False,
                       "properties": {"from": {"type": "number"}, "to": {"type": "number"},
                                      "points": {"type": "integer"}},
                       "required": ["from", "to", "points"]},
                      {"type": "null"}]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"key": {"type": "string", "enum": keys}, "grid": grid,
                           "covariates": covs, "mask": mask,
                           "mask_evidence": {"anyOf": [{"type": "string", "maxLength": MEMBER_REASON_MAX},
                                                       {"type": "null"}]},
                           "pad_absent": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                           "reason": {"type": "string", "maxLength": MEMBER_REASON_MAX}},
            "required": ["key", "grid", "covariates", "mask", "mask_evidence", "pad_absent", "reason"]}


INTERVALS_SCHEMA = {"type": "object", "additionalProperties": False,
                    "properties": {"width": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                                   "n_intervals": {"type": "integer"},
                                   "time_is_index": {"type": "boolean"}},
                    "required": ["width", "n_intervals", "time_is_index"]}


def _row_branch(opts: Options, row: str) -> Dict[str, Any]:
    """One row's plan: the row, its own settings, and members drawn from that row alone. The smoke of
    2026-10-02 (F18): with one key list across rows, Qwen3-8B mixed members of three rows in one plan three
    times running and fell back to the default plan; the grammar now makes a mixed plan unwritable."""
    keys = opts.rows[row]
    props: Dict[str, Any] = {"row": {"type": "string", "enum": [row]}}
    props["ties"] = ({"type": "string", "enum": list(opts.ties_allowed)} if row == "cox_ties"
                     else {"type": "null"})
    if opts.intervals_open:
        props["intervals"] = INTERVALS_SCHEMA if row == "discrete" else {"type": "null"}
    props["members"] = {"type": "array", "minItems": 1, "maxItems": len(keys),
                        "items": _member_schema(opts, keys)}
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


def plan_schema(opts: Options) -> Dict[str, Any]:
    """`reasoning` first; then `analysis`, one branch per admissible row; then the plan's reason."""
    return {"type": "object", "additionalProperties": False,
            "properties": {"reasoning": {"type": "string", "maxLength": REASONING_MAX},
                           "analysis": {"anyOf": [_row_branch(opts, r) for r in opts.rows]},
                           "reason": {"type": "string", "maxLength": REASON_MAX}},
            "required": ["reasoning", "analysis", "reason"]}


def next_step_schema(opts: Options, row: Optional[str] = None) -> Dict[str, Any]:
    """A refinement stays on the plan's row: its members come from that row alone."""
    keys = opts.rows.get(row) if row else None
    keys = keys or opts.all_keys
    return {"type": "object", "additionalProperties": False,
            "properties": {
                "reasoning": {"type": "string", "maxLength": REASONING_MAX},
                "action": {"type": "string", "enum": ["finish", "refine"]},
                "members": {"anyOf": [{"type": "array", "minItems": 1, "maxItems": len(keys),
                                       "items": _member_schema(opts, keys)}, {"type": "null"}]},
                "reason": {"type": "string", "maxLength": REASON_MAX}},
            "required": ["reasoning", "action", "members", "reason"]}


def _plan_part(raw: Dict[str, Any]) -> Dict[str, Any]:
    """The row branch of a plan answer (`analysis`); a flat answer (row and members at the top) is read
    as it is, so scripted planners and older records still parse."""
    a = raw.get("analysis")
    return a if isinstance(a, dict) else raw


def _clean_member(m: Dict[str, Any]) -> Dict[str, Any]:
    """The schema's nulls dropped, so plan.validate sees only what was set. An empty covariate
    list is kept (plan.validate refuses it by name); an empty mask and padding off mean "not set"."""
    return {k: v for k, v in m.items()
            if v is not None and not (k == "mask" and v == []) and not (k == "pad_absent" and v is False)}


def _sig(m: Dict[str, Any]) -> str:
    """What a member's fit depends on in the plan: everything but its reason."""
    return json.dumps({k: v for k, v in m.items() if k != "reason"}, sort_keys=True)


# ------------------------------------------------------------------------------------- the loop
@dataclass
class LoopResult:
    plan: Dict[str, Any]
    reuse: Dict[str, Any]
    steps: List[Dict[str, Any]] = field(default_factory=list)
    fallback: Optional[str] = None
    situations: List[str] = field(default_factory=list)
    n_calls: int = 0


def _validate(raw_plan: Dict[str, Any], opts: Options, budget: int, words: Optional[str] = None):
    return P.validate(raw_plan, design=opts.design, external_form=opts.external_form,
                      has_baseline=opts.has_baseline, covariates=opts.covariates,
                      covered=opts.covered, budget=budget, intervals_open=opts.intervals_open,
                      ties_allowed=opts.ties_allowed, mask_evidence_text=words)


def run_loop(propose: Callable[[str, str, Dict[str, Any], str, int], Dict[str, Any]],
             fit: Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Dict[str, Any]],
             *, declaration: Any, card: Dict[str, Any], opts: Options, words: str,
             max_refinements: int = MAX_REFINEMENTS,
             check_intervals: Optional[Callable[[Dict[str, Any]], List[Dict[str, str]]]] = None
             ) -> LoopResult:
    """The loop. `propose(policy_name, user_text, schema, call_name, max_tokens)` makes one
    constrained model call and returns the parsed object (raising on a failed call); `fit(plan,
    reuse)` fits a plan and returns run_candidates.R's result. Both are injected so the loop is
    tested with a scripted planner and a real or fake fitter. `check_intervals(plan)` runs the gate on
    the declaration amended with a planned discrete grid and returns its refusals as problems; a plan
    that chooses discrete intervals is refused without it."""
    from . import policy
    opts = dataclasses.replace(opts, ties_allowed=ties_allowed(card))
    steps: List[Dict[str, Any]] = []
    sit = situations(card, opts)
    task = render_task(declaration, card, opts, words)
    n_calls = 0

    # ---- the plan
    problems: List[Dict[str, str]] = []
    plan_ok: Optional[Dict[str, Any]] = None
    fallback: Optional[str] = None
    for attempt in range(1, MAX_TRIES + 1):
        user = "\n\n".join(x for x in (task, render_notes(sit), render_problems(problems)) if x)
        n_calls += 1
        try:
            raw = propose("analysis_plan", user, plan_schema(opts), "analysis_plan", PLAN_MAX_TOKENS)
        except Exception as exc:                          # a failed call is recorded, then retried
            problems = [{"code": "no_answer", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}]
            steps.append({"step": "plan", "attempt": attempt, "accepted": False,
                          "problems": problems, "units": 0})
            continue
        part = _plan_part(raw)
        cand = {"row": part.get("row") or "cox",
                "members": [_clean_member(m) for m in part.get("members") or []],
                "reason": raw.get("reason") or part.get("reason") or ""}
        if part.get("ties"):
            cand["ties"] = part["ties"]
        if part.get("intervals"):
            cand["intervals"] = part["intervals"]
        ok, pr, c = _validate(cand, opts, opts.budget, words)
        if ok is not None and ok.get("intervals"):
            # the planned grid goes through the gate on the amended declaration, like a declared one
            pr = (check_intervals(ok) if check_intervals is not None else
                  [{"code": "intervals_unchecked", "message": "no gate is available to check a planned grid"}])
            if pr:
                ok = None
        steps.append({"step": "plan", "attempt": attempt, "accepted": ok is not None,
                      "proposed": cand, "problems": pr, "units": c if ok is not None else 0,
                      "reasoning": str(raw.get("reasoning") or "")[:4000]})
        if ok is not None:
            plan_ok = ok
            break
        problems = pr
    if plan_ok is None:
        row = next(iter(opts.rows))
        plan_ok = P.default_plan(row, opts.design, opts.external_form, opts.has_baseline)
        dok, dpr, dc = _validate(plan_ok, opts, 10 ** 6)
        plan_ok = dok or plan_ok
        fallback = (f"the planner's proposal was refused {MAX_TRIES} times; the fixed default plan "
                    f"(every admissible member of the '{row}' row on its default grid) was fitted")
        steps.append({"step": "plan", "attempt": "fallback", "accepted": True, "proposed": plan_ok,
                      "problems": [], "units": P.plan_cost(plan_ok), "fallback": fallback})

    # ---- fit it (a plan the fitter cannot run falls back to the default plan, once)
    try:
        res = fit(plan_ok, None)
    except Exception as exc:
        if fallback is not None:
            raise
        row = plan_ok.get("row") or next(iter(opts.rows))
        dflt = P.default_plan(row, opts.design, opts.external_form, opts.has_baseline)
        fallback = (f"the planned members could not be fitted ({type(exc).__name__}: "
                    f"{str(exc)[:200]}); the fixed default plan of the '{row}' row was fitted")
        plan_ok = _validate(dflt, opts, 10 ** 6)[0] or dflt
        steps.append({"step": "plan", "attempt": "fallback", "accepted": True, "proposed": plan_ok,
                      "problems": [], "units": P.plan_cost(plan_ok), "fallback": fallback})
        res = fit(plan_ok, None)
    spent = P.plan_cost(plan_ok)
    cur = plan_ok
    rows = list(res.get("candidates") or [])
    partition = res.get("partition") or {}
    sig = {m["key"]: _sig(m) for m in cur["members"]}
    steps.append({"step": "fit", "members": [m["key"] for m in cur["members"]],
                  "units": spent, "reused": []})
    history: List[str] = [f"plan: {cur.get('reason') or ''}"[:300]]

    # ---- refine, a bounded number of times
    refinements = 0 if cur.get("row") == "discrete" else max_refinements
    for step in range(1, refinements + 1):
        if spent >= opts.budget:
            steps.append({"step": "stop", "why": "the budget is spent"})
            break
        problems = []
        done = False
        for attempt in range(1, MAX_TRIES + 1):
            user = "\n\n".join(x for x in (
                task, render_notes(situations(card, opts, rows)),
                render_results(cur, rows, spent, opts.budget, step, history),
                render_problems(problems)) if x)
            n_calls += 1
            try:
                raw = propose("next_step", user, next_step_schema(opts, cur.get("row")), "next_step",
                              STEP_MAX_TOKENS)
            except Exception as exc:
                problems = [{"code": "no_answer", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}]
                steps.append({"step": "next", "refinement": step, "attempt": attempt,
                              "accepted": False, "problems": problems, "units": 0})
                continue
            if raw.get("action") == "finish" or not raw.get("members"):
                steps.append({"step": "next", "refinement": step, "attempt": attempt,
                              "accepted": True, "action": "finish", "units": 0,
                              "reason": str(raw.get("reason") or "")[:1000],
                              "reasoning": str(raw.get("reasoning") or "")[:4000]})
                done = True
                break
            revision = [_clean_member(m) for m in raw.get("members") or []]
            union = {k: v for k, v in cur.items() if k != "members"}
            entries = {m["key"]: m for m in cur["members"]}
            for m in revision:
                entries[m["key"]] = m
            union["members"] = list(entries.values())
            ok, pr, _ = _validate(union, opts, 10 ** 6, words)
            units = 0
            changed: List[str] = []
            if ok is not None:
                changed = [m["key"] for m in ok["members"] if sig.get(m["key"]) != _sig(m)]
                units = sum(P.cost(k) for k in changed)
                if not changed:
                    pr = [{"code": "nothing_changes",
                           "message": "every member you listed is already fitted with those settings; "
                                      "change a setting, add a member, or finish"}]
                elif spent + units > opts.budget:
                    pr = [{"code": "over_budget",
                           "message": f"the refinement costs {units} units and {opts.budget - spent} "
                                      f"are left (units: endpoints 0, plain members 1, ridge or lasso 2, "
                                      f"networks 5)"}]
            steps.append({"step": "next", "refinement": step, "attempt": attempt,
                          "accepted": not pr, "action": "refine", "proposed": revision,
                          "problems": pr, "units": units if not pr else 0, "changed": changed,
                          "reason": str(raw.get("reason") or "")[:1000],
                          "reasoning": str(raw.get("reasoning") or "")[:4000]})
            if pr:
                problems = pr
                continue
            reuse_rows = [r for r in rows if r.get("key") not in changed and r.get("key") != "external"]
            try:
                res = fit(ok, {"rows": reuse_rows, "partition": partition})
            except Exception as exc:
                # the earlier fits stand; the planner is told why this one did not run
                problems = [{"code": "fit_failed", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}]
                steps[-1]["accepted"] = False
                steps[-1]["problems"] = problems
                steps[-1]["units"] = 0
                continue
            rows = list(res.get("candidates") or [])
            spent += units
            cur = ok
            sig = {m["key"]: _sig(m) for m in cur["members"]}
            steps.append({"step": "fit", "members": changed, "units": units,
                          "reused": [r["key"] for r in reuse_rows]})
            history.append(f"refinement {step}: {raw.get('reason') or ''}"[:300])
            break
        else:
            steps.append({"step": "stop", "why": f"no acceptable refinement in {MAX_TRIES} tries"})
            done = True
        if done:
            break
    reuse = {"rows": [r for r in rows if r.get("key") != "external"], "partition": partition}
    return LoopResult(plan=cur, reuse=reuse, steps=steps, fallback=fallback, situations=sit,
                      n_calls=n_calls)


def model_proposer(client, model: str) -> Callable[..., Dict[str, Any]]:
    """`propose` for run_loop, through the agent's one constrained-call path (thinking per act)."""
    from . import boundary, policy

    def _propose(policy_name: str, user: str, schema: Dict[str, Any], call_name: str,
                 max_tokens: int) -> Dict[str, Any]:
        return boundary._chat(client, model, policy.load(policy_name), user, schema, call_name,
                              max_tokens=max_tokens)
    return _propose


def enabled() -> bool:
    """The planner runs unless BREGSURV_PLANNER=off (the "decisions -> defaults" ablation) or the
    ablation switch `no_planner` is set; without a model the V3 set is fitted."""
    from . import ablation
    if os.environ.get("BREGSURV_PLANNER", "").strip().lower() in ("off", "0", "false", "no"):
        return False
    return not ablation.on("no_planner")
