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
from bregsurv_agent.report import build_markdown, markdown_to_pdf


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.resolve()
SAMPLES_DIR = REPO_ROOT / "data"
SAMPLE_FILES = sorted(
    [p for p in SAMPLES_DIR.glob("*.rda") if not p.name.startswith(".")]
)

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
"""


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

def _resolve_data_path(sample_choice: str, uploaded_file) -> Optional[str]:
    """Prefer an upload over the sample dropdown. Returns None if neither."""
    if uploaded_file:
        # Gradio File: 4.x exposes file.name (str path).
        try:
            return uploaded_file.name if hasattr(uploaded_file, "name") else str(uploaded_file)
        except Exception:
            return None
    if sample_choice and sample_choice != "(none)":
        return str(SAMPLES_DIR / sample_choice)
    return None


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
    sample_choice: str,
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

    data_path = _resolve_data_path(sample_choice, uploaded_file)
    try:
        agent = _make_agent(endpoint, model, api_key)
        # Pass prior chat history so follow-ups like "use loss instead"
        # or "same data, different criterion" carry forward; without
        # this the agent treats every turn as a fresh conversation and
        # asks for missing context the user has already given.
        response = agent.query(user_msg, data_path=data_path,
                               history=clean_history)
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

with gr.Blocks(title="BregSurv Agent", theme=gr.themes.Soft()) as demo:
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
        with gr.Column(scale=1, min_width=240):
            gr.Markdown("### Data")
            data_sample = gr.Dropdown(
                choices=["(none)"] + [p.name for p in SAMPLE_FILES],
                value="(none)",
                label="Sample dataset",
                info="Bundled .rda files in data/.",
            )
            data_upload = gr.File(
                label="Or upload your own (.rda / .rds / .RData)",
                file_types=[".rda", ".rds", ".RData"],
                visible=(DEPLOYMENT_MODE == "local"),
            )
            if DEPLOYMENT_MODE != "local":
                gr.Markdown(
                    "<small>Uploads disabled in demo mode. "
                    "Use the sample dropdown above.</small>"
                )

        # ---- Center: chat ----
        with gr.Column(scale=2, min_width=420):
            chatbot = gr.Chatbot(height=500, label="Conversation",
                                 show_copy_button=True)
            msg_in = gr.Textbox(
                placeholder="e.g. 'Fit Cox KL on the lowdim sample with "
                            "eta=[0, 0.5, 1] using the good external beta.'",
                lines=2, label="Your message",
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

    outputs = [chatbot, msg_in, coeff_out, cv_plot_out,
               trace_out, repro_out, md_out, pdf_out]
    inputs = [msg_in, chatbot, data_sample, data_upload,
              endpoint_in, model_in, api_key_in]

    send_btn.click(chat_submit, inputs=inputs, outputs=outputs)
    msg_in.submit(chat_submit, inputs=inputs, outputs=outputs)
    clear_btn.click(reset_chat, inputs=None, outputs=outputs)


if __name__ == "__main__":
    demo.queue()
    demo.launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        inbrowser=False,
        show_error=True,
        show_api=False,  # extra defense against gradio_client schema bug
    )
