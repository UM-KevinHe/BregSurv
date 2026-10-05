"""Components 5, 6 and 7 -- the closed action set, and the orchestrator that walks it.

The three components collapse into one module because in this agent they are
one thing. The TOOLS the model can reach are not the estimator library (it is
addressed by the harness alone, from `run_candidates.R`, and a new estimator
enters that file and never a prompt); they are the typed acts below. The
ACTIONS are those acts. The PLANNER is `plan`: a deterministic function of
the session's phase and the typed intents M1 returned, so there is no model
call that proposes "what next" -- that call was folded into M1 on 2026-09-11
(master memory, M2), because on every path the harness would have
overridden it. The ORCHESTRATOR is `app.submit_answer`, which executes the plan
in order, verifies each act's output the way it would verify a person's
(a name must be in the message, an id must be in the catalogue, a reference
must be in the closed set), records what ran, and stops at the first act that
needs the analyst.

Invariants the module makes checkable:

* every act is in `SPECS`, with who proposes it and what verifies it;
* an act that calls the model is allowed only in the phases listed, so an
  explanation cannot be asked for before a result exists and a role proposal
  cannot be made before a cohort is loaded;
* a turn makes at most `MODEL_CALLS_PER_TURN` model calls, by construction of
  `plan` (the intent call, at most one role proposal, at most one
  published-model lookup, at most one explanation, and the report) -- there
  is no loop in which the model can call itself again.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Sequence, Tuple

from .state import Phase


class Act(str, Enum):
    # proposed by the model, verified by the harness
    TYPE_MESSAGE = "type_message"              # M1
    PROPOSE_ROLES = "propose_roles"            # boundary 1 (+ the backing check)
    NAME_PUBLISHED_MODEL = "name_published_model"  # component 4, only with no file
    READ_RELEASE = "read_release"              # M5, at upload, outside a turn
    WRITE_REPORT = "write_report"              # boundary 2
    EXPLAIN_RESULT = "explain_result"          # M4
    WORD_QUESTION = "word_question"            # the lead-in to the numbered question
    PLAN_STEPS = "plan_steps"                  # M2: the ordered steps of a multi-step request
    EXPLAIN_REFUSAL = "explain_refusal"        # plain words for a gate refusal; never advice
    PLAN_ANALYSIS = "plan_analysis"            # V4: what is fitted (row, members, grids, masks)
    REFINE_ANALYSIS = "refine_analysis"        # V4: finish, or refit / add members after the fit
    EVALUATE_BY_SPLITS = "evaluate_by_splits"  # V4: read the split request; the harness runs it
    # decided and executed by the harness alone
    SHOW_EXTERNAL = "show_external"
    ANSWER_METHOD = "answer_method"
    NO_RESULT_YET = "no_result_yet"
    REFUSE = "refuse"
    COMPLETE = "complete"
    ASK = "ask"
    VERIFY = "verify"
    RUN_CORE = "run_core"
    SELECT_EXTERNAL = "select_external"        # M2: make a loaded release the active one
    COMPARE_RUNS = "compare_runs"              # M2: the harness compares the two latest runs


@dataclass(frozen=True)
class ActionSpec:
    act: Act
    proposer: str        # "model:<schema name the call is logged under>" or "harness"
    verifier: str        # what checks the output before it takes effect
    allowed_in: Tuple[Phase, ...]

    @property
    def needs_model(self) -> bool:
        return self.proposer.startswith("model:")


_LOADED = (Phase.PROFILED, Phase.DECLARING, Phase.REFUSED, Phase.VERIFIED, Phase.DONE)

SPECS: Dict[Act, ActionSpec] = {a.act: a for a in (
    ActionSpec(Act.TYPE_MESSAGE, "model:intent",
               "every intent's evidence must be a substring of the message; an "
               "out-of-scope intent without it is demoted", _LOADED),
    ActionSpec(Act.PROPOSE_ROLES, "model:role_extraction",
               "a name is quoted only if the analyst wrote it (textmatch); every "
               "name is then resolved against the file by parse_reply", _LOADED),
    ActionSpec(Act.NAME_PUBLISHED_MODEL, "model:published_model",
               "ids must be in the catalogue enum and evidence in the message; the "
               "card is rendered from the catalogue, the model's words are not shown",
               _LOADED),
    ActionSpec(Act.READ_RELEASE, "model:external_roles",
               "every named column must exist; canonicalise checks scale, intervals, "
               "symmetry, running sums; a file is pinned by checksum", _LOADED),
    ActionSpec(Act.WRITE_REPORT, "model:report_prose",
               "no digit; every reference in the closed set; a failing draft is "
               "dropped, never repaired", (Phase.VERIFIED,)),
    ActionSpec(Act.EXPLAIN_RESULT, "model:explain",
               "no digit; every reference in the closed set; a failing answer is "
               "dropped and the analyst told", (Phase.DONE, Phase.DECLARING)),
    ActionSpec(Act.WORD_QUESTION, "model:ask",
               "no digit; every column-like name must be a column of the file; the "
               "harness's numbered list follows unchanged and parses the reply; a "
               "failing draft is dropped and the plain list shown",
               (Phase.PROFILED, Phase.DECLARING, Phase.DONE, Phase.REFUSED)),
    ActionSpec(Act.EXPLAIN_REFUSAL, "model:refusal",
               "no digit; every column-like name must be a column of the file; the "
               "harness's refusal text and numbered list follow unchanged; a failing "
               "draft is dropped", (Phase.REFUSED, Phase.DECLARING, Phase.PROFILED, Phase.DONE)),
    ActionSpec(Act.PLAN_STEPS, "model:plan_steps",
               "every act in the step enum, every file name loaded, every evidence "
               "phrase in the message, a comparison only after two runs; the list is "
               "cut at the first step that fails; executed one by one, each verified",
               _LOADED),
    ActionSpec(Act.PLAN_ANALYSIS, "model:analysis_plan",
               "plan.validate: every member admissible for the declared design and release, the "
               "two do-not-borrow endpoints present, grids, covariate subsets, masks and padding "
               "well formed, the cost within the budget; a refused plan goes back with the "
               "problems by name, and after three refusals the fixed default plan is fitted",
               (Phase.VERIFIED,)),
    ActionSpec(Act.REFINE_ANALYSIS, "model:next_step",
               "the same checks on the plan with the refinement merged in, the same row, a "
               "change to something already fitted, and the units of the changed members "
               "within the budget left; members not changed are reused, not refitted; at most "
               "two refinements", (Phase.VERIFIED,)),
    ActionSpec(Act.EVALUATE_BY_SPLITS, "model:split_request",
               "splits.validate: a number is kept only when the analyst wrote it inside the quoted "
               "span and the span is in the message; measures and the figure are checked against "
               "the message's words; a number of splits the message does not state is the model's "
               "choice within the cap, recorded as chosen. The harness draws the splits from a "
               "recorded seed, runs the verified analysis on every split, scores every member and "
               "writes every number; only after a result exists, Cox-family rows only", _LOADED),
    ActionSpec(Act.SELECT_EXTERNAL, "harness",
               "the name must be one of the loaded releases (an enum in M1's schema)", _LOADED),
    ActionSpec(Act.COMPARE_RUNS, "harness",
               "computed from the two latest fitted objects; every number the harness's", _LOADED),
    ActionSpec(Act.SHOW_EXTERNAL, "harness", "the card of the object already read", _LOADED),
    ActionSpec(Act.ANSWER_METHOD, "harness", "fixed text", _LOADED),
    ActionSpec(Act.NO_RESULT_YET, "harness", "fixed text", _LOADED),
    ActionSpec(Act.REFUSE, "harness", "the refusal catalogue, quoting verified evidence",
               _LOADED),
    ActionSpec(Act.COMPLETE, "harness",
               "fills a role only where one column is eligible or a stated rule or a "
               "remembered declaration resolves it; the source is recorded", _LOADED),
    ActionSpec(Act.ASK, "harness", "the numbered question, only the open roles", _LOADED),
    ActionSpec(Act.VERIFY, "harness",
               "parse_reply against the file, the admissibility gate, the individual-"
               "level name check; the configuration is hashed here", _LOADED),
    ActionSpec(Act.RUN_CORE, "harness",
               "the hash is re-checked at dispatch; every member on one partition; "
               "the fitted keys must equal the derived keys", (Phase.VERIFIED,)),
)}

# the intent call, at most one role proposal, at most one published-model
# lookup, at most one explanation, and the report: nothing in plan can
# exceed this (the worst case is a message that names a model with no file
# uploaded, declares roles, and asks about an existing result)
MODEL_CALLS_PER_TURN = 5


def plan(session: Any, intents: Sequence[Any]) -> List[Act]:
    """The acts of this turn, in order, from the phase and the typed intents.

    Deterministic. `intents` are M1's validated intents in dispatch order
    (describe_external, declare/edit, method, result, out_of_scope, other).
    A role proposal is always followed by COMPLETE; what follows COMPLETE
    (ASK, or VERIFY then RUN_CORE) is decided by its outcome, so the plan
    ends at COMPLETE and the orchestrator continues from the completion.
    """
    acts: List[Act] = []
    kinds = [getattr(i, "kind", None) for i in intents]
    if "multi_step" in kinds:
        # M2: the model lays out the steps; nothing else runs on this turn
        return [Act.PLAN_STEPS]
    for k in kinds:
        if k in ("declare_roles", "edit_declaration"):
            if Act.PROPOSE_ROLES not in acts:
                acts.append(Act.PROPOSE_ROLES)
        elif k == "select_external":
            acts.append(Act.SELECT_EXTERNAL)
        elif k == "compare_runs":
            acts.append(Act.COMPARE_RUNS)
        elif k == "evaluate_by_splits":
            acts.append(Act.EVALUATE_BY_SPLITS)
        elif k == "describe_external":
            acts.append(Act.SHOW_EXTERNAL if getattr(session, "external", None) is not None
                        else Act.NAME_PUBLISHED_MODEL)
        elif k == "ask_about_method":
            acts.append(Act.ANSWER_METHOD)
        elif k == "ask_about_result":
            acts.append(Act.EXPLAIN_RESULT if getattr(session, "has_result", False)
                        else Act.NO_RESULT_YET)
        elif k == "out_of_scope":
            acts.append(Act.REFUSE)
    if Act.COMPARE_RUNS in acts:
        # the comparison follows any run this turn makes
        acts = [a for a in acts if a is not Act.COMPARE_RUNS] + [Act.COMPARE_RUNS]
    if Act.EVALUATE_BY_SPLITS in acts:
        # the evaluation by splits is of the analysis this turn runs, if it runs one: last
        acts = [a for a in acts if a is not Act.EVALUATE_BY_SPLITS] + [Act.EVALUATE_BY_SPLITS]
    if Act.PROPOSE_ROLES in acts or (Act.SELECT_EXTERNAL in acts and (
            getattr(session, "declaration", None) is not None
            or getattr(session, "pending", None))):
        # a selection re-runs the current declaration on the newly active release
        tail = [a for a in (Act.COMPARE_RUNS, Act.EVALUATE_BY_SPLITS) if a in acts]
        pos = acts.index(tail[0]) if tail else len(acts)
        acts.insert(pos, Act.COMPLETE)
    elif "other" in kinds:
        acts.append(Act.ASK)
    return acts


def planner_calls() -> int:
    """V4: the most model calls one run's planning loop can make (zero with the planner off)."""
    from . import analyst
    return analyst.MAX_CALLS if analyst.enabled() else 0


def step_budget(n_steps: int) -> int:
    """A multi-step turn may make two calls per step (an extraction and a
    report) on top of the turn's own budget, and V4's planning loop per run."""
    return MODEL_CALLS_PER_TURN + (2 + planner_calls()) * n_steps


def model_calls_in(acts: Sequence[Act]) -> int:
    """How many model calls a plan implies, counting the intent call that
    produced it and the report that follows a run."""
    n = 1  # TYPE_MESSAGE
    n += sum(1 for a in acts if SPECS[a].needs_model)
    if Act.COMPLETE in acts:
        n += 1  # WRITE_REPORT if the completion runs, else WORD_QUESTION: one or the other
    return n


def check(session: Any, acts: Sequence[Act]) -> List[str]:
    """Violations of the action set's own rules; empty when the plan is legal."""
    bad: List[str] = []
    phase = getattr(session, "phase", None)
    for a in acts:
        spec = SPECS.get(a)
        if spec is None:
            bad.append(f"unknown act {a!r}")
            continue
        if phase is not None and phase not in spec.allowed_in and a not in (
                Act.COMPLETE, Act.ASK):
            bad.append(f"{a.value} is not allowed in phase {phase.value}")
    if model_calls_in(acts) > MODEL_CALLS_PER_TURN:
        bad.append(f"the plan implies {model_calls_in(acts)} model calls; the budget is "
                   f"{MODEL_CALLS_PER_TURN}")
    return bad


def registry_table() -> List[Dict[str, str]]:
    """The action set as rows, for documentation and for the paper's appendix."""
    return [{"act": s.act.value, "proposer": s.proposer,
             "verified by": s.verifier,
             "allowed in": ", ".join(p.value for p in s.allowed_in)}
            for s in SPECS.values()]
