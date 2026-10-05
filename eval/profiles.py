"""Synthetic column profiles for the elicitation corpus.

NO PATIENT DATA, and none is needed. Boundary 1 sees exactly two things: the
list of column NAMES in the file, and the analyst's sentence. It never sees a
row. So a corpus item needs a column list, not a dataset -- which is why 500
items cost nothing to store and nothing to run.

The six profiles are chosen to make the corpus's axes reachable rather than to
be realistic in isolation:

  kidney     the ordinary case. Two outcome columns among ten, an identifier and
             a site column that a lazy extractor sweeps in.
  complement THE trap. `survival_event` and `survival_censored` are exact
             complements and BOTH are plausible; `survival_time_days` and
             `survival_time_years` are the same quantity twice. Naming the wrong
             one of either pair inverts or rescales the analysis, and the column
             names alone cannot say which is right.
  opaque     names a clinician would recognise and a model cannot: `os_mo`,
             `status2`, `x1`..`x6`. This is where "time to death" MUST return
             null rather than a guess.
  matched    a nested case-control shape: `set_id` (many small groups), `case`,
             plus `site` and `pid` as decoys.
  wide       forty covariates, so "adjust for everything" has no honest
             representation in a list-of-names field.
  registry   a different naming dialect -- `time_to_event`, `event_flag` --
             so paraphrase robustness is not measured on one house style.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _col(name: str, kind: str = "numeric", **kw) -> Dict[str, Any]:
    c: Dict[str, Any] = {"name": name, "type": kind}
    c.update(kw)
    return c


def _profile(pid: str, cols: List[str], time_col, event_col,
             covariates: List[str], noise: List[str],
             stratum_col=None, note: str = "") -> Dict[str, Any]:
    return {
        "id": pid,
        "columns": cols,
        # what the data actually is, used ONLY to build ground truth -- never
        # shown to the model, which sees `columns` and the sentence
        "truth": {"time": time_col, "event": event_col,
                  "covariates": covariates, "stratum": stratum_col},
        # columns present in the file that a sentence never names and that a
        # lazy extractor must not sweep in
        "noise": noise,
        "note": note,
    }


KIDNEY = _profile(
    "kidney",
    ["age", "bmi", "egfr", "hgb", "albumin", "dialysis_yrs", "donor_age",
     "cold_ischemia", "followup_days", "died", "patient_id", "site"],
    time_col="followup_days", event_col="died",
    covariates=["age", "bmi", "egfr", "donor_age", "cold_ischemia"],
    noise=["patient_id", "site"],
    note="the ordinary case; the same fixture the end-to-end suites use",
)

COMPLEMENT = _profile(
    "complement",
    ["subject_id", "age_at_tx", "bmi", "egfr", "survival_time_days",
     "survival_time_years", "survival_event", "survival_censored"],
    time_col="survival_time_days", event_col="survival_event",
    covariates=["age_at_tx", "bmi", "egfr"],
    noise=["subject_id", "survival_censored", "survival_time_years"],
    note="two complement pairs; the names alone cannot say which is right",
)

OPAQUE = _profile(
    "opaque",
    ["ptid", "ctr", "os_mo", "status2", "x1", "x2", "x3", "x4", "x5", "x6"],
    time_col="os_mo", event_col="status2",
    covariates=["x1", "x2", "x3", "x4", "x5", "x6"],
    noise=["ptid", "ctr"],
    note="a description without a column name must return null here",
)

MATCHED = _profile(
    "matched",
    ["set_id", "site", "pid", "age", "bmi", "egfr", "donor_age", "case"],
    time_col=None, event_col="case",
    covariates=["age", "bmi", "egfr", "donor_age"],
    noise=["site", "pid"],
    stratum_col="set_id",
    note="matched design: no follow-up duration exists in the file",
)

WIDE = _profile(
    "wide",
    [f"g{i:03d}" for i in range(1, 41)] + ["age", "sex", "time", "status", "id"],
    time_col="time", event_col="status",
    covariates=["age", "sex"] + [f"g{i:03d}" for i in range(1, 41)],
    noise=["id"],
    note="'adjust for everything' has no representation in a list of names",
)

REGISTRY = _profile(
    "registry",
    ["recipient_age", "donor_age", "bmi_at_listing", "creatinine",
     "time_to_event", "event_flag", "center_id", "listing_year"],
    time_col="time_to_event", event_col="event_flag",
    covariates=["recipient_age", "donor_age", "bmi_at_listing", "creatinine"],
    noise=["center_id", "listing_year"],
    note="a different naming dialect, so robustness is not measured on one",
)

ALL_PROFILES = {p["id"]: p for p in
                (KIDNEY, COMPLEMENT, OPAQUE, MATCHED, WIDE, REGISTRY)}


def as_model_profile(p: Dict[str, Any]) -> Dict[str, Any]:
    """The shape `boundary.extract_roles` expects: names only, nothing else."""
    return {"columns": [{"name": n} for n in p["columns"]]}
