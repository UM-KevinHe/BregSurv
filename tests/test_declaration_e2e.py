"""End-to-end test driver for C7, the role-declaration protocol.

The language model is not involved anywhere in this suite, which is the point: the
protocol is deterministic, so it does not depend on a 7B being good at extraction.

The case that matters most is `event_complement`. `survival_event` (1 = death) and
`survival_censored` (1 = censored) are exact complements, and no amount of looking
at the data can tell you which one the analyst meant. What the harness CAN do is
say they are complements and then print the consequence -- 25% events against 75%
-- which is a number a clinician rejects instantly. That number, not the column
name, is the safety mechanism.

Run:  python test_declaration_e2e.py
Exits non-zero if any case fails.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

# The R bridge lives in the agent package, not in the MCP server: testing
# the agent must not require the MCP SDK. See bregsurv_agent/rbridge.py.
from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from bregsurv_agent.declaration import (  # noqa: E402
    Declaration, DeclarationError, from_dictionary, parse_reply, render_question,
    verify,
)

GREEN, RED, YEL, DIM, OFF = ("\033[32m", "\033[31m", "\033[33m",
                             "\033[2m", "\033[0m")
passed = failed = skipped = 0

FIXTURE_R = r"""
args <- commandArgs(trailingOnly = TRUE)
set.seed(5)
n <- 200
D <- data.frame(
  subject_id = sprintf("S%04d", seq_len(n)),
  age        = round(rnorm(n, 55, 12), 1),
  bmi        = round(rnorm(n, 27, 4), 1),
  egfr       = round(rnorm(n, 60, 15), 1),
  sex        = factor(sample(c("F", "M"), n, TRUE)),
  site       = 1,
  creat_last = ifelse(runif(n) < 0.7, NA, round(rnorm(n, 1.2, 0.4), 2)),
  survival_time_days = round(rexp(n, 1 / 400)) + 1,
  stringsAsFactors = FALSE
)
D$survival_time_years <- round(D$survival_time_days / 365.25, 3)
D$survival_event      <- rbinom(n, 1, 0.25)
D$survival_censored   <- 1 - D$survival_event
beta_ext <- c(age = 0.03, bmi = -0.01, egfr = -0.02, donor_age = 0.02)
save(D, beta_ext, file = args[1])
cat("fixture:", nrow(D), "rows,", ncol(D), "columns,",
    sum(D$survival_event), "events\n")
"""


def _events(v):
    """(n_events, n_obs) from the gate summary, or None."""
    s = (v.gate or {}).get("summary") or {}
    if s.get("n_events") is None or not s.get("n_obs"):
        return None
    return int(s["n_events"]), int(s["n_obs"])


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def skip(label, note=""):
    global skipped
    skipped += 1
    print(f"  {YEL}SKIP{OFF}  {label}   {DIM}{note}{OFF}")


def build_fixture(td: Path) -> str:
    src = td / "mkfix.R"
    src.write_text(FIXTURE_R, encoding="utf-8")
    rda = td / "Cohort.rda"
    r = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                        "--no-init-file", str(src), str(rda)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit("could not build the fixture")
    print(DIM + r.stdout.strip() + OFF)
    return str(rda)


def profile(rda: str, **extra) -> dict:
    return _run_r("profile_columns.R",
                  {"data_path": rda, "data_expr": "D",
                   "external_beta_expr": "beta_ext", **extra})


# ------------------------------------------------------------------ 1. the facts
def test_profile(p):
    print("\n" + "=" * 78)
    print("1. the profiler emits facts, and the traps are among them")
    print("=" * 78)
    check(p.get("status") == "ok", "profile_columns runs",
          str(p.get("message", ""))[:70])
    names = {c["name"] for c in p["columns"]}
    check(names >= {"survival_event", "survival_censored"},
          "every column is described", f"{len(names)} columns")
    pairs = [tuple(x) for x in p["complementary_pairs"]]
    check(("survival_event", "survival_censored") in pairs,
          "the exact-complement pair is detected", f"pairs={pairs}")
    q = {e["name"]: e["reason"] for e in p["quarantined"]}
    check(set(q) == {"subject_id", "site", "creat_last"},
          "identifier, constant and mostly-missing set aside",
          "; ".join(f"{k}: {v}" for k, v in q.items()))
    check("survival_event" not in p["eligible"]["time"]
          and "survival_time_days" in p["eligible"]["time"],
          "a two-level column is not offered as a follow-up time",
          f"time candidates={p['eligible']['time']}")
    ext = p["external"]
    check(ext["n_matched"] == 3 and ext["unmatched"] == ["donor_age"],
          "external name matching is reported as a fact",
          f"matched={ext['n_matched']}, unmatched={ext['unmatched']}")
    txt = render_question(p)
    import re as _re
    check("exact complements" in txt and "known AT THE START" in txt
          and _re.search(r"min .+ / median .+ / max ", txt) is not None,
          "the question warns about the complement and shows distributions",
          "one message, five numbered items")


# ------------------------------------------------------- 2. deterministic parsing
def test_parse(p):
    print("\n" + "=" * 78)
    print("2. the reply is parsed deterministically -- no model involved")
    print("=" * 78)
    times = p["eligible"]["time"]
    events = p["eligible"]["event"]
    i_t = times.index("survival_time_days") + 1
    i_e = events.index("survival_event") + 1

    d = parse_reply(p, {"time": str(i_t), "event": str(i_e), "event_value": "1",
                        "covariates": "A", "time_zero": "yes"})
    check(d.time_col == "survival_time_days" and d.event_col == "survival_event"
          and d.covariates == ["age", "bmi", "egfr"],
          "numbered answers resolve", f"{d.time_col} / {d.event_col} / {d.covariates}")

    d2 = parse_reply(p, {"time": "survival_time_years", "event": "survival_event",
                         "event_value": "1", "covariates": "A plus egfr",
                         "time_zero": "yes"})
    check(d2.time_col == "survival_time_years" and d2.covariates == ["age", "bmi", "egfr"],
          "column names resolve, and 'A plus <already in A>' is idempotent",
          f"{d2.covariates}")

    d3 = parse_reply(p, {"time": str(i_t), "event": str(i_e), "event_value": "1",
                         "covariates": "A minus bmi", "time_zero": "yes"})
    check(d3.covariates == ["age", "egfr"], "'A minus <name>' edits the preset",
          f"{d3.covariates}")

    d4 = parse_reply(p, {"time": str(i_t), "event": str(i_e), "event_value": "1",
                         "covariates": "age, egfr and bmi", "time_zero": "yes"})
    check(d4.covariates == ["age", "egfr", "bmi"], "an explicit list resolves",
          f"{d4.covariates}")

    d5 = parse_reply(p, {"time": str(i_t), "event": str(i_e), "event_value": "1",
                         "covariates": "B", "time_zero": "yes"})
    # The presets are computed before anyone has said which column is the
    # outcome, so "every usable numeric column" necessarily contains the
    # follow-up time and the event indicator. They are dropped here, because a
    # column cannot be a predictor of itself -- arithmetic, not inference.
    usable = set(p["eligible"]["covariate"])
    expected = usable - {"survival_time_days", "survival_event"}
    check(set(d5.covariates) == expected,
          "preset B is every usable numeric column MINUS the outcome",
          f"{len(usable)} usable -> {len(d5.covariates)} after dropping the outcome")
    check(any("excluded from the preset" in n for n in d5.notes),
          "and the exclusion is stated, not silent", d5.notes[-1])

    # naming the outcome EXPLICITLY is a real mistake and is not quietly fixed
    d6 = parse_reply(p, {"time": str(i_t), "event": str(i_e), "event_value": "1",
                         "covariates": "age, survival_event", "time_zero": "yes"})
    check("survival_event" in d6.covariates,
          "an explicitly listed outcome column is kept, for verify to refuse",
          f"{d6.covariates}")

    for label, answers, needle, item in [
        ("an out-of-range number is refused",
         {"time": "99", "event": "1", "event_value": "1", "covariates": "A"},
         "not one of the", "1"),
        ("an unknown column name is refused",
         {"time": "days", "event": "1", "event_value": "1", "covariates": "A"},
         "no column called", "1"),
        ("a value that does not occur in the event column is refused",
         {"time": str(i_t), "event": str(i_e), "event_value": "2", "covariates": "A"},
         "does not occur in", "3"),
        ("the whole phrase as an event value is refused (Qwen2.5 on MIUM)",
         {"time": str(i_t), "event": str(i_e), "event_value": "1 if they died, 0 if not",
          "covariates": "A"},
         "does not occur in", "3"),
        ("removing something not in the preset is refused",
         {"time": str(i_t), "event": str(i_e), "event_value": "1",
          "covariates": "A minus subject_id"},
         "cannot be removed", "4"),
        ("a missing answer is refused, not defaulted",
         {"time": str(i_t), "event": str(i_e), "event_value": "", "covariates": "A"},
         "which value means the event", "3"),
    ]:
        try:
            parse_reply(p, answers)
            check(False, label, "it was accepted")
        except DeclarationError as e:
            check(needle in str(e) and e.item == item, label,
                  f"item {e.item}: {str(e)[:70]}")


# ---------------------------------------------------- 3. verification + the gate
def test_verify(p, rda):
    print("\n" + "=" * 78)
    print("3. the declaration is verified against the data, and may be refused")
    print("=" * 78)
    base = dict(covariates=["age", "bmi", "egfr"], source="reply",
                covariates_time_zero="yes")

    good = Declaration(time_col="survival_time_days", event_col="survival_event",
                       event_value="1", **base)
    v = verify(p, good, rda, "D", run_r=_run_r)
    card = v.render()
    check(v.admissible, "a correct declaration passes",
          [l.strip() for l in card.splitlines() if "events" in l][:1])
    n_good = _events(v)
    check(n_good is not None and 0 < n_good[0] < n_good[1],
          "the card states the event count the analyst can falsify",
          f"{n_good[0]} of {n_good[1]}" if n_good else "no event line")

    # THE case: the analyst names the complement of the event column
    wrong = Declaration(time_col="survival_time_days",
                        event_col="survival_censored", event_value="1", **base)
    vw = verify(p, wrong, rda, "D", run_r=_run_r)
    cw = vw.render()
    n_bad = _events(vw)
    ok = (n_good and n_bad and n_good[1] == n_bad[1]
          and n_good[0] + n_bad[0] == n_good[1]
          and abs(n_good[0] - n_bad[0]) / n_good[1] > 0.3)
    check(ok, "naming the complement shows an event rate the analyst will reject",
          f"{n_good[0]}/{n_good[1]} ({100*n_good[0]//n_good[1]}%) against "
          f"{n_bad[0]}/{n_bad[1]} ({100*n_bad[0]//n_bad[1]}%) -- the two readings "
          f"partition the cohort" if ok else f"{n_good} vs {n_bad}")
    check(any("complement" in a["message"] for a in vw.advisories),
          "and the complement is named explicitly", "advisory present")

    for label, decl, code in [
        ("the outcome listed as a predictor is refused",
         Declaration(time_col="survival_time_days", event_col="survival_event",
                     event_value="1",
                     covariates=["age", "survival_event"], source="reply",
                     covariates_time_zero="yes"),
         "outcome_used_as_covariate"),
        ("one column named as both time and event is refused",
         Declaration(time_col="survival_event", event_col="survival_event",
                     event_value="1", **base),
         "time_is_event"),
        ("a factor covariate is refused by the gate",
         Declaration(time_col="survival_time_days", event_col="survival_event",
                     event_value="1", covariates=["age", "sex"], source="reply",
                     covariates_time_zero="yes"),
         "covariate_not_numeric"),
        ("an unanswered time-zero question fails CLOSED",
         Declaration(time_col="survival_time_days", event_col="survival_event",
                     event_value="1", covariates=["age", "bmi"], source="reply"),
         "time_zero_undeclared"),
        ("'no' to the time-zero question is refused",
         Declaration(time_col="survival_time_days", event_col="survival_event",
                     event_value="1", covariates=["age", "bmi"], source="reply",
                     covariates_time_zero="no"),
         "time_varying_covariates"),
    ]:
        vv = verify(p, decl, rda, "D", run_r=_run_r)
        codes = [r["code"] for r in vv.refusals]
        check(not vv.admissible and code in codes, label, f"codes={codes}")


# ------------------------------------------------------------------ 4. path 1
def test_dictionary(rda, td):
    print("\n" + "=" * 78)
    print("4. a data dictionary NARROWS the question; it does not answer it")
    print("=" * 78)

    # (a) a dictionary shaped like the real one: two time units, a complement pair
    amb = td / "dict_ambiguous.csv"
    with open(amb, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variable", "role"])
        for v in ["survival_time_days", "survival_time_years",
                  "survival_event", "survival_censored"]:
            w.writerow([v, "primary_outcome"])
        for v in ["age", "bmi", "egfr"]:
            w.writerow([v, "baseline"])
        w.writerow(["subject_id", "identifier"])
    p = profile(rda, dictionary_path=str(amb))
    check(p["dictionary"]["present"] and len(p["dictionary"]["outcome_ish"]) == 4,
          "the dictionary is read and narrows the outcome-ish set",
          f"outcome_ish={p['dictionary']['outcome_ish']}")
    check(from_dictionary(p) is None,
          "two time units and a complement pair leave a CHOICE -> still ask",
          "from_dictionary declines, as it must")

    # (b) an unambiguous dictionary: exactly one time, exactly one 0/1 event
    ok = td / "dict_clean.csv"
    with open(ok, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variable", "role"])
        w.writerow(["survival_time_days", "primary_outcome"])
        w.writerow(["survival_event", "primary_outcome"])
        w.writerow(["survival_time_years", "measurement_timing"])
        w.writerow(["survival_censored", "quality_flag"])
        for v in ["age", "bmi", "egfr"]:
            w.writerow([v, "baseline"])
        w.writerow(["subject_id", "identifier"])
    p2 = profile(rda, dictionary_path=str(ok))
    d = from_dictionary(p2)
    check(d is not None and d.time_col == "survival_time_days"
          and d.event_col == "survival_event" and d.source == "dictionary",
          "an unambiguous dictionary answers it with no question asked",
          f"{d.time_col} / {d.event_col} / {d.covariates}" if d else "declined")

    # (c) the real artifact this protocol was designed around, when present
    real = (REPO.parent.parent / "real_data" / "EHR" / "mimiciv31_20260816"
            / "kidney_tx_mimiciv31" / "output" / "metadata" / "data_dictionary.csv")
    if real.exists():
        rows = list(csv.DictReader(open(real, encoding="utf-8-sig")))
        outcome = [r["variable"] for r in rows
                   if "outcome" in (r.get("role") or "").lower()]
        check(len(outcome) > 2,
              "the real dictionary marks many columns outcome-ish",
              f"{len(outcome)} variables across "
              f"{len({r['role'] for r in rows if 'outcome' in r['role'].lower()})} roles")
    else:
        skip("the real dictionary is checked too", "not on this machine")


def main():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        rda = build_fixture(tdp)
        p = profile(rda)
        if p.get("status") != "ok":
            print(RED + "profile_columns failed: " + str(p.get("message")) + OFF)
            return 1
        test_profile(p)
        test_parse(p)
        test_verify(p, rda)
        test_dictionary(rda, tdp)
    print("\n" + "=" * 78)
    print(f"RESULT: {passed}/{passed + failed} passed"
          + (f", {skipped} skipped" if skipped else ""))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
