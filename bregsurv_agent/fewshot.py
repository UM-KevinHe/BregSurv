"""Retrieved few-shot examples for boundary 1 (master memory ).

A bank of worked examples ships with the agent: synthetic requests over
registry-style and single-centre column layouts, each with its verified
reading in the role-extraction schema's own shape (`examples/fewshot_bank.json`,
built by `eval/generate_corpus.py --bank` and `eval/merge_bank.py`). At the
role-extraction call the harness retrieves the k bank items most similar to
the analyst's sentence and places them before the request as examples.

What "similar" means here. BM25 -- the classic lexical scoring formula -- over
COLUMN-MASKED text: every column name of the analyst's file, and every column
name of each bank item's own layout, is replaced by one placeholder, and every
digit by another, before tokenising. Similarity is therefore about phrasing
("we followed everyone until ...", "adjust for", "published coefficients"),
never about names, which a real analyst's file never shares with the bank.
The scoring is computed by this module; the model sees only the k matches.

What this does NOT change. The examples shape what the model PROPOSES and
nothing of what is fitted: the proposal still passes the backing filter (an
example's column name is never one the analyst wrote, so it can never become
`quoted`), the gate and the configuration hash. Retrieval is deterministic,
needs no network and no second model, and every call records which examples
it showed (`few_shot` on the call record) so a run can be audited.

Evaluation rule: with `exclude_template=` set to the test item's
template suffix, bank items of the same template are never retrieved, so the
bank cannot hold the same case in other words.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import textmatch

BANK_PATH = Path(__file__).resolve().parent / "examples" / "fewshot_bank.json"
DEFAULT_K = 5
_TOKEN = re.compile(r"[a-z]+")
_K1, _B = 1.5, 0.75


# ------------------------------------------------------------------ switches
def enabled() -> bool:
    """`BREGSURV_FEWSHOT` = on | off | <k>. ON unless set to off.

    The default was decided by the measurement, not assumed: unstated roles left open RAW rose from 62 % to 85 % (Qwen2.5-7B)
    and 71 % to 84 % (Qwen3-8B), whole items correct raw from 49 % to 78 % and
    65 % to 77 %, named roles quoted correctly after the filter from 93 % to
    99.9 % and 98 % to 99 %; after the filter the two models meet at 98 %
    whole-item correct. Median prompt 883 -> 2390 tokens, latency unchanged.
    The pre-agreed rule (>= 5 points on both raw rates without lowering
    named-correct after the filter) was met by a wide margin on both models,
    so the examples are on in the product; `off` remains the ablation arm."""
    v = os.environ.get("BREGSURV_FEWSHOT", "").strip().lower()
    return v not in ("off", "0", "false", "no")


def k_from_env() -> int:
    v = os.environ.get("BREGSURV_FEWSHOT", "").strip().lower()
    return int(v) if v.isdigit() and int(v) > 0 else DEFAULT_K


# ---------------------------------------------------------------- the text
def mask(text: str, columns: Iterable[str]) -> str:
    """Replace every column name (in the three accepted spellings) by one
    placeholder and every digit run by another, so BM25 sees phrasing only."""
    low = text.lower()
    names = sorted({str(c) for c in columns}, key=len, reverse=True)
    for n in names:
        for form in textmatch.variants(n):
            low = re.sub(rf"(?<![a-z0-9_]){re.escape(form.lower())}(?![a-z0-9_])",
                         " colname ", low)
    low = re.sub(r"\d+", " num ", low)
    return low


def tokens(text: str) -> List[str]:
    return _TOKEN.findall(text)


# ----------------------------------------------------------------- the bank
class Bank:
    """The example bank with its BM25 index, built once per process."""

    def __init__(self, path: Path = BANK_PATH):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.path = str(path)
        self.sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.items: List[Dict[str, Any]] = list(raw.get("items", []))
        self._profiles = self._load_profiles()
        self.docs: List[List[str]] = []
        for it in self.items:
            cols = self._profiles.get(it["profile"], {}).get("columns", [])
            self.docs.append(tokens(mask(it["request"], cols)))
        self.n = len(self.docs)
        self.avgdl = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - n_t + 0.5) / (n_t + 0.5)) for t, n_t in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    @staticmethod
    def _load_profiles() -> Dict[str, Dict[str, Any]]:
        """The bank profiles' column lists, for masking. The eval package
        holds them; a bank shipped without it still works (no masking of the
        example's own names, which only weakens retrieval)."""
        try:
            import sys
            eval_dir = Path(__file__).resolve().parent.parent / "eval"
            if str(eval_dir) not in sys.path:
                sys.path.insert(0, str(eval_dir))
            from bank_profiles import BANK_PROFILES  # type: ignore
            return dict(BANK_PROFILES)
        except Exception:
            return {}

    def columns_of(self, item: Dict[str, Any]) -> List[str]:
        return list(self._profiles.get(item["profile"], {}).get("columns", []))

    def score(self, query: List[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        s = 0.0
        for t in query:
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0.0) * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * dl / self.avgdl))
        return s

    def retrieve(self, request: str, columns: Iterable[str], k: int = DEFAULT_K,
                 exclude_template: Optional[str] = None,
                 exclude_ids: Iterable[str] = ()) -> List[Dict[str, Any]]:
        """The k most similar bank items, at most one per template so the
        examples are diverse. `exclude_template` is the evaluation rule: a
        template suffix (`stated.reference.perturbation`) whose items are
        skipped; `exclude_ids` skips items by id."""
        cols = [str(c) for c in columns]
        q = tokens(mask(request, cols))
        if not q or not self.n:
            return []
        skip_ids = set(exclude_ids)
        scored: List[Tuple[float, int]] = []
        for i, it in enumerate(self.items):
            if it["id"] in skip_ids:
                continue
            if exclude_template and template_suffix(it["template_id"]) == exclude_template:
                continue
            # an example must never contain a name of the analyst's file, even
            # as an ordinary word ("patients who died" beside a `died` column):
            # the property "no example names a column of your file" is then
            # structural, not statistical
            if cols and textmatch.names_mentioned(it["request"], cols):
                continue
            s = self.score(q, i)
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], self.items[x[1]]["id"]))
        out, seen = [], set()
        for s, i in scored:
            it = self.items[i]
            if it["template_id"] in seen:
                continue
            seen.add(it["template_id"])
            out.append(dict(it, _score=round(s, 4)))
            if len(out) >= k:
                break
        return out


def template_suffix(template_id: str) -> str:
    """`profile.stated.reference.perturbation` -> `stated.reference.perturbation`."""
    parts = str(template_id).split(".")
    return ".".join(parts[1:]) if len(parts) > 1 else str(template_id)


@lru_cache(maxsize=4)
def bank(path: Optional[str] = None) -> Bank:
    return Bank(Path(path) if path else BANK_PATH)


# ------------------------------------------------------------ the prompt part
# the examples carry no stratum; an example is shown with the schema's
# every field, so stratum_column renders as null (the bank's cohorts have none)
_ORDER = ("reasoning", "time_column", "time_evidence", "event_column", "event_evidence",
          "event_value", "event_value_evidence", "stratum_column", "covariate_columns")


def render(examples: List[Dict[str, Any]], b: Optional[Bank] = None) -> str:
    """The block placed before the analyst's request: for each example its
    file's columns, the request, and the answer in the schema's own shape."""
    if not examples:
        return ""
    b = b or bank()
    out = ["Worked examples. Each shows a different file, a request about it, and "
           "the correct reading. They show the format and the rule; none of their "
           "column names is in the file above, so never copy a name from them.", ""]
    for n, ex in enumerate(examples, 1):
        ans = {k: ex["example"].get(k) for k in _ORDER}
        out.append(f"Example {n}")
        out.append("Columns in that file: " + ", ".join(b.columns_of(ex)))
        out.append("The analyst wrote: " + ex["request"].strip())
        out.append("Correct reading: " + json.dumps(ans, ensure_ascii=False))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def record(examples: List[Dict[str, Any]], k: int, b: Optional[Bank] = None,
           exclude_template: Optional[str] = None) -> Dict[str, Any]:
    """What the call record carries, so a run says which examples it showed."""
    b = b or bank()
    return {"k": k, "n_shown": len(examples),
            "ids": [e["id"] for e in examples],
            "scores": [e.get("_score") for e in examples],
            "bank_sha256": b.sha256[:16], "bank_items": b.n,
            "exclude_template": exclude_template}


def describe() -> Dict[str, Any]:
    """For provenance: whether few-shot was on and which bank."""
    if not enabled():
        return {"enabled": False, "switch": os.environ.get("BREGSURV_FEWSHOT", "")}
    try:
        b = bank()
        return {"enabled": True, "k": k_from_env(), "bank_items": b.n,
                "bank_sha256": b.sha256[:16], "path": b.path}
    except Exception as exc:  # a missing bank never breaks a run
        return {"enabled": True, "error": f"{type(exc).__name__}: {exc}"}
