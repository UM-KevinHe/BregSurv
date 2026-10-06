"""C5: the two places the language model is allowed to act, and how.

Both are a SINGLE constrained generation with NO `tools` field. The agent sends no tool
schemas at all, because under V3 the model does not pick an estimator, so it has
no reason to see them: 32 schemas, 68,105 compact characters, roughly 19.5K
tokens, gone from every request.

  boundary 1  extract the roles the analyst stated in prose. The model proposes;
              `declaration.verify` echoes the consequences back as numbers the
              analyst can falsify before anything is fitted. Used only when the
              analyst wrote their roles out in words -- answering the numbered
              question instead is parsed deterministically and never reaches here.
  boundary 2  write the report's connective prose. It emits NAMED REFERENCES and
              no digits; `report_v3.resolve` substitutes the values at render
              time from a closed, typed set.
  explain     (M4, 2026-09-11) answer one question about a report that exists,
              under exactly boundary 2's rules: named references, no digits,
              the closed set. A draft that breaks them is dropped, not fixed.

The intent call (M1) lives in `intent.py` and uses the same `_chat`.

THE `reasoning` FIELD COMES FIRST in every schema, before the decision fields.
In the study behind the "structured output hurts reasoning" result, 100% of the
failures had emitted the answer key before the reason key. Putting it first is
the single logged "reason-then-commit" step the design permits. It is a design
bet, not a measured effect: on the 500-item run of 2026-08-20 the field held a
placeholder or a bare column name on ~81% of calls, because its purpose lived
only in a JSON-Schema `description` the server never shows the model. The purpose
is now stated in the system prompt; whether the step executes is measured at the
final evaluation, and the field is deleted if it still does not.

Every call is recorded (`call_log`): model, endpoint, prompt/completion tokens,
finish_reason, seconds. The prompt-token count of a single-turn call IS its peak
context, which is what the 32K window actually constrains. A response that is
not valid JSON raises `ValueError` carrying finish_reason, completion_tokens and
the raw text -- 48 of 500 calls on 2026-08-20 failed this way and were
undiagnosable because the text was discarded.

This module is OPTIONAL. `pipeline.run` without `write_prose` produces a complete
report; the prose is connective tissue, not content. Nothing here can change a
number, a column, or an estimator.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import policy

# ---------------------------------------------------------------- the schemas
ROLE_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    # `reasoning` first, deliberately. See the module docstring. Its purpose is
    # stated in _EXTRACT_SYSTEM, not here: a `description` reaches the grammar
    # compiler, never the model.
    "properties": {
        "reasoning": {"type": "string"},
        "time_column": {"type": ["string", "null"]},
        # the phrase of the request the column was read from, verbatim. A
        # column the request does not NAME may still be filled from a phrase
        # that describes it (decision (b) revised 2026-09-11): the harness
        # accepts it only if the phrase is in the message and the column is
        # eligible for the role, and discloses it as `described`.
        "time_evidence": {"type": ["string", "null"]},
        "event_column": {"type": ["string", "null"]},
        "event_evidence": {"type": ["string", "null"]},
        "event_value": {"type": ["string", "null"]},
        "event_value_evidence": {"type": ["string", "null"]},
        # the column the analyst names as the stratum or the matched-set
        # identifier (2026-09-30: without this field a request that says
        # "stratify by stratum" or "set_id identifies each matched set" could
        # not declare it, and a stratified cohort ran unstratified). Quoted
        # only: a name the request does not write is dropped by the backing
        # check, never described. The design still follows from what is
        # declared -- a stratum with a follow-up time is a stratified cohort,
        # a matched set without one is a nested case-control sample.
        "stratum_column": {"type": ["string", "null"]},
        # maxItems: the widest corpus profile needs 42-43 names; a cap of 32
        # would force a silent drop, no cap lets a degenerate generation run
        # until max_tokens and come back as a parse error.
        "covariate_columns": {"type": ["array", "null"],
                              "items": {"type": "string"},
                              "maxItems": 64},
        # `stated_explicitly` is gone: the model asserted "read
        # from the request" on 53% of the items where it had guessed. Whether a
        # role was quoted is now decided by the harness, not declared by the model.
    },
    "required": ["reasoning", "time_column", "time_evidence", "event_column",
                 "event_evidence", "event_value", "event_value_evidence",
                 "stratum_column", "covariate_columns"],
}

REPORT_PROSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "data": {"type": "string"},
        "linkage": {"type": "string"},
        "candidates": {"type": "string"},
        "comparison": {"type": "string"},
        "selected": {"type": "string"},
    },
    "required": ["reasoning", "data", "linkage", "candidates", "comparison",
                 "selected"],
}

# Component 2: policies/role_extraction.md -- ghost-column rule, null scoped to the four roles, `reasoning` purpose, all IN the prompt.
_EXTRACT_SYSTEM = policy.load("role_extraction")

# Component 2: policies/report_prose.md.
_PROSE_SYSTEM = policy.load("report_prose")


EXPLAIN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["reasoning", "answer"],
}

# Component 2: policies/explain.md.
_EXPLAIN_SYSTEM = policy.load("explain")


# Every call, in order. `call_log` reads it; app.py copies it into the run's
# provenance. A single-turn call's prompt_tokens is its peak context.
CALLS: List[Dict[str, Any]] = []


def call_log(clear: bool = False) -> List[Dict[str, Any]]:
    out = list(CALLS)
    if clear:
        CALLS.clear()
    return out


# ------------------------------------------------------------ decoding policy
# Temperature is a property of the ACT, not of the agent (
# temperature 0 everywhere turns the model into a pipeline). Quoting acts --
# a name is in the message or it is not -- gain nothing from sampling and are
# decoded greedily; writing acts are sampled. Reproducibility of the ANALYSIS
# never rested on the model being deterministic (master memory ); for an
# EVALUATION that wants repeatable model output, set BREGSURV_SEED.
#
# BREGSURV_THINKING V4: thinking is a property of the act too.
# unset or `auto` -> the acts in THINKING_ACTS think, the
# others do not (chat_template_kwargs.enable_thinking is
# sent on every call; a template without the switch
# ignores it); `on` / `off` -> every act; a comma list of
# act names -> exactly those acts. A thinking act follows
# the Qwen3 guidance, never greedy (temp 0.6, top_p 0.95);
# the hidden reasoning is recorded in the call record as
# `thinking_text`, never shown to the analyst
# BREGSURV_TEMPERATURE a global override, e.g. 0 to reproduce the 2026-08 runs
# BREGSURV_SEED a per-request seed for repeatable sampling
QUOTING_ACTS = ("intent", "role_extraction", "external_roles", "published_model",
                "plan_steps", "split_request")
WRITING_ACTS = ("report_prose", "explain", "ask", "refusal", "chat")
# V4: the acts that plan the analysis think before they answer; reading and
# writing acts do not (the 2026-09 runs: thinking did not make the quoting acts
# more accurate and made them several times slower)
THINKING_ACTS = ("analysis_plan", "next_step")


# tokens added to an act's max_tokens when the model thinks first, so the
# visible JSON keeps its own budget. Override with BREGSURV_THINKING_ALLOWANCE.
# 2000 in V3; the 2026-10-02 rubric round found 34 calls whose thinking (10-14k
# characters, unfinished) used the whole budget, so V4 starts at 8000.
THINKING_ALLOWANCE = int(os.environ.get("BREGSURV_THINKING_ALLOWANCE", "8000") or 0)


def thinks(name: str) -> bool:
    """Whether the act `name` thinks before it answers, under BREGSURV_THINKING."""
    import os
    env = os.environ.get("BREGSURV_THINKING", "").strip().lower()
    if env in ("on", "1", "true", "yes"):
        return True
    if env in ("off", "0", "false", "no"):
        return False
    if env in ("", "auto"):
        return name in THINKING_ACTS
    return name in {a.strip() for a in env.split(",") if a.strip()}


def decoding_for(name: str) -> Dict[str, Any]:
    import os
    thinking = thinks(name)
    if thinking:
        d: Dict[str, Any] = {"temperature": 0.6, "top_p": 0.95}
    elif name in WRITING_ACTS:
        d = {"temperature": 0.7, "top_p": 0.8}
    else:
        d = {"temperature": 0.0, "top_p": 1.0}
    if os.environ.get("BREGSURV_TEMPERATURE", "").strip():
        d["temperature"] = float(os.environ["BREGSURV_TEMPERATURE"])
    if os.environ.get("BREGSURV_SEED", "").strip():
        d["seed"] = int(os.environ["BREGSURV_SEED"])
    d["thinking"] = thinking
    return d


_UNPARSED = object()


def _last_decode_error(text: str) -> Exception:
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return exc
    return ValueError("not valid JSON")


def _chat(client, model: str, system: str, user: str, schema: Dict[str, Any],
          name: str, temperature: Optional[float] = None,
          max_tokens: int = 1200, extra_record: Optional[Dict[str, Any]] = None,
          on_text=None) -> Dict[str, Any]:
    """One constrained generation. No tools, ever. `extra_record` is merged
    into the call record (e.g. which few-shot examples were shown). With
    `on_text`, the answer is streamed and the callback receives the text so
    far after every chunk; the record and the checks are the same."""
    import time as _time
    t0 = _time.time()
    dec = decoding_for(name)
    if temperature is not None:
        dec["temperature"] = temperature
    kw: Dict[str, Any] = {"temperature": dec["temperature"], "top_p": dec["top_p"]}
    if "seed" in dec:
        kw["seed"] = dec["seed"]
    allowance = 0
    if "thinking" in dec:
        # Qwen3: the chat template's switch; the server's reasoning parser
        # then separates the hidden reasoning from the constrained content
        kw["extra_body"] = {"chat_template_kwargs": {"enable_thinking": dec["thinking"]}}
        if dec["thinking"]:
            # the hidden reasoning is generated text and counts against
            # max_tokens. The 2026-09-11 thinking-on run shared the per-act
            # budget (300-900) between the reasoning and the JSON, so a long
            # thought left no room for the answer: empty content, typed as
            # "no intent" / "no coefficient table". The thinking arm measured
            # the cap, not the reasoning. Thinking gets its own allowance.
            allowance = THINKING_ALLOWANCE
            max_tokens = max_tokens + allowance
    from . import ablation
    unconstrained = ablation.on("no_constrained")
    if unconstrained:
        # ablation cell: the schema is described, not enforced
        user = (user + "\n\nAnswer with one JSON object and nothing else, conforming to "
                "this JSON schema:\n" + json.dumps(schema))
        fmt: Dict[str, Any] = {}
    else:
        fmt = {"response_format": {"type": "json_schema",
                                   "json_schema": {"name": name, "schema": schema,
                                                   "strict": True}}}
    if on_text is not None:
        return _chat_streamed(client, model, system, user, name, dec, kw, fmt, max_tokens,
                              allowance, unconstrained, extra_record, on_text, t0)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        # the whole point of C5: NO tools field at all. Measured on
        # vLLM 0.27.1 -- `tools=[]` is rejected with 400 "`tools` must not be
        # an empty array. Either provide at least one tool or omit the field
        # entirely." Omitting it is what "the agent sends no schemas" means.
        max_tokens=max_tokens,
        **fmt,
        **kw,
    )
    choice = completion.choices[0]
    text = choice.message.content or "{}"
    if unconstrained:
        # free text: take the outermost braces, drop a code fence if any
        i, j = text.find("{"), text.rfind("}")
        text = text[i:j + 1] if 0 <= i < j else text
    usage = getattr(completion, "usage", None)
    rec = {"name": name, "model": model,
           "base_url": str(getattr(client, "base_url", "")),
           "temperature": dec["temperature"], "top_p": dec["top_p"],
           "seed": dec.get("seed"), "thinking": dec.get("thinking"),
           "max_tokens": max_tokens, "thinking_allowance": allowance,
           "prompt_tokens": getattr(usage, "prompt_tokens", None),
           "completion_tokens": getattr(usage, "completion_tokens", None),
           "finish_reason": getattr(choice, "finish_reason", None),
           "seconds": round(_time.time() - t0, 2)}
    if extra_record:
        rec.update(extra_record)
    # the hidden reasoning of a thinking model (vLLM's reasoning parser puts
    # it in a field the openai client does not model -- `reasoning` on vLLM
    # 0.27, `reasoning_content` on older builds -- so it sits in model_extra):
    # recorded, never shown, never acted on. (job
    # 60976281): under response_format the model thinks first and the
    # grammar applies to the content after it.
    think = getattr(choice.message, "reasoning_content", None)
    if not think:
        extra = getattr(choice.message, "model_extra", None) or {}
        think = extra.get("reasoning") or extra.get("reasoning_content")
    if think:
        rec["thinking_text"] = str(think)[:6000]
        rec["thinking_chars"] = len(str(think))
    if not (choice.message.content or "").strip() and rec["finish_reason"] == "length":
        # V4: a model that thinks until its budget runs out writes
        # no answer at all. V3 read the empty content as "{}" -- an answer with
        # every field empty -- and recorded no error (34 calls in the 2026-10-02
        # rubric round). An unanswered call is a failure and is said to be one.
        rec["error"] = (f"no answer: the model used its whole budget of {max_tokens} tokens"
                        + (f" thinking ({rec.get('thinking_chars', 0)} characters)" if think else "")
                        + " before writing one")
        rec["raw_text"] = ""
        CALLS.append(rec)
        raise ValueError(f"{name}: {rec['error']} (finish_reason=length)")
    try:
        out = json.loads(text)
    except json.JSONDecodeError as exc:
        # one repair, recorded: an escaped single quote (\') is not a JSON
        # escape, and Qwen2.5 writes it inside its reasoning strings (M5 on
        # the ablation fixture F05, 2026-09-13: seven files refused for it)
        repaired = re.sub(r"\\'", "'", text)
        try:
            out = json.loads(repaired)
            rec["repaired"] = "escaped single quote"
            text = repaired
        except json.JSONDecodeError:
            out = _UNPARSED
    if out is _UNPARSED:
        exc = _last_decode_error(text)
        rec["error"] = f"invalid JSON: {exc}"
        rec["raw_text"] = text[:4000]
        CALLS.append(rec)
        raise ValueError(
            f"{name}: the model's output was not valid JSON "
            f"(finish_reason={rec['finish_reason']}, "
            f"completion_tokens={rec['completion_tokens']}, "
            f"max_tokens={max_tokens}): {exc}. Raw text: {text[:300]!r}") from exc
    # M3: the raw text and the first key are kept for every call, so the
    # claim "the model reasons before it commits" rests on what it emitted,
    # not on the schema it was given. The grammar fixes property order; this
    # is the record that lets a test say so.
    rec["raw_text"] = text[:4000]
    rec["first_key"] = next(iter(out), None) if isinstance(out, dict) else None
    CALLS.append(rec)
    return out


def describe_model(client, model: str) -> Dict[str, Any]:
    """What produced the words. Provenance for trace.json (M8).

    Asks the server what it is serving. vLLM's /v1/models carries `root` (the
    weights path) and `max_model_len` beyond the OpenAI fields; both are taken
    when present. If `root` is a readable directory on this machine, a cheap
    fingerprint of the weights is recorded: sha256 over the sorted
    (file name, size) list of the safetensors plus the config.json text. It
    identifies the checkpoint without reading gigabytes; it is not a hash of
    the tensors.
    """
    import hashlib
    from pathlib import Path
    out: Dict[str, Any] = {"served_model": model,
                           "base_url": str(getattr(client, "base_url", "")),
                           "decoding": "response_format json_schema strict "
                                       "(vLLM xgrammar, compact JSON); tools omitted",
                           "decoding_policy": {n: decoding_for(n) for n in
                                               QUOTING_ACTS + WRITING_ACTS}}
    try:
        for m in client.models.list().data:
            d = m.model_dump() if hasattr(m, "model_dump") else dict(m)
            if d.get("id") == model:
                out["root"] = d.get("root")
                out["max_model_len"] = d.get("max_model_len")
                out["owned_by"] = d.get("owned_by")
                break
    except Exception as exc:                 # provenance must never break a run
        out["models_endpoint_error"] = f"{type(exc).__name__}: {exc}"[:200]
    root = out.get("root")
    if root and Path(str(root)).is_dir():
        h = hashlib.sha256()
        for f in sorted(Path(str(root)).glob("*.safetensors")):
            h.update(f"{f.name}:{f.stat().st_size}\n".encode())
        cfg = Path(str(root)) / "config.json"
        if cfg.exists():
            h.update(cfg.read_bytes())
        out["weights_fingerprint"] = "sha256:" + h.hexdigest()[:16]
    return out


# ------------------------------------------------------------- boundary 1
def extract_roles(client, model: str, request: str,
                  profile: Dict[str, Any],
                  examples: Optional[List[Dict[str, Any]]] = None,
                  few_shot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Propose a role extraction from the analyst's own words.

    The result is a PROPOSAL. It is never acted on directly: the caller builds a
    Declaration from it and `verify` shows the analyst what it means for their
    data -- how many events, what share of the cohort -- before anything runs.

    `examples`: retrieved bank items placed before the request as
    worked examples; `few_shot` is their record for the call log. Retrieval
    is the caller's (`fewshot.retrieve`), so this function stays one call.
    """
    from . import fewshot as _fs
    names = [c["name"] for c in profile.get("columns", [])]
    block = _fs.render(examples) if examples else ""
    user = (f"Columns in the file:\n{', '.join(names)}\n\n"
            + (block + "\n" if block else "")
            + f"The analyst wrote:\n{request}")
    return _chat(client, model, _EXTRACT_SYSTEM, user, ROLE_EXTRACTION_SCHEMA,
                 "role_extraction", extra_record=({"few_shot": few_shot} if few_shot else None))


def examples_for(request: str, profile: Dict[str, Any],
                 exclude_template: Optional[str] = None
                 ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """The retrieval step for `extract_roles`, or (None, None) when few-shot
    is off or the bank is unavailable. Never raises: an example is a
    convenience, and a missing bank must not stop an analysis."""
    from . import fewshot as _fs
    if not _fs.enabled():
        return None, None
    try:
        b = _fs.bank()
        k = _fs.k_from_env()
        cols = [c["name"] for c in profile.get("columns", [])]
        ex = b.retrieve(request, cols, k=k, exclude_template=exclude_template)
        return ex, _fs.record(ex, k, b, exclude_template)
    except Exception as exc:
        return None, {"error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------- boundary 2
def write_prose(client, model: str, max_tokens: int = 900):
    """Return a `write_prose` callable for :func:`pipeline.run`.

    Section by section would lower peak context further; at the sizes this
    produces (about 900 tokens out, a reference list under 300) one call is
    comfortably inside the window and simpler to audit.
    """
    def _fn(ctx: Dict[str, Any]) -> Dict[str, str]:
        from . import report_v3
        refs = ctx["references"]
        res = ctx["result"]
        rows = [f"{c['label']}: {c['status']}" for c in res["candidates"]]
        # 2026-10-01: what each reference IS and the facts of this run, in words
        # (report_v3.prose_facts); before, the model saw names alone and guessed
        # V4: two worked examples generated by rule for the nearest combination of facts
        from . import prose_examples
        ex_prefix, ex_rec = prose_examples.for_run(res, refs)
        user = ex_prefix + (
            "Reference names you may use, and nothing else, with what each one is:\n"
            + "\n".join("  " + g for g in report_v3.reference_glossary(refs))
            + "\n\nFacts of this analysis:\n"
            + "\n".join("  " + s for s in report_v3.prose_facts(res, refs))
            + "\n\nWhat was done: the admissible candidate set was derived from "
              "two facts about the data, every member was fitted on one "
              "cross-validation partition, and the lowest loss was selected.\n"
              "Candidates:\n" + "\n".join("  " + r for r in rows)
            + "\n\nWrite one short paragraph for each of: data, linkage, "
              "candidates, comparison, selected."
        )
        try:
            out = _chat(client, model, _PROSE_SYSTEM, user, REPORT_PROSE_SCHEMA,
                        "report_prose", max_tokens=max_tokens,
                        extra_record=({"prose_examples": ex_rec} if ex_rec else None))
        except ValueError as exc:
            # A draft that is not valid JSON (a small model that ran out of
            # its 900 tokens mid-string: Qwen2.5 P076, Qwen3-off P044/P047/P078
            # of the 100-prompt run) is NO PROSE, not a failed analysis. The
            # fit is verified and finished by the time this runs; the report
            # renders from the numbers alone and says the draft was dropped.
            # The call record still travels, so the tokens are accounted for.
            kept = {"_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            if CALLS:
                kept["_call"] = CALLS[-1]
            return kept
        # The reasoning step is LOGGED, not discarded. It is the only record of
        # why the model wrote what it wrote, and if a draft is ever rejected it
        # is the only place to look. It is kept out of the report itself by
        # being returned under a key the renderer does not use.
        reasoning = out.pop("reasoning", None)
        kept = {k: v for k, v in out.items() if isinstance(v, str) and v.strip()}
        if reasoning:
            kept["_reasoning"] = reasoning
        # the call record travels with the prose so pipeline.run can put it in
        # the provenance without importing this optional module
        if CALLS:
            kept["_call"] = CALLS[-1]
        return kept

    return _fn


# ---------------------------------------------------------------- M4: explain
def explain(client, model: str, question: str, ctx: Dict[str, Any],
            max_tokens: int = 500) -> Dict[str, Any]:
    """Answer one question about a finished report. Boundary 2's rules apply.

    `ctx` carries `references` (the closed set from `report_v3.build_references`),
    `result` (the candidates dict) and optionally `declaration`. The model sees
    reference NAMES, candidate labels and statuses, and the declared roles --
    never a value. The draft is checked exactly as report prose is: a digit the
    model wrote, or a name outside the set, and the answer is dropped and the
    caller told why. Returns `{"answer": str | None, "dropped": str | None,
    "_reasoning": str, "_call": record}`.
    """
    from . import report_v3
    refs = ctx["references"]
    res = ctx["result"]
    rows = [f"  {c['label']}: {c['status']}" for c in res["candidates"]]
    decl = ctx.get("declaration")
    roles = ""
    if decl is not None:
        src = getattr(decl, "sources", None) or {}
        parts = [f"follow-up time = {decl.time_col} ({src.get('time', 'stated')})",
                 f"event = {decl.event_col} at value {decl.event_value} "
                 f"({src.get('event', 'stated')})",
                 f"predictors = {', '.join(decl.covariates)} "
                 f"({src.get('covariates', 'stated')})"]
        roles = "\nHow the roles were settled:\n  " + "\n  ".join(parts) + "\n"
    if ctx.get("plain_facts"):
        # the chat page: the facts are given in plain words, decided by the
        # harness; the model only puts them into an answer to the question
        user = ("Reference names you may use, and nothing else:\n"
                "  [selected_label]  the approach that was kept, a phrase such as \"combining your data with the external model\"; write \"the approach of [selected_label]\" or \"the chosen approach\"\n\n"
                "What the analysis found, in plain words:\n"
                + "\n".join("  - " + f for f in ctx["plain_facts"])
                + "\n\nThe clinician asks:\n" + question.strip())
    else:
      user = (
        "Reference names you may use, and nothing else, with what each one is:\n"
        + "\n".join("  " + g for g in report_v3.reference_glossary(refs))
        + "\n\nFacts of this analysis:\n"
        + "\n".join("  " + s for s in report_v3.prose_facts(res, refs))
        + "\n\nWhat the report contains: the study design ([design]) and the "
          "form of the external information ([external_form]) fixed the "
          "candidate set; every candidate was fitted on one cross-validation "
          "partition of [nfolds] folds; the lowest held-out loss was selected "
          "([selected_label], loss [loss_best]"
        + ("; your data alone [loss_internal]" if "loss_internal" in refs else "")
        + ("; the external model unchanged [loss_external]" if "loss_external" in refs else "")
        + ").\n"
          "Candidates:\n" + "\n".join(rows) + "\n" + roles
        + "\nThe clinician asks:\n" + question.strip()
    )
    out = _chat(client, model, _EXPLAIN_SYSTEM, user, EXPLAIN_SCHEMA, "explain",
                max_tokens=max_tokens)
    rec = CALLS[-1] if CALLS else {}
    draft = (out.get("answer") or "").strip()
    result: Dict[str, Any] = {"answer": None, "dropped": None,
                              "_reasoning": out.get("reasoning"), "_call": rec}
    if not draft:
        result["dropped"] = "empty"
        return result
    leaked = report_v3.check_no_digits(draft)
    if leaked:
        # the value stays in the call record (raw_text); it is NOT repeated
        # here, because `dropped` is shown to the analyst and a model-written
        # number must not reach them by the back door either
        result["dropped"] = "the draft wrote a number itself"
        rec["leaked_digits"] = leaked[:5]
        return result
    try:
        result["answer"] = report_v3.resolve(draft, refs)
    except report_v3.UnknownReference as exc:
        result["dropped"] = str(exc)
    return result


def schema_token_cost() -> Dict[str, int]:
    """What C5 removed, measured rather than asserted."""
    from pathlib import Path
    p = Path(__file__).resolve().parent / "schemas.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    compact = len(json.dumps(d, separators=(",", ":"), ensure_ascii=False))
    return {"tools": len(d), "chars": compact,
            "approx_tokens": round(compact / 3.5),
            "sent_by_v3": 0}


# ------------------------------------------------------------- the question's wording
ASK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"reasoning": {"type": "string"}, "question": {"type": "string"}},
    "required": ["reasoning", "question"],
}

_OPEN_LABELS = {"0": "the study design", "1": "the follow-up time column",
                "2": "the event column", "3": "which value of the event column means the event",
                "4": "the covariates", "5": "the external cohort's table",
                "6": "whether every covariate was known at the start of follow-up",
                "7": "whether follow-up is recorded in discrete intervals, and their width and number"}


def word_question(client, model: str, message: str, profile: Dict[str, Any],
                  settled: Dict[str, str], sources: Dict[str, str],
                  open_items: List[str], max_tokens: int = 300) -> Dict[str, Any]:
    """The model words the lead-in to the harness's numbered question.

    One constrained call; the harness's list follows it unchanged and parses
    the reply. Verified before use: every column-like name in the sentences
    must be a column of the file, and the text must carry no digit. A draft
    that fails is DROPPED (the plain list is shown), never repaired.
    """
    import re as _re
    names = [c["name"] for c in profile.get("columns", [])]
    have = "; ".join(f"{k} = {v} ({sources.get(k, 'stated')})"
                     for k, v in settled.items() if v) or "nothing yet"
    user = ("Columns in the file:\n" + ", ".join(names)
            + "\n\nSettled so far:\n" + have
            + "\n\nStill open, in the order the list below will use:\n"
            + "\n".join(f"  {k}) {_OPEN_LABELS.get(k, k)}" for k in open_items)
            + "\n\nThe analyst wrote:\n" + (message or "").strip())
    # a multi-step turn reaches the question with no message of its own (the
    # harness's "So far" step): the lead-in is then worded from the settled
    # state alone. Until 2026-09-14 this raised on None and the action log
    # recorded the AttributeError as `dropped` on 11 of 98 synthetic requests.
    out = _chat(client, model, policy.load("ask"), user, ASK_SCHEMA, "ask",
                max_tokens=max_tokens)
    rec = CALLS[-1] if CALLS else {}
    q = (out.get("question") or "").strip()
    result: Dict[str, Any] = {"question": None, "dropped": None,
                              "_reasoning": out.get("reasoning"), "_call": rec}
    why = prose_problem(q, names)
    if why:
        result["dropped"] = why
        return result
    result["question"] = q
    return result


CHAT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"reasoning": {"type": "string", "maxLength": 600},
                   "reply": {"type": "string", "maxLength": 1500}},
    "required": ["reasoning", "reply"],
}

# a number next to one of these words in a conversational reply is a number about an analysis, which
# the conversation never has (the report holds the numbers)
_RESULT_NUMBER = re.compile(
    r"(c-?index|concordance|loss|brier|ibs|auc|hazard ratio|coefficient|eta|lambda|p-?value)"
    r"[^.\n]{0,25}\d|\d[^.\n]{0,10}(c-?index|hazard ratio)", re.I)


class _Msg:
    def __init__(self, content, reasoning):
        self.content, self.reasoning_content, self.model_extra = content, reasoning, {}


class _Choice:
    def __init__(self, content, reasoning, finish):
        self.message, self.finish_reason = _Msg(content, reasoning), finish


class _Completion:
    def __init__(self, content, reasoning, finish, usage):
        self.choices, self.usage = [_Choice(content, reasoning, finish)], usage


class _Fake:
    """Hands an already-collected streamed answer to the ordinary path of `_chat`."""
    def __init__(self, completion, base_url):
        self.base_url = base_url
        self.chat = self
        self.completions = self
        self._c = completion

    def create(self, **_):
        return self._c


def _chat_streamed(client, model, system, user, name, dec, kw, fmt, max_tokens, allowance,
                   unconstrained, extra_record, on_text, t0):
    """The streamed form of one call: the chunks are collected, the callback sees the text so far,
    and the collected answer then goes through exactly the record and checks of `_chat`."""
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=max_tokens, stream=True, stream_options={"include_usage": True},
        **fmt, **kw)
    text, think, finish, usage = [], [], None, None
    if getattr(stream, "choices", None) is not None:
        # a client that does not stream (a test double) answered in one piece
        stream = [type("C", (), {"usage": getattr(stream, "usage", None),
                                  "choices": [type("D", (), {"delta": stream.choices[0].message,
                                                             "finish_reason": stream.choices[0].finish_reason})()]})()]
    for ch in stream:
        if getattr(ch, "usage", None):
            usage = ch.usage
        for c in (getattr(ch, "choices", None) or []):
            d = getattr(c, "delta", None)
            if d is not None:
                extra = getattr(d, "model_extra", None) or {}
                r = getattr(d, "reasoning_content", None) or extra.get("reasoning") or extra.get("reasoning_content")
                if r:
                    think.append(str(r))
                if getattr(d, "content", None):
                    text.append(d.content)
                    try:
                        on_text("".join(text))
                    except Exception:
                        pass
            if getattr(c, "finish_reason", None):
                finish = c.finish_reason
    comp = _Completion("".join(text) or None, "".join(think) or None, finish, usage)
    rest = {k: v for k, v in kw.items()}
    temp = rest.pop("temperature", None)
    out = _chat(_Fake(comp, getattr(client, "base_url", "")), model, system, user,
                {"type": "object"} if not unconstrained else {}, name,
                temperature=temp, max_tokens=max_tokens - allowance, extra_record=extra_record)
    rec = CALLS[-1] if CALLS else {}
    rec["seconds"] = round(__import__("time").time() - t0, 2)
    rec["streamed"] = True
    return out


_REPLY_OPEN = re.compile(r'"reply"\s*:\s*"')


def partial_reply(text: str) -> str:
    """The reply field of a partly streamed chat answer, unescaped, or "" before it starts."""
    m = _REPLY_OPEN.search(text or "")
    if not m:
        return ""
    body, out, i = text[m.end():], [], 0
    esc = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "r": ""}
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            if i + 1 >= len(body):
                break
            nx = body[i + 1]
            if nx == "u":
                if i + 6 > len(body):
                    break
                try:
                    out.append(chr(int(body[i + 2:i + 6], 16)))
                except ValueError:
                    pass
                i += 6
                continue
            out.append(esc.get(nx, nx)); i += 2
            continue
        if ch == '"':
            break
        out.append(ch); i += 1
    return "".join(out)


def chat_reply(client, model: str, message: str, state: str, columns: List[str],
               earlier: Optional[List[Tuple[str, str]]] = None, notes: str = "",
               max_tokens: int = 500, on_reply=None) -> Dict[str, Any]:
    """V4: the model answers a message that is not an analysis request, in its own
    words. One constrained call; it sees the state line, the file's column names, the method notes
    that match, and the last few plain turns, never a row. Verified before use: not empty, no
    column-like name outside the file, no number next to an analysis measure. A failing draft is
    dropped, never repaired."""
    turns = "\n".join(f"Analyst: {u}\nAssistant: {a}" for u, a in (earlier or [])[-3:])
    user = (state + "\nColumns in the file: " + (", ".join(columns) if columns else "none loaded")
            + (("\n\nEarlier turns:\n" + turns[-2000:]) if turns else "")
            + (("\n\nNotes from the method documentation:\n" + notes[:3000]) if notes else "")
            + "\n\nThe analyst wrote:\n" + (message or "").strip())
    low = {n.lower() for n in columns}
    cb = None
    if on_reply is not None:
        shown = {"stop": False}

        def cb(text):
            # what is shown while the reply streams passes the same checks as the final reply; at the
            # first that fails nothing more is shown, and the final check decides what stays
            if shown["stop"]:
                return
            part = partial_reply(text)
            whole = part.rsplit(" ", 1)[0] if " " in part else ""
            ids = set(re.findall(r"`([^`]+)`", whole)) | set(re.findall(r"\b[a-zA-Z]+_[a-zA-Z0-9_]+\b", whole))
            if [x for x in ids if x.lower() not in low] or _RESULT_NUMBER.search(part):
                shown["stop"] = True
                on_reply("")
                return
            if whole:
                on_reply(whole)
    out = _chat(client, model, policy.load("chat"), user, CHAT_SCHEMA, "chat", max_tokens=max_tokens,
                on_text=cb)
    rec = CALLS[-1] if CALLS else {}
    r = (out.get("reply") or "").strip()
    res: Dict[str, Any] = {"reply": None, "dropped": None, "_reasoning": out.get("reasoning"),
                           "_call": rec}
    idents = set(re.findall(r"`([^`]+)`", r)) | set(re.findall(r"\b[a-zA-Z]+_[a-zA-Z0-9_]+\b", r))
    if not r:
        res["dropped"] = "empty"
    elif [x for x in idents if x.lower() not in low]:
        res["dropped"] = "the reply named something that is not a column of the file"
    elif _RESULT_NUMBER.search(r):
        res["dropped"] = "the reply stated a number about an analysis"
    else:
        res["reply"] = r
    return res


def prose_problem(text: str, names: List[str]) -> Optional[str]:
    """Why a piece of model-written prose about the analyst's file cannot be
    shown: empty, a digit, or a column-like name that is not in the file.
    None when it may be shown. Shared by the question wording and the
    refusal explanation; the report and the explanation of a result use the
    stricter closed-reference rule in report_v3."""
    import re as _re
    t = (text or "").strip()
    if not t:
        return "empty"
    if _re.search(r"\d", t):
        return "the draft wrote a number"
    low = {n.lower() for n in names}
    idents = set(_re.findall(r"`([^`]+)`", t)) | set(_re.findall(r"\b[a-zA-Z]+_[a-zA-Z0-9_]+\b", t))
    alien = [x for x in idents if x.lower() not in low]
    if alien:
        return "the draft named something that is not a column of the file"
    return None


# ------------------------------------------------------- the backing check for B1
def backed_roles(msg: str, prof: Dict[str, Any], ext: Dict[str, Any]
                 ) -> Tuple[Dict[str, str], Dict[str, Any], Dict[str, str]]:
    """Keep what the analyst wrote, or described (component 9 guard for B1).

    Returns (backed, unbacked, sources). A name the message contains is
    `quoted`. A name it does not contain is `described: "<phrase>"` when the
    model returned the phrase it read the column from, that phrase is in the
    message word for word, and the column is eligible for the role (decision
    (b) revised 2026-09-11: the model may resolve a description, the harness
    checks it and the card discloses it). Anything else is dropped and logged;
    the role then goes to `complete`, which fills it by a disclosed rule or
    asks. A ghost column the analyst wrote is BACKED (textmatch adds the name
    to the candidates), so `parse_reply` still refuses it by name. Covariates
    are never described: the written subset is kept, none written is a gap.
    """
    from . import textmatch, ablation
    cols = [c["name"] for c in prof.get("columns", [])]
    elig = prof.get("eligible", {}) or {}
    backed: Dict[str, str] = {}
    unbacked: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    if ablation.on("no_backing"):
        # ablation cell: every name the model returned is taken as quoted. The
        # names the check WOULD have dropped are returned as `unbacked` all the
        # same (the caller logs them), so the fits that rest on a guess can be
        # counted; under the paper's rule those are failures whichever column
        # was named.
        b, u, src = _backed_roles_checked(msg, prof, ext)
        for key, val in u.items():
            if key == "covariates":
                b[key] = ", ".join(str(c) for c in (ext.get("covariate_columns") or []))
            else:
                b[key] = str(val)
            src[key] = "quoted (unbacked; ablation no_backing)"
        return b, u, src
    return _backed_roles_checked(msg, prof, ext)


def _backed_roles_checked(msg: str, prof: Dict[str, Any], ext: Dict[str, Any]
                          ) -> Tuple[Dict[str, str], Dict[str, Any], Dict[str, str]]:
    from . import textmatch
    cols = [c["name"] for c in prof.get("columns", [])]
    elig = prof.get("eligible", {}) or {}
    backed: Dict[str, str] = {}
    unbacked: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    def _described(key: str, name: str, phrase) -> bool:
        ph = str(phrase or "").strip()
        if not ph or not textmatch.phrase_in(msg, ph):
            return False
        return name in (elig.get(key) or [])

    for role, key in (("time_column", "time"), ("event_column", "event")):
        name = ext.get(role)
        if name:
            if textmatch.mentions(msg, str(name), cols):
                backed[key], sources[key] = str(name), "quoted"
            elif _described(key, str(name), ext.get(f"{role[:-7]}_evidence")):
                backed[key] = str(name)
                sources[key] = f'described: "{str(ext.get(f"{role[:-7]}_evidence")).strip()}"'
            else:
                unbacked[key] = str(name)
    val = ext.get("event_value")
    if val is not None and str(val).strip():
        if textmatch.value_mentioned(msg, str(val)):
            backed["event_value"], sources["event_value"] = str(val), "quoted"
        else:
            unbacked["event_value"] = str(val)
    # The message's own words about the coding, read against the column:
    # "alive ... is 0 when the patient died and 1 when they were alive" read
    # as 1 (rubric tasks H009/H029/H045/H063/H078/H093), and "event_flag is 1
    # if the event occurred, 0 otherwise" on a column holding 1 and 2 taken
    # as written (H042/H044/H048). Both values were in the message, so the
    # quoting check passed them. When the wording contradicts the value read,
    # the value is ASKED (item 3) -- never filled by the 0/1 rule.
    ev = backed.get("event") or (str(ext.get("event_column")) if ext.get("event_column") else None)
    if ev and ev in cols and backed.get("event_value") is not None:
        levels = [str(v) for v in (next((c for c in prof.get("columns", [])
                                        if c.get("name") == ev), {}).get("values") or [])]
        why = _event_coding_conflict(msg, ev, levels, backed["event_value"])
        if why:
            read = backed.pop("event_value")
            unbacked["event_value"] = read
            # 2026-10-02 (the authors: what the analyst states, and the data does not
            # contradict, is the specification): when the message itself names
            # ONE code the column holds as the event, that code is what the
            # analyst wrote, so it is taken -- the reading's other value was the
            # model's slip, not a question for the analyst (H009/H063/H093 asked
            # "which value means the event" after "0 for death, 1 for alive").
            # A code the column lacks, or wording that labels no single code,
            # is still asked.
            code = _labelled_event_code(msg, ev, levels)
            if code is not None and code != read:
                backed["event_value"] = code
                sources["event_value"] = (f"quoted (your message labels {code} as the event; "
                                          f"the reading had {read})")
                unbacked["event_value_corrected"] = {"read": read, "taken": code}
            else:
                backed["event_value"] = None
                sources["event_value"] = "ask: " + why
    # the stratum / matched-set column: quoted or nothing. A ghost name the
    # analyst wrote is backed like any other, so parse_reply refuses it by name.
    strat = ext.get("stratum_column")
    if strat is not None and str(strat).strip():
        if textmatch.mentions(msg, str(strat), cols):
            backed["stratum"], sources["stratum"] = str(strat), "quoted"
        else:
            unbacked["stratum"] = str(strat)
    covs = ext.get("covariate_columns") or []
    keep, drop, respelled = [], [], {}
    for c in covs:
        c = str(c)
        if textmatch.mentions(msg, c, cols):
            keep.append(c)
            continue
        # The model's spelling, not the analyst's: Qwen3 writes `hla_mismatch`
        # as `hl_a_mismatch` / `hlamismatch` (ablation F01/F04/F10/F13,
        # 2026-09-13), and dropping the name silently narrowed the covariate
        # set the analyst wrote. A dropped name that is, letter for letter,
        # exactly one column of the file, and that column is in the message,
        # is that column -- a deterministic repair, recorded as such.
        same = [k for k in cols if _letters(k) == _letters(c)]
        if len(same) == 1 and same[0] not in keep and textmatch.mentions(msg, same[0], cols):
            keep.append(same[0]); respelled[c] = same[0]
            continue
        # The analyst wrote a LONGER name the file does not have, and the
        # model read it as the file column inside it: "hla_mismatch_count"
        # read as `hla_mismatch` (rubric task H046, 2026-10-01). Dropping the
        # column as unwritten ran the analysis without it, with only a note;
        # keeping the analyst's own name sends it to verify, which refuses it
        # by name, so the analyst says which column was meant.
        near = _written_near_miss(msg, c, cols) if c in cols else None
        if near and near not in keep:
            keep.append(near)
            unbacked.setdefault("near_miss", {})[near] = c
        else:
            drop.append(c)
    # The same longer name when the reading LEFT IT OUT altogether: Qwen3
    # returned "age, bmi, egfr, cold_ischemia" for "adjust for age, bmi, egfr,
    # cold_ischemia and hla_mismatch_count only" and the run went ahead on four
    # covariates with nothing said (rubric task H046, second pass, 2026-10-02).
    # Only for an explicit list -- a message that says the other columns are
    # predictors settles the set by the rule below -- and never for a column
    # this reading gave another role.
    if keep and not _REST_PHRASE.search(msg or ""):
        taken = {backed.get(k) for k in ("time", "event", "stratum")} - {None}
        for c in cols:
            if c in keep or c in taken:
                continue
            near = _written_near_miss(msg, c, cols)
            if near and near not in keep:
                keep.append(near)
                unbacked.setdefault("near_miss", {})[near] = c
    # A column this reading already gave another role is not a predictor because the
    # message writes its name. "patients in several strata, recorded in the column stratum"
    # names the strata; Qwen3 also listed `stratum` as the only covariate (its own reasoning
    # said the covariates were not named) and the run stopped on "the outcome is also listed
    # among the predictors" (simulation prompt search, strat_v3, 2026-09-30). Such a name is
    # taken out of the covariates and logged under its own key -- the analyst DID write it, so
    # it is not reported as unwritten; the covariates then fall to the rule or the question.
    # Only when the message says the OTHER columns are predictors and every written name in the
    # list is such a role column: an explicit list that includes the outcome's own column
    # ("adjust for age, bmi and followup_days") is the analyst's mistake and stays, so that
    # verify refuses it by name.
    role_cols = {backed.get(k) for k in ("time", "event", "stratum")} - {None}
    if keep and all(c in role_cols for c in keep) and _REST_PHRASE.search(msg or ""):
        unbacked["covariates_named_as_role"] = list(keep)
        keep = []
    # A RANGE the analyst wrote ("x1 to x10", "v11 through v50", "x1..x10"):
    # the model quotes the two endpoints, both are in the message, the check
    # accepts them, and the analysis runs on TWO covariates instead of ten --
    # a wrong analysis that nothing refuses (hard request set H003/H007/H012/
    # H024, 2026-09-14). A range whose endpoints are columns of the file and
    # appear in the message is expanded to every column of the same stem with
    # a number in between, deterministically, and the card says so.
    ranges = _ranges_in(msg, cols)
    if ranges and keep:
        expanded = []
        for a, b, members in ranges:
            if a in keep or b in keep:
                for m in members:
                    if m not in keep and m not in expanded:
                        expanded.append(m)
        if expanded:
            keep_set = set(keep) | set(expanded)
            keep = [c for c in cols if c in keep_set]      # the file's order
            respelled["ranges"] = ", ".join(f"{a} to {b}" for a, b, _ in ranges)
    # "Everything else, including site" (hard set H009/H093, 2026-09-15): the
    # model lists the file's other columns, which the message does not write,
    # beside the one it does; the check removes the unwritten names and the
    # fit would rest on `site` alone -- a narrowing the analyst never asked
    # for. When the removed names are all columns of the file and the message
    # itself says that the other columns are predictors, the covariates are
    # the every-usable-column preset, by the same rule that applies when the
    # whole list is unwritten; the source line says so. Without such a phrase
    # the written names stand alone, as before.
    # (a kept name the file lacks -- "add recipient_cmv_status" -- is left to
    # be refused by name, as before: the preset must not swallow a ghost)
    # 2026-10-01: ANY unwritten file column in the reading is the sign, not
    # ALL -- a name the model invented and nobody wrote (Qwen3's
    # `hl_a_mismatch` among the fifty columns of rubric task H004) blocked the
    # rule, and the range in a descriptive aside ("lab_01 to lab_40 are the
    # lab values") became the covariate set in place of "every column other
    # than those two". A ghost the ANALYST wrote is still kept and refused.
    if (keep and drop and any(d in cols for d in drop) and all(k in cols for k in keep)
            and _REST_PHRASE.search(msg or "")):
        respelled.clear()
        backed["covariates"] = "B"
        sources["covariates"] = ("inferred: the message says the other columns are predictors "
                                 "and the reading named columns of the file the message does "
                                 "not write, so every usable column enters")
        unbacked["covariates"] = drop
        return backed, unbacked, sources
    # A range with ONE endpoint the file lacks ("v11 to v51" on a file whose
    # last column is v50: hard set H050, 2026-09-15). The range is real and the
    # endpoint is misnamed; left alone, the range collapses to its one existing
    # endpoint and the analysis runs on that column, with nothing refusing it.
    # The missing name is kept so that the declaration is refused BY NAME and
    # corrected by the analyst, the way any column the file lacks is.
    for miss in _broken_range_endpoints(msg, cols):
        if miss not in keep and textmatch.mentions(msg, miss, cols):
            keep.append(miss)
    if keep:
        backed["covariates"] = ", ".join(keep)
        rng = respelled.pop("ranges", None)
        sources["covariates"] = "quoted" if not (respelled or rng) else (
            "quoted (" + "; ".join(x for x in (
                ("spelling matched to the file: " + ", ".join(f"{a} -> {b}" for a, b in respelled.items())) if respelled else "",
                (f"the range {rng} expanded to every column between") if rng else "") if x) + ")")
    if drop:
        unbacked["covariates"] = drop
    return backed, unbacked, sources


_REST_PHRASE = re.compile(r"\b(everything else|every ?thing else|all (the |of the )?(other|others|remaining|rest)|the rest( of)?|"
                          r"every other|any other|the other columns|other columns|the remaining|all (the )?columns|"
                          r"every column|all (the )?variables|all (the )?predictors|all (the )?covariates)\b", re.I)
_RANGE = re.compile(r"\b([A-Za-z][A-Za-z_]*?)(\d+)\s*(?:to|through|thru|until|-|\u2013|\u2014|\.\.+|\u2026)\s*(?:\1)?(\d+)\b")


def _ranges_in(msg: str, cols: List[str]) -> List[Tuple[str, str, List[str]]]:
    """Every "<stem><a> to <stem><b>" the message writes whose endpoints are
    columns of the file, with the columns of that stem numbered a..b."""
    out = []
    for m in _RANGE.finditer(msg or ""):
        # the digits as written: "lab_01 to lab_40" names lab_01, not lab_1
        # (hard set H004, 2026-09-15)
        stem, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        first, last = f"{stem}{m.group(2)}", f"{stem}{m.group(3)}"
        if a >= b or first not in cols or last not in cols:
            continue
        members = []
        for c in cols:
            mm = re.fullmatch(re.escape(stem) + r"(\d+)", c)
            if mm and a <= int(mm.group(1)) <= b:
                members.append(c)
        if len(members) > 2:
            out.append((first, last, members))
    return out


def _broken_range_endpoints(msg: str, cols: List[str]) -> List[str]:
    """The endpoint names of every "<stem><a> to <stem><b>" the message writes
    of which exactly one is a column of the file: the other is a misnamed
    column, to be refused by name rather than dropped."""
    out = []
    for m in _RANGE.finditer(msg or ""):
        stem, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        first, last = f"{stem}{m.group(2)}", f"{stem}{m.group(3)}"
        if a >= b or (first in cols) == (last in cols):
            continue
        miss = last if first in cols else first
        if miss not in out:
            out.append(miss)
    return out


def _written_near_miss(msg: str, col: str, cols: List[str]) -> Optional[str]:
    """A name the message writes that contains the file column `col` as a
    whole underscore-delimited part ("hla_mismatch_count" for `hla_mismatch`)
    and is not itself a column of the file."""
    lc, lower_cols = col.lower(), {c.lower() for c in cols}
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_]*", msg or ""):
        t = tok.lower()
        if t == lc or t in lower_cols:
            continue
        if t.startswith(lc + "_") or t.endswith("_" + lc) or ("_" + lc + "_") in t:
            return tok
    return None


_EVENT_WORDS = re.compile(r"\b(died|die|dies|dying|dead|death|deaths|deceased|event|events|occurred|occurs|"
                          r"happened|happens|failed|failure|graft loss|lost|relapsed?|progressed|progression)\b", re.I)
_NONEVENT_WORDS = re.compile(r"\b(alive|living|censored|censoring|survived|surviving|otherwise|"
                             r"event[- ]free|no event|without (the |an )?event)\b", re.I)
_CODE = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def _event_coding_conflict(msg: str, ev: str, levels: List[str], chosen: str) -> Optional[str]:
    """Why the message's wording of the event column's coding contradicts
    `chosen`, or None. Deterministic and conservative: only pieces of a
    sentence that name the column and write a code are read; a piece with
    both kinds of words, or none, says nothing."""
    from . import textmatch
    for sent in re.split(r"(?<=[.!?;])\s+|\n+", msg or ""):
        if not textmatch.mentions(sent, ev, [ev]):
            continue
        # one code per piece: "0 when the patient died and 1 when alive",
        # "1 if the event occurred, 0 otherwise", "= 1 for an event (0 otherwise)"
        pieces = [p for p in re.split(r",|;|\(|\)|\band\b|\bwhile\b|\bwhereas\b", sent) if _CODE.search(p)]
        label: Dict[str, str] = {}
        for p in pieces:
            codes = _CODE.findall(p)
            if len(codes) != 1:
                continue
            code = codes[0]
            # written AS a code ("= 1", "is 1 if", "0 otherwise", "1 when ..."),
            # not a count ("42 events") that happens to sit in the sentence
            if not _written_as_code(p, code):
                continue
            words = re.sub(re.escape(ev), " ", p, flags=re.I)
            is_ev, is_non = bool(_EVENT_WORDS.search(words)), bool(_NONEVENT_WORDS.search(words))
            if levels and code not in levels and (is_ev or is_non):
                return (f"your message describes `{ev}` = {code}, but the column holds "
                        f"{' and '.join(levels)} only")
            if is_ev != is_non:
                label[code] = "event" if is_ev else "non-event"
        if label.get(chosen) == "non-event" or any(
                v == "event" and c != chosen for c, v in label.items()):
            ev_code = next((c for c, v in label.items() if v == "event"), None)
            return (f"your message describes `{ev}` = {chosen} as "
                    + ("not the event" if label.get(chosen) == "non-event" else "something else")
                    + (f" and {ev_code} as the event" if ev_code and ev_code != chosen else ""))
    return None


def _written_as_code(piece: str, code: str) -> bool:
    """`code` is written as a code of the column in this piece ("= 1", "is 1
    if", "0 otherwise", "1 when ..."), not as a count ("42 events")."""
    return bool(re.search(r"(=|\bis|\bare|\bcoded(?: as)?|\bequals?|\bvalue(?: of)?)\s*" + code + r"(?!\d)"
                          r"|(?<!\d)" + code + r"\s*(=|\bif\b|\bwhen\b|\bfor\b|\bmeans\b|\bindicates?\b|"
                          r"\botherwise\b|\bmarks?\b)", piece, re.I))


def _labelled_event_code(msg: str, ev: str, levels: List[str]) -> Optional[str]:
    """The ONE code of `ev`, held by the column, that the message labels as the
    event, or None. Read the way _event_coding_conflict reads: a sentence that
    names the column, one code per piece, written as a code; a piece with both
    kinds of words, or none, says nothing. None when no code or more than one
    is labelled the event, when a labelled code is not in the column, or when
    two pieces label the same code differently."""
    from . import textmatch
    found: Dict[str, str] = {}
    for sent in re.split(r"(?<=[.!?;])\s+|\n+", msg or ""):
        if not textmatch.mentions(sent, ev, [ev]):
            continue
        for p in re.split(r",|;|\(|\)|\band\b|\bwhile\b|\bwhereas\b", sent):
            codes = _CODE.findall(p)
            if len(codes) != 1 or not _written_as_code(p, codes[0]):
                continue
            code = codes[0]
            words = re.sub(re.escape(ev), " ", p, flags=re.I)
            is_ev, is_non = bool(_EVENT_WORDS.search(words)), bool(_NONEVENT_WORDS.search(words))
            if is_ev == is_non:
                continue
            if levels and code not in levels:
                return None
            lab = "event" if is_ev else "non-event"
            if found.get(code, lab) != lab:
                return None
            found[code] = lab
    ev_codes = [c for c, v in found.items() if v == "event"]
    return ev_codes[0] if len(ev_codes) == 1 else None


def _letters(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


# ------------------------------------------------------------- explaining a refusal
REFUSAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"reasoning": {"type": "string"}, "explanation": {"type": "string"}},
    "required": ["reasoning", "explanation"],
}


def explain_refusal(client, model: str, refusals: List[Dict[str, Any]],
                    profile: Dict[str, Any], declaration: Any,
                    max_tokens: int = 350) -> Dict[str, Any]:
    """The model explains a refusal in plain words; it never advises. A draft
    with a digit or a name outside the file is dropped, never repaired."""
    names = [c["name"] for c in profile.get("columns", [])]
    d = declaration
    roles = (f"follow-up time = {d.time_col}; event = {d.event_col} at value {d.event_value}; "
             f"covariates = {', '.join(d.covariates or [])}") if d is not None else "(none)"
    user = ("Columns in the file:\n" + ", ".join(names)
            + "\n\nThe declaration:\n" + roles
            + "\n\nThe harness refused, for these reasons:\n"
            + "\n".join(f"  - {r.get('code', '')}: {r.get('message', '')}" for r in refusals))
    out = _chat(client, model, policy.load("refusal"), user, REFUSAL_SCHEMA, "refusal",
                max_tokens=max_tokens)
    rec = CALLS[-1] if CALLS else {}
    text = (out.get("explanation") or "").strip()
    why = prose_problem(text, names) or advice_problem(text)
    return {"explanation": None if why else text, "dropped": why,
            "_reasoning": out.get("reasoning"), "_call": rec}


# the phrases by which a refusal explanation turns into advice. The rule
# is explain, never advise; the 2026-09-11 Qwen2.5 draft
# ended "Please specify only two levels in this column to proceed", which the
# earlier six-word check let through. Deterministic, and a false positive
# costs only the model's sentences: the harness's own refusal is always shown.
ADVICE_MARKERS = ("you should", "you could", "you can", "you may", "you might",
                  "you need", "you will need", "you must", "please ", "instead",
                  "recode", "try ", "consider", "recommend", "suggest", "to proceed",
                  "in order to", "make sure", "ensure that", "it is advisable")


def advice_problem(text: str) -> Optional[str]:
    """Why a refusal explanation cannot be shown: it tells the analyst what to
    do. None when it only explains."""
    low = " " + " ".join((text or "").lower().split()) + " "
    hits = [m for m in ADVICE_MARKERS if m in low]
    return f"the draft advised ({hits[0].strip()!r})" if hits else None


# ------------------------------------------------------------- M2: several steps
STEP_ACTS = ("select_external", "run", "edit_and_run", "compare_runs", "explain_result")
MAX_STEPS = 5


def plan_steps_schema(externals: List[str]) -> Dict[str, Any]:
    ext = ({"anyOf": [{"type": "string", "enum": list(externals)}, {"type": "null"}]}
           if externals else {"type": "null"})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {"type": "string"},
            "steps": {"type": "array", "minItems": 1, "maxItems": MAX_STEPS,
                      "items": {"type": "object", "additionalProperties": False,
                                "properties": {
                                    "act": {"type": "string", "enum": list(STEP_ACTS)},
                                    "external": ext,
                                    "evidence": {"type": "string"}},
                                "required": ["act", "external", "evidence"]}},
        },
        "required": ["reasoning", "steps"],
    }


def plan_steps(client, model: str, message: str, state: str,
               externals: List[str], max_tokens: int = 700) -> Dict[str, Any]:
    """M2: one constrained call proposing the ordered steps of a multi-step
    request. A PROPOSAL: `validate_steps` keeps only what the harness can do."""
    user = (f"{state}\n\nLoaded external files: "
            + (", ".join(externals) or "(none)")
            + "\n\nThe analyst wrote:\n" + message.strip())
    out = _chat(client, model, policy.load("plan_steps"), user,
                plan_steps_schema(externals), "plan_steps", max_tokens=max_tokens)
    return out


def validate_steps(message: str, raw: Dict[str, Any], externals: List[str],
                   n_results: int) -> List[Dict[str, Any]]:
    """Deterministic: an act must be known, a file name loaded, the evidence
    in the message; a `select_external` must name a file; a loaded file named
    on a run step becomes a selection before that run; a `compare_runs` needs
    two runs by the time it is reached; the list is cut at the first step
    that fails. Never more than MAX_STEPS."""
    from . import textmatch
    steps: List[Dict[str, Any]] = []
    runs = n_results
    current: Optional[str] = None      # the file the plan has selected so far
    for item in (raw.get("steps") or [])[:MAX_STEPS]:
        if not isinstance(item, dict) or len(steps) >= MAX_STEPS:
            break
        act, ext, ev = item.get("act"), item.get("external"), str(item.get("evidence") or "")
        if act not in STEP_ACTS or not ev or not textmatch.phrase_in(message, ev):
            break
        if act == "select_external":
            if ext not in externals:
                break
            current = ext
        elif ext is not None:
            # a loaded file named on a run step is a selection the model did
            # not spell out ("run it with X"): the 2026-09-11 Qwen2.5 plan was
            # run(A), run(B), compare. Insert the selection unless the plan
            # already selected that file; a name that is not loaded is cut.
            if ext not in externals:
                break
            if act in ("run", "edit_and_run") and ext != current:
                steps.append({"act": "select_external", "external": ext, "evidence": ev})
                current = ext
            ext = None
        if act in ("run", "edit_and_run"):
            runs += 1
        if act == "compare_runs" and runs < 2:
            break
        steps.append({"act": act, "external": ext, "evidence": ev})
    return steps[:MAX_STEPS]
