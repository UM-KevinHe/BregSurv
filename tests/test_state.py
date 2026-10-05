#!/usr/bin/env python3
"""Component 3 (State): the typed session, its derived phase, its transitions
and its provenance. No model, no R, no GPU.

    python mcp/test_state.py
"""
from __future__ import annotations

import json
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
    from bregsurv_agent.state import Phase, Session, ROLE_KEYS
    from bregsurv_agent.declaration import Declaration, Verification
    from bregsurv_agent.external import ExternalObject
    from bregsurv_agent import intent

    prof = {"n_rows": 10, "n_columns": 4,
            "columns": [{"name": c} for c in ("t", "d", "age", "bmi")]}
    decl = Declaration(time_col="t", event_col="d", event_value="1",
                       covariates=["age", "bmi"], source="reply",
                       covariates_time_zero="yes",
                       sources={"time": "quoted", "event": "quoted"})
    ok_v = Verification(admissible=True, card=["ok"])
    bad_v = Verification(admissible=False, card=["no"],
                         refusals=[{"code": "x", "message": "no"}])

    # ------------------------------------------------------------ A. phase
    hdr("A. the phase is derived from the fields, never stored")
    s0 = Session()
    check(s0.phase is Phase.EMPTY and s0.invariants() == [], "empty session: EMPTY, coherent")
    s1 = s0.with_profile("/x.csv", "D", prof)
    check(s1.phase is Phase.PROFILED, "after the profile: PROFILED")
    check(s0.phase is Phase.EMPTY and s0.actions == [],
          "transitions return a NEW session; the old one is untouched")
    s2 = s1.start_turn("time is t and the event is d").with_pending(
        {"time": "t", "event": "d"}, {"time": "quoted", "event": "quoted"},
        asked=["event_value", "covariates"])
    check(s2.phase is Phase.DECLARING and s2.questions == 1,
          "open roles: DECLARING, and the question is counted")
    s3 = s2.with_declaration(decl, bad_v)
    check(s3.phase is Phase.REFUSED and s3.pending == {},
          "a refused declaration: REFUSED, pending cleared")
    s4 = s2.with_declaration(decl, ok_v)
    check(s4.phase is Phase.VERIFIED, "an admissible declaration: VERIFIED")
    s5 = s4.with_result(object(), "/tmp/out")
    check(s5.phase is Phase.DONE and s5.has_result and "/tmp/out" in s5.temp,
          "a result: DONE, and the artifact dir is remembered for the purge")
    s6 = s5.with_pending({"time": "t"}, {"time": "reply"})
    check(s6.phase is Phase.DECLARING and s6.has_result,
          "an edit after a result: DECLARING again, the result still there")

    # ------------------------------------------------------------ B. state line
    hdr("B. the state line the model sees is computed from the object")
    check(s1.state_line() == ("State: cohort loaded: yes | external information: none | "
                              "declaration: none | result: none"),
          "profiled, nothing else", s1.state_line())
    check("declaration: partial (time, event)" in s2.state_line(),
          "partial declaration lists the settled roles in role order", s2.state_line())
    check("declaration: declared but refused" in s3.state_line()
          and "declaration: verified" in s4.state_line()
          and "result: present" in s5.state_line(),
          "refused / verified / present")
    coef = ExternalObject(form="coefficients", scale="log_hazard_ratio",
                          terms={"age": 0.1, "bmi": -0.2}, provenance={})
    check("coefficients (2 terms)" in s1.with_profile("/x.csv", "D", prof,
                                                      external=coef).state_line(),
          "a coefficient table: form and term count")
    cov = ExternalObject(form="coefficients_with_covariance", scale="log_hazard_ratio",
                         terms={"age": 0.1, "bmi": -0.2}, provenance={},
                         Q=[[1.0, 0.0], [0.0, 1.0]], Q_from="precision as published")
    check("with precision matrix" in s1.with_profile("/x.csv", "D", prof,
                                                     external=cov).state_line(),
          "a covariance: says the precision matrix is there")
    indi = ExternalObject(form="individual_level_data", scale="log_hazard_ratio",
                          terms={}, provenance={},
                          individual_data={"path": "/e.csv", "columns": ["t", "d", "age"],
                                           "time_column": "t", "event_column": "d"})
    line = s1.with_profile("/x.csv", "D", prof, external=indi).state_line()
    check("individual-level records (3 columns)" in line,
          "the individual-level cell no longer reads 'none' (the dict-key drift)", line)
    check("a file was uploaded and refused" in s1.with_profile(
              "/x.csv", "D", prof, external_refusal=[{"code": "x", "message": "m"}]).state_line(),
          "a refused file is a fact the model is told")
    check(intent.state_line(s2) == s2.state_line(),
          "intent.state_line delegates to the session")
    check("external information: published coefficients (3)" in intent.state_line(
              {"profile": prof, "coefs": {"a": 1, "b": 2, "c": 3}}),
          "intent.state_line still accepts the check scripts' plain dict")

    # ------------------------------------------------------------ C. invariants
    hdr("C. invariants name what is incoherent")
    from dataclasses import replace
    check(replace(s1, result=object()).invariants()
          == ["a result exists without a declaration",
              "a result exists although the declaration was not verified admissible"],
          "a result with no declaration")
    check("a result exists although the declaration was not verified admissible"
          in replace(s3, result=object()).invariants(),
          "a result on a refused declaration")
    check(replace(s1, pending={"colour": "red"}).invariants()
          == ["pending carries non-role keys: ['colour']"],
          "a pending key that is not a role")
    check(all(s.invariants() == [] for s in (s0, s1, s2, s3, s4, s5, s6)),
          "every state the transitions produce is coherent")
    check(set(ROLE_KEYS) >= {"time", "event", "event_value", "covariates", "time_zero"},
          "ROLE_KEYS covers the numbered question's roles")

    # ------------------------------------------------------------ D. log
    hdr("D. the action log carries every transition with the phase before and after")
    walk = [a["phase"] for a in s6.actions if "transition" in a]
    check(walk == [["empty", "profiled"], ["profiled", "declaring"],
                   ["declaring", "verified"], ["verified", "done"], ["done", "declaring"]],
          "phase before/after on every transition", str(walk))
    check(s6.phase_walk() == ["empty", "profiled", "declaring", "verified", "done", "declaring"],
          "phase_walk is the sequence of phases", str(s6.phase_walk()))
    asked = [a for a in s6.actions if a.get("asked")]
    check(asked and asked[0]["asked"] == ["event_value", "covariates"],
          "the roles that were asked are on the transition that asked them")
    s7 = s6.log(route="intent", intents=[{"kind": "other"}]).start_turn("hello")
    check(s7.actions[-2]["route"] == "intent" and s7.actions[-1]["turn"] == 2
          and s7.turns == 2 and s7.phase is s6.phase,
          "log() and start_turn() record without changing the phase")
    s8 = s7.take_calls([{"name": "intent", "prompt_tokens": 10}])
    check(len(s8.model_calls) == 1 and s7.model_calls == [],
          "take_calls appends; the earlier session is unchanged")
    s9 = s8.restart()
    check(s9.phase is Phase.PROFILED and s9.turns == 0 and s9.questions == 0
          and s9.external is s8.external and s9.actions[-1]["transition"] == "restarted",
          "restart(): same cohort and release, nothing declared, counters reset")
    s10 = s1.with_external(coef)
    check(s10.external is coef and s10.actions[-1]["phase"] == ["profiled", "profiled"],
          "with_external(): a release read after the cohort, logged, phase unchanged")
    # M2: several releases, one active; a run history
    cov2 = ExternalObject(form="coefficients_with_covariance", scale="log_hazard_ratio",
                          terms={"age": 0.2}, provenance={"file": "three_year.csv"},
                          Q=[[1.0]], Q_from="precision as published")
    coef.provenance["file"] = "one_year.csv"
    s11 = s1.with_external(coef).with_external(cov2)
    check(list(s11.externals) == ["one_year.csv", "three_year.csv"] and s11.external_name == "three_year.csv",
          "each release read joins `externals` under its file name; the latest is active")
    s12 = s11.select_external("one_year.csv")
    check(s12.external is coef and s12.actions[-1]["transition"] == "select_external"
          and "external files loaded: one_year.csv, three_year.csv (active: one_year.csv)" in s12.state_line(),
          "select_external() switches the active one, logged, and the state line says so")
    try:
        s11.select_external("nope.csv"); check(False, "an unknown name raises")
    except KeyError:
        check(True, "selecting a release that is not loaded raises")
    s13 = s12.with_declaration(decl, ok_v).with_result("r1").with_pending({"time": "t"}, {"time": "reply"}) \
             .with_declaration(decl, ok_v).with_result("r2")
    check(s13.results == ["r1", "r2"] and s13.result == "r2" and "runs so far: 2" in s13.state_line()
          and s13.to_provenance()["n_results"] == 2,
          "every run is kept in order; the latest is `result`; the count is in the state line")

    # ------------------------------------------------------------ E. provenance
    hdr("E. provenance is JSON-safe and carries the evaluation's two numbers")
    p = s4.to_provenance()
    json.dumps(p)
    check(p["phase"] == "verified" and p["questions_asked"] == 1
          and p["completed_in_one_message"] is False,
          "a run reached after one question: not completed in one message", str(p))
    one = (Session().with_profile("/x.csv", "D", prof).start_turn("do it")
           .with_pending({"time": "t", "event": "d"}, {"time": "quoted", "event": "quoted"})
           .with_declaration(decl, ok_v))
    p1 = one.to_provenance()
    check(p1["turns"] == 1 and p1["questions_asked"] == 0
          and p1["completed_in_one_message"] is True,
          "a run reached from the first message with no question: completed in one")
    check(p1["declaration_sources"] == {"time": "quoted", "event": "quoted"}
          and p1["invariants_violated"] == [],
          "sources and (empty) violations travel with it")

    # ------------------------------------------------------------ F. compat
    hdr("F. name access for drivers and tests is strict")
    check(s5.get("result") is s5.result and s5["temp"] == s5.temp
          and s5.get("_temp") == s5.temp,
          "get()/[] read the fields; the old `_temp` key is aliased")
    try:
        s5.get("declaraton")
        check(False, "a misspelt key raises")
    except KeyError:
        check(True, "a misspelt key raises instead of reading as None")
    check(("profile" in s5) and ("declaration" in s5) and not ("declaration" in s1)
          and not ("pending" in s5),
          "`in` means the field holds something; an empty dict does not count")
    try:
        "profil" in s5  # noqa: B015
        check(False, "`in` with a misspelt key raises")
    except KeyError:
        check(True, "`in` with a misspelt key raises too")
    try:
        s5.turns = 99  # type: ignore[misc]
        frozen = False
    except Exception:
        frozen = True
    check(frozen and s6.pending is not s2.pending
          and s2.pending == {"time": "t", "event": "d"} and s3.pending == {},
          "the session is frozen, and its dict fields are replaced, never edited in place")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
