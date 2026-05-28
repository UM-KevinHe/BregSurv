"""Tool-result post-processing helpers.

Mirror of the ``_attach_*`` / ``_resolve_eta_with_notice`` helpers in
``mcp/server.py``. The agent's ``tools.dispatch`` calls these the same
way the MCP server's per-tool wrappers do. Keep in sync with server.py.

Why these exist (also in server.py docstrings; condensed here):

* ``attach_plot_hint`` — turns a successful ``cv_*`` result into a
  ``_followup_offer_plot``-bearing result so the LLM is steered toward
  emitting a plot artifact next, with correct axis labels per criterion.
* ``resolve_eta_with_notice`` — handles the Python-side default of
  ``eta=0`` for ``fit_*_ridge`` / ``fit_*_enet`` when the user omitted
  ``eta`` entirely. Returns a notice so the LLM surfaces this default to
  the user (R-side warnings do not cross the JSON bridge).
* ``attach_ridge_speed_notice`` / ``attach_enet_speed_notice`` — set
  expectations for high-dim CV runtime.
* ``attach_eta_default_notice`` — only injects when ``notice`` is not None.
"""
from __future__ import annotations

from typing import Optional, Tuple


def attach_plot_hint(result: dict, highdim: bool = False) -> dict:
    """Inject ``_followup_offer_plot`` into a successful cv_* return."""
    if isinstance(result, dict) and result.get("status") == "ok":
        result["_followup_offer_plot"] = (
            "POST-CALL ACTION (REQUIRED): after you summarise these CV "
            "results to the user, your VERY FIRST follow-up suggestion "
            "must be to offer a CV-path plot ('需要我把 CV 曲线画出来吗？ "
            "/ Want me to plot the CV path?'). Do this BEFORE any other "
            "follow-up (grid refinement, alternative criteria, etc.). "
            "Skip the offer only if the user has already declined a plot "
            "earlier in this conversation. "
            "\n\n"
            "If the user agrees: draw an inline chart from the data "
            "already in this very tool result. Use: x = `etas` array, "
            "y = `cv_metric.values` array, plus a vertical marker at "
            "`best.best_eta` and a horizontal reference line at the "
            "y-value corresponding to eta=0."
            "\n\n"
            "Critical: read the `criteria` field of this result to set "
            "axis labels and best-eta direction CORRECTLY. The package "
            "has two criterion families — Cox-family (used by cv_coxkl* "
            "/ cv_cox_*) and NCC-family (used by cv_ncckl / cv_ncc_*) — "
            "and they MUST NOT be conflated. Mappings:"
            "\n  Cox family:"
            "\n  * 'V&VH'               -> y-axis 'Loss (V&VH)';   smaller is better; best_eta = argmin"
            "\n  * 'LinPred'            -> y-axis 'Loss (LinPred)';smaller is better; best_eta = argmin"
            "\n  * 'CIndex_pooled'      -> y-axis 'C Index';       larger  is better; best_eta = argmax"
            "\n  * 'CIndex_foldaverage' -> y-axis 'C Index';       larger  is better; best_eta = argmax"
            "\n  NCC family:"
            "\n  * 'loss'               -> y-axis 'Loss';          smaller is better; best_eta = argmin"
            "\n  * 'Brier'              -> y-axis 'Brier Score';   smaller is better; best_eta = argmin"
            "\n  * 'AUC'                -> y-axis 'AUC';           larger  is better; best_eta = argmax"
            "\n  * 'CIndex'             -> y-axis 'C Index';       larger  is better; best_eta = argmax"
            "\nUse the `cv_metric.name` field as a sanity cross-check. "
            "Mislabelling loss vs index is the single biggest way to "
            "confuse the user."
        )
        if highdim:
            result["_followup_offer_plot"] += (
                "\n\n"
                "HIGHDIM NOTE (this tool is cv_*_ridge or cv_*_enet): the "
                "underlying CV is over a 2D (eta x lambda) grid. The "
                "`cv_metric.values` array you plot is ALREADY the metric "
                "AT each eta's best lambda (one number per eta, not a 2D "
                "surface), so the plot stays 1D — same shape as base cv_* "
                "tools. Per-eta best-lambda values live in "
                "`best_lambda_per_eta` (parallel to `etas`); annotate "
                "those in tooltips so the user sees what lambda was "
                "chosen at each eta. Global optimum is `best.best_eta` + "
                "`best.best_lambda`. Do NOT attempt a 2D heatmap unless "
                "the user explicitly asks for the full grid."
            )
    return result


def resolve_eta_with_notice(
    eta: Optional[float],
) -> Tuple[float, Optional[str]]:
    """Default-eta-to-0 policy for fit_*_ridge / fit_*_enet (KL/MDTL).

    If ``eta is None``, return ``(0.0, notice_string)`` so the dispatcher
    payload has a concrete eta and the result can carry a
    ``_notice_eta_default`` field that the LLM MUST relay to the user.
    Otherwise return ``(eta, None)``.

    Why MCP defaults rather than R-side default: the R function warns
    when eta is NULL but warnings do not survive the JSON bridge to the
    LLM; without this notice, eta=0 would silently strip away external
    borrowing — a correctness-relevant surprise.
    """
    if eta is None:
        notice = (
            "ETA-DEFAULT NOTICE (REQUIRED to surface): the user did NOT "
            "supply `eta`, so this tool defaulted to eta = 0. With eta = "
            "0 the model does NOT borrow any external information and is "
            "equivalent to a plain ridge / enet fit (i.e. external β is "
            "ignored). Tell the user this explicitly and ask them to "
            "confirm — typical workflows want eta > 0 to actually use "
            "the external information they supplied. Suggest a starting "
            "grid or single value (e.g. eta=0.5 or etas=[0, 0.5, 1, 2])."
        )
        return 0.0, notice
    return float(eta), None


def attach_ridge_speed_notice(result: dict) -> dict:
    """Attach ``_notice_speed_slow`` to ridge-tool returns.

    Ridge fits run a full lambda path per eta and (in CV) per fold, with
    no sparsity to short-circuit. CV at default settings on highdim data
    can take 30s+.
    """
    if isinstance(result, dict) and result.get("status") == "ok":
        result["_notice_speed_slow"] = (
            "SPEED NOTICE (surface to user): ridge fits run a full "
            "lambda path with no sparsity short-circuit, and CV "
            "multiplies this by nfolds × n_etas. On high-dimensional "
            "data even the shipped example datasets can take 30s+ for "
            "cv with default settings. If runtime feels slow: "
            "(a) reduce `nlambda` (try 20-30 instead of default 100); "
            "(b) use a smaller `etas` grid for cv_*_ridge "
            "(e.g. 3-5 values instead of 10+); "
            "(c) lower `nfolds` to 3 for exploratory runs; "
            "(d) try the enet variant if variable selection is "
            "acceptable (enet's active-set machinery is often faster "
            "than ridge on sparse signal)."
        )
    return result


def attach_enet_speed_notice(result: dict) -> dict:
    """Attach ``_notice_speed_slow`` to enet-tool returns."""
    if isinstance(result, dict) and result.get("status") == "ok":
        result["_notice_speed_slow"] = (
            "SPEED NOTICE (surface to user): enet fits a full lambda "
            "path via active-set coordinate descent — typically faster "
            "than ridge on sparse signal, but high-dim + CV still scales "
            "with nfolds x n_etas x nlambda. If runtime feels slow: "
            "(a) reduce `nlambda` (try 20-30 instead of default 100); "
            "(b) for cv, use a smaller `etas` grid (3-5 values); "
            "(c) lower `nfolds` to 3 for exploratory runs; "
            "(d) for fit_coxkl_enet / fit_cox_MDTL_enet, increase "
            "`alpha` toward 1.0 for stronger sparsity — fewer active "
            "coefficients = faster convergence. For fit_cox_indi_enet, "
            "alpha is already 1.0 (lasso) by default."
        )
    return result


def attach_eta_default_notice(
    result: dict, notice: Optional[str]
) -> dict:
    """Inject ``_notice_eta_default`` only when Python defaulted eta=0."""
    if (notice is not None
            and isinstance(result, dict)
            and result.get("status") == "ok"):
        result["_notice_eta_default"] = notice
    return result
