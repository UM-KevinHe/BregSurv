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
from .helpers import compress_tool_result_for_llm
from .prompts import SYSTEM_PROMPT_V2, prompt_sha256
from .trace import AgentTrace, TraceEvent, summarize_result, _utc_iso
from .repro import write_repro_r


# -- Stage 4k: structural routing hint -----------------------------------------
#
# After auto-inspect we know whether the data is Cox-cohort shape (z + time +
# delta/status) or NCC matched-set shape (z + y + stratum). Qwen 7B otherwise
# routes by query keywords — "cross validation" → cv_coxkl regardless of
# whether the data has time/status. Empirically (NCC CV runaway 2026-05-29)
# this leads to cv_coxkl being called on $y+$stratum data and crashing R with
# "argument lengths differ", then Qwen consumes the entire max-tokens budget
# trying to "fix" it. The hint below appears AT THE END of the user message,
# making the routing constraint impossible to overlook.
def _detect_data_family_hint(inspect_result):
    """Return a one-line ROUTING HINT string, or '' if structure is ambiguous.

    Delegates family classification to :func:`tools.classify_data_family`
    (single source of truth, shared with the tool-subsetting logic so the
    hint and the exposed tool set can never disagree). Since Stage 4l also
    HIDES the wrong-family tools from the request, the hint no longer needs
    the "DO NOT call cohort tools" negative half — the wrong-family tools
    aren't callable. The hint now just confirms the regime so the LLM
    doesn't waste a turn second-guessing the data shape.
    """
    family = _tools.classify_data_family(inspect_result)
    if family == "ncc":
        return (
            "ROUTING HINT: the DATA STRUCTURE above shows $y + $stratum "
            "fields and no $time/$status/$delta — this is NCC (nested "
            "case-control / matched-set) data. Use an NCC-family tool "
            "(fit_ncc* / cv_ncc*); only those are available to you."
        )
    if family == "cox":
        return (
            "ROUTING HINT: the DATA STRUCTURE above shows $time + "
            "$status/$delta and no $y/$stratum — this is Cox cohort data. "
            "Use a cohort-family tool (fit_cox* / cv_cox* / fit_coxkl* / "
            "cv_coxkl*); only those are available to you."
        )
    return ""


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
        temperature: float = 0.0,
        max_tokens: int = 2048,
        scaffold: Optional[Dict[str, bool]] = None,
    ) -> None:
        self.model_endpoint = model_endpoint
        self.model_name = model_name
        self.api_key = api_key
        self.system_prompt = system_prompt or SYSTEM_PROMPT_V2
        self.deployment_mode = deployment_mode
        self.max_turns = max_turns
        self._client = client
        # Evaluation hooks (backward-compatible: omitting all three leaves
        # the deployed behaviour unchanged). temperature/max_tokens let the
        # pass^k harness sample at t>0; scaffold switches layers off (keys:
        # all, subset_tools, dispatch_guard; each defaults to True = on).
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._scaffold = dict(scaffold or {})
        # Cache schemas once per instance.
        self._tool_schemas = _tools.load_schemas()

    def _scaffold_on(self, key):
        # True if scaffolding layer `key` is enabled (default: on).
        return self._scaffold.get(key, True)

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
        family_override: Optional[str] = None,
        method_override: Optional[str] = None,
        bound_context: Optional[str] = None,
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

        # Stage 4h: Scaffolded context injection.
        #
        # When data_path is given, we pre-dispatch `inspect_data` ourselves
        # and embed the resulting structure verbatim into the user message.
        # Rationale: Qwen 2.5-7B does NOT reliably obey a soft prompt rule
        # like "MUST call inspect_data before fit_*" — even after Stage 4g
        # tightened that rule. It will skip inspect_data and guess ASCII-but-
        # wrong field names ("z" instead of "ExampleData_lowdim$train$z"),
        # then fail at the R subprocess on a shape/name mismatch.
        #
        # By injecting the structure upfront, we make verification an
        # ARCHITECTURAL GUARANTEE rather than a Qwen-compliance question.
        # Trace and repro still record the auto-inspect call so the
        # audit chain stays intact.
        # Stage 4l: context-aware tool subsetting. Default to the full
        # catalogue; narrowed below once we have an inspect result.
        active_schemas = self._tool_schemas

        user_content = user_text
        if data_path is not None and not self._scaffold_on("all"):
            # Ablation 'raw' cell: no auto-inspect, no DATA STRUCTURE / routing
            # hint injection, no tool subsetting. The model sees only the path.
            if not bound_context:
                user_content += f"\n\n[The user's data file is at: {data_path}]"
        elif data_path is not None:
            auto_inspect = _tools.dispatch("inspect_data",
                                           data_path=data_path)
            # Record the auto-inspect call in the trace for audit symmetry
            # with any LLM-initiated inspect_data call. The
            # _auto_prepend=True flag inside effective_args lets reviewers
            # distinguish architectural pre-call from LLM-issued call.
            trace.events.append(TraceEvent(
                timestamp=_utc_iso(),
                tool="inspect_data",
                llm_args={},
                effective_args={"data_path": data_path,
                                "_auto_prepend": True},
                status=auto_inspect.get("status", "ok"),
                result_summary=summarize_result("inspect_data",
                                               auto_inspect),
                latency_ms=0,
            ))
            structure_block = json.dumps(auto_inspect, indent=2,
                                          ensure_ascii=False)
            # Stage 4k: structural routing hint. The auto-inspect tells us
            # which tool family the data fits BEFORE the LLM sees the query;
            # without this hint Qwen 7B routes by query keywords ("cross
            # validation" → Cox) and ignores the data structure, calling
            # cv_coxkl on NCC data and crashing R with "argument lengths
            # differ". Prepending a one-line ROUTING HINT works around the
            # query-wording bias.
            routing_hint = _detect_data_family_hint(auto_inspect)

            # Stage 4l: narrow the exposed tool schemas to the admissible
            # family (+ dimensionality when unambiguous). Cuts the ~18K
            # all-33-tools payload to ~5-12K and shrinks the routing
            # decision space. Recorded in the trace for audit.
            if self._scaffold_on("subset_tools"):
                active_schemas, exposed_meta = _tools.select_tool_schemas(
                    self._tool_schemas, auto_inspect,
                    family_override=family_override,
                    method_override=method_override)
                trace.tools_exposed = exposed_meta

            # When the UI supplies bound_context (demo path), it already
            # lists the exact object/field/beta paths — the raw DATA
            # STRUCTURE block is then redundant AND counterproductive: for
            # high-dim data it balloons to thousands of tokens (e.g. 50
            # Z-column names) and its visible `$test` split tempts the
            # model into picking an individual-data tool. So inject the
            # structure block + routing hint ONLY on the upload path,
            # where the model must build args itself.
            if not bound_context:
                user_content += (
                    f"\n\n[The user's data file is at: {data_path}]"
                    f"\n\n[DATA STRUCTURE — already inspected for you. Use "
                    f"the object name and field names below verbatim in any "
                    f"*_expr arguments. Do NOT call inspect_data again. Do "
                    f"NOT invent or translate field names — only use what is "
                    f"shown here, in ASCII, exactly as written:\n"
                    f"{structure_block}\n]"
                )
                if routing_hint:
                    user_content += f"\n\n[{routing_hint}]"

        # Stage 4m: UI-bound facts. When the deployment UI resolved the
        # dataset / external-beta object / eta grid from explicit
        # selections, it passes them here as authoritative values the LLM
        # must use verbatim (fixes the bare-`beta_external` path bug and
        # the hand-written eta grid). Injected for BOTH the data-file and
        # no-file paths.
        if bound_context:
            user_content += f"\n\n[{bound_context}]"

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
                    tools=active_schemas,
                    tool_choice="auto",
                    # Deterministic greedy decoding. The deployed agent
                    # previously left temperature unset → vLLM's non-zero
                    # default → nondeterministic routing and intermittent
                    # "describe instead of call" turns (observed
                    # 2026-05-30, Cox highdim fit returned prose with no
                    # tool call). Deterministic decoding also makes a run
                    # reproducible from its trace.
                    temperature=self.temperature,
                    # Stage 4k: cap per-turn generation. Without this,
                    # vLLM fills the entire remaining context window —
                    # 2026-05-29 trace had max_tokens=8274 (~4 min at
                    # 38 tok/s) after Qwen mis-routed an NCC query and
                    # tried to "fix" the R error by rambling. 2048 is
                    # plenty for one tool call's arguments + brief
                    # reasoning text + tool calls list; the loop can
                    # take multiple turns if Qwen needs more thinking.
                    max_tokens=self.max_tokens,
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

                # Names exposed to the LLM this run — used to hard-reject
                # hallucinated / non-exposed tool calls.
                active_names = {s["function"]["name"] for s in active_schemas}

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
                    # Stage 4m: hard-guard. Tool subsetting only controls
                    # what the LLM is SHOWN; dispatch() itself still
                    # accepts any of the 33 registry tools. A 7B model can
                    # hallucinate a non-exposed tool name (observed
                    # 2026-05-30: cv_coxkl emitted on NCC data despite an
                    # NCC-only subset, then run by dispatch and crashing
                    # R). Refuse it here and tell the model what IS
                    # available, forcing a retry within the family.
                    if self._scaffold_on("dispatch_guard") and name not in active_names:
                        result = {
                            "status": "error",
                            "class": "ToolNotAvailable",
                            "where": "bregsurv_agent.agent",
                            "message": (
                                f"Tool '{name}' is not available for this "
                                f"dataset. Choose one of the available "
                                f"tools instead: {sorted(active_names)}."
                            ),
                        }
                    else:
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

                    # Stage 4i-B: compress the tool result that the LLM
                    # sees on subsequent iterations. The FULL result is
                    # already in `tool_results` (returned to UI) and in
                    # `trace.events` (via summarize_result above and the
                    # write_repro_r call later) — only the LLM-facing copy
                    # is shrunk. Drops per-iteration cost from ~5K to
                    # ~200 tokens for typical fit_* / cv_* results.
                    llm_facing = compress_tool_result_for_llm(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(llm_facing,
                                              ensure_ascii=False),
                    })
            else:
                # Loop exited via max_turns without a content-only reply.
                error = (f"Max turns ({self.max_turns}) reached without "
                         f"a final assistant response.")
                final_text = (messages[-1].get("content") or "") if messages else ""

        except Exception as e:
            # Stage 4i-A: BadRequestError from a context-length overflow
            # gets a user-readable message instead of a raw traceback.
            # The trace.json and repro.R from successful tool calls in
            # this turn ARE still valid and downloadable — the only
            # thing that failed is the LLM's final response synthesis.
            err_text = str(e)
            err_class = type(e).__name__
            if ("BadRequest" in err_class
                    and "maximum context" in err_text.lower()):
                error = (
                    "This conversation has grown past the model's "
                    "context window (32K tokens). Click 'Clear' to "
                    "start a fresh chat. Your trace.json and repro.R "
                    "downloaded from earlier turns remain valid."
                )
            else:
                error = f"{err_class}: {e}"
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
