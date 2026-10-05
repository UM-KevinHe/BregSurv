#!/usr/bin/env python3
"""Component 4 (Memory): the published-model catalogue, the one constrained
call that names an entry (harness half only), the per-user store, and the
remembered declaration flowing through `complete` and through the app.

No model (a fake answers the one call), no GPU. Section E needs R and gradio
(it runs the app end to end on a COPY of the demo cohort with memory pointed
at a temp file) and is skipped without them.

    python mcp/test_memory.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
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
    from bregsurv_agent import memory, policy
    from bregsurv_agent.declaration import complete

    # ------------------------------------------------------------ A. catalogue
    hdr("A. the catalogue is well-formed metadata, and nothing else")
    cat = memory.catalogue()
    ids = memory.catalogue_ids()
    check(len(cat) >= 5 and len(set(ids)) == len(ids), "entries load; ids unique", str(ids))
    need = ("id", "source", "organ", "donor_type", "population", "outcome", "horizon",
            "model_class", "release", "contents", "files")
    check(all(all(k in m for k in need) for m in cat), "every entry carries the required fields")
    check(all(m["source"] in memory.sources() for m in cat),
          "every entry's source is described (how to obtain, reduction note)")
    src = memory.sources()["SRTR"]
    check(len(src["how_to_obtain"]) >= 3 and "does not try" in src["how_to_obtain"][-1]
          and "refuses this per-level layout" in src["reduction_note"],
          "SRTR: the analyst downloads, the agent does not; per-level tables must be reduced")
    raw = memory.CATALOGUE_PATH.read_text(encoding="utf-8")
    check(not any(w in raw.lower() for w in ("patient_id", "mrn", "date_of_birth"))
          and "coefficient\"," not in raw,
          "no patient data and no coefficient VALUES in the catalogue (metadata only)")
    card = memory.render_entry(memory.entry("srtr.kiddadgs1y.202607"))
    check(any("how to obtain" in l for l in card) and any("before uploading" in l for l in card)
          and any("graft survival" in l for l in card),
          "an entry renders as a card: what it is, how to obtain, how to reduce")
    lst = memory.listing()
    check(all(i in lst for i in ids) and "\n" in lst, "the prompt listing names every id")

    hdr("B. an uploaded file is matched to a published one by checksum")
    hit = memory.match_file("2eb405ccea8d13cd" + "0" * 48)
    check(hit is not None and hit["id"] == "srtr.kiddadps1y.202607"
          and hit["file"] == "kiddadps1y_202607_coefficients.csv",
          "the 2026-07 kidney patient-survival coefficients are recognised")
    check(memory.match_file("deadbeef" * 8) is None and memory.match_file(None) is None,
          "an unknown or absent checksum matches nothing")
    priv = Path(os.environ.get("BREGSURV_PRIVATE_FIXTURES",
                               REPO.parent / "real_data" / "external_fixtures"))
    f = priv / "srtr" / "kiddadps1y_202607_coefficients.csv"
    if f.exists():
        import hashlib
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        check(memory.match_file(sha) is not None and memory.match_file(sha)["release"] == "202607",
              "the private SRTR release file on disk hashes to its catalogue entry")
    else:
        print("  SKIP  private SRTR fixture not present")

    # ------------------------------------------------------------ C. the call
    hdr("C. the one constrained call: schema from the catalogue, harness verifies")
    sch = memory.propose_schema()
    check(list(sch["properties"]) == ["reasoning", "matches"]
          and sch["properties"]["matches"]["items"]["properties"]["id"]["enum"] == ids
          and sch["properties"]["matches"]["maxItems"] == 3,
          "reasoning first; ids are an enum of the current catalogue; at most three")
    msg = ("We want to borrow from the SRTR one-year deceased-donor kidney graft "
           "survival model, the July 2026 release.")
    good = {"reasoning": "q", "matches": [
        {"id": "srtr.kiddadgs1y.202607", "evidence": "one-year deceased-donor kidney graft survival"},
        {"id": "srtr.kiddadgs1y.202105", "evidence": "one-year deceased-donor kidney graft survival"},
        {"id": "srtr.kiddadps1y.202607", "evidence": "patient survival model we never mentioned"}]}
    got = memory.validate_proposal(msg, good)
    check([g["id"] for g in got] == ["srtr.kiddadgs1y.202607", "srtr.kiddadgs1y.202105"],
          "ids kept only with evidence that is in the message; an invented span is dropped",
          str([g["id"] for g in got]))
    check(memory.validate_proposal(msg, {"reasoning": "q", "matches": [
              {"id": "srtr.not.a.model", "evidence": "SRTR"}]}) == [],
          "an id outside the catalogue is dropped even with real evidence")
    check(memory.validate_proposal(msg, {"reasoning": "q", "matches": []}) == [],
          "an empty proposal is an empty list, not an error")
    # the 2026-09-11 Qwen3 habit: the right id, but the catalogue line copied as evidence
    got2 = memory.validate_proposal(msg, {"reasoning": "q", "matches": [
        {"id": "srtr.kiddadgs1y.202607",
         "evidence": "SRTR kidney, deceased donor, adult recipients (18+); graft survival; 1 year after transplant"}]})
    check(got2 and got2[0]["id"] == "srtr.kiddadgs1y.202607" and got2[0]["verified_by"] == "message keywords",
          "a match whose evidence is the catalogue's wording is kept when the analyst's own words carry "
          "the organ, outcome and horizon", str(got2))
    check(memory.validate_proposal("We want the SRTR one-year kidney graft survival model.", {"reasoning": "q", "matches": [
              {"id": "srtr.kiddadps3y.202607", "evidence": "catalogue words"}]}) == [],
          "and dropped when they do not (patient survival, three years: neither is in the message)")
    check(memory.supported_by("the kidney waiting-list transplant rate model", memory.entry("srtr.wl_ki_ad_txrate.202607"))
          and not memory.supported_by("the kidney waiting-list transplant rate model", memory.entry("srtr.kiddadgs1y.202607")),
          "supported_by: organ + outcome (+ horizon where the entry has one)")
    check("published_model" in policy.NAMES
          and "harness will ask" in policy.load("published_model"),
          "the call has a policy file of the fixed shape (test_policy pins the shape)")

    # ------------------------------------------------------------ D. the store
    hdr("D. the per-user store: on locally, off on a shared host, never time zero")
    tmp = Path(tempfile.mkdtemp(prefix="bregsurv_mem_"))
    st = memory.Store(path=str(tmp / "memory.json"), enabled=True)
    check(st.recall_declaration("abc") is None, "nothing remembered yet")
    ok = st.remember_declaration("abc", {"time": "t", "event": "d", "event_value": "1",
                                         "covariates": "age, bmi", "time_zero": "yes"},
                                 {"time": "quoted", "event": "quoted", "time_zero": "checkbox"},
                                 file_name="cohort.csv", columns=["t", "d", "age", "bmi"])
    rec = st.recall_declaration("abc")
    check(ok and rec is not None and rec["answers"] == {"time": "t", "event": "d",
                                                       "event_value": "1",
                                                       "covariates": "age, bmi"},
          "the declaration is remembered by file fingerprint", str(rec))
    check("time_zero" not in rec["answers"] and "time_zero" not in rec["sources"],
          "time zero is NOT remembered: it stays a person's answer every time")
    check(rec["file"] == "cohort.csv" and rec["n_columns"] == 4 and rec.get("date"),
          "file name, column count and date travel with it")
    st.set_preference("write_prose", True)
    check(st.preference("write_prose") is True and st.preference("nope", 7) == 7,
          "one preference round-trips")
    disk = json.loads((tmp / "memory.json").read_text())
    check("declarations" in disk and "abc" in disk["declarations"]
          and not any(k in json.dumps(disk) for k in ("raw_text", "prompt")),
          "the file holds declarations and preferences, no rows, no prompts")
    st.forget_declaration("abc")
    check(st.recall_declaration("abc") is None, "forget removes it")
    off = memory.Store(path=str(tmp / "off.json"), enabled=False)
    check(not off.remember_declaration("abc", {"time": "t"}, {}) and off.recall_declaration("abc") is None
          and not (tmp / "off.json").exists(),
          "disabled: nothing written, nothing recalled")
    saved = dict(os.environ)
    try:
        os.environ["DEPLOYMENT_MODE"] = "demo"
        os.environ.pop("BREGSURV_MEMORY", None)
        check(memory.Store().enabled is False, "DEPLOYMENT_MODE=demo turns memory off")
        os.environ["DEPLOYMENT_MODE"] = "local"
        os.environ["BREGSURV_MEMORY"] = "off"
        check(memory.Store().enabled is False, "BREGSURV_MEMORY=off turns it off locally too")
        os.environ["BREGSURV_MEMORY"] = str(tmp / "elsewhere.json")
        check(memory.Store().enabled and memory.Store().path == tmp / "elsewhere.json",
              "BREGSURV_MEMORY=<path> relocates it")
    finally:
        os.environ.clear(); os.environ.update(saved)
    bad = tmp / "corrupt.json"; bad.write_text("{not json")
    stb = memory.Store(path=str(bad), enabled=True)
    check(stb.recall_declaration("abc") is None and stb.remember_declaration("abc", {"time": "t"}, {}),
          "a corrupt file reads as empty and is rewritten; memory never breaks a run")

    # ------------------------------------------------------------ E. complete
    hdr("E. a remembered declaration is a disclosed SOURCE in complete()")
    prof = {"columns": [{"name": "t", "type": "numeric"}, {"name": "d", "type": "numeric",
                                                            "values": ["0", "1"]},
                        {"name": "age", "type": "numeric"}, {"name": "bmi", "type": "numeric"}],
            "eligible": {"time": ["t", "age"], "event": ["d"], "covariate": ["age", "bmi"]},
            "complementary_pairs": []}
    remembered = {"answers": {"time": "t", "event": "d", "event_value": "1",
                              "covariates": "age, bmi"}, "date": "2026-09-11"}
    c = complete(prof, {}, None, remembered=remembered)
    check(c.answers.get("time") == "t" and c.answers.get("covariates") == "age, bmi"
          and c.sources["time"].startswith("remembered: you declared this for the same file on 2026-09-11"),
          "roles left unsaid come from memory, with the date, as a source", str(c.sources))
    check(c.missing == ["6"], "time zero is STILL asked: memory never answers it", str(c.missing))
    c2 = complete(prof, {"covariates": "age"}, None, remembered=remembered)
    check(c2.answers["covariates"] == "age" and "covariates" not in c2.sources,
          "what the analyst says now wins over what was remembered")
    c3 = complete(prof, {}, None, remembered=None)
    check(c3.missing == ["1", "6"] or "1" in c3.missing,
          "without memory the two eligible time columns are asked, as before", str(c3.missing))

    # ------------------------------------------------------------ F. through the app
    hdr("F. through the app: remembered on a second load of the same file")
    try:
        import app  # noqa: F401
        from bregsurv_agent.rbridge import _find_rscript
        have_r = _find_rscript() is not None
    except Exception as exc:  # pragma: no cover
        app = None; have_r = False
        print(f"  SKIP  app import failed ({type(exc).__name__})")
    if app is not None and have_r:
        work = Path(tempfile.mkdtemp(prefix="bregsurv_memapp_"))
        cohort = work / "my_cohort.csv"
        shutil.copy(app.DEMO_COHORT, cohort)
        saved = dict(os.environ)
        try:
            os.environ["DEPLOYMENT_MODE"] = "local"
            os.environ["BREGSURV_MEMORY"] = str(work / "memory.json")
            # first session: numbered reply, verified, run -> remembered
            h1, s1, *_ = app.start_session(str(cohort), None)
            check(s1 is not None and s1.remembered is None and s1.data_sha256,
                  "first load: nothing remembered, file fingerprinted")
            out1 = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) age, bmi, egfr\n6) yes",
                                     h1, s1, "", "", "")
            h1b, _, s1b, cand1, *_ = out1
            check(cand1 is not None and s1b.has_result, "the run completes",
                  h1b[-1][1][:100] if cand1 is None else "")
            disk = json.loads((work / "memory.json").read_text())
            rec = disk["declarations"].get(s1.data_sha256, {})
            check(rec.get("answers", {}).get("event") == "died"
                  and "time_zero" not in rec.get("answers", {}),
                  "the verified declaration is on disk under the file's fingerprint, without time zero",
                  str(rec.get("answers")))
            check((s1b.result.provenance.get("session") or {}).get("memory", {}).get("enabled") is True,
                  "trace.json says memory was on and where it lives")
            # second session on the SAME bytes: recalled, one message runs
            cohort2 = work / "renamed_copy.csv"
            shutil.copy(cohort, cohort2)
            h2, s2, *_ = app.start_session(str(cohort2), None)
            check(s2.remembered is not None and "I remember how you described this file" in h2[0][1],
                  "second load (same bytes, other name): the declaration is recalled and said so")
            out2 = app.submit_answer("6) yes", h2, s2, "", "", "")
            h2b, _, s2b, cand2, *_ = out2
            srcs = (s2b.declaration.sources or {}) if s2b.declaration else {}
            check(cand2 is not None and all(str(srcs.get(k, "")).startswith("remembered")
                                            for k in ("time", "event", "covariates")),
                  "one message (the time-zero answer) runs it; the card credits memory",
                  str(srcs))
            check((s2b.result.provenance.get("session") or {}).get("remembered_declaration") is True,
                  "provenance records that a remembered declaration was used")
            # memory off: the same file is asked again
            os.environ["BREGSURV_MEMORY"] = "off"
            h3, s3, *_ = app.start_session(str(cohort2), None)
            check(s3.remembered is None and "I remember" not in h3[0][1],
                  "with memory off the same file is not recalled")
            # the shipped example is never remembered
            os.environ["BREGSURV_MEMORY"] = str(work / "memory.json")
            h4, s4, *_ = app.start_session()
            check(s4.remembered is None, "the shipped example never has a remembered declaration")

            # G. naming a published model with no file uploaded: the one call,
            # answered by a fake, its ids and evidence verified by the harness,
            # the catalogue card returned, nothing fitted
            hdr("G. through the app: 'we use the SRTR model' with no file -> the catalogue card")

            class _Msg:
                content = None

            class _Choice:
                finish_reason = "stop"

                def __init__(self):
                    self.message = _Msg()

            class _Usage:
                prompt_tokens = 300
                completion_tokens = 40

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
                                out = {"reasoning": "q", "intents": [
                                    {"kind": "describe_external",
                                     "evidence": "SRTR one-year deceased-donor kidney graft survival model",
                                     "external_form": "coefficients_with_baseline_hazard",
                                     "out_of_scope_reason": None}]}
                            elif name == "published_model":
                                out = {"reasoning": "q", "matches": [
                                    {"id": "srtr.kiddadgs1y.202607",
                                     "evidence": "one-year deceased-donor kidney graft survival"},
                                    {"id": "srtr.wl_ki_ad_txrate.202607",
                                     "evidence": "words the analyst never wrote"}]}
                            else:
                                out = {"reasoning": "q"}
                            c = _Comp()
                            c.choices[0].message.content = json.dumps(out)
                            return c

            app._client = lambda endpoint, api_key: _Fake()
            h5, s5, *_ = app.start_session(str(cohort2), None)   # no external file
            out5 = app.submit_answer(
                "We would like to borrow from the SRTR one-year deceased-donor kidney "
                "graft survival model; we have not downloaded it yet.", h5, s5,
                "http://localhost:1/v1", "fake", "")
            h5b, _, s5b, *r5 = out5
            reply = h5b[-1][1]
            check(all(r is None for r in r5) and "srtr.kiddadgs1y.202607" in reply
                  and "how to obtain it" in reply and "I do not download it" in reply,
                  "the matching entry's card is returned and nothing is fitted", reply[:160])
            check("srtr.wl_ki_ad_txrate.202607" not in reply,
                  "an entry whose evidence is not in the message is dropped by the harness")
            names = [c["name"] for c in s5b.model_calls]
            check(names[-2:] == ["intent", "published_model"],
                  "the two calls are logged in order", str(names))
        finally:
            os.environ.clear(); os.environ.update(saved)
            shutil.rmtree(work, ignore_errors=True)
    else:
        print("  SKIP  section F needs gradio and Rscript")

    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
