"""The routing cells the V3 agent could not reach until 2026-08-19.

Before this, `pipeline.run` reached exactly ONE of the seven states the family
defines: full cohort with external coefficients. The nested case-control half was
structurally unreachable -- `Declaration` had no matched-set field, so
`as_exprs` could only ever emit z/time/delta and `design` was the constant
"full cohort" -- and a run with no external information at all died on an R
error rather than producing an analysis or a reasoned refusal.

What each block here pins down:

  A  detection. A matched-set column has to be separated from the two things
     that look like it -- a site/centre column (few large groups) and a subject
     identifier (n groups of one) -- or the design question is asked constantly
     and stops being read.
  B  the design is DECLARED, by what is answered. Leaving the follow-up-time
     question blank and naming a matched set is the declaration; there is no
     separate claim for the data to contradict.
  C  the falsification number. Under a cohort a complement mix-up shows up as a
     75% event rate. Under a matched design the rate is the sampling ratio and
     looks normal either way, so the one-case-per-set count is what has to
     refuse -- and it must refuse, not merely display.
  D  the matched cell end to end, including a replay with no model.
  E  no external information: a smaller, honest candidate set rather than nine
     rows carrying the same number.
  F  a stratified cohort is a THIRD thing. Time and a stratum together is not a
     matched design, and the stratum must actually reach the estimator.
  G  external individual-level data -- the family's third integration mode, and
     the one that appeared ZERO times in run_candidates.R. Five members, no
     ridge (the library has none), the same loss functional as the coefficient
     cells, and External-only manufactured by fitting the external cohort
     rather than read off a paper.

NO PATIENT DATA. Every fixture is generated here.

Run:  python test_family_cells.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

# The R bridge lives in the agent package, not in the MCP server: testing
# the agent must not require the MCP SDK. See bregsurv_agent/rbridge.py.
from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from bregsurv_agent import pipeline  # noqa: E402
from bregsurv_agent.declaration import (  # noqa: E402
    DeclarationError, complete, parse_reply, render_question, verify)
from test_pipeline_e2e import build_fixture  # noqa: E402

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m", "\033[2m",
                             "\033[0m")
passed = failed = 0

# 150 matched sets of 4 (1:3 matching), plus the two decoys detection has to
# reject: `site` has three large groups, `pid` is one row per subject.
NCC_FIXTURE = r"""
args <- commandArgs(trailingOnly = TRUE)
set.seed(7)
n_sets <- 150; m <- 4; n <- n_sets * m
z <- matrix(rnorm(n * 4), n, 4)
colnames(z) <- c("age", "bmi", "egfr", "donor_age")
NC <- as.data.frame(z)
NC$set_id <- rep(seq_len(n_sets), each = m)
NC$site   <- rep(1:3, length.out = n)
NC$pid    <- sprintf("S%04d", seq_len(n))
NC$case   <- as.numeric(rep(c(1, 0, 0, 0), times = n_sets))
beta_ext <- c(age = 0.5, bmi = -0.3, egfr = -0.4, donor_age = 0.25)
Qext <- diag(4); rownames(Qext) <- colnames(Qext) <- colnames(z)
save(NC, beta_ext, Qext, file = args[1])
cat("ncc fixture:", n, "rows,", n_sets, "matched sets of", m, "\n")
"""


INDI_FIXTURE = r"""
args <- commandArgs(trailingOnly = TRUE)
mk <- function(n, seed) {
  set.seed(seed)
  z <- matrix(rnorm(n * 4), n, 4)
  colnames(z) <- c("age", "bmi", "egfr", "donor_age")
  lp <- z %*% c(0.6, -0.35, -0.4, 0.3)
  tt <- rexp(n, exp(lp) * 0.08); cc <- rexp(n, 0.05)
  D <- as.data.frame(z)
  D$followup_days <- round(pmin(tt, cc) * 100) + 1
  D$died <- as.numeric(tt <= cc)
  D
}
D   <- mk(300, 1)
EXT <- mk(900, 2)
# same four covariates, DIFFERENT order -- the decoy the name check must catch
PERM <- EXT[, c("bmi", "age", "donor_age", "egfr", "followup_days", "died")]
beta_ext <- c(age = 0.5, bmi = -0.3, egfr = -0.4, donor_age = 0.25)
save(D, EXT, PERM, beta_ext, file = args[1])
cat("indi fixture: internal", nrow(D), "external", nrow(EXT), "rows\n")
"""

def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")
    return ok


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def _build(td: Path, src: str, name: str) -> str:
    f = td / f"mk_{name}.R"
    f.write_text(src, encoding="utf-8")
    rda = td / f"{name}.rda"
    r = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                        "--no-init-file", str(f), str(rda)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit(f"could not build the {name} fixture")
    print(DIM + r.stdout.strip() + OFF)
    return str(rda)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        ncc = _build(tdp, NCC_FIXTURE, "NCC")
        prof = _run_r("profile_columns.R", {
            "data_path": ncc, "data_expr": "NC", "external_beta_expr": "beta_ext"})

        # ---- A. detection ---------------------------------------------------
        hdr("A. a matched set is told apart from a site column and an id")
        strat = list(prof["eligible"]["stratum"])
        check(prof.get("possible_ncc") is True and strat == ["set_id"],
              "exactly the matched-set column is detected",
              f"stratum candidates {strat}")
        check("site" not in strat,
              "a site column is NOT mistaken for a matched set",
              "three groups of 200 -- few and large, not many and small")
        check("pid" not in strat
              and any(q["name"] == "pid" for q in prof["quarantined"]),
              "an identifier is NOT mistaken for a matched set",
              "one row per group, and quarantined already")

        coh_probe = _run_r("profile_columns.R", {
            "data_path": build_fixture(tdp), "data_expr": "D"})
        check(coh_probe.get("possible_ncc") is False,
              "an ordinary cohort does not trigger the design question",
              "over-asking would make the question stop being read")

        q = render_question(prof)
        check("0) STUDY DESIGN" in q and "LEAVE QUESTION 1 BLANK" in q,
              "the design question is asked first, with what to do about it")

        # ---- B. the design is declared by what is answered -------------------
        hdr("B. leaving the time question blank IS the matched declaration")
        answers = {"time": "", "stratum": "set_id", "event": "case",
                   "event_value": "1",
                   "covariates": "age, bmi, egfr, donor_age", "time_zero": "yes"}
        d = parse_reply(prof, dict(answers))
        check(d.design == "nested case-control" and d.time_col is None,
              "the declaration resolves to a matched design", f"{d.design}")
        ex = d.as_exprs("NC")
        check(set(ex) == {"z_expr", "y_expr", "stratum_expr"},
              "the matched design emits y_expr and stratum_expr, not time/delta",
              f"{sorted(ex)}")
        try:
            parse_reply(prof, dict(answers, stratum=""))
            check(False, "a matched design without a matched set is refused",
                  "it was accepted")
        except DeclarationError as exc:
            check("matched-set" in str(exc) or "nested case-control" in str(exc),
                  "a matched design without a matched set is refused",
                  str(exc)[:90])

        # ---- B2. the set column named AS the follow-up time ------------------
        # 2026-09-15 (synth200 F08_1, F20_8): "Matched set = set_id" read as the
        # time column passes the backing check (the name is in the message) and
        # would run the matched study as a cohort with the set number as its
        # follow-up. The data flags the column; the design question is reopened.
        hdr("B2. a follow-up time shaped like a matched set reopens the design question")
        c = complete(prof, {"time": "set_id", "event": "case", "event_value": "1",
                            "covariates": "age, bmi, egfr, donor_age", "time_zero": "yes"},
                     sources={"time": "quoted"})
        check("0" in c.missing and "1" in c.missing and not c.answers.get("time")
              and "matched-set" in c.sources.get("design", ""),
              "the reading's time = the set column -> items 0 and 1 are asked, "
              "the time is not settled", f"missing={c.missing}")
        c2 = complete(prof, {"time": "set_id", "event": "case", "event_value": "1",
                             "covariates": "age, bmi, egfr, donor_age", "time_zero": "yes"},
                      sources={"time": "reply"})
        check(c2.answers.get("time") == "set_id" and "0" not in c2.missing,
              "the same column answered BY NUMBER after the question stands",
              "the analyst said NO to the design question")
        # a coarse follow-up time looks set-shaped too (many small groups) but its
        # groups vary in size: the rule needs the regular shape of a matched sample
        import copy
        # (2026-09-30: a coarse time also lacks the profile's `one_case_per_set` --
        # exactly one event in every group is the matched sample's defining fact,
        # so the model of a coarse time drops both)
        prof_irregular = copy.deepcopy(prof)
        for col in prof_irregular["columns"]:
            if col["name"] == "set_id":
                col["regular_sets"] = False
                col.pop("one_case_per_set", None)
        c4 = complete(prof_irregular, {"time": "set_id", "event": "case", "event_value": "1",
                                       "covariates": "age, bmi", "time_zero": "yes"}, sources={"time": "quoted"})
        check(c4.answers.get("time") == "set_id" and "0" not in c4.missing,
              "a set-shaped column whose groups are NOT of one size (a coarse time) stands as the time")
        # irregular sets that still hold one case each ARE a matched sample
        # (random controls leave the late sets short): the design is asked
        prof_short = copy.deepcopy(prof)
        for col in prof_short["columns"]:
            if col["name"] == "set_id":
                col["regular_sets"] = False
        c5 = complete(prof_short, {"time": "set_id", "event": "case", "event_value": "1",
                                   "covariates": "age, bmi", "time_zero": "yes"}, sources={"time": "quoted"})
        check("0" in c5.missing and "1" in c5.missing,
              "irregular sets with one case in each still reopen the design question",
              f"one_case_per_set={next(c.get('one_case_per_set') for c in prof_short['columns'] if c['name']=='set_id')}")
        check(next(col for col in prof["columns"] if col["name"] == "set_id").get("regular_sets") is True,
              "the profile marks the matched-set column's groups as regular")
        c3 = complete(prof, {"time": "set_id", "stratum": "site", "event": "case",
                             "event_value": "1", "covariates": "age, bmi", "time_zero": "yes"},
                      sources={"time": "quoted"})
        check(c3.answers.get("time") == "set_id" and "0" not in c3.missing,
              "with a stratum declared as well the rule does not fire (a stratified cohort)")

        # ---- C. the falsification number, and it must REFUSE ----------------
        hdr("C. the one-case-per-set count refuses, it does not merely display")
        v = verify(prof, d, ncc, "NC", run_r=_run_r)
        card = v.render()
        check(v.admissible, "the correct declaration is admissible",
              f"refusals={[r['code'] for r in v.refusals]}")
        check("sets with exactly one case   150 of 150" in card,
              "the card states the matched-set structure as a number",
              "this is what replaces the event rate as the falsifier")

        wrong = parse_reply(prof, dict(answers, event_value="0"))
        vw = verify(prof, wrong, ncc, "NC", run_r=_run_r)
        codes = [r["code"] for r in vw.refusals]
        # The event RATE cannot catch this: 25% and 75% are both plausible
        # sampling ratios. An earlier version of the gate asked only whether any
        # set had NO case, which this passes -- every set has three.
        check(not vw.admissible and "matched_sets_not_one_case" in codes,
              "declaring the CONTROLS as cases is refused before anything fits",
              f"refusals={codes}")
        check(any("controls" in r["message"].lower() for r in vw.refusals),
              "the refusal names the mistake the analyst most likely made",
              "and the alternative reading, an n:m design")

        # ---- D. the matched cell, end to end --------------------------------
        hdr("D. nested case-control runs end to end, and replays without a model")
        res = pipeline.run(data_path=ncc, data_expr="NC", declaration=d,
                           external_beta_expr="beta_ext", profile=prof,
                           nlambda=6, run_r=_run_r)
        c = res.candidates
        check(c["facts"]["design"] == "nested case-control",
              "the design reached the fitter",
              "unreachable before today: design was a constant")
        keys = [x["key"] for x in c["candidates"]]
        check(len(keys) == 7 and not any("ridge" in k for k in keys),
              "seven candidates, none of them ridge",
              "the library has no NCC ridge, so the set must not claim one")
        check(c.get("scorer") == "cc_loglik/pooled",
              "one scale for the whole matched comparison",
              f"scorer={c.get('scorer')!r}")
        check(c["partition"]["row_order"] == "caller"
              and c["partition"]["seed_is_effective"] is False,
              "the matched partition reports its own provenance honestly",
              "get_fold_cc never reorders and never draws")
        check("ridge" not in res.report.split("## 4.")[0].split("## 3.")[1],
              "the report does not claim a ridge fit that never happened")
        # 2026-10-01: a matched sample has no follow-up, and the report must not speak of one
        check("over the follow-up actually observed" not in res.report
              and "in these matched sets, as they were sampled" in res.report,
              "the matched report's limits do not describe a follow-up it does not have")
        _s1 = res.report.split("## 2.")[0]
        check("| Censored" not in _s1 and "| Controls" in _s1 and "one per matched set" in _s1,
              "section 1 of a matched report counts cases and controls, not censored subjects")

        paths = res.save(str(tdp / "ncc_run"))
        e = dict(os.environ, BREGSURV_R_SCRIPTS=str(REPO / "mcp" / "r_scripts"))
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                            "--no-init-file", paths["repro"], ncc],
                           capture_output=True, text=True, env=e,
                           stdin=subprocess.DEVNULL, timeout=1800)
        txt = (r.stdout or "") + (r.stderr or "")
        check("fold assignment REPRODUCED" in txt,
              "the matched partition is reproduced, not assumed",
              "repro.R had to learn y_expr and stratum_expr to do this")
        check(f"selected: {c['selected']['label']}" in txt,
              "the replay reaches the same recommendation with NO model",
              c["selected"]["label"])

        # ---- E. nothing to borrow from --------------------------------------
        hdr("E. no external information is an analysis, not an R error")
        coh = build_fixture(tdp)
        pc = _run_r("profile_columns.R", {"data_path": coh, "data_expr": "D"})
        dc = parse_reply(pc, {"time": "followup_days", "event": "died",
                              "event_value": "1", "covariates": "age, bmi, egfr",
                              "time_zero": "yes"})
        rn = pipeline.run(data_path=coh, data_expr="D", declaration=dc,
                          profile=pc, nlambda=6, run_r=_run_r)
        cn = rn.candidates
        check(cn["facts"]["external_form"] == "none",
              "the absence of external information is a stated fact")
        nk = [x["key"] for x in cn["candidates"]]
        # Internal-only is manufactured as `beta = zeros, eta = 0`, so leaving
        # the borrowing members in would give nine rows carrying ONE number and
        # an argmin breaking the tie arbitrarily -- then reporting a "borrowing"
        # method as the winner of a comparison that never happened.
        check(nk == ["internal", "internal_ridge", "internal_lasso"],
              "only the members that mean something are offered", f"{nk}")
        check(cn["selected"]["borrowing"] == "none"
              if "borrowing" in cn["selected"] else True,
              "the winner is an internal-only method")
        check("## 2. External information" in rn.report
              and "nothing was borrowed" in rn.report,
              "the report says there was no external model, and stops there",
              "rather than a linkage table of three zeros")
        check("matched **by name**" not in rn.report,
              "the report does not describe matching against a model that does "
              "not exist")

        # ---- F. a stratified cohort is a third thing ------------------------
        hdr("F. time AND a stratum is a stratified cohort, not a matched design")
        ds = parse_reply(prof, {"time": "", "stratum": "set_id", "event": "case",
                                "event_value": "1", "covariates": "age, bmi",
                                "time_zero": "yes"})
        check(ds.design == "nested case-control",
              "no time plus a stratum stays matched")
        dstrat = parse_reply(pc, {"time": "followup_days", "event": "died",
                                  "event_value": "1", "stratum": "site",
                                  "covariates": "age, bmi, egfr",
                                  "time_zero": "yes"})
        check(dstrat.design == "full cohort" and dstrat.stratum_col == "site",
              "time plus a stratum is a COHORT that happens to be stratified",
              "a different analysis from a matched one")
        exs = dstrat.as_exprs("D")
        check("stratum_expr" in exs and "time_expr" in exs,
              "the stratum actually reaches the estimator",
              "as_exprs never emitted one before, so every cohort run was "
              "unstratified whatever was declared")


        # ---- G. external individual-level data ------------------------------
        hdr("G. borrowing from the external cohort's rows, not its summary")
        ind = _build(tdp, INDI_FIXTURE, "INDI")
        pi_ = _run_r("profile_columns.R", {"data_path": ind, "data_expr": "D"})
        di = parse_reply(pi_, {
            "time": "followup_days", "event": "died", "event_value": "1",
            "covariates": "age, bmi, egfr, donor_age", "time_zero": "yes",
            "external_data_expr": "EXT"})
        exi = di.as_exprs("D")
        check({"z_ext_expr", "time_ext_expr", "delta_ext_expr"} <= set(exi),
              "the external cohort's roles are addressed by the SAME names",
              "one set of column names for both tables is what makes the "
              "linkage checkable instead of positional")

        ri = pipeline.run(data_path=ind, data_expr="D", declaration=di,
                          profile=pi_, nlambda=6, run_r=_run_r)
        ci = ri.candidates
        check(ci["facts"]["external_form"] == "individual-level data",
              "the third form of external information is a recognised fact",
              "`indi` appeared zero times in run_candidates.R before today")
        ik = [x["key"] for x in ci["candidates"]]
        check(ik == ["internal", "indi", "internal_lasso", "indi_lasso",
                     "external"],
              "five members, and no ridge among them", f"{ik}")
        check(all(x["status"] == "ok" for x in ci["candidates"]),
              "every member of the individual-level set fitted",
              f"selected {ci['selected']['label']}; "
              + "; ".join(f"{x['key']}: {x['status']} {(x.get('message') or '')[:160]}"
                          for x in ci["candidates"] if x["status"] != "ok"))
        check(ci.get("scorer") == "vvh/pl_cal_theta",
              "the individual-level loss is the SAME functional as the "
              "coefficient cells",
              "external rows enter training only; the loss is over internal "
              "rows with the same -2*sum/n")
        xrow = [x for x in ci["candidates"] if x["key"] == "external"][0]
        check(xrow["label"] == "External cohort only",
              "External-only is relabelled: this beta was fitted by us, not "
              "published", f"{xrow['label']!r}")
        check(xrow["borrowing"] == "external"
              and ci["linkage"]["matched_by"] == "external cohort",
              "it is a separate row, not a point on the eta path",
              "in cox_indi the internal rows always carry weight 1, so "
              "'ignore my data entirely' is unreachable by tuning")

        paths = ri.save(str(tdp / "indi_run"))
        r2 = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                             "--no-init-file", paths["repro"], ind],
                            capture_output=True, text=True, env=e,
                            stdin=subprocess.DEVNULL, timeout=1800)
        t2 = (r2.stdout or "") + (r2.stderr or "")
        check("fold assignment REPRODUCED" in t2
              and f"selected: {ci['selected']['label']}" in t2,
              "the two-cohort analysis replays with NO model running",
              ci["selected"]["label"])

        # The decoy: same width, same names, different ORDER.
        # The DECLARATION path is immune by construction and that is worth
        # stating: as_exprs addresses both tables BY NAME, so `PERM[, c("age",
        # "bmi", "egfr", "donor_age")]` undoes the permutation on the way in.
        # The R check exists for a direct caller handing over raw matrices --
        # which is what fit_cox_indi.R has always allowed, comparing ncol and
        # nothing else. Positional selection below is how that caller looks.
        bad = _run_r("run_candidates.R", {
            "data_path": ind, "seed": 20260818, "nfolds": 5, "nlambda": 6,
            "event_value": "1",
            "z_expr": 'D[, c("age", "bmi", "egfr", "donor_age")]',
            "time_expr": 'D[["followup_days"]]',
            "delta_expr": 'D[["died"]]',
            "z_ext_expr": "PERM[, 1:4]",
            "time_ext_expr": 'PERM[["followup_days"]]',
            "delta_ext_expr": 'PERM[["died"]]'}, timeout_s=900)
        # fit_cox_indi.R compares ncol and nothing else, so this fits
        # happily and attaches every borrowed coefficient to the wrong variable.
        check(bad.get("status") == "error"
              and "same order" in str(bad.get("message", "")),
              "an external cohort whose columns are in another ORDER is refused",
              str(bad.get("message", ""))[:110])

        both = _run_r("run_candidates.R", dict(
            {"data_path": ind, "seed": 20260818, "nfolds": 5, "nlambda": 6,
             "event_value": "1", "beta_expr": "beta_ext"},
            **di.as_exprs("D")), timeout_s=900)
        check(both.get("status") == "error"
              and "one form of external information" in str(both.get("message", "")),
              "supplying two forms of external information at once is refused",
              "the set is derived from ONE form; choosing between them silently "
              "is the judgement this design removes")

        # ---- H. the discrete-time row: the third data fact ------------
        # The map of the family is kept in one place. The cells are enumerated
        # here; the fits, the gate and the replays are exercised end to end
        # by mcp/test_discrete.py (with DiSKD through the bridge).
        hdr("H. the discrete-time row is a third fact and an independent set")
        dk = pipeline.derive_candidate_keys
        cells = {
            ("full cohort", "coefficients alone", True, True):
                ["internal_discrete", "discretekl", "internal_nn", "diskd", "external_discrete"],
            ("full cohort", "coefficients and covariance", True, True):
                ["internal_discrete", "discretekl", "internal_nn", "diskd", "external_discrete"],
            ("full cohort", "coefficients alone", True, False): ["internal_discrete", "internal_nn"],
            ("full cohort", "none", True, False): ["internal_discrete", "internal_nn"],
            ("full cohort", "individual-level data", True, False): ["internal_discrete", "internal_nn"],
            ("nested case-control", "coefficients alone", True, True): [],
        }
        for (design, form, disc, base), want in cells.items():
            got = dk(design, form, discrete=disc, has_baseline=base)
            check(got == want, f"{design} / {form} / baseline={base}",
                  ", ".join(got) or "(refused by the gate)")
        check(all(k not in dk(design, form) for design in ("full cohort", "nested case-control")
                  for form in ("none", "coefficients alone", "coefficients and covariance",
                               "individual-level data")
                  for k in ("internal_discrete", "discretekl", "internal_nn", "diskd", "external_discrete")),
              "no discrete member ever enters a continuous-time cell",
              "the rows are never ranked against each other (ruling 4)")


        # a single declared covariate is an analysis, not an R error (hard set
        # H075, 2026-09-15: "incorrect number of dimensions" from the gate)
        d1 = parse_reply(pc, {"time": "followup_days", "event": "died", "event_value": "1",
                              "covariates": "age", "time_zero": "yes"})
        check(d1.as_exprs("D")["z_expr"].endswith("drop = FALSE]"),
              "one covariate is addressed as a one-column table", d1.as_exprs("D")["z_expr"])
        v1 = verify(pc, d1, coh, "D", run_r=_run_r)
        check(v1.admissible, "the gate checks a single-covariate declaration",
              f"refusals={[r['code'] for r in v1.refusals]}")

        # ---- F. the declaration decides the external table's design ----------
        # 2026-09-15 (synth200 F21, 8 of 8 with Qwen3-8B): another matched
        # sample, read BEFORE the declaration, had a covariate named as its
        # follow-up time; the line-up check then refused and told the analyst
        # to rename columns that already matched. The declaration is the fact.
        hdr("F. a matched sample named with a time column is read under the matched declaration")
        import app as APP
        from bregsurv_agent import external as X
        csv_src = (
            "args <- commandArgs(trailingOnly = TRUE)\n"
            "load(args[1]); NC$site <- NULL; NC$pid <- NULL\n"
            "write.csv(NC, args[2], row.names = FALSE)\n"
            "write.csv(NC, args[3], row.names = FALSE)\n"
            "write.csv(NC[, setdiff(names(NC), 'set_id')], args[4], row.names = FALSE)\n")
        fcsv = tdp / "mk_csv.R"; fcsv.write_text(csv_src, encoding="utf-8")
        ncc_csv, ext_csv, ext_noset = (str(tdp / "ncc.csv"), str(tdp / "external_cohort.csv"),
                                       str(tdp / "external_noset.csv"))
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                            str(fcsv), ncc, ncc_csv, ext_csv, ext_noset],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(r.returncode == 0, "the csv fixtures were written", r.stderr[-200:])
        h, s, *_ = APP.start_session(ncc_csv, None)
        tabs = X.read_tables(ext_csv)
        # the model's reading on F21: a covariate as the follow-up time
        asg = [{"table": tabs[0].name, "role": "individual_level_data",
                "time_column": "age", "event_column": "case", "event_value": "1"}]
        o = X.canonicalise(tabs, asg, {"file": "external_cohort.csv", "path": ext_csv,
                                       "format": "csv", "n_tables": 1})
        check(o.individual_data["time_column"] == "age",
              "read before the declaration, the table carries the model's time column")
        s = s.with_external(o)
        h2, _, s2, cand2, *_ = APP.submit_answer(
            "0) set_id\n2) case\n3) 1\n4) age, bmi, egfr, donor_age\n6) yes", h, s, "", "", "")
        text2 = "\n".join(t for _, t in h2 if t)
        check(cand2 is not None and s2.get("result") is not None
              and "individual" in s2["result"].candidates["facts"]["external_form"],
              "under the matched declaration the table is used, not refused",
              (s2["result"].candidates["facts"]["external_form"] if s2.get("result")
               else h2[-1][1][:160]))
        check(s2.external.individual_data["time_column"] is None
              and any("stays a covariate" in n for n in s2.external.notes),
              "the model's time column is set aside and the card says so")
        check(any(a.get("route") == "external_time_set_aside" for a in s2.actions),
              "the rule is on the record as an action")
        # the table without the set column is refused BY NAME
        tabs3 = X.read_tables(ext_noset)
        o3 = X.canonicalise(tabs3, [dict(asg[0], table=tabs3[0].name)],
                            {"file": "external_noset.csv", "path": ext_noset,
                             "format": "csv", "n_tables": 1})
        s3 = s.restart().with_external(o3)
        h4, _, s4, cand4, *_ = APP.submit_answer(
            "0) set_id\n2) case\n3) 1\n4) age, bmi, egfr, donor_age\n6) yes", h, s3, "", "", "")
        check(cand4 is None and "lacks your matched-set column 'set_id'" in h4[-1][1],
              "a matched sample without the set column is refused by name",
              h4[-1][1][:160])

        # ---- G. a refused release, selected in the message that declares -----
        # 2026-09-15 (synth200 F24, a risk-score file): with the same refusal on
        # record, Qwen3-8B ran on the cohort alone and Qwen2.5-7B, which typed
        # "use it if you can" as a selection, waited for ever. The declared
        # analysis runs; the reply restates the refusal and that nothing is borrowed.
        hdr("G. a refused release named in the declaring message: the cohort alone, said so")
        scores = tdp / "external_scores.csv"
        scores.write_text("patient,risk_score\n" + "\n".join(f"P{i},{0.1 * i:.2f}" for i in range(1, 41)) + "\n",
                          encoding="utf-8")
        hg, sg, *_ = APP.start_session(str(APP.DEMO_COHORT), str(scores))
        check(sg.get("external") is None and sg.get("external_refusal"),
              "the risk-score file is refused at the load",
              (sg.get("external_refusal") or [{}])[0].get("code"))
        msg_g = ("Use external_scores.csv if it helps. The follow-up time is followup_days, "
                 "the event is died with 1 meaning the event, and the covariates are age, bmi and egfr.")

        class _Choice:
            class message:
                content = ""
            finish_reason = "stop"

        class _Usage:
            prompt_tokens = 300
            completion_tokens = 60

        class _Comp:
            def __init__(self):
                self.choices = [_Choice()]
                self.usage = _Usage()

        class _Fake:
            base_url = "http://localhost:1/v1"

            class models:
                @staticmethod
                def list():
                    class R:
                        data = []
                    return R()

            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        name = kw["response_format"]["json_schema"]["name"]
                        if name == "intent":
                            declares = "followup_days" in json.dumps(kw.get("messages"))
                            out = {"reasoning": "q", "intents": [
                                {"kind": "select_external", "evidence": "Use external_scores.csv if it helps",
                                 "external_form": None, "external_name": "external_scores.csv",
                                 "out_of_scope_reason": None}] + ([
                                {"kind": "declare_roles", "evidence": "The follow-up time is followup_days",
                                 "external_form": None, "external_name": None, "out_of_scope_reason": None}]
                                if declares else [])}
                        elif name == "role_extraction":
                            out = {"reasoning": "q", "time_column": "followup_days",
                                   "time_evidence": "follow-up time is followup_days",
                                   "event_column": "died", "event_evidence": "the event is died",
                                   "event_value": "1", "event_value_evidence": "1 meaning the event",
                                   "covariate_columns": ["age", "bmi", "egfr"]}
                        else:
                            out = {"reasoning": "q"}
                        c = _Comp()
                        c.choices[0].message.content = json.dumps(out)
                        return c

        APP._client = lambda endpoint, api_key: _Fake()
        hg2, _, sg2, cg2, *_ = APP.submit_answer(msg_g, hg, sg, "http://localhost:1/v1", "fake",
                                                 "", write_prose=False, tz_known=True)
        textg = "\n".join(t for _, t in hg2 if t)
        check(cg2 is not None and sg2.get("result") is not None
              and sg2["result"].candidates["facts"]["external_form"] == "none",
              "the declared analysis runs on the cohort alone",
              (sg2["result"].candidates["facts"]["external_form"] if sg2.get("result")
               else hg2[-1][1][:200]))
        check("could not be used" in textg and "nothing is borrowed" in textg,
              "the reply restates the refusal and that nothing is borrowed")
        check(any(a.get("route") == "refused_external_selected" for a in sg2.actions),
              "the decision is on the record as an action")
        # the same selection with NO analysis in the message still waits
        hg3, _, sg3, cg3, *_ = APP.submit_answer("Use external_scores.csv if it helps.", hg, sg,
                                                 "http://localhost:1/v1", "fake", "",
                                                 write_prose=False, tz_known=True)
        check(cg3 is None and "No external file is loaded" in hg3[-1][1],
              "a bare selection of the refused file still waits for a usable one",
              hg3[-1][1][:120])

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
