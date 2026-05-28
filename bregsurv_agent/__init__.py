"""BregSurv local Qwen agent (bregsurv_agent).

Thin Python coordination layer over the BregSurv R package + an
OpenAI-compatible LLM endpoint (vLLM / Together / OpenRouter). Mirrors
``mcp/server.py``'s tool surface without depending on the ``mcp``
library; safe to ship to HF Space, Docker, or any Python 3.8+ host.

Typical usage::

    from bregsurv_agent import BregSurvAgent

    agent = BregSurvAgent(
        model_endpoint="http://localhost:8000/v1",
        model_name="qwen2.5-7b-awq",
        api_key="EMPTY",  # vLLM ignores key value
    )
    response = agent.query(
        "Fit Cox KL on ExampleData_lowdim with eta=0.5",
        data_path="/path/to/ExampleData_lowdim.rda",
    )
    print(response.text)
    response.trace.save("trace.json")
    response.write_repro_r("repro.R")
"""
from __future__ import annotations

from .agent import BregSurvAgent, AgentResponse
from .trace import AgentTrace, TraceEvent
from .tools import TOOL_REGISTRY, load_schemas, dispatch

__all__ = [
    "BregSurvAgent",
    "AgentResponse",
    "AgentTrace",
    "TraceEvent",
    "TOOL_REGISTRY",
    "load_schemas",
    "dispatch",
]

__version__ = "0.1.0"
