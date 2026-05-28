"""Audit-trail container for one agent run.

The trace is one of the three "verification-backed" pillars: every
tool call (script invoked, args, status, latency, result-summary) is
recorded so a future reader can verify what the agent actually did
without rerunning the LLM.

Design choices:

* ``args`` is the EXACT dict sent to ``runner.run_r`` — i.e. after the
  agent's :func:`tools.dispatch` resolved the eta default (if any).
  Original LLM-emitted args are also recorded under ``llm_args`` so the
  trace can distinguish what the LLM said from what we ran.
* ``result_summary`` is a small dict (status + a few key fields), NOT
  the full R return. Full results live in the agent response object
  during the run; saving everything to trace.json would bloat the file
  with coefficient matrices that are also in the chat.
* Token usage is best-effort: vLLM exposes it via the OpenAI usage
  field; some providers don't. ``None`` is acceptable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class TraceEvent:
    """One tool-call record."""
    timestamp: str
    tool: str
    llm_args: Dict[str, Any]
    effective_args: Dict[str, Any]
    status: str
    result_summary: Dict[str, Any]
    latency_ms: int
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentTrace:
    """All tool calls + run-level metadata for one ``agent.query()``."""
    user_query: str
    model_name: str
    model_endpoint: str
    system_prompt_sha256: str
    deployment_mode: str
    started_at: str = field(default_factory=_utc_iso)
    finished_at: Optional[str] = None
    total_latency_ms: Optional[int] = None
    llm_turns: int = 0
    prompt_tokens_total: Optional[int] = None
    completion_tokens_total: Optional[int] = None
    events: List[TraceEvent] = field(default_factory=list)

    def add_event(self, event: TraceEvent) -> None:
        self.events.append(event)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_query": self.user_query,
            "model_name": self.model_name,
            "model_endpoint": self.model_endpoint,
            "system_prompt_sha256": self.system_prompt_sha256,
            "deployment_mode": self.deployment_mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_latency_ms": self.total_latency_ms,
            "llm_turns": self.llm_turns,
            "prompt_tokens_total": self.prompt_tokens_total,
            "completion_tokens_total": self.completion_tokens_total,
            "events": [e.to_dict() for e in self.events],
        }

    def save(self, path: str) -> None:
        """Write trace as pretty JSON to ``path``."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def summarize_result(tool: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a full R result dict to a small ``result_summary`` for trace.

    Keeps: status, common scalar fields (n_obs, n_etas, eta, message,
    where, class), and a one-line description of any large arrays
    ("beta": [6x4 matrix]"). Skips raw arrays and decorating notices.
    """
    if not isinstance(result, dict):
        return {"status": "non_dict", "type": type(result).__name__}

    keep_scalar = {
        "status", "message", "class", "where", "returncode",
        "n_obs", "n_covariates", "n_etas", "n_internal", "n_external",
        "external_via", "method", "criteria", "n", "max_eta", "min_eta",
    }
    summary: Dict[str, Any] = {}
    for k, v in result.items():
        if k in keep_scalar:
            summary[k] = v
        elif isinstance(v, list):
            if v and isinstance(v[0], list):
                # 2D array
                summary[k + "_shape"] = [len(v), len(v[0])]
            else:
                summary[k + "_length"] = len(v)
        elif isinstance(v, dict):
            # Drill one level for cv_metric.{name,values} etc.
            if "name" in v:
                summary[k + ".name"] = v.get("name")
            if "values" in v and isinstance(v["values"], list):
                summary[k + ".values_length"] = len(v["values"])
            if "best_eta" in v:
                summary[k + ".best_eta"] = v["best_eta"]
            if "best_lambda" in v:
                summary[k + ".best_lambda"] = v["best_lambda"]
    return summary
