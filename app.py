"""Gradio web UI for the BregSurv agent (V3).

Entry point for three deployment targets:
  * Local self-host (`python app.py` -> http://localhost:7860).
  * Docker container.
  * HuggingFace Space (HF picks up ``app.py`` at the repo root).

WHAT CHANGED FROM V2, AND WHY THE OLD CONTROLS ARE GONE RATHER THAN MOVED.

The previous UI asked the analyst to choose the study type, the form of the
external information, and the eta grid. Under V3 none of those is a choice:

  * the study design is DECLARED and then confirmed against the data, so a
    dropdown offering it would give a wrong claim somewhere to live;
  * the form of the external information is READ off the external object;
  * the eta grids are fixed in run_candidates.R and tuned against the two real
    cohorts. That file says in as many words that thinning them degrades the
    selection this tool performs. Exposing them as a slider invites exactly
    that.

Keeping them would have made the interface contradict the method.

THE SHAPE OF THE INTERACTION. decide, run, disclose.

  1. data in -> profile -> a short message and the numbered list, for anyone
     who prefers to answer by number. No model is called.
  2. one message -> typed by the model (M1: is this a declaration, a question,
     a description of external information, something out of scope) -> the
     roles the analyst stated are extracted (boundary 1) -> what they left out
     is settled by a deterministic rule wherever the data leaves one
     possibility (`declaration.complete`) -> verified against the data -> and
     if nothing is left to ask, the fit runs at once, bound to the hash of
     what verify saw.
  3. the report opens with the consequence card and a table of where each
     role came from. A wrong inference is corrected by one more message.

The analyst is asked only what neither the request nor the data can settle:
a column the file lacks, an event column among several, a form of external
information that cannot be typed -- and the time-zero question, which cannot
be read off a one-row-per-subject table and which the gate refuses without;
it is a checkbox beside the upload so a careful analyst still runs in one shot.
There is no approval step and no Run button.

Environment variables:

  OPENAI_API_KEY               LLM auth (only needed for the two optional
                               boundaries; the analysis runs without it).
  SURVBREGDIV_MODEL_ENDPOINT   OpenAI-compatible base URL.
  SURVBREGDIV_MODEL_NAME       Model identifier.
  DEPLOYMENT_MODE              ``local`` (default) or ``demo``.
  SURVBREGDIV_RSCRIPT          Override Rscript path.
  SURVBREGDIV_R_SCRIPTS        Override the R-script directory.
"""
from __future__ import annotations

import contextvars
import json
import threading
import time
import math
import re
import os
import tempfile
import traceback
from pathlib import Path
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

# Monkey-patch gradio_client to fix a known bug where its JSON-schema walker
# chokes on a boolean `additionalProperties`. Fixed upstream in
# gradio_client >= 1.4.1, but Gradio 4.44 pins gradio_client ~= 1.3.
import gradio_client.utils as _gc_utils

_orig_get_type = _gc_utils.get_type


def _safe_get_type(schema):
    if not isinstance(schema, dict):
        return "Any"
    return _orig_get_type(schema)


_gc_utils.get_type = _safe_get_type
_orig_json_to_pytype = _gc_utils._json_schema_to_python_type


def _safe_json_to_pytype(schema, defs=None):
    if not isinstance(schema, dict):
        return "Any"
    return _orig_json_to_pytype(schema, defs)


_gc_utils._json_schema_to_python_type = _safe_json_to_pytype

import gradio as gr  # noqa: E402
import pandas as pd  # noqa: E402

from bregsurv_agent import ablation, actions, analyst, boundary, external, fewshot, guards, intent, knowledge, memory, pipeline, textmatch  # noqa: E402
from bregsurv_agent.state import Phase, Session  # noqa: E402
from bregsurv_agent.declaration import (  # noqa: E402
    DeclarationError, complete, from_dictionary, parse_reply, render_question,
    verify)
from bregsurv_agent.rbridge import _run_r  # noqa: E402

HERE = Path(__file__).resolve().parent

# Progress of the current turn, shown in the chat while the turn runs.
_PROGRESS: "contextvars.ContextVar[Optional[List[str]]]" = contextvars.ContextVar("progress", default=None)
# the conversational reply as it streams, shown in place of the progress steps
_PARTIAL: "contextvars.ContextVar[Optional[List[str]]]" = contextvars.ContextVar("partial", default=None)


def _step(text: str) -> None:
    steps = _PROGRESS.get()
    if steps is not None and (not steps or steps[-1] != text):
        steps.append(text)
DEMO_DIR = HERE / "demo"
DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "local").lower()
DEFAULT_ENDPOINT = os.environ.get("SURVBREGDIV_MODEL_ENDPOINT",
                                  "https://api.openai.com/v1")
DEFAULT_MODEL = os.environ.get("SURVBREGDIV_MODEL_NAME", "gpt-4o-mini")
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")

DEMO_COHORT = DEMO_DIR / "kidney_cohort.csv"
DEMO_COEFS = DEMO_DIR / "registry_coefficients.csv"

# THE EXAMPLE IS A SENTENCE, NOT A DROPDOWN. The cohort is already loaded and
# the question already asked when the page opens, so what a first-time visitor
# needs is not a data picker -- it is one plausible thing to say. Tab fills this
# in. It is deliberately written the way a clinician writes: the columns named
# in passing, five of the eight covariates asked for, the registry model
# mentioned without any statistical vocabulary, and no instruction about method.
EXAMPLE_QUERY = (
    "We have a kidney transplant cohort. Follow-up is in followup_days, and "
    "died is 1 when the patient died during follow-up. Please adjust for age, "
    "bmi, egfr, hgb, albumin, dialysis_yrs, donor_age and cold_ischemia. We also "
    "have published coefficients from a larger registry model and would like "
    "to borrow from them if that helps."
)

# Tab in an empty message box fills the example. Bound with capture so it beats
# the browser's own focus handling, and it writes through the native value
# setter so Svelte sees the change -- assigning `.value` directly does not
# notify the framework and the box looks filled while the state stays empty.
_TAB_AUTOFILL_JS = """
() => {
  const EXAMPLE = %s;
  document.addEventListener('keydown', (e) => {
    const ta = e.target;
    if (ta && ta.tagName === 'TEXTAREA' && ta.closest('#msg_in')
        && e.key === 'Tab' && ta.value.trim() === '') {
      e.preventDefault();
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, EXAMPLE);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }, true);
}
""" % json.dumps(EXAMPLE_QUERY)

INTRO_MD = """
# BregSurv — survival analysis that borrows from published models

Load a cohort and, if you have one, a published model or another cohort's
records. Then say in plain words what you want. The agent reads your request,
checks how well the published model fits your data, plans which analyses are
worth fitting, and lets cross-validation pick the final model. Every number
comes from the R estimator library, and the `repro.R` it produces reruns the
analysis without the language model.
"""


# --------------------------------------------------------------------------
# Data intake
# --------------------------------------------------------------------------
def _banner() -> str:
    """What actually happens to an uploaded file. Not a prohibition.

    The old banner said uploads were DISABLED and warned that tool arguments
    transit the LLM provider. Under V3 neither half is true: uploads are allowed, and the model sees column NAMES and one
    sentence -- measured at 175 prompt tokens -- never a row. Telling people a
    danger that has moved is worse than telling them nothing, because they stop
    reading the banner that matters.
    """
    if DEPLOYMENT_MODE == "demo":
        return (
            "<div style='background:#fff8e1;color:#795548;padding:10px 14px;"
            "border-radius:6px;border:1px solid #ffe082;'>"
            "<b>Public demo.</b> Your file is uploaded to this Space's temporary "
            "storage on HuggingFace and deleted when your session ends. It is "
            "never sent to a language model — the model sees your column "
            "<i>names</i> and your one-sentence request, nothing else. Even so, "
            "this is a third-party host: for identifiable patient data, run it "
            "locally instead."
            "</div>")
    return (
        "<div style='background:#e8f5e9;color:#2e7d32;padding:10px 14px;"
        "border-radius:6px;border:1px solid #a5d6a7;'>"
        "<b>Running locally.</b> Your data stays on this machine. The model, if "
        "one is configured, sees column names and your request — never a row."
        "</div>")


def _purge(session) -> None:
    """Delete everything this session put on disk. Never the shipped example.

    THE BANNER MAKES A PROMISE AND THIS IS WHERE IT IS KEPT. It tells a
    visitor their file is deleted when the session ends, and a promise about
    someone else's clinical data is not something to leave to a framework's
    default temp handling.

    Bound as the State's `delete_callback`, which Gradio invokes with the state
    value when a session is cleaned up. `demo.unload` is deliberately NOT used:
    it receives no session argument, so it cannot know which files to remove,
    and a cleanup hook that cleans nothing is worse than none -- it reads like
    the promise is kept.

    Only paths WE caused to exist are recorded: the copy Gradio makes of an
    upload, and the artifact directory a run produced. The example cohort ships
    with the app and is guarded against explicitly -- deleting it would break
    the next visitor rather than protect this one.
    """
    if not isinstance(session, Session):
        return
    import shutil
    for path in session.temp:
        try:
            q = Path(path)
            if not q.exists() or q == DEMO_DIR or DEMO_DIR in q.parents:
                continue
            if q.is_dir():
                shutil.rmtree(q, ignore_errors=True)
            else:
                q.unlink()
        except OSError:
            pass


def _ours(*paths) -> List[str]:
    """The subset of `paths` this session is responsible for deleting."""
    out = []
    for q in paths:
        if q and DEMO_DIR not in Path(q).parents:
            out.append(q)
    return out


def _upload_path(f) -> Optional[str]:
    if f is None:
        return None
    p = getattr(f, "name", None) or (f if isinstance(f, str) else None)
    return p if p and Path(p).exists() else None


def _cohort_header(data_path: Optional[str]) -> Optional[List[str]]:
    """The column names of a delimited cohort file, from its first line; None for
    other formats. Only the model-free reader of an external file uses them, to
    recognise another cohort's records by their shared columns."""
    if not data_path or Path(data_path).suffix.lower() not in (".csv", ".tsv", ".txt"):
        return None
    try:
        with open(data_path, encoding="utf-8", errors="replace") as fh:
            line = fh.readline().rstrip("\r\n")
        sep = "\t" if "\t" in line else ","
        return [c.strip().strip('"') for c in line.split(sep)] or None
    except OSError:
        return None


def _read_external(path: Optional[str], endpoint: str = "", model: str = "",
                   api_key: str = "", use_model: bool = True,
                   cohort_columns: Optional[List[str]] = None):
    """M5: any external-information file -> one ExternalObject, or a refusal.

    The shipped demo file and the no-model path go through the heuristic
    (recognisable headers, or a two-column table); an upload with a model
    configured goes through the constrained assignment call. Returns
    (object | None, refusal reasons | None).
    """
    if not path:
        return None, None
    client = None
    if use_model and (api_key or "localhost" in (endpoint or "")):
        client = _client(endpoint, api_key)
    try:
        return external.read_external(path, client=client, model=model,
                                      run_r=_run_r, cohort_columns=cohort_columns), None
    except external.ExternalRefusal as exc:
        return None, exc.reasons
    except Exception as exc:                      # a reader bug is still a refusal
        return None, [{"code": type(exc).__name__,
                       "message": f"the file could not be read: {exc}"[:300]}]


def _data_expr_for(path: str) -> str:
    """How run_candidates.R will address the table it loads from this file."""
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in ("rda", "rdata"):
        return "D"          # by convention for the .rda path; see load_any
    # load_any names a flat file after itself, with make.names applied
    stem = Path(path).stem
    safe = "".join(ch if (ch.isalnum() or ch == "." or ch == "_") else "."
                   for ch in stem)
    if not safe[:1].isalpha():
        safe = "X" + safe
    return safe


# --------------------------------------------------------------------------
# Step 1 — profile the data and ask
# --------------------------------------------------------------------------
def _link_external(ext, prof) -> None:
    """The linkage from the profile's own name matching, and the catalogue pin."""
    names = [c["name"] for c in prof.get("columns", [])]
    keys = list(ext.terms) if ext.terms else list(
        (ext.individual_data or {}).get("columns", []))
    ext.linkage = {"matched": [k for k in keys if k in names],
                   "unmatched": [k for k in keys if k not in names]}
    hit = memory.match_file(ext.provenance.get("sha256"))
    if hit:
        ext.provenance["catalogue"] = hit
        ext.notes.append(f"byte-identical to the published file {hit['file']} of {hit['id']}")


def add_external(coef_uploaded=None, session=None, history=None, endpoint: str = "",
                 model: str = "", api_key: str = ""):
    """M2: a further external file into the SAME session. Read by M5, linked
    to the cohort, added to the loaded releases and made the active one; the
    declaration, if any, stays. Returns (chat, session)."""
    history = list(history or [])
    if not session or session.phase is Phase.EMPTY:
        history.append([None, "Load a cohort first."])
        return history, session
    path = _upload_path(coef_uploaded)
    if not path:
        history.append([None, "Choose an external file first."])
        return history, session
    ext, refusal = _read_external(path, endpoint, model, api_key,
                                  cohort_columns=[c["name"] for c in (session.profile or {}).get("columns", [])] or None)
    if ext is not None:
        _link_external(ext, session.profile)
        session = session.with_external(ext)
        session = _take_calls(session)
        session = replace(session, temp=list(session.temp) + _ours(path))
        history.append([None, "I have read another external file:\n\n```\n"
                              + "\n".join(ext.card()) + "\n```\n\nLoaded external files: "
                              + ", ".join(f"`{n}`" for n in session.externals)
                              + f" (active: `{session.external_name}`). Say which to use, "
                                "or ask me to run with each and compare."])
    else:
        session = session.with_external(None, refusal)
        history.append([None, "**The external file could not be used:**\n"
                              + "\n".join(f"- {r['message']}" for r in (refusal or []))])
    return history, session


def _plain_external(ext) -> str:
    """One or two plain sentences on the external information and how it lines up."""
    if ext.individual_data:
        d = ext.individual_data
        out = (f"You also gave another cohort's patient records "
               f"({len(d.get('columns', []))} columns), which I can borrow from.")
    else:
        n = len(ext.terms or {})
        out = f"You also gave a published model with {n} coefficients"
        extra = []
        if ext.Q is not None:
            extra.append("their covariance")
        if ext.baseline_hazard:
            extra.append("a baseline hazard")
        if extra:
            out += " and " + " and ".join(extra)
        out += "."
        if ext.provenance.get("converted_from") == "hazard_ratio":
            out += " They were given as hazard ratios, so I took their logarithms."
    L = ext.linkage or {}
    um = L.get("unmatched") or []
    if L.get("matched") is not None:
        if um:
            names = ", ".join(f"`{u}`" for u in um)
            out += (f" {len(L['matched'])} of them match columns in your data; "
                    f"{names} {'is' if len(um) == 1 else 'are'} not in your data "
                    "and will be left out.")
        else:
            out += " All of them match columns in your data."
    return out


def start_session(uploaded=None, coef_uploaded=None, endpoint: str = "",
                  model: str = "", api_key: str = "", test_uploaded=None):
    """Profile the cohort, read the external information (M5), post the
    opening message. The model is involved only for an uploaded external file,
    and only to say which column holds what.

    Called with no arguments when the page opens, which is what makes the
    example cohort the default state rather than something to go and select. An
    upload replaces it.

    `test_uploaded` is the analyst's OWN test file, supplied
    explicitly and never drawn by the agent: every fitted model is scored on
    it once and the report carries the numbers; the selection never reads
    them. Only meaningful with an uploaded cohort.
    """
    try:
        data_path = _upload_path(uploaded)
        test_path = _upload_path(test_uploaded) if data_path else None
        if data_path:
            ext, ext_refusal = _read_external(_upload_path(coef_uploaded),
                                              endpoint, model, api_key,
                                              cohort_columns=_cohort_header(data_path))
        else:
            data_path = str(DEMO_COHORT)
            # the shipped two-column file needs no model to be read
            ext, ext_refusal = _read_external(str(DEMO_COEFS), use_model=False)
        coefs = dict(ext.terms) if ext is not None and ext.terms else None

        data_expr = _data_expr_for(data_path)
        payload: Dict[str, Any] = {"data_path": data_path,
                                   "data_expr": data_expr}
        if coefs:
            payload["external_beta_inline"] = coefs
        prof = _run_r("profile_columns.R", payload)
        if prof.get("status") != "ok":
            return (([[None, "**The file could not be read.**\n\n"
                             f"{prof.get('message', 'unknown error')}"]]), None) + _EMPTY

        # the linkage, from the profile's own name matching, and the
        # catalogue pin (component 4): a file byte-identical to a catalogued
        # release is pinned to it, whatever anyone said about it
        if ext is not None:
            _link_external(ext, prof)
        # component 4: the declaration the analyst gave for this same file
        # before, if memory is on and this is not the shipped example
        is_example = data_path == str(DEMO_COHORT)
        data_sha = pipeline._fingerprint(data_path)["sha256"]
        remembered = (None if is_example
                      else memory.Store().recall_declaration(data_sha))
        # component 3: one typed object carries the analysis between turns;
        # its phase and the state line the model sees are derived from it
        session = Session().with_profile(
            data_path, data_expr, prof,
            # what a data dictionary settles on its own, if one is present
            # and it leaves no choice; `complete` uses it for the outcome
            # columns the analyst does not name
            dict_decl=from_dictionary(prof),
            external=ext, external_refusal=ext_refusal,
            temp=_ours(_upload_path(uploaded), _upload_path(coef_uploaded),
                       test_path),
            # M5's model call, if any, joins the run's provenance
            model_calls=boundary.call_log(clear=True),
            data_sha256=data_sha, remembered=remembered,
            # : the test file travels with the session and is attached
            # to the declaration when it is settled; it raises no question
            test_data_path=test_path,
            test_data_expr=_data_expr_for(test_path) if test_path else None)
        # The opening is plain language: what was loaded and what to do next.
        # The numbered form is not posted here; numbered replies still work,
        # and an item is asked only when the agent actually needs it.
        what = ("a synthetic kidney transplant cohort" if is_example
                else f"**{Path(data_path).name}**")
        head = (f"I have loaded {what}: {prof['n_rows']} patients and "
                f"{prof['n_columns']} columns.")
        if ext is not None:
            head += " " + _plain_external(ext)
        elif ext_refusal:
            head += (" The external file could not be used: "
                     + " ".join(r["message"] for r in ext_refusal)
                     + " I will analyse your cohort alone unless you upload a "
                       "corrected file.")
        if test_path:
            head += (f" Your test file **{Path(test_path).name}** will be used "
                     "only to score the models, never to choose one.")
        if remembered:
            head += (" I remember how you described this file last time and "
                     "will reuse that for anything you leave out.")
        head += ("\n\nTell me in your own words what you want to analyse: "
                 "which column is the follow-up time, which one records the "
                 "event, and what to adjust for.")
        if is_example:
            head += (" You can try the example below the message box, or drop "
                     "your own files into the message box to use them instead.")
        return ([[None, head]], session) + _EMPTY
    except Exception as exc:
        return (([[None, "**The file could not be read.**\n\n"
                         f"{type(exc).__name__}: {exc}"]]), None) + _EMPTY


# --------------------------------------------------------------------------
# Step 2 — type the message, settle the roles, verify, and RUN
# --------------------------------------------------------------------------
_NUMBERED = ("1", "2", "3", "4", "5", "6", "7")


_ITEM_LABEL = {"0": "the matched-set column", "1": "the follow-up time column",
               "2": "the event column", "3": "the value that means the event occurred",
               "4": "the covariates", "6": "the time-zero question", "7": "the time scale"}


# time_is_event: one column named as both; the time is usually the one the
# analyst wrote, so the event is the item to correct (simulation prompt search,
# 2026-09-30: pointing at item 1 had the analyst re-send the same time column)
_ITEM_OF_REFUSAL = {"covariate": "4", "outcome_used_as_covariate": "4",
                    "stratum_used_as_covariate": "4",
                    "time_is_event": "2", "time": "1",
                    "event": "2", "degenerate_outcome": "2", "competing_risks": "2",
                    "matched": "0", "stratum": "0", "time_zero": "6", "discrete": "7"}


def _refusal_family(code: str) -> str:
    """The item a gate refusal is about, from its code's first word(s)."""
    if code in _ITEM_OF_REFUSAL:
        return code
    if code.startswith("time_zero"):
        return "time_zero"
    if code.startswith("matched_set"):
        return "matched"
    return code.split("_")[0]


def _same_column(prof, kind: str, a, b) -> bool:
    """Whether two answers for a role name the same column (an index into the
    offered list, or a name); an answer that resolves to nothing is compared
    as written."""
    from bregsurv_agent.declaration import _resolve_one

    def res(x):
        try:
            return _resolve_one(prof, kind, str(x))
        except Exception:
            return str(x).strip()
    return res(a) == res(b)


def _correct_by_number(exc) -> str:
    """The last line of a refusal: which numbered item to reply with."""
    item = getattr(exc, "item", None)
    if item in _ITEM_LABEL:
        return f"Reply by number to correct it: item {item}, {_ITEM_LABEL[item]}."
    return "Reply by number to correct it."


def _answers_from_reply(text: str) -> Dict[str, str]:
    """Read a numbered reply. Deterministic; the model is not involved.

    Accepts `1) followup_days` / `1. followup_days` / `1 followup_days`, in any
    order, and ignores anything it does not recognise rather than guessing.
    """
    key = {"0": "stratum", "1": "time", "2": "event", "3": "event_value",
           "4": "covariates", "5": "external_data_expr", "6": "time_zero",
           "7": "discrete"}                      # : the time scale
    out: Dict[str, str] = {}
    for line in text.splitlines():
        t = line.strip()
        if len(t) > 1 and t[0] in _NUMBERED + ("0",):
            rest = t[1:].lstrip(").:- \t")
            if rest:
                out[key[t[0]]] = rest.strip()
    return out


# the seven result outputs, empty: nothing was fitted on this turn (the
# seventh, repro_diskd.py, exists only on the discrete-time row -- )
# V4: an eighth result slot, the files of an evaluation by repeated splits
_EMPTY = (None, None, None, None, None, None, None, None)
_ROLE_KEYS = ("time", "event", "event_value", "covariates", "time_zero",
              "stratum", "discrete")


def _answers_of(decl) -> Dict[str, str]:
    """A declaration back in parse_reply's vocabulary, as the base for an edit."""
    # : the time scale, in the words item 7 accepts; "no" only when
    # it was answered no (a run on which the question never arose carries
    # nothing, so nothing is remembered as an answer)
    if getattr(decl, "discrete", False):
        disc = (f"index {decl.n_intervals}" if decl.time_is_interval_index
                else f"{decl.interval_width:g} {decl.n_intervals}")
    elif (any("item 7 answered no" in n for n in (decl.notes or []))
          and not str((decl.sources or {}).get("discrete", "")).startswith("default:")):
        disc = "no"
    else:
        # the continuous-time DEFAULT is not an answer: nothing is remembered
        # or carried into an edit, so a later "7) 7 53" is not overriding a
        # statement the analyst never made
        disc = None
    raw = {"time": decl.time_col, "event": decl.event_col,
           "event_value": decl.event_value,
           "covariates": ", ".join(decl.covariates),
           "stratum": decl.stratum_col,
           "external_data_expr": decl.external_data_expr,
           "time_zero": decl.covariates_time_zero,
           "discrete": disc}
    return {k: v for k, v in raw.items() if v}


def _client(endpoint, api_key):
    from openai import OpenAI
    return OpenAI(base_url=endpoint, api_key=api_key or "EMPTY")


# the backing check itself lives with the other verifiers of model output
# (boundary.backed_roles), so the live check measures the same predicate
_backed_roles = boundary.backed_roles


def _log_action(session: Session, **rec) -> Session:
    """The typed action log (component 3). Every routing decision, in order."""
    return session.log(**rec)


_NO_COLUMN = re.compile(r"there is no column called '([^']+)'")


def _note_missing_column(session: Session, exc: Exception) -> Session:
    """Record a column the analyst named that the file does not have (the
    refusal by name), so the settled declaration can say what became of it."""
    m = _NO_COLUMN.search(str(exc))
    return _log_action(session, route="missing_column", name=m.group(1)) if m else session


def _missing_columns(session: Session) -> List[str]:
    out = []
    for a in session.actions or []:
        if isinstance(a, dict) and a.get("route") == "missing_column" and a.get("name") not in out:
            out.append(a["name"])
    return out


# A column the analyst named is not in the file and the run stopped on it; a
# reply such as "leave it out" removes that column from the covariates the
# reading settled and nothing else (the session-(b) recording, 2026-10-04: the
# plain reply re-asked the same question, because only a numbered list could
# remove the name).
_DROP_WORDS = re.compile(r"\b(leave (it|that|this|them|those)( one| column)?s? out|leave out|drop (it|that|this|them)|"
                         r"remove (it|that|this|them)|without (it|that|them)|skip (it|that|them)|"
                         r"ignore (it|that|them)|not needed|don'?t (need|use) (it|that|them))\b", re.I)


def _drop_missing_reply(msg: str, session, given: Dict[str, str]) -> Dict[str, str]:
    gone = _missing_columns(session)
    cov = given.get("covariates")
    if not gone or not cov or not _DROP_WORDS.search(msg or ""):
        return {}
    names = [c.strip() for c in str(cov).split(",") if c.strip()]
    kept = [c for c in names if c not in gone]
    if len(kept) == len(names) or not kept:
        return {}
    return {"covariates": ", ".join(kept)}


def _take_calls(session: Session) -> Session:
    return session.take_calls(boundary.call_log(clear=True))


def _external_reply(session, it, client=None, model: str = "",
                    msg: str = "") -> str:
    ext = session.external
    form = ""
    if it.external_form and it.external_form != "unknown":
        form = it.external_form.replace("_", " ")
    if ext is not None:
        return ("This is the external information I have read:\n\n```\n"
                + "\n".join(ext.card()) + "\n```\n\nIt is borrowed from only "
                "if that lowers the held-out loss; the report shows the "
                "comparison either way.")
    why = ""
    if session.external_refusal:
        why = ("\n\nThe last file was refused: "
               + "; ".join(r["message"] for r in session.external_refusal))
    # component 4: no file yet -- does the message name a published model the
    # catalogue knows? One constrained call; ids and evidence are verified.
    if client is not None and msg.strip():
        try:
            prop = memory.propose_model(client, model, msg)
        except Exception as exc:              # memory must never break a turn
            prop = {"matches": [], "error": f"{type(exc).__name__}: {exc}"}
        if prop.get("matches"):
            cards = []
            for m in prop["matches"]:
                e = memory.entry(m["id"])
                if e is not None:
                    cards.append("\n".join(memory.render_entry(e)))
            return ("You seem to mean a published model this system knows of "
                    f"(you wrote \"{prop['matches'][0]['evidence']}\"):\n\n```\n"
                    + "\n\n".join(cards) + "\n```\n\nI do not download it. "
                    "Obtain the file as described, reduce it to one coefficient "
                    "per variable of your own cohort, upload it on the left and "
                    "press *Use my file instead*; I will say what I read before "
                    "anything is fitted, and a file identical to the published "
                    "one is recognised by its checksum." + why)
    return ("To use external information, upload the file on the left -- "
            "coefficients (with or without a covariance or a baseline hazard), "
            "or another cohort's rows; csv, xlsx, json, rds -- and press "
            "*Use my file instead*. I will say what I read before anything is "
            "fitted" + (f" (you mentioned {form})." if form else ".") + why)


def _result_reply(session, question: str = "", client=None,
                  model: str = "") -> str:
    """M4: a question about a report that exists is answered by `explain`,
    under boundary 2's rules; a draft that breaks them is dropped and said so."""
    if not session.has_result:
        return ("There is no result yet. Tell me which columns are the "
                "follow-up time and the event, and which columns to adjust "
                "for, and I will run the analysis.")
    if client is None or not question.strip():
        return ("The report above holds every number; candidates.json lists "
                "every method that was tried, and repro.R re-runs the whole "
                "analysis.")
    from bregsurv_agent import report_v3
    res = session.result
    c = res.candidates
    sel = c.get("selected") or {}
    ok = [k for k in c.get("candidates", []) if k.get("status") == "ok" and k.get("loss") is not None]
    by = {k["key"]: k for k in ok}
    best = sel.get("loss")

    def _vs(key, name):
        k = by.get(key)
        if k is None or best is None or key == sel.get("key"):
            return None
        if abs(k["loss"] - best) <= 5e-4 * abs(best):
            return f"It did about as well as {name}."
        return f"It did better than {name}."
    facts = [f"The analysis tried {len(ok)} approaches: "
             + "; ".join(_plain_label(k["key"]) for k in ok) + ".",
             "It tried each approach while repeatedly setting part of the patients aside, "
             "and checked how well each one anticipated what happened to those patients.",
             "It kept [selected_label], because that did best in this check."]
    facts += [x for x in (_vs("internal", "using your data alone"),
                          _vs("external", "using the external model as it is")) if x]
    k0 = sel.get("key", "")
    if report_v3.selected_borrows_nothing(c):
        facts.append("The kept approach was given a borrowing weight of zero, so in the end it "
                     "borrows nothing from the external information: it uses your data alone.")
    elif not (k0.startswith("internal") or k0.startswith("external")):
        facts.append("So borrowing from the external information helped.")
    facts += _more_facts(c, question)
    facts.append("The report does not assess calibration and says nothing about how well any approach "
                 "is calibrated.")
    # the short form: the clauses after the first comma made the answer read
    # "The chosen approach, the approach of combining ..., with ..., did better"
    refs = {"selected_label": _plain_label(k0).split(",")[0]}
    out = boundary.explain(client, model, question, {
        "references": refs, "result": c, "declaration": res.declaration,
        "plain_facts": facts})
    if out.get("answer"):
        a = out["answer"].strip()
        a = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), a)
        return a
    return ("I could not put that into words reliably. The PDF report has the "
            "full details; you can also ask the question another way.")


def _more_facts(c: Dict[str, Any], question: str) -> List[str]:
    """Plain-word facts the harness reads off the fitted objects for a follow-up question (V4,
    2026-10-05): which approach did worst, how the approaches did on the analyst's test file, what the
    report's tables hold, and, for a variable the question names, where the kept coefficient lies
    relative to the external model's and to your data's. No digit; the model decides what answers
    the question."""
    from bregsurv_agent import textmatch
    out: List[str] = []
    ok = [k for k in c.get("candidates", []) if k.get("status") == "ok" and k.get("loss") is not None]
    sel = c.get("selected") or {}
    if len(ok) > 2:
        worst = max(ok, key=lambda k: k["loss"])
        out.append(f"The approach that did worst in this check was {_plain_label(worst['key']).split(',')[0]}.")
    ho = [k for k in ok if (k.get("holdout") or {}).get("cindex") is not None]
    if c.get("test_data") and ho:
        best = max(ho, key=lambda k: k["holdout"]["cindex"])
        bl = _plain_label(best["key"]).split(",")[0]
        if best["key"] == sel.get("key"):
            out.append("On your separate test file, the kept approach also ranked patients best of all "
                       "the approaches tried.")
        else:
            out.append(f"On your separate test file, the approach that ranked patients best was {bl}; the "
                       "kept approach was chosen by the check on your own data, which never looked at the "
                       "test file.")
        out.append("The report has a table of every approach's results on your test file.")
    if c.get("coefficients"):
        out.append("The report has a table that lists, for every variable, the external model's "
                   "coefficient, the coefficient from your data alone, and the kept approach's.")
        names = [r["variable"] for r in c["coefficients"]]
        for v in textmatch.names_mentioned(question or "", names)[:3]:
            r = next(x for x in c["coefficients"] if x["variable"] == v)
            e, i, k = r.get("beta_external"), r.get("beta_internal"), r.get("beta_selected")
            if k is None or i is None:
                continue
            if not r.get("covered_by_external") or e is None:
                out.append(f"For {v}, the external model has no coefficient, so it was estimated from "
                           "your data alone.")
                continue
            if abs(k - i) < 1e-9:
                where = "is the same as the one from your data alone"
            elif abs(k - e) < 1e-9:
                where = "is the same as the external model's"
            elif min(e, i) <= k <= max(e, i):
                where = ("lies between the two, nearer the external model's" if abs(k - e) < abs(k - i)
                         else "lies between the two, nearer the one from your data alone")
            else:
                where = "lies outside the range of the two"
            sign = "agree in sign" if e * i > 0 else "differ in sign"
            out.append(f"For {v}, the external model's coefficient and the one from your data alone "
                       f"{sign}; the kept approach's coefficient {where}.")
    return out


def _compare_reply(session: Session) -> str:
    """The harness compares the two most recent runs; every number is its own."""
    from bregsurv_agent import compare
    if len(session.results) < 2:
        return ("There is only one analysis in this session so far; run a second "
                "(with another external file, or a changed declaration) and I will "
                "compare the two.")
    a, b = session.results[-2], session.results[-1]
    la = f"run {len(session.results) - 1}"
    lb = f"run {len(session.results)}"
    cmp = compare.compare_runs(a, b, la, lb)
    return cmp["text"] + ("\n\n<small>Every number above was taken from the two "
                          "fitted objects by the harness; no model wrote any of "
                          "them.</small>")


def _evaluate_by_splits(out, chat_msg, client, model: str, message: str = ""):
    """V4: the evaluation by repeated random splits the analyst asked for, of the
    analysis just run. The model reads the settings from the analyst's words once (policy
    `split_request`); `splits.validate` keeps only what the words support; the harness draws the
    splits, runs the same verified analysis on every one, and writes every number, the table, the
    box plots, the record and the replay script -- files of their own, never part of the report.
    `out` is the turn's outputs so far; the split files go in the last result slot and the run's
    own files stay where they are. The reply goes under `chat_msg` (None: a new line)."""
    from bregsurv_agent import splits
    history, _, session, *rest = out
    rest = (list(rest) + [None] * len(_EMPTY))[:len(_EMPTY)]

    def done(text, **log):
        history.append([chat_msg, text])
        return (history, "", _log_action(session, route="evaluate_by_splits", **log)) + tuple(rest)

    res = session.result
    if res is None:
        return done("There is no analysis to evaluate yet. Tell me which columns are the "
                    "follow-up time and the event, and which to adjust for; I will run the "
                    "analysis and then evaluate it on repeated splits.",
                    ran=False, why="no result")
    decl, plan = res.declaration, getattr(res, "plan", None)
    why = splits.declined_reason(decl, plan)
    if why:
        return done(f"**The evaluation by splits was not run.** {why}", ran=False, why=why)
    mode = "subsample" if decl.has_test_data else "split"
    secs, secs_src = splits.estimate_seconds(res)
    raw: Dict[str, Any] = {}
    if client is not None and (message or "").strip():
        try:
            raw = splits.read_request(client, model, message, mode, secs, secs_src,
                                      splits.workers_for(splits.MAX_SPLITS))
        except Exception as exc:          # a failed reading leaves the harness defaults
            session = _log_action(session, route="split_request_failed",
                                  error=f"{type(exc).__name__}: {str(exc)[:300]}")
        session = _take_calls(session)
    req = splits.validate(message or "", raw, mode)
    session = _log_action(session, route="split_request", request=req.as_dict(),
                          seconds_per_split=round(secs, 1), seconds_source=secs_src)
    outdir = tempfile.mkdtemp(prefix="bregsurv_splits_")
    session = replace(session, temp=list(session.temp) + [outdir])
    ext_kw = {k: v for k, v in (("external_beta_inline", res.external_beta_inline),
                                ("external_Q_inline", res.external_Q_inline),
                                ("external_baseline_inline", res.external_baseline_inline))
              if v}
    call = next((c for c in reversed(session.model_calls)
                 if c.get("name") == "split_request"), None)
    prov = {"session": session.to_provenance(), "analysis_config_sha256": res.config_sha256,
            "split_request_call": call,
            "analysis": {k: res.provenance.get(k) for k in
                         ("bregsurv_version", "bregsurv_build", "bregsurv_git_sha", "r_version")}}
    try:
        sr = splits.evaluate(res.data_path, res.data_expr, decl, req, outdir, plan=plan,
                             ext_kw=ext_kw, run_r=_run_r,
                             inner_seed=int(res.provenance.get("seed", 20260818)),
                             nfolds=int(res.provenance.get("nfolds", 5)),
                             nlambda=int(res.provenance.get("nlambda", 50)),
                             provenance=prov)
    except splits.SplitRefusal as exc:
        return done(f"**The evaluation by splits was not run.** {exc}", ran=False, why=str(exc))
    except Exception:
        detail = traceback.format_exc()[-1200:]
        return done("**The evaluation by splits did not run.** The analysis above stands; "
                    "nothing from the splits is reported.\n\n<details><summary>Technical "
                    f"detail</summary>\n\n```\n{detail}\n```\n</details>",
                    ran=False, why="error")
    rest[-1] = sr.paths
    return done(splits.reply_text(sr), ran=True, mode=req.mode, n_splits=req.n_splits,
                n_analysed=sum(1 for x in sr.record["splits"] if x.get("status") == "ok"),
                seed=sr.record["seed"], workers=sr.record["workers"], seconds=sr.seconds,
                files=sr.paths)


def _draw_km(out, chat_msg, by: Optional[str], evidence: str = ""):
    """V4: the Kaplan-Meier curve the analyst asked to see, of the analysis just run
    (or already run): pooled, by the declared strata, or by the column the analyst wrote (`by`,
    checked against the file). Redrawn into the report in place of the default one and shown in
    the chat; the harness draws it, the model only read the request."""
    history, _, session, *rest = out
    rest = (list(rest) + [None] * len(_EMPTY))[:len(_EMPTY)]

    def done(text, image=None, **log):
        history.append([chat_msg, text])
        if image:
            history.append([None, (image,)])
        return (history, "", _log_action(session, route="kaplan_meier", **log)) + tuple(rest)

    res = session.result
    if res is None or not session.temp:
        return done("The Kaplan-Meier curve is drawn with the analysis. Tell me which columns are "
                    "the follow-up time and the event, and I will run it and draw the curve.",
                    drawn=False, why="no result")
    cols = [c["name"] for c in (session.profile or {}).get("columns", [])]
    col = None
    if by:
        col = next((c for c in cols if c == by), None) or next(
            (c for c in cols if textmatch.mentions(by, c, cols)), None)
        if col is None:
            return done(f"Your data has no column called `{by}`, so the curve was not split by it.",
                        drawn=False, why="no such column", by=by)
    km = res.draw_km(Path(session.temp[-1]), group_col=col)
    if not km or km.get("status") != "ok":
        why = (km or {}).get("reason") or "the curve could not be drawn"
        return done(f"The Kaplan-Meier curve was not drawn: {why}.", drawn=False, why=why, by=col)
    by_txt = {"levels": f" by `{km.get('grouped_by')}`", "strata": " by stratum",
              "median": f" by `{km.get('grouped_by')}`, split at its median"}.get(km.get("grouping") or "", "")
    return done(f"Here is the Kaplan-Meier estimate of your cohort{by_txt}; it is also in the report.",
                image=km["png"], drawn=True, by=col, grouping=km.get("grouping"))


def _show_partial(text: str) -> None:
    box = _PARTIAL.get()
    if box is not None:
        box[0] = text or ""


def _chat_answer(client, model, msg, session, prof, history, notes: str = ""):
    """V4: the model's own answer to a message that is not an analysis request, or None
    (no model, or a draft the harness dropped). Returns (text or None, session)."""
    if client is None:
        return None, session
    earlier = [(u, b) for u, b in (history or [])[-6:] if isinstance(u, str) and isinstance(b, str)]
    try:
        r = boundary.chat_reply(client, model, msg, session.state_line(),
                                [c["name"] for c in (prof or {}).get("columns", [])],
                                earlier=[(u[:500], b[:800]) for u, b in earlier], notes=notes,
                                on_reply=_show_partial)
    except Exception as exc:
        r = {"reply": None, "dropped": f"{type(exc).__name__}: {str(exc)[:200]}"}
    session = _take_calls(session)
    session = _log_action(session, route="chat", used=bool(r.get("reply")), dropped=r.get("dropped"))
    return r.get("reply"), session


def _execute_steps(steps, session, history, msg, replies, client, prof, write_prose,
                   endpoint, model, api_key, tz_known):
    """M2's orchestrator: the verified steps, in order, each checked before
    the next; stop at the first that needs the analyst. Returns the nine
    outputs of the last run."""
    lead = "\n\n".join(replies + [
        "Plan: " + " -> ".join(
            f"{st['act']}" + (f" ({st['external']})" if st.get("external") else "")
            for st in steps)])
    history.append([msg, lead])
    last = (history, "", session) + _EMPTY
    n_calls_at_start = len(session.model_calls) - 2   # the intent and the plan calls count
    for k, st in enumerate(steps, 1):
        act = st["act"]
        if act == "select_external":
            session = session.select_external(st["external"])
            history.append([None, f"Step {k}: using **{st['external']}** as the "
                                  "external information."])
            # keep the outputs of a run already made this turn (as compare_runs and
            # explain_result do): under Qwen3 most plans end "... -> run ->
            # select_external", and returning _EMPTY here blanked the report,
            # trace and repro panels of the run that had just completed
            last = (history, "", session) + tuple(last[3:])
        elif act in ("run", "edit_and_run"):
            # A run step on a FRESH session takes its roles from the message
            # itself (boundary 1), exactly as a `declare_roles` turn would.
            # Until 2026-09-12 this branch answered "there is no declaration
            # yet; tell me which columns..." -- a dead end when the message
            # named every role: under Qwen3 the case-1 request ("follow-up
            # time is in followup_days, died is 1 if ...; a registry
            # published coefficients ...") was typed multi_step and planned
            # as select_external -> edit_and_run, and the agent stopped
            # without a fit (job 61023996). The roles the analyst wrote are
            # read; what is missing goes to `complete`, which asks.
            fresh = session.declaration is None and not session.pending
            given = (_answers_of(session.declaration) if session.declaration is not None
                     else dict(session.pending))
            sources = dict((session.declaration.sources if session.declaration is not None
                            else session.pending_sources) or {})
            if act == "edit_and_run" or fresh:
                _step("Finding the columns you named")
                ext = boundary.extract_roles(client, model, msg, prof,
                                                 *boundary.examples_for(msg, prof))
                session = _take_calls(session)
                backed, unbacked, how = _backed_roles(msg, prof, ext)
                for key, val in backed.items():
                    given[key], sources[key] = val, how[key]
                if unbacked:
                    session = _log_action(session, route="unbacked_names", dropped=unbacked)
            history.append([None, f"Step {k}: running with "
                                  f"**{session.external_name or 'no external information'}**."])
            out = _settle_and_run(session, history, None, given, sources, [], True,
                                  client, prof, write_prose, endpoint, model, api_key,
                                  tz_known)
            history, _, session, *rest = out
            last = (history, "", session) + tuple(rest)
            if rest and rest[0] is None:
                return last          # a question or a refusal: stop here
        elif act == "compare_runs":
            history.append([None, f"Step {k}:\n\n" + _compare_reply(session)])
            last = (history, "", session) + tuple(last[3:])
        elif act == "explain_result":
            history.append([None, f"Step {k}: " + _result_reply(session, st["evidence"],
                                                                 client, model)])
            session = _take_calls(session)
            last = (history, "", session) + tuple(last[3:])
    used = len(session.model_calls) - n_calls_at_start
    session = _log_action(session, route="turn_calls", model_calls=used,
                          budget=actions.step_budget(len(steps)), steps=len(steps))
    return (history, "", session) + tuple(last[3:])


def _unbacked_note(unbacked: Dict[str, Any], prof: Dict[str, Any]) -> Optional[str]:
    """One line telling the analyst which of the file's columns the reading
    named that they did not write, and that were therefore left out (hard set
    H046, 2026-09-15: the analyst wrote `hla_mismatch_count`, the model read
    the file's `hla_mismatch`, the check removed it and the fit ran on four of
    the five covariates with nothing said). A name that is not a column of the
    file is not reported: it was never a candidate."""
    cols = {c["name"] for c in (prof or {}).get("columns", [])}
    named = [c for c in (unbacked or {}).get("covariates") or [] if c in cols]
    if not named:
        return None
    return ("The reading also named " + ", ".join(f"`{c}`" for c in named[:12])
            + (" and others" if len(named) > 12 else "")
            + ", which you did not write, so " + ("it was" if len(named) == 1 else "they were")
            + " left out; say so if " + ("it" if len(named) == 1 else "any of them")
            + " should enter.")


def _settled(answers: Dict[str, str], sources: Dict[str, str]) -> str:
    """What is settled so far, with its source, before the open questions."""
    label = {"time": "follow-up time", "event": "event indicator",
             "event_value": "event value", "covariates": "predictors",
             "time_zero": "known at time zero", "stratum": "strata",
             "discrete": "time scale"}
    lines = []
    for k in _ROLE_KEYS:
        if answers.get(k):
            v = answers[k]
            if k == "covariates" and v in ("A", "B"):
                v = f"preset {v}"
            if k == "discrete" and str(v).strip().lower() == "no":
                v = "continuous"
            lines.append(f"  {label[k]:<20} {v}   <- {sources.get(k, 'stated')}")
    if not lines:
        return ""
    return "So far:\n\n```\n" + "\n".join(lines) + "\n```\n\n"


def submit_answer(msg: str, history, session, endpoint, model, api_key,
                  write_prose=False, tz_known=False):
    """Read one message and go as far as it allows: settle, verify, run.

    Returns the eleven outputs the message box is bound to: the chat, the
    cleared box, the session, and the eight result outputs (empty unless a fit
    ran on this turn; the eighth holds the files of an evaluation by repeated
    splits, when one was asked for).
    """
    history = list(history or [])
    if not session or session.phase is Phase.EMPTY:
        history.append([msg, "Load a dataset first."])
        return (history, "", session) + _EMPTY
    if not (msg or "").strip():
        return (history, "", session) + _EMPTY

    prof = session.profile
    model_ok = bool(api_key) or "localhost" in (endpoint or "")
    given: Dict[str, str] = dict(session.pending)
    sources: Dict[str, str] = dict(session.pending_sources)
    replies: List[str] = []
    used_model = False
    session = session.start_turn(msg)
    try:
        answers = _answers_from_reply(msg) or _drop_missing_reply(msg, session, given)
        if answers:
            # a numbered reply never reaches the model
            if not given and session.declaration is not None:
                # after a run (nothing pending): the current declaration is
                # the base and only the numbered items change -- how an
                # analyst asks for the discrete row ("7) 7 53") or swaps one
                # role after seeing the report
                given = _answers_of(session.declaration)
                sources = dict(session.declaration.sources or {})
            old_event = given.get("event")
            for k, v in answers.items():
                given[k], sources[k] = v, "reply"
            # A reply that changes the event column, and says nothing about
            # the value, leaves a value that was stated for ANOTHER column:
            # "the event column is died (1 = death)" on a file whose event
            # column is `alive`, corrected by "2) alive", ran with alive = 1
            # (rubric task H045, 2026-10-02). A value the 0/1 rule filled is
            # filled again for the new column; any other is asked (item 3).
            if ("event" in answers and "event_value" not in answers and old_event
                    and not _same_column(prof, "event", answers["event"], old_event)
                    and given.get("event_value")):
                was, how = given.pop("event_value"), str(sources.get("event_value") or "")
                if how.startswith("inferred") or how.startswith("default"):
                    sources.pop("event_value", None)
                else:
                    sources["event_value"] = (
                        f"ask: the value {was} was stated for `{old_event}`, not for "
                        f"`{str(answers['event']).strip()}`")
                    replies.append(f"The value {was} was stated for `{old_event}`; which value "
                                   f"of `{str(answers['event']).strip()}` means the event?")
                session = _log_action(session, route="event_value_reset",
                                      old_event=old_event, value=was, source=how)
            session = _log_action(session, route="numbered_reply",
                                  fields=sorted(answers))
        else:
            if not model_ok:
                raise DeclarationError(
                    "I could not read that as an answer to the numbered "
                    "question, and no model endpoint is configured to "
                    "interpret it. Reply with the numbers, for example:\n"
                    "  1) followup_days\n  2) died\n  3) 1\n  4) A\n  6) yes")
            client = _client(endpoint, api_key)
            # M1: type the message before doing anything with it
            _step("Reading your request")
            raw = intent.classify(client, model, msg, intent.state_line(session),
                                  externals=list(session.externals),
                                  columns=[c.get("name") for c in (session.profile or {}).get("columns") or []
                                           if isinstance(c, dict)])
            intents = intent.dispatch_order(intent.validate(
                msg, raw, result_present=session.result is not None))
            used_model = True
            session = _take_calls(session)
            # A message that writes the file's own column names declares
            # roles, whatever M1 typed. Qwen2.5 on the ablation fixtures
            # (2026-09-13, F07_6, F09_5) typed a request that named the set,
            # the case indicator and five covariates as `describe_external`
            # alone, and the turn ended with the external card and no fit. The
            # rule adds the intent by a deterministic test (textmatch, the
            # corpus's own rule); what the model reads is still checked by
            # the backing check and by verify, so nothing is guessed here.
            if (session.declaration is None
                    and not any(i.kind in ("declare_roles", "edit_declaration") for i in intents)):
                # An out-of-scope request that names columns ("competing risks
                # on time and status") is refused, not analysed: the names are
                # counted OUTSIDE the refused span. An aside at the end of an
                # ordinary request ("also, could you draw a Kaplan-Meier
                # curve": hard set H071/H081, Qwen2.5 typed the aside alone and
                # the whole message was refused, 2026-09-15) leaves the roles
                # the message writes elsewhere, so the analysis runs and the
                # aside is declined in the same reply.
                rest = msg
                for i in intents:
                    if i.kind == "out_of_scope" and i.evidence:
                        rest = rest.replace(i.evidence, " ")
                named = textmatch.names_mentioned(
                    rest, [c["name"] for c in prof.get("columns", [])])
                if len(named) >= 2:
                    ev = sorted(named, key=lambda n: rest.find(n))[0]
                    intents = intent.dispatch_order(list(intents) + [intent.Intent(
                        kind="declare_roles", evidence=ev, evidence_verified=True)])
                    session = _log_action(session, route="declare_roles_by_rule",
                                          columns_named=sorted(named),
                                          beside_out_of_scope=any(i.kind == "out_of_scope" for i in intents))
            # components 5-7: the acts of this turn are a deterministic
            # function of the phase and the typed intents; the plan is
            # checked against the action set's own rules and logged before
            # anything runs
            acts = actions.plan(session, intents)
            illegal = actions.check(session, acts)
            if illegal:
                raise RuntimeError("the planned acts break the action set: "
                                   + "; ".join(illegal))
            n_calls_before = len(session.model_calls)
            session = _log_action(
                session, route="intent",
                intents=[i.as_dict() for i in intents],
                plan=[a.value for a in acts],
                reasoning=str(raw.get("reasoning") or "")[:1000])
            by_kind = {i.kind: i for i in intents}
            steps: List[Dict[str, Any]] = []
            replan: List[Any] = []
            queue = list(acts)
            while queue:                      # a queue, not a for: a dead-ended
                act = queue.pop(0)            # plan may append its fallback acts
                if act is actions.Act.PROPOSE_ROLES:
                    it = by_kind.get("edit_declaration") or by_kind["declare_roles"]
                    if session.declaration is not None:
                        # the current declaration is the base; only the roles
                        # the message names change, and what an unfinished
                        # question already collected stays on top. 2026-10-01:
                        # this used to hold only for a message typed
                        # edit_declaration -- "Adjust for age, bmi, egfr,
                        # cold_ischemia and hla_mismatch only" sent after a
                        # run was typed declare_roles, started from nothing and
                        # asked for the event column again (rubric task H070)
                        base = _answers_of(session.declaration)
                        base.update(given)
                        given = base
                        srcs = dict(session.declaration.sources or {})
                        srcs.update(sources)
                        sources = srcs
                    # boundary 1: the model proposes what was NAMED; a null
                    # is a gap for `complete`, never a guess
                    _step("Finding the columns you named")
                    ext = boundary.extract_roles(client, model, msg, prof,
                                                 *boundary.examples_for(msg, prof))
                    session = _take_calls(session)
                    # the invariant, enforced here and nowhere else: a name
                    # is `quoted` only if the analyst WROTE it (textmatch, the
                    # corpus's own rule). A name the message does not contain
                    # is dropped -- the role then goes to `complete`, which
                    # fills it by a disclosed rule or asks -- and the drop is
                    # logged, so a guess becomes a question, never a fit.
                    backed, unbacked, how = _backed_roles(msg, prof, ext)
                    for key, val in backed.items():
                        given[key], sources[key] = val, how[key]
                    if str(how.get("event_value") or "").startswith("ask:"):
                        # the wording of the coding contradicts the value read:
                        # asked (item 3), and the analyst is told why
                        replies.append("Before fitting, the value that means the event "
                                       "needs to be confirmed: "
                                       + how["event_value"][len("ask: "):] + ".")
                        session = _log_action(session, route="event_value_conflict",
                                              read=unbacked.get("event_value"),
                                              why=how["event_value"])
                    if unbacked:
                        session = _log_action(session, route="unbacked_names",
                                              dropped=unbacked)
                        note = _unbacked_note(unbacked, prof)
                        if note and given.get("covariates") not in (None, "", "A", "B"):
                            replies.append(note)
                elif act in (actions.Act.SHOW_EXTERNAL,
                             actions.Act.NAME_PUBLISHED_MODEL):
                    replies.append(_external_reply(
                        session, by_kind["describe_external"], client, model, msg))
                    session = _take_calls(session)
                elif act is actions.Act.ANSWER_METHOD:
                    # component 8: the matching method notes; 2026-10-06: the model answers in its
                    # own words with the notes as its source, the notes verbatim when it cannot
                    found = knowledge.retrieve(msg)
                    shown = [n.id for n in found]
                    said, session = _chat_answer(client, model, msg, session, prof, history,
                                                 "\n\n".join(f"[{n.id}] {n.body}" for n in found))
                    replies.append(said or knowledge.answer_method(msg, intent.METHOD_ANSWER))
                    session = _log_action(session, route="method_notes", notes=shown,
                                          worded_by_model=bool(said))
                elif act in (actions.Act.EXPLAIN_RESULT, actions.Act.NO_RESULT_YET):
                    replies.append(_result_reply(session, msg, client, model))
                    session = _take_calls(session)
                elif act is actions.Act.REFUSE:
                    oos = by_kind["out_of_scope"]
                    said = None
                    if oos.out_of_scope_reason in (None, "other"):
                        # 2026-10-06: something that is not an analysis this system declines (a general
                        # question) is answered by the model; the named refusals stay as they are
                        said, session = _chat_answer(client, model, msg, session, prof, history)
                    replies.append(said or intent.refusal(oos))
                elif act is actions.Act.SELECT_EXTERNAL:
                    it = by_kind.get("select_external") or by_kind.get("describe_external")
                    name = getattr(it, "external_name", None)
                    if not name and len(session.externals) == 1:
                        # "use it if it helps" with one file loaded names that file
                        # (ablation F09_5, 2026-09-13: the turn asked "which of the
                        # loaded files" with a list of one and never ran)
                        name = next(iter(session.externals))
                    if name and name in session.externals:
                        session = session.select_external(name)
                        replies.append(f"Using **{name}** as the external information "
                                       f"for the next analysis.")
                        if session.declaration is not None:
                            # what this turn or an unfinished question already
                            # holds stays on top of the declaration (H070: the
                            # covariate edit of the message before was wiped
                            # here and the run went back to all ten columns)
                            base = _answers_of(session.declaration)
                            base.update(given)
                            given = base
                            srcs = dict(session.declaration.sources or {})
                            srcs.update(sources)
                            sources = srcs
                    elif session.externals:
                        replies.append("Which of the loaded external files do you mean? "
                                       + ", ".join(f"`{n}`" for n in session.externals)
                                       + ". Name it and I will use it.")
                        acts = [a for a in acts if a is not actions.Act.COMPLETE]
                    elif actions.Act.COMPLETE in acts and session.external_refusal:
                        # nothing is loaded because the file was refused, and the
                        # same message declares the analysis: it runs on the cohort
                        # alone, and the reply says so and why, in place of the
                        # borrowing it asked for. Waiting here (the 2026-09-13
                        # ruling, MIUM P005) made the outcome depend on whether
                        # the model typed the sentence as a selection: synth200
                        # F24, a risk-score file, ran on the cohort alone under
                        # Qwen3-8B and waited under Qwen2.5-7B. The
                        # refusal is on record from the load and is restated.
                        why = "; ".join(str(r.get("message") or r.get("code"))
                                        for r in session.external_refusal[:3])
                        replies.append(f"**{name or 'The external file'} could not be used** "
                                       f"({why}), so nothing is borrowed: the analysis "
                                       f"below is on your cohort alone. Upload a usable "
                                       f"release to borrow from it.")
                        session = _log_action(session, route="refused_external_selected",
                                              named=name, ran_internal_only=True)
                    else:
                        # nothing is loaded (the file was refused, see above) and
                        # no analysis is declared in this message: it waits for a
                        # usable file or an explicit "run on my cohort alone"
                        replies.append("No external file is loaded, so there is nothing "
                                       "to borrow from. Upload a usable file, or say "
                                       "that you want the analysis on your cohort alone.")
                        acts = [a for a in acts if a is not actions.Act.COMPLETE]
                elif act is actions.Act.PLAN_STEPS:
                    # M2: the model lays out the steps; the harness verifies
                    # each and executes them in order below
                    raw_steps = boundary.plan_steps(client, model, msg,
                                                    intent.state_line(session),
                                                    list(session.externals))
                    session = _take_calls(session)
                    steps = boundary.validate_steps(msg, raw_steps, list(session.externals),
                                                    len(session.results))
                    decl_it = by_kind.get("declare_roles")
                    if (steps and all(st["act"] == "select_external" for st in steps)
                            and decl_it is not None and not ablation.on("no_planner_fallback")):
                        # a plan that only selects a file, for a message that
                        # declares the roles and asks for the analysis: the run
                        # the message itself requests follows the selection
                        # (Qwen2.5 planned "select_external" alone on MIUM P068,
                        # 2026-09-13, and the turn ended with nothing fitted)
                        steps.append({"act": "run", "external": None,
                                      "evidence": str(decl_it.evidence or "")[:200],
                                      "added_by": "harness: the message declares roles"})
                    session = _log_action(session, route="plan_steps",
                                          proposed=raw_steps.get("steps"),
                                          accepted=steps,
                                          reasoning=str(raw_steps.get("reasoning") or "")[:600])
                    if not steps:
                        # no usable plan (the thinking arm spent its budget and returned
                        # nothing on MIUM S02/S03, 2026-09-13; a cut plan is the other way
                        # here). If the message ALSO names roles or a release, it is
                        # handled as one analysis by the ordinary acts rather than
                        # dead-ending; only a message that offers nothing else asks back.
                        rest = [i for i in intents if i.kind != "multi_step"]
                        fallback = (actions.plan(session, rest)
                                    if rest and not ablation.on("no_planner_fallback") else [])
                        if fallback and actions.Act.ASK not in fallback and not actions.check(session, fallback):
                            session = _log_action(session, route="plan_steps_fallback",
                                                  acts=[a.value for a in fallback])
                            replies.append("I could not lay that out as separate steps, so I "
                                           "am treating it as one analysis.")
                            replan = fallback
                        else:
                            replies.append("I could not turn that into steps I can carry out. "
                                           "Say which external file to use, or ask for one "
                                           "analysis at a time.")
                elif act in (actions.Act.EVALUATE_BY_SPLITS, actions.Act.DRAW_KM):
                    # V4: carried out after the turn's run, if it makes one (below)
                    pass
                elif act is actions.Act.ASK:
                    comp = complete(prof, given, session.dict_decl,
                                    remembered=session.remembered)
                    lead = ("Nothing has been fitted yet, so there is no result to "
                            "ask about. "
                            if any(i.demoted_from == "ask_about_result" for i in intents)
                            else "I could not tell what you wanted from that. ")
                    # 2026-10-06: a message that is not an analysis request is answered by the
                    # model in its own words; the numbered form follows only while an analysis
                    # is being declared
                    said, session = _chat_answer(client, model, msg, session, prof, history)
                    if said:
                        replies.append(said + (
                            "\n\nStill open for the analysis:\n\n```\n"
                            + render_question(prof, only=comp.missing or None,
                                              time_col=comp.answers.get("time")) + "\n```"
                            if session.pending and comp.missing else ""))
                        continue
                    replies.append(
                        lead + "You can name the columns in a sentence, ask how "
                        "this works, or reply by number:\n\n```\n"
                        + render_question(prof, only=comp.missing or None,
                                          time_col=comp.answers.get("time"))
                        + "\n```")
                # COMPLETE is the harness continuation below this block
                if replan:
                    # the fallback acts replace the dead-ended plan; they are
                    # part of this turn's plan for the budget and the log
                    queue = list(replan)
                    acts = list(acts) + list(replan)
                    replan = []
            used = len(session.model_calls) - n_calls_before + 1
            session = _log_action(session, route="turn_calls", model_calls=used,
                                  budget=actions.MODEL_CALLS_PER_TURN)
            # V4: an evaluation by repeated splits follows whatever this turn runs
            wants_splits = "evaluate_by_splits" in {i.kind for i in intents}
            # V4: a Kaplan-Meier curve the analyst asked to see, drawn after the run
            km_it = by_kind.get("kaplan_meier")
            wants_km = km_it is not None

            def _km(o, chat_msg=None):
                return _draw_km(o, chat_msg, km_it.km_by, km_it.evidence) if wants_km else o
            if steps:
                out = _execute_steps(steps, session, history, msg, replies, client,
                                     prof, write_prose, endpoint, model, api_key,
                                     tz_known)
                return _km(_evaluate_by_splits(out, None, client, model, message=msg)
                           if wants_splits else out)
            wants_compare = actions.Act.COMPARE_RUNS in acts
            if (actions.Act.COMPLETE not in acts and not replies and not wants_splits and not wants_km
                    and "evaluate_on_test" in by_kind):
                # V4: scoring on the supplied test file is part of every analysis; a
                # message that asks only for it is answered from what the session holds
                replies.append(
                    "Every fitted model is scored on your test file; the report's table "
                    "\"Performance on your test data\" gives the C-index, loss, integrated Brier "
                    "score and time-dependent AUC of each." if session.test_data_path else
                    "No test file was uploaded, so there is nothing held out to score the models on. "
                    "Upload one with the same columns and every model is scored on it.")
            wants_compare = actions.Act.COMPARE_RUNS in acts
            if actions.Act.COMPLETE not in acts:
                if wants_compare:
                    replies.append(_compare_reply(session))
                if wants_splits:
                    # of the analysis already run (no run on this turn); the reply goes
                    # under the message itself unless other replies already did
                    if replies:
                        history.append([msg, "\n\n".join(replies)])
                    return _km(_evaluate_by_splits((history, "", session) + _EMPTY,
                                                   None if replies else msg, client, model,
                                                   message=msg))
                if wants_km:
                    if replies:
                        history.append([msg, "\n\n".join(replies)])
                    return _km((history, "", session) + _EMPTY, None if replies else msg)
                history.append([msg, "\n\n".join(replies)])
                return (history, "", session) + _EMPTY
            if wants_compare or wants_splits or wants_km:
                # the comparison and the evaluation follow the run this turn makes
                out = _settle_and_run(session, history, msg, given, sources, replies,
                                      used_model, client, prof, write_prose, endpoint,
                                      model, api_key, tz_known)
                h2, _, s2, *rest = out
                ran = len(s2.results) > len(session.results)
                if wants_compare and ran:
                    h2.append([None, _compare_reply(s2)])
                out = (h2, "", s2) + tuple(rest)
                if wants_splits and ran:
                    out = _evaluate_by_splits(out, None, client, model, message=msg)
                return _km(out) if ran else out
    except DeclarationError as exc:
        session = _note_missing_column(session, exc)
        history.append([msg, f"**I could not use that.**\n\n{exc}"])
        return (history, "", session) + _EMPTY
    except Exception as exc:
        # The model failed to read the message (a thinking model that spent
        # its whole allowance and returned no JSON: Qwen3-thinking on three
        # ghost-column prompts of the MIUM run). The numbered form never needs
        # the model, so the turn ends with it rather than with a dead end.
        session = _log_action(session, route="model_failure",
                              error=f"{type(exc).__name__}: {str(exc)[:300]}")
        history.append([msg, "**I could not read that.** The model that reads "
                             "free text failed on this message, so tell me by "
                             "number instead; nothing has been settled from it.\n\n"
                             f"<small>{type(exc).__name__}: {str(exc)[:300]}</small>\n\n"
                             "```\n" + render_question(prof) + "\n```"])
        return (history, "", session) + _EMPTY

    return _settle_and_run(session, history, msg, given, sources, replies,
                           used_model, client if used_model else None, prof,
                           write_prose, endpoint, model, api_key, tz_known)


def _settle_and_run(session, history, msg, given, sources, replies, used_model,
                    client, prof, write_prose, endpoint, model, api_key, tz_known):
    """Complete the roles, ask what nothing settles, or verify and run. One
    step of the orchestrator; a multi-step turn calls it once per run."""
    # the one answer that always comes from a person: given once, by checkbox
    if tz_known and not given.get("time_zero"):
        given["time_zero"] = "yes"
        sources["time_zero"] = ("reply: you said every covariate was recorded "
                                "at the start of follow-up")

    # settle what was left unsaid, where the data leaves one possibility
    comp = complete(prof, given, session.dict_decl, remembered=session.remembered,
                    sources=sources)
    if comp.sources.get("design"):
        # the design question was reopened on a time column shaped like a
        # matched set; the analyst is told why before the numbered list
        replies = list(replies) + [comp.sources["design"]]
        session = _log_action(session, route="design_reopened",
                              named=str(given.get("time")))
    sources.update(comp.sources)
    session = session.with_pending(comp.answers, sources,
                                   asked=comp.missing or None)
    lead = ("\n\n".join(replies) + "\n\n") if replies else ""
    if comp.missing:
        # the model words the lead-in when it read the message (a numbered
        # reply never reaches it); the harness's list follows unchanged
        worded = ""
        if used_model:
            try:
                w = boundary.word_question(client, model, msg, prof, comp.answers,
                                           sources, comp.missing)
            except Exception as exc:                 # never block the question
                w = {"question": None, "dropped": f"{type(exc).__name__}: {exc}"}
            session = _take_calls(session)
            session = _log_action(session, route="word_question",
                                  used=bool(w.get("question")),
                                  dropped=w.get("dropped"))
            if w.get("question"):
                worded = w["question"] + "\n\n"
        body = (lead + worded + _settled(comp.answers, sources) + "```\n"
                + render_question(prof, only=comp.missing, time_col=comp.answers.get("time"))
                + "\n```")
        history.append([msg, body])
        return (history, "", session) + _EMPTY

    try:
        decl = parse_reply(prof, dict(comp.answers))
    except DeclarationError as exc:
        # what was said contradicts the file: the one kind of gap that has
        # to go back to the analyst -- and the refusal names the item to
        # correct, so a reply of "3) 1" is all it takes
        session = _note_missing_column(session, exc)
        history.append([msg, lead + f"**I could not use that.**\n\n{exc}\n\n"
                                    + _correct_by_number(exc)])
        return (history, "", session) + _EMPTY
    decl.sources = {k: v for k, v in sources.items() if k in _ROLE_KEYS}
    # a column named earlier that the file lacks, and that the settled
    # declaration does not carry: say so in the report (report_v3 section 1)
    for gone in _missing_columns(session):
        if gone not in (decl.covariates or []) and gone not in (decl.time_col, decl.event_col, decl.stratum_col):
            note = f"named but not a column of the file: '{gone}'; left out at the analyst's reply"
            if note not in decl.notes:
                decl.notes.append(note)
    if used_model:
        decl.source = "model_extraction"
    # another cohort's rows: the same column names, or nothing (no renaming
    # is done here -- that is the analyst's file to fix)
    ext = session.external
    if ext is not None and ext.individual_data:
        d = ext.individual_data
        bad = []
        # a release in the cohort's own layout whose outcome columns the
        # reading left to the declaration (external.canonicalise): filled here
        # by name, when the table carries them; the checks below then hold it
        # to the declaration like any other external cohort
        if d.get("outcome_from_declaration") and not d.get("event_column"):
            d = dict(d)
            if decl.event_col in d["columns"]:
                d["event_column"] = decl.event_col
                d["event_value"] = decl.event_value
            if decl.time_col and not d.get("time_column") and decl.time_col in d["columns"]:
                d["time_column"] = decl.time_col
            ext.individual_data = d
            session = _log_action(session, route="external_outcome_from_declaration",
                                  time=d.get("time_column"), event=d.get("event_column"))
        # The declaration decides the design, whichever arrived first. A
        # release read BEFORE the declaration is read without knowing it, and
        # on another matched sample the model can name a covariate as the
        # follow-up time ('age' on synth200 F21, 8 of 8 with Qwen3-8B,
        # 2026-09-15) -- the same table read after a matched declaration is
        # read with no time (`canonicalise(matched_design=True)`). So under a
        # matched declaration the model's time column is set aside here by
        # the same rule, the card records it, and what is checked is what
        # the matched estimator uses: the set column and the case column.
        if (decl.stratum_col and not decl.time_col and d.get("time_column")
                and decl.stratum_col in d["columns"]):
            named = d["time_column"]
            d = dict(d, time_column=None)
            ext.individual_data = d
            ext.notes.append(f"the reading named {named!r} as the follow-up time; "
                             f"your declaration is a matched design with "
                             f"{decl.stratum_col!r} as the set column, which the "
                             f"table carries, so it is read as a matched sample "
                             f"like yours and {named!r} stays a covariate")
            session = _log_action(session, route="external_time_set_aside",
                                  named=named, stratum=decl.stratum_col)
        if decl.stratum_col and decl.stratum_col not in d["columns"]:
            bad.append(f"it lacks your matched-set column {decl.stratum_col!r}")
        if d["time_column"] != decl.time_col:
            bad.append(f"its follow-up time column is {d['time_column']!r}, "
                       f"yours is {decl.time_col!r}")
        if d["event_column"] != decl.event_col:
            bad.append(f"its event column is {d['event_column']!r}, yours is "
                       f"{decl.event_col!r}")
        miss = [c for c in decl.covariates if c not in d["columns"]]
        if miss:
            bad.append("it lacks " + ", ".join(miss))
        if bad:
            history.append([msg, lead + "**The external cohort does not line "
                                        "up with your declaration:** "
                            + "; ".join(bad) + ". Rename the columns in the "
                            "external file to match yours and upload it "
                            "again. Nothing was fitted."])
            return (history, "", session) + _EMPTY
        decl.external_data_path = d["path"]
        decl.external_data_expr = _data_expr_for(d["path"])

    # : the analyst's test file, if one was uploaded, is part of the
    # declaration (hashed by content, gated for the same columns, replayed)
    if session.test_data_path:
        decl.test_data_path = session.test_data_path
        decl.test_data_expr = session.test_data_expr

    # : the external baseline hazard, if one was read, reaches the gate
    # only to be checked against a declared horizon; it raises no question
    _step("Checking your data")
    v = verify(prof, decl, session.data_path, session.data_expr,
               run_r=_run_r,
               external_baseline=(getattr(ext, "baseline_hazard", None)
                                  if ext is not None else None))
    session = session.with_declaration(decl, v)
    body = lead + "```\n" + v.render() + "\n```"
    if not v.admissible:
        # the model may explain the refusal in plain words -- never advise;
        # the harness's own refusal text above stays as it is
        if used_model and client is not None and v.refusals:
            try:
                ex = boundary.explain_refusal(client, model, v.refusals, prof, decl)
            except Exception as exc:
                ex = {"explanation": None, "dropped": f"{type(exc).__name__}: {exc}"}
            session = _take_calls(session)
            session = _log_action(session, route="explain_refusal",
                                  used=bool(ex.get("explanation")), dropped=ex.get("dropped"))
            if ex.get("explanation"):
                body += "\n\n" + ex["explanation"]
        body += ("\n\n**Nothing was fitted.** Change the declaration above -- "
                 "reply by number -- and I will try again.")
        # which numbered item the first refusal is about, so the analyst (or the
        # benchmark's simulated one) knows what to correct (ablation F07, 2026-09-13:
        # Qwen3 quoted the outcome columns as the predictors, the gate refused, and
        # the turn named no item)
        item = next((_ITEM_OF_REFUSAL.get(_refusal_family(r.get("code", "")))
                     for r in v.refusals if _ITEM_OF_REFUSAL.get(_refusal_family(r.get("code", "")))), None)
        if item:
            body += f" Reply by number to correct it: item {item}, {_ITEM_LABEL[item]}."
        history.append([msg, body])
        return (history, "", session) + _EMPTY
    planning = analyst.enabled() and bool(model) and bool(api_key or "localhost" in (endpoint or ""))
    body += ("\n\nPlanning which models to fit, then fitting them." if planning
             else "\n\nRunning every admissible method now.")
    history.append([msg, body])
    return run_analysis(session, write_prose, endpoint, model, api_key, history)


# --------------------------------------------------------------------------
# Step 3 — nothing left to ask: fit everything, select, report
# --------------------------------------------------------------------------
def _candidate_table(res: Dict[str, Any]) -> pd.DataFrame:
    sel = res["selected"]["key"]
    rows = []
    for c in res["candidates"]:
        rows.append({
            "": "<-" if c["key"] == sel else "",
            "method": c["label"],
            "status": c["status"],
            "held-out loss": (None if c.get("loss") is None
                              else round(float(c["loss"]), 5)),
            "eta": (None if c.get("eta") in (None, "") else
                    round(float(c["eta"]), 4)),
            "lambda": (None if c.get("lambda") in (None, "") else
                       float(c["lambda"])),
            "non-zero": c.get("n_nonzero"),
            "seconds": c.get("seconds"),
            "why not": (c.get("message") or "")[:80],
        })
        h = c.get("holdout")
        if h:
            # : reported beside the CV loss, never selected on
            for k, lab in (("cindex", "test C-index"), ("loss", "test loss"),
                           ("ibs", "test IBS"), ("tdauc", "test tdAUC")):
                v = h.get(k)
                rows[-1][lab] = (None if v is None else round(float(v), 5))
    return pd.DataFrame(rows)


def _coefficient_table(res: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for c in res.get("coefficients", []):
        rows.append({
            "variable": c["variable"],
            "external": (None if c.get("beta_external") is None
                         else round(float(c["beta_external"]), 4)),
            "your data alone": (None if c.get("beta_internal") is None
                                else round(float(c["beta_internal"]), 4)),
            "selected": (None if c.get("beta_selected") is None
                         else round(float(c["beta_selected"]), 4)),
        })
    return pd.DataFrame(rows)


def run_analysis(session, write_prose, endpoint, model, api_key, history):
    """Fit everything, select, report. Called by `submit_answer` the moment
    nothing is left to ask; returns the same ten outputs."""
    history = list(history or [])
    if not session or session.declaration is None:
        history.append([None, "Tell me what the columns are first."])
        return (history, "", session) + _EMPTY
    v = session.verification
    if not v.admissible:
        history.append([None, "The declaration was refused; nothing was run."])
        return (history, "", session) + _EMPTY

    # component 9: the harness audits its own invariants before the core runs
    # and fails closed -- a harness that broke one is not trusted with the rest
    violations = guards.audit(session)
    if violations:
        session = _log_action(session, route="guard_audit", violations=violations)
        history.append([None, "**The analysis was refused by the harness's own "
                              "audit.** Nothing was fitted.\n\n"
                        + "\n".join(f"- {v}" for v in violations)
                        + "\n\nThis is a defect in the harness, not in your data; "
                          "start over and, if it recurs, report it with trace.json."])
        return (history, "", session) + _EMPTY

    # M5: the external object by value (coefficients, and the precision
    # matrix if one was read) plus its provenance
    ext = session.external
    ext_kw = ext.pipeline_kwargs() if ext is not None else {}
    ext_prov = ext.provenance if ext is not None else None

    # V4 item 4: the planner decides WHAT is fitted -- the row, the members, their
    # grids, covariate subsets and masks -- from the diagnostics card, the playbook
    # and the analyst's words; the harness checks every proposal, fits it on one
    # partition, and cross-validation still picks the final model. Without a model
    # (or with the planner switched off) the V3 set is fitted.
    loop = None
    if analyst.enabled() and model and (api_key or "localhost" in (endpoint or "")):
        try:
            _step("Checking how well the external data fits your cohort")
            card = pipeline.diagnose(session.data_path, session.data_expr,
                                     session.declaration, run_r=_run_r, **ext_kw)
        except Exception as exc:
            card = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
        if card.get("status") == "ok":
            opts = analyst.options_for(session.declaration, ext_kw)
            words = "\n\n".join(a["message"] for a in session.actions
                                 if isinstance(a, dict) and a.get("message"))

            def _fit(pl, reuse):
                _step("Fitting the planned models")
                return pipeline.fit_plan(session.data_path, session.data_expr,
                                         analyst.amend_declaration(session.declaration, pl),
                                         pl, reuse=reuse, run_r=_run_r, **ext_kw)

            def _check_intervals(pl):
                # 4b: a planned discrete grid goes through the gate like a declared one
                v2 = verify(session.profile, analyst.amend_declaration(session.declaration, pl),
                            session.data_path, session.data_expr, run_r=_run_r,
                            external_baseline=ext_kw.get("external_baseline_inline"))
                return [{"code": "intervals_refused:" + str(r.get("code")),
                         "message": str(r.get("message"))} for r in v2.refusals]
            try:
                _step("Planning which models to fit")
                loop = analyst.run_loop(analyst.model_proposer(_client(endpoint, api_key), model),
                                        _fit, declaration=session.declaration, card=card,
                                        opts=opts, words=words, check_intervals=_check_intervals)
            except pipeline.PipelineRefusal as exc:
                session = _take_calls(session)
                why = "\n".join(f"- {r['message']}" for r in exc.refusals)
                history.append([None, f"**The planned analysis could not be fitted.**\n\n{why}"
                                      "\n\nNothing was reported."])
                return (history, "", session) + _EMPTY
            session = _take_calls(session)
            session = _log_action(session, route="analysis_planned",
                                  row=loop.plan.get("row"),
                                  members=[m["key"] for m in loop.plan.get("members") or []],
                                  units=sum(int(st.get("units") or 0) for st in loop.steps
                                            if st.get("step") == "fit"),
                                  model_calls=loop.n_calls, fallback=loop.fallback,
                                  situations=loop.situations)
        else:
            session = _log_action(session, route="diagnose_failed",
                                  message=str(card.get("message"))[:300])

    prose_fn = None
    model_prov = None
    if write_prose and (api_key or "localhost" in (endpoint or "")):
        client = _client(endpoint, api_key)
        _prose = boundary.write_prose(client, model)

        def prose_fn(*a, **k):
            _step("Writing the report")
            return _prose(*a, **k)
        model_prov = boundary.describe_model(client, model)
    if session.model_calls or session.actions:
        model_prov = dict(model_prov or {"served_model": model,
                                         "base_url": endpoint})
        model_prov["calls"] = list(session.model_calls)
        model_prov["actions"] = list(session.actions)
        from bregsurv_agent import policy
        model_prov["policies"] = policy.describe()     # component 2

    # C3 with no human in the middle: hash the configuration verify saw (and,
    # in V4, the plan the harness accepted), and let pipeline.run prove that is
    # what it fitted
    plan_final = loop.plan if loop is not None else None
    decl_run = analyst.amend_declaration(session.declaration, plan_final)
    sha = pipeline.resolve_config(
        session.data_path, session.data_expr, decl_run,
        external_beta_inline=ext_kw.get("external_beta_inline"),
        external_Q_inline=ext_kw.get("external_Q_inline"),
        external_baseline_inline=ext_kw.get("external_baseline_inline"),
        plan=plan_final)["sha256"]
    try:
        _step("Comparing the models and choosing the best")
        res = pipeline.run(
            data_path=session.data_path, data_expr=session.data_expr,
            declaration=decl_run,
            profile=session.profile, run_r=_run_r, write_prose=prose_fn,
            approved_config_sha256=sha, model_provenance=model_prov,
            external_provenance=ext_prov,
            # component 3: the phase walk, turn and question counts;
            # component 4: whether memory was on and what it supplied
            session_provenance=dict(session.to_provenance(),
                                    memory=memory.Store().describe(),
                                    knowledge=knowledge.describe(),
                                    ablation=ablation.describe(),
                                    few_shot=fewshot.describe(),
                                    guard_violations=[]),
            plan=plan_final,
            reuse=(loop.reuse if loop is not None else None),
            plan_steps=(loop.steps if loop is not None else None),
            **ext_kw)
    except pipeline.PipelineRefusal as exc:
        why = "\n".join(f"- {r['message']}" for r in exc.refusals)
        history.append([None, f"**The analysis was refused.**\n\n{why}\n\n"
                              "Nothing was fitted."])
        return (history, "", session) + _EMPTY
    except Exception:
        detail = traceback.format_exc()[-1200:]
        history.append([None,
            "**The analysis did not run.**\n\nNothing was fitted, so there is "
            "no result to interpret and nothing has been saved.\n\n"
            f"<details><summary>Technical detail</summary>\n\n```\n{detail}\n"
            "```\n</details>"])
        return (history, "", session) + _EMPTY

    outdir = Path(tempfile.mkdtemp(prefix="bregsurv_"))
    paths = res.save(str(outdir))
    c = res.candidates
    history.append([None, res.report])
    session = session.with_result(res, str(outdir))
    # component 4: the verified declaration is remembered for this exact file
    # (never the shipped example, never on a shared host, never time zero)
    if session.data_sha256 and session.data_path != str(DEMO_COHORT):
        decl = session.declaration
        memory.Store().remember_declaration(
            session.data_sha256, _answers_of(decl), decl.sources or {},
            file_name=Path(session.data_path).name,
            columns=[col["name"] for col in session.profile.get("columns", [])])
    return (history, "", session,
            _candidate_table(c), _coefficient_table(c),
            paths["report"], paths["trace"], paths["repro"],
            paths["candidates"], paths.get("repro_diskd"), None)


def reset_all(session=None):
    """Clear the screen AND the disk. Pressing 'start over' is a statement that
    the previous file is finished with, so it should not linger until the
    session happens to be collected."""
    _purge(session)
    return ([], "", None) + _EMPTY


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
# A clean light theme, used whatever the visitor's system colour scheme is.
_THEME = gr.themes.Soft(primary_hue="sky", secondary_hue="slate", neutral_hue="slate").set(
    body_background_fill="#f7f9fb",
    block_background_fill="#ffffff",
    block_border_color="#e3e8ee",
    block_label_background_fill="#eef3f8",
    block_label_text_color="#4a5b6e",
    block_title_text_color="#2b3a4a",
    button_primary_background_fill="#2f80c0",
    button_primary_background_fill_hover="#256aa3",
    button_primary_text_color="#ffffff",
    button_secondary_background_fill="#ffffff",
    button_secondary_border_color="#cfd8e3",
    code_background_fill="#f3f6f9",
)
_FORCE_LIGHT_JS = """
() => {
  const u = new URL(window.location.href);
  if (u.searchParams.get('__theme') !== 'light') {
    u.searchParams.set('__theme', 'light');
    window.location.replace(u.href);
  }
}
"""
_CSS = """
footer { display: none !important; }
.gradio-container { max-width: 860px !important; margin: auto; }
#topbar { display: flex; justify-content: space-between; align-items: center; }
#brand { font-weight: 600; color: #2b3a4a; font-size: 15px; }
#greeting { text-align: center; margin-top: 22vh; margin-bottom: 18px; }
#greeting h1 { font-family: Georgia, 'Times New Roman', serif; font-weight: 400;
               font-size: 2.0rem; color: #22303e; letter-spacing: -0.01em; }
#greeting, #greeting > div { border: none !important; background: transparent !important; box-shadow: none !important; }
#msg_in { border-radius: 22px !important; border: 1px solid #d9e1ea !important;
          box-shadow: 0 2px 10px rgba(30, 50, 80, 0.06) !important; background: #fff !important; }
#msg_in textarea { font-size: 16px !important; }
#msg_in, #msg_in > div, .block:has(> #msg_in) { background: transparent; }
div:has(> #msg_in) { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
#chat { border: none !important; background: transparent !important; }
#chat .message { font-size: 15px; line-height: 1.55; }
#example_row { justify-content: center; }
#example_btn { max-width: 240px; border-radius: 16px; }
#newbtn { max-width: 140px; }
#foot { color: #8a96a3; font-size: 12px; text-align: center; margin-top: 8px; }
"""

# --------------------------------------------------------------------------
# The chat page: one conversation, files dropped into the message box
# --------------------------------------------------------------------------
_TABLE_EXT = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".parquet"}
_TEST_WORDS = re.compile(r"\b(test|testing|hold[- ]?out|held[- ]?out|validation|validate|evaluate on)\b", re.I)
_BORROW_WORDS = re.compile(r"\b(borrow|external|another (cohort|centre|center|hospital|site|registry)|registry|other (cohort|centre|center|hospital|site))\b", re.I)
_YES = re.compile(r"^\s*(y|yes|yeah|yep|correct|right|true|they were|all (of them )?were)\b", re.I)
_NO = re.compile(r"^\s*(n|no|nope|not all|false)\b", re.I)
# a sentence in which the analyst states the covariates were recorded at time zero
_TZ_STATED = re.compile(
    r"(recorded|measured|known|collected|taken|available)\s+(at|before)\s+(baseline|transplant(ation)?|"
    r"the start of follow[- ]?up|time zero|enrol?ment|entry|diagnosis|admission|surgery|randomi[sz]ation)"
    r"|\bbaseline (values|covariates|variables|measurements)\b", re.I)


def _table_shape(path: str):
    """(columns, rows) of a table file, or None for anything that is not a table."""
    suf = Path(path).suffix.lower()
    try:
        if suf in (".csv", ".tsv", ".txt"):
            df = pd.read_csv(path, sep=None, engine="python", nrows=2000)
        elif suf in (".xlsx", ".xls"):
            df = pd.read_excel(path, nrows=2000)
        elif suf == ".parquet":
            df = pd.read_parquet(path)
        else:
            return None
        return [str(c) for c in df.columns], len(df)
    except Exception:
        return None


def _assign_files(paths: List[str], text: str, cohort_cols: Optional[List[str]]):
    """Decide what each dropped file is: the cohort, an external release, or a
    test file. A table with the cohort's columns that could be a test file or
    another cohort's records is settled by the analyst's words, else asked."""
    shapes = {p: _table_shape(p) for p in paths}
    cohort = None
    if cohort_cols is None:
        tables = [(p, sh) for p, sh in shapes.items() if sh and sh[1] >= 30 and len(sh[0]) >= 3]
        if tables:
            cohort = max(tables, key=lambda t: (len(t[1][0]), t[1][1]))[0]
            cohort_cols = shapes[cohort][0]
    roles, ask = {}, []
    if cohort:
        roles[cohort] = "cohort"
    for p in paths:
        if p == cohort:
            continue
        sh = shapes.get(p)
        same = bool(sh and cohort_cols and len(set(sh[0]) & set(cohort_cols)) >= 0.8 * len(cohort_cols))
        if not same:
            roles[p] = "external"
        elif _TEST_WORDS.search(text or "") and not _BORROW_WORDS.search(text or ""):
            roles[p] = "test"
        elif _BORROW_WORDS.search(text or "") and not _TEST_WORDS.search(text or ""):
            roles[p] = "external"
        else:
            ask.append(p)
    return roles, ask


def _plain_label(key: str) -> str:
    """A method name a non-statistician can read."""
    k = (key or "").replace("_ties", "")
    if k.startswith("internal"):
        base = "using your data alone"
    elif k.startswith("external"):
        base = "using the external model as it is"
    elif k.startswith("kl") or k.startswith("discretekl") or k.startswith("diskd"):
        base = "combining your data with the external model, pulling your estimates toward it"
    elif k.startswith("mahalanobis") or k.startswith("euclidean"):
        base = "combining your data with the external model, keeping your estimates close to its coefficients"
    elif k.startswith("indi"):
        base = "pooling your data with the other cohort's records"
    else:
        base = "combining your data with the external information"
    if k.endswith("_lasso"):
        base += ", with a penalty that can drop variables that add nothing"
    elif k.endswith("_ridge"):
        base += ", with estimates shrunk to keep them stable"
    return base


def _plain_declaration(session) -> str:
    """What the analysis used, in one sentence (instead of the technical card)."""
    d = session.declaration
    if d is None:
        return ""
    card = "\n".join(session.verification.card) if session.verification else ""
    m = re.search(r"events\s+(\d+) of (\d+)", card)
    ev = f" ({m.group(1)} events among {m.group(2)} patients)" if m else ""
    cov = d.covariates or []
    covs = (", ".join(f"`{c}`" for c in cov[:-1]) + f" and `{cov[-1]}`") if len(cov) > 1 else \
           (f"`{cov[0]}`" if cov else "nothing")
    if d.time_col:
        lead = f"I used `{d.time_col}` as the follow-up time and `{d.event_col}` = {d.event_value} as the event"
    else:
        lead = (f"I analysed the matched sets in `{d.stratum_col}`, with `{d.event_col}` = "
                f"{d.event_value} marking the case")
    return f"{lead}, adjusting for {covs}{ev}."


def _summary_reply(session) -> str:
    """The result in plain words, for the chat. The full report is in the download."""
    res = session.result
    c = res.candidates
    sel = c.get("selected") or {}
    cands = [k for k in c.get("candidates", []) if k.get("status") == "ok"]
    key = sel.get("key", "")
    n = (session.profile or {}).get("n_rows")
    if key.startswith("internal"):
        verdict = ("Your cohort on its own gave the best model, so the external "
                   "information was **not** used.")
    elif key.startswith("external"):
        verdict = ("The external model, used as it is, did best on your data, so "
                   "it is recommended unchanged.")
    else:
        verdict = ("Combining your cohort with the external information did best, "
                   "so borrowing **helped**. The recommended approach: "
                   + _plain_label(key) + ".")
    out = [_plain_declaration(session),
           f"**Done.** I compared {len(cands)} ways of analysing your "
           f"{n} patients, including your cohort on its own and the external "
           f"model as it is. {verdict}"]
    rows = []
    for r in c.get("coefficients") or []:
        b = r.get("beta_selected")
        if b is None:
            continue
        rows.append(f"| {r['variable']} | {b:.3f} |")
    if rows:
        out.append("The coefficients of the recommended model (a positive value means "
                   "higher risk of the event, a negative value lower risk):\n\n"
                   "| variable | coefficient |\n|---|---|\n" + "\n".join(rows))
    out.append("The full report, with every model that was tried and how to read "
               "these coefficients, is attached below as a PDF. Ask me anything "
               "about the result.")
    return "\n\n".join(out)


_PDF_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 10.5pt; color: #1f2a36; line-height: 1.45; }
h1 { font-size: 17pt; color: #1f4e79; } h2 { font-size: 13pt; color: #1f4e79; margin-top: 16pt;
     border-bottom: 1px solid #d6dee8; padding-bottom: 2pt; } h3 { font-size: 11pt; }
table { border-collapse: collapse; margin: 6pt 0; font-size: 9pt; }
th, td { border: 1px solid #d6dee8; padding: 3pt 6pt; text-align: left; }
th { background: #eef3f8; } .col { color: #1f4e79; font-weight: 600; } code, pre { font-family: 'DejaVu Sans Mono', monospace; font-size: 9.5pt; color: #24425f; }
pre { background: #f5f7fa; padding: 6pt; white-space: pre-wrap; }
img { max-width: 100%; }
"""


_READING_GUIDE = (
    "> **How to read the coefficients.** Each coefficient is a log hazard ratio. "
    "A positive value means a higher risk of the event, a negative value a lower "
    "risk, and zero means the variable was left out. Exponentiating a coefficient "
    "gives the hazard ratio: the factor by which the risk is multiplied when the "
    "variable is one unit higher and the other variables are unchanged (for "
    "example, a coefficient of 0.5 gives a hazard ratio of about 1.65, a 65% "
    "higher risk). A unit is whatever unit the column uses in your data, so a "
    "coefficient for age in years and one for age in decades are not comparable. "
    "These are associations in your cohort, not causal effects.\n\n")


def _with_reading_guide(md_text: str) -> str:
    m = re.search(r"^## 5\..*$", md_text, flags=re.M)
    if not m:
        return md_text + "\n\n" + _READING_GUIDE
    return md_text[:m.end()] + "\n\n" + _READING_GUIDE + md_text[m.end():]


def _report_pdf(session) -> Optional[str]:
    """The full report as a PDF, written next to the run's other files."""
    if session is None or session.result is None or not session.temp:
        return None
    outdir = Path(session.temp[-1])
    md = outdir / "report.md"
    if not md.is_file():
        return None
    pdf = outdir / "BregSurv_report.pdf"
    try:
        import markdown
        from weasyprint import HTML
        body = markdown.markdown(_with_reading_guide(md.read_text()), extensions=["tables", "fenced_code"])
        body = re.sub(r"<code>(.*?)</code>", r"<span class='col'>\1</span>", body)
        HTML(string=f"<html><head><meta charset='utf-8'><style>{_PDF_CSS}</style></head>"
                    f"<body>{body}</body></html>", base_url=str(outdir)).write_pdf(str(pdf))
        return str(pdf)
    except Exception as exc:
        print(f"[app] weasyprint unavailable ({type(exc).__name__}); using xhtml2pdf", flush=True)
    try:
        import markdown
        from xhtml2pdf import pisa
        body = markdown.markdown(_with_reading_guide(md.read_text()), extensions=["tables", "fenced_code"])
        body = re.sub(r"<code>(.*?)</code>", r"<span class='col'>\1</span>", body)
        with open(pdf, "wb") as fh:
            r = pisa.CreatePDF(f"<html><head><meta charset='utf-8'><style>{_PDF_CSS}</style>"
                               f"</head><body>{body}</body></html>", dest=fh)
        return None if r.err else str(pdf)
    except Exception as exc:
        print(f"[app] PDF not written: {type(exc).__name__}: {exc}", flush=True)
        return None


def _new_result(before, after) -> bool:
    return after is not None and after.result is not None and (
        before is None or before.result is not after.result)


_EXT_CARD = re.compile(r"This is the external information I have read:\n\n```.*?```\n\n"
                       r"It is borrowed from only if that lowers the held-out loss; the "
                       r"report shows the comparison either way\.\s*", re.S)


def _plain_turn(text: str) -> str:
    """The chat page's wording of a turn that stops before a result: the release
    card is dropped (the opening already said what the file holds), and a column
    the file lacks is asked about in plain words."""
    t = _EXT_CARD.sub("", text)
    m = _NO_COLUMN.search(t)
    if m and "**I could not use that.**" in t:
        t = (t[:t.index("**I could not use that.**")]
             + f"Your data has no column called `{m.group(1)}`. Should I leave it out, "
               "or did you mean another column? You can answer in your own words, "
               "for example \"leave it out\".")
    elif "**I could not use that.**\n\n" in t:
        head, rest = t.split("**I could not use that.**\n\n", 1)
        t = head + "I could not use that: " + rest[:1].lower() + rest[1:]
    t = t.strip()
    return t or ("I have the external information. To run the analysis, tell me which column is the "
                 "follow-up time, which is the event and which value means it occurred, and what to adjust "
                 "for; a sentence is enough.")


def chat_turn(mm, history, session, ui):
    """One turn of the chat page: files first (loaded, each given a role), then
    the words. Returns (chat, box, session, ui)."""
    history = list(history or [])
    ui = dict(ui or {})
    text = ((mm or {}).get("text") or "").strip()
    files = [f if isinstance(f, str) else (f.get("path") if isinstance(f, dict) else getattr(f, "name", None))
             for f in ((mm or {}).get("files") or [])]
    files = [f for f in files if f]
    ep, mdl, key = DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_API_KEY
    before = session

    # an answer to "is this file a test set or another cohort?"
    if ui.get("ask_file") and text and not files:
        p = ui.pop("ask_file")
        role = ("test" if _TEST_WORDS.search(text) else
                "external" if _BORROW_WORDS.search(text) or re.search(r"\bborrow", text, re.I) else None)
        if role is None:
            ui["ask_file"] = p
            history.append([text, "Please say **test** (only to check the result) "
                                  "or **borrow** (another group of patients to learn from)."])
            return history, None, session, ui
        history.append([text, None])
        files, text = [p], ""
        ui["forced_role"] = role

    if files:
        names = ", ".join(f"`{Path(f).name}`" for f in files)
        cohort_cols = None
        if session is not None and session.profile and session.data_path != str(DEMO_COHORT):
            cohort_cols = [c["name"] for c in session.profile.get("columns", [])]
        roles, ask = _assign_files(files, text, cohort_cols)
        if ui.get("forced_role"):
            roles = {files[0]: ui.pop("forced_role")}; ask = []
        if ask:
            ui["ask_file"] = ask[0]
            history.append([f"📎 {names}" + (f"\n\n{text}" if text else ""),
                            f"`{Path(ask[0]).name}` has the same columns as your data. "
                            "Is it a **test** set (only to check the result) or another "
                            "group of patients to **borrow** from?"])
            ui["held_text"] = text
            return history, None, session, ui
        cohort = next((p for p, r in roles.items() if r == "cohort"), None)
        ext = [p for p, r in roles.items() if r == "external"]
        test = next((p for p, r in roles.items() if r == "test"), None)
        if history and history[-1][1] is None:
            history.pop()
        user_line = f"📎 {names}"
        if cohort is not None:
            h, session, *_ = start_session(cohort, ext[0] if ext else None, ep, mdl, key, test)
            history.append([user_line, h[0][1] if h else "The file could not be read."])
            for extra in ext[1:]:
                history, session = add_external(extra, session, history, ep, mdl, key)
            ui["tz_ok"] = False
        elif session is not None and session.phase is not Phase.EMPTY:
            if ext:
                history.append([user_line, None])
                for e in ext:
                    history, session = add_external(e, session, history, ep, mdl, key)
                last = history.pop()
                history[-1][1] = last[1]
            if test:
                session = replace(session, test_data_path=test, test_data_expr=_data_expr_for(test),
                                  temp=list(session.temp) + _ours(test))
                history.append([user_line, f"`{Path(test).name}` will be used only to score "
                                           "the models on patients they have not seen."])
        else:
            history.append([user_line, "I could not tell which file is your cohort. "
                                       "Drop the patient-level table with the follow-up "
                                       "time and the event."])
            return history, None, session, ui
        text = text or ui.pop("held_text", "")
        if not text:
            return history, None, session, ui

    if not text:
        return history, None, session, ui

    # time zero: the one thing only the analyst can say; read it from the words
    # when stated, otherwise ask once, in plain words, before the first run
    if ui.get("tz_wait"):
        held = ui.pop("tz_wait")
        if _YES.search(text):
            ui["tz_ok"] = True
            history.append([text, None])
            text = held
        elif _NO.search(text):
            history.append([text, "Then this analysis cannot be done here: a value "
                                  "recorded after follow-up began, treated as if it were "
                                  "known at the start, can reverse the direction of an "
                                  "effect. Use only variables recorded at the start."])
            return history, None, session, ui
        else:
            ui["tz_wait"] = held
            history.append([text, "Please answer **yes** or **no**: were all the "
                                  "variables recorded at the start of follow-up?"])
            return history, None, session, ui
    if _TZ_STATED.search(text):
        ui["tz_ok"] = True
    # 2026-10-06: every message is read first (a greeting or a question is answered as such); the
    # time-zero question is put only when it is the one thing left before a run (below)

    answered_yes = bool(history and history[-1][1] is None)
    if answered_yes:
        history.pop()
    n0 = len(history)
    n_act0 = len(before.actions) if before is not None else 0
    out = submit_answer(text, history, session, ep, mdl, key, True, bool(ui.get("tz_ok")))
    history, session = list(out[0]), out[2]
    asked = next((a.get("asked") for a in reversed(list(session.actions)[n_act0:])
                  if isinstance(a, dict) and a.get("asked")), None) if session is not None else None
    if asked and set(map(str, asked)) == {"6"} and not ui.get("tz_ok") and not _new_result(before, session):
        # everything else is settled: the one question only the analyst can answer, in plain words
        ui["tz_wait"] = text
        history = history[:n0] + [[text, "One question before I start: were all the variables "
                                         "you want to adjust for recorded at the start of "
                                         "follow-up (for example, at transplant)? Reply **yes** "
                                         "or **no**."]]
        return history, None, session, ui
    if not _new_result(before, session):
        for i in range(n0, len(history)):
            if isinstance(history[i][1], str):
                history[i][1] = _plain_turn(history[i][1])
    if answered_yes and len(history) > n0:
        # the request was already shown; the reply follows the analyst's "yes"
        history[n0] = ["yes", history[n0][1]]
    if _new_result(before, session):
        # this turn's replies carried the technical cards and the full report;
        # in the chat they become one plain summary (the report is the PDF)
        new = history[n0:]
        user = next((u for u, _ in new if u), "yes" if answered_yes else text)
        history = history[:n0] + [[user, _summary_reply(session)]]
        _step("Preparing the PDF report")
        pdf = _report_pdf(session)
        if pdf:
            history.append([None, (pdf,)])
        # the Kaplan-Meier curve is in the report; the chat shows it only when the analyst asked
        for u, b in new:
            if isinstance(b, (tuple, list)) and b and str(b[0]).endswith("km_curve.png"):
                history.append([None, (b[0],)])
                break
    return history, None, session, ui


def chat_reset(session=None):
    _purge(session)
    h, s, *_ = start_session()
    return h, None, s, {}


GREETING = "📊 What external data should your cohort learn from today?"
EXAMPLE_REQUEST = EXAMPLE_QUERY + " All of these were recorded at transplant."


_WAIT = "→ Reading your message…"


def show_pending(mm, history):
    """Show the message at once, with a waiting line, before the slow turn runs."""
    mm = mm or {}
    text = (mm.get("text") or "").strip()
    files = [f if isinstance(f, str) else (f.get("path") if isinstance(f, dict) else getattr(f, "name", ""))
             for f in (mm.get("files") or [])]
    shown = "\n\n".join(x for x in [("📎 " + ", ".join(f"`{Path(f).name}`" for f in files)) if files else "",
                                       text] if x)
    h = list(history or []) + [[shown or "…", _WAIT]]
    return (gr.update(value=h, visible=True), None, mm,
            gr.update(visible=False), gr.update(visible=False))


def _render_progress(steps: List[str]) -> str:
    if not steps:
        return "→ Starting…"
    done = [f"✓ {x}" for x in steps[:-1]]
    return "\n\n".join(done + [f"→ {steps[-1]}…"])


def chat_turn_ui(mm, history, session, ui):
    history = list(history or [])
    shown = None
    if history and history[-1][1] == _WAIT:
        shown = history.pop()[0]
    steps: List[str] = []
    ctx = contextvars.copy_context()
    ctx.run(_PROGRESS.set, steps)
    partial = [""]
    ctx.run(_PARTIAL.set, partial)
    box: List[Any] = []

    def work():
        try:
            box.append(ctx.run(chat_turn, mm, list(history), session, ui))
        except Exception as exc:  # shown in the chat, never a crash of the page
            box.append(exc)
    t = threading.Thread(target=work, daemon=True)
    t.start()
    while t.is_alive():
        if shown is not None:
            live = partial[0] or _render_progress(steps)
            yield (gr.update(value=history + [[shown, live]], visible=True),
                   gr.skip(), gr.skip(), gr.skip(), gr.update(visible=False), gr.update(visible=False))
        t.join(0.25 if partial[0] else 1.0)
    r = box[0] if box else RuntimeError("no result")
    if isinstance(r, Exception):
        h = history + [[shown, f"Something went wrong: {type(r).__name__}: {r}"]]
        yield (gr.update(value=h, visible=True), None, session, ui,
               gr.update(visible=False), gr.update(visible=False))
        return
    h, b, s2, u = r
    yield (gr.update(value=h, visible=True), b, s2, u,
           gr.update(visible=False), gr.update(visible=False))


def example_pending(history):
    return show_pending({"text": EXAMPLE_REQUEST, "files": []}, history)


def reset_ui(session=None):
    h, box, s, u = chat_reset(session)
    return (gr.update(value=[], visible=False), box, s, u,
            gr.update(visible=True), gr.update(visible=True))


with gr.Blocks(title="BregSurv", theme=_THEME, css=_CSS,
               js="() => { (" + _FORCE_LIGHT_JS + ")(); }") as demo:
    with gr.Row(elem_id="topbar"):
        gr.HTML("<div id='brand'>BregSurv</div>")
        new_btn = gr.Button("New analysis", size="sm", elem_id="newbtn", variant="secondary")
    session_state = gr.State(None, delete_callback=_purge)
    ui_state = gr.State({})
    greeting = gr.HTML(f"<h1>{GREETING}</h1>", elem_id="greeting")
    chatbot = gr.Chatbot(height=620, show_label=False, elem_id="chat", type="tuples",
                         show_copy_button=False, visible=False)
    msg_in = gr.MultimodalTextbox(
        placeholder="Ask anything, or attach your data",
        file_count="multiple", show_label=False, elem_id="msg_in", sources=["upload"])
    with gr.Row(elem_id="example_row") as example_row:
        example_btn = gr.Button("Try the example data", size="sm", elem_id="example_btn",
                                variant="secondary")
    gr.HTML("<div id='foot'>"
            + ("Public demo with synthetic data. For real patient data, run it on your own computer."
               if DEPLOYMENT_MODE == "demo" else "Running on this computer; your data stays here.")
            + "</div>")

    demo.load(lambda: start_session()[1], inputs=None, outputs=[session_state])
    pending_state = gr.State(None)
    _outs = [chatbot, msg_in, session_state, ui_state, greeting, example_row]
    _pend = [chatbot, msg_in, pending_state, greeting, example_row]
    msg_in.submit(show_pending, inputs=[msg_in, chatbot], outputs=_pend).then(
        chat_turn_ui, inputs=[pending_state, chatbot, session_state, ui_state], outputs=_outs)
    example_btn.click(example_pending, inputs=[chatbot], outputs=_pend).then(
        chat_turn_ui, inputs=[pending_state, chatbot, session_state, ui_state], outputs=_outs)
    new_btn.click(reset_ui, inputs=[session_state], outputs=_outs)


def _resolve_auth():
    user = os.environ.get("BREGSURV_AUTH_USER", "").strip()
    pw = os.environ.get("BREGSURV_AUTH_PASS", "").strip()
    return (user, pw) if user and pw else None


if __name__ == "__main__":
    # load the retrieval models before the first message, beside the page starting up
    threading.Thread(target=__import__("bregsurv_agent.retrieval", fromlist=["warm"]).warm,
                     daemon=True).start()
    demo.queue()
    _auth = _resolve_auth()
    if _auth is not None:
        print(f"[app] Gradio auth enabled (user={_auth[0]})", flush=True)
    demo.launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        inbrowser=False,
        show_error=True,
        show_api=False,
        auth=_auth,
    )
