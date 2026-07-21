"""Declarative tool registry + uniform dispatcher.

Each entry in ``TOOL_REGISTRY`` says, for one of the 33 BregSurv MCP
tools, (a) which R script implements it and (b) which post-processing
helpers from :mod:`bregsurv_agent.helpers` to apply to the R result.
``dispatch(name, **kwargs)`` does the matching work that each per-tool
function does in ``mcp/server.py``.

Mirror invariant: this file is the per-tool dispatch contract that must
match ``mcp/server.py``'s 33 ``@mcp.tool()`` functions. If a tool gains
or drops a post-processing wrapper, update both.

Post-processing flags:

  ``plot_hint``           → :func:`helpers.attach_plot_hint(result)`
  ``plot_hint_highdim``   → :func:`helpers.attach_plot_hint(result, highdim=True)`
  ``ridge_speed``         → :func:`helpers.attach_ridge_speed_notice(result)`
  ``enet_speed``          → :func:`helpers.attach_enet_speed_notice(result)`
  ``resolve_eta``         → before the R call, default ``eta``=None to 0.0
                            and capture a notice attached via
                            :func:`helpers.attach_eta_default_notice` AFTER
                            other post-processing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from . import helpers
from . import runner


# -- Tool registry -----------------------------------------------------------
# Each value is (r_script_filename, frozenset_of_post_flags).

TOOL_REGISTRY: Dict[str, Tuple[str, FrozenSet[str]]] = {
    # Helpers / wizard (no post-processing).
    "inspect_data":       ("inspect_data.R",       frozenset()),
    "generate_eta":       ("generate_eta.R",       frozenset()),
    "start_analysis":     ("start_analysis.R",     frozenset()),

    # Cox — base fit (no post-processing).
    "fit_coxkl":          ("fit_coxkl.R",          frozenset()),
    "fit_cox_indi":       ("fit_cox_indi.R",       frozenset()),
    "fit_cox_MDTL":       ("fit_cox_MDTL.R",       frozenset()),
    "fit_coxkl_ties":     ("fit_coxkl_ties.R",     frozenset()),

    # Cox — base cv (plot hint).
    "cv_coxkl":           ("cv_coxkl.R",           frozenset({"plot_hint"})),
    "cv_coxkl_ties":      ("cv_coxkl_ties.R",      frozenset({"plot_hint"})),
    "cv_cox_MDTL":        ("cv_cox_MDTL.R",        frozenset({"plot_hint"})),
    "cv_cox_indi":        ("cv_cox_indi.R",        frozenset({"plot_hint"})),

    # Cox — ridge.
    "fit_coxkl_ridge":    ("fit_coxkl_ridge.R",    frozenset({"resolve_eta", "ridge_speed"})),
    "cv_coxkl_ridge":     ("cv_coxkl_ridge.R",     frozenset({"plot_hint_highdim", "ridge_speed"})),
    "fit_cox_MDTL_ridge": ("fit_cox_MDTL_ridge.R", frozenset({"resolve_eta", "ridge_speed"})),
    "cv_cox_MDTL_ridge":  ("cv_cox_MDTL_ridge.R",  frozenset({"plot_hint_highdim", "ridge_speed"})),

    # Cox — enet.
    "fit_coxkl_enet":     ("fit_coxkl_enet.R",     frozenset({"resolve_eta", "enet_speed"})),
    "fit_cox_MDTL_enet":  ("fit_cox_MDTL_enet.R",  frozenset({"resolve_eta", "enet_speed"})),
    "fit_cox_indi_enet":  ("fit_cox_indi_enet.R",  frozenset({"enet_speed"})),
    "cv_coxkl_enet":      ("cv_coxkl_enet.R",      frozenset({"plot_hint_highdim", "enet_speed"})),
    "cv_cox_MDTL_enet":   ("cv_cox_MDTL_enet.R",   frozenset({"plot_hint_highdim", "enet_speed"})),
    "cv_cox_indi_enet":   ("cv_cox_indi_enet.R",   frozenset({"plot_hint_highdim", "enet_speed"})),

    # NCC — base fit.
    "fit_ncckl":          ("fit_ncckl.R",          frozenset()),
    "fit_ncc_indi":       ("fit_ncc_indi.R",       frozenset()),
    "fit_ncc_MDTL":       ("fit_ncc_MDTL.R",       frozenset()),

    # NCC — base cv (plot hint).
    "cv_ncckl":           ("cv_ncckl.R",           frozenset({"plot_hint"})),
    "cv_ncc_indi":        ("cv_ncc_indi.R",        frozenset({"plot_hint"})),
    "cv_ncc_MDTL":        ("cv_ncc_MDTL.R",        frozenset({"plot_hint"})),

    # NCC — enet (no ridge by intentional design).
    "fit_ncckl_enet":     ("fit_ncckl_enet.R",     frozenset({"resolve_eta", "enet_speed"})),
    "fit_ncc_MDTL_enet":  ("fit_ncc_MDTL_enet.R",  frozenset({"resolve_eta", "enet_speed"})),
    "fit_ncc_indi_enet":  ("fit_ncc_indi_enet.R",  frozenset({"enet_speed"})),
    "cv_ncckl_enet":      ("cv_ncckl_enet.R",      frozenset({"plot_hint_highdim", "enet_speed"})),
    "cv_ncc_MDTL_enet":   ("cv_ncc_MDTL_enet.R",   frozenset({"plot_hint_highdim", "enet_speed"})),
    "cv_ncc_indi_enet":   ("cv_ncc_indi_enet.R",   frozenset({"plot_hint_highdim", "enet_speed"})),
}


# -- Schemas -----------------------------------------------------------------

_SCHEMAS_PATH = Path(__file__).resolve().parent / "schemas.json"


def load_schemas() -> List[dict]:
    """Return the cached OpenAI tool-schema list (one entry per tool)."""
    with open(_SCHEMAS_PATH, encoding="utf-8") as f:
        return json.load(f)


# -- Context-aware tool subsetting --------------------------------------------
#
# The 33 tool schemas cost ~18K tokens — the single largest fixed item in
# every request, eating ~56% of Qwen 7B's 32K window before the user says
# anything. But once we have auto-inspected the data file (Stage 4h), the
# data structure already determines which tool FAMILY is admissible. There
# is no reason to send the LLM the NCC tool schemas when the data is Cox
# cohort shape (and vice-versa) — those tools would crash R anyway (the
# Stage 4k "argument lengths differ" failure mode). Subsetting the schema
# list to the admissible family (and, when unambiguous, dimensionality
# regime) before the request both cuts tokens AND shrinks the routing
# decision space, which raises small-model routing accuracy.
#
# Two axes:
#   * Family (Cox vs NCC) — DEFINITIVE from field names; always applied.
#   * Dimensionality (base vs ridge/enet) — CONSERVATIVE; applied only in
#     unambiguous cases so a legitimate request is never blocked.
#
# Helpers (inspect_data / generate_eta / start_analysis) are ALWAYS kept:
# inspect_data is the documented self-recovery path for the ASCII gate
# (Stage 4g), and start_analysis is the wizard escape for any query the
# subset can't satisfy.

_HELPER_TOOLS: FrozenSet[str] = frozenset(
    {"inspect_data", "generate_eta", "start_analysis"}
)


def _tool_family(name: str) -> str:
    """Return "ncc", "cox", or "helper" for a registry tool name."""
    if name in _HELPER_TOOLS:
        return "helper"
    low = name.lower()
    if "ncc" in low:
        return "ncc"
    if "cox" in low:
        return "cox"
    return "helper"


def _is_highdim_tool(name: str) -> bool:
    """True for the ridge / enet (high-dimensional) tool variants."""
    return "_ridge" in name or "_enet" in name


def classify_data_family(inspect_result: Any) -> "Optional[str]":
    """Return "ncc" | "cox" | None from an inspect_data result.

    Field-name signatures (matches the deployed Stage 4k heuristic
    verbatim so behaviour does not regress): NCC = $y + $stratum with no
    $time/$status/$delta; Cox = $time + $status/$delta with no $y+$stratum.
    Anything else (individual two-source, MDTL with vcov, mixed) → None.
    """
    if not isinstance(inspect_result, dict):
        return None
    blob = json.dumps(inspect_result).lower()
    has_y = '"y"' in blob
    has_stratum = '"stratum"' in blob
    has_time = '"time"' in blob
    has_status = '"status"' in blob
    has_delta = '"delta"' in blob
    is_ncc = (has_y and has_stratum) and not (has_time and (has_status or has_delta))
    is_cox = (has_time and (has_status or has_delta)) and not (has_y and has_stratum)
    if is_ncc:
        return "ncc"
    if is_cox:
        return "cox"
    return None


_DIM_RE = re.compile(r"(\d+)\s*x\s*(\d+)")


def _covariate_dims(obj: Any) -> "Optional[Tuple[int, int]]":
    """Depth-first search for a ``z`` field; parse its "(n)x(p)" dims.

    ``inspect_data`` reports the covariate matrix as either a plain string
    ("matrix 1000x6 (double)") or a dict with a ``.kind`` string
    ("data.frame 100x6"). Returns ``(n_rows, p_cols)`` or ``None``.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "z":
                dims = _parse_dims(v)
                if dims:
                    return dims
            found = _covariate_dims(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _covariate_dims(item)
            if found:
                return found
    return None


def _parse_dims(v: Any) -> "Optional[Tuple[int, int]]":
    s = v if isinstance(v, str) else (v.get(".kind") if isinstance(v, dict) else None)
    if not isinstance(s, str):
        return None
    m = _DIM_RE.search(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def classify_dimensionality(inspect_result: Any) -> "Optional[str]":
    """Return "lowdim" | "highdim" | None — conservatively.

    Only the unambiguous extremes are classified, so a borderline case
    (where a user might legitimately want either base or regularized
    tools) keeps the full family and is never blocked:

      * ``lowdim``  — p <= 10 AND n >= 3p  (classical low-dimensional Cox;
        ridge/enet are pointless → safe to drop them)
      * ``highdim`` — p >= n  (base Cox cannot fit; safe to drop base)
      * otherwise   — None  (keep both base and regularized variants)
    """
    if not isinstance(inspect_result, dict):
        return None
    dims = _covariate_dims(inspect_result.get("structure", inspect_result))
    if not dims:
        return None
    n, p = dims
    if p <= 10 and n >= 3 * p:
        return "lowdim"
    if p >= n:
        return "highdim"
    return None


def _tool_penalty(name: str) -> str:
    """"none" | "ridge" | "enet" -- which penalty a tool actually applies."""
    if name.endswith("_ridge"):
        return "ridge"
    if name.endswith("_enet"):
        return "enet"
    return "none"


def select_tool_schemas(
    all_schemas: List[dict],
    inspect_result: Any,
    family_override: "Optional[str]" = None,
    method_override: "Optional[str]" = None,
    penalty_override: "Optional[str]" = None,
) -> "Tuple[List[dict], Dict[str, Any]]":
    """Return (subset_of_schemas, decision_metadata) for one request.

    ``family_override`` ("cox" / "ncc"), when supplied by the UI (which
    knows the family definitively from the user's dataset selection),
    takes precedence over the inspect-result heuristic. Otherwise the
    family is classified from the data structure.

    ``method_override`` ("kl") narrows further to the KL-divergence
    tools only (names containing ``kl``), dropping the individual-data
    (``_indi``) and Mahalanobis (``_MDTL``) tools. The deployment UI sets
    this because its only external-information option is a coefficient
    vector → KL. Without it, a 7B model seeing a ``$train``/``$test``
    split mistakes ``$test`` for an external cohort and picks an
    ``_indi`` tool (observed 2026-05-30, NCC cv).

    ``penalty_override`` ("none" / "ridge" / "enet") narrows to the tools
    that actually apply that penalty. Supply it whenever the request fixes
    the penalty, which the deployment UI always knows. Dimensionality
    classification deliberately leaves both base and regularized tools
    exposed in the borderline band (neither p<=10 nor p>=n), and in that
    band nothing otherwise enforced the user's stated penalty: on real
    registry data with p=60, n=4865, a request for ridge was answered by
    the *unpenalized* estimator, and the model then reported in prose that
    ridge had been applied (observed 2026-07-20, KP). Selecting the penalty
    is a deterministic check on a stated requirement, so it belongs in the
    harness rather than in the model's discretion.

    ``decision_metadata`` is recorded in the trace for audit. When the
    family is ambiguous (None and no override), the full 33-tool list is
    returned unchanged (safe fallback — e.g. individual / MDTL-vcov
    data, or no inspect result available).
    """
    family = family_override or classify_data_family(inspect_result)
    dim = classify_dimensionality(inspect_result) if family else None

    if family is None:
        kept = [s["function"]["name"] for s in all_schemas]
        return all_schemas, {
            "family": None, "dimensionality": None, "method": None,
            "n_exposed": len(kept), "n_total": len(all_schemas),
            "names": kept,
        }

    keep: List[str] = []
    for name in TOOL_REGISTRY:
        fam = _tool_family(name)
        if fam == "helper":
            keep.append(name)
            continue
        if fam != family:
            continue
        if dim == "lowdim" and _is_highdim_tool(name):
            continue
        if dim == "highdim" and not _is_highdim_tool(name):
            continue
        if method_override == "kl" and "kl" not in name:
            continue
        if penalty_override and _tool_penalty(name) != penalty_override:
            continue
        keep.append(name)

    keep_set = set(keep)
    subset = [s for s in all_schemas if s["function"]["name"] in keep_set]
    return subset, {
        "family": family, "dimensionality": dim, "method": method_override,
        "penalty": penalty_override,
        "n_exposed": len(subset), "n_total": len(all_schemas),
        "names": [s["function"]["name"] for s in subset],
    }


# -- ASCII validation for R expression args ----------------------------------
#
# Qwen 2.5-7B-AWQ has a documented Chinese-language bias: when uncertain
# about R field names, it falls back to its Chinese training distribution
# and emits things like `dataset$生存时间` / `dataset$事件发生`. These are
# never valid R identifiers (R syntax requires ASCII-letter / digit / dot
# / underscore in identifiers). Rather than relying on the LLM to comply
# with a soft prompt rule, we enforce ASCII at the dispatcher boundary:
# any `*_expr` arg containing a non-ASCII character is rejected with a
# structured error that explicitly tells the agent to call `inspect_data`
# before retrying. The next turn's prompt then contains this error, and
# the agent self-corrects.
#
# Note: we do NOT validate `data_path` (a Chinese filesystem path is
# legitimate) or descriptive free-text args. Only the R-expression args
# where non-ASCII guarantees a downstream R parse error.

_EXPR_ARGS_REQUIRE_ASCII: FrozenSet[str] = frozenset({
    # Cohort / NCC core fields
    "z_expr", "time_expr", "delta_expr", "y_expr", "stratum_expr",
    # External-info fields
    "beta_expr", "vcov_expr", "RS_expr", "beta_initial_expr",
    # Two-source individual-data variants (_int / _ext)
    "z_int_expr", "time_int_expr", "delta_int_expr",
    "y_int_expr", "stratum_int_expr",
    "z_ext_expr", "time_ext_expr", "delta_ext_expr",
    "y_ext_expr", "stratum_ext_expr",
    # NCC-specific c-index stratum (Brier / CIndex CV)
    "c_index_stratum_expr",
})


def _validate_ascii_in_exprs(name: str, kwargs: Dict[str, Any]) -> dict:
    """If any `*_expr` arg contains non-ASCII, return a structured error.

    Returns an empty dict when validation passes (clean dispatch can proceed).
    The error message instructs the LLM to call `inspect_data` first.
    """
    offenders: Dict[str, str] = {}
    for arg_name, val in kwargs.items():
        if arg_name not in _EXPR_ARGS_REQUIRE_ASCII:
            continue
        if not isinstance(val, str):
            continue
        try:
            val.encode("ascii")
        except UnicodeEncodeError:
            offenders[arg_name] = val
    if not offenders:
        return {}
    return {
        "status": "error",
        "class": "NonAsciiIdentifier",
        "where": "bregsurv_agent.tools.dispatch",
        "message": (
            f"Tool {name!r} was called with non-ASCII characters in R "
            f"field expressions: {offenders}. R variable names MUST be "
            f"valid R syntax in ASCII only — never Chinese, Japanese, "
            f"Korean, or other non-Latin scripts. Do NOT guess field "
            f"names. Call `inspect_data` on the data file FIRST to "
            f"discover the actual R object structure, then retry this "
            f"tool with the verbatim field names you observe (they will "
            f"be ASCII)."
        ),
        "offending_args": offenders,
        "remediation": "call_inspect_data_then_retry",
    }


# -- Dispatch ----------------------------------------------------------------

def dispatch(name: str, **kwargs: Any) -> dict:
    """Run one tool by name with the given kwargs; return the R result dict.

    Mirrors the per-tool wrappers in ``mcp/server.py``:

    0. Reject non-ASCII characters in any ``*_expr`` argument with a
       structured error (forces the agent to call ``inspect_data`` first
       instead of hallucinating non-ASCII field names — see Stage 4g).
    1. If ``resolve_eta`` flag set and ``eta`` arg is None / missing, default
       to 0.0 and capture an eta-default notice to attach later.
    2. Build payload = kwargs (R scripts ignore extra keys, but we drop
       ``_*``-prefixed internal keys defensively).
    3. Call :func:`runner.run_r(script, payload)`.
    4. Apply post-processing helpers in the right order (matches
       server.py: speed-notice wraps eta-default notice; plot hint wraps
       speed notice for cv_*_enet/_ridge tools).
    """
    if name not in TOOL_REGISTRY:
        return {
            "status": "error",
            "message": f"Unknown tool: {name!r}. "
                       f"Known: {sorted(TOOL_REGISTRY)}",
            "class": "UnknownTool",
            "where": "bregsurv_agent.tools.dispatch",
        }

    # Step 0: ASCII gate (Stage 4g defense against Qwen's Chinese
    # hallucination on field-name args).
    ascii_err = _validate_ascii_in_exprs(name, kwargs)
    if ascii_err:
        return ascii_err

    script, flags = TOOL_REGISTRY[name]

    # Step 1: eta-default resolution.
    eta_notice = None
    if "resolve_eta" in flags:
        eta = kwargs.get("eta")
        if eta is None:
            kwargs["eta"] = 0.0
            _, eta_notice = helpers.resolve_eta_with_notice(None)
        else:
            kwargs["eta"] = float(eta)

    # Step 2: payload. Strip internal-only keys (none expected from LLM,
    # but be defensive against hand-built test inputs).
    payload = {k: v for k, v in kwargs.items() if not k.startswith("_")}

    # Step 3: R call.
    result = runner.run_r(script, payload)

    # Step 4: post-processing in server.py order. For cv_*_enet / cv_*_ridge,
    # server.py applies speed-notice OUTSIDE plot-hint (speed-notice wraps
    # plot-hint), so we apply plot-hint first then speed-notice. For
    # fit_*_ridge / fit_*_enet, server.py applies eta-default OUTSIDE
    # speed-notice, so eta-default goes last.
    if "plot_hint" in flags:
        result = helpers.attach_plot_hint(result, highdim=False)
    elif "plot_hint_highdim" in flags:
        result = helpers.attach_plot_hint(result, highdim=True)

    if "ridge_speed" in flags:
        result = helpers.attach_ridge_speed_notice(result)
    elif "enet_speed" in flags:
        result = helpers.attach_enet_speed_notice(result)

    if eta_notice is not None:
        result = helpers.attach_eta_default_notice(result, eta_notice)

    return result
