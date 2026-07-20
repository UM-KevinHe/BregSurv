"""Verify ``repro.R`` from a real agent trace produces bit-identical
output when run via Rscript.

This is the "verification-scaffolded inference" pillar #3 — the audit trail
plus the standalone reproducer let a reviewer rerun the agent's
computation without the LLM in the loop.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bregsurv_agent import BregSurvAgent
from bregsurv_agent.runner import find_rscript

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_DATA = REPO_ROOT / "data" / "ExampleData_lowdim.rda"
R_SCRIPTS_DIR = REPO_ROOT / "mcp" / "r_scripts"


def _build_chat_response(content="", tool_calls=()):
    tcs = []
    for i, tc in enumerate(tool_calls):
        tcs.append(SimpleNamespace(
            id=f"call_{i}",
            type="function",
            function=SimpleNamespace(
                name=tc["name"], arguments=tc["arguments"]),
        ))
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tcs or None),
            finish_reason="tool_calls" if tcs else "stop",
        )],
        usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
    )


class _StubClient:
    def __init__(self, scripted):
        self._s = list(scripted)
        self._i = 0
        self.chat = self
        self.completions = self

    def create(self, *a, **kw):
        r = self._s[self._i]
        self._i += 1
        return r


class ReproBitmatchTest(unittest.TestCase):

    def test_repro_R_reproduces_agent_coefficients(self):
        if not EXAMPLE_DATA.exists():
            self.skipTest(f"missing {EXAMPLE_DATA}")
        if not R_SCRIPTS_DIR.exists():
            self.skipTest(f"missing {R_SCRIPTS_DIR}")

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
            _build_chat_response(content="Done."),
        ]

        agent = BregSurvAgent(
            model_endpoint="http://stub", client=_StubClient(scripted))
        response = agent.query("Fit Cox KL on ExampleData (good beta).")
        self.assertIsNone(response.error)
        self.assertEqual(response.trace.events[0].status, "ok")

        agent_beta = response.tool_results[0]["result"]["beta"]
        agent_loglik = response.tool_results[0]["result"]["likelihood"]

        # Render and run repro.R.
        with tempfile.TemporaryDirectory() as tmpdir:
            repro_path = os.path.join(tmpdir, "repro.R")
            stdout_path = os.path.join(tmpdir, "repro.stdout.txt")
            response.write_repro_r(repro_path)

            # Run repro.R, capture the JSON of the first result via a tail
            # block we append to test.
            tail = f"""
# Append: dump the first replayed result as JSON for the test to parse.
jsonlite::write_json(results[[1]], "{tmpdir}/result.json", auto_unbox = TRUE,
                     matrix = "rowmajor", null = "null", na = "null", pretty = FALSE)
"""
            with open(repro_path, "a", encoding="utf-8") as f:
                f.write(tail)

            env = dict(os.environ)
            env["SURVBREGDIV_R_SCRIPTS"] = str(R_SCRIPTS_DIR)
            rscript = find_rscript()
            with open(stdout_path, "w") as out:
                ret = subprocess.run(
                    [rscript, "--no-save", "--no-restore", "--no-init-file",
                     repro_path],
                    stdout=out, stderr=out, env=env, cwd=str(REPO_ROOT),
                    timeout=120,
                )
            with open(stdout_path) as f:
                tail_out = f.read()
            self.assertEqual(ret.returncode, 0,
                             f"repro.R failed:\n{tail_out}")

            with open(os.path.join(tmpdir, "result.json")) as f:
                repro_result = json.load(f)

        self.assertEqual(repro_result["status"], "ok")
        # Compare betas (matrix of floats) and log-likelihoods (vector).
        self.assertEqual(repro_result["beta"], agent_beta,
                         "repro.R beta differs from agent's beta")
        self.assertEqual(repro_result["likelihood"], agent_loglik,
                         "repro.R likelihood differs from agent's")


if __name__ == "__main__":
    unittest.main(verbosity=2)
