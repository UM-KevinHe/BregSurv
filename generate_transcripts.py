#!/usr/bin/env python3
"""Generate the 6 ExampleData supplement transcripts for the paper.

Runs one query per bundled .rda dataset against an OpenAI-compatible
LLM endpoint (vLLM / Together / OpenAI), saves trace.json + repro.R +
report.md + report.pdf + transcript.txt per dataset.

Typical use on Great Lakes::

    # First terminal: salloc + restart vLLM in tmux
    salloc --account=kevinhe1 --partition=spgpu --gres=gpu:a40:1 \\
        --mem=64G --cpus-per-task=8 --time=2:00:00
    module load python/3.11.5 cuda/12.8.2 R/4.4
    source /scratch/.../envs/vllm-env/bin/activate
    tmux new -s vllm
    vllm serve /scratch/.../models/qwen2.5-7b-awq \\
        --port 8000 --served-model-name qwen2.5-7b-awq \\
        --tool-call-parser hermes --enable-auto-tool-choice \\
        --max-model-len 32768 --gpu-memory-utilization 0.5

    # Second terminal on the same node
    cd /scratch/.../BregSurv-mcp
    python generate_transcripts.py --prompt-file prompt_v2.txt

Locally on Mac against OpenAI for a quick sanity check::

    OPENAI_API_KEY=sk-... python generate_transcripts.py \\
        --endpoint https://api.openai.com/v1 --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict

# Make sure the local package is importable when run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bregsurv_agent import BregSurvAgent  # noqa: E402
from bregsurv_agent.prompts import set_system_prompt  # noqa: E402
from bregsurv_agent.report import build_markdown, markdown_to_pdf  # noqa: E402


# --------------------------------------------------------------------------
# The 6 supplement transcripts.
#
# Each `query` is written to sound like a real user (some context, some
# hints about field names). The agent is responsible for routing to the
# right tool; we record what it picked in the transcript so the paper
# table can claim "Qwen 7B picked X/6 correctly without intervention".
#
# `expected_tool` is the one we want; if the model picks something else,
# the transcript still saves but a warning prints.
# --------------------------------------------------------------------------

SPECS: List[Dict] = [
    {
        "name": "01_lowdim_coxkl",
        "data": "ExampleData_lowdim.rda",
        "expected_tool": "fit_coxkl",
        "query": (
            "I have a small cohort study saved at {data_path}. The "
            "object is named ExampleData_lowdim; its `train` slot has "
            "`z` (6 covariates), `time`, `status`, and `stratum`. I "
            "have external Cox coefficients in `beta_external_good`. "
            "Please fit a KL-divergence transfer-learning Cox model at "
            "eta = 0, 0.5, and 1 so I can see how the borrowing affects "
            "estimates."
        ),
        "explicit_query": (
            "Fit a Cox KL transfer-learning model on the cohort data "
            "at {data_path}. Use these EXACT R expressions verbatim "
            "(do not wrap in brackets or shorten):\n"
            "  z       = ExampleData_lowdim$train$z\n"
            "  time    = ExampleData_lowdim$train$time\n"
            "  delta   = ExampleData_lowdim$train$status\n"
            "  stratum = ExampleData_lowdim$train$stratum\n"
            "  beta    = ExampleData_lowdim$beta_external_good\n"
            "  etas    = [0, 0.5, 1]"
        ),
    },
    {
        "name": "02_indi_cox_indi",
        "data": "ExampleData_indi.rda",
        "expected_tool": "fit_cox_indi",
        "query": (
            "I have two cohorts at {data_path}, named "
            "ExampleData_indi$internal and ExampleData_indi$external. "
            "Each has fields z, time, status, stratum. The external "
            "cohort has full individual-level data, not just summary "
            "coefficients. Please fit a Cox transfer-learning model "
            "that borrows from the external individuals at eta = 0, "
            "0.5, and 1."
        ),
        "explicit_query": (
            "Fit an individual-data Cox transfer-learning model on "
            "{data_path}. Use these EXACT R expressions verbatim "
            "(do not shorten or omit the ExampleData_indi$ prefix):\n"
            "  z_int       = ExampleData_indi$internal$z\n"
            "  time_int    = ExampleData_indi$internal$time\n"
            "  delta_int   = ExampleData_indi$internal$status\n"
            "  stratum_int = ExampleData_indi$internal$stratum\n"
            "  z_ext       = ExampleData_indi$external$z\n"
            "  time_ext    = ExampleData_indi$external$time\n"
            "  delta_ext   = ExampleData_indi$external$status\n"
            "  stratum_ext = ExampleData_indi$external$stratum\n"
            "  etas        = [0, 0.5, 1]"
        ),
    },
    {
        "name": "03_highdim_coxkl_enet",
        "data": "ExampleData_highdim.rda",
        "expected_tool": "fit_coxkl_enet",
        "query": (
            "High-dimensional Cox cohort at {data_path}. "
            "ExampleData_highdim$train has `z` with 50 covariates, "
            "plus `time` and `status`. External coefficients are in "
            "`beta_external`. Please fit an elastic-net Cox with KL "
            "borrowing at eta = 0.5. I want variable selection."
        ),
        "explicit_query": (
            "Fit an elastic-net Cox KL model (variable selection on "
            "p=50 covariates) on {data_path}. Use these EXACT R "
            "expressions verbatim:\n"
            "  z     = ExampleData_highdim$train$z\n"
            "  time  = ExampleData_highdim$train$time\n"
            "  delta = ExampleData_highdim$train$status\n"
            "  beta  = ExampleData_highdim$beta_external\n"
            "  eta   = 0.5"
        ),
    },
    {
        "name": "04_cc_lowdim_ncckl",
        "data": "ExampleData_cc_lowdim.rda",
        "expected_tool": "fit_ncckl",
        "query": (
            "Nested case-control study at {data_path}. "
            "ExampleData_cc_lowdim$train has `y` (case status), "
            "`stratum` (matched-set ID), and `z` (6 covariates). "
            "External summary coefficients are in `beta_external`. "
            "Please fit a NCC transfer-learning model with KL borrowing "
            "at eta = 0.5."
        ),
        "explicit_query": (
            "Fit a NCC (nested case-control) KL transfer-learning "
            "model on {data_path}. Use these EXACT R expressions "
            "verbatim (note the $train$ nesting — do not skip it):\n"
            "  z       = ExampleData_cc_lowdim$train$z\n"
            "  y       = ExampleData_cc_lowdim$train$y\n"
            "  stratum = ExampleData_cc_lowdim$train$stratum\n"
            "  beta    = ExampleData_cc_lowdim$beta_external\n"
            "  etas    = [0.5]"
        ),
    },
    {
        "name": "05_cc_indi_ncc_indi",
        "data": "ExampleData_cc_indi.rda",
        "expected_tool": "fit_ncc_indi",
        "query": (
            "I have two NCC cohorts at {data_path} — "
            "ExampleData_cc_indi$internal and "
            "ExampleData_cc_indi$external. Each has z, y, stratum. "
            "Use the external cohort (individual records, not "
            "summary stats) as the borrowing source. Fit at eta = 0, "
            "0.5, 1."
        ),
        "explicit_query": (
            "Fit an individual-data NCC transfer-learning model on "
            "{data_path}. Use these EXACT R expressions verbatim "
            "(keep the full ExampleData_cc_indi$ prefix on every one):\n"
            "  z_int       = ExampleData_cc_indi$internal$z\n"
            "  y_int       = ExampleData_cc_indi$internal$y\n"
            "  stratum_int = ExampleData_cc_indi$internal$stratum\n"
            "  z_ext       = ExampleData_cc_indi$external$z\n"
            "  y_ext       = ExampleData_cc_indi$external$y\n"
            "  stratum_ext = ExampleData_cc_indi$external$stratum\n"
            "  etas        = [0, 0.5, 1]"
        ),
    },
    {
        "name": "06_cc_highdim_ncckl_enet",
        "data": "ExampleData_cc_highdim.rda",
        "expected_tool": "fit_ncckl_enet",
        "query": (
            "High-dimensional NCC at {data_path}. "
            "ExampleData_cc_highdim$train has 20 covariates in `z`, "
            "plus `y` and `stratum`. External coefficients in "
            "`beta_external`. Please fit an elastic-net NCC with KL "
            "borrowing at eta = 0.5."
        ),
        "explicit_query": (
            "Fit an elastic-net NCC KL model (variable selection on "
            "p=20 covariates) on {data_path}. Use these EXACT R "
            "expressions verbatim (note the $train$ nesting):\n"
            "  z       = ExampleData_cc_highdim$train$z\n"
            "  y       = ExampleData_cc_highdim$train$y\n"
            "  stratum = ExampleData_cc_highdim$train$stratum\n"
            "  beta    = ExampleData_cc_highdim$beta_external\n"
            "  eta     = 0.5"
        ),
    },
]


# --------------------------------------------------------------------------
# Per-transcript orchestration
# --------------------------------------------------------------------------

def run_one(spec: Dict, data_dir: Path, out_dir: Path,
            agent_kwargs: Dict, use_explicit: bool = False) -> Dict:
    """Run one spec; return a summary row for the manifest."""
    data_path = (data_dir / spec["data"]).resolve()
    target = (out_dir / spec["name"]).resolve()
    target.mkdir(parents=True, exist_ok=True)

    summary = {
        "name": spec["name"],
        "data": spec["data"],
        "expected_tool": spec["expected_tool"],
        "data_exists": data_path.exists(),
        "query_style": "explicit" if use_explicit else "natural",
    }
    if not data_path.exists():
        print(f"  ✗ SKIP: {data_path} not found")
        return summary

    query_template = (spec.get("explicit_query") if use_explicit
                      else spec.get("query"))
    if not query_template:
        print(f"  ✗ SKIP: no {'explicit_query' if use_explicit else 'query'} "
              f"defined for {spec['name']}")
        return summary
    query = query_template.format(data_path=str(data_path))
    print(f"  query (first 120 chars): {query[:120]}...")

    agent = BregSurvAgent(**agent_kwargs)
    t0 = time.monotonic()
    response = agent.query(query, data_path=str(data_path))
    wall_s = time.monotonic() - t0

    # Save artifacts.
    response.save_trace(str(target / "trace.json"))
    response.write_repro_r(str(target / "repro.R"))
    md = build_markdown(response, query)
    (target / "report.md").write_text(md, encoding="utf-8")
    pdf_path = target / "report.pdf"
    try:
        markdown_to_pdf(md, str(pdf_path))
        pdf_ok = True
    except Exception as e:
        pdf_ok = False
        print(f"  ! PDF skipped: {type(e).__name__}: {e}")

    # Plain transcript for quick paper-figure use.
    with open(target / "transcript.txt", "w", encoding="utf-8") as f:
        f.write("=== USER QUERY ===\n")
        f.write(query + "\n\n")
        f.write("=== ASSISTANT FINAL MESSAGE ===\n")
        f.write((response.text or "(empty)") + "\n\n")
        f.write(f"=== TOOLS CALLED ({len(response.trace.events)}) ===\n")
        for ev in response.trace.events:
            f.write(f"  {ev.tool}  status={ev.status}  "
                    f"latency={ev.latency_ms}ms\n")
            if ev.error_message:
                f.write(f"    error: {ev.error_message[:200]}\n")
        if response.error:
            f.write(f"\n=== AGENT-LEVEL ERROR ===\n{response.error}\n")

    # Routing accuracy: did any tool call match `expected_tool`?
    tools_seen = [e.tool for e in response.trace.events]
    routed_correctly = spec["expected_tool"] in tools_seen

    # Did the expected tool EVENTUALLY produce a usable result?
    # (More realistic than `all e.status == "ok"` — Qwen 7B often retries
    # after wrong _expr args, and a self-recovered fit is still a valid
    # paper-supplement outcome.)
    succeeded_eventually = any(
        e.tool == spec["expected_tool"] and e.status == "ok"
        for e in response.trace.events
    )
    # Index of the first successful expected-tool call (1-based), or None.
    success_at_attempt = None
    matching_calls = 0
    for ev in response.trace.events:
        if ev.tool == spec["expected_tool"]:
            matching_calls += 1
            if ev.status == "ok" and success_at_attempt is None:
                success_at_attempt = matching_calls
    # How many failed attempts before the first success on the expected tool
    retries_before_success = (
        (success_at_attempt - 1) if success_at_attempt is not None else None
    )
    all_ok = all(e.status == "ok" for e in response.trace.events) and not response.error

    summary.update({
        "wall_s": round(wall_s, 2),
        "llm_turns": response.trace.llm_turns,
        "tools_called": tools_seen,
        "routed_correctly": routed_correctly,
        "succeeded_eventually": succeeded_eventually,
        "retries_before_success": retries_before_success,
        "all_tools_ok": all_ok,
        "pdf_generated": pdf_ok,
    })

    if succeeded_eventually:
        if retries_before_success == 0:
            flag = "✓ one-shot"
        else:
            flag = f"✓ recovered (after {retries_before_success} retr"
            flag += "y)" if retries_before_success == 1 else "ies)"
    else:
        flag = "✗ failed"
    print(f"  {flag}  tools={tools_seen}  wall={wall_s:.1f}s  routed={routed_correctly}")
    return summary


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", default=os.environ.get(
        "SURVBREGDIV_MODEL_ENDPOINT", "http://localhost:8000/v1"),
        help="OpenAI-compatible base URL. Default: localhost vLLM.")
    ap.add_argument("--model", default=os.environ.get(
        "SURVBREGDIV_MODEL_NAME", "qwen2.5-7b-awq"),
        help="Served model name.")
    ap.add_argument("--api-key", default=os.environ.get(
        "OPENAI_API_KEY", "EMPTY"),
        help="API key (vLLM ignores; OpenAI requires).")
    ap.add_argument("--data-dir", type=Path,
                    default=Path(__file__).parent / "data",
                    help="Directory holding the bundled .rda fixtures.")
    ap.add_argument("--out-dir", type=Path,
                    default=Path(__file__).parent / "paper_figures" / "transcripts",
                    help="Where to write per-transcript subdirectories.")
    ap.add_argument("--prompt-file", type=Path, default=None,
                    help="Path to a text file containing the v2 system "
                         "prompt (overrides the package placeholder).")
    ap.add_argument("--only", default=None,
                    help="Run only this single transcript name (e.g. "
                         "'01_lowdim_coxkl').")
    ap.add_argument("--explicit-paths", action="store_true",
                    help="Use the EXPLICIT-PATH query variant for each "
                         "spec (gives Qwen literal R expression strings "
                         "verbatim instead of natural-language hints). "
                         "Produces cleaner one-shot results; pair with "
                         "a different --out-dir to keep both variants.")
    args = ap.parse_args()

    # System prompt: use file if given, else the package placeholder.
    if args.prompt_file:
        text = args.prompt_file.read_text(encoding="utf-8")
        set_system_prompt(text)
        print(f"[prompt] loaded {len(text)} chars from {args.prompt_file}")
    else:
        print("[prompt] using package placeholder (set --prompt-file to "
              "override; routing accuracy will be lower)")

    agent_kwargs = {
        "model_endpoint": args.endpoint,
        "model_name": args.model,
        "api_key": args.api_key,
        "deployment_mode": "local",
    }
    print(f"[agent] endpoint={args.endpoint} model={args.model}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    specs_to_run = [s for s in SPECS if not args.only or s["name"] == args.only]
    if not specs_to_run:
        print(f"No specs match --only={args.only!r}")
        return 2

    print(f"[query style] {'EXPLICIT-PATH' if args.explicit_paths else 'natural'}")

    manifest = []
    for i, spec in enumerate(specs_to_run, 1):
        print(f"\n=== [{i}/{len(specs_to_run)}] {spec['name']} ===")
        try:
            row = run_one(spec, args.data_dir, args.out_dir, agent_kwargs,
                          use_explicit=args.explicit_paths)
        except Exception as e:
            print(f"  ✗✗ CRASH: {type(e).__name__}: {e}")
            row = {"name": spec["name"], "crashed": True,
                   "error": f"{type(e).__name__}: {e}"}
        manifest.append(row)

    manifest_path = args.out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Realistic success metric: did the expected tool eventually succeed?
    n_routed = sum(1 for r in manifest if r.get("routed_correctly"))
    n_success = sum(1 for r in manifest if r.get("succeeded_eventually"))
    n_oneshot = sum(1 for r in manifest
                    if r.get("succeeded_eventually")
                    and r.get("retries_before_success") == 0)
    print(f"\n=== Done.  routed correctly: {n_routed}/{len(manifest)}  |  "
          f"succeeded eventually: {n_success}/{len(manifest)}  |  "
          f"one-shot (no retry): {n_oneshot}/{len(manifest)} ===")
    print(f"Manifest: {manifest_path}")
    return 0 if n_success == len(manifest) else 1


if __name__ == "__main__":
    sys.exit(main())
