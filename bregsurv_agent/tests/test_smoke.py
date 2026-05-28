"""Stub-LLM smoke test for the BregSurv agent.

Hits the REAL R subprocess (no GPU / no vLLM required) using a
scripted fake LLM client. Verifies plumbing end-to-end:

    canned tool_calls
        → BregSurvAgent.query
        → tools.dispatch
        → runner.run_r (real Rscript)
        → BregSurv::coxkl
        → AgentResponse.trace + repro.R + trace.json

Prerequisites on the host:
  * R + the ``BregSurv`` package installed.
  * ``data/ExampleData_lowdim.rda`` present at the repo root (it is —
    the package ships it as part of the R sources).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bregsurv_agent import BregSurvAgent


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_DATA = REPO_ROOT / "data" / "ExampleData_lowdim.rda"


# -- Stub OpenAI client ------------------------------------------------------

def _build_chat_response(content: str = "", tool_calls=()):
    """Return a duck-typed ``ChatCompletion``."""
    tcs = []
    for i, tc in enumerate(tool_calls):
        tcs.append(SimpleNamespace(
            id=f"call_{i}",
            type="function",
            function=SimpleNamespace(
                name=tc["name"],
                arguments=tc["arguments"],
            ),
        ))
    msg = SimpleNamespace(content=content, tool_calls=tcs or None)
    choice = SimpleNamespace(message=msg, finish_reason=(
        "tool_calls" if tcs else "stop"
    ))
    return SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(prompt_tokens=42, completion_tokens=17),
    )


class StubLLMClient:
    """Returns scripted responses in order on every ``create()`` call."""

    def __init__(self, scripted_responses):
        self._scripted = list(scripted_responses)
        self._call_count = 0
        # Make ``client.chat.completions.create`` resolve to self.create.
        self.chat = self
        self.completions = self

    def create(self, *args, **kwargs):  # noqa: ARG002 (mimic OpenAI signature)
        if self._call_count >= len(self._scripted):
            raise RuntimeError(
                f"StubLLMClient: scripted responses exhausted "
                f"({len(self._scripted)} calls)"
            )
        resp = self._scripted[self._call_count]
        self._call_count += 1
        return resp


# -- Tests -------------------------------------------------------------------

class FitCoxklSmokeTest(unittest.TestCase):
    """One tool round: agent emits fit_coxkl, R runs, agent says 'done'."""

    def setUp(self):
        self.assertTrue(
            EXAMPLE_DATA.exists(),
            f"Missing test fixture: {EXAMPLE_DATA}. The repo should ship "
            f"data/ExampleData_lowdim.rda as part of the R-package source."
        )

    def test_fit_coxkl_against_real_R(self):
        tool_args = {
            "data_path": str(EXAMPLE_DATA),
            "z_expr": "ExampleData_lowdim$train$z",
            "time_expr": "ExampleData_lowdim$train$time",
            "delta_expr": "ExampleData_lowdim$train$status",
            "etas": [0.0, 0.5, 1.0],
            "beta_expr": "ExampleData_lowdim$beta_external_good",
        }
        scripted = [
            _build_chat_response(tool_calls=[{
                "name": "fit_coxkl",
                "arguments": json.dumps(tool_args),
            }]),
            _build_chat_response(
                content="Done — fit_coxkl returned coefficients for 3 etas."
            ),
        ]

        agent = BregSurvAgent(
            model_endpoint="http://stub",
            model_name="stub-qwen",
            api_key="EMPTY",
            client=StubLLMClient(scripted),
        )
        response = agent.query(
            "Fit Cox KL on ExampleData with etas=[0, 0.5, 1] and the "
            "good external beta."
        )

        self.assertIsNone(response.error, f"agent.query errored: {response.error}")
        self.assertEqual(response.text,
                         "Done — fit_coxkl returned coefficients for 3 etas.")
        self.assertEqual(len(response.trace.events), 1)

        event = response.trace.events[0]
        self.assertEqual(event.tool, "fit_coxkl")
        self.assertEqual(
            event.status, "ok",
            f"R subprocess failed: {event.error_message}\n"
            f"summary: {event.result_summary}",
        )
        self.assertIn("n_obs", event.result_summary)
        self.assertEqual(event.result_summary["n_obs"], 100)
        self.assertEqual(event.result_summary["n_covariates"], 6)
        self.assertEqual(event.result_summary["n_etas"], 3)

    def test_writes_repro_r_and_trace_json(self):
        tool_args = {
            "data_path": str(EXAMPLE_DATA),
            "z_expr": "ExampleData_lowdim$train$z",
            "time_expr": "ExampleData_lowdim$train$time",
            "delta_expr": "ExampleData_lowdim$train$status",
            "etas": [0.5],
            "beta_inline": [0.2, -0.3, 0.1, -0.3, 0.3, 0.1],
        }
        scripted = [
            _build_chat_response(tool_calls=[{
                "name": "fit_coxkl",
                "arguments": json.dumps(tool_args),
            }]),
            _build_chat_response(content="Coefficients computed."),
        ]

        agent = BregSurvAgent(
            model_endpoint="http://stub",
            client=StubLLMClient(scripted),
        )
        response = agent.query("Fit Cox KL with eta=0.5 using inline beta.")
        self.assertIsNone(response.error, response.error)
        self.assertEqual(response.trace.events[0].status, "ok")

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "trace.json")
            repro_path = os.path.join(tmpdir, "repro.R")
            response.save_trace(trace_path)
            response.write_repro_r(repro_path)

            with open(trace_path, encoding="utf-8") as f:
                trace_dict = json.load(f)
            self.assertEqual(trace_dict["llm_turns"], 2)
            self.assertEqual(len(trace_dict["events"]), 1)
            self.assertEqual(trace_dict["events"][0]["tool"], "fit_coxkl")

            with open(repro_path, encoding="utf-8") as f:
                repro = f.read()
            self.assertIn("library(jsonlite)", repro)
            self.assertIn("fit_coxkl", repro)
            self.assertIn("beta_inline", repro)
            self.assertIn(str(EXAMPLE_DATA), repro)


class EtaDefaultResolutionTest(unittest.TestCase):
    """Confirm that fit_coxkl_ridge with eta=None gets resolved to 0.0."""

    def setUp(self):
        self.assertTrue(EXAMPLE_DATA.exists())

    def test_resolves_eta_None_to_zero_and_attaches_notice(self):
        # Use highdim data so ridge actually runs reasonably fast.
        highdim_path = REPO_ROOT / "data" / "ExampleData_highdim.rda"
        if not highdim_path.exists():
            self.skipTest("ExampleData_highdim.rda not available")

        tool_args = {
            "data_path": str(highdim_path),
            "z_expr": "ExampleData_highdim$train$z",
            "time_expr": "ExampleData_highdim$train$time",
            "delta_expr": "ExampleData_highdim$train$status",
            "beta_expr": "ExampleData_highdim$beta_external",
            "nlambda": 5,  # speed up
            # NB: eta is intentionally omitted.
        }
        scripted = [
            _build_chat_response(tool_calls=[{
                "name": "fit_coxkl_ridge",
                "arguments": json.dumps(tool_args),
            }]),
            _build_chat_response(content="Done."),
        ]

        agent = BregSurvAgent(
            model_endpoint="http://stub",
            client=StubLLMClient(scripted),
        )
        response = agent.query("Ridge fit on highdim with the external beta.")
        self.assertIsNone(response.error, response.error)

        event = response.trace.events[0]
        self.assertEqual(event.tool, "fit_coxkl_ridge")
        # Effective args MUST have eta=0.0 even though LLM omitted it.
        self.assertEqual(event.effective_args.get("eta"), 0.0)
        # And the result should carry a _notice_eta_default + _notice_speed_slow.
        # (These live on the full R result in response.tool_results, not the
        # summary; check there.)
        full = response.tool_results[0]["result"]
        self.assertEqual(full.get("status"), "ok",
                         f"R failed: {full.get('message')}")
        self.assertIn("_notice_eta_default", full)
        self.assertIn("_notice_speed_slow", full)


if __name__ == "__main__":
    unittest.main(verbosity=2)
