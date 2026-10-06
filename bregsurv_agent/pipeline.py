"""The V3 run: profile -> declare -> verify -> derive -> fit all -> select -> report.

This is the whole agent. The language model appears at exactly two boundaries and
is OPTIONAL at both:

  boundary 1  elicitation -- and only on the path where the analyst stated the
              roles in prose. When they answer the numbered questions instead,
              :mod:`declaration` parses the reply deterministically and the model
              is not called at all.
  boundary 2  the report's prose -- and even there it writes no digits, only
              named references that :mod:`report_v3` resolves.

Everything between is deterministic. The model never names a column, never names
an estimator, and never chooses a tuning parameter. That is not a restriction
imposed on a weak model; it is what makes the analysis checkable.

Four artifacts come out of every run, and they are the product:
  1. the estimates and diagnostics, computed only by the verified library;
  2. a plain-language report a non-statistician can act on;
  3. an audit trail of the run;
  4. a runnable R script that reproduces the fit without the language model.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .declaration import Declaration, Verification, verify

_HERE = Path(__file__).resolve().parent
_MCP = _HERE.parent / "mcp"
# : how long the discrete row may take. DiSKD's nested CV is the slow
# member (ruling 2 accepts that); the R members finish in seconds.
DISCRETE_TIMEOUT_S = 4 * 3600
# the Cox row: ten members, five folds each, on the wider η grids of 2026-09-12 (MIUM, p = 48:
# ~8 min for the covariance release, of which the penalised Mahalanobis members are most);
# rbridge's default of 600 s was measured to be exceeded there. A bound, not a target.
COX_TIMEOUT_S = int(os.environ.get("BREGSURV_COX_TIMEOUT_S", "1800"))


def _default_run_r():
    from .rbridge import _run_r
    return _run_r


# THE ONE PLACE THAT DECIDES WHAT A DECLARATION FIELD IS.
#
# Three sites used to enumerate declaration fields by hand -- the approval hash,
# the trace, and repro.R -- with no reflection over the dataclass and no check
# that they agreed. `Declaration.external_model` has been escaping all three
# since it was added, silently, and that is the mild case: add `stratum_col` for
# a nested case-control design and the analyst approves a hash that does not
# cover the matched-set column while repro.R reproduces a DIFFERENT analysis and
# says it matched.
#
# Every field is CONFIGURATION -- it changes what gets fitted -- unless named
# here. Enumerating the exceptions inverts the failure mode: a field added later
# is hashed, traced and replayed by default, so the mistake available is a
# harmless over-inclusion rather than a silent escape.
_DECL_PROVENANCE_ONLY = frozenset({
    "source",   # which of the three declaration paths was taken
    "notes",    # human-readable trail, e.g. "preset A minus bmi"
    "sources",  # role -> how it was settled (quoted / inferred / checkbox);
                # the columns themselves are hashed, the story of them is not
    # The two file PATHS of the declaration. Their CONTENTS are hashed
    # (`external_data`, `test_data` fingerprints below), exactly as the cohort
    # is (`data`, never `data_path`); hashing the path string as well made the
    # same bytes at another location a different approval and defeated the
    # result cache across the benchmark's per-prompt directories.
    # Both stay in trace.json (asdict) and in repro.R's args block.
    "external_data_path",
    "test_data_path",
})


def _decl_config(decl: Declaration) -> Dict[str, Any]:
    """The configuration half of a declaration, by reflection, not by hand."""
    out: Dict[str, Any] = {}
    for f in fields(decl):
        if f.name in _DECL_PROVENANCE_ONLY:
            continue
        v = getattr(decl, f.name)
        out[f.name] = list(v) if isinstance(v, list) else v
    return out


class PipelineRefusal(RuntimeError):
    """The run stopped on purpose. `refusals` says what and why."""

    def __init__(self, message: str, refusals: List[Dict[str, Any]]):
        super().__init__(message)
        self.refusals = refusals


@dataclass
class RunResult:
    data_path: str
    data_expr: str
    external_beta_expr: Optional[str]
    external_Q_expr: Optional[str]
    profile: Dict[str, Any]
    declaration: Declaration
    verification: Verification
    candidates: Dict[str, Any]
    report: str
    provenance: Dict[str, Any]
    config_sha256: str
    seconds: float
    prose: Dict[str, str] = field(default_factory=dict)
    # kept last: a dataclass cannot have a defaulted field before an undefaulted
    # one, and everything above this line is required
    external_beta_inline: Optional[Dict[str, float]] = None
    # M5: the precision matrix by value, rows in external_beta_inline's order
    external_Q_inline: Optional[List[List[float]]] = None
    # : the external baseline hazard by value ({time, cumhaz}); read by
    # the discrete-time row only, recorded on every run that had one
    external_baseline_inline: Optional[Dict[str, List[float]]] = None
    # V4: the planner's plan (canonical form, reasons included); None when the V3 set was fitted
    plan: Optional[Dict[str, Any]] = None

    @property
    def has_network_members(self) -> bool:
        """Whether a DiSKD member (the Python estimator) was in the set."""
        return any(c.get("key") in ("internal_nn", "diskd")
                   for c in self.candidates.get("candidates", []))

    def save(self, outdir: str) -> Dict[str, str]:
        """Write the four artifacts. Returns the paths written."""
        # render_repro FAILS CLOSED, and it must do so before anything is on
        # disk. Rendering it last meant report.md and trace.json were already
        # written when the guard fired, leaving an artifact set that looks
        # complete, has no repro.R, and returns no path map to say so. The four
        # artifacts are the product; three of them is not a partial success.
        repro_text = render_repro(self)
        d = Path(outdir)
        d.mkdir(parents=True, exist_ok=True)
        paths = {}
        (d / "report.md").write_text(self.report, encoding="utf-8")
        paths["report"] = str(d / "report.md")
        trace = {
            "provenance": self.provenance,
            "config_sha256": self.config_sha256,
            "seconds": self.seconds,
            # Everything, provenance included -- the trace is the record of what
            # was declared, so a hand-written subset here is how a field goes
            # missing from the audit trail. asdict cannot forget one.
            "declaration": asdict(self.declaration),
            "verification": {
                "admissible": self.verification.admissible,
                "refusals": self.verification.refusals,
                "advisories": self.verification.advisories,
            },
            "facts": self.candidates["facts"],
            "partition": self.candidates["partition"],
            "criteria": self.candidates["criteria"],
            "candidates": self.candidates["candidates"],
            "selected": self.candidates["selected"],
            "linkage": self.candidates["linkage"],
            "prose": self.prose,
        }
        (d / "trace.json").write_text(
            json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
        paths["trace"] = str(d / "trace.json")
        (d / "repro.R").write_text(repro_text, encoding="utf-8")
        paths["repro"] = str(d / "repro.R")
        if self.has_network_members:
            # ruling 3: the network members are replayed by a Python
            # script beside repro.R, from the recorded seed, folds and settings
            (d / "repro_diskd.py").write_text(render_repro_diskd(self),
                                              encoding="utf-8")
            paths["repro_diskd"] = str(d / "repro_diskd.py")
        (d / "candidates.json").write_text(
            json.dumps(self.candidates, indent=2, ensure_ascii=False),
            encoding="utf-8")
        paths["candidates"] = str(d / "candidates.json")
        # V4: the Kaplan-Meier estimate of the target cohort, a figure in the report,
        # drawn by the harness from the declared roles; a full-cohort design only (a matched sample
        # has no follow-up time to draw). A failed figure never fails the artifacts.
        km = self.draw_km(d)
        if km:
            paths["km_pdf"], paths["km_png"] = km["pdf"], km["png"]
        return paths

    _KM_START, _KM_END = "<!-- km -->", "<!-- /km -->"

    def draw_km(self, d: Path, group_col: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Draw km_curve.{pdf,png} in `d` (pooled, by the declared strata, or by `group_col`, a column
        the analyst asked for) and put the figure into report.md in place of any earlier one. Returns
        the R result, or None when nothing was drawn (a matched design, or a failure). `error`
        carries the reason a requested grouping could not be drawn."""
        dec = self.declaration
        if not dec.time_col or not dec.event_col:
            return None
        d = Path(d)
        try:
            r = _default_run_r()("plot_km.R", {
                "data_path": self.data_path, "data_expr": self.data_expr,
                "time_col": dec.time_col, "event_col": dec.event_col,
                "event_value": str(dec.event_value), "stratum_col": dec.stratum_col or "",
                "group_col": group_col or "", "out_base": str(d / "km_curve")}, timeout_s=120)
        except Exception as exc:
            return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"} if group_col else None
        if not (isinstance(r, dict) and r.get("status") == "ok"):
            return r if group_col and isinstance(r, dict) else None
        by = r.get("grouped_by")
        how = {"levels": f" by `{by}`", "strata": f" by stratum (`{by}`)",
               "median": f" by `{by}`, split at its median"}.get(r.get("grouping") or "", "")
        band = "its pointwise 95% band and " if (r.get("n_strata") or 1) == 1 else ""
        note = (f"{self._KM_START}\nThe Kaplan-Meier estimate of the target cohort{how}, with {band}"
                "the number at risk, is drawn below and in `km_curve.pdf`.\n\n"
                f"![Kaplan-Meier estimate of the target cohort](km_curve.png)\n{self._KM_END}\n\n")
        md = d / "report.md"
        rep = md.read_text(encoding="utf-8") if md.is_file() else self.report
        a, b = rep.find(self._KM_START), rep.find(self._KM_END)
        if a >= 0 and b > a:
            rep = rep[:a] + note.rstrip("\n") + rep[b + len(self._KM_END):]
        else:
            k = rep.find("\n## 2.")
            rep = (rep[:k + 1] + note + rep[k + 1:]) if k >= 0 else rep + "\n\n" + note
        md.write_text(rep, encoding="utf-8")
        return r


# ------------------------------------------------------------------ provenance
def _r_version(run_r=None) -> Dict[str, str]:
    """C4a: what produced the numbers. Cannot be added retroactively.

    Written to a temp file rather than passed with `-e`: on Windows the embedded
    quotes in the expression are mangled before R ever sees them, and the failure
    is a bare "The system cannot find the path specified" that looks like a
    missing Rscript rather than a quoting problem.
    """
    out: Dict[str, str] = {}
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "ver.R"
            # The third field fingerprints the INSTALLED build (its lazy-load R code and its
            # compiled library). 2026-09-30: a recompile that keeps the version number is
            # invisible to the version string, and on 2026-09-21 the run cache served fits of
            # the pre-fix cox_indi_enet for that reason.
            f.write_text(
                'p <- find.package("BregSurv"); '
                'f <- c(file.path(p, "R", "BregSurv.rdb"), '
                'list.files(file.path(p, "libs"), pattern = "[.]so$", '
                'full.names = TRUE, recursive = TRUE)); '
                'cat(R.version.string, "|", '
                'as.character(packageVersion("BregSurv")), "|", '
                'paste(tools::md5sum(f[file.exists(f)]), collapse = ""), sep = "")',
                encoding="utf-8")
            r = subprocess.run(
                [_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                 str(f)],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                timeout=120)
        parts = (r.stdout or "").split("|")
        if len(parts) >= 2:
            out["r_version"] = parts[0].strip()
            out["bregsurv_version"] = parts[1].strip()
        if len(parts) == 3 and parts[2].strip():
            out["bregsurv_build"] = hashlib.sha256(
                parts[2].strip().encode("utf-8")).hexdigest()[:16]
    except Exception:
        pass
    return out


def _find_rscript():
    from .rbridge import _find_rscript as f
    return f()


def _git_sha(repo: Path) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _fingerprint(path: str) -> Dict[str, Any]:
    p = Path(path)
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"name": p.name, "bytes": p.stat().st_size, "sha256": h.hexdigest()}


def derive_candidate_keys(design: str, external_form: str,
                          discrete: bool = False,
                          has_baseline: bool = False) -> List[str]:
    """The members the facts admit, by name, without fitting anything.

    Pure enumeration, so it can run BEFORE the analyst is asked to confirm -- and
    it has to, because the confirmation is bound to it. `run_candidates.R` derives
    the same set from the same facts and the caller asserts they agree; a
    disagreement means the two derivations have drifted apart and the run aborts
    rather than fitting a set nobody approved.

    THE DISCRETE-TIME ROW is a third data fact, declared by the
    analyst (item 7), never read off the release. It is an INDEPENDENT
    candidate set (ruling 4): the two internal members always, and the
    borrowing members -- DiscreteKL, DiSKD and the teacher scored unchanged
    -- only when the external model brings a baseline hazard, which is what
    a Cox model needs to say anything about interval hazards. A published
    vector without a baseline, or another cohort's rows, borrows nothing
    here, and the report says so. Never ranked against the Cox row.
    """
    ncc = "nested" in design.lower() or "case-control" in design.lower()
    if discrete:
        if ncc:
            return []                      # refused by the gate before this
        keys = ["internal_discrete", "internal_nn"]
        coef = external_form.strip().lower().startswith("coefficients")
        if coef and has_baseline:
            keys = ["internal_discrete", "discretekl", "internal_nn", "diskd",
                    "external_discrete"]
        return keys
    # external_form was accepted and never read. It is read now, because with
    # nothing to borrow from, the KL, Mahalanobis and External-only members are
    # not merely pointless -- they are HARMFUL. Internal-only is manufactured as
    # `beta = zeros, eta = 0`, so with no external vector every borrowing member
    # degenerates to exactly the same internal fit: nine rows carrying one
    # number, an argmin breaking the tie arbitrarily, and a "borrowing" label
    # reported as the winner of a comparison that never happened.
    # The individual-level row of the library is a DIFFERENT set, not the
    # coefficient set plus one member: there is no cox_indi_ridge and no
    # ncc_indi_ridge, so the penalty axis has two levels rather than three, and
    # External-only means a model fitted on the external cohort rather than a
    # published vector read off a paper.
    if "individual" in external_form.lower():
        keys = ["internal", "indi", "internal_lasso", "indi_lasso"]
        if not ncc:
            # A full cohort's records also yield a fitted coefficient vector and its covariance,
            # so the whole coefficient-and-covariance set is admissible beside the composite
            # likelihood (2026-10-05; run_candidates.R fits the records and adds the same keys).
            keys += ["kl", "mahalanobis", "euclidean", "internal_ridge", "kl_ridge",
                     "mahalanobis_ridge", "euclidean_ridge", "kl_lasso", "mahalanobis_lasso",
                     "euclidean_lasso"]
            # no fixed-coefficient conditional-likelihood loss exists, so the
            # matched side cannot score a model it did not fit
            keys.append("external")
        return keys

    none_ext = external_form.strip().lower() in ("none", "", "no external information")
    # A released covariance ADDS the Mahalanobis metric; the Euclidean members
    # (identity on the covered coordinates) stay in the set beside it. The two
    # used to be alternatives, so the analyst who released more lost the member
    # that is best on MIUM (Euclidean lasso 0.643, covariance-weighted 0.620).
    # run_candidates.R derives the same keys; see has_Q there.
    has_cov = (not none_ext) and "covariance" in external_form.lower()
    keys = ["internal"]
    if not none_ext:
        keys += ["kl", "mahalanobis"] + (["euclidean"] if has_cov else [])
    if not ncc:                       # ridge exists for the Cox family only
        keys += ["internal_ridge"]
        if not none_ext:
            keys += ["kl_ridge", "mahalanobis_ridge"] + (["euclidean_ridge"] if has_cov else [])
    keys += ["internal_lasso"]
    if not none_ext:
        keys += (["kl_lasso", "mahalanobis_lasso"] + (["euclidean_lasso"] if has_cov else [])
                 + ["external"])
    return keys


def canonical_config(data_path: str, data_expr: str, decl: Declaration,
                     external_expr: Optional[str], seed: int, nfolds: int,
                     nlambda: int, candidate_keys: Optional[List[str]] = None,
                     external_Q_expr: Optional[str] = None,
                     external_beta_inline: Optional[Dict[str, float]] = None,
                     external_Q_inline: Optional[List[List[float]]] = None,
                     external_baseline_inline: Optional[Dict[str, List[float]]] = None,
                     plan: Optional[Dict[str, Any]] = None
                     ) -> str:
    """C3: the exact configuration, serialized deterministically, then hashed.

    The approval the analyst gives is bound to THIS string. It is re-derived at
    the moment of dispatch and compared; a mismatch aborts. The incident this
    prevents is on record: a ridge request answered by the unpenalized estimator,
    with the model reporting in prose that ridge had been applied.
    """
    payload = {
        "data": _fingerprint(data_path),
        "data_expr": data_expr,
        # By reflection, so a field added to Declaration cannot escape the
        # approval the analyst gives. See _DECL_PROVENANCE_ONLY.
        **_decl_config(decl),
        "external_expr": external_expr,
        # the covariance matrix changes the penalty geometry and the report's
        # "External information" row, and it used to be outside the hash
        # entirely -- so two analyses that differ in whether Q was supplied
        # hashed identically and one approval covered both.
        "external_Q_expr": external_Q_expr,
        # by VALUE, so the approval covers the numbers themselves rather than a
        # reference to wherever they happened to be read from
        "external_beta_inline": (dict(sorted(external_beta_inline.items()))
                                 if external_beta_inline else None),
        # M5: the precision matrix by value as well. Until now only
        # `external_Q_expr` was hashed, so two analyses that differed in the
        # matrix itself -- or in whether one was supplied by value at all --
        # hashed identically.
        "external_Q_inline": ([[float(x) for x in r] for r in external_Q_inline]
                              if external_Q_inline else None),
        # : the baseline hazard by value. It is what the discrete-time
        # row borrows from, so two analyses that differ in it must not hash
        # alike; on the Cox row it is recorded and unused, and hashing it
        # there costs nothing but a longer string.
        "external_baseline_inline": (
            {"time": [float(x) for x in external_baseline_inline["time"]],
             "cumhaz": [float(x) for x in external_baseline_inline["cumhaz"]]}
            if external_baseline_inline else None),
        # The external cohort by its CONTENTS, not by its filename. A path
        # string in the hash means the analyst approves "the file at /x/y",
        # and swapping what lives there afterwards keeps the same hash -- while
        # the internal data has been fingerprinted since C3 existed. Half the
        # data in an individual-level run would otherwise sit outside the
        # approval entirely.
        "external_data": (_fingerprint(decl.external_data_path)
                          if decl.external_data_path else None),
        # : the analyst's test file by its contents, for the same reason.
        # It never enters the selection, but the held-out table the report
        # prints is computed on it, so the run must be bound to those rows.
        "test_data": (_fingerprint(decl.test_data_path)
                      if decl.test_data_path else None),
        "seed": seed,
        "nfolds": nfolds,
        "nlambda": nlambda,
        # what will actually be fitted, not merely what was asked for
        "candidates": list(candidate_keys or []),
        # V4: the planner's plan in canonical form (plan.validate) -- every grid, covariate set, mask
        # and padding choice, so two plans that fit different things never hash alike. The reasons
        # are kept out: they explain the plan and change nothing that is fitted.
        "plan": _plan_for_hash(plan),
    }
    # A Declaration field named like one of the literal keys above would be
    # silently swallowed by the splat -- the field would vanish from the hash
    # while `_decl_config` reported it present, which is precisely the class of
    # silent escape this function was rewritten to end. Cheap to make loud.
    _lit = {"data", "data_expr", "external_expr", "external_Q_expr",
            "external_Q_inline", "external_baseline_inline", "external_data",
            "test_data", "seed", "nfolds", "nlambda", "candidates", "plan"}
    _clash = _lit & set(_decl_config(decl))
    if _clash:
        raise RuntimeError(
            "a Declaration field collides with a configuration key and would be "
            "dropped from the approval hash: " + ", ".join(sorted(_clash)))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def config_hash(cfg: str) -> str:
    return hashlib.sha256(cfg.encode("utf-8")).hexdigest()


def _plan_for_hash(plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The plan without its reasons: what is fitted, not why."""
    if not plan:
        return None
    out = {k: v for k, v in plan.items() if k not in ("reason", "members")}
    out["members"] = [{k: v for k, v in m.items() if k not in ("reason", "mask_evidence")}
                      for m in plan.get("members") or []]
    return out


def resolve_config(data_path: str, data_expr: str, declaration: Declaration,
                   external_beta_expr: Optional[str] = None,
                   external_Q_expr: Optional[str] = None,
                   external_beta_inline: Optional[Dict[str, float]] = None,
                   seed: int = 20260818, nfolds: int = 5, nlambda: int = 50,
                   external_Q_inline: Optional[List[List[float]]] = None,
                   external_baseline_inline: Optional[Dict[str, List[float]]] = None,
                   plan: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Any]:
    """The design, the external form, the candidate set, and the C3 hash.

    V4: with a `plan` (already in canonical form, plan.validate), the candidate set is the plan's
    members and the plan itself enters the hash.

    One function, called by :func:`run` and by whoever shows the analyst the
    consequence card, so that the hash bound at verify time and the hash
    checked at dispatch are computed by the same code rather than by two
    copies that could drift.
    """
    # Was `declaration.event_col is None`, on a field parse_reply can never
    # leave empty -- so the condition was always false and `design` was the
    # constant "full cohort", making the entire nested case-control branch of
    # derive_candidate_keys unreachable. The design is now read off the same
    # thing run_candidates.R reads it off: whether a follow-up time exists.
    design = declaration.design
    ext_form = ("individual-level data" if declaration.external_data_expr
                else "none" if not (external_beta_expr or external_beta_inline)
                else "coefficients and covariance"
                if (external_Q_expr or external_Q_inline)
                else "coefficients alone")
    has_baseline = bool(external_baseline_inline
                        and external_baseline_inline.get("time"))
    expected_keys = derive_candidate_keys(design, ext_form,
                                          discrete=declaration.discrete,
                                          has_baseline=has_baseline)
    if plan:
        expected_keys = [str(m["key"]) for m in plan.get("members") or []]
    cfg = canonical_config(data_path, data_expr, declaration, external_beta_expr,
                           seed, nfolds, nlambda, candidate_keys=expected_keys,
                           external_Q_expr=external_Q_expr,
                           external_beta_inline=external_beta_inline,
                           external_Q_inline=external_Q_inline,
                           external_baseline_inline=external_baseline_inline,
                           plan=plan)
    return {"design": design, "external_form": ext_form,
            "outcome_scale": declaration.outcome_scale,
            "has_baseline": has_baseline,
            "candidate_keys": expected_keys, "config": cfg,
            "sha256": config_hash(cfg)}


# -------------------------------------------------------------------- the run
def build_payload(data_path: str, data_expr: str, declaration: Declaration,
                  external_beta_expr: Optional[str] = None, external_Q_expr: Optional[str] = None,
                  external_beta_inline: Optional[Dict[str, float]] = None,
                  external_Q_inline: Optional[List[List[float]]] = None,
                  external_baseline_inline: Optional[Dict[str, List[float]]] = None,
                  seed: int = 20260818, nfolds: int = 5, nlambda: int = 50,
                  baseline_always: bool = False,
                  plan: Optional[Dict[str, Any]] = None,
                  reuse: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The object run_candidates.R (and, in V4, diagnose_transfer.R) reads. Factored out of `run`
    on 2026-10-02 unchanged, so the fit and the diagnostics read the same declaration the same way.
    `baseline_always` sends a released baseline hazard even when the Cox row is declared: the
    diagnostics card reports it, the Cox row ignores it."""
    exprs = declaration.as_exprs(data_expr)
    # event_value MUST travel with the expressions (2026-08-19; see run)
    payload = {"data_path": data_path, **exprs, "seed": seed, "nfolds": nfolds,
               "nlambda": nlambda, "event_value": declaration.event_value}
    if external_beta_expr:
        payload["beta_expr"] = external_beta_expr
    if external_beta_inline:
        payload["beta_inline"] = external_beta_inline
    if external_Q_inline:
        payload["Q_inline"] = external_Q_inline
    if external_Q_expr:
        payload["Q_expr"] = external_Q_expr
    # not an R expression, so it does not come through as_exprs
    if declaration.external_data_path:
        payload["external_data_path"] = declaration.external_data_path
    # : the grid the analyst declared, and the baseline hazard the
    # discrete row borrows from (the Cox row ignores both)
    if declaration.discrete:
        payload["discrete"] = declaration.discrete_spec()
    if (declaration.discrete or baseline_always) and external_baseline_inline \
            and external_baseline_inline.get("time"):
        payload["baseline_inline"] = {
            "time": [float(x) for x in external_baseline_inline["time"]],
            "cumhaz": [float(x) for x in external_baseline_inline["cumhaz"]]}
    # : the analyst's own test file -- scored, never selected on
    if declaration.has_test_data:
        payload["test_data"] = declaration.test_spec()
    # V4: the planner's plan, reasons stripped (run_candidates.R reads only what is fitted)
    if plan:
        payload["plan"] = _plan_for_hash(plan)
    # V4 item 2: rows an earlier call of this analysis fitted under the same plan entries, and the
    # partition they were scored on; not hashed -- they change what is recomputed, not what is fitted
    if reuse and reuse.get("rows"):
        payload["reuse"] = {"rows": list(reuse["rows"]), "partition": reuse.get("partition") or {}}
    return payload


DIAGNOSE_TIMEOUT_S = int(os.environ.get("BREGSURV_DIAGNOSE_TIMEOUT_S", "900"))


def diagnose(data_path: str, data_expr: str, declaration: Declaration,
             run_r: Optional[Callable] = None, **kw) -> Dict[str, Any]:
    """V4 work item 3: the transfer-diagnostics card for a verified declaration (training data only;
    the test file is never read). `kw` are the external-information arguments `run` takes."""
    run_r = run_r or _default_run_r()
    payload = build_payload(data_path, data_expr, declaration, baseline_always=True, **kw)
    payload.pop("test_data", None)
    try:
        return run_r("diagnose_transfer.R", payload, timeout_s=DIAGNOSE_TIMEOUT_S)
    except TypeError:
        return run_r("diagnose_transfer.R", payload)


def _admissible_on_row(plan: Dict[str, Any], design: str, ext_form: str,
                       baseline: Optional[Dict[str, List[float]]]) -> List[str]:
    from . import plan as _P
    return _P.admissible_keys(str(plan.get("row") or "cox"), design, ext_form,
                              bool(baseline and baseline.get("time")))


def fit_plan(data_path: str, data_expr: str, declaration: Declaration, plan: Dict[str, Any],
             reuse: Optional[Dict[str, Any]] = None, run_r: Optional[Callable] = None,
             seed: int = 20260818, nfolds: int = 5, nlambda: int = 50, **kw) -> Dict[str, Any]:
    """V4 item 4: one intermediate fit of the planner's loop -- the fitted table only, no report.
    The declaration was verified by the caller (`run` verifies again for the final result). `kw` are
    the external-information arguments `run` takes. Refuses when the fitted keys are not the plan's."""
    run_r = run_r or _default_run_r()
    payload = build_payload(data_path, data_expr, declaration, seed=seed, nfolds=nfolds,
                            nlambda=nlambda, plan=plan, reuse=reuse, **kw)
    # the planner decides from cross-validation on the cohort alone: an intermediate fit never
    # reads the analyst's test file, so no held-out number exists for the planner to see. The final
    # `run` scores every member on it, reused ones included.
    payload.pop("test_data", None)
    timeout = DISCRETE_TIMEOUT_S if declaration.discrete else COX_TIMEOUT_S
    try:
        res = run_r("run_candidates.R", payload, timeout_s=timeout)
    except TypeError:
        res = run_r("run_candidates.R", payload)
    if res.get("status") != "ok":
        raise PipelineRefusal("the planned members could not be fitted: " + str(res.get("message")),
                              [{"code": "fit_failed", "message": str(res.get("message"))}])
    want = sorted(str(m["key"]) for m in plan.get("members") or [])
    got = sorted(str(c["key"]) for c in res.get("candidates") or [])
    if got != want:
        raise PipelineRefusal("the fitted members are not the planned ones",
                              [{"code": "candidate_set_changed",
                                "message": f"planned {want}, fitted {got}"}])
    return res


def run(data_path: str, data_expr: str, declaration: Declaration,
        external_beta_expr: Optional[str] = None,
        external_Q_expr: Optional[str] = None,
        external_beta_inline: Optional[Dict[str, float]] = None,
        profile: Optional[Dict[str, Any]] = None,
        seed: int = 20260818, nfolds: int = 5, nlambda: int = 50,
        run_r: Optional[Callable] = None,
        write_prose: Optional[Callable[[Dict[str, Any]], Dict[str, str]]] = None,
        approved_config_sha256: Optional[str] = None,
        model_provenance: Optional[Dict[str, Any]] = None,
        external_Q_inline: Optional[List[List[float]]] = None,
        external_provenance: Optional[Dict[str, Any]] = None,
        session_provenance: Optional[Dict[str, Any]] = None,
        external_baseline_inline: Optional[Dict[str, List[float]]] = None,
        plan: Optional[Dict[str, Any]] = None,
        reuse: Optional[Dict[str, Any]] = None,
        plan_steps: Optional[List[Dict[str, Any]]] = None
        ) -> RunResult:
    """Execute one analysis end to end.

    V4: `plan` (canonical form, plan.validate) restricts and configures what is fitted; it enters the
    approval hash, the payload, the trace (with its reasons) and repro.R. Absent, the V3 set is fitted.
    `reuse` ({rows, partition}) hands run_candidates.R the members an earlier call of the same analysis
    fitted under the same entries, so they are not refitted; `plan_steps` is the planner's record
    (each decision, what it cost, what it changed), kept in the trace beside the final plan.

    `write_prose` is boundary 2. Omit it and the report is rendered from the
    tables alone, which is a complete and correct report -- the prose is
    connective tissue, not content.

    `model_provenance` is what the caller knows about the language model
    (`boundary.describe_model`) plus the boundary-1 call records it collected;
    boundary 2's own record is appended here. It lands in trace.json under
    `provenance.model`. Until 2026-09-11 the provenance named the R version and
    the package SHA and said nothing about the model that wrote the prose.
    """
    t0 = time.time()
    run_r = run_r or _default_run_r()

    if profile is None:
        profile = run_r("profile_columns.R", {
            "data_path": data_path, "data_expr": data_expr,
            **({"external_beta_expr": external_beta_expr}
               if external_beta_expr else {})})
        if profile.get("status") != "ok":
            raise PipelineRefusal(
                "the data could not be profiled: " + str(profile.get("message")),
                [{"code": "profile_failed", "message": str(profile.get("message"))}])

    # ---- verify the declaration, and run the admissibility gate -------------
    v = verify(profile, declaration, data_path, data_expr, run_r=run_r,
               external_baseline=external_baseline_inline)
    if not v.admissible:
        raise PipelineRefusal(
            "the analysis was refused before anything was fitted", v.refusals)

    # ---- C3: bind the approval to the resolved configuration ----------------
    # The set is derived BEFORE the approval, because the approval is bound to it.
    gate = v.gate or {}
    rc = resolve_config(data_path, data_expr, declaration, external_beta_expr,
                        external_Q_expr, external_beta_inline, seed, nfolds,
                        nlambda, external_Q_inline=external_Q_inline,
                        external_baseline_inline=external_baseline_inline, plan=plan)
    design, ext_form = rc["design"], rc["external_form"]
    expected_keys, cfg, sha = rc["candidate_keys"], rc["config"], rc["sha256"]
    if approved_config_sha256 is not None and approved_config_sha256 != sha:
        # Fail closed. What executes must be what was verified and shown. Since
        # 2026-09-11 no human stands between the card and the run; the caller
        # hashes the configuration at verify time and this check proves the
        # session was not mutated in between.
        raise PipelineRefusal(
            "the configuration changed between approval and execution; nothing "
            "was fitted", [{"code": "config_changed",
                            "message": f"approved {approved_config_sha256[:12]}, "
                                       f"about to run {sha[:12]}"}])

    # ---- derive the candidate set, fit all of it, select --------------------
    exprs = declaration.as_exprs(data_expr)
    # event_value MUST travel with the expressions. It is declared by the
    # analyst, printed on the consequence card, counted by the gate, and hashed
    # into the approval -- and until 2026-08-19 it was never sent here, while
    # run_candidates.R hard-coded 1 as the event. Declaring event_value="0" on a
    # 0/1 column therefore fitted the complement of the declared outcome with no
    # refusal anywhere, which is exactly the complement trap the whole
    # survival_event/survival_censored machinery exists to catch. It also made
    # C3's promise ("what executes is what was approved") false for this field
    # in the strongest way available: changing it changed the hash and changed
    # nothing about the run.
    payload = build_payload(data_path, data_expr, declaration, external_beta_expr=external_beta_expr,
                            external_Q_expr=external_Q_expr, external_beta_inline=external_beta_inline,
                            external_Q_inline=external_Q_inline,
                            external_baseline_inline=external_baseline_inline,
                            seed=seed, nfolds=nfolds, nlambda=nlambda, plan=plan, reuse=reuse)

    # ---- the result cache ------------------------------------
    # The fitted set is a deterministic function of the configuration C3 hashes
    # (data by content, every declared role, the external object by value, seed,
    # folds, grids inside run_candidates.R) -- proven on MIUM to 5e-12 against a
    # hand-run. So an identical configuration may reuse the fitted result
    # instead of refitting for minutes: `BREGSURV_RUN_CACHE=<dir>` keeps one
    # JSON per hash, keyed additionally by the package version and the
    # dispatcher's own bytes so a changed estimator or grid never serves a
    # stale result. Off unless the variable is set; the provenance records a
    # hit (`cache_hit`, and the seconds the original fit took). The report,
    # prose, trace and repro.R are still produced per run.
    cache_dir = os.environ.get("BREGSURV_RUN_CACHE")
    cache_key = None
    cache_hit = False
    if cache_dir:
        try:
            disp = (_HERE.parent / "mcp" / "r_scripts" / "run_candidates.R").read_bytes()
            rv = _r_version(run_r)
            cache_key = hashlib.sha256(
                (sha + "|" + hashlib.sha256(disp).hexdigest() + "|"
                 + str(rv.get("bregsurv_version")) + "|" + str(rv.get("r_version"))
                 + "|" + str(rv.get("bregsurv_build"))
                 ).encode("utf-8")).hexdigest()
            cpath = Path(cache_dir) / f"{cache_key}.json"
            if cpath.exists():
                # A file that does not parse is a MISS, not a reason to give
                # up on the key: on 2026-09-13 two arms of the benchmark fitted
                # the same configuration in the same minute, both wrote this
                # file with a plain truncate-and-write, the bytes interleaved,
                # and every later prompt with that configuration refitted for
                # four minutes because the parse error dropped the key and the
                # store below never ran (jobs 61039334/61039336 ran out of time
                # at 89 and 69 prompts). The write is now atomic (below) and a
                # corrupt file is simply replaced by the next fit.
                try:
                    cached = json.loads(cpath.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    cached = {}
                if cached.get("config_sha256") == sha and cached.get("result", {}).get("status") == "ok":
                    res = cached["result"]
                    cache_hit = True
        except Exception:
            cache_key, cache_hit = None, False
    if cache_hit:
        pass
    elif declaration.discrete:
        # the network members train for minutes, not seconds; a fake run_r
        # in a test may not take a timeout, so the argument is optional
        try:
            res = run_r("run_candidates.R", payload, timeout_s=DISCRETE_TIMEOUT_S)
        except TypeError:
            res = run_r("run_candidates.R", payload)
    else:
        try:
            res = run_r("run_candidates.R", payload, timeout_s=COX_TIMEOUT_S)
        except TypeError:
            res = run_r("run_candidates.R", payload)
    if cache_dir and cache_key and not cache_hit and res.get("status") == "ok" and not reuse:
        try:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            # write to a private temporary name and rename into place: os.replace
            # is atomic on one filesystem, so concurrent writers of the same key
            # leave one complete file, never a mixture (see the read above)
            final = Path(cache_dir) / f"{cache_key}.json"
            tmp = final.with_name(f".{cache_key}.{os.getpid()}.{time.time_ns()}.tmp")
            tmp.write_text(json.dumps(
                {"config_sha256": sha, "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "fit_seconds": round(time.time() - t0, 1), "result": res}), encoding="utf-8")
            os.replace(tmp, final)
        except Exception:
            pass
    if res.get("status") != "ok":
        raise PipelineRefusal(
            "the candidate set could not be fitted: " + str(res.get("message")),
            [{"code": "fit_failed", "message": str(res.get("message"))}])

    # The set that ran must be the set that was hashed. Two independent
    # derivations of the same two facts -- one here, one in R -- and if they ever
    # disagree the approval covered something else.
    got_keys = [c["key"] for c in res["candidates"]]
    if sorted(got_keys) != sorted(expected_keys):
        raise PipelineRefusal(
            "the fitted candidate set is not the one the configuration was "
            "approved against",
            [{"code": "candidate_set_changed",
              "message": f"approved {sorted(expected_keys)}, "
                         f"fitted {sorted(got_keys)}"}])

    # ---- boundary 2: prose, checked against the closed reference set --------
    from . import report_v3
    prose: Dict[str, str] = {}
    model_prov: Dict[str, Any] = dict(model_provenance or {})
    calls: List[Dict[str, Any]] = list(model_prov.pop("calls", []) or [])
    if write_prose is not None:
        refs = report_v3.build_references(res)
        # Boundary 2 decorates a verified result; it can never undo one. Until
        # 2026-09-13 an exception here (a truncated draft) surfaced as "The
        # analysis did not run" although the fit had completed and was cached.
        try:
            raw = write_prose({"references": refs, "result": res}) or {}
        except Exception as exc:
            raw = {"_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        if isinstance(raw.get("_error"), str):
            model_prov["prose_dropped"] = raw.pop("_error")
        # `_reasoning` is logged, never rendered, so the no-digits and
        # closed-reference checks do not apply to it -- those guard what the
        # analyst reads, and this is only ever read by an auditor.
        if isinstance(raw.get("_reasoning"), str):
            prose["_reasoning"] = raw.pop("_reasoning")
        if isinstance(raw.get("_call"), dict):
            calls.append(raw.pop("_call"))
        for k, text in raw.items():
            leaked = report_v3.check_no_digits(text)
            if leaked:
                # Dropped, not repaired: a retry at temperature 0 returns the
                # same draft, so there is nothing to retry.
                continue
            if report_v3.not_prose(text):
                model_prov.setdefault("prose_sections_not_prose", []).append(
                    {"section": k, "why": report_v3.not_prose(text)})
                continue
            try:
                report_v3.resolve(text, refs)
            except report_v3.UnknownReference:
                continue
            prose[k] = text

    report = report_v3.render(res, prose=prose, declaration=declaration,
                              external=external_provenance,
                              plan=plan, plan_steps=plan_steps,
                              n_admissible=(len(_admissible_on_row(plan, design, ext_form, external_baseline_inline))
                                            if plan else None))

    prov = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "data": _fingerprint(data_path),
        "seed": seed, "nfolds": nfolds, "nlambda": nlambda,
        "bregsurv_git_sha": _git_sha(_HERE.parent),
        **_r_version(run_r),
    }
    if declaration.test_data_path:
        # : the analyst's test file by content; its rows fixed the
        # held-out table and nothing else
        prov["test_data"] = _fingerprint(declaration.test_data_path)
    if cache_dir:
        prov["result_cache"] = {"hit": cache_hit, "key": cache_key}
    if model_prov or calls:
        toks = [c.get("prompt_tokens") for c in calls
                if isinstance(c.get("prompt_tokens"), int)]
        model_prov["calls"] = calls
        # the number the 32K window constrains: the largest single prompt
        model_prov["peak_prompt_tokens"] = max(toks) if toks else None
        model_prov["n_calls"] = len(calls)
        model_prov["truncated_calls"] = sum(
            1 for c in calls if c.get("finish_reason") == "length")
        prov["model"] = model_prov
    if external_provenance:
        # M5: file fingerprint, format, which table/column was what, whether a
        # hazard ratio was logged or a covariance inverted, the assignment
        # and its model call. What the coefficients ARE, not just their values.
        prov["external"] = external_provenance
    if session_provenance:
        # component 3: the phase walk, turns and questions of the session
        # that reached this run -- "completed in one message" and "questions
        # per request" are read from here at evaluation time
        prov["session"] = session_provenance
    if plan:
        # V4: the plan as the planner gave it, reasons included, and what it cost
        from . import plan as _plan
        prov["plan"] = {"plan": plan, "cost_units": _plan.plan_cost(plan)}
        if plan_steps:
            prov["plan"]["steps"] = plan_steps
            prov["plan"]["units_spent"] = sum(int(st.get("units") or 0) for st in plan_steps
                                              if st.get("step") == "fit")
    # component 11: the report discloses every model call it involved
    report = report + "\n\n" + report_v3.render_model_use(prov)

    return RunResult(data_path=data_path, data_expr=data_expr,
                     external_beta_expr=external_beta_expr,
                     external_Q_expr=external_Q_expr,
                     external_beta_inline=external_beta_inline,
                     external_Q_inline=external_Q_inline,
                     external_baseline_inline=external_baseline_inline,
                     profile=profile, declaration=declaration, verification=v,
                     candidates=res, report=report, provenance=prov,
                     config_sha256=sha, seconds=round(time.time() - t0, 1),
                     prose=prose, plan=plan)


# ------------------------------------------------------------------- repro.R
def render_repro(r: RunResult) -> str:
    """A script that reproduces the fit from the estimator library alone.

    It re-runs the same dispatcher with the same arguments and then CHECKS the
    fold assignment against the one recorded, rather than asserting that it
    matched. If the split differs, the losses are not the losses that were
    reported, and it stops instead of printing a convincing lookalike.
    """
    d = r.declaration
    c = r.candidates
    ex = d.as_exprs(r.data_expr)
    folds = c["partition"].get("folds") or []

    # FAIL CLOSED ON AN UNREPLAYED FIELD. repro.R re-runs run_candidates.R and
    # nothing else, so not every configuration field has somewhere to go -- but
    # "no obvious home" must not silently become "left out". Anything not
    # emitted below and not excused here stops generation, which turns adding a
    # Declaration field into a decision instead of an omission.
    #
    # This is not hypothetical: `event_value` was absent from the args block
    # until 2026-08-19, so once the fitter began honouring it a replay of any
    # run that declared the other level would have reproduced a DIFFERENT model
    # and reported that the fold assignment matched.
    _replayed = {"time_col", "event_col", "covariates", "event_value",
                 "stratum_col", "external_data_expr",
                 "interval_width", "n_intervals", "time_is_interval_index",
                 "test_data_expr"}
    _excused = {
        "covariates_time_zero":
            "an input to the admissibility gate, which repro.R does not re-run; "
            "the run being reproduced was already gated and refused if it failed",
        "external_model":
            "a human-readable label for the external model, not an argument to "
            "any estimator",
    }
    _loose = set(_decl_config(d)) - _replayed - set(_excused)
    if _loose:
        raise RuntimeError(
            "repro.R would silently drop these declaration fields: "
            + ", ".join(sorted(_loose))
            + ". Emit them in the args block below, or excuse them in _excused "
              "with the reason. A reproduction script that omits part of the "
              "declaration reproduces a different analysis.")
    lines = [
        "#!/usr/bin/env Rscript",
        "# repro.R -- reproduces one BregSurv agent analysis.",
        "#",
        f"# Generated:  {r.provenance.get('generated_at')}",
        f"# R:          {r.provenance.get('r_version', 'unknown')}",
        f"# BregSurv:   {r.provenance.get('bregsurv_version', 'unknown')}"
        f"  (git {r.provenance.get('bregsurv_git_sha') or 'unknown'})",
        f"# Data:       {r.provenance['data']['name']}  "
        f"sha256 {r.provenance['data']['sha256'][:16]}...",
        f"# Config:     sha256 {r.config_sha256[:16]}...",
        "#",
        "# The language model is not involved in anything below.",
        *( ["#",
            "# Discrete-time row: the network members (Internal-NN, DiSKD) are refitted",
            "# through mcp/py_scripts/run_diskd.py. Set BREGSURV_PYTHON to a Python",
            "# with numpy and torch (default: python3 on PATH), or",
            "# BREGSURV_SKIP_PYTHON=1 to replay the R members only. repro_diskd.py,",
            "# beside this script, replays the network members without R."]
           if d.discrete else [] ),
        "",
        'DATA <- commandArgs(TRUE)[1]',
        'if (is.na(DATA)) stop("usage: Rscript repro.R <path to the data file>")',
        'SCRIPTS <- Sys.getenv("BREGSURV_R_SCRIPTS", unset = "mcp/r_scripts")',
        'if (!dir.exists(SCRIPTS)) stop("set BREGSURV_R_SCRIPTS to mcp/r_scripts")',
        "",
        "suppressPackageStartupMessages(library(jsonlite))",
        "",
        "args <- list(",
        f'  data_path   = DATA,',
        # every expression as_exprs produced, whatever the design -- a hand
        # written z/time/delta triple cannot replay a matched run, which needs
        # y_expr and stratum_expr instead
        *[f'  {k:<11} = {json.dumps(v)},' for k, v in ex.items()],
        # which level of the event column the analyst said was the event; the
        # fitter recodes on it, so a replay without it is a different analysis
        f'  event_value = {json.dumps(d.event_value)},',
        *( [f'  beta_expr   = {json.dumps(r.external_beta_expr)},']
           if r.external_beta_expr else [] ),
        # the numbers themselves, so the replay needs nothing but this script
        # and the data file -- not whatever file the coefficients came from.
        # `list(...)`, not `c(...)`: jsonlite drops the names of an atomic
        # vector, so a `c("age" = 0.5, ...)` reached run_candidates.R as an
        # UNNAMED vector and was matched by POSITION -- a replay of a
        # name-matched run fitted the coefficients onto the wrong variables,
        # or stopped on a length mismatch. A named list serialises as an
        # object, which is exactly what the app sends. (while
        # adding Q_inline; the inline path had never been replayed by a test.)
        # In the object's own order, NOT sorted: Q_inline's rows follow it.
        *( ['  beta_inline = list(' + ", ".join(
               f"{json.dumps(k)} = {v!r}"
               for k, v in r.external_beta_inline.items()) + '),']
           if r.external_beta_inline else [] ),
        *( [f'  Q_expr      = {json.dumps(r.external_Q_expr)},']
           if r.external_Q_expr else [] ),
        # the precision matrix by value, one row per line, in beta's order
        *( ['  Q_inline    = list(' + ", ".join(
               "c(" + ", ".join(repr(float(x)) for x in row) + ")"
               for row in r.external_Q_inline) + '),']
           if r.external_Q_inline else [] ),
        *( [f'  external_data_path = {json.dumps(d.external_data_path)},']
           if d.external_data_path else [] ),
        # : the declared grid, and the baseline hazard by value, so the
        # discrete row replays from this script and the data file alone
        *( ['  discrete    = list(n_intervals = ' + str(int(d.n_intervals))
            + ', width = ' + ("NULL" if d.time_is_interval_index
                              else repr(float(d.interval_width)))
            + ', time_is_index = ' + ("TRUE" if d.time_is_interval_index else "FALSE")
            + '),']
           if d.discrete else [] ),
        *( ['  baseline_inline = list(time = c(' + ", ".join(
                repr(float(x)) for x in r.external_baseline_inline["time"])
            + '), cumhaz = c(' + ", ".join(
                repr(float(x)) for x in r.external_baseline_inline["cumhaz"]) + ')),']
           if d.discrete and r.external_baseline_inline else [] ),
        # : the analyst's test file, by the same path and column names,
        # so the replay prints the same held-out table (it selects on nothing)
        *( ['  test_data   = list('
            + (f'path = {json.dumps(d.test_data_path)}, ' if d.test_data_path else '')
            + f'expr = {json.dumps(d.test_data_expr)}, '
            + f'time_col = {json.dumps(d.time_col)}, '
            + f'event_col = {json.dumps(d.event_col)}, '
            + 'covariates = list(' + ", ".join(json.dumps(x) for x in d.covariates) + ')'
            + (f', stratum_col = {json.dumps(d.stratum_col)}' if d.stratum_col else '')
            + '),']
           if d.has_test_data else [] ),
        # V4: the planner's plan, exactly as it was fitted (reasons stripped), so the replay fits the
        # same members on the same grids and variable sets with no model running
        *( ['  plan        = jsonlite::fromJSON(' + json.dumps(json.dumps(_plan_for_hash(r.plan)))
            + ', simplifyVector = FALSE),']
           if r.plan else [] ),
        f'  seed        = {c["partition"]["seed"]},',
        f'  nfolds      = {c["partition"]["nfolds"]},',
        f'  nlambda     = {r.provenance["nlambda"]}',
        ")",
        "",
        "in_f <- tempfile(fileext = '.json'); out_f <- tempfile(fileext = '.json')",
        # digits = NA: jsonlite's default of four significant digits handed
        # run_candidates.R a ROUNDED external vector, so every replay refitted a
        # different model and the held-out check failed at the 1e-5 level (found
        # by replaying all 375 scripts, 2026-09-14). The Python side writes the
        # payload at full precision; the script must too.
        "writeLines(toJSON(args, auto_unbox = TRUE, null = 'null', digits = NA), in_f)",
        "cmd <- paste(shQuote(file.path(R.home('bin'), 'Rscript')),",
        "             shQuote(file.path(SCRIPTS, 'run_candidates.R')),",
        "             shQuote(in_f), shQuote(out_f))",
        "system(cmd)",
        "res <- fromJSON(out_f, simplifyVector = FALSE)",
        "",
        "if (!identical(res$status, 'ok')) {",
        "  stop('the replay could not be fitted: ', res$message, call. = FALSE)",
        "}",
        "",
        "# the split that was actually used, recorded at the time",
        # An empty vector made `identical(integer(0), integer(0))` true and
        # the script printed "fold assignment REPRODUCED" having compared
        # nothing -- a check that fails OPEN, which is worse than no check,
        # because the line it prints is the evidence someone would cite.
        "expected <- c(" + ", ".join(str(int(x)) for x in folds) + ")",
        "if (length(expected) == 0L) {",
        "  stop(paste('this run recorded no fold assignment, so the replay ',",
        "       'cannot be checked against it. The losses below may or may not ',",
        "       'be the ones that were reported.'), call. = FALSE)",
        "}",
        "got <- as.integer(unlist(res$partition$folds))",
        "if (!identical(got, as.integer(expected))) {",
        "  stop(sprintf(paste0('the replayed fold assignment differs from the ',",
        "       'recorded one (%d of %d subjects moved). The losses printed ',",
        "       'below are NOT the ones that were reported.'),",
        "       sum(got != expected), length(expected)), call. = FALSE)",
        "}",
        "cat(sprintf('fold assignment REPRODUCED (%d subjects, %d folds)\\n',",
        "            length(got), length(unique(got))))",
        "",
        "for (cand in res$candidates) {",
        "  cat(sprintf('%-30s %-10s %s\\n', cand$label, cand$status,",
        "      if (is.null(cand$loss)) '-' else sprintf('%.6f', cand$loss)))",
        "}",
        "cat(sprintf('\\nselected: %s (loss %.6f)\\n',",
        "            res$selected$label, res$selected$loss))",
        "",
        f"# recorded at the time: {c['selected']['label']} "
        f"(loss {c['selected']['loss']:.6f})",
    ]
    if d.has_test_data and c.get("test_data"):
        # the held-out table, and a CHECK of the selected member's four
        # numbers against the ones that were reported -- same rows, same
        # coefficients, same library calls, so they must agree to rounding
        ho = (c.get("selected") or {}).get("holdout") or {}
        lines += [
            "",
            "cat('\\nheld-out performance on the test data (reported only):\\n')",
            "for (cand in res$candidates) {",
            "  h <- cand$holdout; if (is.null(h)) next",
            "  f <- function(x) if (is.null(x) || is.na(x)) '-' else sprintf('%.6f', x)",
            "  cat(sprintf('%-30s C %s  loss %s  IBS %s  tdAUC %s\\n', cand$label,",
            "      f(h$cindex), f(h$loss), f(h$ibs), f(h$tdauc)))",
            "}",
            "expected_ho <- list(" + ", ".join(
                f"{k} = {('NA' if ho.get(k) is None else repr(float(ho[k])))}"
                for k in ("cindex", "loss", "ibs", "tdauc")) + ")",
            "got_ho <- res$selected$holdout",
            "moved <- character(0)",
            "for (k in names(expected_ho)) {",
            "  a <- expected_ho[[k]]; b <- got_ho[[k]]",
            "  same <- (is.na(a) && (is.null(b) || is.na(b))) ||",
            "          (!is.na(a) && !is.null(b) && !is.na(b) && abs(a - b) <= 1e-8)",
            "  if (!same) moved <- c(moved, k)",
            "}",
            "if (length(moved)) {",
            "  stop(sprintf('the replayed held-out numbers differ from the recorded ones (%s).',",
            "       paste(moved, collapse = ', ')), call. = FALSE)",
            "}",
            "cat('held-out numbers of the selected model REPRODUCED\\n')",
        ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- repro_diskd.py
def render_repro_diskd(r: RunResult) -> str:
    """A Python script that replays the network members of the discrete row
    (ruling 3, ): Internal-NN and DiSKD refitted from the recorded seed,
    fold assignment, teacher and training settings, and compared with the
    numbers that were reported. It needs only the data file, numpy, pandas,
    torch and the agent's `bregsurv_agent/discrete/diskd.py`; R is not
    involved. `repro.R` replays every member through the same R dispatcher,
    including these two through the bridge, so the two scripts agree by
    construction; this one exists so that the Python estimator can be
    replayed without R at all.
    """
    d = r.declaration
    c = r.candidates
    disc = c.get("discrete") or {}
    teacher = disc.get("teacher") or {}
    rows = {x["key"]: x for x in c.get("candidates", [])}
    settings = ((rows.get("diskd") or rows.get("internal_nn") or {}).get("settings")
                or {})
    folds = c["partition"].get("folds") or []
    recorded = {k: {"status": rows[k].get("status"), "loss": rows[k].get("loss"),
                    "eta": rows[k].get("eta"),
                    "learning_rate": (rows[k].get("settings") or {}).get("learning_rate_selected"),
                    "epochs": (rows[k].get("settings") or {}).get("epochs")}
                for k in ("internal_nn", "diskd") if k in rows}
    lines = [
        "#!/usr/bin/env python3",
        "# repro_diskd.py -- replays the network members (Internal-NN, DiSKD) of",
        "# one BregSurv agent analysis on the discrete-time row, without R.",
        "#",
        f"# Generated:  {r.provenance.get('generated_at')}",
        f"# Data:       {r.provenance['data']['name']}  "
        f"sha256 {r.provenance['data']['sha256'][:16]}...",
        f"# Config:     sha256 {r.config_sha256[:16]}...",
        "#",
        "# Usage:  python repro_diskd.py <path to the data file>",
        "# Needs numpy, pandas, torch, and the agent's estimator module",
        "# bregsurv_agent/discrete/diskd.py -- run from the repository root or set",
        "# BREGSURV_REPO to it. The language model is not involved in anything below.",
        "",
        "import json, math, os, sys",
        "from pathlib import Path",
        "import numpy as np",
        "import pandas as pd",
        "",
        "DATA = sys.argv[1] if len(sys.argv) > 1 else None",
        'if not DATA: sys.exit("usage: python repro_diskd.py <path to the data file>")',
        'sys.path.insert(0, os.environ.get("BREGSURV_REPO", "."))',
        "from bregsurv_agent.discrete.diskd import DiSKD, TrainingProfile, cox_teacher_hazard",
        "",
        "# --- the declaration, as recorded ---------------------------------------",
        f"TIME_COL, EVENT_COL, EVENT_VALUE = {d.time_col!r}, {d.event_col!r}, {d.event_value!r}",
        f"COVARIATES = {list(d.covariates)!r}",
        f"N_INTERVALS, WIDTH, TIME_IS_INDEX = {int(d.n_intervals)}, "
        f"{None if d.time_is_interval_index else float(d.interval_width)!r}, "
        f"{bool(d.time_is_interval_index)!r}",
        "# the teacher as the harness built it (external coefficients aligned by",
        "# name, zero elsewhere; baseline increments over the K intervals)",
        f"BETA_EXT = {json.dumps(teacher.get('beta')) if teacher else 'None'}",
        f"DH0 = {json.dumps(teacher.get('dH0')) if teacher else 'None'}",
        "# the fold assignment every member was scored on (row order of the file)",
        "FOLDS = np.array(" + json.dumps([int(x) for x in folds]) + ")",
        f"SETTINGS = {json.dumps(settings)}",
        f"RECORDED = {json.dumps(recorded)}",
        "",
        "# --- the data, read the way the run read it -------------------------------",
        "ext = Path(DATA).suffix.lower()",
        'if ext in (".csv", ".tsv", ".txt"):',
        '    df = pd.read_csv(DATA, sep="," if ext == ".csv" else "\\t")',
        'elif ext == ".parquet":',
        "    df = pd.read_parquet(DATA)",
        'elif ext in (".xlsx", ".xls"):',
        "    df = pd.read_excel(DATA)",
        "else:",
        '    sys.exit("this script reads csv/tsv/parquet/xlsx; for an R data file run '
        'repro.R, which replays every member through R")',
        "x = df[COVARIATES].to_numpy(dtype=float)",
        "t = df[TIME_COL].to_numpy(dtype=float)",
        "e = (df[EVENT_COL].to_numpy(dtype=float) == float(EVENT_VALUE)).astype(int)",
        "if len(FOLDS) != len(t):",
        '    sys.exit(f"the file has {len(t)} rows but {len(FOLDS)} fold labels were '
        'recorded: not the same data")',
        "",
        "# --- the grid, exactly as run_candidates.R cut it -------------------------",
        "if TIME_IS_INDEX:",
        "    idx0 = np.rint(t).astype(int) - 1",
        "else:",
        "    raw = np.floor(t / WIDTH).astype(int)",
        "    beyond = raw >= N_INTERVALS",
        "    idx0 = np.minimum(raw, N_INTERVALS - 1)",
        "    e = np.where(beyond, 0, e)          # censored at the horizon",
        "if BETA_EXT is not None and DH0 is not None:",
        "    beta = np.array([float(BETA_EXT.get(c, 0.0)) for c in COVARIATES])",
        "    teacher = cox_teacher_hazard(x @ beta, np.array(DH0, dtype=float))",
        "    eta_grid = tuple(SETTINGS.get('eta_grid', (0.0,)))",
        "else:",
        "    teacher = np.zeros((len(t), N_INTERVALS))",
        "    eta_grid = (0.0,)",
        "",
        "# --- the refit ---------------------------------------------------------",
        "prof = SETTINGS.get('profile') or {}",
        "profile = TrainingProfile(**{k: (tuple(v) if isinstance(v, list) else v)",
        "                             for k, v in prof.items()})",
        "model = DiSKD(n_intervals=N_INTERVALS,",
        "              architecture=SETTINGS.get('architecture', 'repo_lh4x128'),",
        "              eta_grid=eta_grid,",
        "              learning_rates=tuple(SETTINGS.get('learning_rates', (5e-4, 1e-3))),",
        "              n_folds=int(SETTINGS.get('n_folds', 5)),",
        "              stop_fraction=float(SETTINGS.get('stop_fraction', 0.2)),",
        "              profile=profile, seed=int(SETTINGS.get('seed', 20260907)),",
        "              threads=int(SETTINGS.get('threads', 1))",
        "              ).fit(x, idx0, e, teacher, folds=FOLDS)",
        "",
        "got = {",
        '    "internal_nn": {"loss": model.cv_pooled_hard_nll_.get(0.0), "eta": 0.0,',
        '                    "learning_rate": model.learning_rate_,',
        '                    "epochs": model.epochs_["internal"]},',
        '    "diskd": {"loss": model.cv_pooled_hard_nll_.get(model.eta_), "eta": model.eta_,',
        '              "learning_rate": model.learning_rate_,',
        '              "epochs": model.epochs_["diskd"]},',
        "}",
        "ok = True",
        "for k, rec in RECORDED.items():",
        "    g = got[k]",
        '    same = (rec.get("loss") is not None and g["loss"] is not None',
        '            and math.isclose(float(rec["loss"]), float(g["loss"]), rel_tol=1e-6, abs_tol=1e-8)',
        '            and float(rec.get("eta") or 0.0) == float(g["eta"]))',
        "    ok = ok and same",
        '    print(f"{k:<12} recorded loss {rec.get(\'loss\')} eta {rec.get(\'eta\')}  |  '
        'replayed loss {g[\'loss\']:.6f} eta {g[\'eta\']}  ->  {\'REPRODUCED\' if same else \'DIFFERS\'}")',
        'print("network members " + ("REPRODUCED" if ok else "NOT reproduced -- the numbers '
        'above are not the ones that were reported"))',
        "sys.exit(0 if ok else 1)",
    ]
    return "\n".join(lines) + "\n"
