"""The six-section report (SS ), rendered from the fitted objects alone.

Written as a CHECKABLE SPECIFICATION, not a prompt. Every table here is rendered
by this module from `run_candidates.R`'s output; the language model contributes
prose and nothing else, and even that prose contains no digits.

HOW NUMBERS REACH THE PROSE, and why it is built this way.  The model emits
named references -- `[loss_best]`, `[selected_label]` -- and :func:`resolve`
substitutes them at render time from a closed, typed set. The invariant "every
numeric quantity returned to the analyst is an element of the fitted object" then
holds BY CONSTRUCTION and needs no checking pass.

The alternative -- let the model write numbers, then check them and send the
draft back to be rewritten -- is unimplementable here and must not be
reinstated: at temperature 0 the same prompt returns the same draft, so a
rejected draft cannot be fixed by retrying, and appending the violations to the
prompt is the reflexion pattern the design forbids.

Deliberately absent, each for a recorded reason:
  * no figure -- three encodings were built against real data and rejected;
  * no confidence intervals on the coefficients -- the only interval machinery
    in the package cannot represent the borrowing and takes no eta;
  * no "difference from the best", no tie or indistinguishability judgement --
    an inference the analyst did not ask for, and a five-fold interval cannot
    carry it;
  * no IBS and no time-dependent AUC -- both need a held-out set and a training
    baseline hazard, and V3 takes no outer split.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# The closed set of names the model may refer to. Anything else is an error, not
# a silently empty string.
_REFERENCE_KEYS = {
    "n", "n_events", "event_rate", "p", "p_covered", "p_internal_only",
    "p_dropped", "design", "external_form", "criteria", "nfolds", "seed",
    "n_candidates", "selected_label", "selected_borrowing", "selected_penalty",
    "loss_best", "loss_internal", "loss_external", "eta_best", "lambda_best",
    "n_nonzero",
    # : the discrete-time row
    "outcome_scale", "n_intervals",
}

_REF = re.compile(r"\[([a-z_]+)\]")


def _fmt(x: Any) -> str:
    if x is None:
        return "not available"
    if isinstance(x, float):
        if x != x:
            return "not available"
        return f"{x:.4f}".rstrip("0").rstrip(".") if abs(x) < 1e4 else f"{x:.4g}"
    return str(x)


def build_references(res: Dict[str, Any]) -> Dict[str, Any]:
    """The typed set of quantities the model's prose may name."""
    f = res["facts"]
    sel = res["selected"]
    cands = res["candidates"]
    by = {c["key"]: c for c in cands}
    ok = [c for c in cands if c["status"] == "ok"]
    refs = {
        "n": f["n"],
        "n_events": f["n_events"],
        "event_rate": (round(100 * f["n_events"] / f["n"], 1)
                       if f["n"] else None),
        "p": f["p"],
        "p_covered": f["p_covered"],
        "p_internal_only": f["p_internal_only"],
        "p_dropped": len(res["linkage"]["dropped"]),
        "design": f["design"],
        "external_form": f["external_form"],
        "criteria": res["criteria"],
        "nfolds": res["partition"]["nfolds"],
        "seed": res["partition"]["seed"],
        "n_candidates": len(cands),
        "selected_label": sel["label"],
        "selected_borrowing": by.get(sel["key"], {}).get("borrowing"),
        "selected_penalty": by.get(sel["key"], {}).get("penalty"),
        "loss_best": sel["loss"],
        # the two ways of not borrowing, whichever row was fitted
        "loss_internal": (by.get("internal") or by.get("internal_discrete") or {}).get("loss"),
        "loss_external": (by.get("external") or by.get("external_discrete") or {}).get("loss"),
        "outcome_scale": f.get("outcome_scale", "continuous"),
        "n_intervals": (res.get("discrete") or {}).get("n_intervals"),
        "eta_best": sel.get("eta"),
        "lambda_best": sel.get("lambda"),
        "n_nonzero": sel.get("n_nonzero"),
    }
    td = res.get("test_data")
    if td:
        # : the analyst's own test file, when one was supplied. These are
        # the only performance quantities in the report that are NOT
        # cross-validated; the selection never read them. Absent otherwise,
        # so the prose cannot name a held-out number that does not exist.
        ho = sel.get("holdout") or {}
        refs.update({
            "test_n": td.get("n"),
            "test_events": td.get("n_events"),
            "test_cindex_selected": ho.get("cindex"),
            "test_loss_selected": ho.get("loss"),
            "test_ibs_selected": ho.get("ibs"),
            "test_tdauc_selected": ho.get("tdauc"),
        })
    # A reference without a value in THIS run is not offered: on a
    # continuous-time run `[n_intervals]` rendered as "the outcome scale was
    # continuous, evaluated over not available intervals" (report rubric on the
    # cohort benchmark, 2026-09-15). A draft that names one anyway names a
    # quantity outside the closed set and its section is dropped, as any
    # unknown name is. (`runtime_seconds` is gone for the same reason: no table
    # of the report shows it, so a sentence naming it rests on nothing shown.)
    return {k: v for k, v in refs.items() if v is not None}


class UnknownReference(KeyError):
    """The prose named something outside the closed set."""


# How a reference reads inside a sentence. The model writes `[selected_borrowing]`
# and the harness used to substitute the candidate's KEY ("kl", "none"), so the
# prose said "which incorporated kl and none"; `[event_rate]` lost its percent
# sign; `[criteria]` is the scorer's short name. Seen in the synthetic-benchmark
# reports, 2026-09-14. The tables keep the raw values; only the prose changes.
_PROSE_WORDING = {
    "selected_borrowing": {"kl": "Kullback-Leibler borrowing",
                           "mahalanobis": "Mahalanobis borrowing",
                           "euclidean": "Euclidean borrowing",
                           "individual": "individual-level borrowing",
                           "external": "the external model unchanged",
                           "discretekl": "Kullback-Leibler borrowing",
                           "diskd": "distillation from the external model",
                           "none": "no borrowing"},
    "selected_penalty": {"none": "no variable-selection penalty",
                         "ridge": "a ridge penalty", "lasso": "a lasso penalty",
                         "enet": "an elastic-net penalty"},
    "criteria": {"V&VH": "the Verweij-van Houwelingen cross-validated loss",
                 "CIndex": "the cross-validated concordance"},
}


def _fmt_in_prose(key: str, x: Any) -> str:
    if key == "event_rate" and x is not None:
        return f"{_fmt(x)}%"
    words = _PROSE_WORDING.get(key)
    if words and x is not None:
        return words.get(str(x), str(x))
    return _fmt(x)


# What the prose writer is told. Until now the model saw the
# reference NAMES and the candidates' statuses and nothing else, so it could
# not know which candidate was selected, whether the external model covers
# every predictor, or what `[p_internal_only]` counts -- and it wrote stock
# sentences ("not all variables were covered" on a fully covered release,
# member and penalty misnamed, counts used for the wrong quantity: the report
# rubric of 2026-09-15 and the rubric smoke of 2026-10-01). It is now given
# what each reference IS, and the facts of this run in words. No value
# crosses: the facts are categorical and contain no digit.
REFERENCE_MEANING = {
    "n": "number of subjects in the cohort",
    "n_events": "number of subjects with the event",
    "event_rate": "events as a percentage of subjects",
    "p": "number of predictors in the analysis",
    "p_covered": "predictors the external model has a coefficient for",
    "p_internal_only": "predictors the external model does not cover (estimated from the cohort alone)",
    "p_dropped": "external terms with no column in the cohort, set aside",
    "design": "the study design",
    "external_form": "the form in which the external information arrived",
    "criteria": "the cross-validation criterion every candidate was scored by",
    "nfolds": "number of cross-validation folds",
    "seed": "the seed of the cross-validation partition",
    "n_candidates": "number of candidate methods in the admissible set",
    "selected_label": "the name of the selected method",
    "selected_borrowing": "how the selected method uses the external information",
    "selected_penalty": "the penalty of the selected method",
    "loss_best": "cross-validated loss of the selected method",
    "loss_internal": "cross-validated loss of the model fitted to the cohort alone",
    "loss_external": "cross-validated loss of the external model used unchanged",
    "outcome_scale": "continuous time or discrete intervals",
    "n_intervals": "number of discrete follow-up intervals",
    "eta_best": "the borrowing weight chosen for the selected method",
    "lambda_best": "the penalty weight chosen for the selected method",
    "n_nonzero": "non-zero coefficients in the selected model",
    "test_n": "subjects in the analyst's own test file",
    "test_events": "events in the analyst's own test file",
    "test_cindex_selected": "concordance index of the selected model on the test file",
    "test_loss_selected": "partial-likelihood loss of the selected model on the test file",
    "test_ibs_selected": "integrated Brier score of the selected model on the test file",
    "test_tdauc_selected": "time-dependent AUC of the selected model on the test file",
}


def prose_facts(res: Dict[str, Any], refs: Dict[str, Any]) -> List[str]:
    """The facts of this run, in words and without a digit, for the prose writer."""
    f = res["facts"]
    sel = res["selected"]
    out = [f"Study design: {f['design']}."
           + (" The rows are cases and their matched controls; there is no follow-up "
              "time and no censoring, and [n_events] counts the cases."
              if f["design"] == "nested case-control" else "")]
    form = f.get("external_form") or "none"
    out.append(f"External information: {form}.")
    if "p_internal_only" in refs and form not in ("none", "no external information"):
        out.append("The external model covers every predictor of the analysis."
                   if not refs["p_internal_only"] else
                   "The external model does not cover every predictor; the uncovered ones "
                   "are estimated from the cohort alone ([p_internal_only] of them).")
    if refs.get("p_dropped"):
        out.append("Some terms of the external model have no column in the cohort and "
                   "were set aside ([p_dropped] of them).")
    elif "p_dropped" in refs and form not in ("none", "no external information"):
        out.append("Every term of the external model matched a column of the cohort.")
    out.append(f"Selected method: {sel['label']}. It was selected because it has the "
               "lowest cross-validated loss of the admissible set; nothing else was weighed.")
    if res.get("test_data"):
        out.append("The analyst supplied a separate test file; the selected model's "
                   "measures on it are the test_ references. The selection did not use it.")
    else:
        out.append("No test file was supplied; the cross-validated loss is the only "
                   "performance quantity in this report.")
    return out


# A count that is zero in this run is not offered to the prose writer: given
# `[p_internal_only]` = 0 it wrote "as 0 is zero" (rubric full run, first
# reports, 2026-10-01). The fact sentence already says "covers every predictor".
# The reference stays in the closed set, so the tables and resolve are unchanged.
_HIDE_WHEN_ZERO = {"p_internal_only", "p_dropped"}


def prose_references(refs: Dict[str, Any]) -> List[str]:
    """The reference names the prose writer and the explanation call are shown."""
    return [k for k, v in refs.items() if not (k in _HIDE_WHEN_ZERO and v == 0)]


def reference_glossary(refs: Dict[str, Any]) -> List[str]:
    return [f"[{k}]: {REFERENCE_MEANING.get(k, k.replace('_', ' '))}" for k in prose_references(refs)]


# A label's own last word, written again by the model right after the
# reference ("incorporated [selected_borrowing] borrowing" -> "Mahalanobis
# borrowing borrowing", 3 of the first 9 cohort reports graded on 2026-09-15):
# the rendering drops the repeat. Wording, never a quantity.
_DUP_AFTER = re.compile(r"\[(selected_borrowing|selected_penalty|criteria)\]\s+(borrowing|penalty|loss)\b", re.I)


def resolve(text: str, refs: Dict[str, Any]) -> str:
    """Substitute `[name]` references. Raises on a name outside the closed set."""
    unknown = {m.group(1) for m in _REF.finditer(text)} - set(refs)
    if unknown:
        raise UnknownReference(
            "the draft refers to quantities that do not exist: "
            + ", ".join(sorted(unknown)))

    def _dedup(m):
        word = _fmt_in_prose(m.group(1), refs[m.group(1)])
        return word if word.lower().endswith(" " + m.group(2).lower()) else word + " " + m.group(2)
    text = _DUP_AFTER.sub(_dedup, text)
    # "[event_rate]%" -- the substitution already carries the percent sign
    # ("69%%" in the first reports of the rubric run, 2026-10-01)
    text = re.sub(r"\[event_rate\]\s*%", "[event_rate]", text)
    return _REF.sub(lambda m: _fmt_in_prose(m.group(1), refs[m.group(1)]), text)


def not_prose(text: str) -> Optional[str]:
    """Why a draft section is not a sentence, or None when it is one. A list
    of reference names with no words around them ("[n], [event_rate]" ->
    "343, 9.3%"), or a fragment ending in a stray brace, is a section the
    model did not write; it is dropped like a digit, never rendered (report
    rubric on the cohort benchmark, Qwen2.5-7B, 2026-09-15)."""
    words = re.findall(r"[A-Za-z]{3,}", _REF.sub(" ", text or ""))
    if len(words) < 4:
        return "fewer than four words outside its references"
    if re.search(r"[{}\[\]]\s*$", (text or "").strip()):
        return "ends in a stray bracket"
    return None


def check_no_digits(text: str) -> List[str]:
    """Bare digits the model wrote itself. The harness renders every number."""
    stripped = _REF.sub("", text)
    return re.findall(r"(?<![\w.])\d[\d,.]*", stripped)


# --------------------------------------------------------------- table rendering
_PAD_CAP = 34   # padding past this just makes the source unreadable


def _table(headers: List[str], rows: List[List[str]], align: str = "") -> List[str]:
    if not rows:
        return ["_(nothing to show)_", ""]
    widths = [min(_PAD_CAP, max(len(h), *(len(r[i]) for r in rows)))
              for i, h in enumerate(headers)]
    sep = ["-" * w for w in widths]
    if align:
        sep = [("-" * (w - 1) + ":") if a == "r" else "-" * w
               for w, a in zip(widths, align.ljust(len(headers), "l"))]
    out = ["| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |",
           "|" + "|".join(s for s in sep) + "|"]
    for r in rows:
        out.append("| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |")
    out.append("")
    return out


def _plan_settings(m: Dict[str, Any]) -> str:
    """What a planned member was fitted with, rendered by the harness from the checked plan."""
    bits = []
    g = m.get("grid")
    if g:
        bits.append(f"weight from {_fmt(g['from'])} to {_fmt(g['to'])}, {g['points']} values")
    elif m.get("etas"):
        bits.append(f"weight from {_fmt(min(m['etas']))} to {_fmt(max(m['etas']))}, {len(m['etas'])} values")
    if m.get("covariates"):
        bits.append(f"{len(m['covariates'])} covariates: " + ", ".join(f"`{c}`" for c in m["covariates"]))
    if m.get("mask"):
        bits.append("not borrowed: " + ", ".join(f"`{c}`" for c in m["mask"])
                    + (f" (you wrote: \"{m['mask_evidence']}\")" if m.get("mask_evidence") else ""))
    if m.get("pad_absent"):
        bits.append("terms the release lacks padded with zero")
    return "; ".join(bits) or "default settings"


def _planner_words(text: Any) -> str:
    """A reason the planner wrote, shown only when it carries no digit: every number in the report
    comes from a fitted object or the checked plan, never from the model's prose. The words are
    kept whole in trace.json either way."""
    t = " ".join(str(text or "").split())
    if not t:
        return "--"
    if check_no_digits(t):
        return "(in trace.json: the planner's words contain numbers)"
    return t[:400]


def render_plan(plan: Dict[str, Any], steps: Optional[List[Dict[str, Any]]], n_admissible: int,
                budget: Optional[int] = None) -> List[str]:
    """V4 item 7: how the analysis was planned -- what was fitted, with what settings, why, at what
    cost, and what the planner changed after seeing the cross-validated results."""
    from . import plan as _P
    out = ["### How the analysis was planned", ""]
    steps = steps or []
    fb = next((s.get("fallback") for s in steps if s.get("fallback")), None)
    members = plan.get("members") or []
    row = plan.get("row") or "cox"
    row_text = {"cox": "the standard partial likelihood",
                "cox_ties": f"the partial likelihood with the {plan.get('ties') or 'breslow'} correction for tied times",
                "discrete": "the grouped-time likelihood on the declared intervals"}.get(row, row)
    iv = plan.get("intervals")
    if row == "discrete" and iv:
        row_text = ("the grouped-time likelihood on " + str(iv.get("n_intervals")) + " intervals "
                    + ("numbered by the time column itself" if iv.get("time_is_index")
                       else f"of width {_fmt(iv.get('width'))} in the time column's unit")
                    + ", a grid the planner set and the admissibility check accepted")
    if fb:
        out.append(f"The planner's proposals were not accepted, so the fixed default plan was "
                   f"fitted: {fb}.")
    else:
        out.append(f"Of the **{n_admissible}** admissible methods, **{len(members)}** were fitted, on "
                   f"{row_text}. The language model planned which, and with what settings, from "
                   f"the diagnostics of your data; the harness checked every decision -- that each "
                   f"method is admissible here, that your data alone and the external model "
                   f"unchanged are always included, and that the plan stays within a fixed "
                   f"computing budget -- and cross-validation chose among what was fitted.")
    out.append("")
    rows = [[f"`{m['key']}`", _plan_settings(m), _planner_words(m.get("reason"))] for m in members]
    out.extend(_table(["method", "fitted with", "why (the planner's words)"], rows))
    out.append("")
    if plan.get("reason") and not fb:
        out.append("The plan as a whole: " + _planner_words(plan.get("reason")))
        out.append("")
    refits = [s for s in steps if s.get("step") == "fit"][1:]
    nexts = {(s.get("refinement")): s for s in steps
             if s.get("step") == "next" and s.get("accepted") and s.get("action") == "refine"}
    for i, fs in enumerate(refits, start=1):
        st = nexts.get(i) or {}
        out.append(f"After seeing the cross-validated results, the planner refitted "
                   + ", ".join(f"`{k}`" for k in fs.get("members") or [])
                   + "; the other methods were kept as fitted. Why: "
                   + _planner_words(st.get("reason")))
        out.append("")
    fin = [s for s in steps if s.get("step") == "next" and s.get("action") == "finish"]
    if fin and not fb:
        out.append("The planner then finished: " + _planner_words(fin[-1].get("reason")))
        out.append("")
    spent = sum(int(s.get("units") or 0) for s in steps if s.get("step") == "fit")
    if spent:
        out.append(f"Computing used **{spent}**" + (f" of **{budget}**" if budget else "")
                   + " cost units (a method without a penalty path costs one unit, a ridge or lasso "
                     "path two, a neural network five; the external model unchanged costs nothing).")
        out.append("")
    return out


def render(res: Dict[str, Any], prose: Optional[Dict[str, str]] = None,
           declaration: Any = None,
           external: Optional[Dict[str, Any]] = None,
           plan: Optional[Dict[str, Any]] = None,
           plan_steps: Optional[List[Dict[str, Any]]] = None,
           n_admissible: Optional[int] = None) -> str:
    """Render the whole report. `prose` is the model's contribution, by section. V4: with a `plan`,
    section 3 says what was planned and why instead of "all of them were fitted"."""
    refs = build_references(res)
    prose = prose or {}
    f, sel = res["facts"], res["selected"]
    L = res["linkage"]
    out: List[str] = ["# Survival analysis with external information", ""]

    def say(key: str) -> None:
        t = prose.get(key)
        if t:
            out.extend([resolve(t.strip(), refs), ""])

    # ---- 1. Data ------------------------------------------------------------
    out.append("## 1. The data")
    out.append("")
    # The declared outcome is stated, not left implicit. `render` has always
    # accepted a `declaration` and never read it, so the report could not say
    # WHICH column and WHICH value the analyst nominated -- the two things the
    # whole declaration protocol exists to pin down, and the two the reader
    # needs in order to spot a complement mix-up from the event count beside it.
    disc = res.get("discrete") if f.get("outcome_scale") == "discrete intervals" else None
    _rows = [["Study design", f["design"]]]
    # 2026-10-01: a matched sample has no follow-up time and no censoring; its
    # rows are cases and their controls, one case per matched set (the gate
    # refuses otherwise), so section 1 says that instead of "censored"
    _matched = f["design"] == "nested case-control"
    if declaration is not None:
        _rows.append(["Outcome as you declared it",
                      f"`{declaration.event_col}` = {declaration.event_value}"
                      + (f", in matched sets `{declaration.stratum_col}`"
                         if _matched and getattr(declaration, "stratum_col", None)
                         else f", followed up by `{declaration.time_col}`")])
    if disc:
        #, ruling 1: the grid is part of the model and is stated here
        # like the event value, with what the cut did to the data
        K = disc["n_intervals"]
        _tc = getattr(declaration, "time_col", None) or "the time column"
        _rows.append(["Time scale",
                      (f"discrete: `{_tc}` is the interval index 1..{K}"
                       if disc.get("time_is_index")
                       else f"discrete: {K} intervals of width {_fmt(disc.get('width'))}; "
                            f"interval k covers [(k-1) x width, k x width)")
                      + (f"; {disc['n_beyond_horizon']} subject(s) observed past the "
                         f"horizon were censored at interval {K}"
                         f" ({disc.get('n_events_beyond_horizon', 0)} of them events)"
                         if disc.get("n_beyond_horizon") else "")])
    _rows += ([["Subjects", str(f["n"])],
               ["Cases", f"{f['n_events']} (one per matched set)"],
               ["Controls", str(f["n"] - f["n_events"])]] if _matched else
              [["Subjects", str(f["n"])],
               ["Events", f"{f['n_events']} ({refs['event_rate']}%)"],
               ["Censored", str(f["n"] - f["n_events"])]])
    _rows += [["Predictors", str(f["p"])],
              ["External information", f["external_form"]]]
    out.extend(_table(["", "value"], _rows))
    # Where each role came from. Since 2026-09-11 the harness settles what
    # the analyst left unsaid wherever the data leaves one possibility, and
    # runs without asking. This table is the disclosure that replaces the
    # approval step: a wrong inference is read here and corrected by one
    # message, not approved unseen.
    srcs = getattr(declaration, "sources", None) if declaration else None
    if srcs:
        out.append("")
        out.append("How each role was settled:")
        out.append("")
        _how = [["follow-up time", (f"`{declaration.time_col}`" if declaration.time_col
                                    else "none (matched design)"), "time"],
                ["event indicator", f"`{declaration.event_col}`", "event"],
                ["event value", f"`{declaration.event_value}`", "event_value"],
                ["predictors", f"{len(declaration.covariates)} columns",
                 "covariates"],
                ["known at time zero",
                 str(declaration.covariates_time_zero or "not stated"),
                 "time_zero"]]
        if declaration.stratum_col:
            _how.insert(0, ["strata / matched set",
                            f"`{declaration.stratum_col}`", "stratum"])
        if getattr(declaration, "discrete", False):
            _how.append(["time scale",
                         ("interval index" if declaration.time_is_interval_index
                          else f"{declaration.n_intervals} x {_fmt(declaration.interval_width)}"),
                         "discrete"])
        out.extend(_table(["role", "settled as", "how"],
                          [[r, v, srcs.get(k, "stated by you")]
                           for r, v, k in _how]))
    # 2026-10-01: a column the analyst named that the file does not have was
    # asked back by name and left out at the reply (app._settle_and_run records
    # it in the notes); the report says so, so the analysis delivered is not
    # silently a different one from the analysis asked for
    _missing = [n.split("'")[1] for n in (getattr(declaration, "notes", None) or [])
                if n.startswith("named but not a column of the file:") and n.count("'") >= 2]
    if _missing:
        out.append("")
        out.append("You also named " + ", ".join(f"`{m}`" for m in _missing)
                   + (", which is" if len(_missing) == 1 else ", which are")
                   + " not a column of the file; following your reply "
                   + ("it was" if len(_missing) == 1 else "they were")
                   + " left out of the analysis.")
    say("data")

    # ---- 2. Linkage ---------------------------------------------------------
    # This is exactly what the analyst needs and exactly what the paper is not
    # the place for.
    # With nothing to borrow from, this whole section has no source. It used
    # to render anyway: a linkage table of three zeros, and a sentence about how
    # variables were matched against a model that does not exist. Saying less is
    # the only honest option, and the closed reference set the model may name
    # still offers [p_covered] and [p_dropped], so the prose slot is kept.
    if f["external_form"] == "none":
        out.append("## 2. External information")
        out.append("")
        out.append("No external model was supplied, so nothing was borrowed. "
                   "Everything below was estimated from your data alone, and "
                   "the methods that borrow were not among the options.")
        out.append("")
        say("linkage")
    else:
        out.append("## 2. How the external model lines up with your data")
        out.append("")
        # M5: where the external information came from and what
        # was done to it on the way in -- the two conversions the reader must
        # know about (a logged hazard ratio, an inverted covariance) and the
        # things recorded but not used (standard errors, a baseline hazard).
        if external:
            bits = [f"Read from `{external.get('file')}` "
                    f"({external.get('format')}; table "
                    f"`{external.get('coefficient_table')}`, names from "
                    f"`{external.get('name_column')}`, coefficients from "
                    f"`{external.get('coefficient_column')}`)."]
            if external.get("converted_from") == "hazard_ratio":
                bits.append("The published values were **hazard ratios** and "
                            "were logged.")
            if external.get("scale_overridden"):
                bits.append("The scale was taken from the column header, not from "
                            f"the reading of the file ({external['scale_overridden']}).")
            if external.get("matrix_table"):
                mc = external.get("matrix_conditioning") or {}
                bits.append(f"A {external.get('matrix_role')} matrix was read "
                            f"from table `{external['matrix_table']}`"
                            + (" and inverted to the precision matrix the "
                               "Mahalanobis penalty takes"
                               if external.get("matrix_role") == "covariance"
                               else " as the precision matrix the Mahalanobis "
                                    "penalty takes")
                            + (f"; it was scaled to unit mean diagonal and shrunk "
                               f"{int(round(100 * mc['shrink_toward_identity']))}% "
                               f"toward the identity for conditioning (condition "
                               f"number {mc['kappa_raw']:.3g} to "
                               f"{mc['kappa_final']:.3g})."
                               if mc else "."))
                if external.get("matrix_role_overridden"):
                    bits.append("Which of the two it is was decided from the file, not "
                                f"from the reading ({external['matrix_role_overridden']}).")
            if external.get("baseline_table"):
                if disc and f.get("has_baseline"):
                    bits.append(f"Its baseline cumulative hazard was read, evaluated "
                                f"at the {disc['n_intervals']} interval edges and "
                                f"differenced into one increment per interval; "
                                f"with the coefficients it forms the external "
                                f"model on your grid, which the borrowing "
                                f"members lean on and which was also scored "
                                f"unchanged.")
                else:
                    bits.append("A baseline hazard was read and recorded; it is "
                                "used only when follow-up is declared to be in "
                                "discrete intervals, which was not the case here.")
            if external.get("assigned_by") == "model":
                bits.append("Which column held what was proposed by the "
                            "language model and checked by the harness "
                            "against the file.")
            out.append(" ".join(bits))
            out.append("")
        out.extend(_table(
            ["", "count", "variables"],
            [["Covered by the external model", str(len(L["covered"])),
              ", ".join(L["covered"][:14]) + (" ..." if len(L["covered"]) > 14 else "")],
             ["In your data only, not borrowed", str(len(L["zero_padded"])),
              ", ".join(L["zero_padded"][:14]) + (" ..." if len(L["zero_padded"]) > 14 else "")],
             ["In the external model only, dropped", str(len(L["dropped"])),
              ", ".join(L["dropped"][:14]) + (" ..." if len(L["dropped"]) > 14 else "")]]))
        # DERIVED, NOT ASSERTED. run_candidates.R falls back to POSITIONAL
        # matching when the external vector is unnamed, and this sentence used to
        # say "by name" unconditionally with the actual value in parentheses beside
        # it -- so on a positional run the report contradicted itself in one line.
        if L["matched_by"] == "name":
            out.append("Variables were matched **by name**. A variable your data has "
                       "but the external model lacks receives no borrowing; it is "
                       "still estimated from your own data.")
        else:
            out.append("> **Read this one carefully.** The external coefficient "
                       "vector arrived **without names**, so variables were matched "
                       "**by position**: the first external coefficient was applied "
                       "to your first covariate, and so on. Nothing can check that "
                       "the two orderings agree. If they do not, every borrowed "
                       "coefficient is attached to the wrong variable.")
        out.append("")
        if L["dropped"]:
            # Stated plainly rather than buried: this is a real caveat, not
            # bookkeeping. The published coefficients were estimated CONDITIONAL on
            # these variables being in the model.
            out.append(f"> **Worth knowing.** The external model also reports "
                       f"{len(L['dropped'])} predictor(s) your data does not contain "
                       f"({', '.join(L['dropped'])}). They were dropped. Its published "
                       f"coefficients were estimated with those variables in the model, "
                       f"so what is being borrowed is not quite the quantity that study "
                       f"reported.")
            out.append("")
        say("linkage")

    # ---- 3. Candidate set ---------------------------------------------------
    out.append("## 3. What was tried, and why those")
    out.append("")
    if disc:
        out.append(f"Three things decide which methods can apply at all: the study "
                   f"design (**{f['design']}**), the form the external information "
                   f"came in (**{f['external_form']}**), and the time scale you "
                   f"declared (**discrete intervals**). Follow-up in intervals "
                   f"calls for a different row of the library -- grouped-time "
                   f"models, scored by their own likelihood -- which is never "
                   f"ranked against the continuous-time methods. That row admits "
                   f"**{len(res['candidates'])}** members, and all of them were "
                   f"fitted. Nothing was chosen by judgement.")
        out.append("")
        if f.get("has_baseline"):
            out.append("Two model families were fitted: the grouped proportional-"
                       "hazards model with a complementary log-log link "
                       "(DiscreteKL) and a logistic-hazard neural network "
                       "(DiSKD), each once without borrowing and once with the "
                       "borrowing weight chosen by cross-validation; the "
                       "external model was also scored unchanged on your grid.")
        else:
            out.append("The external information carries no baseline hazard, so "
                       "nothing can be borrowed on an interval grid: a Cox "
                       "coefficient vector says how the hazard differs between "
                       "patients, not how large it is in each interval. Both "
                       "families were fitted from your data alone -- the grouped "
                       "proportional-hazards model (DiscreteKL at eta = 0) and "
                       "the logistic-hazard network (DiSKD at eta = 0) -- and "
                       "compared.")
        out.append("")
    elif plan:
        out.append(f"Two things about your data decide which methods can apply at "
                   f"all: the study design (**{f['design']}**) and the form the "
                   f"external information came in (**{f['external_form']}**).")
        out.append("")
    else:
        out.append(f"Two things about your data decide which methods can apply at "
                   f"all: the study design (**{f['design']}**) and the form the "
                   f"external information came in (**{f['external_form']}**). Together "
                   f"they admit **{len(res['candidates'])}** methods, and all of them "
                   f"were fitted. Nothing was chosen by judgement.")
        out.append("")
    if plan:
        from . import plan as _P
        out.extend(render_plan(plan, plan_steps, n_admissible or len(res["candidates"]),
                               _P.DEFAULT_BUDGET))
    # DERIVED FROM THE SET THAT ACTUALLY RAN. This paragraph used to assert
    # that "unpenalised, ridge and lasso were all fitted" and that both ways of
    # not borrowing "can win" -- neither survives a nested case-control design,
    # where the library has no ridge at all and External-only comes back
    # `unavailable` because no fixed-coefficient conditional-likelihood loss
    # exists. A report that describes a candidate set other than the one that
    # ran is worse than one that says less.
    if not disc:
        _pen = [p for p in ("none", "ridge", "lasso")
                if any(c.get("penalty") == p for c in res["candidates"])]
        _names = {"none": "unpenalised", "ridge": "ridge", "lasso": "lasso"}
        _fitted = [_names[p] for p in _pen]
        _phrase = (" and ".join(_fitted) if len(_fitted) < 3
                   else ", ".join(_fitted[:-1]) + " and " + _fitted[-1])
        if not plan:
            out.append(f"Whether a variable-selection penalty helps is not something the "
                       f"data announces in advance, so it was not guessed either: the "
                       f"{_phrase} versions were all fitted and compared.")
            out.append("")
    _nb = [c for c in res["candidates"] if c.get("borrowing") in ("none", "external")]
    _nb_ok = [c for c in _nb if c.get("status") == "ok"]
    if len(_nb_ok) == len(_nb) and len(_nb) > 1:
        out.append("The set also contains the two ways of **not** borrowing -- "
                   "your data alone, and the external model used unchanged -- so "
                   "either can win.")
    else:
        _missing = [c["label"] for c in _nb if c.get("status") != "ok"]
        out.append("The set contains your data alone, so not borrowing at all "
                   "can win. " + ("Note that " + ", ".join(_missing) +
                   " could not be scored on this design, so it was not among the "
                   "options." if _missing else ""))
    out.append("")
    say("candidates")

    # ---- 4. Comparison ------------------------------------------------------
    out.append("## 4. How they compared")
    out.append("")
    rows = []
    for c in res["candidates"]:
        mark = " **<-**" if c["key"] == sel["key"] else ""
        rows.append([
            c["label"] + mark,
            _fmt(c["loss"]) if c["status"] == "ok" else f"_{c['status']}_",
            _fmt(c["eta"]) if c.get("eta") is not None else "-",
            _fmt(c["lambda"]) if c.get("lambda") is not None else "-",
            str(c["n_nonzero"]) if c["n_nonzero"] is not None else "-"])
    out.extend(_table(
        ["method", ("held-out NLL per subject" if disc else "cross-validated loss"),
         "eta", "lambda", "predictors used"],
        rows, align="lrrrr"))
    if disc:
        out.append(f"Lower is better. The number is the **negative log-likelihood "
                   f"per subject of the grouped-time model on held-out data**, "
                   f"pooled over {res['partition']['nfolds']} folds of your own "
                   f"data, all {len(res['candidates'])} members scored on the "
                   f"identical split (the network members choose their learning "
                   f"rate and borrowing weight inside the training folds and "
                   f"are scored on the same held-out folds). It is not an "
                   f"estimate of how the model will perform on new patients. "
                   f"A network member has no coefficient count.")
    else:
        crit = {"V&VH": "Verweij-van Houwelingen (V&VH)"}.get(res["criteria"], res["criteria"])
        out.append(f"Lower is better. The number is a **{crit} "
                   f"cross-validated loss** computed on "
                   f"{res['partition']['nfolds']} folds of your own data, all "
                   f"{len(res['candidates'])} methods scored on the identical split. "
                   f"It is not an estimate of how the model will perform on new "
                   f"patients.")
    out.append("")
    failed = [c for c in res["candidates"] if c["status"] != "ok"]
    if failed:
        out.append("Methods that could not be fitted:")
        out.append("")
        for c in failed:
            out.append(f"- **{c['label']}** -- {c.get('message') or c['status']}")
        out.append("")
    # a borrowing weight chosen at the TOP of its grid: the cross-validation curve was still
    # falling at the largest weight tried, so a larger one might have done better (disclosed,
    # not acted on -- the grid is fixed and never thinned or extended per run)
    at_max = [c for c in res["candidates"] if c["status"] == "ok" and c.get("eta_at_grid_max")]
    if at_max:
        out.append("For " + ", ".join(f"**{c['label']}** (eta {_fmt(c['eta'])})" for c in at_max)
                   + " the borrowing weight was chosen at the largest value the grid offers, "
                     "so a still larger weight might have done as well or better; the "
                     "comparison above is over the grid as fitted.")
        out.append("")
    out.append(f"**Recommended: {sel['label']}.**")
    out.append("")
    say("comparison")

    # ---- 4b. The analyst's test data -------------------------------
    # Printed only when the analyst supplied a test file. Every fitted member
    # is scored on it by the library; the recommendation above did not read
    # these numbers, and the text says so, because a reader who sees a
    # held-out table beside a recommendation assumes the one produced the other.
    td = res.get("test_data")
    if td:
        out.append("### Performance on your test data")
        out.append("")
        rows = []
        for c in res["candidates"]:
            h = c.get("holdout")
            if not h:
                continue
            mark = " **<-**" if c["key"] == sel["key"] else ""
            dash = lambda v: "-" if v is None or (isinstance(v, float) and v != v) else _fmt(v)
            rows.append([c["label"] + mark,
                         dash(h.get("cindex")), dash(h.get("loss")),
                         dash(h.get("ibs")), dash(h.get("tdauc"))])
        out.extend(_table(["method", "C-index", "loss", "IBS", "tdAUC"],
                          rows, align="lrrrr"))
        out.append(f"Computed on the **{td['n']} subjects ({td['n_events']} events) "
                   f"of the test file you supplied** ({td.get('source', 'test data')}), "
                   f"which took no part in fitting or in choosing among the methods: "
                   f"every model above was fitted on your cohort alone and scored "
                   f"once on these rows. Higher is better for the C-index and tdAUC; "
                   f"lower is better for the loss (the deviance per subject) and the "
                   f"integrated Brier score, which uses each model's own baseline "
                   f"hazard from your cohort. The recommendation was made from the "
                   f"cross-validated loss in the table above and did not read this "
                   f"table. A dash means the quantity could not be computed on these "
                   f"rows (too few distinct event times, or no baseline).")
        out.append("")

    # ---- 5. The selected model ---------------------------------------------
    out.append("## 5. The recommended model")
    out.append("")
    _network = disc is not None and sel["key"] in ("internal_nn", "diskd")
    if _network:
        out.append("The recommended model is a neural network: it has no "
                   "coefficient table. Its output is a risk score and a "
                   "hazard for every interval, available from the fitted "
                   "object and reproduced by `repro_diskd.py`. For reference, "
                   "the table shows what the external model said and what the "
                   "grouped proportional-hazards model fitted from your data "
                   "alone said, variable by variable.")
    else:
        out.append("These are point estimates. The table shows what borrowing "
                   "actually did: what the external model said, what your data "
                   "alone said, and where the recommended fit landed.")
    out.append("")
    rows = []
    for c in res["coefficients"]:
        rows.append([c["variable"],
                     _fmt(c["beta_external"]) if c["covered_by_external"] else "-",
                     _fmt(c.get("beta_internal")),
                     "-" if c.get("beta_selected") is None else _fmt(c["beta_selected"])])
    out.extend(_table(["variable", "external model", "your data alone",
                       "recommended"], rows, align="lrrr"))
    if disc and res.get("baseline"):
        # the interval baseline: the second half of a grouped-time model,
        # which the coefficient table alone does not show
        out.append("Baseline hazard by interval, as the log of the hazard "
                   "increment (gamma_k) -- the external model on your grid, "
                   "your data alone, and the recommended fit. The at-risk and "
                   "event counts are what each interval's estimate rests on.")
        out.append("")
        brows = []
        for b in res["baseline"]:
            brows.append([str(b["interval"]),
                          f"[{_fmt(b['from'])}, {_fmt(b['to'])})",
                          str(b["n_at_risk"]), str(b["n_events"]),
                          "-" if b.get("gamma_external") is None else _fmt(b["gamma_external"]),
                          "-" if b.get("gamma_internal") is None else _fmt(b["gamma_internal"]),
                          "-" if b.get("gamma_selected") is None else _fmt(b["gamma_selected"])])
        out.extend(_table(["interval", "covers", "at risk", "events",
                           "external model", "your data alone", "recommended"],
                          brows, align="lrrrrrr"))
    big = [c["variable"] for c in res["coefficients"]
           if c.get("beta_internal") is not None and abs(c["beta_internal"]) > 5]
    if big:
        # Flagged rather than exponentiated into a hazard ratio, which would turn
        # a numerical artefact into a clinical-sounding claim.
        out.append(f"> **{', '.join(big)}**: the estimate from your data alone is "
                   f"implausibly large, which usually means that variable almost "
                   f"perfectly separates who had an event from who did not. Read "
                   f"the recommended column instead, and do not exponentiate the "
                   f"middle one.")
        out.append("")
    say("selected")

    # ---- 6. What this does not establish ------------------------------------
    out.append("## 6. What this analysis does not establish")
    out.append("")
    out.extend([
        "- **Nothing here is causal.** These are associations in one cohort. "
        "None of it says what would happen if a patient's value were changed.",
        ("- **It does not extrapolate.** The fit describes patients like the ones "
         "in these matched sets, as they were sampled. It says nothing about other "
         "populations or about absolute risk, which a matched sample does not carry."
         if "case-control" in str(f.get("design") or "") else
         "- **It does not extrapolate.** The fit describes patients like the ones "
         "in this cohort, over the follow-up actually observed. It says nothing "
         "about other populations or longer horizons."),
        "- **The comparison number is not a performance estimate.** The "
        "cross-validated loss ranked the methods against each other on this "
        "data. It is not how well the model will do on new patients; that "
        "needs a separate, untouched dataset.",
        "- **Only quantities in the table above are supported.** Anything not "
        "shown here was not computed and should not be inferred from it.",
        ""])

    # ---- provenance ---------------------------------------------------------
    out.append("---")
    out.append("")
    out.append(f"_Cross-validation used {res['partition']['nfolds']} folds with "
               f"seed {res['partition']['seed']}; the fold assignment is recorded "
               f"in the run's trace, and `repro.R` reproduces this analysis from "
               f"the estimator library alone, without the language model"
               + (", with `repro_diskd.py` replaying the network members in "
                  "Python alone" if disc else "") + "._")
    return "\n".join(out)


# ------------------------------------------------------------ component 11
_PURPOSE = {
    "intent": "typing the message",
    "role_extraction": "reading the roles the request named",
    "external_roles": "reading the layout of the external file",
    "published_model": "naming a published model from the catalogue",
    "report_prose": "writing the connective prose of this report",
    "explain": "answering a question about the report",
}


def render_model_use(prov: Dict[str, Any]) -> str:
    """Section 7: what the language model was asked, and that it decided no
    number. Rendered by the harness from the call records; a report that
    used no model says so in one line."""
    m = (prov or {}).get("model") or {}
    calls = m.get("calls") or []
    out = ["## 7. How the language model was used", ""]
    if not calls:
        out.append("No language model was used: the declaration was given by number "
                   "and the report is the harness's own text.")
        return "\n".join(out)
    out.append(f"The language model was called {len(calls)} time(s), each call one "
               "constrained generation under a named policy. None of the calls "
               "determined a number, a method, a tuning parameter, or a column the "
               "analyst did not name; every quantity in this report was inserted "
               "from the fitted objects by the harness.")
    out.append("")
    out.append("| call | purpose | prompt tokens | completion tokens | policy |")
    out.append("|---|---|---|---|---|")
    pol = m.get("policies") or {}
    for i, c in enumerate(calls, 1):
        name = c.get("name", "")
        sha = (pol.get(name) or {}).get("sha256", "")
        out.append(f"| {i} | {_PURPOSE.get(name, name)} | {c.get('prompt_tokens', '')} | "
                   f"{c.get('completion_tokens', '')} | {sha} |")
    out.append("")
    served = m.get("served_model") or "(unknown)"
    fp = m.get("weights_fingerprint")
    line = f"Served model: {served}" + (f" ({fp})" if fp else "") + "."
    if m.get("peak_prompt_tokens") is not None:
        line += f" Peak prompt: {m['peak_prompt_tokens']} tokens"
        if m.get("max_model_len"):
            line += f" of a {m['max_model_len']}-token window"
        line += "."
    if m.get("truncated_calls"):
        line += f" {m['truncated_calls']} call(s) were cut off by the length limit."
    out.append(line)
    # : retrieved worked examples, if any call was shown some
    shown = [c.get("few_shot") for c in calls if isinstance(c.get("few_shot"), dict)
             and c["few_shot"].get("n_shown")]
    if shown:
        fs = shown[0]
        out.append(f"The column-role reading was shown {fs['n_shown']} worked example(s) "
                   f"retrieved from the agent's example bank (bank {fs.get('bank_sha256', '')}, "
                   f"examples {', '.join(fs.get('ids', []))}). Their column names are not "
                   f"those of this file; every name in the declaration was checked against "
                   f"the analyst's own words regardless.")
    return "\n".join(out)
