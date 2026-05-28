"""Top-level :class:`BregSurvAgent` and :class:`AgentResponse`.

The agent talks to any OpenAI-compatible Chat-Completions endpoint
(vLLM ``--enable-auto-tool-choice``, Together AI, OpenRouter, ...). It
loops:

    user query
        → LLM ↦ tool_calls
        → :func:`tools.dispatch` (R subprocess, post-processing)
        → append tool messages
        → LLM (next turn)
        → ... until LLM returns no more tool_calls
        → final assistant text → :class:`AgentResponse`

A trace event is recorded at every R subprocess call. Stub-LLM clients
that implement ``chat.completions.create`` can be injected via
``client=`` for tests that don't require a running vLLM.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import tools as _tools
from .prompts import SYSTEM_PROMPT_V2, prompt_sha256
from .trace import AgentTrace, TraceEvent, summarize_result, _utc_iso
from .repro import write_repro_r


@dataclass
class AgentResponse:
    """Container returned by :meth:`BregSurvAgent.query`.

    ``text`` is the LLM's final user-facing answer (after all tool
    rounds). ``trace`` is the full audit record. ``tool_results`` is
    the in-memory list of full R results (not summarized), useful for
    Gradio UIs that want to render coefficient tables / plots.
    """
    text: str
    trace: AgentTrace
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def save_trace(self, path: str) -> None:
        self.trace.save(path)

    def write_repro_r(self, path: str) -> None:
        write_repro_r(self.trace, path)


class BregSurvAgent:
    """LLM tool-use loop over the BregSurv R catalogue.

    Parameters
    ----------
    model_endpoint:
        OpenAI-compatible base URL (e.g. ``http://localhost:8000/v1`` for
        a local vLLM server, ``https://api.together.xyz/v1`` for Together).
    model_name:
        Model identifier the endpoint expects (must match vLLM's
        ``--served-model-name`` or the provider's listed model).
    api_key:
        Bearer token. vLLM ignores key values; pass anything non-empty.
    system_prompt:
        Override the default ``SYSTEM_PROMPT_V2``. The default is a
        placeholder; for serious use replace with the canonical v2
        prompt from ``benchmark_routing_v2.py``.
    deployment_mode:
        ``"local"`` (user can upload data files) or ``"demo"`` (sample
        datasets only). Recorded in trace.json; downstream UIs can use
        it to gate the upload widget.
    max_turns:
        Safeguard against infinite LLM loops. 12 is plenty for the
        wizard + inspect + fit + cv path; raise if you build longer
        workflows.
    client:
        Optional pre-built OpenAI-style client. If omitted, a fresh
        ``openai.OpenAI`` is constructed from ``model_endpoint`` +
        ``api_key``. Tests pass a stub here.
    """

    def __init__(
        self,
        model_endpoint: str,
        model_name: str = "qwen2.5-7b-awq",
        api_key: str = "EMPTY",
        system_prompt: Optional[str] = None,
        deployment_mode: str = "local",
        max_turns: int = 12,
        client: Optional[Any] = None,
    ) -> None:
        self.model_endpoint = model_endpoint
        self.model_name = model_name
        self.api_key = api_key
        self.system_prompt = system_prompt or SYSTEM_PROMPT_V2
        self.deployment_mode = deployment_mode
        self.max_turns = max_turns
        self._client = client
        # Cache schemas once per instance.
        self._tool_schemas = _tools.load_schemas()

    # -- Lazy OpenAI client construction (defers import) --------------------

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai SDK not installed. Run `pip install openai`."
            ) from e
        self._client = OpenAI(
            base_url=self.model_endpoint,
            api_key=self.api_key,
        )
        return self._client

    # -- Main query loop ----------------------------------------------------

    def query(
        self,
        user_text: str,
        data_path: Optional[str] = None,
        history: Optional[List] = None,
    ) -> AgentResponse:
        """Run one user turn end-to-end. Returns an :class:`AgentResponse`.

        ``history`` is an optional list of ``(user_msg, assistant_msg)``
        tuples (the format Gradio's ``Chatbot`` uses) representing the
        prior turns of THIS conversation. When provided, they are
        prepended to the messages list so the LLM has multi-turn
        context — without this, follow-ups like "use loss instead" or
        "same as before" cannot be routed because the agent only sees
        the single current message. The inner tool_call / tool_result
        chain from prior turns is NOT replayed (would bloat tokens for
        no benefit; the prior assistant's natural-language summary is
        enough context for routing).
        """
        start = time.monotonic()
        trace = AgentTrace(
            user_query=user_text,
            model_name=self.model_name,
            model_endpoint=self.model_endpoint,
            system_prompt_sha256=prompt_sha256(self.system_prompt),
            deployment_mode=self.deployment_mode,
        )

        # Optionally include data_path as a context line so the model
        # knows the exact path string to pass to tool args.
        user_content = user_text
        if data_path is not None:
            user_content += (
                f"\n\n[The user's data file is at: {data_path}]"
            )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        # Replay prior turns from Gradio history (user + final assistant
        # text only — no tool_calls / tool_results from prior rounds).
        if history:
            for entry in history:
                # Gradio passes (user, assistant) tuples; be defensive
                # against malformed entries.
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                prev_user, prev_asst = entry[0], entry[1]
                if prev_user:
                    messages.append({"role": "user", "content": str(prev_user)})
                if prev_asst:
                    messages.append({"role": "assistant",
                                     "content": str(prev_asst)})
        messages.append({"role": "user", "content": user_content})

        tool_results: List[Dict[str, Any]] = []
        final_text = ""
        error: Optional[str] = None
        prompt_tokens = 0
        completion_tokens = 0

        try:
            client = self._ensure_client()
            for turn in range(self.max_turns):
                trace.llm_turns = turn + 1
                completion = client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=self._tool_schemas,
                    tool_choice="auto",
                )
                # Best-effort token accounting.
                usage = getattr(completion, "usage", None)
                if usage is not None:
                    prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens += getattr(usage, "completion_tokens", 0) or 0

                choice = completion.choices[0]
                msg = choice.message
                tool_calls = getattr(msg, "tool_calls", None) or []

                # Persist assistant turn into history (with tool_calls if any).
                assistant_entry: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                }
                if tool_calls:
                    assistant_entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_entry)

                if not tool_calls:
                    final_text = msg.content or ""
                    break

                # Dispatch every tool call this turn.
                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        llm_args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        llm_args = {"_raw_arguments_str": tc.function.arguments}

                    effective_args = dict(llm_args)
                    if "resolve_eta" in _tools.TOOL_REGISTRY.get(
                        name, ("", frozenset()))[1] and effective_args.get("eta") is None:
                        effective_args["eta"] = 0.0

                    t0 = time.monotonic()
                    result = _tools.dispatch(name, **llm_args)
                    latency_ms = int((time.monotonic() - t0) * 1000)

                    status = result.get("status", "ok") if isinstance(result, dict) else "non_dict"
                    err_msg = (result.get("message") if isinstance(result, dict)
                               and status == "error" else None)

                    event = TraceEvent(
                        timestamp=_utc_iso(),
                        tool=name,
                        llm_args=llm_args,
                        effective_args=effective_args,
                        status=status,
                        result_summary=summarize_result(name, result),
                        latency_ms=latency_ms,
                        error_message=err_msg,
                    )
                    trace.add_event(event)
                    tool_results.append({"tool": name, "args": llm_args,
                                          "result": result})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            else:
                # Loop exited via max_turns without a content-only reply.
                error = (f"Max turns ({self.max_turns}) reached without "
                         f"a final assistant response.")
                final_text = (messages[-1].get("content") or "") if messages else ""

        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            final_text = final_text or ""

        # Run-level metadata.
        trace.finished_at = _utc_iso()
        trace.total_latency_ms = int((time.monotonic() - start) * 1000)
        trace.prompt_tokens_total = prompt_tokens or None
        trace.completion_tokens_total = completion_tokens or None

        return AgentResponse(
            text=final_text,
            trace=trace,
            tool_results=tool_results,
            error=error,
        )
