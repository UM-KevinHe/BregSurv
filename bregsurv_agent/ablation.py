"""The ablation switches (ICLR Table `tab:ablation`, 2026-09-13).

`BREGSURV_ABLATE` is a comma-separated list of harness pieces to REMOVE for a
measurement. Off unless set; every run records what was removed in its
provenance (`describe`), so an ablated run can never pass for a real one.

  no_backing      a column name the model returns is accepted as `quoted`
                  whether or not the analyst wrote it (component 9 off)
  no_verify       the declaration is not checked against the file: an event
                  value that occurs nowhere in the column, or a covariate the
                  file lacks, reaches the estimator instead of a refusal
  no_planner_fallback
                  a plan the model cannot lay out ends the turn (the
                  2026-09-13 fallbacks off): an empty plan is a dead end, a
                  plan of only `select_external` gets no run appended
  no_constrained  the schemas are described in the prompt but not enforced by
                  the grammar; the reply is parsed as free text
  no_planner      V4: the planner's decisions replaced by fixed defaults -- every
                  admissible member of the declared row on its default grid

Nothing here is reachable from the app's UI; the variable is read once per
process. Never set it in a deployment.
"""
from __future__ import annotations

import os
from typing import Dict, List

KNOWN = ("no_backing", "no_verify", "no_planner_fallback", "no_constrained", "no_planner")


def cells() -> List[str]:
    raw = os.environ.get("BREGSURV_ABLATE", "")
    out = [t.strip() for t in raw.split(",") if t.strip()]
    bad = [t for t in out if t not in KNOWN]
    if bad:
        raise ValueError(f"BREGSURV_ABLATE names unknown pieces {bad}; known: {KNOWN}")
    return out


def on(piece: str) -> bool:
    """True when `piece` is REMOVED for this run."""
    return piece in cells()


def describe() -> Dict[str, object]:
    return {"removed": cells()}
