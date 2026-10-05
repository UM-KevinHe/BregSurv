"""Evaluation by repeated random train/test splits, on request (V4, decided 2026-10-03).

The analyst asks in words -- "evaluate the methods on 500 random 70/30 splits and show box plots
of the C-index" -- and the agent does all of it. This does NOT reverse the rulings that the agent's
own analysis draws no outer split and its report carries no figure: those govern the
default analysis, and this is an evaluation the analyst asked for, delivered as a SEPARATE set of
files beside the report, never inside it.

Who does what:

* the model reads the request, once (`read_request`, policy `split_request`): how many splits,
  how large the test part, which measures, whether a figure is wanted. `validate` keeps a number
  only when it occurs in the analyst's message inside the evidence span the model quoted, and the
  span is in the message; anything else is dropped and recorded. When the message states no
  number of splits, the model chooses one with the cost in view (the estimated seconds per split,
  how many run at a time, the cap), and the record says the number was CHOSEN, not stated;
* the harness does everything else: `draw_splits.R` draws event-stratified splits from a recorded
  seed with the Mersenne-Twister kind; every split's training part is analysed by
  `run_candidates.R` exactly as the cohort was -- the same verified declaration, the same release,
  the same V4 plan if one was made (else the admissible set), every member tuned by its own inner
  cross-validation -- and every member, and the member cross-validation selects, is scored on the
  split's test part by the dispatcher's own held-out block (C-index, loss, IBS, tdAUC). No new
  estimation code. Splits run in parallel, one R process per core, each pinned to one thread;
* when the analyst supplied a test file, the cohort is not split: each replicate keeps a share of
  the TRAINING rows (70% unless the analyst says otherwise) and is scored on the analyst's file;
* outputs, all harness-rendered: a table (mean +- sd of every requested measure per member, and on
  how many splits cross-validation selected it) as CSV and Markdown, box plots (PDF and PNG; base R
  through `plot_splits.R`), a JSON record (seed, RNG kind, split membership, settings, every
  per-split per-member number) and `replay_splits.R`, which redraws the splits from the seed,
  refits them and stops unless the recorded numbers come back.

Cox-family rows only: a discrete-time analysis is scored by a grouped-time likelihood and a
matched design has no fixed-coefficient held-out loss in the library, so both are declined in
plain words (`declined_reason`).
"""
from __future__ import annotations

import csv
import dataclasses
import json
import math
import multiprocessing as mp
import os
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import boundary, policy, textmatch

MEASURES = ("cindex", "loss", "ibs", "tdauc")
MEASURE_LABEL = {"cindex": "C-index", "loss": "test loss", "ibs": "IBS", "tdauc": "tdAUC"}
_DIGITS = {"cindex": 3, "loss": 4, "ibs": 4, "tdauc": 3}

MAX_SPLITS = 1000          # the most splits one request runs
MIN_CHOSEN = 10            # a number the model chooses must be at least this
DEFAULT_SPLITS = 100       # when the model chose nothing usable either
DEFAULT_TEST_FRACTION = 0.3
DEFAULT_KEEP_FRACTION = 0.7
SPLIT_SEED = 20261004      # the outer draw; the inner CV keeps the analysis's own seed
SELECTED_KEY = "cv_selected"
SELECTED_LABEL = "CV-selected (the member CV chose on each split)"

PLACE_TRAIN = "__BREGSURV_SPLIT_TRAIN__"
PLACE_TEST = "__BREGSURV_SPLIT_TEST__"

# which words of the message name a measure, and which ask for a figure: the model's choice of
# measures and of a figure is checked against these, so it cannot add what the analyst did not ask
_MEASURE_WORDS = {"cindex": ("c-index", "c index", "cindex", "concordance", "harrell"),
                  "loss": ("loss", "likelihood", "deviance"),
                  "ibs": ("ibs", "brier"),
                  "tdauc": ("tdauc", "auc", "area under")}
_FIGURE_WORDS = ("plot", "figure", "chart", "graph", "boxplot", "box-plot", "visuali", "picture",
                 "draw")

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "n_splits": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "n_splits_evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "n_splits_if_unstated": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "test_fraction": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "test_fraction_evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "subsample_fraction": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "subsample_fraction_evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "measures": {"type": "array", "maxItems": 4,
                     "items": {"type": "string", "enum": list(MEASURES)}},
        "figure": {"type": "boolean"},
    },
    "required": ["reasoning", "n_splits", "n_splits_evidence", "n_splits_if_unstated",
                 "test_fraction", "test_fraction_evidence", "subsample_fraction",
                 "subsample_fraction_evidence", "measures", "figure"],
}

_SYSTEM = policy.load("split_request")


class SplitRefusal(RuntimeError):
    """The evaluation was not run, on purpose; the message says why in plain words."""


def declined_reason(declaration: Any, plan: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Why this analysis cannot be evaluated by splits, or None."""
    if getattr(declaration, "discrete", False) or (plan or {}).get("row") == "discrete":
        return ("This analysis is on the discrete-time row, whose methods are scored by a "
                "grouped-time likelihood rather than by the C-index, loss, Brier score and "
                "time-dependent AUC the split evaluation reports, so it was not evaluated by "
                "splits. The evaluation covers analyses in continuous time.")
    if getattr(declaration, "time_col", None) is None:
        return ("This is a matched (nested case-control) design. The library has no held-out "
                "score for a matched design's methods, so it was not evaluated by splits.")
    return None


# ------------------------------------------------------------- reading the request
def estimate_seconds(result: Any) -> Tuple[float, str]:
    """Seconds one split is expected to take: the fit time recorded for the analysis already run."""
    cands = ((getattr(result, "candidates", None) or {}).get("candidates") or []) if result else []
    s = 0.0
    for c in cands:
        try:
            s += float(c.get("seconds") or 0)
            s += float((c.get("holdout") or {}).get("seconds") or 0)
        except (TypeError, ValueError):
            pass
    if s > 0:
        return s, "the fit time recorded for the analysis already run"
    if result is not None and float(getattr(result, "seconds", 0) or 0) > 0:
        return float(result.seconds), "the time the analysis already run took"
    return 20.0 * max(1, len(cands) or 10), "a rough estimate, twenty seconds per method"


def workers_for(n_splits: int) -> int:
    """How many splits run at once: the cores this process may use, bounded by the job's
    allocation (`SLURM_CPUS_PER_TASK`) and by `BREGSURV_SPLIT_WORKERS` if set."""
    try:
        cores = len(os.sched_getaffinity(0))
    except AttributeError:            # pragma: no cover (not Linux)
        cores = os.cpu_count() or 1
    for var in ("SLURM_CPUS_PER_TASK", "BREGSURV_SPLIT_WORKERS"):
        v = os.environ.get(var, "").strip()
        if v.isdigit() and int(v) > 0:
            cores = min(cores, int(v))
    return max(1, min(int(n_splits), cores))


def read_request(client, model: str, message: str, mode: str, seconds_per_split: float,
                 seconds_source: str, workers: int, cap: int = MAX_SPLITS) -> Dict[str, Any]:
    """One constrained generation (policy `split_request`); the raw dict, see :func:`validate`."""
    what = ("the cohort is cut into a training and a test part on every split"
            if mode == "split" else
            "the analyst supplied a test file, so each replicate keeps a share of the training "
            "rows and is scored on that file")
    user = (f"Mode: {what}.\n"
            f"Estimated seconds per split: {seconds_per_split:.0f} ({seconds_source}). "
            f"Splits run {workers} at a time. At most {cap} splits are run.\n\n"
            f"The analyst wrote:\n{message}")
    return boundary._chat(client, model, _SYSTEM, user, SCHEMA, "split_request", max_tokens=600)


_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+")
_PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|:|-|–|to)\s*(\d+(?:\.\d+)?)")


def _numbers(text: str) -> List[float]:
    return [float(t.replace(",", "")) for t in _NUM.findall(text or "")]


def number_supported(value: Any, evidence: Optional[str], message: str, kind: str) -> Optional[str]:
    """None when `value` is written in the analyst's message inside `evidence`; otherwise why not.

    `kind` is "count" (an integer written as digits), "test_fraction" or "keep_fraction" (a share
    written as a decimal, a percentage, or a pair such as 70/30, whose second part is the test
    share and whose first part is the share kept)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not a number"
    if not evidence or not str(evidence).strip():
        return "no evidence span was quoted"
    if not textmatch.phrase_in(message, evidence):
        return "the evidence span is not in the message"
    ev = str(evidence)
    v = float(value)
    if kind == "count":
        return None if any(abs(t - v) < 1e-9 for t in _numbers(ev)) else \
            "the number does not occur in the evidence span"
    pairs = [(float(a), float(b)) for a, b in _PAIR.findall(ev)]
    if pairs:
        for a, b in pairs:
            share = (b if kind == "test_fraction" else a) / (a + b) if (a + b) > 0 else -1
            if abs(share - v) < 1e-9:
                return None
        return "the share does not match the split written in the evidence span"
    if any(abs(t - v) < 1e-9 or abs(t - 100 * v) < 1e-6 for t in _numbers(ev)):
        return None
    return "the share does not occur in the evidence span"


@dataclass
class SplitRequest:
    mode: str                     # "split" or "subsample"
    n_splits: int
    n_splits_source: str
    fraction: float               # the test share ("split") or the share of training rows kept
    fraction_source: str
    measures: List[str]
    measures_source: str
    figure: bool
    figure_source: str
    n_splits_chosen: bool = False
    dropped: List[Dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _words(message: str) -> str:
    return " ".join((message or "").lower().split())


def validate(message: str, raw: Dict[str, Any], mode: str, cap: int = MAX_SPLITS) -> SplitRequest:
    """Check the model's reading against the analyst's words. Deterministic.

    A number is kept only when the analyst wrote it inside the quoted span; a dropped number is
    recorded with the reason. The measures and the figure are checked against the message's own
    words: a measure the message does not name is dropped, and a figure is drawn exactly when the
    message asks for one."""
    raw = raw if isinstance(raw, dict) else {}
    dropped: List[Dict[str, Any]] = []
    msg = _words(message)

    # ---- how many splits
    n, n_src, chosen = None, "", False
    v, ev = raw.get("n_splits"), raw.get("n_splits_evidence")
    if v is not None:
        why = number_supported(v, ev, message, "count")
        if why is None and float(v) != int(v):
            why = "not a whole number"
        if why is None and int(v) < 2:
            why = "fewer than two splits"
        if why is None:
            n = int(v)
            n_src = f'stated: "{ev}"'
            if n > cap:
                n_src += f" -- more than the {cap} this system runs, so {cap}"
                n = cap
        else:
            dropped.append({"field": "n_splits", "value": v, "evidence": ev, "why": why})
    if n is None:
        c = raw.get("n_splits_if_unstated")
        if isinstance(c, int) and not isinstance(c, bool) and MIN_CHOSEN <= c <= cap:
            n, chosen = c, True
            n_src = ("chosen by the model, with the estimated cost in view, because the message "
                     "states no number of splits")
        else:
            if c is not None:
                dropped.append({"field": "n_splits_if_unstated", "value": c,
                                "why": f"outside {MIN_CHOSEN} to {cap}"})
            n = min(DEFAULT_SPLITS, cap)
            n_src = "default: the message states no usable number of splits"

    # ---- the share of the test part, or of the training rows kept
    key, kind, default = (("test_fraction", "test_fraction", DEFAULT_TEST_FRACTION)
                          if mode == "split" else
                          ("subsample_fraction", "keep_fraction", DEFAULT_KEEP_FRACTION))
    frac, f_src = None, ""
    v, ev = raw.get(key), raw.get(key + "_evidence")
    if v is not None:
        why = number_supported(v, ev, message, kind)
        if why is None and not (0.05 <= float(v) <= 0.95):
            why = "outside 0.05 to 0.95"
        if why is None:
            frac, f_src = float(v), f'stated: "{ev}"'
        else:
            dropped.append({"field": key, "value": v, "evidence": ev, "why": why})
    other = "subsample_fraction" if mode == "split" else "test_fraction"
    if raw.get(other) is not None:
        dropped.append({"field": other, "value": raw.get(other),
                        "why": "does not apply: " + ("the cohort is split" if mode == "split"
                                                      else "the analyst supplied a test file")})
    if frac is None:
        frac = default
        f_src = ("default: a test part of three tenths of the cohort" if mode == "split"
                 else "default: each replicate keeps seven tenths of the training rows")

    # ---- measures and figure, against the message's words
    named = [m for m in MEASURES if any(w in msg for w in _MEASURE_WORDS[m])]
    proposed = [m for m in (raw.get("measures") or []) if m in MEASURES]
    for m in proposed:
        if m not in named:
            dropped.append({"field": "measures", "value": m,
                            "why": "the message does not name this measure"})
    kept = [m for m in MEASURES if m in proposed and m in named]
    if kept:
        measures, m_src = kept, "the measures the message names"
    elif named:
        measures, m_src = named, "the measures the message names (read by the harness)"
    else:
        measures, m_src = list(MEASURES), "default: all four (the message names none)"
    asked = any(w in msg for w in _FIGURE_WORDS)
    fig_model = bool(raw.get("figure"))
    if fig_model and not asked:
        dropped.append({"field": "figure", "value": True,
                        "why": "the message does not ask for a figure"})
    figure = asked
    fig_src = ("the message asks for a figure" if asked
               else "the message does not ask for a figure")
    return SplitRequest(mode=mode, n_splits=n, n_splits_source=n_src, fraction=frac,
                        fraction_source=f_src, measures=measures, measures_source=m_src,
                        figure=figure, figure_source=fig_src, n_splits_chosen=chosen,
                        dropped=dropped, reasoning=str(raw.get("reasoning") or "")[:1000])


# ------------------------------------------------------------------- execution
def payload_template(declaration: Any, mode: str, plan: Optional[Dict[str, Any]] = None,
                     ext_kw: Optional[Dict[str, Any]] = None, seed: int = 20260818,
                     nfolds: int = 5, nlambda: int = 50) -> str:
    """The dispatcher's input for one split, as JSON text with the split's file paths left as
    placeholders: built ONCE by `pipeline.build_payload`, so every split is the same analysis,
    and the replay script substitutes the paths the same way."""
    from . import pipeline
    decl = (dataclasses.replace(declaration, test_data_path=PLACE_TEST, test_data_expr="test")
            if mode == "split" else declaration)
    payload = pipeline.build_payload(PLACE_TRAIN, "train", decl, seed=seed, nfolds=nfolds,
                                     nlambda=nlambda, plan=plan, **(ext_kw or {}))
    return json.dumps(payload, ensure_ascii=False)


def _esc(path: str) -> str:
    return json.dumps(str(path))[1:-1]


def payload_for(template: str, train: str, test: Optional[str] = None) -> Dict[str, Any]:
    text = template.replace(PLACE_TRAIN, _esc(train))
    if test is not None:
        text = text.replace(PLACE_TEST, _esc(test))
    return json.loads(text)


_POOL: Dict[str, Any] = {}
_THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def _fit_one(i: int) -> Tuple[int, Dict[str, Any], float]:
    """One split, in a worker. R's BLAS is pinned to one thread: the splits are the parallelism."""
    from . import pipeline
    for v in _THREAD_VARS:
        os.environ[v] = "1"
    run_r = _POOL["run_r"]
    t0 = time.time()
    try:
        res = run_r("run_candidates.R", _POOL["payloads"][i], timeout_s=pipeline.COX_TIMEOUT_S)
    except TypeError:
        res = run_r("run_candidates.R", _POOL["payloads"][i])
    except Exception as exc:          # one split's failure is recorded, never fatal
        res = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
    return i, res, round(time.time() - t0, 2)


def fit_splits(payloads: List[Dict[str, Any]], run_r: Callable, workers: int) -> List[Tuple]:
    """Every split's analysis, `workers` at a time (fork, so `run_r` need not pickle)."""
    _POOL.clear()
    _POOL.update(run_r=run_r, payloads=payloads)
    try:
        if workers <= 1 or len(payloads) <= 1:
            saved = {v: os.environ.get(v) for v in _THREAD_VARS}
            try:
                return [_fit_one(i) for i in range(len(payloads))]
            finally:
                for v, old in saved.items():
                    if old is None:
                        os.environ.pop(v, None)
                    else:
                        os.environ[v] = old
        with mp.get_context("fork").Pool(workers) as pool:
            return sorted(pool.map(_fit_one, range(len(payloads)), chunksize=1),
                          key=lambda t: t[0])
    finally:
        _POOL.clear()


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def split_record(k: int, rows: List[int], res: Dict[str, Any], seconds: float) -> Dict[str, Any]:
    """What one split produced: every member's status, CV loss, tuning and held-out numbers."""
    rec: Dict[str, Any] = {"split": k, "rows": rows, "seconds": seconds,
                           "status": res.get("status")}
    if res.get("status") != "ok":
        rec["message"] = str(res.get("message"))[:500]
        return rec
    members = {}
    for c in res.get("candidates") or []:
        ho = c.get("holdout") or {}
        members[c["key"]] = {"label": c.get("label"), "status": c.get("status"),
                             "cv_loss": _num(c.get("loss")), "eta": c.get("eta"),
                             "lambda": c.get("lambda"),
                             "holdout": {m: _num(ho.get(m)) for m in MEASURES}}
    sel = res.get("selected") or {}
    rec["members"] = members
    rec["order"] = [c["key"] for c in res.get("candidates") or []]
    rec["selected"] = sel.get("key")
    rec["selected_holdout"] = {m: _num((sel.get("holdout") or {}).get(m)) for m in MEASURES}
    rec["n_test"] = (res.get("test_data") or {}).get("n")
    rec["n_test_events"] = (res.get("test_data") or {}).get("n_events")
    return rec


def summarise(records: List[Dict[str, Any]], measures: List[str]) -> List[Dict[str, Any]]:
    """One row per member (in the dispatcher's order), then the CV-selected row: on how many
    splits it was fitted and selected, and mean and sd of every requested measure."""
    order: List[str] = []
    labels: Dict[str, str] = {}
    for r in records:
        for k in r.get("order") or []:
            if k not in order:
                order.append(k)
                labels[k] = r["members"][k].get("label") or k
    rows = []
    for k in order + [SELECTED_KEY]:
        vals: Dict[str, List[float]] = {m: [] for m in measures}
        n_fit = n_sel = 0
        for r in records:
            if r.get("status") != "ok":
                continue
            if k == SELECTED_KEY:
                ho, ok = r.get("selected_holdout") or {}, r.get("selected") is not None
            else:
                mem = (r.get("members") or {}).get(k)
                ok = bool(mem) and mem.get("status") == "ok"
                ho = (mem or {}).get("holdout") or {}
                n_sel += int(r.get("selected") == k)
            n_fit += int(ok)
            if ok:
                for m in measures:
                    if ho.get(m) is not None:
                        vals[m].append(ho[m])
        row = {"key": k, "label": SELECTED_LABEL if k == SELECTED_KEY else labels[k],
               "n_fitted": n_fit, "n_selected": (n_fit if k == SELECTED_KEY else n_sel)}
        for m in measures:
            v = vals[m]
            row[f"{m}_n"] = len(v)
            row[f"{m}_mean"] = statistics.fmean(v) if v else None
            row[f"{m}_sd"] = statistics.stdev(v) if len(v) > 1 else None
        rows.append(row)
    return rows


def _fmt(m: str, mean: Optional[float], sd: Optional[float]) -> str:
    if mean is None:
        return "-"
    d = _DIGITS[m]
    return f"{mean:.{d}f}" + (f" ± {sd:.{d}f}" if sd is not None else "")


def table_markdown(rows: List[Dict[str, Any]], measures: List[str], n_ok: int) -> str:
    head = (["method", "fitted on", "selected by CV on"]
            + [f"{MEASURE_LABEL[m]} (mean ± sd)" for m in measures])
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        sel = ("every split" if r["key"] == SELECTED_KEY
               else f"{r['n_selected']} of {n_ok}")
        out.append("| " + " | ".join(
            [r["label"], f"{r['n_fitted']} of {n_ok}", sel]
            + [_fmt(m, r[f"{m}_mean"], r[f"{m}_sd"]) for m in measures]) + " |")
    return "\n".join(out)


def write_table_csv(rows: List[Dict[str, Any]], measures: List[str], path: Path) -> None:
    cols = ["key", "label", "n_fitted", "n_selected"]
    for m in measures:
        cols += [f"{m}_mean", f"{m}_sd", f"{m}_n"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})


def write_values_csv(records: List[Dict[str, Any]], measures: List[str], path: Path) -> None:
    """The long table the box plots are drawn from: split, member, measure, value."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split", "key", "measure", "value"])
        for r in records:
            if r.get("status") != "ok":
                continue
            for k, mem in (r.get("members") or {}).items():
                if mem.get("status") != "ok":
                    continue
                for m in measures:
                    if mem["holdout"].get(m) is not None:
                        w.writerow([r["split"], k, m, repr(mem["holdout"][m])])
            for m in measures:
                v = (r.get("selected_holdout") or {}).get(m)
                if v is not None:
                    w.writerow([r["split"], SELECTED_KEY, m, repr(v)])


@dataclass
class SplitsResult:
    request: SplitRequest
    record: Dict[str, Any]
    table: List[Dict[str, Any]]
    markdown: str
    files: Dict[str, str]
    seconds: float

    @property
    def paths(self) -> List[str]:
        return [self.files[k] for k in ("table_md", "table_csv", "figure_pdf", "figure_png",
                                        "record", "replay") if self.files.get(k)]


def evaluate(data_path: str, data_expr: str, declaration: Any, request: SplitRequest,
             outdir: str, plan: Optional[Dict[str, Any]] = None,
             ext_kw: Optional[Dict[str, Any]] = None, run_r: Optional[Callable] = None,
             seed: int = SPLIT_SEED, workers: Optional[int] = None,
             inner_seed: int = 20260818, nfolds: int = 5, nlambda: int = 50,
             provenance: Optional[Dict[str, Any]] = None) -> SplitsResult:
    """Draw the splits, analyse every one as the cohort was analysed, score, tabulate, plot,
    record, and write the replay script. Raises SplitRefusal when the analysis cannot be
    evaluated this way or the splits cannot be drawn."""
    from . import pipeline
    why = declined_reason(declaration, plan)
    if why:
        raise SplitRefusal(why)
    if request.mode == "subsample" and not declaration.has_test_data:
        raise SplitRefusal("resampling the training rows needs the analyst's test file")
    t0 = time.time()
    run_r = run_r or pipeline._default_run_r()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    draw = {"data_path": data_path, "data_expr": data_expr,
            "event_col": declaration.event_col, "event_value": declaration.event_value,
            "n_splits": int(request.n_splits), "fraction": float(request.fraction),
            "mode": request.mode, "seed": int(seed), "outdir": str(out / "splits")}
    drawn = run_r("draw_splits.R", draw)
    if drawn.get("status") != "ok":
        raise SplitRefusal("the splits could not be drawn: " + str(drawn.get("message")))
    splits = drawn["splits"] if isinstance(drawn["splits"], list) else [drawn["splits"]]
    template = payload_template(declaration, request.mode, plan, ext_kw, inner_seed, nfolds,
                                nlambda)
    payloads = [payload_for(template, sp["train"], sp.get("test")) for sp in splits]
    n_work = workers or workers_for(len(payloads))
    fitted = fit_splits(payloads, run_r, n_work)
    records = []
    for (i, res, secs), sp in zip(fitted, splits):
        rows = sp.get("rows")
        rows = [int(x) for x in (rows if isinstance(rows, list) else [rows])]
        records.append(split_record(int(sp["split"]), rows, res, secs))
    ok = [r for r in records if r.get("status") == "ok"]
    if not ok:
        raise SplitRefusal("no split could be analysed: "
                           + "; ".join(sorted({r.get("message", "") for r in records}))[:600])
    measures = list(request.measures)
    table = summarise(records, measures)
    md = table_markdown(table, measures, len(ok))

    files: Dict[str, str] = {}
    (out / "splits_table.md").write_text(md + "\n", encoding="utf-8")
    files["table_md"] = str(out / "splits_table.md")
    write_table_csv(table, measures, out / "splits_table.csv")
    files["table_csv"] = str(out / "splits_table.csv")
    write_values_csv(records, measures, out / "splits_values.csv")
    files["values"] = str(out / "splits_values.csv")
    figure_problem = None
    if request.figure:
        labels = {r["key"]: r["label"] for r in table}
        pr = run_r("plot_splits.R", {"values_csv": files["values"], "measures": measures,
                                     "labels": labels, "order": [r["key"] for r in table],
                                     "selected_key": SELECTED_KEY,
                                     "out_base": str(out / "splits_boxplot")})
        if pr.get("status") == "ok":
            files["figure_pdf"], files["figure_png"] = pr["pdf"], pr["png"]
        else:
            figure_problem = str(pr.get("message"))[:300]

    record = {
        "what": "evaluation by repeated random splits, requested by the analyst; reported "
                "beside the analysis, never used to choose its model",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data": pipeline._fingerprint(data_path),
        "mode": request.mode, "seed": int(seed), "rng_kind": drawn.get("rng_kind"),
        "n": drawn.get("n"), "n_events": drawn.get("n_events"),
        "n_splits": int(request.n_splits), "fraction": float(request.fraction),
        "measures": measures, "workers": n_work,
        "inner": {"seed": inner_seed, "nfolds": nfolds, "nlambda": nlambda,
                  "plan": pipeline._plan_for_hash(plan),
                  "candidate_set": "the plan's members" if plan else "the admissible set"},
        "request": request.as_dict(),
        # the draw as replay_splits.R repeats it (the data path is the replayer's argument)
        "draw": {k: v for k, v in draw.items() if k not in ("data_path", "outdir")},
        "payload_template": template,
        "placeholders": {"train": PLACE_TRAIN, "test": PLACE_TEST},
        "test_data": (pipeline._fingerprint(declaration.test_data_path)
                      if request.mode == "subsample" and declaration.test_data_path else None),
        "splits": records,
        "table": table,
        "figure_problem": figure_problem,
        "provenance": provenance or {},
        "seconds": round(time.time() - t0, 1),
    }
    (out / "splits.json").write_text(json.dumps(record, indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    files["record"] = str(out / "splits.json")
    (out / "replay_splits.R").write_text(render_replay(record), encoding="utf-8")
    files["replay"] = str(out / "replay_splits.R")
    return SplitsResult(request=request, record=record, table=table, markdown=md, files=files,
                        seconds=record["seconds"])


# ----------------------------------------------------------------- the chat reply
def reply_text(sr: SplitsResult) -> str:
    """The chat reply, rendered by the harness from the record; the model writes none of it."""
    r, rec = sr.request, sr.record
    n_ok = sum(1 for s in rec["splits"] if s.get("status") == "ok")
    if r.mode == "split":
        how = (f"{r.n_splits} random splits of your cohort, each holding out "
               f"{r.fraction:.0%} of the subjects as a test part (event-stratified, seed "
               f"{rec['seed']}, {rec['rng_kind'].split('/')[0]})")
    else:
        how = (f"{r.n_splits} random subsamples of your training rows, each keeping "
               f"{r.fraction:.0%} of them (event-stratified, seed {rec['seed']}, "
               f"{rec['rng_kind'].split('/')[0]}), every one scored on your test file")
    lines = [f"**Evaluation by repeated splits.** {how}. On every split the same analysis was "
             "run on the training part -- every method tuned by its own cross-validation, one "
             "selected -- and every method was scored on the held-out part."]
    if n_ok < len(rec["splits"]):
        lines.append(f"{len(rec['splits']) - n_ok} of {len(rec['splits'])} splits could not be "
                     "analysed; the table is over the other " f"{n_ok}.")
    lines.append("")
    lines.append(sr.markdown)
    lines.append("")
    settled = [f"- number of splits: {r.n_splits_source}",
               f"- {'test part' if r.mode == 'split' else 'rows kept'}: {r.fraction_source}",
               f"- measures: {r.measures_source}",
               f"- figure: {r.figure_source}"]
    lines.append("How the settings were settled:\n" + "\n".join(settled))
    if r.dropped:
        lines.append("Set aside from the reading of your message (not in your words): "
                     + "; ".join(f"{d['field']} {d.get('value')!r} ({d['why']})"
                                 for d in r.dropped) + ".")
    if rec.get("figure_problem"):
        lines.append(f"The box plots could not be drawn: {rec['figure_problem']}")
    lines.append("The files -- the table (CSV and Markdown), "
                 + ("the box plots (PDF and PNG), " if r.figure and not rec.get("figure_problem")
                    else "")
                 + "splits.json (seed, split membership and every number) and replay_splits.R, "
                   "which redraws the splits and checks the numbers come back -- are separate "
                   "from the report. These numbers describe how the procedure behaves over "
                   "splits; the analysis above did not use them to choose its model.")
    lines.append("<small>Every number above was computed and written by the harness; no model "
                 "wrote any of them.</small>")
    return "\n".join(lines)


# ----------------------------------------------------------------- the replay script
def render_replay(rec: Dict[str, Any]) -> str:
    """replay_splits.R: redraw the splits from the seed and check the membership, refit every
    split (or the ones named) with the recorded dispatcher input and check every number."""
    return f"""#!/usr/bin/env Rscript
# replay_splits.R -- replays one BregSurv agent evaluation by repeated splits.
#
# Generated:  {rec.get('generated_at')}
# Data:       {rec['data']['name']}  sha256 {rec['data']['sha256'][:16]}...
# Splits:     {rec['n_splits']} ({rec['mode']}), seed {rec['seed']}, {rec.get('rng_kind')}
#
# Usage:  Rscript replay_splits.R <data file> [splits.json] [all | 1,2,3]
#   Set BREGSURV_R_SCRIPTS to mcp/r_scripts. The language model is not involved.
#   It stops, saying what moved, unless the splits and the recorded numbers come back.

suppressPackageStartupMessages(library(jsonlite))
a <- commandArgs(TRUE)
if (length(a) < 1) stop("usage: Rscript replay_splits.R <data file> [splits.json] [which]")
DATA <- a[1]
here <- dirname(normalizePath(sub("^--file=", "", grep("^--file=", commandArgs(FALSE),
                                                       value = TRUE)[1])))
RECORD <- if (length(a) >= 2) a[2] else file.path(here, "splits.json")
WHICH <- if (length(a) >= 3) a[3] else "all"
SCRIPTS <- Sys.getenv("BREGSURV_R_SCRIPTS", unset = "mcp/r_scripts")
if (!dir.exists(SCRIPTS)) stop("set BREGSURV_R_SCRIPTS to mcp/r_scripts")
rec <- fromJSON(RECORD, simplifyVector = FALSE)

call_script <- function(name, text) {{
  in_f <- tempfile(fileext = ".json"); out_f <- tempfile(fileext = ".json")
  writeLines(text, in_f)
  system2(file.path(R.home("bin"), "Rscript"),
          c("--no-save", "--no-restore", "--no-init-file",
            shQuote(file.path(SCRIPTS, name)), shQuote(in_f), shQuote(out_f)))
  fromJSON(out_f, simplifyVector = FALSE)
}}
esc <- function(p) {{ j <- as.character(toJSON(p, auto_unbox = TRUE)); substr(j, 2, nchar(j) - 1) }}

## 1. the splits, redrawn from the seed
work <- tempfile("splits_replay_"); dir.create(work)
draw <- rec$draw
draw$data_path <- DATA
draw$outdir <- file.path(work, "splits")
d <- call_script("draw_splits.R", as.character(toJSON(draw, auto_unbox = TRUE, null = "null",
                                                      digits = NA)))
if (!identical(d$status, "ok")) stop("the splits could not be drawn: ", d$message, call. = FALSE)
if (length(d$splits) != length(rec$splits))
  stop("the replay drew a different number of splits", call. = FALSE)
for (k in seq_along(rec$splits)) {{
  if (!identical(as.integer(unlist(d$splits[[k]]$rows)), as.integer(unlist(rec$splits[[k]]$rows))))
    stop(sprintf("split %d: the redrawn rows differ from the recorded ones", k), call. = FALSE)
}}
cat(sprintf("split membership REPRODUCED (%d splits, seed %s)\\n", length(rec$splits), rec$seed))

## 2. the analyses, refitted and checked
ks <- if (identical(WHICH, "all")) seq_along(rec$splits) else as.integer(strsplit(WHICH, ",")[[1]])
same <- function(x, y) {{
  if (is.null(x) || is.null(y)) return(is.null(x) && is.null(y))
  x <- as.numeric(x); y <- as.numeric(y)
  if (is.na(x) || is.na(y)) return(is.na(x) && is.na(y))
  abs(x - y) <= 1e-8 * max(1, abs(x))
}}
for (k in ks) {{
  r <- rec$splits[[k]]
  if (!identical(r$status, "ok")) {{ cat(sprintf("split %d: recorded as not analysed; skipped\\n", k)); next }}
  txt <- gsub(rec$placeholders$train, esc(d$splits[[k]]$train), rec$payload_template, fixed = TRUE)
  if (!is.null(d$splits[[k]]$test))
    txt <- gsub(rec$placeholders$test, esc(d$splits[[k]]$test), txt, fixed = TRUE)
  res <- call_script("run_candidates.R", txt)
  if (!identical(res$status, "ok")) stop(sprintf("split %d could not be refitted: %s", k, res$message), call. = FALSE)
  if (!identical(res$selected$key, r$selected))
    stop(sprintf("split %d: CV selected %s, the record says %s", k, res$selected$key, r$selected), call. = FALSE)
  moved <- character(0)
  for (cand in res$candidates) {{
    m <- r$members[[cand$key]]
    if (is.null(m)) {{ moved <- c(moved, paste(cand$key, "not recorded")); next }}
    if (!identical(cand$status, m$status)) {{ moved <- c(moved, paste(cand$key, "status")); next }}
    if (!identical(cand$status, "ok")) next
    if (!same(cand$loss, m$cv_loss)) moved <- c(moved, paste(cand$key, "cv loss"))
    for (h in c("cindex", "loss", "ibs", "tdauc"))
      if (!same(cand$holdout[[h]], m$holdout[[h]])) moved <- c(moved, paste(cand$key, h))
  }}
  if (length(moved)) stop(sprintf("split %d: the replayed numbers differ (%s)", k,
                                   paste(moved, collapse = ", ")), call. = FALSE)
  cat(sprintf("split %d REPRODUCED (selected %s)\\n", k, r$selected))
}}
cat("evaluation by splits REPRODUCED\\n")
"""
