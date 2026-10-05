#!/usr/bin/env python3
"""Component 2 (Instructions / Policy) and the boundary-1 backing check.

No model, no R, no GPU. Three things are pinned:

  A. every boundary's policy is a file with the five fixed headings, the
     purpose of `reasoning` stated in the prompt (not in a schema description
     the model never sees), null scoped to the role fields, the ghost-column
     rule, the no-digit rule where prose is written, and every enum the
     schema offers named in the text -- so a schema and its policy cannot
     drift apart silently;
  B. the modules send exactly the file's text, and provenance can name it;
  C. `textmatch` -- the ONE predicate the corpus builder and the harness
     share -- and `boundary.backed_roles`, the runtime check that a model-proposed
     name is `quoted` only if the analyst wrote it.

    python mcp/test_policy.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  -- {note}" if note else ""))


def hdr(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def main() -> int:
    from bregsurv_agent import policy, textmatch, boundary, intent, external

    # ---------------------------------------------------------------- A
    hdr("A. every policy file has the fixed shape and says what it must")
    for name in policy.NAMES:
        text = policy.load(name)
        secs = policy.sections(name)
        order = [h for h in text.split("\n") if h.startswith("## ")]
        check(order == list(policy.HEADINGS),
              f"{name}: the five headings, in order", str(order))
        check(text.startswith("# "), f"{name}: opens with a title line")
        before = secs.get("## Before you decide", "")
        check("`reasoning`" in before,
              f"{name}: the purpose of `reasoning` is stated IN the prompt",
              "a schema description never reaches the model (2026-08-20)")
        check(all(secs[h].strip() for h in policy.HEADINGS),
              f"{name}: no section is empty")
        check("\r" not in text, f"{name}: LF line endings")

    r = policy.load("role_extraction")
    check("null" in policy.sections("role_extraction")["## The fields"]
          and "It is not an answer for `reasoning`" in r,
          "role_extraction: null is scoped to the four roles and denied to reasoning")
    check("not in the column list, return it exactly as they wrote it" in r,
          "role_extraction: the ghost-column rule (decision d) is in the prompt")
    check("Covariates are never filled from a description" in r and "word for word" in r
          and "time_evidence" in r and "event_evidence" in r,
          "role_extraction: a described time/event column may be resolved WITH its verbatim "
          "phrase; covariates never (decision b, revised 2026-09-11)")
    check("spaces or hyphens" in r and "underscores" in r,
          "role_extraction: the three accepted spellings are the ones textmatch accepts")

    i = policy.load("intent")
    check(all(k in i for k in intent.KINDS),
          "intent: every kind the schema offers is described", str(intent.KINDS))
    check(all(k in i for k in intent.OUT_OF_SCOPE_REASONS),
          "intent: every out-of-scope reason the schema offers is named")
    check("state line says a result exists" in i,
          "intent: 'about this result' vs 'about the method' is decided by the state line",
          "case 1 (job 60955756) routed a result question to the method answer")

    e = policy.load("external_roles")
    roles = ("coefficients", "covariance", "precision", "baseline_hazard",
             "individual_level_data", "ignore")
    check(all(x in e for x in roles), "external_roles: all six table roles described")
    check("never a row" in e, "external_roles: says the model sees no row")

    for name in ("report_prose", "explain"):
        t = policy.load(name)
        check("square brackets" in t and "Do not write any number" in t,
              f"{name}: named references only, no numbers")
        check(not re.search(r"\d", t),
              f"{name}: the prompt itself contains no digit",
              "a digit in the prompt is a digit the model may copy")
    p = policy.sections("report_prose")["## The fields"]
    check(all(k in p for k in ("data", "linkage", "candidates", "comparison", "selected")),
          "report_prose: the five sections the schema requires are described")

    # ---------------------------------------------------------------- B
    hdr("B. the modules send the file's text, and provenance names it")
    check(boundary._EXTRACT_SYSTEM == policy.load("role_extraction")
          and boundary._PROSE_SYSTEM == policy.load("report_prose")
          and boundary._EXPLAIN_SYSTEM == policy.load("explain")
          and intent._INTENT_SYSTEM == policy.load("intent")
          and external._ASSIGN_SYSTEM == policy.load("external_roles"),
          "each boundary's system prompt IS its policy file, verbatim")
    d = policy.describe()
    check(set(d) == set(policy.NAMES)
          and all(v["sha256"].startswith("sha256:") and v["chars"] > 200 for v in d.values()),
          "describe(): one hash per policy, for provenance.model.policies")
    check(len({v["sha256"] for v in d.values()}) == len(d),
          "the five hashes are distinct")

    # ---------------------------------------------------------------- B2
    hdr("B2. decoding is a property of the act, with the thinking / seed switches")
    import os
    saved = dict(os.environ)
    try:
        for k in ("BREGSURV_THINKING", "BREGSURV_TEMPERATURE", "BREGSURV_SEED"):
            os.environ.pop(k, None)
        q = boundary.decoding_for("role_extraction"); w = boundary.decoding_for("report_prose")
        # V4: unset means "per act" -- reading and writing acts send thinking off
        p = boundary.decoding_for("analysis_plan")
        check(q["temperature"] == 0.0 and w["temperature"] == 0.7 and q["thinking"] is False
              and w["thinking"] is False and p["thinking"] is True,
              "quoting acts are greedy, writing acts are sampled, only the planning acts think",
              f"{q} {w} {p}")
        os.environ["BREGSURV_THINKING"] = "on"
        t = boundary.decoding_for("role_extraction")
        check(t["thinking"] is True and t["temperature"] == 0.6 and t["top_p"] == 0.95,
              "thinking on: never greedy (the Qwen3 guidance), and the switch is sent", str(t))
        os.environ["BREGSURV_THINKING"] = "off"
        check(boundary.decoding_for("intent")["thinking"] is False,
              "thinking off is sent explicitly (Qwen3 thinks by default)")
        os.environ["BREGSURV_TEMPERATURE"] = "0"; os.environ["BREGSURV_SEED"] = "7"
        r = boundary.decoding_for("report_prose")
        check(r["temperature"] == 0.0 and r["seed"] == 7,
              "a global temperature override and a seed, for repeatable evaluation")
    finally:
        os.environ.clear(); os.environ.update(saved)

    # ---------------------------------------------------------------- C
    hdr("C. textmatch: one predicate for the corpus and the harness")
    cols = ["followup_days", "died", "age", "donor_age", "survival_time_days", "site"]
    msg = "Follow-up is in followup_days, and died is 1 when the patient died. Adjust for donor age."
    got = textmatch.names_mentioned(msg, cols)
    check(set(got) == {"followup_days", "died", "donor_age"},
          "names the analyst wrote, and only those; `donor age` is donor_age, not age",
          str(got))
    check("survival_time_days" in textmatch.names_mentioned(
              "time is survival-time-days here", cols),
          "underscore -> hyphen is an accepted spelling")
    check(textmatch.names_mentioned("the age of the donor", ["donor_age"]) == [],
          "no stemming, no synonyms: 'age of the donor' does not name donor_age")
    check(textmatch.mentions("the event is hla_mismatch", "hla_mismatch", cols),
          "a ghost column the analyst wrote is backed (so it can be refused by name)")
    check(not textmatch.mentions("adjust for age", "site", cols),
          "a column the analyst did not write is not backed")
    check(textmatch.value_mentioned("died is 1 when", "1")
          and not textmatch.value_mentioned("transplanted in 2011", "1")
          and textmatch.value_mentioned("status is Dead", "dead"),
          "event values: token match, digits do not match inside numbers")

    # verify_corpus imports the same function
    sys.path.insert(0, str(REPO / "eval"))
    import verify_corpus  # noqa: E402
    check(verify_corpus.names_mentioned is textmatch.names_mentioned,
          "eval/verify_corpus.py uses the SAME function object as the harness")

    hdr("C2. boundary.backed_roles: what the model proposes vs what the analyst wrote")
    try:
        import app  # needs gradio
        check(app._backed_roles is boundary.backed_roles,
              "the app runs the SAME predicate the live check measures")
    except Exception as exc:  # pragma: no cover
        print(f"  SKIP  app import failed ({type(exc).__name__}); the predicate is tested directly")
    if True:
        prof = {"columns": [{"name": c} for c in cols],
                "eligible": {"time": ["followup_days", "survival_time_days"],
                             "event": ["died"], "covariate": ["age", "donor_age", "site"]}}
        ext = {"time_column": "followup_days", "event_column": "died",
               "event_value": "1", "covariate_columns": ["age", "site", "donor_age"]}
        backed, unbacked, how = boundary.backed_roles(
            "Time is followup_days, death is coded 1, adjust for age and donor age.",
            prof, ext)
        check(backed == {"time": "followup_days", "event_value": "1",
                         "covariates": "age, donor_age"}
              and all(v == "quoted" for v in how.values()),
              "backed: the time column, the value and the two written covariates, all quoted",
              str(backed))
        check(unbacked == {"event": "died", "covariates": ["site"]},
              "unbacked: the guessed event column (no phrase) and the added covariate, per role",
              str(unbacked))
        backed2, unbacked2, _ = boundary.backed_roles(
            "Adjust for site.", prof,
            {"time_column": None, "event_column": None, "event_value": None,
             "covariate_columns": ["age"]})
        check(backed2 == {} and unbacked2 == {"covariates": ["age"]},
              "a covariate list with no written name is a gap, not a partial quote")
        # decision (b) revised: a DESCRIBED role, with its verbatim phrase, on an eligible column
        msg_d = "We know how long each patient was followed and whether they reached the endpoint."
        b3, u3, h3 = boundary.backed_roles(msg_d, prof, {
            "time_column": "followup_days", "time_evidence": "how long each patient was followed",
            "event_column": "died", "event_evidence": "whether they reached the endpoint",
            "event_value": None, "covariate_columns": None})
        check(b3 == {"time": "followup_days", "event": "died"}
              and h3["time"] == 'described: "how long each patient was followed"'
              and h3["event"].startswith("described:"),
              "a described time and event column are accepted WITH the phrase, as `described`",
              f"{b3} {h3}")
        b4, u4, _ = boundary.backed_roles(msg_d, prof, {
            "time_column": "followup_days", "time_evidence": "the duration of observation",
            "event_column": "age", "event_evidence": "whether they reached the endpoint",
            "event_value": None, "covariate_columns": None})
        check(b4 == {} and u4 == {"time": "followup_days", "event": "age"},
              "a phrase the analyst did not write, or a column not eligible for the role, is dropped",
              f"{b4} {u4}")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
