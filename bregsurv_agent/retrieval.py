"""Hybrid retrieval for the example banks, V4.

Every example bank (role-reading examples `fewshot.py`, intent examples `intent_examples.py`, and the
banks added after them) ranks its items by BM25 over column-masked text. BM25 matches words; two
requests that mean the same thing in different words ("score every model on my test file" and "how do
the fitted models do on the held-out patients") share few of them. This module adds a second, semantic
ranking and fuses the two:

    BM25 top-N  +  dense top-N (dot product of normalised embeddings)
        -> reciprocal rank fusion (k = 60)
        -> cross-encoder rerank of the fused pool
        -> the bank keeps its own filters (one item per template, state agreement) and takes the top k

Only raw bank text reaches the language model; the vectors are an index. The bank's embeddings are
computed once and stored beside the bank as `<bank>.<model>.npy` with a JSON header holding the hash of
the texts, so a changed bank is never searched with stale vectors. The query embedding and the rerank are
computed at the call.

`BREGSURV_RETRIEVAL` = bm25 | hybrid | rerank (hybrid + cross-encoder; the default when the models are
present). `BREGSURV_EMBED_MODEL`, `BREGSURV_RERANK_MODEL` name a model directory under
`BREGSURV_RETRIEVAL_MODELS`. Nothing here may stop an analysis: a missing model, a missing vector file or
any error falls back to the bank's BM25 order, and the record says so.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MODELS_DIR = Path(os.environ.get("BREGSURV_RETRIEVAL_MODELS",
                                 "/models/retrieval"))
DEFAULT_EMBED = "Qwen3-Embedding-0.6B"
DEFAULT_RERANK = "Qwen3-Reranker-0.6B"
POOL = 20          # candidates taken from each ranking, and the size of the reranked pool
RRF_K = 60

# the task the embedding and rerank models are told they serve
_TASK = ("Given an analyst's request to a survival-analysis assistant, retrieve worked examples whose "
         "requests ask for the same kind of thing in similar ways")

_lock = threading.Lock()
_models: Dict[str, Any] = {}


def device() -> str:
    """Where the two retrieval models run. `BREGSURV_RETRIEVAL_DEVICE` = cpu (the default, as
    evaluated) or cuda (half precision, beside the language model; the hosted demo uses it)."""
    v = (os.environ.get("BREGSURV_RETRIEVAL_DEVICE") or "cpu").strip().lower()
    if v.startswith("cuda"):
        try:
            import torch
            if torch.cuda.is_available():
                return v
        except Exception:
            pass
    return "cpu"


def _dtype(torch):
    return torch.float16 if device() != "cpu" else torch.float32


def warm() -> None:
    """Load both models now, so the first message does not wait for them. Never raises."""
    try:
        e = _get("embed", embed_name())
        e.encode(["warm up"], query=True)          # the first forward pass initialises the kernels
        if mode() == "rerank":
            _get("rerank", rerank_name()).score("warm up", ["warm up"])
    except Exception:
        pass


def mode() -> str:
    v = (os.environ.get("BREGSURV_RETRIEVAL") or "rerank").strip().lower()
    return v if v in ("bm25", "hybrid", "rerank") else "rerank"


def embed_name() -> str:
    return os.environ.get("BREGSURV_EMBED_MODEL") or DEFAULT_EMBED


def rerank_name() -> str:
    return os.environ.get("BREGSURV_RERANK_MODEL") or DEFAULT_RERANK


def _is_qwen(name: str) -> bool:
    return name.lower().startswith("qwen")


def texts_sha(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8")); h.update(b"\x00")
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ encoders
class _Embedder:
    def __init__(self, name: str):
        import torch
        from transformers import AutoModel, AutoTokenizer
        path = MODELS_DIR / name
        self.name, self.qwen = name, _is_qwen(name)
        self.tok = AutoTokenizer.from_pretrained(str(path), padding_side="left" if self.qwen else "right")
        self.dev = device()
        self.model = AutoModel.from_pretrained(str(path), dtype=_dtype(torch)).to(self.dev).eval()
        self.torch = torch

    def encode(self, texts: Sequence[str], query: bool = False, batch: int = 16):
        import numpy as np
        torch = self.torch
        if self.qwen and query:
            texts = [f"Instruct: {_TASK}\nQuery:{t}" for t in texts]
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), batch):
                enc = self.tok(list(texts[i:i + batch]), padding=True, truncation=True,
                               max_length=512, return_tensors="pt").to(self.dev)
                h = self.model(**enc).last_hidden_state.float()
                if self.qwen:          # last-token pooling (left padding)
                    v = h[:, -1]
                else:                  # BGE: the [CLS] vector
                    v = h[:, 0]
                v = torch.nn.functional.normalize(v, p=2, dim=1)
                out.append(v.cpu().numpy().astype("float32"))
        return np.concatenate(out, axis=0) if out else np.zeros((0, 1), dtype="float32")


class _Reranker:
    def __init__(self, name: str):
        import torch
        from transformers import (AutoModelForCausalLM, AutoModelForSequenceClassification,
                                  AutoTokenizer)
        path = MODELS_DIR / name
        self.name, self.qwen, self.torch = name, _is_qwen(name), torch
        self.dev = device()
        if self.qwen:
            self.tok = AutoTokenizer.from_pretrained(str(path), padding_side="left")
            self.model = AutoModelForCausalLM.from_pretrained(str(path), dtype=_dtype(torch)).to(self.dev).eval()
            self.yes = self.tok.convert_tokens_to_ids("yes")
            self.no = self.tok.convert_tokens_to_ids("no")
            self.prefix = ("<|im_start|>system\nJudge whether the Document meets the requirements based on "
                           "the Query and the Instruct provided. Note that the answer can only be \"yes\" "
                           "or \"no\".<|im_end|>\n<|im_start|>user\n")
            self.suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        else:
            self.tok = AutoTokenizer.from_pretrained(str(path))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(path)).to(self.dev).eval()

    def score(self, query: str, docs: Sequence[str], batch: int = 10) -> List[float]:
        torch = self.torch
        out: List[float] = []
        with torch.no_grad():
            for i in range(0, len(docs), batch):
                chunk = docs[i:i + batch]
                if self.qwen:
                    pairs = [f"{self.prefix}<Instruct>: {_TASK}\n<Query>: {query}\n<Document>: {d}"
                             f"{self.suffix}" for d in chunk]
                    enc = self.tok(pairs, padding=True, truncation=True, max_length=1024,
                                   return_tensors="pt").to(self.dev)
                    logits = self.model(**enc).logits[:, -1, :].float()
                    two = torch.stack([logits[:, self.no], logits[:, self.yes]], dim=1)
                    out.extend(torch.log_softmax(two, dim=1)[:, 1].exp().tolist())
                else:
                    enc = self.tok([query] * len(chunk), list(chunk), padding=True, truncation=True,
                                   max_length=512, return_tensors="pt").to(self.dev)
                    out.extend(self.model(**enc).logits.view(-1).float().tolist())
        return out


def _get(kind: str, name: str):
    key = f"{kind}:{name}"
    with _lock:
        if key not in _models:
            if not (MODELS_DIR / name).is_dir():
                raise FileNotFoundError(f"retrieval model {name} not found under {MODELS_DIR}")
            _models[key] = _Embedder(name) if kind == "embed" else _Reranker(name)
        return _models[key]


# ------------------------------------------------------------- bank vectors
def vector_path(bank_path: Path, name: str) -> Path:
    return Path(str(bank_path) + f".{name}.npy")


def build_vectors(bank_path: Path, texts: Sequence[str], name: Optional[str] = None) -> Path:
    """Embed a bank's (masked) texts and store them beside the bank."""
    import numpy as np
    name = name or embed_name()
    vec = _get("embed", name).encode(texts, query=False)
    p = vector_path(bank_path, name)
    np.save(p, vec)
    Path(str(p) + ".json").write_text(json.dumps(
        {"model": name, "n": len(texts), "dim": int(vec.shape[1]), "texts_sha": texts_sha(texts)}))
    return p


_vec_cache: Dict[str, Any] = {}


def load_vectors(bank_path: Path, texts: Sequence[str], name: Optional[str] = None):
    import numpy as np
    name = name or embed_name()
    p = vector_path(bank_path, name)
    key = f"{p}:{texts_sha(texts)}"
    if key in _vec_cache:
        return _vec_cache[key]
    head = Path(str(p) + ".json")
    if not p.exists() or not head.exists():
        raise FileNotFoundError(f"no vectors {p.name}")
    meta = json.loads(head.read_text())
    if meta.get("texts_sha") != texts_sha(texts):
        raise ValueError(f"vectors {p.name} are stale (bank texts changed)")
    v = np.load(p)
    _vec_cache[key] = v
    return v


# ------------------------------------------------------------------ fusion
def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> List[Tuple[float, int]]:
    """Reciprocal rank fusion of several best-first index lists."""
    s: Dict[int, float] = {}
    for r in rankings:
        for pos, i in enumerate(r):
            s[i] = s.get(i, 0.0) + 1.0 / (k + pos + 1)
    return sorted(((v, i) for i, v in s.items()), key=lambda x: (-x[0], x[1]))


def rank(bank_path: Path, texts: Sequence[str], query: str, bm25: Dict[int, float],
         candidates: Sequence[int], pool: int = POOL) -> Tuple[List[int], Dict[str, Any]]:
    """Best-first order of `candidates` (bank indices already filtered by the bank's own rules).

    `texts` are the bank's masked texts in bank order, `query` the masked query, `bm25` the bank's BM25
    score of each candidate. Returns (order, record). Under `bm25` mode, or on any failure, the order is
    BM25's and the record names the reason."""
    t0 = time.time()
    m = mode()
    bm_order = sorted(candidates, key=lambda i: (-bm25.get(i, 0.0), i))
    rec: Dict[str, Any] = {"mode": m, "pool": pool}
    if m == "bm25" or not candidates:
        rec["used"] = "bm25"
        return bm_order, rec
    try:
        import numpy as np
        V = load_vectors(bank_path, texts)
        q = _get("embed", embed_name()).encode([query], query=True)[0]
        cand = np.asarray(list(candidates))
        sims = V[cand] @ q
        dense_order = [int(cand[j]) for j in np.argsort(-sims, kind="stable")[:pool]]
        fused = rrf([[i for i in bm_order if bm25.get(i, 0.0) > 0][:pool], dense_order])
        pool_idx = [i for _, i in fused][:pool]
        rec.update(embed_model=embed_name(), dense_top=dense_order[:5])
        if m == "rerank":
            sc = _get("rerank", rerank_name()).score(query, [texts[i] for i in pool_idx])
            order = [i for _, i in sorted(zip(sc, pool_idx), key=lambda x: (-x[0], x[1]))]
            rec.update(rerank_model=rerank_name())
        else:
            order = pool_idx
        # the reranked pool first, then BM25's tail so a bank filter never runs dry
        seen = set(order)
        order = order + [i for i in bm_order if i not in seen]
        rec["used"] = m
        rec["seconds"] = round(time.time() - t0, 3)
        return order, rec
    except Exception as exc:  # noqa: BLE001 -- retrieval must never stop the analysis
        rec.update(used="bm25", fallback=f"{type(exc).__name__}: {str(exc)[:200]}")
        return bm_order, rec


def describe() -> Dict[str, Any]:
    return {"mode": mode(), "embed_model": embed_name(), "rerank_model": rerank_name(),
            "pool": POOL, "rrf_k": RRF_K}
