"""Hybrid retrieval (V4, 2026-10-05): BM25 order unchanged under bm25 mode; hybrid / rerank run with the
real models when present; stale or missing vectors fall back to BM25 and the record says so."""
import os, sys, json, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bregsurv_agent import fewshot, intent_examples, retrieval  # noqa: E402
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print("PASS", name)
    else: fail += 1; print("FAIL", name, detail)

# A. rrf
r = retrieval.rrf([[1, 2, 3], [3, 1, 4]])
check("A1 rrf puts the item ranked high in both first", r[0][1] in (1, 3) and {i for _, i in r} == {1, 2, 3, 4})

# B. bm25 mode reproduces the pre-hybrid BM25 order (fewshot: one per template, score>0)
os.environ["BREGSURV_RETRIEVAL"] = "bm25"
fb = fewshot.Bank()
req = "Follow-up is in months_since_tx and graft_loss marks the event; adjust for donor and recipient characteristics."
got = [e["id"] for e in fb.retrieve(req, ["months_since_tx", "graft_loss"], k=5)]
# reference: the old algorithm, recomputed here
q = fewshot.tokens(fewshot.mask(req, ["months_since_tx", "graft_loss"]))
sc = sorted(((fb.score(q, i), i) for i in range(fb.n) if fb.score(q, i) > 0), key=lambda x: (-x[0], fb.items[x[1]]["id"]))
ref, seen = [], set()
for s, i in sc:
    t = fb.items[i]["template_id"]
    if t in seen: continue
    seen.add(t); ref.append(fb.items[i]["id"])
    if len(ref) >= 5: break
check("B1 fewshot bm25 order identical to the old algorithm", got == ref, f"{got} vs {ref}")
check("B2 record says bm25", fb.last_retrieval.get("used") == "bm25")
ib = intent_examples.Bank()
st = "State: cohort loaded: yes | external information: none | declaration: none | result: none"
got_i = [e["id"] for e in ib.retrieve("please fit the model and report the c index", st, [], 5)]
check("B3 intent bm25 returns 5", len(got_i) == 5)

# C. hybrid / rerank with the real models
have = (retrieval.MODELS_DIR / retrieval.DEFAULT_EMBED).is_dir()
if not have:
    print("SKIP C: models absent")
else:
    tmp = Path(tempfile.mkdtemp())
    texts = ["score every fitted model on the patients we held out",
             "plot the survival curves by sex",
             "which columns are the predictors",
             "repeat the random train test split two hundred times",
             "how well do the models do on the separate validation file"]
    bp = tmp / "toy.json"; bp.write_text("{}")
    retrieval.build_vectors(bp, texts)
    for m in ("hybrid", "rerank"):
        os.environ["BREGSURV_RETRIEVAL"] = m
        t0 = time.time()
        order, rec = retrieval.rank(bp, texts, "evaluate the fitted models on our test file",
                                    {i: 0.0 for i in range(5)}, list(range(5)))
        check(f"C {m} used", rec.get("used") == m, json.dumps(rec))
        check(f"C {m} a test-file item ranks first with zero BM25 overlap", order[0] in (0, 4), f"{order}")
        check(f"C {m} the repeated-split item is not first", order[0] != 3, f"{order}")
        print("   ", m, "order", order, "seconds", round(time.time() - t0, 2))
    # stale vectors -> fallback
    order, rec = retrieval.rank(bp, texts + ["one more"], "x", {i: 1.0 for i in range(6)}, list(range(6)))
    check("C stale vectors fall back to bm25 and say so", rec.get("used") == "bm25" and "stale" in rec.get("fallback", ""), json.dumps(rec))
    # BGE pair
    os.environ["BREGSURV_EMBED_MODEL"] = "bge-base-en-v1.5"; os.environ["BREGSURV_RERANK_MODEL"] = "bge-reranker-base"
    retrieval.build_vectors(bp, texts, "bge-base-en-v1.5")
    order, rec = retrieval.rank(bp, texts, "evaluate the fitted models on our test file", {i: 0.0 for i in range(5)}, list(range(5)))
    check("C bge rerank used", rec.get("used") == "rerank" and rec.get("rerank_model") == "bge-reranker-base", json.dumps(rec))
    print("    bge order", order)
    os.environ.pop("BREGSURV_EMBED_MODEL"); os.environ.pop("BREGSURV_RERANK_MODEL")
# D. missing model -> fallback
os.environ["BREGSURV_RETRIEVAL"] = "rerank"; os.environ["BREGSURV_EMBED_MODEL"] = "no-such-model"
order, rec = retrieval.rank(Path("/nonexistent.json"), ["a", "b"], "a", {0: 1.0, 1: 0.5}, [0, 1])
check("D missing model falls back to the BM25 order", order == [0, 1] and rec.get("used") == "bm25", json.dumps(rec))
print(f"RESULT: {ok}/{ok + fail} passed")
sys.exit(1 if fail else 0)
