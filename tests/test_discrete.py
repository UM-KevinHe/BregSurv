"""The discrete-time row (master memory ): DiscreteKL + DiSKD in the agent.

What is checked, in order:
  A. without R -- the candidate-key matrix, item 7's parser, `complete`'s
     never-inferred rule, the question, the C3 hash, repro.R / repro_diskd.py,
     the report's discrete rendering, the declaration's own checks;
  B. with R -- the profiler's time-grid facts and trigger, the gate's discrete
     checks (horizon, index, baseline coverage, matched design), the R members
     through run_candidates.R with the network members skipped, and then the
     whole pipeline with DiSKD through the bridge (ruling 2: the smoke test
     must show the agent can call it), the artifacts, and both replays.

Run:  python mcp/test_discrete.py            (from the repository root)
      BREGSURV_DISCRETE_FAST=1 ...            skips the DiSKD end-to-end block
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent.rbridge import _run_r, _find_rscript, R_SCRIPTS  # noqa: E402
from bregsurv_agent import pipeline, report_v3, external as X  # noqa: E402
from bregsurv_agent.declaration import (Declaration, DeclarationError, complete,  # noqa: E402
                                        parse_reply, render_question, verify,
                                        _own_checks)

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def hdr(t):
    print(f"\n{t}")


# --------------------------------------------------------------- the fixture
K, WIDTH = 8, 7.0
COLS = ["age", "egfr", "albumin", "donor_age"]
BETA_TRUE = [0.7, -0.6, -0.4, 0.3]
ALPHA = [-3.0 + 0.2 * k for k in range(K)]          # cloglog baseline per interval


def make_fixture(td: Path, n: int = 240, seed: int = 5):
    """A grouped-time cohort in DAYS on a weekly grid, plus its interval index,
    plus the true model as an external release (coefficients on three of the
    four columns and one name we lack, and the baseline cumulative hazard)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        x = [rng.gauss(0, 1) for _ in COLS]
        lp = sum(b * v for b, v in zip(BETA_TRUE, x))
        bin_, ev = K, 0
        for k in range(K):
            h = 1 - math.exp(-math.exp(ALPHA[k] + lp))
            if rng.random() < h:
                bin_, ev = k + 1, 1
                break
        c = rng.randint(1, K)                          # censoring interval
        if c < bin_:
            bin_, ev = c, 0
        days = int((bin_ - 1) * WIDTH + rng.random() * WIDTH)   # floor(days/7)+1 == bin
        if rng.random() < 0.06:                        # observed past the horizon
            days = int(K * WIDTH + rng.random() * 30)
            ev = rng.randint(0, 1)
        rows.append(x + [days, ev, min(bin_, K), i])
    csv = td / "cohort.csv"
    with open(csv, "w", encoding="utf-8") as fh:
        fh.write(",".join(COLS + ["followup_days", "died", "week_index", "patient_id"]) + "\n")
        for r in rows:
            fh.write(",".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in r) + "\n")
    # the release: coefficients on three columns + a name we lack, and the
    # baseline cumulative hazard as a step function with one jump per interval
    d_h0 = [math.exp(a) for a in ALPHA]
    cum, cumhaz = 0.0, []
    for h in d_h0:
        cum += h
        cumhaz.append(cum)
    ext = {"coefficients": [{"variable": "age", "coef": BETA_TRUE[0]},
                            {"variable": "egfr", "coef": BETA_TRUE[1]},
                            {"variable": "donor_age", "coef": BETA_TRUE[3]},
                            {"variable": "hla_mismatch", "coef": 0.2}],
           "baseline_hazard": [{"time": (k + 0.5) * WIDTH, "cumulative_hazard": cumhaz[k]}
                               for k in range(K)]}
    ext_path = td / "release.json"
    ext_path.write_text(json.dumps(ext, indent=1), encoding="utf-8")
    return str(csv), str(ext_path), rows


def fake_profile(possible_discrete=True, possible_ncc=False):
    cols = [{"name": c, "type": "numeric", "n_missing": 0, "pct_missing": 0,
             "n_distinct": 200, "can_be_time": True, "can_be_event": False,
             "can_be_covariate": True, "can_be_stratum": False,
             "summary": {"min": -3, "median": 0, "max": 3}} for c in COLS]
    cols.append({"name": "followup_days", "type": "integer", "n_missing": 0, "pct_missing": 0,
                 "n_distinct": 60, "can_be_time": True, "can_be_event": False,
                 "can_be_covariate": True, "can_be_stratum": False,
                 "summary": {"min": 0, "median": 20, "max": 80},
                 "time_grid": {"integer_valued": True, "step": 1, "n_distinct": 60,
                               "coarse": possible_discrete}})
    cols.append({"name": "week_index", "type": "integer", "n_missing": 0, "pct_missing": 0,
                 "n_distinct": 8, "can_be_time": True, "can_be_event": False,
                 "can_be_covariate": True, "can_be_stratum": False,
                 "summary": {"min": 1, "median": 4, "max": 8},
                 "time_grid": {"integer_valued": True, "step": 1, "n_distinct": 8,
                               "coarse": True}})
    cols.append({"name": "died", "type": "integer", "n_missing": 0, "pct_missing": 0,
                 "n_distinct": 2, "can_be_time": False, "can_be_event": True,
                 "can_be_covariate": True, "can_be_stratum": False, "values": ["0", "1"]})
    return {"status": "ok", "n_rows": 240, "n_columns": len(cols), "columns": cols,
            "eligible": {"time": ["followup_days", "week_index"] + COLS, "event": ["died"],
                         "covariate": COLS + ["followup_days", "week_index"], "stratum": []},
            "possible_ncc": possible_ncc, "possible_discrete": possible_discrete,
            "quarantined": [], "complementary_pairs": [],
            "external": {"present": False, "names": [], "n_matched": 0, "unmatched": []},
            "dictionary": {"present": False}}


def decl(**kw) -> Declaration:
    base = dict(time_col="followup_days", event_col="died", event_value="1",
                covariates=list(COLS), source="reply", covariates_time_zero="yes")
    base.update(kw)
    return Declaration(**base)


# ================================================================ A. no R
def part_a():
    hdr("A1. the candidate set is derived from three facts")
    dk = pipeline.derive_candidate_keys
    check(dk("full cohort", "coefficients alone", discrete=True, has_baseline=True)
          == ["internal_discrete", "discretekl", "internal_nn", "diskd", "external_discrete"],
          "coefficients + baseline: the five members, in order")
    check(dk("full cohort", "coefficients alone", discrete=True, has_baseline=False)
          == ["internal_discrete", "internal_nn"],
          "coefficients without a baseline: nothing to borrow on a grid, two internal members")
    check(dk("full cohort", "none", discrete=True) == ["internal_discrete", "internal_nn"],
          "no external information: two internal members")
    check(dk("full cohort", "individual-level data", discrete=True, has_baseline=True)
          == ["internal_discrete", "internal_nn"],
          "another cohort's rows carry no baseline: two internal members")
    check(dk("nested case-control", "coefficients alone", discrete=True, has_baseline=True) == [],
          "a matched design has no discrete row (the gate refuses first)")
    check(len(dk("full cohort", "coefficients alone")) == 10
          and "internal_discrete" not in dk("full cohort", "coefficients alone"),
          "the Cox row is untouched: ten members, none of them discrete")

    hdr("A2. item 7 is parsed deterministically")
    prof = fake_profile()
    base = {"time": "followup_days", "event": "died", "event_value": "1",
            "covariates": "age, egfr, albumin, donor_age", "time_zero": "yes"}
    d = parse_reply(prof, dict(base, discrete="no"))
    check(not d.discrete and any("item 7 answered no" in n for n in d.notes),
          "'no' -> continuous, recorded in the notes")
    d = parse_reply(prof, dict(base, discrete="7 53"))
    check(d.discrete and d.interval_width == 7 and d.n_intervals == 53
          and not d.time_is_interval_index, "'7 53' -> width 7, K 53")
    d = parse_reply(prof, dict(base, discrete="width 7, horizon 53 intervals"))
    check(d.interval_width == 7 and d.n_intervals == 53, "words around the two numbers are fine")
    d = parse_reply(prof, dict(base, time="week_index", discrete="index"))
    check(d.time_is_interval_index and d.n_intervals == 8 and d.interval_width is None,
          "'index' -> K from the column's maximum (8)")
    d = parse_reply(prof, dict(base, time="week_index", discrete="index 10"))
    check(d.time_is_interval_index and d.n_intervals == 10, "'index 10' -> K = 10")
    for bad, why in (("weekly 53", "a unit word without the width"),
                     ("7", "one number"), ("0 53", "zero width"), ("7 1", "K < 2"),
                     ("7 8.5", "non-integer K")):
        try:
            parse_reply(prof, dict(base, discrete=bad))
            check(False, f"{bad!r} is refused ({why})")
        except DeclarationError as exc:
            check(True, f"{bad!r} is refused ({why})", str(exc)[:60])
    try:
        parse_reply(prof, dict(base, time="week_index", discrete="index 5"))
        check(False, "'index 5' on a column reaching 8 is refused")
    except DeclarationError as exc:
        check("reaches 8" in str(exc), "'index 5' on a column reaching 8 is refused", str(exc)[:70])
    check(d.discrete_spec() == {"n_intervals": 10, "width": None, "time_is_index": True},
          "discrete_spec is what the R side takes")

    hdr("A3. complete() never asks item 7: continuous time is the default, disclosed when the column is coarse")
    c = complete(prof, dict(base))
    check("7" not in c.missing and c.ready and c.answers.get("discrete") == "no"
          and c.sources.get("discrete", "").startswith("default: continuous time")
          and "followup_days" in c.sources["discrete"] and "7) <width> <K>" in c.sources["discrete"],
          "a coarse settled time column: NOT asked; the default is set and disclosed with the fact",
          str(c.sources.get("discrete")))
    c = complete(prof, dict(base, discrete="no"))
    check("7" not in c.missing and c.ready and "discrete" not in c.sources, "answered no -> ready, no default source")
    c = complete(prof, dict(base, discrete="7 8"))
    check(c.ready and c.answers["discrete"] == "7 8" and "discrete" not in c.sources,
          "the analyst asked for intervals -> carried as given, never overridden by the default")
    c = complete(fake_profile(possible_discrete=False), dict(base))
    check("7" not in c.missing and "discrete" not in c.answers, "the settled column not coarse -> nothing said")
    c = complete(prof, dict(base, time="age"))
    check("7" not in c.missing and "discrete" not in c.answers,
          "a fine-grained time column -> nothing said, whatever other columns look like")
    c = complete(prof, {k: v for k, v in base.items() if k != "time"})
    check("1" in c.missing and "7" not in c.missing and "discrete" not in c.answers,
          "no time column settled yet -> item 1 is open, no default yet")
    c = complete(prof, {"stratum": "site", "event": "died", "event_value": "1",
                        "covariates": "B", "time_zero": "yes"})
    check("7" not in c.missing and "discrete" not in c.answers, "a matched declaration (stratum, no time): nothing said")
    c = complete(prof, dict(base), remembered={"date": "2026-09-01",
                                                "answers": {"discrete": "7 53"}})
    check(c.answers.get("discrete") == "7 53" and c.sources["discrete"].startswith("remembered")
          and "7" not in c.missing, "an earlier answer for the same file is remembered and disclosed")

    hdr("A4. the question")
    q = render_question(prof)
    check("7) TIME SCALE" not in q,
          "item 7 is not in the opening list (eligibility for time is too broad to ask on)")
    q = render_question(prof, only=["7"])
    check("7) TIME SCALE" in q and "week_index" in q and "'7 53'" in q,
          "rendered on request, with the coarse columns and the reply format")
    q = render_question(prof, only=["7"], time_col="followup_days")
    check("followup_days" in q and "week_index" not in q,
          "with the settled column given, only that column is described")

    hdr("A5. the C3 hash covers the grid and the baseline")
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "d.csv"; f.write_text("a,b\n1,2\n", encoding="utf-8")
        bl = {"time": [3.5, 10.5], "cumhaz": [0.05, 0.11]}
        h = lambda d, b=None: pipeline.config_hash(pipeline.canonical_config(
            str(f), "d", d, None, 1, 5, 50, external_baseline_inline=b))
        d0 = decl(); d1 = decl(interval_width=7.0, n_intervals=53)
        d2 = decl(interval_width=7.0, n_intervals=52)
        d3 = decl(interval_width=30.0, n_intervals=53)
        d4 = decl(n_intervals=53, time_is_interval_index=True)
        hs = {h(d0), h(d1), h(d2), h(d3), h(d4)}
        check(len(hs) == 5, "continuous / width / K / index flag all hash differently")
        check(h(d1) != h(d1, bl), "the baseline hazard by value changes the hash")
        rc = pipeline.resolve_config(str(f), "d", d1, external_beta_inline={"a": 0.1},
                                     external_baseline_inline=bl)
        check(rc["candidate_keys"][1] == "discretekl" and rc["has_baseline"]
              and rc["outcome_scale"] == "discrete intervals",
              "resolve_config derives the five-member row from the baseline")
        rc = pipeline.resolve_config(str(f), "d", d1, external_beta_inline={"a": 0.1})
        check(rc["candidate_keys"] == ["internal_discrete", "internal_nn"],
              "... and the two-member row without it")

    hdr("A6. the replays")
    res = fake_result(selected="diskd")
    rr = fake_run(res, decl(interval_width=7.0, n_intervals=K),
                  baseline={"time": [3.5], "cumhaz": [0.05]})
    script = pipeline.render_repro(rr)
    check("discrete    = list(n_intervals = 8, width = 7.0, time_is_index = FALSE)" in script
          and "baseline_inline = list(time = c(3.5), cumhaz = c(0.05))" in script
          and "BREGSURV_PYTHON" in script,
          "repro.R carries the grid, the baseline and the Python note")
    py = pipeline.render_repro_diskd(rr)
    check("N_INTERVALS, WIDTH, TIME_IS_INDEX = 8, 7.0, False" in py
          and '"eta_grid"' in py and "FOLDS = np.array(" in py and "RECORDED" in py,
          "repro_diskd.py carries the grid, the settings, the folds and the recorded numbers")
    check(rr.has_network_members, "the run knows it has network members")
    rr2 = fake_run(res, decl(n_intervals=K, time_is_interval_index=True))
    check("width = NULL, time_is_index = TRUE" in pipeline.render_repro(rr2),
          "index mode replays with width NULL")

    hdr("A7. the report")
    txt = report_v3.render(res, declaration=decl(interval_width=7.0, n_intervals=K),
                           external={"file": "release.json", "format": "json",
                                     "coefficient_table": "coefficients",
                                     "name_column": "variable", "coefficient_column": "coef",
                                     "baseline_table": "baseline_hazard"})
    check("Time scale" in txt and "8 intervals of width 7" in txt
          and "censored at interval 8" in txt, "section 1 states the grid and the cut")
    check("held-out NLL per subject" in txt and "grouped-time model" in txt,
          "section 4 names the functional")
    check("neural network" in txt and "no coefficient table" in txt,
          "section 5 says a network winner has no coefficients")
    check("Baseline hazard by interval" in txt and "| 8 " in txt,
          "section 5 shows the interval baseline table")
    check("differenced into one increment per interval" in txt,
          "section 2 says what was done to the baseline")
    check("repro_diskd.py" in txt, "the provenance line names the Python replay")
    refs = report_v3.build_references(res)
    check(refs["loss_internal"] == 1.30 and refs["loss_external"] == 1.25
          and refs["outcome_scale"] == "discrete intervals" and refs["n_intervals"] == K,
          "references fall back to the discrete members")
    txt2 = report_v3.render(fake_result(selected="discretekl"),
                            declaration=decl(interval_width=7.0, n_intervals=K))
    check("no coefficient table" not in txt2 and "| age " in txt2
          and "| 8 " in txt2, "a DiscreteKL winner shows its coefficients and its baseline")

    hdr("A8. the declaration's own checks")
    codes = [r["code"] for r in _own_checks(prof, Declaration(
        time_col=None, event_col="died", event_value="1", covariates=COLS, source="reply",
        stratum_col="site", n_intervals=8, interval_width=7.0))]
    check("discrete_needs_followup_time" in codes, "discrete + matched design is refused")
    codes = [r["code"] for r in _own_checks(prof, decl(n_intervals=1, interval_width=7.0))]
    check("discrete_k_too_small" in codes, "K = 1 is refused")
    codes = [r["code"] for r in _own_checks(prof, decl(n_intervals=8, interval_width=0))]
    check("discrete_width_invalid" in codes, "width 0 is refused")

    hdr("A9. the app's vocabulary")
    import app  # noqa: F401
    a = app._answers_from_reply("1) followup_days\n2) died\n7) 7 53")
    check(a.get("discrete") == "7 53", "a numbered reply carries item 7")
    check(app._answers_of(decl(interval_width=7.0, n_intervals=53))["discrete"] == "7 53"
          and app._answers_of(decl(n_intervals=8, time_is_interval_index=True))["discrete"] == "index 8"
          and "discrete" not in app._answers_of(decl()),
          "a declaration goes back into item 7's words; nothing when it never arose")
    d_no = decl(); d_no.notes = ["time scale: continuous (item 7 answered no)"]
    check(app._answers_of(d_no)["discrete"] == "no", "... and 'no' when it was answered no")
    from bregsurv_agent import state, memory, guards
    check("discrete" in state.ROLE_KEYS and "discrete" in memory.REMEMBERED_ROLES,
          "the session and the memory know the role")


def fake_result(selected="diskd"):
    """A run_candidates.R output of the discrete row, shaped like the real one."""
    rows = [
        {"key": "internal_discrete", "label": "Internal only, discrete time", "borrowing": "none",
         "penalty": "none", "status": "ok", "scorer": "discrete_nll/pooled", "loss": 1.30,
         "eta": 0, "lambda": None, "n_nonzero": 4, "seconds": 0.4, "message": None,
         "settings": {"etas": [0, 1, 5], "tol": 1e-20, "max_iter": 25}},
        {"key": "discretekl", "label": "DiscreteKL (Kullback-Leibler, discrete time)",
         "borrowing": "kl", "penalty": "none", "status": "ok", "scorer": "discrete_nll/pooled",
         "loss": 1.22, "eta": 5, "lambda": None, "n_nonzero": 4, "seconds": 0.4, "message": None},
        {"key": "internal_nn", "label": "Internal only, network", "borrowing": "none",
         "penalty": "none", "status": "ok", "scorer": "discrete_nll/pooled", "loss": 1.28,
         "eta": 0, "lambda": None, "n_nonzero": None, "seconds": 30, "message": None,
         "settings": {"architecture": "repo_lh4x128", "eta_grid": [0, 1, 5], "learning_rates": [5e-4],
                      "seed": 1, "threads": 1, "profile": {"max_epochs": 50, "patience": 5},
                      "learning_rate_selected": 5e-4, "epochs": 20}},
        {"key": "diskd", "label": "DiSKD (distilled network, discrete time)", "borrowing": "kl",
         "penalty": "none", "status": "ok", "scorer": "discrete_nll/pooled", "loss": 1.20,
         "eta": 5, "lambda": None, "n_nonzero": None, "seconds": 30, "message": None,
         "settings": {"architecture": "repo_lh4x128", "eta_grid": [0, 1, 5], "learning_rates": [5e-4],
                      "seed": 1, "threads": 1, "profile": {"max_epochs": 50, "patience": 5},
                      "learning_rate_selected": 5e-4, "epochs": 22}},
        {"key": "external_discrete", "label": "External model, unchanged", "borrowing": "external",
         "penalty": "none", "status": "ok", "scorer": "discrete_nll/pooled", "loss": 1.25,
         "eta": None, "lambda": None, "n_nonzero": 3, "seconds": 0, "message": None},
    ]
    sel = next(r for r in rows if r["key"] == selected)
    beta = {c: 0.1 * (i + 1) for i, c in enumerate(COLS)}
    return {
        "status": "ok",
        "facts": {"design": "full cohort", "external_form": "coefficients alone",
                  "outcome_scale": "discrete intervals", "n": 240, "n_events": 90, "p": 4,
                  "p_covered": 3, "p_internal_only": 1, "has_baseline": True,
                  "tie_handling": "not applicable (grouped time)"},
        "partition": {"seed": 1, "nfolds": 5, "folds": [1 + i % 5 for i in range(240)],
                      "rng_kind": "Mersenne-Twister", "drawn_by": "harness", "row_order": "caller",
                      "seed_is_effective": True},
        "criteria": "held-out NLL per subject", "scorer": ["discrete_nll/pooled"],
        "candidates": rows,
        "selected": {"key": sel["key"], "label": sel["label"], "loss": sel["loss"],
                     "eta": sel["eta"], "lambda": None, "n_nonzero": sel["n_nonzero"],
                     "beta": (beta if selected in ("discretekl", "internal_discrete") else {})},
        "coefficients": [{"variable": c, "beta_external": (BETA_TRUE[i] if c != "albumin" else None),
                          "beta_internal": 0.1 * (i + 1),
                          "beta_selected": (0.12 * (i + 1) if selected in ("discretekl", "internal_discrete") else None),
                          "covered_by_external": c != "albumin"} for i, c in enumerate(COLS)],
        "baseline": [{"interval": k + 1, "from": k * WIDTH, "to": (k + 1) * WIDTH,
                      "n_at_risk": 240 - 20 * k, "n_events": 12,
                      "gamma_external": ALPHA[k], "gamma_internal": ALPHA[k] + 0.1,
                      "gamma_selected": (ALPHA[k] + 0.05 if selected in ("discretekl", "internal_discrete") else None)}
                     for k in range(K)],
        "linkage": {"matched_by": "name", "n_internal": 4, "n_external": 4,
                    "covered": ["age", "egfr", "donor_age"], "zero_padded": ["albumin"],
                    "dropped": ["hla_mismatch"]},
        "discrete": {"n_intervals": K, "width": WIDTH, "time_is_index": False,
                     "n_beyond_horizon": 14, "n_events_beyond_horizon": 6,
                     "teacher": {"beta": {"age": 0.7, "egfr": -0.6, "albumin": 0.0, "donor_age": 0.3},
                                 "dH0": [math.exp(a) for a in ALPHA]},
                     "etas_discretekl": [0, 1, 5]},
    }


def fake_run(res, d, baseline=None):
    from bregsurv_agent.declaration import Verification
    return pipeline.RunResult(
        data_path=__file__, data_expr="cohort", external_beta_expr=None, external_Q_expr=None,
        profile=fake_profile(), declaration=d, verification=Verification(True, []),
        candidates=res, report="", provenance={"generated_at": "now", "data": {"name": "x", "sha256": "0" * 64},
                                               "nlambda": 50},
        config_sha256="f" * 64, seconds=1.0, external_beta_inline={"age": 0.7},
        external_baseline_inline=baseline)


# ================================================================ B. with R
def part_b():
    with tempfile.TemporaryDirectory() as td_:
        td = Path(td_)
        csv, ext_path, rows = make_fixture(td)
        n = len(rows)
        beyond = sum(1 for r in rows if r[4] >= K * WIDTH)
        print(DIM + f"fixture: {n} subjects, {sum(r[5] for r in rows)} events, "
              f"{beyond} observed past the horizon" + OFF)

        hdr("B1. the profiler reports the time-grid facts and raises the question")
        prof = _run_r("profile_columns.R", {"data_path": csv, "data_expr": "cohort"})
        check(prof.get("status") == "ok", "profiled", str(prof.get("message", ""))[:80])
        by = {c["name"]: c for c in prof["columns"]}
        tg = by["followup_days"].get("time_grid") or {}
        check(tg.get("integer_valued") and tg.get("step") == 1 and tg.get("coarse"),
              "followup_days: integer, step 1, coarse", json.dumps(tg))
        tg2 = by["week_index"].get("time_grid") or {}
        check(tg2.get("coarse") and tg2.get("n_distinct") == K, "week_index: coarse, 8 values")
        check(prof.get("possible_discrete") is True, "possible_discrete raised")
        check("time_grid" not in by["age"] or not by["age"]["time_grid"].get("coarse"),
              "a continuous covariate is not coarse")

        hdr("B2. the gate: the cut, the horizon, the index, the baseline, the design")
        ext = X.read_external(ext_path)
        bl = ext.baseline_hazard
        check(ext.form == "coefficients_with_baseline_hazard" and bl and len(bl["time"]) == K,
              "the release is read as coefficients with a baseline hazard")
        d = decl(interval_width=WIDTH, n_intervals=K)
        v = verify(prof, d, csv, "cohort", run_r=_run_r, external_baseline=bl)
        s = (v.gate or {}).get("summary", {}).get("discrete") or {}
        check(v.admissible, "declared 7 x 8 on days: admissible (day 0 is interval 1)",
              "; ".join(r["code"] for r in v.refusals))
        check(min(r[4] for r in rows) == 0, "the fixture holds a day-0 subject, so that rule is exercised")
        check(s.get("n_intervals") == K and s.get("n_beyond_horizon") == beyond
              and s.get("n_reach_horizon", 0) > 0, "the card counts the subjects past the horizon",
              json.dumps({k: s.get(k) for k in ("n_beyond_horizon", "n_reach_horizon")}))
        check((s.get("baseline") or {}).get("status") == "covers the horizon",
              "the baseline covers the horizon", json.dumps(s.get("baseline")))
        card = v.render()
        check("time scale        discrete: 8 intervals of width 7" in card
              and "intervals         8;" in card and "external baseline covers the horizon" in card,
              "the card states the grid, the cut and the coverage")
        v = verify(prof, decl(interval_width=WIDTH, n_intervals=40), csv, "cohort", run_r=_run_r,
                   external_baseline=bl)
        check(not v.admissible and any(r["code"] in ("discrete_horizon_unreached", "discrete_baseline_short")
                                       for r in v.refusals),
              "K = 40 weeks: refused (horizon unreached / baseline short)",
              "; ".join(r["code"] for r in v.refusals))
        v = verify(prof, decl(interval_width=WIDTH, n_intervals=5), csv, "cohort", run_r=_run_r,
                   external_baseline={"time": bl["time"][:2], "cumhaz": bl["cumhaz"][:2]})
        check(not v.admissible and any(r["code"] == "discrete_baseline_short" for r in v.refusals),
              "a baseline ending before the last interval: refused")
        v = verify(prof, decl(time_col="week_index", n_intervals=K, time_is_interval_index=True),
                   csv, "cohort", run_r=_run_r, external_baseline=None)
        check(v.admissible and "is the interval index 1..8" in v.render(),
              "the index column declared as such: admissible, no baseline needed")
        v = verify(prof, decl(time_col="week_index", n_intervals=5, time_is_interval_index=True),
                   csv, "cohort", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "discrete_index_beyond_k" for r in v.refusals),
              "index beyond K: refused")
        v = verify(prof, decl(time_col="followup_days", n_intervals=K, time_is_interval_index=True),
                   csv, "cohort", run_r=_run_r)
        check(not v.admissible and any(r["code"] in ("discrete_index_beyond_k", "discrete_index_not_integer")
                                       for r in v.refusals),
              "days declared as an index: refused (values outside 1..K)",
              "; ".join(r["code"] for r in v.refusals))
        v = verify(prof, Declaration(time_col=None, event_col="died", event_value="1", covariates=COLS,
                                     source="reply", stratum_col="patient_id", n_intervals=K,
                                     interval_width=WIDTH, covariates_time_zero="yes"),
                   csv, "cohort", run_r=_run_r)
        check(not v.admissible and any(r["code"] == "discrete_needs_followup_time" for r in v.refusals),
              "matched design + discrete: refused by the declaration's own checks")

        hdr("B3. run_candidates.R: the R members, the teacher, the network members skipped")
        d = decl(interval_width=WIDTH, n_intervals=K)
        payload = {"data_path": csv, **d.as_exprs("cohort"), "seed": 20260818, "nfolds": 5,
                   "nlambda": 50, "event_value": "1", "beta_inline": dict(ext.terms),
                   "discrete": d.discrete_spec(),
                   "baseline_inline": {"time": bl["time"], "cumhaz": bl["cumhaz"]}}
        os.environ["BREGSURV_SKIP_PYTHON"] = "1"
        try:
            res = _run_r("run_candidates.R", payload)
        finally:
            os.environ.pop("BREGSURV_SKIP_PYTHON", None)
        check(res.get("status") == "ok", "the discrete row ran", str(res.get("message", ""))[:200])
        if res.get("status") == "ok":
            rows_ = {c["key"]: c for c in res["candidates"]}
            check(sorted(rows_) == sorted(["internal_discrete", "discretekl", "internal_nn", "diskd",
                                           "external_discrete"]),
                  "five members recorded", ", ".join(sorted(rows_)))
            check(all(rows_[k]["status"] == "ok" for k in ("internal_discrete", "discretekl", "external_discrete")),
                  "the R members fitted",
                  "; ".join(f"{k}: {rows_[k]['status']} {rows_[k].get('message') or ''}"
                            for k in ("internal_discrete", "discretekl", "external_discrete")))
            check(all(rows_[k]["status"] == "skipped" for k in ("internal_nn", "diskd")),
                  "the network members are recorded as skipped under BREGSURV_SKIP_PYTHON")
            sc = res["scorer"] if isinstance(res["scorer"], list) else [res["scorer"]]
            check(sc == ["discrete_nll/pooled"] and res["criteria"] == "held-out NLL per subject",
                  "one scorer for the row", str(res["scorer"]))
            check(len(res["partition"]["folds"]) == n and res["partition"]["row_order"] == "caller",
                  "the shared partition covers every subject, in the file's order")
            t = res["discrete"]["teacher"]
            check(abs(t["beta"]["age"] - BETA_TRUE[0]) < 1e-9 and t["beta"]["albumin"] == 0
                  and len(t["dH0"]) == K and all(abs(t["dH0"][k] - math.exp(ALPHA[k])) < 1e-9 for k in range(K)),
                  "the teacher: external coefficients by name, zero elsewhere, dH0 from the cumulative hazard")
            check(res["facts"]["outcome_scale"] == "discrete intervals"
                  and res["discrete"]["n_beyond_horizon"] == beyond
                  and res["facts"]["n_events"] == sum(1 for r in rows if r[5] == 1 and r[4] < K * WIDTH),
                  "the facts: the cut and the binned event count")
            check(len(res["baseline"]) == K and res["baseline"][-1]["n_at_risk"] > 0
                  and abs(res["baseline"][0]["gamma_external"] - ALPHA[0]) < 1e-9,
                  "the interval baseline table: K rows, external gamma_k = log dH0_k")
            ext_row = rows_["external_discrete"]
            check(ext_row["loss"] > 0 and ext_row["n_nonzero"] == 3, "the teacher scored unchanged")
            check(rows_["discretekl"]["eta"] in (0, 1, 5, 10, 20, 50, 100)
                  and rows_["discretekl"]["loss"] <= rows_["internal_discrete"]["loss"] + 1e-9,
                  "DiscreteKL chose an eta on the grid and did no worse than eta = 0",
                  f"eta={rows_['discretekl']['eta']} loss={rows_['discretekl']['loss']:.4f} "
                  f"vs {rows_['internal_discrete']['loss']:.4f}")
            check(res["selected"]["key"] in rows_ and rows_[res["selected"]["key"]]["status"] == "ok",
                  "a member was selected", res["selected"]["label"])
            # a second run with the same seed reproduces the partition and the numbers
            os.environ["BREGSURV_SKIP_PYTHON"] = "1"
            try:
                res2 = _run_r("run_candidates.R", payload)
            finally:
                os.environ.pop("BREGSURV_SKIP_PYTHON", None)
            check(res2["partition"]["folds"] == res["partition"]["folds"]
                  and all(abs(rows_[k]["loss"] - next(c for c in res2["candidates"] if c["key"] == k)["loss"]) < 1e-12
                          for k in ("internal_discrete", "discretekl", "external_discrete")),
                  "the same seed reproduces the partition and every R member's loss")
            # index mode through the R members
            d2 = decl(time_col="week_index", n_intervals=K, time_is_interval_index=True)
            payload2 = dict(payload, **d2.as_exprs("cohort"), discrete=d2.discrete_spec(),
                            baseline_inline={"time": [k + 1.5 for k in range(K)], "cumhaz": [sum(math.exp(a) for a in ALPHA[:k + 1]) for k in range(K)]},
                            include=["internal_discrete", "discretekl", "external_discrete"])
            os.environ["BREGSURV_SKIP_PYTHON"] = "1"
            try:
                res3 = _run_r("run_candidates.R", payload2)
            finally:
                os.environ.pop("BREGSURV_SKIP_PYTHON", None)
            check(res3.get("status") == "ok" and res3["discrete"]["time_is_index"]
                  and res3["discrete"]["n_beyond_horizon"] == 0
                  and abs(res3["discrete"]["teacher"]["dH0"][2] - math.exp(ALPHA[2])) < 1e-9,
                  "index mode: no binning, dH0 from jumps inside [k, k+1)",
                  str(res3.get("message", ""))[:120])
            # no baseline: the two internal members only
            payload3 = {k: v for k, v in payload.items() if k != "baseline_inline"}
            os.environ["BREGSURV_SKIP_PYTHON"] = "1"
            try:
                res4 = _run_r("run_candidates.R", payload3)
            finally:
                os.environ.pop("BREGSURV_SKIP_PYTHON", None)
            check(res4.get("status") == "ok"
                  and sorted(c["key"] for c in res4["candidates"]) == ["internal_discrete", "internal_nn"]
                  and res4["facts"]["has_baseline"] is False,
                  "without a baseline the row holds the two internal members",
                  str(res4.get("message", ""))[:120])

        hdr("B4. the whole pipeline with DiSKD through the bridge (the smoke test, ruling 2)")
        if os.environ.get("BREGSURV_DISCRETE_FAST"):
            print(DIM + "  skipped (BREGSURV_DISCRETE_FAST)" + OFF)
            return
        d = decl(interval_width=WIDTH, n_intervals=K)
        rc = pipeline.resolve_config(csv, "cohort", d, external_beta_inline=dict(ext.terms),
                                     external_baseline_inline={"time": bl["time"], "cumhaz": bl["cumhaz"]})
        try:
            rr = pipeline.run(csv, "cohort", d, external_beta_inline=dict(ext.terms),
                              external_baseline_inline={"time": bl["time"], "cumhaz": bl["cumhaz"]},
                              profile=prof, run_r=_run_r, approved_config_sha256=rc["sha256"],
                              external_provenance=ext.provenance)
        except pipeline.PipelineRefusal as exc:
            check(False, "the pipeline ran", "; ".join(r["message"][:150] for r in exc.refusals))
            return
        rows_ = {c["key"]: c for c in rr.candidates["candidates"]}
        check(sorted(rows_) == sorted(rc["candidate_keys"]), "the fitted set is the approved set")
        nn_ok = all(rows_[k]["status"] == "ok" for k in ("internal_nn", "diskd"))
        check(nn_ok, "the agent called DiSKD and it fitted",
              "; ".join(f"{k}: {rows_[k]['status']} {(rows_[k].get('message') or '')[:120]}"
                        for k in ("internal_nn", "diskd")))
        if nn_ok:
            st = rows_["diskd"]["settings"]
            check(st["architecture"] == "repo_lh4x128" and st["eta_grid"] == [0, 1, 5, 10, 20, 40, 80]
                  and st["profile"]["max_epochs"] == 512 and st["profile"]["patience"] == 5,
                  "DiSKD ran with the released settings (nested CV as handed over)",
                  f"eta={rows_['diskd']['eta']} lr={st.get('learning_rate_selected')} "
                  f"epochs={st.get('epochs')} loss={rows_['diskd']['loss']:.4f} "
                  f"in {rows_['diskd']['seconds']}s")
            check(rows_["diskd"]["loss"] <= rows_["internal_nn"]["loss"] + 1e-9,
                  "DiSKD did no worse than the network at eta = 0",
                  f"{rows_['diskd']['loss']:.4f} vs {rows_['internal_nn']['loss']:.4f}")
        check(rr.candidates["selected"]["key"] in rows_, "a member was selected",
              rr.candidates["selected"]["label"])
        check("## 4. How they compared" in rr.report and "held-out NLL per subject" in rr.report
              and "Baseline hazard by interval" in rr.report, "the report renders the discrete row")
        out = td / "run"
        paths = rr.save(str(out))
        check("repro_diskd" in paths and Path(paths["repro_diskd"]).exists()
              and Path(paths["repro"]).exists() and Path(paths["trace"]).exists(),
              "the artifacts: report, trace, repro.R AND repro_diskd.py")
        trace = json.loads(Path(paths["trace"]).read_text(encoding="utf-8"))
        check(trace["declaration"]["n_intervals"] == K and trace["declaration"]["interval_width"] == WIDTH
              and trace["facts"]["outcome_scale"] == "discrete intervals",
              "the trace records the grid")
        # the hash guard: a different K is a different analysis
        try:
            pipeline.run(csv, "cohort", decl(interval_width=WIDTH, n_intervals=K - 1),
                         external_beta_inline=dict(ext.terms),
                         external_baseline_inline={"time": bl["time"], "cumhaz": bl["cumhaz"]},
                         profile=prof, run_r=_run_r, approved_config_sha256=rc["sha256"])
            check(False, "a changed K fails the approval hash")
        except pipeline.PipelineRefusal as exc:
            check(exc.refusals[0]["code"] == "config_changed", "a changed K fails the approval hash")

        hdr("B5. the replays")
        env = dict(os.environ, BREGSURV_R_SCRIPTS=str(R_SCRIPTS), BREGSURV_SKIP_PYTHON="1")
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                            paths["repro"], csv], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env, timeout=600)
        check(r.returncode == 0 and "fold assignment REPRODUCED" in r.stdout,
              "repro.R replays the R members on the recorded partition",
              (r.stdout + r.stderr)[-300:].replace("\n", " | "))
        if nn_ok:
            r = subprocess.run([sys.executable, paths["repro_diskd"], csv],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               env=dict(os.environ, BREGSURV_REPO=str(REPO)), timeout=3600)
            check(r.returncode == 0 and "network members REPRODUCED" in r.stdout,
                  "repro_diskd.py replays the network members without R",
                  (r.stdout + r.stderr)[-400:].replace("\n", " | "))


def main() -> int:
    part_a()
    part_b()
    print(f"\nRESULT: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
