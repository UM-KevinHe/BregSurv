"""Component 8 -- knowledge the harness shows on request, retrieved without a model.

The agent's model sees knowledge in exactly three places, and all three are
already progressive disclosure: the policy of the one boundary it is acting
at (component 2), the column facts of the one file in front of it (M5, the
profile), and the catalogue listing when a published model is being named
(component 4). What remained was the analyst's own questions about the METHOD
-- "how is the amount decided?", "why cross-validation?", "what does it not
do?" -- which the harness answered with one fixed paragraph. This module
answers them from a small, versioned, hand-written file of digit-free notes,
`knowledge/method_notes.md`, selected by keyword over the analyst's words.

No model writes, selects or paraphrases a note: retrieval is keyword overlap,
deterministic, and the text shown is the text in the file. RAG over the
estimator library was rejected in the master memory (section ) and is not
what this is; the library is never in the model's reach.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

NOTES_PATH = Path(__file__).resolve().parent / "knowledge" / "method_notes.md"


@dataclass(frozen=True)
class Note:
    id: str
    keywords: tuple
    body: str


@lru_cache(maxsize=None)
def notes() -> List[Note]:
    text = NOTES_PATH.read_text(encoding="utf-8")
    out: List[Note] = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        lines = block.strip().split("\n")
        nid = lines[0].strip()
        kw_line = next((l for l in lines[1:] if l.startswith("keywords:")), "keywords:")
        kws = tuple(k.strip().lower() for k in kw_line[len("keywords:"):].split(",")
                    if k.strip())
        body = "\n".join(l for l in lines[1:] if not l.startswith("keywords:")).strip()
        out.append(Note(id=nid, keywords=kws, body=body))
    return out


def _hits(text: str, note: Note) -> int:
    low = " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()) + " "
    return sum(1 for k in note.keywords
               if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", low))


def retrieve(text: str, limit: int = 3) -> List[Note]:
    """The notes whose keywords the text mentions, most hits first."""
    scored = [(_hits(text, n), i, n) for i, n in enumerate(notes())]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [n for _, _, n in scored[:limit]]


def answer_method(text: str, fallback: str) -> str:
    """What the harness says to a question about the method: the matching
    notes, verbatim, or the fixed fallback when nothing matches."""
    found = retrieve(text)
    if not found:
        return fallback
    parts = [f"**{n.id.replace('-', ' ').capitalize()}.** {n.body}" for n in found]
    return "\n\n".join(parts) + ("\n\n<small>From the method notes; no language "
                                 "model wrote or chose them.</small>")


def describe() -> Dict[str, object]:
    import hashlib
    return {"file": NOTES_PATH.name, "n_notes": len(notes()),
            "sha256": "sha256:" + hashlib.sha256(
                NOTES_PATH.read_bytes()).hexdigest()[:16]}
