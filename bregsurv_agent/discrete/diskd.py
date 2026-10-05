#!/usr/bin/env python3
"""DiSKD: discrete-time survival knowledge distillation from a Cox teacher.

A logistic-hazard network is trained on the internal cohort against the soft
target  (hard + eta * teacher) / (1 + eta)  on every interval up to and
including the subject's own interval, where ``teacher`` is the interval hazard
implied by an external Cox model.  ``eta = 0`` is the internal-only network.

Protocol (identical to the MIUM comparison runner, 21_run_diskd_paper_nll.py):
  1. K score folds over the training set; inside each, the other folds are
     split 80/20 (event-stratified) into a fit part and an early-stopping part.
     Features are standardised on the fit part only.
  2. Learning rate is chosen at eta = 0 by the pooled held-out hard NLL.
  3. eta is chosen by the same criterion, over a grid or with Optuna TPE.
  4. Final models (Internal-NN at eta = 0, DiSKD at the selected eta) are
     refitted on the whole training set for a fixed number of epochs equal to
     the median best epoch of the corresponding CV trial, from one shared
     initialisation.

Dependencies: numpy, torch; optuna only when tuner="optuna".

Usage
-----
    from diskd import DiSKD, cox_teacher_hazard, floor_bins
    teacher = cox_teacher_hazard(lp_external, baseline_increment)   # (n, K)
    idx = floor_bins(time_days, width=7.0, n_intervals=53)          # 0-based
    model = DiSKD(n_intervals=53).fit(X, idx, event, teacher)
    hazard, survival = model.predict(X_new)          # (m, K) each
    score = model.risk_score(X_new)                  # log cumulative hazard
    hazard0, survival0 = model.predict(X_new, which="internal")

    python diskd.py --self-test
"""
from __future__ import annotations

import copy
import math
import random
import sys
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ARCHITECTURES = ("small_lh", "repo_lh4x128", "repo_te4x128")
HAZARD_CLIP = 1e-7


# ----------------------------------------------------------------------------
# Data helpers
# ----------------------------------------------------------------------------
def floor_bins(durations: np.ndarray, width: float, n_intervals: int) -> np.ndarray:
    """0-based interval index  min(floor(t / width), n_intervals - 1)."""
    t = np.asarray(durations, dtype=float)
    if not np.isfinite(t).all() or (t < 0).any():
        raise ValueError("durations must be finite and nonnegative")
    return np.minimum(np.floor(t / float(width)).astype(np.int64), n_intervals - 1)


def cox_teacher_hazard(lp: np.ndarray, baseline_increment: np.ndarray) -> np.ndarray:
    """Interval hazards 1 - exp(-dH0_k * exp(lp_i)) implied by an external Cox model.

    ``lp`` is the external linear predictor of each subject (external coefficients
    times the subject's covariates); ``baseline_increment`` is the external
    baseline cumulative hazard increment over each of the K intervals.
    """
    lp = np.asarray(lp, dtype=np.float64).reshape(-1)
    d_h0 = np.asarray(baseline_increment, dtype=np.float64).reshape(-1)
    if (d_h0 < 0).any():
        raise ValueError("baseline increments must be nonnegative")
    return 1.0 - np.exp(-np.outer(np.exp(lp), d_h0))


def hard_targets_and_mask(
    indices: np.ndarray, events: np.ndarray, n_intervals: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Event indicator per interval and the at-risk mask (intervals <= own index)."""
    indices = np.asarray(indices, dtype=np.int64)
    if (indices < 0).any() or (indices >= n_intervals).any():
        raise ValueError("interval index out of range")
    events = np.asarray(events, dtype=np.float32)
    target = np.zeros((len(indices), n_intervals), dtype=np.float32)
    target[np.arange(len(indices)), indices] = events
    mask = (np.arange(n_intervals, dtype=np.int64)[None, :] <= indices[:, None]).astype(np.float32)
    return target, mask


def make_scaler(x: np.ndarray) -> Dict[str, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    center = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    scale[(~np.isfinite(scale)) | (scale <= np.sqrt(np.finfo(float).eps))] = 1.0
    return {"center": center, "scale": scale}


def apply_scaler(x: np.ndarray, scaler: Dict[str, np.ndarray]) -> np.ndarray:
    out = (np.asarray(x, dtype=np.float64) - scaler["center"]) / scaler["scale"]
    if not np.isfinite(out).all():
        raise ValueError("non-finite value after scaling")
    return out.astype(np.float32)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32 - 1))
    torch.manual_seed(seed)


def stratified_folds(events: np.ndarray, n_folds: int, seed: int) -> np.ndarray:
    """Fold labels 1..n_folds, balanced within event classes."""
    events = np.asarray(events, dtype=np.int64)
    rng = np.random.RandomState(seed % (2**32 - 1))
    folds = np.zeros(len(events), dtype=np.int64)
    for value in (0, 1):
        members = np.flatnonzero(events == value)
        rng.shuffle(members)
        folds[members] = 1 + np.arange(len(members)) % n_folds
    return folds


def stratified_stop_split(
    pool: np.ndarray, events: np.ndarray, stop_fraction: float, seed: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Split a fit pool into fit / early-stop parts by event class."""
    pool = np.asarray(pool, dtype=np.int64)
    rng = np.random.RandomState(seed % (2**32 - 1))
    fit_parts: List[np.ndarray] = []
    stop_parts: List[np.ndarray] = []
    for value in (0, 1):
        members = pool[np.asarray(events)[pool] == value].copy()
        if not len(members):
            continue
        rng.shuffle(members)
        n_stop = 0 if len(members) == 1 else min(max(1, int(np.rint(len(members) * stop_fraction))), len(members) - 1)
        stop_parts.append(members[:n_stop])
        fit_parts.append(members[n_stop:])
    fit = np.sort(np.concatenate(fit_parts))
    stop = np.sort(np.concatenate(stop_parts))
    if not len(fit) or not len(stop):
        raise ValueError("early-stop split produced an empty partition")
    return fit, stop


# ----------------------------------------------------------------------------
# Networks (repo_* blocks follow DiSKD/net/MLP_Vanilla.py and MLP_Timeemb.py)
# ----------------------------------------------------------------------------
class SmallLH(nn.Module):
    def __init__(self, n_features: int, n_intervals: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 32), nn.ReLU(), nn.Dropout(dropout), nn.Linear(32, n_intervals)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class RepoDenseBlock(nn.Module):
    def __init__(self, n_in: int, n_out: int, dropout: float) -> None:
        super().__init__()
        self.linear = nn.Linear(n_in, n_out, bias=True)
        nn.init.kaiming_normal_(self.linear.weight.data, nonlinearity="relu")
        self.norm = nn.LayerNorm(n_out)
        self.dropout = nn.Dropout(dropout) if dropout else None
        self.use_residual = n_in == n_out

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.norm(self.linear(x)))
        if self.dropout is not None:
            out = self.dropout(out)
        return out + x if self.use_residual else out


class RepoLH4x128(nn.Module):
    def __init__(self, n_features: int, n_intervals: int, dropout: float) -> None:
        super().__init__()
        widths = [n_features, 128, 128, 128, 128]
        self.blocks = nn.ModuleList([RepoDenseBlock(a, b, dropout) for a, b in zip(widths[:-1], widths[1:])])
        self.head = nn.Linear(128, n_intervals, bias=True)
        nn.init.kaiming_normal_(self.head.weight.data, nonlinearity="relu")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for block in self.blocks:
            x = block(x)
        return self.head(x)


def trigonometric_embedding(n_intervals: int, width: int) -> torch.Tensor:
    embedding = torch.zeros((n_intervals, width), dtype=torch.float32)
    even = torch.arange(0, width, 2, dtype=torch.float32)
    odd = torch.arange(1, width, 2, dtype=torch.float32)
    for k in range(n_intervals):
        embedding[k, even.long()] = torch.sin(k * torch.pow(torch.tensor(10000.0), -even / width))
        embedding[k, odd.long()] = torch.cos(k * torch.pow(torch.tensor(10000.0), -(odd - 1.0) / width))
    return embedding.unsqueeze(0)


class RepoDenseSequenceBlock(nn.Module):
    def __init__(self, n_in: int, n_out: int, dropout: float) -> None:
        super().__init__()
        self.linear = nn.Linear(n_in, n_out, bias=True)
        nn.init.kaiming_normal_(self.linear.weight.data, nonlinearity="relu")
        self.norm = nn.LayerNorm(n_out)
        self.dropout = nn.Dropout(dropout) if dropout else None
        self.skip = nn.Identity() if n_in == n_out else nn.Linear(n_in, n_out, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.norm(self.linear(x)))
        if self.dropout is not None:
            out = self.dropout(out)
        return out + self.skip(x)


class RepoTE4x128(nn.Module):
    def __init__(self, n_features: int, n_intervals: int, dropout: float) -> None:
        super().__init__()
        self.feature_embedding = nn.Linear(n_features, 128, bias=True)
        self.register_buffer("time_embedding", trigonometric_embedding(n_intervals, 128))
        self.blocks = nn.ModuleList([RepoDenseSequenceBlock(128, 128, dropout) for _ in range(3)])
        self.tail = RepoDenseSequenceBlock(128, 64, dropout)
        self.head = nn.Linear(64, 1, bias=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.feature_embedding(x).unsqueeze(1) + self.time_embedding
        for block in self.blocks:
            out = block(out)
        return self.head(self.tail(out)).squeeze(2)


def make_model(architecture: str, n_features: int, n_intervals: int, dropout: float) -> nn.Module:
    if architecture == "small_lh":
        return SmallLH(n_features, n_intervals, dropout)
    if architecture == "repo_lh4x128":
        return RepoLH4x128(n_features, n_intervals, dropout)
    if architecture == "repo_te4x128":
        return RepoTE4x128(n_features, n_intervals, dropout)
    raise ValueError(f"unknown architecture: {architecture}; choose from {ARCHITECTURES}")


# ----------------------------------------------------------------------------
# Loss and training
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class TrainingProfile:
    learning_rate: float = 5e-4
    weight_decay: float = 0.0
    betas: Tuple[float, float] = (0.9, 0.99)
    eps: float = 1e-8
    batch_size: int = 32
    max_epochs: int = 512
    patience: int = 5
    min_delta: float = 1e-5
    gradient_clip: float = 0.0
    dropout: float = 0.10


def masked_distillation_loss(logits, hard, mask, teacher, eta: float) -> torch.Tensor:
    soft = (hard + float(eta) * teacher) / (1.0 + float(eta))
    element = F.binary_cross_entropy_with_logits(logits, soft, reduction="none")
    return (element * mask).sum(dim=1).mean()


def masked_hard_nll(logits, hard, mask) -> torch.Tensor:
    element = F.binary_cross_entropy_with_logits(logits, hard, reduction="none")
    return (element * mask).sum(dim=1).mean()


def _bundle(x, indices, events, teacher, n_intervals: int, device) -> Dict[str, torch.Tensor]:
    target, mask = hard_targets_and_mask(indices, events, n_intervals)
    return {
        "x": torch.as_tensor(x, dtype=torch.float32, device=device),
        "hard": torch.as_tensor(target, dtype=torch.float32, device=device),
        "mask": torch.as_tensor(mask, dtype=torch.float32, device=device),
        "teacher": torch.as_tensor(teacher, dtype=torch.float32, device=device),
    }


def _evaluate(model: nn.Module, bundle, eta: float) -> Tuple[float, float]:
    """(distillation loss at eta, hard NLL) on a bundle, per subject."""
    model.eval()
    with torch.no_grad():
        logits = model(bundle["x"])
        distilled = masked_distillation_loss(logits, bundle["hard"], bundle["mask"], bundle["teacher"], eta)
        hard = masked_hard_nll(logits, bundle["hard"], bundle["mask"])
    return float(distilled), float(hard)


def _train(
    architecture: str,
    profile: TrainingProfile,
    initial_state: Dict[str, torch.Tensor],
    fit_bundle,
    eta: float,
    seed: int,
    device,
    stop_bundle=None,
    epochs: Optional[int] = None,
) -> Tuple[nn.Module, Dict[str, Any]]:
    """Adam on the masked distillation loss.

    With ``stop_bundle``: early stopping on its distillation loss (patience /
    min_delta), returning the best state.  Without it: exactly ``epochs`` epochs.
    """
    set_seed(seed)
    model = make_model(architecture, int(fit_bundle["x"].shape[1]), int(fit_bundle["hard"].shape[1]), profile.dropout)
    model.load_state_dict(initial_state)
    model.to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=profile.learning_rate, betas=profile.betas, eps=profile.eps, weight_decay=profile.weight_decay
    )
    rng = np.random.RandomState(seed % (2**32 - 1))
    n = int(fit_bundle["x"].shape[0])
    n_epochs = profile.max_epochs if stop_bundle is not None else max(1, int(epochs))
    best_state, best_value, best_epoch, stale, stop_reason = copy.deepcopy(model.state_dict()), math.inf, 0, 0, "max_epochs"
    epoch = 0
    for epoch in range(1, n_epochs + 1):
        model.train()
        order = rng.permutation(n)
        for start in range(0, n, profile.batch_size):
            take = torch.as_tensor(order[start : start + profile.batch_size], dtype=torch.int64, device=device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(fit_bundle["x"].index_select(0, take))
            loss = masked_distillation_loss(
                logits, fit_bundle["hard"].index_select(0, take), fit_bundle["mask"].index_select(0, take),
                fit_bundle["teacher"].index_select(0, take), eta,
            )
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite training loss at epoch {epoch}")
            loss.backward()
            if profile.gradient_clip > 0:
                nn.utils.clip_grad_norm_(model.parameters(), profile.gradient_clip)
            optimizer.step()
        if stop_bundle is None:
            continue
        stop_value, _ = _evaluate(model, stop_bundle, eta)
        if not math.isfinite(stop_value):
            raise FloatingPointError(f"non-finite early-stop loss at epoch {epoch}")
        if stop_value < best_value - profile.min_delta:
            best_value, best_epoch, best_state, stale = stop_value, epoch, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
            if stale >= profile.patience:
                stop_reason = "patience"
                break
    if stop_bundle is not None:
        model.load_state_dict(best_state)
    else:
        best_epoch, stop_reason = epoch, "fixed_epochs"
    model.eval()
    return model, {"best_epoch": int(best_epoch), "epochs_run": int(epoch), "stop_reason": stop_reason}


# ----------------------------------------------------------------------------
# Estimator
# ----------------------------------------------------------------------------
class DiSKD:
    """Internal-NN (eta = 0) and DiSKD (eta selected by nested CV) in one fit.

    Parameters
    ----------
    n_intervals      number of discrete intervals K.
    architecture     "repo_lh4x128" (default), "small_lh" or "repo_te4x128".
    eta_grid         candidate etas when tuner="grid" (must contain 0).
    tuner            "grid" or "optuna" (TPE on [eta_low, eta_high], endpoints first).
    learning_rates   candidates chosen at eta = 0 before the eta search.
    n_folds          score folds for the nested CV (ignored when folds are given).
    stop_fraction    share of each fit pool held out for early stopping.
    profile          TrainingProfile (Adam settings, batch, epochs, patience, dropout).
    """

    def __init__(
        self,
        n_intervals: int,
        architecture: str = "repo_lh4x128",
        eta_grid: Sequence[float] = (0.0, 1.0, 5.0, 10.0, 20.0, 40.0, 80.0),
        tuner: str = "grid",
        eta_low: float = 0.0,
        eta_high: float = 80.0,
        n_trials: int = 20,
        learning_rates: Sequence[float] = (5e-4, 1e-3),
        n_folds: int = 5,
        stop_fraction: float = 0.2,
        profile: TrainingProfile = TrainingProfile(),
        seed: int = 20260907,
        threads: int = 1,
        device: str = "cpu",
    ) -> None:
        if architecture not in ARCHITECTURES:
            raise ValueError(f"architecture must be one of {ARCHITECTURES}")
        if tuner not in ("grid", "optuna"):
            raise ValueError("tuner must be 'grid' or 'optuna'")
        if tuner == "grid" and not any(math.isclose(e, 0.0) for e in eta_grid):
            raise ValueError("eta_grid must contain 0 (the internal-only model)")
        self.n_intervals = int(n_intervals)
        self.architecture = architecture
        self.eta_grid = tuple(float(e) for e in eta_grid)
        self.tuner, self.eta_low, self.eta_high, self.n_trials = tuner, float(eta_low), float(eta_high), int(n_trials)
        self.learning_rates = tuple(float(v) for v in learning_rates)
        self.n_folds, self.stop_fraction, self.profile, self.seed = int(n_folds), float(stop_fraction), profile, int(seed)
        self.device = torch.device(device)
        torch.set_num_threads(max(1, int(threads)))
        self.cv_path_: List[Dict[str, Any]] = []

    # -- nested CV -----------------------------------------------------------
    def _contexts(self, x, indices, events, teacher, folds) -> List[Dict[str, Any]]:
        contexts = []
        for fold in sorted(set(int(f) for f in folds)):
            score = np.flatnonzero(folds == fold)
            pool = np.flatnonzero(folds != fold)
            fit, stop = stratified_stop_split(pool, events, self.stop_fraction, self.seed + fold * 11)
            scaler = make_scaler(x[fit])
            bundles = {
                name: _bundle(apply_scaler(x[pos], scaler), indices[pos], events[pos], teacher[pos], self.n_intervals, self.device)
                for name, pos in (("fit", fit), ("stop", stop), ("score", score))
            }
            set_seed(self.seed + fold * 100 + 1)
            template = make_model(self.architecture, x.shape[1], self.n_intervals, self.profile.dropout)
            contexts.append({"fold": fold, "n_score": len(score), "bundles": bundles,
                             "init": copy.deepcopy(template.state_dict()), "fit_seed": self.seed + fold * 100 + 2})
        return contexts

    def _pooled_score(self, contexts, profile: TrainingProfile, eta: float, stage: str) -> Tuple[float, List[int]]:
        """Pooled held-out hard NLL over the score folds (inf when any fold fails)."""
        weighted, n_total, epochs = 0.0, 0, []
        for c in contexts:
            row = {"stage": stage, "learning_rate": profile.learning_rate, "eta": eta, "fold": c["fold"], "status": "ok"}
            try:
                model, history = _train(self.architecture, profile, c["init"], c["bundles"]["fit"], eta, c["fit_seed"],
                                        self.device, stop_bundle=c["bundles"]["stop"])
                _, hard = _evaluate(model, c["bundles"]["score"], eta)
                if not math.isfinite(hard):
                    raise FloatingPointError("non-finite held-out hard NLL")
                weighted += hard * c["n_score"]
                n_total += c["n_score"]
                epochs.append(history["best_epoch"])
                row.update(score_hard_nll=hard, best_epoch=history["best_epoch"], stop_reason=history["stop_reason"])
            except Exception as exc:  # a failed fold disqualifies the candidate, never the run
                row.update(status=f"failed: {type(exc).__name__}: {exc}")
            self.cv_path_.append(row)
        pooled = weighted / n_total if len(epochs) == len(contexts) else math.inf
        for row in self.cv_path_:
            if row["stage"] == stage and row["eta"] == eta and row["learning_rate"] == profile.learning_rate:
                row["pooled_hard_nll"] = pooled
        return pooled, epochs

    def fit(self, x, duration_index, event, teacher_hazard, folds=None) -> "DiSKD":
        """x (n, p); duration_index (n,) 0-based; event (n,) 0/1; teacher_hazard (n, K); folds optional labels."""
        x = np.asarray(x, dtype=np.float64)
        indices = np.asarray(duration_index, dtype=np.int64)
        events = np.asarray(event, dtype=np.int64)
        teacher = np.asarray(teacher_hazard, dtype=np.float64)
        n = len(indices)
        if x.shape[0] != n or events.shape[0] != n or teacher.shape != (n, self.n_intervals):
            raise ValueError("inconsistent shapes: x (n,p), duration_index (n,), event (n,), teacher (n,K)")
        if (teacher < 0).any() or (teacher > 1).any():
            raise ValueError("teacher hazards must lie in [0, 1]")
        folds = stratified_folds(events, self.n_folds, self.seed) if folds is None else np.asarray(folds, dtype=np.int64)
        self.cv_path_ = []
        contexts = self._contexts(x, indices, events, teacher, folds)

        # stage 1: learning rate at eta = 0
        lr_scores = {lr: self._pooled_score(contexts, replace(self.profile, learning_rate=lr), 0.0, "learning_rate")
                     for lr in self.learning_rates}
        finite = [lr for lr, (v, _) in lr_scores.items() if math.isfinite(v)]
        if not finite:
            raise RuntimeError("no learning rate completed every score fold")
        self.learning_rate_ = min(finite, key=lambda lr: (lr_scores[lr][0], lr))
        profile = replace(self.profile, learning_rate=self.learning_rate_)

        # stage 2: eta
        results: Dict[float, Tuple[float, List[int]]] = {}
        if self.tuner == "grid":
            for eta in self.eta_grid:
                results[eta] = self._pooled_score(contexts, profile, eta, "eta")
        else:
            import optuna  # optional dependency

            sampler = optuna.samplers.TPESampler(seed=self.seed)
            study = optuna.create_study(direction="minimize", sampler=sampler)
            study.enqueue_trial({"eta": self.eta_low})
            study.enqueue_trial({"eta": self.eta_high})

            def objective(trial):
                eta = float(trial.suggest_float("eta", self.eta_low, self.eta_high))
                results[eta] = self._pooled_score(contexts, profile, eta, "eta")
                return results[eta][0]

            study.optimize(objective, n_trials=self.n_trials, n_jobs=1, catch=(Exception,))
        finite_etas = [e for e, (v, _) in results.items() if math.isfinite(v)]
        zero = [e for e in finite_etas if math.isclose(e, 0.0, abs_tol=1e-15)]
        if not finite_etas or not zero:
            raise RuntimeError("the eta = 0 trial (Internal-NN) must complete every score fold")
        self.eta_ = min(finite_etas, key=lambda e: (results[e][0], e))
        self.cv_pooled_hard_nll_ = {e: results[e][0] for e in results}
        internal_epochs = max(1, int(np.rint(np.median(results[zero[0]][1]))))
        diskd_epochs = max(1, int(np.rint(np.median(results[self.eta_][1]))))

        # final refits on the whole training set from one shared initialisation
        self.scaler_ = make_scaler(x)
        bundle = _bundle(apply_scaler(x, self.scaler_), indices, events, teacher, self.n_intervals, self.device)
        set_seed(self.seed + 90001)
        init = copy.deepcopy(make_model(self.architecture, x.shape[1], self.n_intervals, profile.dropout).state_dict())
        self.internal_model_, _ = _train(self.architecture, profile, init, bundle, 0.0, self.seed + 90002, self.device, epochs=internal_epochs)
        if self.eta_ == 0.0 and diskd_epochs == internal_epochs:
            self.model_ = copy.deepcopy(self.internal_model_)
        else:
            self.model_, _ = _train(self.architecture, profile, init, bundle, self.eta_, self.seed + 90002, self.device, epochs=diskd_epochs)
        self.epochs_ = {"internal": internal_epochs, "diskd": diskd_epochs}
        return self

    # -- prediction ----------------------------------------------------------
    def _model(self, which: str) -> nn.Module:
        if which == "diskd":
            return self.model_
        if which == "internal":
            return self.internal_model_
        raise ValueError("which must be 'diskd' or 'internal'")

    def predict(self, x, which: str = "diskd") -> Tuple[np.ndarray, np.ndarray]:
        """Interval hazards (clipped to [1e-7, 1-1e-7]) and survival S_k = prod_{j<=k}(1 - h_j)."""
        model = self._model(which)
        model.eval()
        with torch.no_grad():
            logits = model(torch.as_tensor(apply_scaler(x, self.scaler_), dtype=torch.float32, device=self.device))
            hazard = torch.sigmoid(logits).cpu().numpy().astype(np.float64)
        hazard = np.clip(hazard, HAZARD_CLIP, 1.0 - HAZARD_CLIP)
        return hazard, np.cumprod(1.0 - hazard, axis=1)

    def risk_score(self, x, which: str = "diskd") -> np.ndarray:
        """log of the cumulative hazard over all K intervals; higher = higher risk (for C-index)."""
        hazard, _ = self.predict(x, which)
        cumulative = np.clip(-np.log1p(-hazard).sum(axis=1), np.finfo(float).tiny, np.finfo(float).max)
        return np.log(cumulative)

    def hard_nll(self, x, duration_index, event, which: str = "diskd") -> float:
        """Mean per-subject discrete-time negative log-likelihood on new data."""
        hazard, _ = self.predict(x, which)
        target, mask = hard_targets_and_mask(np.asarray(duration_index), np.asarray(event), self.n_intervals)
        element = -(target * np.log(hazard) + (1.0 - target) * np.log1p(-hazard))
        return float(np.mean(np.sum(element * mask, axis=1)))


# ----------------------------------------------------------------------------
# Self-test on simulated data
# ----------------------------------------------------------------------------
def _self_test() -> int:
    """Small internal cohort (120 subjects) with the true model as external teacher."""
    rng = np.random.RandomState(3)
    n, p, K = 600, 6, 12
    beta = np.array([0.8, -0.8, 0.5, 0.0, 0.3, 0.0])
    alpha = np.linspace(-3.0, -1.5, K)                      # true cloglog baseline
    x = rng.normal(size=(n, p))
    hazard = 1.0 - np.exp(-np.exp(alpha[None, :] + (x @ beta)[:, None]))
    u = rng.uniform(size=(n, K))
    has_event = (u < hazard).any(axis=1)
    idx = np.where(has_event, np.argmax(u < hazard, axis=1), K - 1)
    event = has_event.astype(int)
    cens = rng.randint(0, K, size=n)
    censored = cens < idx
    idx[censored], event[censored] = cens[censored], 0
    d_h0 = np.diff(np.concatenate([[0.0], np.cumsum(np.exp(alpha))]))
    teacher = cox_teacher_hazard(x @ beta, d_h0)
    train, test = np.arange(0, 120), np.arange(400, n)

    fit = DiSKD(
        n_intervals=K, architecture="small_lh", eta_grid=(0.0, 2.0, 10.0, 40.0), learning_rates=(1e-3,),
        profile=TrainingProfile(max_epochs=100, patience=5), seed=7, threads=1,
    ).fit(x[train], idx[train], event[train], teacher[train])
    hazard_hat, survival_hat = fit.predict(x[test])
    assert hazard_hat.shape == (len(test), K) and survival_hat.shape == (len(test), K)
    assert np.isfinite(hazard_hat).all() and (np.diff(survival_hat, axis=1) <= 1e-12).all()
    assert fit.eta_ in fit.eta_grid and fit.learning_rate_ == 1e-3
    assert all(math.isfinite(v) for v in fit.cv_pooled_hard_nll_.values())
    assert len(fit.cv_path_) == 5 * (1 + len(fit.eta_grid))
    score = fit.risk_score(x[test])
    t, e = idx[test], event[test]
    num = den = 0.0
    for i in np.flatnonzero(e == 1):
        later = t > t[i]
        den += later.sum()
        num += (score[later] < score[i]).sum() + 0.5 * (score[later] == score[i]).sum()
    cindex = num / den
    nll_diskd = fit.hard_nll(x[test], t, e)
    nll_internal = fit.hard_nll(x[test], t, e, which="internal")
    print(f"self-test: n_train={len(train)} events={int(event[train].sum())} lr={fit.learning_rate_} "
          f"eta={fit.eta_} epochs={fit.epochs_} pooled CV NLL={ {k: round(v, 4) for k, v in fit.cv_pooled_hard_nll_.items()} }")
    print(f"           test C-index={cindex:.3f}  test NLL: diskd={nll_diskd:.4f} internal={nll_internal:.4f}")
    assert cindex > 0.6, "signal not recovered"
    print("diskd.py self-test: PASS")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    print(__doc__)
