"""Component 2 -- the instructions each boundary runs under, as files.

Every place the language model acts has exactly one policy: a text file in
`bregsurv_agent/policies/`, sent verbatim as the system prompt of that one
constrained call. Nothing the model must know lives anywhere else -- a JSON
Schema `description` reaches the decoding grammar and is never shown to the
model (measured 2026-08-20: a required `reasoning` field whose purpose was
stated only in its description came back as the literal string "null" on 58%
of calls), so the purpose of every field is stated in the policy.

Why files rather than string constants: the text is what the model is
governed by, so it should be readable and reviewable without reading Python,
diffable on its own, and hashed into every run's provenance
(`provenance.model.policies`), so that a run records not only which model
answered but which instructions it answered under.

Every policy has the same five headings, in this order, and `mcp/test_policy.py`
asserts them:

    # <title>
    ## What you are doing         one sentence: typing / quoting / pointing / writing
    ## What the system is          only what this boundary needs to know
    ## Before you decide           what the `reasoning` field is FOR
    ## The fields                  every field, with its rule; null scoped explicitly
    ## What you must not do        the closed list

The names are the schema names the calls are logged under, so a call record
and its policy can be joined: intent, role_extraction, external_roles,
report_prose, explain, published_model (component 4).
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Dict

POLICY_DIR = Path(__file__).resolve().parent / "policies"

NAMES = ("intent", "role_extraction", "external_roles", "report_prose", "explain",
         "published_model", "ask", "plan_steps", "refusal",
         "analysis_plan", "next_step",          # V4: the planner's two acts
         "split_request")                       # V4: evaluation by repeated splits, on request

HEADINGS = ("## What you are doing", "## What the system is",
            "## Before you decide", "## The fields", "## What you must not do")


def path(name: str) -> Path:
    if name not in NAMES:
        raise KeyError(f"no policy named {name!r}; known: {NAMES}")
    return POLICY_DIR / f"{name}.md"


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """The policy text, exactly as sent to the model."""
    text = path(name).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"policy {name} is empty")
    return text


def sha256(name: str) -> str:
    return "sha256:" + hashlib.sha256(load(name).encode("utf-8")).hexdigest()[:16]


def describe() -> Dict[str, Dict[str, object]]:
    """For provenance: which instructions every boundary answered under."""
    return {n: {"sha256": sha256(n), "chars": len(load(n)),
                "file": str(path(n).relative_to(POLICY_DIR.parent.parent))}
            for n in NAMES}


def sections(name: str) -> Dict[str, str]:
    """The five sections, keyed by heading, for tests and for display."""
    text = load(name)
    out: Dict[str, str] = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current = line.strip()
            out[current] = ""
        elif current is not None:
            out[current] += line + "\n"
    return out
