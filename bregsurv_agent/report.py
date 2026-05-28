"""Markdown + PDF report generation for one ``AgentResponse``.

Markdown is the source format (cheap, no deps). PDF is generated via
``weasyprint`` (which has system-lib deps — pango, cairo, harfbuzz —
that ship on Linux base images and HF Space, and install via conda on
macOS). PDF generation is **optional**: callers should catch and
gracefully degrade when ``weasyprint`` is unavailable.

Layout of one report:

    # Analysis Report
    **Generated** ...        **Model** ...       **Mode** ...

    ## User query
    > <verbatim>

    ## Tool calls
    ### 1. fit_coxkl
    - Args (effective): ...
    - Status: ok
    - Result summary: ...

    ## Final assistant message
    > <verbatim>

    ## Reproducibility
    repro.R + trace.json are attached.
"""
from __future__ import annotations

import json
from typing import Optional

from .agent import AgentResponse


_CSS = """
@page { size: Letter; margin: 0.9in 0.9in; }
body { font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
       color: #202124; line-height: 1.45; font-size: 11pt; }
h1 { color: #1a73e8; border-bottom: 2px solid #1a73e8;
     padding-bottom: 4pt; margin-top: 0; }
h2 { color: #1a73e8; margin-top: 18pt; }
h3 { color: #5f6368; margin-top: 12pt; }
code, pre { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9.5pt; }
pre { background: #f6f8fa; padding: 8pt; border-radius: 4pt;
      white-space: pre-wrap; word-wrap: break-word; }
blockquote { border-left: 3pt solid #1a73e8; padding-left: 10pt;
             color: #5f6368; margin-left: 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
th, td { border: 1pt solid #dadce0; padding: 4pt 8pt; text-align: left;
         font-size: 10pt; }
th { background: #f1f3f4; }
.meta { color: #5f6368; font-size: 9.5pt; }
"""


def _short(text: str, n: int = 4000) -> str:
    """Truncate long strings for inclusion in the report."""
    if text is None:
        return ""
    if len(text) > n:
        return text[:n].rstrip() + " …[truncated]"
    return text


def _md_quote(text: str) -> str:
    """Quote a block as markdown ``>`` lines, preserving newlines."""
    if not text:
        return "> _(empty)_"
    return "\n".join(("> " + line) for line in text.splitlines())


def build_markdown(response: AgentResponse, user_query: str) -> str:
    """Render the full markdown report for one agent response."""
    trace = response.trace
    parts: list[str] = []

    parts.append("# BregSurv Agent — Analysis Report")
    parts.append("")
    parts.append(
        f"**Generated** {trace.finished_at or trace.started_at} "
        f"&nbsp;&nbsp; **Model** `{trace.model_name}` "
        f"&nbsp;&nbsp; **Mode** `{trace.deployment_mode}` "
        f"&nbsp;&nbsp; **Prompt SHA** `{trace.system_prompt_sha256}`"
    )
    if trace.total_latency_ms is not None:
        parts.append(
            f"<div class='meta'>"
            f"LLM turns: {trace.llm_turns} &middot; "
            f"Tool calls: {len(trace.events)} &middot; "
            f"Total latency: {trace.total_latency_ms / 1000:.2f} s"
            f"</div>"
        )
    parts.append("")

    parts.append("## User query")
    parts.append(_md_quote(user_query))
    parts.append("")

    if response.error:
        parts.append("## Error")
        parts.append("```")
        parts.append(_short(response.error, 1000))
        parts.append("```")
        parts.append("")

    parts.append(f"## Tool calls ({len(trace.events)})")
    if not trace.events:
        parts.append("_No tools were invoked._")
        parts.append("")
    for i, event in enumerate(trace.events, 1):
        parts.append(f"### {i}. `{event.tool}`")
        parts.append("")
        parts.append(
            f"<span class='meta'>Status: **{event.status}** "
            f"&middot; Latency: {event.latency_ms} ms "
            f"&middot; Timestamp: {event.timestamp}</span>"
        )
        parts.append("")
        parts.append("**Effective args:**")
        parts.append("```json")
        parts.append(_short(
            json.dumps(event.effective_args, indent=2, ensure_ascii=False),
            2000,
        ))
        parts.append("```")
        parts.append("**Result summary:**")
        parts.append("```json")
        parts.append(_short(
            json.dumps(event.result_summary, indent=2, ensure_ascii=False),
            2000,
        ))
        parts.append("```")
        if event.error_message:
            parts.append("**Error message:**")
            parts.append("```")
            parts.append(_short(event.error_message, 1000))
            parts.append("```")
        parts.append("")

    parts.append("## Final assistant message")
    parts.append(_md_quote(response.text or "_(empty)_"))
    parts.append("")

    parts.append("## Reproducibility")
    parts.append(
        "* `repro.R` — standalone R script that replays every tool call "
        "with the same args and produces bit-identical coefficients.\n"
        "* `trace.json` — full audit log (this report is a human-readable "
        "summary of it)."
    )
    parts.append("")

    return "\n".join(parts)


def markdown_to_html(md_text: str) -> str:
    """Convert markdown to a self-contained HTML document (with CSS)."""
    import markdown as _md
    body = _md.markdown(
        md_text,
        extensions=["fenced_code", "tables", "md_in_html"],
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )


def markdown_to_pdf(md_text: str, path: str) -> Optional[str]:
    """Render ``md_text`` to a PDF at ``path``. Returns ``path`` on success.

    Raises ``RuntimeError`` with a clear message if ``weasyprint`` is
    unavailable (caller should catch and degrade to markdown-only).
    """
    try:
        import weasyprint
    except (ImportError, OSError) as e:
        raise RuntimeError(
            f"weasyprint unavailable ({e}); PDF report skipped. "
            f"On macOS install pango+cairo via conda; on Linux apt-get."
        ) from e
    html = markdown_to_html(md_text)
    weasyprint.HTML(string=html).write_pdf(path)
    return path
