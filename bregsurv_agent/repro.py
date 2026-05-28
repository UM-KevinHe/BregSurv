"""Generate a standalone ``repro.R`` from an :class:`AgentTrace`.

What ``repro.R`` does when run: replays each fit/cv tool call with the
*effective_args* the agent dispatched (after eta-default resolution) and
prints each R result. Skips informational tools (``inspect_data``,
``generate_eta``, ``start_analysis``) and any event whose status was not
``ok``.

Strategy (Stage 4a — pragmatic): each replayed call shells out to the
existing ``mcp/r_scripts/<tool>.R`` via ``Rscript``. This guarantees
bit-match with the agent (same R script, same args, same R session
flags) but means the user must have ``mcp/r_scripts/`` on disk.

TODO (Stage 4e, paper-quality): emit fully standalone R that calls the
BregSurv package functions directly (e.g. ``coxkl(z=..., ...)``)
without going through the MCP dispatcher. That would let a reviewer
reproduce the agent's coefficients with just the BregSurv R package
installed. Until then, ``repro.R`` requires the MCP repo checkout.
"""
from __future__ import annotations

from typing import Any

from .trace import AgentTrace

_INFO_ONLY_TOOLS = {"inspect_data", "generate_eta", "start_analysis"}


def _r_literal(value: Any) -> str:
    """Convert a Python value to an R literal expression."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Escape backslashes + quotes; preserve UTF-8.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return "c()"
        # If all elements are the same scalar type, use c(); else use list().
        if all(isinstance(v, bool) for v in value):
            return "c(" + ", ".join("TRUE" if v else "FALSE" for v in value) + ")"
        if all(isinstance(v, (int, float)) and not isinstance(v, bool)
               for v in value):
            return "c(" + ", ".join(repr(v) for v in value) + ")"
        if all(isinstance(v, str) for v in value):
            return "c(" + ", ".join(_r_literal(v) for v in value) + ")"
        return "list(" + ", ".join(_r_literal(v) for v in value) + ")"
    if isinstance(value, dict):
        items = [f"{k} = {_r_literal(v)}" for k, v in value.items()]
        return "list(" + ", ".join(items) + ")"
    # Fallback — treat as string.
    return _r_literal(str(value))


def render_repro_r(trace: AgentTrace) -> str:
    """Return the contents of ``repro.R`` as a string."""
    header = [
        "#!/usr/bin/env Rscript",
        "#",
        "# repro.R — replay of one BregSurv agent run.",
        f"# Generated:    {trace.finished_at or trace.started_at}",
        f"# User query:   {trace.user_query.replace(chr(10), ' ')[:200]}",
        f"# Model:        {trace.model_name} @ {trace.model_endpoint}",
        f"# Prompt SHA:   {trace.system_prompt_sha256}",
        "#",
        "# Each block below dispatches one tool call against the same",
        "# R script the agent used (mcp/r_scripts/<tool>.R). Provide the",
        "# path to the mcp/r_scripts directory via the SURVBREGDIV_R_SCRIPTS",
        "# environment variable, or set the default below.",
        "",
        "suppressPackageStartupMessages({",
        "  library(jsonlite)",
        "})",
        "",
        "MCP_R_SCRIPTS <- Sys.getenv(",
        "  'SURVBREGDIV_R_SCRIPTS',",
        "  unset = file.path(getwd(), 'mcp', 'r_scripts')",
        ")",
        "if (!dir.exists(MCP_R_SCRIPTS)) {",
        "  stop(paste0(",
        "    'mcp/r_scripts/ not found at: ', MCP_R_SCRIPTS, '\\n',",
        "    'Clone the BregSurv-mcp repo and set SURVBREGDIV_R_SCRIPTS.'",
        "  ))",
        "}",
        "RSCRIPT <- Sys.which('Rscript')",
        "if (RSCRIPT == '') stop('Rscript not found on PATH.')",
        "",
        "run_tool <- function(tool_name, args) {",
        "  in_file  <- tempfile(fileext = '.in.json')",
        "  out_file <- tempfile(fileext = '.out.json')",
        "  on.exit({ unlink(in_file); unlink(out_file) }, add = TRUE)",
        "  writeLines(toJSON(args, auto_unbox = TRUE, null = 'null'), in_file)",
        "  script <- file.path(MCP_R_SCRIPTS, paste0(tool_name, '.R'))",
        "  # NOTE: system2() does not individually shell-quote `args`, so paths",
        "  # containing spaces (common on macOS Dropbox folders) get word-split.",
        "  # Build the command string with shQuote on every variable and use",
        "  # system() instead.",
        "  cmd <- paste(",
        "    shQuote(RSCRIPT),",
        "    '--no-save --no-restore --no-init-file',",
        "    shQuote(script), shQuote(in_file), shQuote(out_file)",
        "  )",
        "  status <- system(cmd, ignore.stdout = TRUE, ignore.stderr = TRUE)",
        "  if (!file.exists(out_file))",
        "    stop(sprintf('%s.R produced no output (status=%d)', tool_name, status))",
        "  fromJSON(out_file)",
        "}",
        "",
        "results <- list()",
        "",
    ]

    body = []
    step = 0
    for event in trace.events:
        step += 1
        if event.tool in _INFO_ONLY_TOOLS:
            body.append(
                f"# Step {step}: skipping {event.tool} "
                f"(informational, not part of the model fit)."
            )
            body.append("")
            continue
        if event.status != "ok":
            body.append(
                f"# Step {step}: skipping {event.tool} "
                f"(original run errored: {event.error_message or 'unknown'})."
            )
            body.append("")
            continue

        args_r = _r_literal(event.effective_args)
        var = f"r{step}"
        body += [
            f"# Step {step}: {event.tool}",
            f"cat('=== Step {step}: {event.tool} ===\\n')",
            f"{var}_args <- {args_r}",
            f"{var} <- run_tool('{event.tool}', {var}_args)",
            f"results[['{event.tool}_step{step}']] <- {var}",
            f"print({var})",
            "",
        ]

    footer = [
        "# All steps complete. Inspect `results` for the full set of",
        "# replayed outputs (one named list entry per non-skipped step).",
        "invisible(results)",
        "",
    ]

    return "\n".join(header + body + footer)


def write_repro_r(trace: AgentTrace, path: str) -> None:
    """Write ``repro.R`` to ``path``."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_repro_r(trace))
