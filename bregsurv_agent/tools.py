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
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Tuple

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


# -- Dispatch ----------------------------------------------------------------

def dispatch(name: str, **kwargs: Any) -> dict:
    """Run one tool by name with the given kwargs; return the R result dict.

    Mirrors the per-tool wrappers in ``mcp/server.py``:

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
