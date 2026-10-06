"""Retrieved worked examples for the intent-typing call (M1), V4.

The same mechanism as the role-reading examples (`fewshot.py`): a bank of synthetic analyst messages, each
with its correct typing in the intent schema's own shape (`examples/intent_bank.json`, built by
`/home/ybshao/jobs/v4/intent_bank/merge_bank.py` and checked there), and at the call the harness retrieves
the k items most similar to the analyst's message and places them before it.

Similarity is BM25 over column-masked text (the analyst's column names and the bank's own vocabulary
replaced by one placeholder, digits by another), so it is about phrasing, never about names. Items are
drawn first from the bank entries whose state agrees with the session on whether a result exists, since
that fact changes the correct typing of the same words (a question about results before anything was
run). The bank's messages, its column vocabulary and its wording are disjoint from every evaluation set
(the 120 labelled intents, the rubric tasks and the hand-written requests); the merge script checks it.

What this does NOT change: the typing is still validated by `intent.validate` (evidence must be a
substring of the analyst's own message, so an example's words can never become evidence), and the
dispatch that follows is unchanged. `BREGSURV_INTENT_EXAMPLES` = on | off | <k>; on by default when the
bank exists.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import fewshot, retrieval

BANK_PATH = Path(os.environ["BREGSURV_INTENT_BANK"]) if os.environ.get("BREGSURV_INTENT_BANK") else Path(__file__).resolve().parent / "examples" / "intent_bank.json"
DEFAULT_K = 5
_K1, _B = 1.5, 0.75


def k_from_env() -> int:
    v = (os.environ.get("BREGSURV_INTENT_EXAMPLES") or "on").strip().lower()
    if v in ("off", "0", "no", "false"):
        return 0
    if v.isdigit():
        return int(v)
    return DEFAULT_K


def _has_result(state: str) -> bool:
    return "result: present" in (state or "")


class Bank:
    def __init__(self, path: Path = BANK_PATH):
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()[:16]
        data = json.loads(raw)
        self.items: List[Dict[str, Any]] = data["items"]
        self.vocab: List[str] = list(data.get("vocabulary") or [])
        self.path = path
        self.masked = [fewshot.mask(it["message"], self.vocab) for it in self.items]
        self.docs = [fewshot.tokens(t) for t in self.masked]
        self.last_retrieval: Dict[str, Any] = {}
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def score(self, query: List[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        s = 0.0
        for t in query:
            f = tf.get(t, 0)
            if f:
                s += self.idf.get(t, 0.0) * f * (_K1 + 1) / (f + _K1 * (1 - _B + _B * dl / self.avgdl))
        return s

    def retrieve(self, message: str, state: str, columns: Iterable[str] = (), k: int = DEFAULT_K
                 ) -> List[Dict[str, Any]]:
        if k <= 0:
            return []
        qtext = fewshot.mask(message, list(columns) + self.vocab)
        q = fewshot.tokens(qtext)
        want = _has_result(state)
        cand = [i for i in range(len(self.items)) if _has_result(self.items[i]["state"]) == want]
        bm = {i: self.score(q, i) for i in cand}
        # V4: hybrid order (retrieval.py); BM25 alone under BREGSURV_RETRIEVAL=bm25
        order, self.last_retrieval = retrieval.rank(Path(self.path), self.masked, qtext, bm, cand)
        out = []
        for i in order[:k]:
            it = dict(self.items[i]); it["_score"] = round(bm.get(i, 0.0), 4)
            out.append(it)
        return out


@lru_cache(maxsize=1)
def bank() -> Optional[Bank]:
    return Bank() if BANK_PATH.exists() else None


def render(examples: List[Dict[str, Any]]) -> str:
    if not examples:
        return ""
    parts = ["Worked examples of typing other analysts' messages (different cohorts; their words are never "
             "evidence for this message):"]
    for j, it in enumerate(examples, 1):
        # the schema's current fields, in its order (V4 2026-10-06 added km_by after the bank was built)
        ans = {"reasoning": it["reasoning"],
               "intents": [{**i, "km_by": i.get("km_by")} for i in it["intents"]]}
        parts.append(f"Example {j}\n{it['state']}\nThe analyst wrote:\n{it['message']}\n"
                     f"Correct typing:\n{json.dumps(ans, ensure_ascii=False)}")
    return "\n\n".join(parts) + "\n\nNow type this message.\n\n"


def record(examples: List[Dict[str, Any]], k: int) -> Dict[str, Any]:
    b = bank()
    return {"k": k, "n_shown": len(examples), "ids": [e["id"] for e in examples],
            "scores": [e.get("_score") for e in examples],
            "bank_sha256": b.sha256 if b else None, "bank_items": len(b.items) if b else 0,
            "retrieval": dict(getattr(b, "last_retrieval", {}) or {}) if b else {}}


def for_message(message: str, state: str, columns: Iterable[str] = ()):
    """(prompt prefix, record) for one intent call; ("", None) when off or the bank is absent."""
    k = k_from_env()
    b = bank()
    if not k or b is None:
        return "", None
    ex = b.retrieve(message, state, columns, k)
    return render(ex), record(ex, k)
