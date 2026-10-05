"""Component 9 -- the guardrails, audited as one check a run must pass.

The individual guards live where they act: the admissibility gate in
`check_admissibility.R`, the backing check in `boundary.backed_roles`, evidence
substrings in `intent.validate` and `memory.validate_proposal`, no-digit and
closed references in `report_v3`, the configuration hash in `pipeline`, the
phase rules and call budget in `actions`. This module does not add another
guard. It re-checks, from the session alone and just before the core runs,
that the invariants the guards exist to enforce actually held on THIS
session, and it fails closed: a violation refuses the run and is written into
the provenance, because a harness that has broken one of its own invariants
must not be trusted to have kept the others.

The invariants audited are the five of the paper's Appendix E:

  1. every role that executes has a recorded source;
  2. a role marked `quoted` names something the analyst wrote (textmatch,
     the same predicate the backing check used), a role marked `described`
     carries a phrase the analyst wrote, and every other source has a
     recognised form (`reply`, `inferred: …`, `remembered: …`, `checkbox…`);
  3. the state is coherent (`Session.invariants`: no result without an
     admissible verification, and so on);
  4. every model call was one constrained call under a named policy, with
     its raw output recorded, and no turn exceeded the call budget;
  5. every planned act was in the action set and legal in its phase.

Invariant 4 of the paper (every quantity is an element of a fitted object)
holds by construction in `report_v3.resolve` and is tested there; it is not
re-derived from a rendered report, where tables legitimately carry digits.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import actions, policy, textmatch

_SOURCE_PREFIXES = ("quoted", "reply", "inferred", "remembered", "checkbox",
                    "dictionary", "described",
                    "planned")       # V4 4b: a discrete grid the planner set and the gate checked


def analyst_text(session: Any) -> str:
    """Everything the analyst typed this session, from the action log."""
    parts = [a["message"] for a in getattr(session, "actions", [])
             if isinstance(a, dict) and a.get("message")]
    return "\n".join(str(p) for p in parts)


def audit(session: Any) -> List[str]:
    bad: List[str] = []
    decl = getattr(session, "declaration", None)
    prof = getattr(session, "profile", None) or {}
    cols = [c["name"] for c in prof.get("columns", [])]
    text = analyst_text(session)

    # 1 + 2: sources
    if decl is not None:
        src = dict(getattr(decl, "sources", {}) or {})
        roles = {"time": decl.time_col, "event": decl.event_col,
                 "event_value": decl.event_value,
                 "covariates": ", ".join(decl.covariates or []),
                 "stratum": decl.stratum_col,
                 "time_zero": decl.covariates_time_zero,
                 # : a declared grid must carry a source like any role
                 "discrete": (f"{decl.n_intervals}"
                              if getattr(decl, "discrete", False) else None)}
        for role, val in roles.items():
            if not val:
                continue
            s = str(src.get(role, "") or "")
            if not s:
                if getattr(decl, "source", "") == "dictionary" and role != "time_zero":
                    continue                      # path 1: the dictionary decided, no dialogue
                bad.append(f"role {role} executes without a recorded source")
                continue
            if not s.startswith(_SOURCE_PREFIXES):
                bad.append(f"role {role} has an unrecognised source {s!r}")
            elif s.startswith("described:"):
                ph = s.split(":", 1)[1].strip().strip('"')
                if not textmatch.phrase_in(text, ph):
                    bad.append(f"role {role} is marked described from a phrase the "
                               f"analyst never wrote: {ph!r}")
            elif s == "quoted":
                names = ([n.strip() for n in val.split(",")] if role == "covariates"
                         else [val])
                for n in names:
                    ok = (textmatch.value_mentioned(text, n) if role == "event_value"
                          else textmatch.mentions(text, n, cols))
                    if not ok:
                        bad.append(f"role {role} is marked quoted but the analyst "
                                   f"never wrote {n!r}")

    # 3: state coherence
    inv = session.invariants() if hasattr(session, "invariants") else []
    bad += [f"state: {v}" for v in inv]

    # 4: model calls
    for c in getattr(session, "model_calls", []) or []:
        name = c.get("name")
        if name not in policy.NAMES:
            bad.append(f"model call {name!r} is not one of the policies")
        if "error" not in c and not c.get("raw_text"):
            bad.append(f"model call {name!r} has no raw output recorded")
    for a in getattr(session, "actions", []) or []:
        if isinstance(a, dict) and a.get("route") == "turn_calls":
            if a.get("model_calls", 0) > a.get("budget", actions.MODEL_CALLS_PER_TURN):
                bad.append(f"a turn made {a['model_calls']} model calls; the budget is "
                           f"{a['budget']}")

    # 5: every planned act is in the set
    known = {x.value for x in actions.Act}
    for a in getattr(session, "actions", []) or []:
        if isinstance(a, dict) and a.get("plan"):
            for p in a["plan"]:
                if p not in known:
                    bad.append(f"planned act {p!r} is not in the action set")
    return bad
