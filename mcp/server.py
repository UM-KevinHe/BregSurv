"""
SurvBregDiv MCP server.

FastMCP server that bridges Claude Desktop (or any MCP client) to the
SurvBregDiv R package. Each tool shells out to Rscript via a temp JSON
file; no R logic lives in this module.

Tool surface (see individual @mcp.tool docstrings for parameters):
  * start_analysis — guided wizard; recommended entry point for users.
  * inspect_data, generate_eta — small helpers.
  * fit_*, cv_* — Cox & NCC model fitters and their CV companions,
    each with low-dim, ridge, and elastic-net variants where applicable.

Architecture invariants — DO NOT change without re-verifying in Claude
Desktop (see CLAUDE.md "Phase 4" section for the failure modes):
  1. `subprocess.run(..., stdin=subprocess.DEVNULL)` on every Rscript
     call. Without this, Rscript inherits Claude Desktop's never-writing
     stdin and stalls on TTY probes (readline).
  2. Rscript flags must be `--no-save --no-restore --no-init-file`.
     `--vanilla` implies `--no-environ` which suppresses `R_LIBS_USER`
     and breaks user-installed packages on Windows.

Run for local debugging (outside Claude Desktop):
    python server.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------
# Paths and Rscript discovery
# --------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
R_SCRIPTS = SCRIPT_DIR / "r_scripts"


def _find_rscript() -> str:
    """Locate an Rscript executable.

    Resolution order:
      1. $SURVBREGDIV_RSCRIPT (explicit override)
      2. "Rscript" on PATH
      3. Highest-versioned R-x.y.z under C:\\Program Files\\R\\
    """
    override = os.environ.get("SURVBREGDIV_RSCRIPT")
    if override and Path(override).exists():
        return override

    on_path = shutil.which("Rscript") or shutil.which("Rscript.exe")
    if on_path:
        return on_path

    for base in (Path(r"C:\Program Files\R"), Path(r"C:\Program Files (x86)\R")):
        if not base.exists():
            continue
        candidates = sorted(
            (d for d in base.iterdir() if d.is_dir() and d.name.startswith("R-")),
            key=lambda d: d.name,
            reverse=True,
        )
        for d in candidates:
            exe = d / "bin" / "Rscript.exe"
            if exe.exists():
                return str(exe)

    raise FileNotFoundError(
        "Rscript not found. Install R (https://cran.r-project.org/), or set "
        "the SURVBREGDIV_RSCRIPT environment variable to the full path of "
        "Rscript(.exe)."
    )


# --------------------------------------------------------------------------
# Rscript bridge
# --------------------------------------------------------------------------

def _run_r(script_name: str, payload: dict, timeout_s: int = 600) -> dict:
    """Invoke an R script via a temp-file JSON handshake.

    Writes `payload` to a temp input.json, runs
        Rscript --no-save --no-restore --no-init-file <script> <in.json> <out.json>
    and returns the parsed contents of output.json. If the R script fails to
    produce output, returns a structured {status:"error",...} dict so the MCP
    tool never throws.

    Two non-obvious flag choices:
      * --no-save --no-restore --no-init-file (NOT --vanilla). `--vanilla`
        also implies `--no-environ`, which suppresses R_LIBS_USER. When the
        required R packages (jsonlite, SurvBregDiv) are installed only in
        the user library (default on Windows via `install.packages()`), R
        started with --vanilla cannot find them.
      * stdin=subprocess.DEVNULL. Without this, the Rscript child inherits
        the parent Python's stdin (which, when this server runs under
        Claude Desktop, is bound to the MCP stdio channel). R's startup
        can stall on that inherited stdin.
    """
    script_path = R_SCRIPTS / script_name
    if not script_path.exists():
        return {
            "status": "error",
            "message": f"R script not found: {script_path}",
            "class": "FileNotFoundError",
            "where": "server.py:_run_r",
        }

    try:
        rscript = _find_rscript()
    except FileNotFoundError as e:
        return {
            "status": "error",
            "message": str(e),
            "class": "FileNotFoundError",
            "where": "server.py:_find_rscript",
        }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".in.json", delete=False, encoding="utf-8"
    ) as fin:
        json.dump(payload, fin, ensure_ascii=False)
        in_path = fin.name
    out_path = in_path.replace(".in.json", ".out.json")

    try:
        cmd = [rscript, "--no-save", "--no-restore", "--no-init-file",
               str(script_path), in_path, out_path]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
        )

        if Path(out_path).exists():
            try:
                with open(out_path, encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "message": f"R output was not valid JSON: {e}",
                    "class": "JSONDecodeError",
                    "where": script_name,
                    "stderr": proc.stderr.strip()[:2000],
                }

        return {
            "status": "error",
            "message": (proc.stderr.strip() or
                        "Rscript exited without producing output"),
            "class": "RscriptCrash",
            "where": script_name,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip()[:2000],
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": f"Rscript timed out after {timeout_s}s",
            "class": "TimeoutExpired",
            "where": script_name,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"{type(e).__name__}: {e}",
            "class": type(e).__name__,
            "where": f"server.py:_run_r -> {script_name}",
        }
    finally:
        for p in (in_path, out_path):
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass


# --------------------------------------------------------------------------
# Follow-up hint helpers
# --------------------------------------------------------------------------

def _attach_plot_hint(result: dict, highdim: bool = False) -> dict:
    """Inject `_followup_offer_plot` into a successful cv_* return.

    `highdim=True` is for cv_*_ridge / cv_*_enet tools whose `cv_metric.values`
    is the metric AT each eta's best lambda (NOT raw metric — there is also a
    `best_lambda_per_eta` array in the same result giving the chosen lambda
    per eta, and a `best.best_lambda` for the global optimum). The 1D plot
    is still x=eta, y=cv_metric.values; the only difference is the AI should
    name the chosen lambda per eta in tooltips / annotations.

    Why this exists: docstring instructions about post-tool-call behaviour
    are read at *call-planning* time and the model tends to drop them by
    the time it composes its reply. Injecting the same instruction as a
    field in the tool's return value lands the instruction at exactly the
    moment the AI is deciding what to say next — far more reliable.

    Why no MCP plot tool: an earlier iteration (Stage 3.5, 2026-04-25)
    shipped four `plot_cv_*` tools that called SurvBregDiv::cv.plot() and
    returned the PNG via FastMCP `Image`. Wire emission was correct, but
    Claude Desktop's UI did not render the inline ImageContent reliably.
    User confirmed the workaround that does render reliably is Claude
    Desktop's own artifact / visualize capability — so we drive AI through
    that path instead, using the structured CV data this tool already
    returns. Tradeoff: we no longer use cv.plot's R-side styling.

    The hint must reference the criterion direction (loss vs C-index)
    because AI needs to know whether smaller or larger metric values are
    "better" when marking the optimal eta — getting this wrong would put
    the best-eta marker on the wrong end of the curve.
    """
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
            "If the user agrees: do NOT call any MCP tool for plotting "
            "(none exists). Instead use Claude Desktop's built-in "
            "artifact / visualize capability to draw an inline SVG line "
            "chart from the data already in this very tool result. Use: "
            "x = `etas` array, y = `cv_metric.values` array, plus a "
            "vertical marker at `best.best_eta` and a horizontal "
            "reference line at the y-value corresponding to eta=0. "
            "\n\n"
            "Critical: read the `criteria` field of this result to set "
            "axis labels and best-eta direction CORRECTLY. The package has "
            "two criterion families — Cox-family (used by cv_coxkl* / "
            "cv_cox_*) and NCC-family (used by cv_ncckl / cv_ncc_*) — and "
            "they MUST NOT be conflated. Mappings: "
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
            "\nUse the `cv_metric.name` field as a sanity cross-check "
            "(e.g. 'VVH_Loss' -> Loss, 'CIndex_pooled' -> C Index, 'AUC' -> AUC). "
            "Mislabelling these (loss vs index) is the single biggest "
            "way to confuse the user — be careful."
            "\n\n"
            "Suggested visual: x-axis labelled 'eta' or 'η'; y-axis "
            "labelled per criterion as above; line+points for the "
            "integrated CV path; dotted horizontal at the eta=0 baseline; "
            "dashed vertical at best_eta; brief title naming the function "
            "this CV is for (e.g. 'cv.coxkl_ties — CIndex_pooled')."
        )
        if highdim:
            result["_followup_offer_plot"] += (
                "\n\n"
                "HIGHDIM NOTE (this tool is cv_*_ridge or cv_*_enet): the "
                "underlying CV is over a 2D (eta x lambda) grid. The "
                "`cv_metric.values` array you plot is ALREADY the metric AT "
                "each eta's best lambda (i.e. one number per eta, not a 2D "
                "surface), so the plot stays 1D — same shape as base cv_* "
                "tools. Per-eta best-lambda values live in the result's "
                "`best_lambda_per_eta` array (parallel to `etas`); annotate "
                "those in tooltips so the user sees what lambda was chosen "
                "at each eta. The single global optimum is `best.best_eta` "
                "+ `best.best_lambda`. Do NOT attempt a 2D heatmap unless "
                "the user explicitly asks for the full grid."
            )
    return result


def _resolve_eta_with_notice(eta: Optional[float]) -> tuple[float, Optional[str]]:
    """Default-eta-to-0 policy for fit_*_ridge / fit_*_enet (KL/MDTL families).

    If `eta is None`, return (0.0, notice_string) so the dispatcher payload
    has a concrete eta and the result can carry a `_notice_eta_default`
    field that AI MUST relay to the user. Otherwise return (eta, None).

    Why MCP defaults rather than R-side default: the R function warns when
    eta is NULL but warnings do not survive the JSON bridge to AI; without
    this notice, eta=0 would silently strip away external borrowing — a
    correctness-relevant surprise.
    """
    if eta is None:
        notice = (
            "ETA-DEFAULT NOTICE (REQUIRED to surface): the user did NOT "
            "supply `eta`, so this tool defaulted to eta = 0. With eta = 0 "
            "the model does NOT borrow any external information and is "
            "equivalent to a plain ridge / enet fit (i.e. external β is "
            "ignored). Tell the user this explicitly and ask them to "
            "confirm — typical workflows want eta > 0 to actually use the "
            "external information they supplied. Suggest a starting grid "
            "or single value (e.g. eta=0.5 or etas=[0, 0.5, 1, 2])."
        )
        return 0.0, notice
    return float(eta), None


def _attach_ridge_speed_notice(result: dict) -> dict:
    """Attach `_notice_speed_slow` to ridge-tool returns.

    Ridge fits run a full lambda path per eta and (in CV) per fold, with
    no sparsity to short-circuit. Even on 50-covariate example data it
    can take 30s+ for cv with default nlambda=100 and 5 folds. AI should
    set user expectations + suggest cheaper grids when possible.
    """
    if isinstance(result, dict) and result.get("status") == "ok":
        result["_notice_speed_slow"] = (
            "SPEED NOTICE (surface to user): ridge fits run a full "
            "lambda path with no sparsity short-circuit, and CV multiplies "
            "this by nfolds × n_etas. On high-dimensional data even the "
            "shipped example datasets can take 30s+ for cv with default "
            "settings. If runtime feels slow: (a) reduce `nlambda` (try "
            "20-30 instead of default 100); (b) use a smaller `etas` grid "
            "for cv_*_ridge (e.g. 3-5 values instead of 10+); "
            "(c) lower `nfolds` to 3 for exploratory runs; "
            "(d) try the enet variant if variable selection is acceptable "
            "(enet's active-set machinery is often faster than ridge on "
            "sparse signal)."
        )
    return result


def _attach_enet_speed_notice(result: dict) -> dict:
    """Attach `_notice_speed_slow` to enet-tool returns.

    Enet uses active-set coordinate descent over the lambda path, which is
    typically faster than ridge on sparse signal because inactive coefficients
    short-circuit. But at high-dim + CV the cost still scales with
    nfolds × n_etas × nlambda. AI should set expectations + offer cheaper
    grids.

    Different optimisation tips from ridge:
      * Increasing alpha toward 1 (more lasso-like) usually speeds the
        active set up because more coefficients hit zero quickly.
      * `lambda.early.stop = TRUE` (an R-side option, not exposed via MCP)
        can shorten the path; rebuild with that on the R side if needed.
    """
    if isinstance(result, dict) and result.get("status") == "ok":
        result["_notice_speed_slow"] = (
            "SPEED NOTICE (surface to user): enet fits a full lambda "
            "path via active-set coordinate descent — typically faster "
            "than ridge on sparse signal, but high-dim + CV still scales "
            "with nfolds x n_etas x nlambda. If runtime feels slow: "
            "(a) reduce `nlambda` (try 20-30 instead of default 100); "
            "(b) for cv, use a smaller `etas` grid (3-5 values); "
            "(c) lower `nfolds` to 3 for exploratory runs; "
            "(d) for fit_coxkl_enet / fit_cox_MDTL_enet, increase `alpha` "
            "toward 1.0 for stronger sparsity — fewer active coefficients "
            "= faster convergence. For fit_cox_indi_enet, alpha is "
            "already 1.0 (lasso) by default."
        )
    return result


def _attach_eta_default_notice(result: dict, notice: Optional[str]) -> dict:
    """Inject `_notice_eta_default` only when Python defaulted eta to 0."""
    if (notice is not None
            and isinstance(result, dict)
            and result.get("status") == "ok"):
        result["_notice_eta_default"] = notice
    return result


# --------------------------------------------------------------------------
# MCP tools
# --------------------------------------------------------------------------

mcp = FastMCP("survbregdiv")


@mcp.tool()
def inspect_data(data_path: str) -> dict:
    """Describe the structure of a local R data file (.rda / .RData / .rds).

    Reads only metadata (object names, classes, dimensions, lengths) — it
    never materialises the actual data values, so it is safe to run on very
    large files. Use this before calling `fit_coxkl` to discover what objects
    a file contains and how to reference them in the *_expr parameters.

    Args:
        data_path: Absolute path to a local .rda, .RData, or .rds file. On
            Windows, backslashes in JSON must be escaped as "\\\\".

    Returns:
        On success: {status: "ok", data_path, top_level_names, structure}
        On error:   {status: "error", message, class, where}.
    """
    return _run_r("inspect_data.R", {"data_path": data_path})


@mcp.tool()
def generate_eta(
    method: str = "exponential",
    n: int = 10,
    max_eta: float = 5.0,
    min_eta: float = 0.0,
) -> dict:
    """Produce a numeric `eta` sequence from a range + grid spec.

    Convenience helper: when the user has only described the *range* and
    *shape* of the eta values they want (e.g. "10 exponentially spaced
    values from 0 to 5"), call this to get a ready-to-use array. The
    returned `etas` list can be fed directly into the `etas` argument of
    any `fit_*` tool.

    The user does NOT have to type out an explicit eta array. Suggest this
    helper whenever the user only specifies a range or grid type, or when
    they ask "what eta values should I try?" — propose a sensible default
    (e.g. exponential, n=10, max_eta=5 for typical Cox + KL workflows; the
    grid always includes 0 so you also recover the no-borrowing baseline)
    and call this tool to materialise it.

    Args:
        method:  "exponential" (default; values are exp-spaced from 0 up
                 to max_eta — denser sampling near 0, sparser near max_eta;
                 good default for KL / MDTL where small eta values are most
                 informative) or "linear" (uniform spacing).
        n:       Number of grid points. Default 10.
        max_eta: Upper end of the eta range. Default 5.
        min_eta: Lower end. Default 0. **Ignored when method="exponential"**
                 — the exponential grid is rescaled to start at 0 regardless.

    Returns:
        On success: {status, method, n, min_eta, max_eta, etas (list of n floats)}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "method": method,
        "n": n,
        "max_eta": max_eta,
        "min_eta": min_eta,
    }
    return _run_r("generate_eta.R", payload)


# --------------------------------------------------------------------------
# Guided-analysis wizard (recommended entry point for new users).
# Stateless state machine: AI calls with whatever is accumulated; wizard
# returns either the next-question payload or the final recommendation.
# Designed so end-users never see internal MCP tool names.
# --------------------------------------------------------------------------


@mcp.tool()
def start_analysis(
    study_design: Optional[str] = None,
    has_ties: Optional[bool] = None,
    external_info: Optional[str] = None,
    regularization: Optional[str] = None,
    output_type: Optional[str] = None,
    user_language: Optional[str] = None,
) -> dict:
    """Guided wizard to pick the right SurvBregDiv model for a new user's data.

    USE THIS FIRST when the user is unsure which model / function they need.
    The wizard walks them through 5 plain-language questions (no jargon, no
    function names) and returns the matching tool internally so AI can drive
    the next step (inspect_data, then the actual fit/cv tool).

    KEY UX RULES (must follow):
      * NEVER expose `recommended_mcp_tool` to the user — it's an internal
        handle. Describe the model with `user_facing_model` instead.
      * NEVER mention `inspect_data` or any other tool name to the user.
        If you need to scan their file, just say "let me look at your data"
        and call inspect_data silently.
      * Translate `question` and `options[*].label` to the user's
        conversation language. The wizard already returns localized strings
        IF you pass `user_language="zh"` for Chinese conversations or
        `user_language="en"` for English. Pass it on every call.

    STATELESS state machine: pass back EVERY answer accumulated so far on
    each call, plus the new one. Wizard infers what's still needed.

    SKIP-AHEAD supported: if the user volunteers all five answers in one
    breath, pass them all at once; the wizard returns the final
    recommendation immediately, skipping the per-question loop.

    Args:
        study_design:   "cohort" (standard cohort with time + event) or
                        "ncc" (matched case-control with strata).
        has_ties:       True if >~10% of event times repeat (cohort only;
                        wizard sets it to False for NCC automatically).
        external_info:  "beta_only" / "beta_and_vcov" / "individual_data"
                        / "none". "none" → wizard tells user this package
                        is unnecessary (use `survival` directly).
        regularization: "none" / "enet" / "ridge". Wizard handles fallbacks
                        (NCC has no ridge; indi has no ridge; ties + reg
                        not supported).
        output_type:    "fit" (single eta, point estimate) or "cv"
                        (multiple etas, cross-validated optimum).
        user_language:  "en" (default) or "zh". Auto-pass based on the
                        language the user has been writing in.

    Returns:
        On a question step: {status, step, progress, question, options,
                             next_param, ai_instruction}.
        On a fallback (e.g. NCC + ridge): {status, step,
                             recommendation_type:"fallback_required",
                             user_facing_message, options, next_param,
                             ai_instruction}.
        On final recommendation: {status, step:"DONE",
                             recommendation_type:"tool_recommended",
                             recommended_mcp_tool (INTERNAL),
                             required_args, user_facing_intro,
                             user_facing_model, user_facing_next_step,
                             ai_instruction, state_collected}.
        On out-of-scope (no external info): {status, step,
                             recommendation_type:"out_of_scope",
                             user_facing_message, ai_instruction}.
        On error: {status:"error", message, class, where}.
    """
    payload = {
        "study_design": study_design,
        "has_ties": has_ties,
        "external_info": external_info,
        "regularization": regularization,
        "output_type": output_type,
        "user_language": user_language,
    }
    return _run_r("start_analysis.R", payload)


@mcp.prompt(
    name="survbregdiv-start",
    description="Start a guided SurvBregDiv analysis (recommended for first-time users).",
)
def survbregdiv_start_prompt() -> str:
    """User-clickable entry point. When the user picks this from Claude
    Desktop's slash menu, this text gets injected into the conversation as
    if the user typed it — kicking off the start_analysis wizard.
    """
    return (
        "I'd like to use SurvBregDiv to analyze my data, but I'm not sure "
        "which model is right for me. Please call the `start_analysis` MCP "
        "tool to walk me through choosing step by step. Detect my preferred "
        "language from how I respond (Chinese or English) and pass it to "
        "`start_analysis` as `user_language` on every call. Don't mention "
        "internal tool names to me — just ask the questions in plain "
        "language and tell me which model you'll use in plain words."
    )


@mcp.tool()
def fit_coxkl(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 100,
    backtrack: bool = False,
    beta_initial_expr: Optional[str] = None,
) -> dict:
    """Fit SurvBregDiv::coxkl() — Cox PH with KL-divergence external integration.

    The data file is read by a local R subprocess; the file *path* is the
    only data-related value that transits this conversation. Raw covariate
    values stay on disk.

    Exactly one of `beta_expr`, `beta_inline`, `RS_expr`, `RS_inline` is
    required — external information is the whole point of KL integration,
    and `coxkl()` itself enforces this.

    Args:
        data_path:   Path to a .rda / .RData / .rds file on the local machine.
        z_expr:      R expression resolving to the n×p covariate matrix
                     (or data.frame) inside the loaded file.
        time_expr:   R expression for the observed-time vector.
        delta_expr:  R expression for the event indicator (1/0).
        etas:        Numeric array of KL tuning values. 0 = no borrowing.
                     If the user only gave a range / grid type rather than
                     an explicit array, call `generate_eta` first and pass
                     its `etas` field here.
        beta_expr:   R expression naming external β inside the file.
        beta_inline: Alternative — external β as a JSON array typed into chat.
        RS_expr / RS_inline: same pattern for external risk scores.
        stratum_expr: Optional R expression for stratum vector.
        tol, Mstop, backtrack, beta_initial_expr: pass-through to coxkl().

    Returns:
        On success: {status, eta, beta (p×n_etas matrix), likelihood,
                     n_obs, n_covariates, n_etas, external_via}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "beta_initial_expr": beta_initial_expr,
    }
    return _run_r("fit_coxkl.R", payload)


@mcp.tool()
def fit_cox_indi(
    data_path: str,
    z_int_expr: str,
    time_int_expr: str,
    delta_int_expr: str,
    z_ext_expr: str,
    time_ext_expr: str,
    delta_ext_expr: str,
    etas: list[float],
    stratum_int_expr: Optional[str] = None,
    stratum_ext_expr: Optional[str] = None,
    max_iter: int = 100,
    tol: float = 1e-7,
) -> dict:
    """Fit SurvBregDiv::cox_indi() — Cox PH with individual-level external data.

    Use this when you have full covariate + outcome data for an external
    cohort (not just summary coefficients). The objective is a composite
    (weighted) stratified Cox likelihood: internal observations get weight
    1, external observations get weight `eta`. eta = 0 recovers an
    internal-only fit.

    Internal and external z must have the same number of columns (same
    covariates, same order). Strata are kept separate across the two
    cohorts — risk sets do not mix.

    Args:
        data_path:        Path to a .rda / .RData / .rds file.
        z_int_expr:       R expression for internal n×p covariate matrix.
        time_int_expr:    R expression for internal observed-time vector.
        delta_int_expr:   R expression for internal event indicator (1/0).
        z_ext_expr:       R expression for external n×p covariate matrix.
        time_ext_expr:    R expression for external observed-time vector.
        delta_ext_expr:   R expression for external event indicator (1/0).
        etas:             Numeric array of external weights (≥0). 0 = internal only.
                          If the user only gave a range / grid type rather
                          than an explicit array, call `generate_eta` first
                          and pass its `etas` field here.
        stratum_int_expr: Optional R expression for internal stratum vector.
        stratum_ext_expr: Optional R expression for external stratum vector.
        max_iter, tol:    Pass-through to cox_indi() (Newton-Raphson).

    Returns:
        On success: {status, eta, beta (p×n_etas matrix),
                     n_obs_int, n_obs_ext, n_covariates, n_etas}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "time_int_expr": time_int_expr,
        "delta_int_expr": delta_int_expr,
        "z_ext_expr": z_ext_expr,
        "time_ext_expr": time_ext_expr,
        "delta_ext_expr": delta_ext_expr,
        "etas": etas,
        "stratum_int_expr": stratum_int_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "max_iter": max_iter,
        "tol": tol,
    }
    return _run_r("fit_cox_indi.R", payload)


@mcp.tool()
def fit_cox_MDTL(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 50,
    backtrack: bool = False,
    beta_initial_expr: Optional[str] = None,
) -> dict:
    """Fit SurvBregDiv::cox_MDTL() — Cox PH with Mahalanobis-distance penalty.

    Penalises (β − β_ext)ᵀ Q (β − β_ext) where β_ext is the external
    coefficient vector and Q is a p×p weighting matrix (typically the
    inverse covariance / precision matrix of β_ext). When `vcov` is not
    supplied, Q defaults to the identity → ridge-style shrinkage toward
    β_ext.

    Use this when both external β̂ AND its (precision / covariance) matrix
    are available. If only β̂ is available, use `fit_coxkl` instead.

    Exactly one of `beta_expr` or `beta_inline` is required. `vcov_expr`
    and `vcov_inline` are optional and mutually exclusive; omit both for
    the identity-Q ridge variant.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        time_expr:    R expression for observed-time vector.
        delta_expr:   R expression for event indicator (1/0).
        etas:         Numeric array of penalty weights. 0 = standard Cox.
                      If the user only gave a range / grid type rather than
                      an explicit array, call `generate_eta` first and pass
                      its `etas` field here.
        beta_expr:    R expression naming external β inside the file.
        beta_inline:  Alternative — external β as a JSON numeric array.
        vcov_expr:    R expression for p×p weighting matrix Q (precision).
        vcov_inline:  Alternative — Q as JSON list-of-rows (e.g. [[1,0],[0,1]]).
        stratum_expr: Optional R expression for stratum vector.
        tol, Mstop, backtrack, beta_initial_expr: pass-through to cox_MDTL().

    Returns:
        On success: {status, eta, beta (p×n_etas), likelihood, n_obs,
                     n_covariates, n_etas, vcov_used}.
                    vcov_used is "identity" when no vcov was supplied.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "beta_initial_expr": beta_initial_expr,
    }
    return _run_r("fit_cox_MDTL.R", payload)


@mcp.tool()
def fit_coxkl_ties(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    ties: str = "breslow",
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 100,
    beta_initial_expr: Optional[str] = None,
    comb_max: float = 1e7,
) -> dict:
    """Fit SurvBregDiv::coxkl_ties() — coxkl with proper handling of tied event times.

    Use this instead of `fit_coxkl` whenever the data has a non-trivial
    fraction of tied event times. Plain `fit_coxkl` treats events as if all
    times were unique, which biases the partial likelihood under repeated
    event times.

    `coxkl_ties` does NOT accept an external risk score (RS) — only `beta`
    is supported. Exactly one of `beta_expr` or `beta_inline` is required.

    There is no Efron option on this function (`ties` is "breslow" or
    "exact" only). There is also no `_ridge`/`_enet` companion: ties +
    regularization is not currently supported in this package.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        time_expr:    R expression for observed-time vector.
        delta_expr:   R expression for event indicator (1/0).
        etas:         Numeric array of KL tuning values. 0 = no borrowing.
                      If the user only gave a range / grid type, call
                      `generate_eta` first and pass its `etas` field here.
        beta_expr:    R expression naming external β inside the file.
        beta_inline:  Alternative — external β as a JSON numeric array.
        ties:         "breslow" (default; fast, scales linearly) or
                      "exact" (enumerates combinations within tied risk
                      sets — slow combinatorially in tie multiplicity).
                      Always pass this argument explicitly.
        stratum_expr: Optional R expression for stratum vector.
        tol, Mstop, beta_initial_expr: pass-through to coxkl_ties().
        comb_max:     Cap on combination evaluations under ties="exact"
                      (default 1e7). Ignored when ties="breslow".

    Returns:
        On success: {status, eta, beta (p×n_etas), likelihood, n_obs,
                     n_covariates, n_etas, ties, external_via}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "ties": ties,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "beta_initial_expr": beta_initial_expr,
        "comb_max": comb_max,
    }
    return _run_r("fit_coxkl_ties.R", payload)


@mcp.tool()
def cv_coxkl(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 100,
    backtrack: bool = False,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::coxkl().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot ("需要我把 CV
    曲线画出来吗？"). If the user agrees, do NOT call any MCP tool —
    instead use Claude Desktop's built-in artifact / visualize feature
    to draw an inline SVG line chart from this result's `etas` and
    `cv_metric.values` arrays. Read `criteria` to set axis labels and
    best-eta direction correctly. Full instructions live in the result's
    `_followup_offer_plot` field — read it at result-parsing time.

    Fits `coxkl` on each (training fold + external info) split, evaluates
    on the held-out fold under `cv_criteria`, and reports the CV-optimal
    eta plus its full coefficient path.

    `cv_criteria` is one of (Cox-family):
      * "V&VH" (default; Verweij & van Houwelingen partial-likelihood loss)
      * "LinPred"
      * "CIndex_pooled"
      * "CIndex_foldaverage"

    Do NOT pass NCC-family criteria ("AUC" / "Brier" / "loss") here — they
    will silently misbehave on a Cox cohort. (This is the single biggest
    landmine in the package's API.)

    Args:
        data_path, z_expr, time_expr, delta_expr: data + outcome.
        etas:        Candidate eta grid. Use `generate_eta` if you only
                     have a range/method spec.
        beta_expr / beta_inline / RS_expr / RS_inline: external info,
                     exactly one required.
        cv_criteria: One of the four Cox-family criteria above.
        nfolds:      Number of CV folds (default 5).
        stratum_expr, c_index_stratum_expr: optional strata.
        tol, Mstop, backtrack: pass-through to coxkl().
        seed:        Optional integer for reproducible fold assignment.

    Returns:
        On success: {status, criteria, nfolds, etas, cv_metric:{name,values},
                     best:{best_eta, best_beta, criteria},
                     beta_full (p×n_etas), n_obs, n_covariates, n_etas,
                     external_via, _followup_offer_plot}.
                    The trailing `_followup_offer_plot` field is a meta-
                    instruction you MUST act on (see top of docstring).
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_coxkl.R", payload))


@mcp.tool()
def cv_coxkl_ties(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    ties: str = "breslow",
    cv_criteria: str = "CIndex_pooled",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 100,
    seed: Optional[int] = None,
    comb_max: float = 1e7,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::coxkl_ties().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    Use this instead of `cv_coxkl` when the data has tied event times.
    Note: `cv.coxkl_ties` does NOT accept an external risk score — `beta`
    is required (exactly one of `beta_expr` / `beta_inline`).

    The R-side default for `cv_criteria` is `"CIndex_pooled"` here, which
    differs from `cv_coxkl`'s default of `"V&VH"`. Pass `cv_criteria`
    explicitly to avoid surprise.

    Same Cox-family criterion choices and same NCC-criteria warning as
    `cv_coxkl`.

    Args:
        data_path, z_expr, time_expr, delta_expr: data + outcome.
        etas:        Candidate eta grid.
        beta_expr / beta_inline: external β (one required).
        ties:        "breslow" (default) or "exact".
        cv_criteria: One of "V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage".
        nfolds:      Number of CV folds.
        stratum_expr, c_index_stratum_expr: optional strata.
        tol, Mstop, comb_max: pass-through to coxkl_ties().
        seed:        Optional reproducibility seed.

    Returns: same shape as `cv_coxkl`, plus a `ties` field, plus the
    `_followup_offer_plot` meta-instruction (act on it).
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "ties": ties,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "seed": seed,
        "comb_max": comb_max,
    }
    return _attach_plot_hint(_run_r("cv_coxkl_ties.R", payload))


@mcp.tool()
def cv_cox_MDTL(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 100,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::cox_MDTL().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    Mirrors `fit_cox_MDTL`'s parameter style: external `beta` is required;
    optional precision matrix `vcov` either via R expression (`vcov_expr`)
    or inline list-of-rows (`vcov_inline`); when neither is given, Q
    defaults to identity (ridge-style penalty toward β_ext).

    Same Cox-family `cv_criteria` choices as `cv_coxkl`. Same NCC-criteria
    warning applies.

    Returns: same shape as `cv_coxkl`, plus a `vcov_used` field reporting
    `"identity"` / `"vcov_expr"` / `"vcov_inline"`, plus the
    `_followup_offer_plot` meta-instruction (act on it).
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_cox_MDTL.R", payload))


@mcp.tool()
def cv_cox_indi(
    data_path: str,
    z_int_expr: str,
    time_int_expr: str,
    delta_int_expr: str,
    z_ext_expr: str,
    time_ext_expr: str,
    delta_ext_expr: str,
    etas: list[float],
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_int_expr: Optional[str] = None,
    stratum_ext_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    max_iter: int = 100,
    tol: float = 1e-7,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::cox_indi().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    Internal data are split into folds; for each fold the model is trained
    on (internal-train ∪ full external) and evaluated on the held-out
    internal fold. External data are NEVER held out — they are always
    included in training, on the assumption that the external cohort is
    large and fixed.

    Mirrors `fit_cox_indi`'s dual-cohort parameter style: separate
    `*_int_expr` and `*_ext_expr` for z/time/delta/stratum. Internal and
    external z must have the same number of columns.

    Args:
        data_path:        Path to a .rda / .RData / .rds file.
        z_int_expr, time_int_expr, delta_int_expr: internal cohort.
        z_ext_expr, time_ext_expr, delta_ext_expr: external cohort.
        etas:             Candidate eta grid.
        cv_criteria:      Cox-family criterion. Default "V&VH".
        nfolds:           Number of CV folds.
        stratum_int_expr, stratum_ext_expr, c_index_stratum_expr: optional.
        max_iter, tol:    Pass-through to cox_indi() (Newton-Raphson).
                          Note: cox_indi uses `max_iter` (not `Mstop`).
        seed:             Optional reproducibility seed.

    Returns:
        On success: {status, criteria, nfolds, etas, cv_metric:{name,values},
                     best, beta_full, n_obs_int, n_obs_ext, n_covariates,
                     n_etas, _followup_offer_plot}.
                    The trailing `_followup_offer_plot` field is a meta-
                    instruction you MUST act on (see top of docstring).
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "time_int_expr": time_int_expr,
        "delta_int_expr": delta_int_expr,
        "z_ext_expr": z_ext_expr,
        "time_ext_expr": time_ext_expr,
        "delta_ext_expr": delta_ext_expr,
        "etas": etas,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_int_expr": stratum_int_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "max_iter": max_iter,
        "tol": tol,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_cox_indi.R", payload))


# --------------------------------------------------------------------------
# Cox high-dimensional family (ridge + enet)
#
# DESIGN CONVENTIONS (consistent across all fit_*_ridge / fit_*_enet KL/MDTL):
#   * `fit_*_ridge` / `fit_*_enet` for KL and MDTL take a SINGLE `eta` scalar
#     and return the beta path along the lambda sequence at that one eta.
#     This is the user's intentional design — multi-eta scanning belongs in
#     the cv_* counterpart. (`fit_cox_indi_enet` is the one exception: it
#     takes plural `etas` because dual-cohort indi naturally supports it.)
#   * All `cv_*_ridge` / `cv_*_enet` take plural `etas`; internally they CV
#     a 2D (eta x lambda) grid and return per-eta best-lambda + global
#     best (eta, lambda) pair.
#   * MDTL family never accepts RS — only `beta` (+ optional `vcov`).
# --------------------------------------------------------------------------


@mcp.tool()
def fit_coxkl_ridge(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    penalty_factor: float = 0.999,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 50,
    backtrack: bool = False,
    beta_initial_expr: Optional[str] = None,
) -> dict:
    """Fit SurvBregDiv::coxkl_ridge() — Cox PH with Ridge (L2) penalty + KL.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_coxkl`: useful when p >> n or under
    heavy collinearity. Ridge does NOT perform variable selection — all
    coefficients are shrunk toward zero but stay non-zero. Ridge fits run
    a full lambda path; on high-dim data this can be slow (see returned
    `_notice_speed_slow` field for tuning tips).

    DESIGN CONSTRAINT: `eta` is a SINGLE scalar (not an array). The fit
    returns the full beta path along the lambda sequence at that one eta.
    To compare multiple eta values, call `cv_coxkl_ridge` instead — that's
    where multi-eta tuning belongs. Same convention as `fit_*_enet` for
    the KL/MDTL families.

    ETA DEFAULT POLICY: if `eta` is omitted, it defaults to 0 (no external
    borrowing) and the result carries a `_notice_eta_default` field
    instructing AI to flag this to the user. Most users actually want
    eta > 0 — defaulting silently would discard their external info.

    Exactly one of `beta_expr` / `beta_inline` / `RS_expr` / `RS_inline`
    is required.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        time_expr:    R expression for the observed-time vector.
        delta_expr:   R expression for the event indicator (1/0).
        eta:          Optional single non-negative scalar. If omitted,
                      defaults to 0 with a user-visible notice.
        beta_expr / beta_inline / RS_expr / RS_inline: external info, exactly
                      one required. β is length-p; RS is length-n risk score.
        lambda_:      Optional explicit lambda sequence (passed as `lambda` to R).
                      If None, an internal sequence of length `nlambda` is
                      auto-generated.
        nlambda:      Length of the auto-generated lambda sequence. Default 100.
        penalty_factor: Numeric in [0, 1) controlling internal lambda-sequence
                      generation. Default 0.999. Rarely changed.
        stratum_expr: Optional R expression for stratum vector.
        tol, Mstop, backtrack, beta_initial_expr: pass-through to coxkl_ridge().

    Returns:
        On success: {status, eta, lambda (length L), beta (p×L matrix),
                     likelihood (length L), n_obs, n_covariates, n_lambda,
                     external_via, _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "lambda": lambda_,
        "nlambda": nlambda,
        "penalty_factor": penalty_factor,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "beta_initial_expr": beta_initial_expr,
    }
    return _attach_eta_default_notice(
        _attach_ridge_speed_notice(_run_r("fit_coxkl_ridge.R", payload)),
        eta_notice,
    )


@mcp.tool()
def cv_coxkl_ridge(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::coxkl_ridge().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: after summarising results, your VERY FIRST follow-up
    suggestion must be to offer a CV-path plot. If the user agrees, draw
    an inline SVG line chart via Claude Desktop's built-in artifact /
    visualize feature from this result's `etas` and `cv_metric.values`
    arrays — the values are ALREADY the metric at each eta's best lambda
    (1D plot, same shape as base cv_* tools). Annotate `best_lambda_per_eta`
    in tooltips. Full instructions live in `_followup_offer_plot`.

    Internally CVs a 2D (eta x lambda) grid; for each eta, the best lambda
    under `cv_criteria` is selected; among those per-eta winners, the global
    best (eta, lambda) pair is reported as `best`.

    `cv_criteria` is one of (Cox-family ONLY):
      * "V&VH" (default; partial-likelihood loss)
      * "LinPred"
      * "CIndex_pooled"
      * "CIndex_foldaverage"

    NCC-family criteria are rejected at dispatcher level.

    Args:
        data_path, z_expr, time_expr, delta_expr: data + outcome.
        etas:             Candidate eta grid (plural). Use `generate_eta` if
                          only a range/method spec is available.
        beta_expr / beta_inline / RS_expr / RS_inline: external info, one required.
        lambda_:          Optional explicit lambda sequence (shared across all etas).
                          If None, auto-generated internally per eta.
        nlambda:          Length of auto-generated lambda sequence. Default 100.
        lambda_min_ratio: Lower-end ratio for auto-generated lambda sequence.
                          If None, R defaults to 0.01 (n<p) or 1e-4 (n≥p).
        cv_criteria:      One of the four Cox-family criteria above.
        nfolds:           Number of CV folds (default 5).
        stratum_expr, c_index_stratum_expr: optional strata.
        seed:             Optional integer for reproducible folds.

    Returns:
        On success: {status, criteria, nfolds, etas, cv_metric:{name,values
                       (per-eta best-lambda metric)},
                     best_lambda_per_eta (parallel to etas),
                     best:{best_eta, best_lambda, best_beta, criteria},
                     beta_best_per_eta (p×n_etas matrix; beta at each eta's
                       best lambda),
                     n_obs, n_covariates, n_etas, external_via,
                     _followup_offer_plot}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "seed": seed,
    }
    return _attach_ridge_speed_notice(
        _attach_plot_hint(_run_r("cv_coxkl_ridge.R", payload), highdim=True)
    )


@mcp.tool()
def fit_cox_MDTL_ridge(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    penalty_factor: float = 0.999,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 50,
    backtrack: bool = False,
    beta_initial_expr: Optional[str] = None,
) -> dict:
    """Fit SurvBregDiv::cox_MDTL_ridge() — Cox PH with Ridge + Mahalanobis penalty.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_cox_MDTL`: penalises (β−β_ext)ᵀ Q (β−β_ext)
    PLUS an L2 ridge penalty along a lambda path. Q defaults to identity
    when `vcov` is omitted (ridge-style shrinkage toward β_ext). Ridge fits
    can be slow on high-dim data — see returned `_notice_speed_slow`.

    DESIGN CONSTRAINTS:
      * `eta` is a SINGLE scalar (not an array). For multi-eta tuning,
        call `cv_cox_MDTL_ridge`. If omitted, defaults to 0 with a
        user-visible `_notice_eta_default` notice.
      * MDTL never accepts RS — only `beta` (+ optional `vcov`). Exactly
        one of `beta_expr` / `beta_inline` is required.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        time_expr:    R expression for observed-time vector.
        delta_expr:   R expression for event indicator (1/0).
        eta:          Optional single non-negative scalar. Defaults to 0
                      with notice if omitted.
        beta_expr / beta_inline: external β (one required).
        vcov_expr / vcov_inline: optional precision/covariance matrix Q
                      (mutually exclusive). Omit both for identity-Q.
        lambda_:      Optional explicit lambda sequence (passed as `lambda`
                      to R). If None, auto-generated of length `nlambda`.
        nlambda:      Length of auto-generated lambda sequence. Default 100.
        penalty_factor: Numeric in [0, 1) controlling internal lambda
                      generation. Default 0.999. Rarely changed.
        stratum_expr: Optional R expression for stratum vector.
        tol, Mstop, backtrack, beta_initial_expr: pass-through.

    Returns:
        On success: {status, eta, lambda, beta (p×L), likelihood,
                     n_obs, n_covariates, n_lambda, vcov_used,
                     _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "lambda": lambda_,
        "nlambda": nlambda,
        "penalty_factor": penalty_factor,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "beta_initial_expr": beta_initial_expr,
    }
    return _attach_eta_default_notice(
        _attach_ridge_speed_notice(_run_r("fit_cox_MDTL_ridge.R", payload)),
        eta_notice,
    )


@mcp.tool()
def cv_cox_MDTL_ridge(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::cox_MDTL_ridge().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: after summarising results, your VERY FIRST follow-up
    suggestion must be to offer a CV-path plot. If user agrees, draw an
    inline SVG line chart from `etas` and `cv_metric.values` (already
    per-eta best-lambda — 1D plot). Annotate `best_lambda_per_eta` in
    tooltips. Full instructions in `_followup_offer_plot`.

    Same return shape as `cv_coxkl_ridge`. Same Cox-family `cv_criteria`
    whitelist; NCC criteria rejected at dispatcher level.

    MDTL never accepts RS. External `beta` required (one of expr/inline).
    Optional `vcov` either expr or inline (mutually exclusive); omit both
    for identity-Q ridge.

    Returns: same shape as `cv_coxkl_ridge`, plus `vcov_used` field, plus
    `_notice_speed_slow`. Ridge CV is the slowest tool in this family —
    consider small `etas` grids and `nlambda=20-30` for exploratory runs.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "seed": seed,
    }
    return _attach_ridge_speed_notice(
        _attach_plot_hint(_run_r("cv_cox_MDTL_ridge.R", payload), highdim=True)
    )


# --------------------------------------------------------------------------
# Cox enet family (KL + MDTL: single eta; indi: plural etas)
# --------------------------------------------------------------------------


@mcp.tool()
def fit_coxkl_enet(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::coxkl_enet() — Cox PH with elastic-net + KL.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_coxkl`. Returns the beta path along
    the lambda sequence at a single eta. For multi-eta tuning, call
    `cv_coxkl_enet`. Enet performs variable selection (alpha=1 → lasso,
    alpha<1 → elastic net). See `_notice_speed_slow` in the result for
    timing tips.

    ETA DEFAULT POLICY: if `eta` is omitted, defaults to 0 with notice.

    Exactly one of `beta_expr` / `beta_inline` / `RS_expr` / `RS_inline`
    is required.

    Args:
        data_path:        .rda / .RData / .rds.
        z_expr / time_expr / delta_expr: required.
        eta:              Optional single non-negative scalar. Default 0
                          with notice.
        beta_expr / beta_inline / RS_expr / RS_inline: external info, one required.
        alpha:            Elastic-net mixing (0=ridge-only, 1=lasso). Default 1.
        lambda_:          Optional explicit lambda sequence. If None,
                          auto-generated of length `nlambda`.
        nlambda:          Default 100.
        lambda_min_ratio: Lower-end ratio for auto sequence. If None, R uses 1e-3.
        stratum_expr:     Optional stratum vector.
        tol, Mstop:       Pass-through to coxkl_enet().

    Returns:
        On success: {status, eta, alpha, lambda (length L), beta (p×L),
                     likelihood, n_obs, n_covariates, n_lambda, external_via,
                     _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_eta_default_notice(
        _attach_enet_speed_notice(_run_r("fit_coxkl_enet.R", payload)),
        eta_notice,
    )


@mcp.tool()
def fit_cox_MDTL_enet(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    stratum_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::cox_MDTL_enet() — Cox PH with elastic-net + Mahalanobis.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_cox_MDTL`. Single eta. MDTL never
    accepts RS — only `beta` (+ optional `vcov`). When `vcov` is omitted,
    Q defaults to identity (ridge-style shrinkage toward β_ext).

    ETA DEFAULT POLICY: if `eta` is omitted, defaults to 0 with notice.

    Args:
        data_path, z_expr, time_expr, delta_expr: data + outcome.
        eta:              Optional single non-negative scalar. Default 0 with notice.
        beta_expr / beta_inline: external β (one required).
        vcov_expr / vcov_inline: optional precision matrix Q (mutually exclusive).
        alpha, lambda_, nlambda, lambda_min_ratio, stratum_expr, tol, Mstop:
                          enet pass-through, same semantics as fit_coxkl_enet.

    Returns:
        On success: {status, eta, alpha, lambda, beta (p×L), likelihood,
                     n_obs, n_covariates, n_lambda, vcov_used,
                     _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "stratum_expr": stratum_expr,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_eta_default_notice(
        _attach_enet_speed_notice(_run_r("fit_cox_MDTL_enet.R", payload)),
        eta_notice,
    )


@mcp.tool()
def fit_cox_indi_enet(
    data_path: str,
    z_int_expr: str,
    time_int_expr: str,
    delta_int_expr: str,
    z_ext_expr: str,
    time_ext_expr: str,
    delta_ext_expr: str,
    etas: list[float],
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    stratum_int_expr: Optional[str] = None,
    stratum_ext_expr: Optional[str] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::cox_indi_enet() — Cox PH dual-cohort indi + enet.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_cox_indi`. Differs from the KL/MDTL
    fit_*_enet tools in TWO ways:
      * `etas` is REQUIRED PLURAL (no scalar eta, no defaulting policy).
        Same convention as base `fit_cox_indi` — dual-cohort composite
        likelihood naturally supports multi-eta.
      * No external β / RS arguments — external information is supplied as
        the full external cohort (z_ext + time_ext + delta_ext).

    Internal weight = 1; external weight = eta. eta=0 recovers internal-only.
    Internal and external z must have the same number of columns.

    The return is a JAGGED structure: each eta has its own lambda sequence
    (auto-generated per eta) and its own p × L_i beta matrix. See the
    `beta_per_eta` and `lambda_per_eta` lists below.

    Args:
        data_path:        .rda / .RData / .rds.
        z_int_expr / time_int_expr / delta_int_expr: internal cohort.
        z_ext_expr / time_ext_expr / delta_ext_expr: external cohort.
        etas:             REQUIRED non-empty numeric array.
        alpha, lambda_, nlambda, lambda_min_ratio: enet controls.
        stratum_int_expr / stratum_ext_expr: optional strata.
        tol, Mstop:       pass-through.

    Returns:
        On success: {status, etas (vector), alpha,
                     beta_per_eta (list of p×L_i matrices, one per eta),
                     lambda_per_eta (list of length-L_i vectors, one per eta),
                     n_obs_int, n_obs_ext, n_covariates, n_etas,
                     n_lambda_per_eta (vector parallel to etas),
                     _notice_speed_slow}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "time_int_expr": time_int_expr,
        "delta_int_expr": delta_int_expr,
        "z_ext_expr": z_ext_expr,
        "time_ext_expr": time_ext_expr,
        "delta_ext_expr": delta_ext_expr,
        "etas": etas,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "stratum_int_expr": stratum_int_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_enet_speed_notice(_run_r("fit_cox_indi_enet.R", payload))


@mcp.tool()
def cv_coxkl_enet(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::coxkl_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: after summarising results, your VERY FIRST follow-up
    suggestion must be to offer a CV-path plot. If user agrees, draw an
    inline SVG line chart from `etas` and `cv_metric.values` (already
    per-eta best-lambda — 1D plot). Annotate `best_lambda_per_eta` in
    tooltips. Full instructions in `_followup_offer_plot`.

    Same Cox-family `cv_criteria` whitelist as `cv_coxkl_ridge`.

    Returns: same shape as `cv_coxkl_ridge`, plus `alpha`. Notice fields:
    `_notice_speed_slow`, `_followup_offer_plot`.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_coxkl_enet.R", payload), highdim=True)
    )


@mcp.tool()
def cv_cox_MDTL_enet(
    data_path: str,
    z_expr: str,
    time_expr: str,
    delta_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::cox_MDTL_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: see `_followup_offer_plot`.

    MDTL never accepts RS. External `beta` required (one of expr/inline).
    Optional `vcov` (mutually exclusive expr/inline); identity Q otherwise.

    Returns: same shape as `cv_coxkl_enet`, plus `vcov_used` field.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "time_expr": time_expr,
        "delta_expr": delta_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_expr": stratum_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_cox_MDTL_enet.R", payload), highdim=True)
    )


@mcp.tool()
def cv_cox_indi_enet(
    data_path: str,
    z_int_expr: str,
    time_int_expr: str,
    delta_int_expr: str,
    z_ext_expr: str,
    time_ext_expr: str,
    delta_ext_expr: str,
    etas: list[float],
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "V&VH",
    nfolds: int = 5,
    stratum_int_expr: Optional[str] = None,
    stratum_ext_expr: Optional[str] = None,
    c_index_stratum_expr: Optional[str] = None,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::cox_indi_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: see `_followup_offer_plot`.

    Internal data are split into folds; the external cohort is fully
    included in every training fold (assumed large and fixed).

    Same Cox-family `cv_criteria` whitelist. Returns: per-eta best-lambda
    1D shape (same as cv_coxkl_enet), plus `alpha`, plus
    `n_obs_int`/`n_obs_ext` instead of `n_obs`.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "time_int_expr": time_int_expr,
        "delta_int_expr": delta_int_expr,
        "z_ext_expr": z_ext_expr,
        "time_ext_expr": time_ext_expr,
        "delta_ext_expr": delta_ext_expr,
        "etas": etas,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "stratum_int_expr": stratum_int_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "c_index_stratum_expr": c_index_stratum_expr,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_cox_indi_enet.R", payload), highdim=True)
    )


# --------------------------------------------------------------------------
# NCC-family tools (matched case-control / nested case-control)
#
# NCC API differs from Cox in three ways every NCC tool below enforces:
#   * `y_expr` + `stratum_expr` instead of `time_expr` + `delta_expr`
#     — the package internally maps (time = 1, delta = y) and dispatches
#     to a stratified Cox engine.
#   * `stratum_expr` is REQUIRED — the matched-set structure is what
#     defines the conditional likelihood.
#   * `cv_criteria` is the NCC family ("loss" / "AUC" / "CIndex" / "Brier").
#     Cox-family criteria are rejected at the dispatcher level, NOT just
#     deferred to R's match.arg (which would silently pick choices[1]).
#
# MDTL family (`fit_ncc_MDTL`, `cv_ncc_MDTL`) takes `beta` + optional
# `vcov` — never RS. KL family (`fit_ncckl`, `cv_ncckl`) also takes only
# `beta` here (the underlying ncckl() does not accept RS, unlike coxkl()).
# --------------------------------------------------------------------------


@mcp.tool()
def fit_ncckl(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    method: str = "breslow",
    tol: float = 1e-4,
    Mstop: int = 100,
    comb_max: float = 1e7,
) -> dict:
    """Fit SurvBregDiv::ncckl() — NCC conditional logistic regression with KL integration.

    Use for matched case-control / nested case-control data with summary-level
    external coefficients. The package maps the matched-set problem to a
    stratified Cox model (time = 1, delta = y) internally.

    NCC API differs from `fit_coxkl`:
      * `y_expr` is a binary outcome (1 = case, 0 = control), NOT (time, delta).
      * `stratum_expr` is REQUIRED (matched-set identifier).
      * Only `beta_expr` / `beta_inline` accepted — `ncckl()` does NOT take
        an external risk score, unlike `coxkl()`. Provide exactly one.

    `method` controls the matched-set conditional-likelihood form for
    1:M vs n:m designs — it is NOT a tie-handling argument (every NCC
    matched set has exactly one event by construction). For 1:M designs
    "breslow" and "exact" are mathematically identical; for n:m with
    n > 1 they differ. There is no `ncckl_ties` function — do not look
    for one.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        y_expr:       R expression for the binary outcome (1=case, 0=control).
        stratum_expr: R expression for the matched-set identifier (REQUIRED).
        etas:         Numeric array of KL tuning values. 0 = no borrowing.
                      If the user only gave a range / grid type, call
                      `generate_eta` first and pass its `etas` field here.
        beta_expr:    R expression naming external β inside the file.
        beta_inline:  Alternative — external β as a JSON numeric array.
        method:       "breslow" (default) or "exact". For 1:M matching these
                      give identical results; pick "exact" for n:m if
                      mathematical strictness is required.
        tol, Mstop:   Pass-through to ncckl().
        comb_max:     Cap on combination evaluations under method="exact".

    Returns:
        On success: {status, eta, beta (p×n_etas), likelihood, n_obs,
                     n_strata, n_covariates, n_etas, method, external_via}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "method": method,
        "tol": tol,
        "Mstop": Mstop,
        "comb_max": comb_max,
    }
    return _run_r("fit_ncckl.R", payload)


@mcp.tool()
def fit_ncc_indi(
    data_path: str,
    z_int_expr: str,
    y_int_expr: str,
    stratum_int_expr: str,
    z_ext_expr: str,
    y_ext_expr: str,
    stratum_ext_expr: str,
    etas: list[float],
    max_iter: int = 100,
    tol: float = 1e-7,
) -> dict:
    """Fit SurvBregDiv::ncc_indi() — NCC with individual-level external data.

    Use when you have full matched case-control data for an external
    cohort (not just summary β). The objective is a composite (weighted)
    conditional log-likelihood: internal sets get weight 1, external sets
    get weight `eta`. eta = 0 recovers an internal-only fit.

    Both internal AND external cohorts must be in 1:m matched form, with
    `stratum_*_expr` identifying the matched set. Each stratum must contain
    exactly one case in both cohorts. Internal and external z must have
    the same number of columns.

    Args:
        data_path:        Path to a .rda / .RData / .rds file.
        z_int_expr:       R expression for internal n×p covariate matrix.
        y_int_expr:       R expression for internal binary outcome.
        stratum_int_expr: R expression for internal matched-set ID (REQUIRED).
        z_ext_expr:       R expression for external n×p covariate matrix.
        y_ext_expr:       R expression for external binary outcome.
        stratum_ext_expr: R expression for external matched-set ID (REQUIRED).
        etas:             Numeric array of external weights (≥0).
                          If only a range / grid type was given, call
                          `generate_eta` first.
        max_iter, tol:    Pass-through (Newton-Raphson).

    Returns:
        On success: {status, eta, beta (p×n_etas), n_obs_int, n_obs_ext,
                     n_strata_int, n_strata_ext, n_covariates, n_etas}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "y_int_expr": y_int_expr,
        "stratum_int_expr": stratum_int_expr,
        "z_ext_expr": z_ext_expr,
        "y_ext_expr": y_ext_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "etas": etas,
        "max_iter": max_iter,
        "tol": tol,
    }
    return _run_r("fit_ncc_indi.R", payload)


@mcp.tool()
def fit_ncc_MDTL(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    tol: float = 1e-4,
    Mstop: int = 50,
    backtrack: bool = False,
    beta_initial_expr: Optional[str] = None,
) -> dict:
    """Fit SurvBregDiv::ncc_MDTL() — NCC with Mahalanobis-distance penalty.

    Penalises (β − β_ext)ᵀ Q (β − β_ext) where β_ext is the external
    coefficient vector and Q is a p×p weighting matrix (typically the
    inverse covariance / precision matrix of β_ext). When `vcov` is not
    supplied, Q defaults to the identity → ridge-style shrinkage toward β_ext.

    Use this when both external β̂ AND its (precision / covariance) matrix
    are available for an NCC analysis. If only β̂ is available, use
    `fit_ncckl` instead.

    DESIGN CONSTRAINT: ncc_MDTL never accepts an external risk score (RS) —
    only `beta` (+ optional `vcov`). This mirrors `cox_MDTL`. Do not look
    for an RS_expr / RS_inline argument — none exists.

    Args:
        data_path:    Path to a .rda / .RData / .rds file.
        z_expr:       R expression for the n×p covariate matrix.
        y_expr:       R expression for binary outcome.
        stratum_expr: R expression for the matched-set ID (REQUIRED).
        etas:         Numeric array of penalty weights. 0 = no borrowing.
        beta_expr:    R expression naming external β (one of expr/inline).
        beta_inline:  Alternative — external β as a JSON numeric array.
        vcov_expr:    Optional R expression for p×p weighting matrix Q.
        vcov_inline:  Alternative — Q as JSON list-of-rows (e.g. [[1,0],[0,1]]).
        tol, Mstop, backtrack, beta_initial_expr: pass-through.

    Returns:
        On success: {status, eta, beta (p×n_etas), likelihood, n_obs,
                     n_strata, n_covariates, n_etas, vcov_used}.
                    vcov_used is "identity" when no vcov was supplied.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "tol": tol,
        "Mstop": Mstop,
        "backtrack": backtrack,
        "beta_initial_expr": beta_initial_expr,
    }
    return _run_r("fit_ncc_MDTL.R", payload)


@mcp.tool()
def cv_ncckl(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    cv_criteria: str = "loss",
    method: str = "breslow",
    nfolds: int = 5,
    tol: float = 1e-4,
    Mstop: int = 100,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::ncckl().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    CV folds are constructed at the stratum level so the 1:m matched
    structure is preserved within every fold.

    `cv_criteria` is one of (NCC-family ONLY):
      * "loss"   (default; smaller is better)
      * "AUC"    (larger is better)
      * "CIndex" (larger is better; matched-set C-index)
      * "Brier"  (smaller is better)

    Do NOT pass Cox-family criteria ("V&VH" / "LinPred" / "CIndex_pooled" /
    "CIndex_foldaverage") here — they are rejected at the dispatcher
    level with a clear error. (This is the single biggest landmine in
    the NCC API and is enforced strictly to prevent silent misuse.)

    Args:
        data_path, z_expr, y_expr, stratum_expr: data + outcome + matched
            sets. `stratum_expr` is REQUIRED (matched-set identifier).
        etas:         Candidate eta grid. Use `generate_eta` if you only
                      have a range/method spec.
        beta_expr / beta_inline: external β (one required; ncckl does not
                      accept RS).
        cv_criteria:  One of the four NCC-family criteria above.
        method:       "breslow" (default) or "exact" — matched-set
                      likelihood form, NOT tie-handling.
        nfolds:       Number of CV folds (default 5).
        tol, Mstop:   Pass-through to ncckl().
        seed:         Optional integer for reproducible fold assignment.

    Returns:
        On success: {status, criteria, nfolds, etas, cv_metric:{name,values},
                     best:{best_eta, best_beta, criteria},
                     beta_full (p×n_etas), n_obs, n_strata, n_covariates,
                     n_etas, method, external_via, _followup_offer_plot}.
                    The trailing `_followup_offer_plot` field is a meta-
                    instruction you MUST act on (see top of docstring).
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "cv_criteria": cv_criteria,
        "method": method,
        "nfolds": nfolds,
        "tol": tol,
        "Mstop": Mstop,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_ncckl.R", payload))


@mcp.tool()
def cv_ncc_indi(
    data_path: str,
    z_int_expr: str,
    y_int_expr: str,
    stratum_int_expr: str,
    z_ext_expr: str,
    y_ext_expr: str,
    stratum_ext_expr: str,
    etas: list[float],
    cv_criteria: str = "loss",
    nfolds: int = 5,
    max_iter: int = 100,
    tol: float = 1e-7,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::ncc_indi().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    Internal data are split at the stratum level (matched sets stay
    together within a fold); the external cohort is always fully
    included in every training fold (assumed large and fixed).

    `cv_criteria` whitelist (NCC-family only): "loss" (default) / "AUC"
    / "CIndex" / "Brier". Cox-family criteria are rejected at dispatcher
    level — see `cv_ncckl` for full landmine warning.

    Args:
        data_path:        Path to a .rda / .RData / .rds file.
        z_int_expr, y_int_expr, stratum_int_expr: internal cohort.
        z_ext_expr, y_ext_expr, stratum_ext_expr: external cohort.
                          All matched-set identifiers REQUIRED.
        etas:             Candidate eta grid.
        cv_criteria:      NCC-family criterion. Default "loss".
        nfolds:           Number of CV folds.
        max_iter, tol:    Pass-through (Newton-Raphson).
        seed:             Optional reproducibility seed.

    Returns:
        On success: {status, criteria, nfolds, etas, cv_metric, best,
                     beta_full, n_obs_int, n_obs_ext, n_strata_int,
                     n_strata_ext, n_covariates, n_etas,
                     _followup_offer_plot}.
                    The trailing `_followup_offer_plot` field is a meta-
                    instruction you MUST act on (see top of docstring).
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "y_int_expr": y_int_expr,
        "stratum_int_expr": stratum_int_expr,
        "z_ext_expr": z_ext_expr,
        "y_ext_expr": y_ext_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "etas": etas,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "max_iter": max_iter,
        "tol": tol,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_ncc_indi.R", payload))


@mcp.tool()
def cv_ncc_MDTL(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    cv_criteria: str = "loss",
    nfolds: int = 5,
    tol: float = 1e-4,
    Mstop: int = 100,
    seed: Optional[int] = None,
) -> dict:
    """K-fold cross-validation of `eta` for SurvBregDiv::ncc_MDTL().

    POST-CALL ACTION: after summarising the CV results, your VERY FIRST
    follow-up suggestion must be to offer a CV-path plot. If the user
    agrees, draw an inline SVG line chart via Claude Desktop's built-in
    artifact / visualize feature from this result's `etas` and
    `cv_metric.values` arrays — there is no MCP plot tool to call. Read
    `criteria` to set axis labels and best-eta direction correctly.
    Full instructions live in the result's `_followup_offer_plot` field.

    Mirrors `fit_ncc_MDTL`'s parameter style: external `beta` is required;
    optional precision matrix `vcov` either via R expression (`vcov_expr`)
    or inline list-of-rows (`vcov_inline`); when neither is given, Q
    defaults to identity (ridge-style shrinkage toward β_ext).

    NCC-family `cv_criteria` whitelist enforced (loss / AUC / CIndex / Brier).
    DESIGN CONSTRAINT: never RS — only `beta` (+ optional `vcov`).

    Returns: same shape as `cv_ncckl`, plus a `vcov_used` field reporting
    `"identity"` / `"vcov_expr"` / `"vcov_inline"`, plus the
    `_followup_offer_plot` meta-instruction (act on it).
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "tol": tol,
        "Mstop": Mstop,
        "seed": seed,
    }
    return _attach_plot_hint(_run_r("cv_ncc_MDTL.R", payload))


# --------------------------------------------------------------------------
# NCC enet family (Stage 3.5 — KL/MDTL: single eta; indi: plural etas).
# Mirrors the Cox enet family. NCC has NO ridge variants by design — only enet.
# Differences from Cox enet:
#   * y_expr + stratum_expr (REQUIRED) — NOT time/delta
#   * NCC-family CV criteria whitelist: "loss" / "AUC" / "CIndex" / "Brier"
#   * fit_ncckl_enet / cv_ncckl_enet accept BOTH beta AND RS (mutually
#     exclusive) — different from base ncckl which accepts only beta.
#     Mirrors Cox enet's behaviour, not the NCC base.
# --------------------------------------------------------------------------


@mcp.tool()
def fit_ncckl_enet(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::ncckl_enet() — NCC + elastic-net + KL.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_ncckl`. Single eta. Returns the beta
    path along the lambda sequence at that one eta. For multi-eta tuning,
    call `cv_ncckl_enet`.

    NCC API: `y_expr` + `stratum_expr` (REQUIRED — matched-set ID), NOT
    time/delta. Internally maps to stratified Cox via (time = 1, delta = y).

    EXTERNAL INFO: unlike base `ncckl` (which only accepts `beta`),
    `ncckl_enet` accepts BOTH `beta` AND `RS` (mutually exclusive). Mirrors
    Cox enet behaviour. Provide exactly one of beta_expr / beta_inline /
    RS_expr / RS_inline.

    ETA DEFAULT POLICY: if `eta` is omitted, defaults to 0 with a notice.

    Args:
        data_path:   .rda / .RData / .rds.
        z_expr:      n×p covariate matrix.
        y_expr:      binary outcome (1=case, 0=control).
        stratum_expr: matched-set ID (REQUIRED).
        eta:         optional single non-negative scalar; defaults to 0 with notice.
        beta_expr/beta_inline/RS_expr/RS_inline: external info (one required).
        alpha:       elastic-net mixing. Default 1 (lasso).
        lambda_:     optional explicit lambda sequence.
        nlambda:     length of auto-generated sequence. Default 100.
        lambda_min_ratio: lower-end ratio (R default 1e-3 if None).
        tol, Mstop:  pass-through.

    Returns:
        On success: {status, eta, alpha, lambda (length L), beta (p×L),
                     likelihood, n_obs, n_strata, n_covariates, n_lambda,
                     external_via, _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_eta_default_notice(
        _attach_enet_speed_notice(_run_r("fit_ncckl_enet.R", payload)),
        eta_notice,
    )


@mcp.tool()
def fit_ncc_MDTL_enet(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    eta: Optional[float] = None,
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::ncc_MDTL_enet() — NCC + elastic-net + Mahalanobis.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_ncc_MDTL`. Single eta. NCC API
    (`y_expr` + `stratum_expr` required, NOT time/delta).

    MDTL never accepts RS — only `beta` (+ optional `vcov`). When `vcov`
    is omitted, Q defaults to identity (ridge-style shrinkage toward β_ext).

    ETA DEFAULT POLICY: if `eta` is omitted, defaults to 0 with notice.

    Args:
        data_path, z_expr, y_expr, stratum_expr: data + outcome + matched set.
        eta:         optional scalar; defaults to 0 with notice.
        beta_expr/beta_inline: external β (one required).
        vcov_expr/vcov_inline: optional precision matrix Q (mutually exclusive).
        alpha, lambda_, nlambda, lambda_min_ratio, tol, Mstop: enet pass-through.

    Returns:
        On success: {status, eta, alpha, lambda, beta (p×L), likelihood,
                     n_obs, n_strata, n_covariates, n_lambda, vcov_used,
                     _notice_speed_slow,
                     _notice_eta_default (only if eta defaulted)}.
        On error:   {status: "error", message, class, where}.
    """
    eta_resolved, eta_notice = _resolve_eta_with_notice(eta)
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "eta": eta_resolved,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_eta_default_notice(
        _attach_enet_speed_notice(_run_r("fit_ncc_MDTL_enet.R", payload)),
        eta_notice,
    )


@mcp.tool()
def fit_ncc_indi_enet(
    data_path: str,
    z_int_expr: str,
    y_int_expr: str,
    stratum_int_expr: str,
    z_ext_expr: str,
    y_ext_expr: str,
    stratum_ext_expr: str,
    etas: list[float],
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    tol: float = 1e-4,
    Mstop: int = 1000,
) -> dict:
    """Fit SurvBregDiv::ncc_indi_enet() — NCC dual-cohort indi + enet.

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    High-dimensional companion to `fit_ncc_indi`. **Plural `etas` REQUIRED**
    (no scalar; no eta-default policy — same convention as Cox indi enet).
    No external β / RS — external info is the full external matched cohort
    (z_ext + y_ext + stratum_ext).

    Returns JAGGED structure: each eta has its own lambda sequence and
    p × L_i beta matrix. See `beta_per_eta` and `lambda_per_eta`.

    Args:
        data_path:   .rda / .RData / .rds.
        z_int_expr / y_int_expr / stratum_int_expr: internal cohort.
        z_ext_expr / y_ext_expr / stratum_ext_expr: external cohort.
        etas:        REQUIRED non-empty numeric array.
        alpha, lambda_, nlambda, lambda_min_ratio, tol, Mstop: enet pass-through.

    Returns:
        On success: {status, etas (vector), alpha,
                     beta_per_eta (list of p×L_i matrices),
                     lambda_per_eta (list of length-L_i vectors),
                     n_obs_int, n_obs_ext, n_strata_int, n_strata_ext,
                     n_covariates, n_etas, n_lambda_per_eta,
                     _notice_speed_slow}.
        On error:   {status: "error", message, class, where}.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "y_int_expr": y_int_expr,
        "stratum_int_expr": stratum_int_expr,
        "z_ext_expr": z_ext_expr,
        "y_ext_expr": y_ext_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "etas": etas,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "tol": tol,
        "Mstop": Mstop,
    }
    return _attach_enet_speed_notice(_run_r("fit_ncc_indi_enet.R", payload))


@mcp.tool()
def cv_ncckl_enet(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    RS_expr: Optional[str] = None,
    RS_inline: Optional[list[float]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "loss",
    nfolds: int = 5,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::ncckl_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: after summarising results, your VERY FIRST follow-up
    suggestion must be to offer a CV-path plot. Use Claude Desktop's
    artifact / visualize feature. See `_followup_offer_plot`.

    NCC-family `cv_criteria` whitelist (`loss`/`AUC`/`CIndex`/`Brier`)
    enforced at dispatcher level. Cox-family criteria rejected.

    EXTERNAL INFO: cv.ncckl_enet accepts BOTH `beta` AND `RS` (mutually
    exclusive), unlike base cv.ncckl which only accepts beta.

    Returns: same shape as `cv_coxkl_enet`, plus `n_strata`. Notice fields:
    `_notice_speed_slow`, `_followup_offer_plot`.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "RS_expr": RS_expr,
        "RS_inline": RS_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_ncckl_enet.R", payload), highdim=True)
    )


@mcp.tool()
def cv_ncc_MDTL_enet(
    data_path: str,
    z_expr: str,
    y_expr: str,
    stratum_expr: str,
    etas: list[float],
    beta_expr: Optional[str] = None,
    beta_inline: Optional[list[float]] = None,
    vcov_expr: Optional[str] = None,
    vcov_inline: Optional[list[list[float]]] = None,
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "loss",
    nfolds: int = 5,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::ncc_MDTL_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: see `_followup_offer_plot`.

    NCC-family `cv_criteria` whitelist enforced. MDTL never accepts RS —
    only `beta` (+ optional `vcov`).

    Returns: same shape as `cv_ncckl_enet`, plus `vcov_used` field.
    """
    payload = {
        "data_path": data_path,
        "z_expr": z_expr,
        "y_expr": y_expr,
        "stratum_expr": stratum_expr,
        "etas": etas,
        "beta_expr": beta_expr,
        "beta_inline": beta_inline,
        "vcov_expr": vcov_expr,
        "vcov_inline": vcov_inline,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_ncc_MDTL_enet.R", payload), highdim=True)
    )


@mcp.tool()
def cv_ncc_indi_enet(
    data_path: str,
    z_int_expr: str,
    y_int_expr: str,
    stratum_int_expr: str,
    z_ext_expr: str,
    y_ext_expr: str,
    stratum_ext_expr: str,
    etas: list[float],
    alpha: float = 1.0,
    lambda_: Optional[list[float]] = None,
    nlambda: int = 100,
    lambda_min_ratio: Optional[float] = None,
    cv_criteria: str = "loss",
    nfolds: int = 5,
    seed: Optional[int] = None,
) -> dict:
    """K-fold CV of (eta, lambda) for SurvBregDiv::ncc_indi_enet().

    PRE-CALL ACTION (REQUIRED): before invoking this tool, you MUST first
    tell the user that high-dimensional ridge/enet computations can be slow
    (the algorithm runs a full lambda path; CV multiplies that cost by
    nfolds × n_etas — minutes are common at default settings) and get their
    explicit go-ahead. Do not silently invoke this tool.

    POST-CALL ACTION: see `_followup_offer_plot`.

    Internal data are split at the stratum level (matched sets stay
    together within fold); external cohort fully included in every
    training fold. NCC-family `cv_criteria` whitelist enforced.

    Returns: per-eta-best-lambda 1D shape (same as cv_ncckl_enet), plus
    `n_obs_int`/`n_obs_ext`/`n_strata_int`/`n_strata_ext`.
    """
    payload = {
        "data_path": data_path,
        "z_int_expr": z_int_expr,
        "y_int_expr": y_int_expr,
        "stratum_int_expr": stratum_int_expr,
        "z_ext_expr": z_ext_expr,
        "y_ext_expr": y_ext_expr,
        "stratum_ext_expr": stratum_ext_expr,
        "etas": etas,
        "alpha": alpha,
        "lambda": lambda_,
        "nlambda": nlambda,
        "lambda_min_ratio": lambda_min_ratio,
        "cv_criteria": cv_criteria,
        "nfolds": nfolds,
        "seed": seed,
    }
    return _attach_enet_speed_notice(
        _attach_plot_hint(_run_r("cv_ncc_indi_enet.R", payload), highdim=True)
    )


if __name__ == "__main__":
    mcp.run()
