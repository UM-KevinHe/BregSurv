"""Three deterministic checks on the model's reading of a request, added 2026-10-01 from the
rubric run's hard requests. No model and no R.

  1. the message's own wording of the event coding contradicts the value read -> asked (item 3):
     "alive ... is 0 when the patient died and 1 when they were alive" read as 1 (H009 and five
     more); "event_flag is 1 if the event occurred, 0 otherwise" on a column of 1 and 2 (H042,
     H044, H048);
  2. a longer name the analyst wrote is kept, so it is refused by name (H046:
     "hla_mismatch_count" read as the file's `hla_mismatch`);
  3. an invented, unwritten name no longer blocks the every-other-column rule (H004).

Each check is also tested where it must NOT fire, since a false conflict costs a question.

Run: python mcp/test_reading_checks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    passed += bool(ok); failed += not ok
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))


def _prof(cols, values):
    """A profile with the fields the backing check reads."""
    return {"columns": [{"name": c, "values": values.get(c)} for c in cols],
            "eligible": {"time": [c for c in cols if c.endswith(("days", "_mo", "event"))],
                         "event": [c for c in cols if c in values],
                         "covariate": [c for c in cols if c not in values]}}


def main():
    from bregsurv_agent import boundary as B
    from bregsurv_agent.declaration import complete

    C = B._event_coding_conflict
    h009 = ("Hi, one thing to flag before anything else: in this export the outcome column is "
            "called alive and it is 0 when the patient died and 1 when they were alive at last "
            "contact, the opposite of our usual coding. Follow-up is followup_days.")
    check(C(h009, "alive", ["0", "1"], "1") is not None, "reversed coding read as 1 is a conflict")
    check(C(h009, "alive", ["0", "1"], "0") is None, "reversed coding read as 0 is not")
    h042 = ("train.csv: time_to_event is the follow-up in years and event_flag is 1 if the event "
            "occurred, 0 otherwise. Use all other columns as predictors.")
    w = C(h042, "event_flag", ["1", "2"], "1")
    check(w is not None and "0" in w and "1 and 2" in w,
          "a code the column does not hold is a conflict", str(w))
    h048 = "train.csv, os_mo = time in days, status2 = 1 for an event (0 otherwise). Predictors x1..x10."
    check(C(h048, "status2", ["1", "2"], "1") is not None, "the parenthetical '(0 otherwise)' is read")
    check(C(h048, "status2", ["0", "1"], "1") is None, "the same words on a 0/1 column are no conflict")
    for msg, ev, chosen in [("died = 1 means the patient died", "died", "1"),
                            ("died is 1 if it happened, 0 if not", "died", "1"),
                            ("alive is 0 if the event occurred and 1 otherwise", "alive", "0"),
                            ("The event: alive (0 = event).", "alive", "0"),
                            ("died: 42 events among 300 patients; died = 1 for death.", "died", "1"),
                            ("Follow-up is followup_days and died marks the event.", "died", "1")]:
        check(C(msg, ev, ["0", "1"], chosen) is None, f"no false conflict: {msg[:48]}")
    check(C("alive is 0 if the event occurred and 1 otherwise", "alive", ["0", "1"], "1") is not None,
          "'1 otherwise' read as the event is a conflict")
    check(C("The event: alive (0 = event).", "alive", ["0", "1"], "1") is not None,
          "terse '(0 = event)' read as 1 is a conflict")

    # complete asks rather than filling the 0/1 rule
    prof = _prof(["followup_days", "alive", "age", "bmi"], {"alive": ["0", "1"]})
    comp = complete(prof, {"time": "followup_days", "event": "alive", "event_value": None,
                           "covariates": "age, bmi", "time_zero": "yes"},
                    sources={"event_value": "ask: your message describes `alive` = 1 as not the event"})
    check("3" in comp.missing and not comp.answers.get("event_value"),
          "a contradicted value is asked, never filled by the 0/1 rule", str(comp.missing))
    comp2 = complete(prof, {"time": "followup_days", "event": "alive", "event_value": None,
                            "covariates": "age, bmi", "time_zero": "yes"}, sources={})
    check(comp2.answers.get("event_value") == "1", "without a conflict the 0/1 rule still applies")

    # the backing check end to end on the event value: the message labels ONE code
    # the column holds as the event, so that code is taken (2026-10-02; it used to ask)
    ext = {"time_column": "followup_days", "event_column": "alive", "event_value": "1",
           "covariate_columns": ["age", "bmi"]}
    backed, unbacked, how = B._backed_roles_checked(h009 + " Adjust for age and bmi.", prof, ext)
    check(backed.get("event_value") == "0" and str(how.get("event_value", "")).startswith("quoted (")
          and unbacked.get("event_value_corrected") == {"read": "1", "taken": "0"},
          "the code the message labels as the event is taken over the reading's", str(how.get("event_value")))
    L = B._labelled_event_code
    check(L(h009, "alive", ["0", "1"]) == "0", "H009: 0 is the labelled event code")
    h063 = ("train.csv. The outcome column is alive, coded 0 for death and 1 for alive at last "
            "contact; follow-up is followup_days.")
    check(L(h063, "alive", ["0", "1"]) == "0", "H063: 0 is the labelled event code")
    check(L(h042, "event_flag", ["1", "2"]) is None, "a labelled code the column lacks: nothing taken")
    check(L("died is 1 if it happened, 0 if not", "died", ["0", "1"]) == "1", "a plain 1 = event")
    check(L("Follow-up is followup_days and died marks the event.", "died", ["0", "1"]) is None,
          "no code written: nothing taken")
    # a code the column does not hold is still asked
    prof12 = _prof(["time_to_event", "event_flag", "age"], {"event_flag": ["1", "2"]})
    ext12 = {"time_column": "time_to_event", "event_column": "event_flag", "event_value": "1",
             "covariate_columns": ["age"]}
    b12, u12, s12 = B._backed_roles_checked(h042 + " Adjust for age.", prof12, ext12)
    check(b12.get("event_value") is None and str(s12.get("event_value", "")).startswith("ask:"),
          "a code the column does not hold is asked", str(s12.get("event_value")))

    # 2. near miss
    cols = ["followup_days", "died", "age", "bmi", "egfr", "cold_ischemia", "hla_mismatch", "donor_age"]
    msg46 = ("Cohort in train.csv, followup_days in days, died = 1 for death. Adjust for age, bmi, "
             "egfr, cold_ischemia and hla_mismatch_count only.")
    check(B._written_near_miss(msg46, "hla_mismatch", cols) == "hla_mismatch_count",
          "the longer written name is found")
    check(B._written_near_miss("adjust for donor_age", "age", cols) is None,
          "a written name that IS a column is no near miss")
    check(B._written_near_miss("our agent reads ages", "age", cols) is None,
          "a word that merely contains the column is no near miss")
    prof46 = _prof(cols, {"died": ["0", "1"]})
    ext46 = {"time_column": "followup_days", "event_column": "died", "event_value": "1",
             "covariate_columns": ["age", "bmi", "egfr", "cold_ischemia", "hla_mismatch"]}
    b46, u46, _ = B._backed_roles_checked(msg46, prof46, ext46)
    check("hla_mismatch_count" in (b46.get("covariates") or "") and "hla_mismatch_count" in u46.get("near_miss", {}),
          "the analyst's own name is kept, so verify refuses it by name", str(b46.get("covariates")))

    # 2b. the same longer name when the reading left it out altogether (H046, second pass)
    ext46b = dict(ext46, covariate_columns=["age", "bmi", "egfr", "cold_ischemia"])
    b46b, u46b, _ = B._backed_roles_checked(msg46, prof46, ext46b)
    check("hla_mismatch_count" in (b46b.get("covariates") or "")
          and u46b.get("near_miss", {}).get("hla_mismatch_count") == "hla_mismatch",
          "an omitted longer name is put back, so verify refuses it by name", str(b46b.get("covariates")))
    b46c, u46c, _ = B._backed_roles_checked(
        "followup_days, died = 1. Adjust for age, bmi and egfr.", prof46,
        dict(ext46, covariate_columns=["age", "bmi", "egfr"]))
    check(b46c.get("covariates") == "age, bmi, egfr" and "near_miss" not in u46c,
          "an explicit list with no longer name is left as written", str(b46c.get("covariates")))
    b46d, _, _ = B._backed_roles_checked(
        "followup_days, died = 1; use every other column; the hla_mismatch_count is in hla_mismatch.",
        prof46, dict(ext46, covariate_columns=["age", "bmi", "egfr", "cold_ischemia", "donor_age"]))
    check("hla_mismatch_count" not in (b46d.get("covariates") or ""),
          "a message that says the other columns are predictors is not given the longer name",
          str(b46d.get("covariates")))

    # 2c. the pending state keeps an open question on a role with no value (H063)
    from bregsurv_agent.state import Session
    s = Session().with_pending({"time": "followup_days", "event": "alive", "event_value": None},
                               {"time": "quoted", "event": "quoted",
                                "event_value": "ask: your message describes `alive` = 1 as not the event"})
    check(str(s.pending_sources.get("event_value", "")).startswith("ask:")
          and "event_value" not in s.pending,
          "an 'ask:' source is kept although the value is not pending")
    check(not any("pending_sources" in v for v in s.invariants()),
          "and the state invariants accept it", str(s.invariants()))
    s2 = Session().with_pending({"time": "followup_days"}, {"time": "quoted", "event": "quoted"})
    check("event" not in s2.pending_sources, "any other source of an unset role is still dropped")

    # 3. the every-other-column rule with an invented name in the reading
    labs = [f"lab_{i:02d}" for i in range(1, 41)]
    cols4 = ["followup_days", "died", "age", "bmi", "egfr", "hla_mismatch"] + labs
    prof4 = _prof(cols4, {"died": ["0", "1"]})
    msg4 = ("Hello, this is the cohort with the extended lab panel (lab_01 to lab_40 are the "
            "standardised lab values). train.csv: followup_days is days of follow-up, died = 1 "
            "means the patient died. Please put every column other than those two into the model.")
    ext4 = {"time_column": "followup_days", "event_column": "died", "event_value": "1",
            "covariate_columns": ["age", "bmi", "egfr", "hl_a_mismatch"] + labs}
    b4, _, s4 = B._backed_roles_checked(msg4, prof4, ext4)
    check(b4.get("covariates") == "B", "a range in an aside does not replace 'every other column'",
          str(b4.get("covariates"))[:80])
    msg4b = "followup_days and died = 1. Use lab_01 to lab_40 as the predictors."
    ext4b = dict(ext4, covariate_columns=["lab_01", "lab_40"])
    b4b, _, _ = B._backed_roles_checked(msg4b, prof4, ext4b)
    check(b4b.get("covariates", "").count("lab_") == 40, "a range on its own still expands")
    msg4c = "followup_days and died = 1. Add recipient_cmv_status and everything else."
    ext4c = dict(ext4, covariate_columns=["recipient_cmv_status", "age", "bmi"])
    b4c, _, _ = B._backed_roles_checked(msg4c, prof4, ext4c)
    check("recipient_cmv_status" in (b4c.get("covariates") or ""),
          "a ghost the analyst wrote is still kept for the refusal by name", str(b4c.get("covariates")))

    print(f"\nRESULT: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
