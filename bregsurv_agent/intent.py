"""M1: what is this message asking the system to do.

The first thing the harness does with a message it cannot parse as a numbered
reply is ask the model to TYPE it -- not answer it -- so that a question about
the report is not sent to the role extractor and a description of an external
file is not read as a declaration. One constrained call, single-turn, from a
four-line state summary; the closed set of kinds is the routing table, and the
harness does the routing.

  declare_roles      the message names a column for at least one role
  edit_declaration   it changes a role declared earlier
  describe_external  it describes or points to external information
  evaluate_by_splits evaluate the methods on repeated random train/test splits (V4,
                     2026-10-04; `splits.py`), alone or with a declaration
  ask_about_result   a question about the report already produced
  ask_about_method   a question about how the system works
  out_of_scope       something this system does not do
  other              none of the above, or too unclear to type

There is deliberately NO `approve` kind and no approval step for it to route
to. the analyst is asked only what the harness cannot
decide from the request and the data; everything else is decided, run, and
DISCLOSED in the report, where a wrong decision is visible and corrected by one
more message (`edit_declaration`). A typing error here is therefore always the
recoverable kind: it costs a canned reply or a re-run, never a wrong number.

Every intent carries `evidence`, a span the model must quote verbatim from the
message -- the same quoting invariant boundary 1 rests on. The harness checks
it. An intent whose evidence is not in the message is marked unverified and,
for `out_of_scope` only, demoted to `other`: a refusal must never rest on words
the analyst did not write. The other kinds go ahead unverified because nothing
they trigger is consequence-bearing -- an extraction is verified against the
data, and the replies are canned text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import boundary, policy

KINDS = ("declare_roles", "edit_declaration", "describe_external",
         "select_external", "compare_runs", "multi_step",
         "evaluate_by_splits",                      # V4: evaluation by repeated splits
         "kaplan_meier",                            # V4: the analyst asks to see the KM curve
         "evaluate_on_test",                        # V4: score the models on the supplied test file
         "ask_about_result", "ask_about_method", "out_of_scope", "other")

EXTERNAL_FORMS = ("coefficients", "coefficients_with_covariance",
                  "coefficients_with_baseline_hazard", "individual_level_data",
                  "unknown")

OUT_OF_SCOPE_REASONS = ("competing_risks", "time_varying_covariates",
                        "individual_prediction", "figure_requested",
                        "causal_claim", "different_outcome_type", "other")

# The grammar allows MAX_INTENTS_RAW items so the output is bounded and always
# closes; the harness keeps at most MAX_INTENTS distinct kinds, which is what the
# per-turn call budget (actions.MODEL_CALLS_PER_TURN) is checked against.
MAX_INTENTS_RAW = 6
MAX_INTENTS = 4


def schema_for(externals: Optional[List[str]] = None) -> Dict[str, Any]:
    """The intent schema, with `external_name` an enum of the releases loaded
    in this session (M2): a message that means one of them can only name one
    of them. With none loaded the field is null-only."""
    names = list(externals or [])
    ext_name = ({"anyOf": [{"type": "string", "enum": names}, {"type": "null"}]}
                if names else {"type": "null"})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            # first, as in every schema: the reason precedes the decision
            "reasoning": {"type": "string"},
            "intents": {
                "type": "array", "minItems": 1, "maxItems": MAX_INTENTS_RAW,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string", "enum": list(KINDS)},
                        "evidence": {"type": "string"},
                        "external_form": {"anyOf": [
                            {"type": "string", "enum": list(EXTERNAL_FORMS)},
                            {"type": "null"}]},
                        "external_name": ext_name,
                        "out_of_scope_reason": {"anyOf": [
                            {"type": "string", "enum": list(OUT_OF_SCOPE_REASONS)},
                            {"type": "null"}]},
                        # V4: the column a requested Kaplan-Meier curve is split by,
                        # as the analyst wrote it; null for the whole cohort
                        "km_by": {"anyOf": [{"type": "string", "maxLength": 80}, {"type": "null"}]},
                    },
                    "required": ["kind", "evidence", "external_form",
                                 "external_name", "out_of_scope_reason", "km_by"],
                },
            },
        },
        "required": ["reasoning", "intents"],
    }


INTENT_SCHEMA: Dict[str, Any] = schema_for([])

# Component 2: the instructions live in policies/intent.md, hashed into provenance.
_INTENT_SYSTEM = policy.load("intent")


@dataclass
class Intent:
    kind: str
    evidence: str
    external_form: Optional[str] = None
    out_of_scope_reason: Optional[str] = None
    evidence_verified: bool = True
    demoted_from: Optional[str] = None
    external_name: Optional[str] = None       # M2: which loaded release the message means
    km_by: Optional[str] = None               # V4: the column a requested KM curve is split by

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "evidence": self.evidence,
                "external_form": self.external_form,
                "external_name": self.external_name,
                "out_of_scope_reason": self.out_of_scope_reason,
                "evidence_verified": self.evidence_verified,
                "demoted_from": self.demoted_from, "km_by": self.km_by}


# ------------------------------------------------------------------- the call
def state_line(session: Any) -> str:
    """The four facts the model is shown instead of a transcript.

    A `state.Session` computes its own line (component 3); a plain dict is
    still accepted for the check scripts that build a synthetic state.
    """
    if hasattr(session, "state_line"):
        return session.state_line()
    s = session or {}
    coefs = s.get("coefs")
    ext = f"published coefficients ({len(coefs)})" if coefs else "none"
    decl = s.get("declaration")
    pend = s.get("pending") or {}
    if decl is not None:
        d = "verified" if getattr(s.get("verification"), "admissible", False) \
            else "declared but refused"
    elif pend:
        d = "partial (" + ", ".join(k for k in ("time", "event", "event_value",
                                                 "covariates", "time_zero")
                                     if pend.get(k)) + ")"
    else:
        d = "none"
    res = "present" if s.get("result") is not None else "none"
    return (f"State: cohort loaded: {'yes' if s.get('profile') else 'no'} | "
            f"external information: {ext} | declaration: {d} | result: {res}")


def classify(client, model: str, message: str, state: str,
             externals: Optional[List[str]] = None,
             columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """One constrained generation. The raw dict; see :func:`validate`. V4: up to five retrieved worked
    examples precede the message (`intent_examples`), recorded on the call as `examples`."""
    from . import intent_examples
    prefix, rec = intent_examples.for_message(message, state, columns or [])
    user = f"{prefix}{state}\n\nThe analyst wrote:\n{message}"
    return boundary._chat(client, model, _INTENT_SYSTEM, user,
                          schema_for(externals), "intent", max_tokens=600,
                          extra_record=({"examples": rec} if rec else None))


_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def validate(message: str, raw: Dict[str, Any],
             result_present: Optional[bool] = None) -> List[Intent]:
    """Check the evidence against the message; never trust the model's typing
    of `out_of_scope` on words that are not there. Deterministic.

    `result_present`, when given, is the phase rule for `ask_about_result`: a
    question about a result cannot exist before a result does. on the A40: both models typed "Please analyse my transplant
    data and tell me what predicts survival" and "Can you plot the
    Kaplan-Meier curves" as `ask_about_result` with no result in the state.
    Such an intent is demoted to `other` (the harness then asks), and the
    demotion is on the record as `demoted_from`."""
    msg = _norm(message)
    out: List[Intent] = []
    seen = set()
    # duplicates are dropped BEFORE the cap, so a kind the model repeated cannot
    # crowd out a different one (live smoke 2026-10-04: two `declare_roles`
    # pushed the split request past the cap)
    for item in (raw.get("intents") or [])[:MAX_INTENTS_RAW]:
        if len(out) >= MAX_INTENTS:
            break
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in KINDS or kind in seen:
            continue
        seen.add(kind)
        ev = str(item.get("evidence") or "")
        ok = bool(ev) and _norm(ev) in msg
        it = Intent(kind=kind, evidence=ev,
                    external_form=(item.get("external_form")
                                   if kind == "describe_external" else None),
                    external_name=(item.get("external_name")
                                   if kind in ("select_external", "describe_external",
                                               "compare_runs") else None),
                    out_of_scope_reason=(item.get("out_of_scope_reason")
                                         if kind == "out_of_scope" else None),
                    evidence_verified=ok)
        if kind == "kaplan_meier":
            # a grouping column is kept only as the analyst wrote it; the app then checks it is a
            # column of the file
            by = str(item.get("km_by") or "").strip()
            it.km_by = by if by and _norm(by) in msg else None
        if kind == "out_of_scope" and not ok:
            it.demoted_from, it.kind = "out_of_scope", "other"
            it.out_of_scope_reason = None
        elif kind == "ask_about_result" and result_present is False:
            it.demoted_from, it.kind = "ask_about_result", "other"
        if it.kind in seen and it.kind != kind:
            continue
        seen.add(it.kind)
        out.append(it)
    if not out:
        out.append(Intent(kind="other", evidence="", evidence_verified=False,
                          demoted_from="(no usable intent returned)"))
    return out


_ORDER = {k: i for i, k in enumerate((
    "multi_step", "describe_external", "select_external",
    "declare_roles", "edit_declaration", "compare_runs", "evaluate_by_splits", "kaplan_meier", "evaluate_on_test",
    "ask_about_method", "ask_about_result", "out_of_scope", "other"))}


def dispatch_order(intents: List[Intent]) -> List[Intent]:
    """External information first (it changes what a declaration means), then
    the declaration, then answers; fixed, not the model's ordering."""
    return sorted(intents, key=lambda i: _ORDER.get(i.kind, 99))


# --------------------------------------------------------------- canned text
REFUSALS: Dict[str, str] = {
    "competing_risks":
        "This library fits one event type. Competing risks are not modelled. If "
        "the other event can be treated as censoring for your question, declare "
        "the outcome that way; if it cannot, this is not the tool for it.",
    "time_varying_covariates":
        "This library fits one row per subject. A covariate that changes after "
        "the start of follow-up cannot be represented, and treating a later "
        "value as a baseline value can reverse the direction of an effect.",
    "individual_prediction":
        "This system estimates coefficients and compares estimators. It does not "
        "produce a risk score for an individual patient.",
    "figure_requested":
        "Beyond the Kaplan-Meier estimate of your cohort, drawn with every "
        "analysis (by stratum when you declared strata), and the box plots of an "
        "evaluation by repeated splits, this system draws no figures. The "
        "candidates.json and repro.R it writes hold everything a figure would "
        "need.",
    "causal_claim":
        "Everything here is an adjusted association from observational data. "
        "Nothing in the analysis supports a causal claim, and the report says "
        "so.",
    "different_outcome_type":
        "This system fits time-to-event outcomes only: a follow-up time and an "
        "event indicator per subject.",
    "other":
        "This system fits survival models on your cohort, borrowing from "
        "external information when that helps. What you asked for is outside "
        "that.",
}


def refusal(it: Intent) -> str:
    quoted = f'You wrote "{it.evidence}". ' if it.evidence else ""
    return quoted + REFUSALS.get(it.out_of_scope_reason or "other",
                                 REFUSALS["other"])


METHOD_ANSWER = (
    "**How this works.** Two facts about your data -- the study design, and "
    "the form the external information arrived in -- decide which estimators "
    "can apply. Every one of them is fitted on one shared cross-validation "
    "partition, and the one with the lowest held-out loss is selected; no "
    "model chooses. Nothing is fitted until the columns you named are checked "
    "against the file, and the report states every decision that was made "
    "for you and where it came from. `repro.R` re-runs the whole thing with no "
    "language model involved."
)
