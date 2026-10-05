#!/usr/bin/env python3
"""run_diskd.py - the network members of the discrete-time row.

Called by mcp/r_scripts/run_candidates.R as:
    python run_diskd.py <input.json> <output.json>

HARNESS-INVOKED, from R, with the same temp-file JSON handshake every R
script takes. It fits Internal-NN (eta = 0) and DiSKD (eta by nested CV) with
`bregsurv_agent/discrete/diskd.py`, the estimator as handed over, on the fold
assignment the R side drew, and returns each member's pooled held-out
negative log-likelihood per subject -- the same functional DiscreteKL is
scored by, so the row ranks on one scale. Nothing here decides anything.

input.json:
  x               n x p numeric matrix (row-major), the covariates
  columns         the p column names, in x's order
  duration_index  n, 0-based interval index (the R side's time_bin - 1)
  event           n, 0/1 after censoring at the horizon
  n_intervals     K
  folds           n fold labels 1..nfolds (the shared partition)
  seed            the run's seed
  threads         torch threads (pinned by the caller)
  teacher         null, or {beta: {name: value} on the columns, dH0: [K]}
  settings        null, or overrides -- TESTING ONLY (ruling 2: the product
                  runs the released nested CV): architecture, eta_grid,
                  learning_rates, max_epochs, patience, stop_fraction

output.json:
  {"status": "ok", "settings": {...effective...},
   "internal": {loss, eta: 0, learning_rate, epochs},
   "diskd":    {loss, eta, learning_rate, epochs}      (absent without a teacher)
   "cv_path": [...], "seconds": s, "versions": {torch, numpy}}
  or {"status": "error", "message": ...}
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent            # mcp/py_scripts -> repo root

# the released settings of the DiSKD run (README: "TrainingProfile holds
# the frozen training settings of the MIUM run")
DEFAULTS = {
    "architecture": "repo_lh4x128",
    "eta_grid": [0.0, 1.0, 5.0, 10.0, 20.0, 40.0, 80.0],
    "learning_rates": [5e-4, 1e-3],
    "stop_fraction": 0.2,
}


def main(in_path: str, out_path: str) -> int:
    t0 = time.time()
    try:
        payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
        import numpy as np
        if str(_REPO) not in sys.path:
            sys.path.insert(0, str(_REPO))
        import torch
        from bregsurv_agent.discrete.diskd import (DiSKD, TrainingProfile,
                                                   cox_teacher_hazard)

        cols = [str(c) for c in payload["columns"]]
        x = np.asarray(payload["x"], dtype=float).reshape(-1, len(cols))
        idx = np.asarray(payload["duration_index"], dtype=int)
        ev = np.asarray(payload["event"], dtype=int)
        K = int(payload["n_intervals"])
        folds = np.asarray(payload["folds"], dtype=int)
        seed = int(payload.get("seed") or 20260818)
        threads = max(1, int(payload.get("threads") or 1))
        opts = dict(payload.get("settings") or {})

        teacher_in = payload.get("teacher")
        if teacher_in:
            beta = np.array([float(teacher_in["beta"].get(c, 0.0)) for c in cols])
            d_h0 = np.asarray(teacher_in["dH0"], dtype=float)
            if d_h0.shape != (K,):
                raise ValueError(f"dH0 has {d_h0.shape[0]} entries, K is {K}")
            teacher = cox_teacher_hazard(x @ beta, d_h0)
            eta_grid = [float(e) for e in opts.get("eta_grid", DEFAULTS["eta_grid"])]
        else:
            teacher = np.zeros((len(idx), K))
            eta_grid = [0.0]
        if not any(abs(e) < 1e-15 for e in eta_grid):
            eta_grid = [0.0] + eta_grid

        prof_kw = {k: opts[k] for k in ("max_epochs", "patience", "min_delta",
                                        "batch_size", "dropout", "weight_decay")
                   if k in opts}
        profile = TrainingProfile(**prof_kw)
        settings = {
            "architecture": str(opts.get("architecture", DEFAULTS["architecture"])),
            "eta_grid": eta_grid,
            "learning_rates": [float(v) for v in opts.get("learning_rates",
                                                          DEFAULTS["learning_rates"])],
            "stop_fraction": float(opts.get("stop_fraction", DEFAULTS["stop_fraction"])),
            "n_folds": int(len(set(folds.tolist()))),
            "seed": seed, "threads": threads,
            "profile": asdict(profile),
            "tuner": "grid",
        }
        model = DiSKD(n_intervals=K, architecture=settings["architecture"],
                      eta_grid=tuple(eta_grid), tuner="grid",
                      learning_rates=tuple(settings["learning_rates"]),
                      n_folds=settings["n_folds"],
                      stop_fraction=settings["stop_fraction"],
                      profile=profile, seed=seed, threads=threads,
                      ).fit(x, idx, ev, teacher, folds=folds)
        pooled = {float(k): float(v) for k, v in model.cv_pooled_hard_nll_.items()}
        out = {
            "status": "ok",
            "settings": settings,
            "internal": {"loss": pooled.get(0.0), "eta": 0.0,
                         "learning_rate": float(model.learning_rate_),
                         "epochs": int(model.epochs_["internal"])},
            "cv_pooled_hard_nll": {str(k): v for k, v in pooled.items()},
            "cv_path": model.cv_path_,
            "seconds": round(time.time() - t0, 2),
            "versions": {"torch": torch.__version__, "numpy": np.__version__},
        }
        if teacher_in:
            out["diskd"] = {"loss": pooled.get(float(model.eta_)),
                            "eta": float(model.eta_),
                            "learning_rate": float(model.learning_rate_),
                            "epochs": int(model.epochs_["diskd"])}
    except Exception as exc:          # a structured error, never a traceback on stdout
        out = {"status": "error",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()[-2000:],
               "seconds": round(time.time() - t0, 2)}
    # strict JSON for R: a failed trial's inf pooled value becomes null
    Path(out_path).write_text(json.dumps(_finite(out), default=_json_default,
                                         allow_nan=False),
                              encoding="utf-8")
    return 0 if out["status"] == "ok" else 1


def _finite(o):
    """inf / nan -> None, recursively; the rest untouched."""
    import math
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


def _json_default(o):
    """numpy scalars and the like, which json cannot serialise on its own."""
    try:
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python run_diskd.py <input.json> <output.json>")
    sys.exit(main(sys.argv[1], sys.argv[2]))
