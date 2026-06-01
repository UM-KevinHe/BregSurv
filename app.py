"""Gradio Web UI for the BregSurv agent.

Entry point for three deployment targets:
  * Local self-host (`python app.py` → http://localhost:7860).
  * Docker container (same as local + DEPLOYMENT_MODE/Rscript baked in).
  * HuggingFace Space (HF picks up ``app.py`` at the repo root).

Environment variables (override at runtime via the "Model & connection"
accordion if you want to test without resetting them):

  ============================== =========================================
  ``OPENAI_API_KEY``             LLM auth (required for the default
                                 OpenAI endpoint).
  ``SURVBREGDIV_MODEL_ENDPOINT`` OpenAI-compatible base URL.
                                 Default: ``https://api.openai.com/v1``.
                                 Set to ``http://localhost:8000/v1`` for
                                 a local vLLM Qwen 7B AWQ.
  ``SURVBREGDIV_MODEL_NAME``     Model identifier. Default: ``gpt-4o-mini``.
                                 Use ``qwen2.5-7b-awq`` for vLLM.
  ``DEPLOYMENT_MODE``            ``local`` (default) shows the upload
                                 widget. ``demo`` hides it.
  ``SURVBREGDIV_RSCRIPT``        Override Rscript path.
  ``SURVBREGDIV_R_SCRIPTS``      Override the R-script directory
                                 (default ``mcp/r_scripts`` next to this
                                 file).
  ============================== =========================================
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import traceback
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Monkey-patch gradio_client to fix a known bug where its JSON-schema
# walker crashes on bool-valued schemas (e.g. `additionalProperties: true`
# emitted by gr.Dataframe / gr.Chatbot). The bug is fixed in
# gradio_client >= 1.4.1, but Gradio 4.44 pins gradio_client ~= 1.3, so
# we patch in place rather than juggling versions. Without this, HF Space
# startup crashes inside `gradio_client.utils.get_type(schema)` with
# `TypeError: argument of type 'bool' is not iterable`.
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

import gradio as gr
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend; we render figures to PNG ourselves
import matplotlib.pyplot as plt
from PIL import Image

from bregsurv_agent import BregSurvAgent, AgentResponse
from bregsurv_agent import tools
from bregsurv_agent.report import build_markdown, markdown_to_pdf


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.resolve()
SAMPLES_DIR = REPO_ROOT / "data"

# --------------------------------------------------------------------------
# Demo dataset catalogue (user-facing).
#
# The reviewer picks a study type + a friendly dataset name + an external
# estimate; the UI resolves these to the real .rda file, the family, and
# the exact R field expressions. Those resolved facts are injected into
# the agent (see _build_bound_context) so the 7B model never has to guess
# the object name, the field paths, or the beta-object path — eliminating
# the bare-`beta_external` / wrong-family / train-vs-test-confusion bugs.
# Individual-level (`indi`) datasets are intentionally excluded from the
# demo to keep the choice space small; the KL family (coxkl / ncckl) is
# the flagship method.
# --------------------------------------------------------------------------

DEMO_DATASETS = {
    "Cohort · low-dimensional (6 covariates)": {
        "file": "ExampleData_lowdim.rda",
        "object": "ExampleData_lowdim",
        "family": "cox",
        "exprs": {
            "z_expr": "ExampleData_lowdim$train$z",
            "time_expr": "ExampleData_lowdim$train$time",
            "delta_expr": "ExampleData_lowdim$train$status",
            "stratum_expr": "ExampleData_lowdim$train$stratum",
        },
        "betas": {
            "Good external estimate": "ExampleData_lowdim$beta_external_good",
            "Fair external estimate": "ExampleData_lowdim$beta_external_fair",
            "Poor external estimate": "ExampleData_lowdim$beta_external_poor",
        },
    },
    "Cohort · high-dimensional (50 covariates)": {
        "file": "ExampleData_highdim.rda",
        "object": "ExampleData_highdim",
        "family": "cox",
        "exprs": {
            "z_expr": "ExampleData_highdim$train$z",
            "time_expr": "ExampleData_highdim$train$time",
            "delta_expr": "ExampleData_highdim$train$status",
            "stratum_expr": "ExampleData_highdim$train$stratum",
        },
        "betas": {
            "External estimate": "ExampleData_highdim$beta_external",
        },
    },
    "Nested case-control · low-dimensional (6 covariates)": {
        "file": "ExampleData_cc_lowdim.rda",
        "object": "ExampleData_cc_lowdim",
        "family": "ncc",
        "exprs": {
            "z_expr": "ExampleData_cc_lowdim$train$z",
            "y_expr": "ExampleData_cc_lowdim$train$y",
            "stratum_expr": "ExampleData_cc_lowdim$train$stratum",
        },
        "betas": {
            "External estimate": "ExampleData_cc_lowdim$beta_external",
        },
    },
    "Nested case-control · high-dimensional (20 covariates)": {
        "file": "ExampleData_cc_highdim.rda",
        "object": "ExampleData_cc_highdim",
        "family": "ncc",
        "exprs": {
            "z_expr": "ExampleData_cc_highdim$train$z",
            "y_expr": "ExampleData_cc_highdim$train$y",
            "stratum_expr": "ExampleData_cc_highdim$train$stratum",
        },
        "betas": {
            "External estimate": "ExampleData_cc_highdim$beta_external",
        },
    },
}

STUDY_TYPES = ["Any", "Cohort (Cox)", "Nested case-control (NCC)"]
_STUDY_FAMILY = {"Cohort (Cox)": "cox", "Nested case-control (NCC)": "ncc"}
ETA_METHODS = ["exponential", "linear"]


def _datasets_for_study_type(study_type: str):
    """Friendly dataset names admissible under the chosen study type."""
    fam = _STUDY_FAMILY.get(study_type)
    if fam is None:  # "Any"
        return list(DEMO_DATASETS)
    return [name for name, d in DEMO_DATASETS.items() if d["family"] == fam]


def _beta_choices(dataset_name: str):
    """External-estimate choices for a dataset (e.g. good/fair/poor)."""
    d = DEMO_DATASETS.get(dataset_name)
    return list(d["betas"]) if d else []

DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "local").lower()
DEFAULT_ENDPOINT = os.environ.get(
    "SURVBREGDIV_MODEL_ENDPOINT", "https://api.openai.com/v1"
)
DEFAULT_MODEL = os.environ.get("SURVBREGDIV_MODEL_NAME", "gpt-4o-mini")
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")

INTRO_MD = """\
# BregSurv Agent

Survival-analysis transfer learning with the
[BregSurv](https://um-kevinhe.github.io/BregSurv/) R package, driven
by a tool-use LLM agent. Describe your analysis in plain language; the
agent picks the right estimator, runs it on your data locally, and
returns coefficients along with a reproducible R script.

*Tip: press **Tab** in an empty message box to auto-fill the example query.*
"""

# Canonical example query — kept in one place so the textbox placeholder
# and the Tab-to-fill JS stay in sync.
EXAMPLE_QUERY = (
    "Cross-validate the KL model on the selected data and plot the CV path."
)

# Injected on page load: pressing Tab in the (empty) message box fills
# the example. Document-level capture listener survives Gradio re-renders.
# Uses the native value setter + an 'input' event so Svelte picks up the
# change (a bare el.value = ... would desync Gradio's reactive state).
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


# --------------------------------------------------------------------------
# Mode banner
# --------------------------------------------------------------------------

def _mode_banner_html() -> str:
    if DEPLOYMENT_MODE == "demo":
        return (
            "<div style='background:#ffebee;color:#c62828;"
            "padding:10px 14px;border-radius:6px;border:1px solid #ef9a9a;"
            "font-weight:600;'>"
            "⚠️ DEMO MODE — File uploads are disabled. "
            "Use the bundled sample datasets only. "
            "Tool args + chat messages transit the LLM provider; "
            "raw data values do not."
            "</div>"
        )
    return (
        "<div style='background:#e8f5e9;color:#2e7d32;"
        "padding:10px 14px;border-radius:6px;border:1px solid #a5d6a7;"
        "font-weight:600;'>"
        "🔒 LOCAL MODE — Your data stays on this machine. "
        "Only tool calls and chat messages reach the LLM provider; "
        "file contents are read by a local R subprocess."
        "</div>"
    )


# --------------------------------------------------------------------------
# Data path resolution
# --------------------------------------------------------------------------

def _resolve_upload_path(uploaded_file) -> Optional[str]:
    """Local-mode upload path (Gradio File exposes ``.name``)."""
    if not uploaded_file:
        return None
    try:
        return uploaded_file.name if hasattr(uploaded_file, "name") else str(uploaded_file)
    except Exception:
        return None


def _build_bound_context(dataset_name: str, beta_choice: str,
                         eta_method: str, eta_n: int, eta_max: float):
    """Resolve sidebar selections to (data_path, family, bound_context_str).

    The returned ``bound_context_str`` is injected into the agent message
    as authoritative pre-resolved facts (object/field paths, the exact
    external-beta object path, the eta grid). Returns (None, None, None)
    when the dataset is unknown.
    """
    d = DEMO_DATASETS.get(dataset_name)
    if d is None:
        return None, None, None
    data_path = str(SAMPLES_DIR / d["file"])
    family = d["family"]

    # External-beta object path (full, e.g. ExampleData_lowdim$beta_external_fair).
    betas = d["betas"]
    beta_expr = betas.get(beta_choice) or next(iter(betas.values()))

    # Eta grid for cross-validation — generated by the R package's own
    # generate_eta so it matches exactly what a reproducible script would
    # produce (user choice: UI builds the grid; the model never hand-writes it).
    etas = None
    try:
        g = tools.dispatch("generate_eta", method=eta_method,
                           n=int(eta_n), max_eta=float(eta_max))
        if isinstance(g, dict):
            etas = g.get("etas")
    except Exception:
        etas = None

    fam_word = "cohort" if family == "cox" else "NCC"
    kl_tool = "coxkl" if family == "cox" else "ncckl"
    lines = [
        "SELECTED SETUP — use these EXACT argument values; do not alter, "
        "re-derive, or translate them:",
        f"- Study family: {family}  (call a {fam_word}-family tool only)",
        f"- Method: KL divergence — the external information is a "
        f"coefficient VECTOR, so use the KL tool (fit_{kl_tool} / "
        f"cv_{kl_tool} or its _enet variant). This is NOT individual-"
        f"level external data: the $test split is held-out evaluation "
        f"data, never an external cohort, so do NOT use an _indi tool.",
        f"- data_path: {data_path}",
    ]
    for arg, expr in d["exprs"].items():
        lines.append(f'- {arg}: "{expr}"')
    lines.append(f'- beta_expr (external coefficients): "{beta_expr}"')
    if etas:
        lines.append(
            f"- For cross-validation use this eta grid verbatim: etas={etas}"
        )
    return data_path, family, "\n".join(lines)


# --------------------------------------------------------------------------
# Coefficient table extraction
# --------------------------------------------------------------------------

def _last_fit_result(response: AgentResponse) -> Optional[dict]:
    """Return the most-recent fit_*/cv_* tool result, or None."""
    for entry in reversed(response.tool_results):
        tool = entry.get("tool", "")
        if tool.startswith("fit_") or tool.startswith("cv_"):
            res = entry.get("result", {})
            if isinstance(res, dict) and res.get("status") == "ok":
                return entry
    return None


def _coefficients_df(response: AgentResponse) -> Optional[pd.DataFrame]:
    """Convert the last fit/cv result's ``beta`` (and ``eta``) into a DataFrame.

    Layout: rows = covariates (Z1, Z2, ...), columns = etas. For ``cv_*``
    results we use ``best.best_beta`` (a single column at best eta).
    """
    entry = _last_fit_result(response)
    if entry is None:
        return None
    result = entry["result"]
    tool = entry["tool"]

    if tool.startswith("cv_"):
        best = result.get("best") or {}
        best_beta = best.get("best_beta")
        if not best_beta:
            return None
        return pd.DataFrame(
            {f"eta={best.get('best_eta')}": best_beta},
            index=[f"Z{i+1}" for i in range(len(best_beta))],
        )

    # fit_* path
    beta = result.get("beta")
    etas = result.get("eta") or result.get("etas")
    if not beta:
        return None
    # beta is p x n_etas (rowmajor matrix in JSON). For fit_*_indi_enet
    # it's a list-per-eta jagged structure — skip in that case.
    if isinstance(beta[0], list):
        try:
            df = pd.DataFrame(
                beta,
                columns=[f"eta={e}" for e in (etas or [])][:len(beta[0])],
                index=[f"Z{i+1}" for i in range(len(beta))],
            )
            return df
        except Exception:
            return None
    # Plain vector (e.g., n_etas=1).
    return pd.DataFrame(
        {f"eta={etas[0] if etas else 'NA'}": beta},
        index=[f"Z{i+1}" for i in range(len(beta))],
    )


# --------------------------------------------------------------------------
# CV-path plot
# --------------------------------------------------------------------------

_LOSS_CRITERIA = {"V&VH", "LinPred", "loss", "Brier"}
_INDEX_CRITERIA = {"CIndex_pooled", "CIndex_foldaverage", "CIndex", "AUC"}


def _cv_plot(response: AgentResponse) -> Optional[Image.Image]:
    """Build a PIL Image of the CV path for the last cv_* result, or None.

    Returns a PIL Image (PNG-rendered from matplotlib) rather than a raw
    matplotlib ``Figure`` so we bypass Gradio 4.44's
    matplotlib-to-webp serialization path — that path explodes on the
    old matplotlib 3.3.x shipped with anaconda Python 3.8 (no webp
    backend; the error reads "Format 'webp' is not supported"). PIL
    Image goes through gr.Image directly, no format negotiation.
    """
    cv_entry = None
    for entry in reversed(response.tool_results):
        if entry.get("tool", "").startswith("cv_"):
            res = entry.get("result")
            if isinstance(res, dict) and res.get("status") == "ok":
                cv_entry = entry
                break
    if cv_entry is None:
        return None
    res = cv_entry["result"]
    etas = res.get("etas") or []
    metric = res.get("cv_metric") or {}
    values = metric.get("values") or []
    name = metric.get("name", "metric")
    best = (res.get("best") or {}).get("best_eta")
    if not (etas and values):
        return None

    fig, ax = plt.subplots(figsize=(5, 3.2), dpi=110)
    ax.plot(etas, values, marker="o", color="#1a73e8")
    ax.set_xlabel("η (eta)")

    # Y-axis label by criterion.
    criteria = res.get("criteria") or name
    smaller_better = criteria in _LOSS_CRITERIA
    larger_better = criteria in _INDEX_CRITERIA
    if smaller_better:
        ax.set_ylabel(f"{criteria} (loss, lower=better)")
    elif larger_better:
        ax.set_ylabel(f"{criteria} (index, higher=better)")
    else:
        ax.set_ylabel(name)

    if best is not None:
        ax.axvline(best, color="#d93025", linestyle="--", linewidth=1,
                   label=f"best η = {best:g}")
        ax.legend()
    ax.set_title(f"CV path — {cv_entry['tool']}")
    fig.tight_layout()

    # Render to PNG bytes, wrap in PIL Image, free the Figure.
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)


# --------------------------------------------------------------------------
# Download bundles
# --------------------------------------------------------------------------

def _write_downloads(response: AgentResponse, user_query: str):
    """Write trace.json, repro.R, report.md, report.pdf to a temp dir.

    Returns (trace_path, repro_path, md_path, pdf_path); any may be None
    if writing failed (e.g. weasyprint missing).
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="bregsurv_"))
    trace_path = tmpdir / "trace.json"
    repro_path = tmpdir / "repro.R"
    md_path = tmpdir / "report.md"
    pdf_path = tmpdir / "report.pdf"

    try:
        response.save_trace(str(trace_path))
    except Exception:
        trace_path = None
    try:
        response.write_repro_r(str(repro_path))
    except Exception:
        repro_path = None

    md_text = build_markdown(response, user_query)
    try:
        md_path.write_text(md_text, encoding="utf-8")
    except Exception:
        md_path = None
    try:
        markdown_to_pdf(md_text, str(pdf_path))
    except Exception:
        pdf_path = None

    return (
        str(trace_path) if trace_path else None,
        str(repro_path) if repro_path else None,
        str(md_path) if md_path else None,
        str(pdf_path) if pdf_path else None,
    )


# --------------------------------------------------------------------------
# Chat handler
# --------------------------------------------------------------------------

def _make_agent(endpoint: str, model: str, api_key: str) -> BregSurvAgent:
    """Build a fresh agent (per query — keeps the state-machine simple)."""
    return BregSurvAgent(
        model_endpoint=endpoint or DEFAULT_ENDPOINT,
        model_name=model or DEFAULT_MODEL,
        api_key=api_key or DEFAULT_API_KEY or "EMPTY",
        deployment_mode=DEPLOYMENT_MODE,
    )


def chat_submit(
    user_msg: str,
    history: List[Tuple[str, str]],
    dataset_name: str,
    beta_choice: str,
    eta_method: str,
    eta_n: int,
    eta_max: float,
    uploaded_file,
    endpoint: str,
    model: str,
    api_key: str,
):
    """One round: send user message through the agent, render results.

    Returns the new tuple matching the .outputs= list below.
    """
    history = history or []
    if not user_msg or not user_msg.strip():
        return (history, "", None, None, None, None, None, None)

    # Strip the UI-only "<small>Tools: ...</small>" suffix from prior
    # assistant turns before feeding history back to the LLM — that
    # marker is a UI affordance, not something we want the model to
    # learn to emit. Use the marker comment also added at write time.
    clean_history = []
    for entry in (history or []):
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            u, a = entry[0], entry[1]
            if isinstance(a, str):
                a = re.sub(r"\n\n<small>Tools:[^<]*</small>\s*$", "", a)
            clean_history.append((u, a))

    # Resolve the data source. An upload (local mode) takes precedence and
    # uses the un-bound path (the agent auto-inspects and builds args).
    # Otherwise a selected demo dataset is fully resolved: data_path,
    # family override (for tool subsetting), and a bound-context block of
    # pre-resolved field/beta/eta facts injected into the agent message.
    upload_path = _resolve_upload_path(uploaded_file)
    if upload_path:
        data_path, family_override, bound_context = upload_path, None, None
        method_override = None
    else:
        data_path, family_override, bound_context = _build_bound_context(
            dataset_name, beta_choice, eta_method, eta_n, eta_max)
        # Demo external info is always a coefficient vector → KL family.
        method_override = "kl" if family_override else None

    try:
        agent = _make_agent(endpoint, model, api_key)
        # Pass prior chat history so follow-ups like "use loss instead"
        # or "same data, different criterion" carry forward; without
        # this the agent treats every turn as a fresh conversation and
        # asks for missing context the user has already given.
        response = agent.query(user_msg, data_path=data_path,
                               history=clean_history,
                               family_override=family_override,
                               method_override=method_override,
                               bound_context=bound_context)
    except Exception:
        tb = traceback.format_exc()
        history.append((user_msg, f"**Agent crashed:**\n```\n{tb[-2000:]}\n```"))
        return (history, "", None, None, None, None, None, None)

    assistant_text = response.text or "_(no assistant reply)_"
    if response.error:
        assistant_text += f"\n\n**Note:** {response.error}"
    if response.trace.events:
        tools_called = ", ".join(
            f"`{e.tool}`" + (f" ({e.status})" if e.status != "ok" else "")
            for e in response.trace.events
        )
        assistant_text += f"\n\n<small>Tools: {tools_called}</small>"

    history.append((user_msg, assistant_text))

    coeff_df = _coefficients_df(response)
    plot_fig = _cv_plot(response)
    trace_p, repro_p, md_p, pdf_p = _write_downloads(response, user_msg)

    return (history, "", coeff_df, plot_fig, trace_p, repro_p, md_p, pdf_p)


def reset_chat():
    return ([], "", None, None, None, None, None, None)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

with gr.Blocks(title="BregSurv Agent", theme=gr.themes.Soft(),
               js=_TAB_AUTOFILL_JS) as demo:
    gr.HTML(_mode_banner_html())
    gr.Markdown(INTRO_MD)

    with gr.Accordion("Model & connection", open=False):
        with gr.Row():
            endpoint_in = gr.Textbox(
                value=DEFAULT_ENDPOINT, label="Model endpoint (OpenAI-compatible)",
                placeholder="https://api.openai.com/v1",
            )
            model_in = gr.Textbox(
                value=DEFAULT_MODEL, label="Model name",
                placeholder="gpt-4o-mini",
            )
            api_key_in = gr.Textbox(
                value=DEFAULT_API_KEY, label="API key",
                type="password", placeholder="sk-...",
            )

    with gr.Row():
        # ---- Left: data ----
        with gr.Column(scale=1, min_width=260):
            gr.Markdown("### 1 · Choose your data")
            _DEFAULT_STUDY = "Cohort (Cox)"
            _default_datasets = _datasets_for_study_type(_DEFAULT_STUDY)
            _default_ds = "Cohort · low-dimensional (6 covariates)"
            _default_beta = "Poor external estimate"
            study_type = gr.Radio(
                choices=STUDY_TYPES, value=_DEFAULT_STUDY,
                label="Study type",
                info="Optional — filters the datasets below.",
            )
            data_sample = gr.Dropdown(
                choices=_default_datasets, value=_default_ds,
                label="Dataset",
            )
            beta_select = gr.Dropdown(
                choices=_beta_choices(_default_ds),
                value=_default_beta,
                label="External information",
                info="The external estimate to borrow from.",
            )

            gr.Markdown("### 2 · Eta grid (for cross-validation)")
            eta_method = gr.Dropdown(
                choices=ETA_METHODS, value="exponential",
                label="Spacing",
            )
            with gr.Row():
                eta_n = gr.Number(value=20, label="# of etas", precision=0,
                                  minimum=2, maximum=50)
                eta_max = gr.Number(value=50.0, label="Max eta", minimum=0.1)

            data_upload = gr.File(
                label="Or upload your own (.rda / .rds / .RData)",
                file_types=[".rda", ".rds", ".RData"],
                visible=(DEPLOYMENT_MODE == "local"),
            )

        # ---- Center: chat ----
        with gr.Column(scale=2, min_width=420):
            chatbot = gr.Chatbot(height=500, label="Conversation",
                                 show_copy_button=True)
            msg_in = gr.Textbox(
                placeholder=f"e.g. '{EXAMPLE_QUERY}'  (press Tab to fill)",
                lines=2, label="Your message", elem_id="msg_in",
            )
            with gr.Row():
                send_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear")

        # ---- Right: results ----
        with gr.Column(scale=2, min_width=420):
            gr.Markdown("### Results")
            coeff_out = gr.Dataframe(
                label="Coefficients (rows = covariates, columns = etas)",
                interactive=False, wrap=True,
            )
            cv_plot_out = gr.Image(
                label="CV path (if a cv_* tool was called)",
                type="pil", interactive=False, height=320,
            )
            gr.Markdown("### Downloads")
            with gr.Row():
                trace_out = gr.File(label="trace.json", interactive=False)
                repro_out = gr.File(label="repro.R", interactive=False)
            with gr.Row():
                md_out = gr.File(label="report.md", interactive=False)
                pdf_out = gr.File(label="report.pdf", interactive=False)

    # ----------------------------- Handlers --------------------------------

    # Cascade: study type filters the dataset list; dataset choice resets
    # the external-information options to that dataset's set.
    def _on_study_type(study_type_val):
        names = _datasets_for_study_type(study_type_val)
        first = names[0] if names else None
        betas = _beta_choices(first) if first else []
        return (
            gr.update(choices=names, value=first),
            gr.update(choices=betas, value=(betas[0] if betas else None)),
        )

    def _on_dataset(dataset_val):
        betas = _beta_choices(dataset_val)
        return gr.update(choices=betas, value=(betas[0] if betas else None))

    study_type.change(_on_study_type, inputs=study_type,
                      outputs=[data_sample, beta_select])
    data_sample.change(_on_dataset, inputs=data_sample, outputs=beta_select)

    outputs = [chatbot, msg_in, coeff_out, cv_plot_out,
               trace_out, repro_out, md_out, pdf_out]
    inputs = [msg_in, chatbot, data_sample, beta_select,
              eta_method, eta_n, eta_max, data_upload,
              endpoint_in, model_in, api_key_in]

    send_btn.click(chat_submit, inputs=inputs, outputs=outputs)
    msg_in.submit(chat_submit, inputs=inputs, outputs=outputs)
    clear_btn.click(reset_chat, inputs=None, outputs=outputs)


def _resolve_auth():
    """Return Gradio auth tuple from env, or None when unset.

    Both ``BREGSURV_AUTH_USER`` and ``BREGSURV_AUTH_PASS`` must be set
    (non-empty) for the login gate to engage. This is the HF Space
    deployment pattern: credentials live in HF Space Secrets, never in
    the image. Local Docker self-host and dev runs leave the env vars
    unset so Gradio launches without a login page.
    """
    user = os.environ.get("BREGSURV_AUTH_USER", "").strip()
    pw = os.environ.get("BREGSURV_AUTH_PASS", "").strip()
    if user and pw:
        return (user, pw)
    return None


if __name__ == "__main__":
    demo.queue()
    _auth = _resolve_auth()
    if _auth is not None:
        print(f"[app] Gradio auth enabled (user={_auth[0]})", flush=True)
    demo.launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        inbrowser=False,
        show_error=True,
        show_api=False,  # extra defense against gradio_client schema bug
        auth=_auth,
        auth_message=(
            "Reviewer access only. Credentials are provided in the "
            "paper submission. Random visitors: please use the local "
            "Docker self-host (mcp/DEPLOY.md) instead."
        ),
    )
