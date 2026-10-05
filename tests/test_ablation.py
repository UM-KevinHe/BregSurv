"""The ablation switches (bregsurv_agent/ablation.py, 2026-09-13): each removes one piece of
the harness for a measurement, is off unless BREGSURV_ABLATE names it, and is recorded.

Run: python mcp/test_ablation.py      (sections C-E need gradio and Rscript, like test_m2)
"""
from __future__ import annotations

import json
import os
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


def hdr(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def main():
    from bregsurv_agent import ablation, boundary
    hdr("A. the switch")
    os.environ.pop("BREGSURV_ABLATE", None)
    check(ablation.cells() == [] and not ablation.on("no_backing") and ablation.describe() == {"removed": []},
          "nothing is removed unless the variable names it")
    os.environ["BREGSURV_ABLATE"] = "no_backing, no_verify"
    check(ablation.on("no_backing") and ablation.on("no_verify") and not ablation.on("no_constrained"),
          "a comma list removes exactly what it names", str(ablation.describe()))
    os.environ["BREGSURV_ABLATE"] = "no_grammar"
    try:
        ablation.cells(); check(False, "an unknown piece is refused")
    except ValueError as e:
        check("no_grammar" in str(e), "an unknown piece is refused", str(e)[:60])
    os.environ.pop("BREGSURV_ABLATE", None)

    hdr("B. no_backing: the model's names are taken as quoted, and still reported")
    prof = {"columns": [{"name": n} for n in ("followup_days", "died", "age", "bmi", "egfr", "site")],
            "eligible": {"time": ["followup_days"], "event": ["died"]}}
    msg = "Time is followup_days and death is coded 1. Please adjust for age and bmi."
    ext = {"time_column": "followup_days", "event_column": "died", "event_value": "1",
           "covariate_columns": ["age", "bmi", "site"]}
    b0, u0, s0 = boundary.backed_roles(msg, prof, ext)
    check(u0.get("event") == "died" and u0.get("covariates") == ["site"] and "event" not in b0,
          "with the check: the guessed event column and the unmentioned covariate are dropped", str(u0))
    # a name the model respelled (Qwen3: hla_mismatch -> hl_a_mismatch) is the column the
    # analyst wrote; a name that matches nothing is still dropped
    prof2 = {"columns": [{"name": n} for n in ("followup_days", "died", "age", "hla_mismatch", "site")],
             "eligible": {"time": ["followup_days"], "event": ["died"]}}
    msg2 = "Time is followup_days, died is 1 for death. Adjust for age and hla_mismatch."
    b2, u2, s2 = boundary.backed_roles(msg2, prof2, {"time_column": "followup_days", "event_column": "died",
                                                       "event_value": "1", "covariate_columns": ["age", "hl_a_mismatch", "sight"]})
    check(b2.get("covariates") == "age, hla_mismatch" and u2.get("covariates") == ["sight"]
          and "spelling matched" in s2["covariates"] and "hl_a_mismatch -> hla_mismatch" in s2["covariates"],
          "a respelled covariate is matched letter for letter to the column the analyst wrote; an alien name is dropped",
          str((b2.get("covariates"), u2, s2.get("covariates"))))
    os.environ["BREGSURV_ABLATE"] = "no_backing"
    b1, u1, s1 = boundary.backed_roles(msg, prof, ext)
    check(b1.get("event") == "died" and b1.get("covariates") == "age, bmi, site"
          and s1["event"].startswith("quoted (unbacked; ablation") and u1 == u0,
          "without it: the same names are fitted as quoted, and the drop list is still returned",
          str(s1))
    os.environ.pop("BREGSURV_ABLATE", None)

    class _Usage:
        prompt_tokens = 10; completion_tokens = 5

    hdr("B2. the reader's headers-over-model checks, and the recorded JSON repair (2026-09-13)")
    from bregsurv_agent import external as X
    import pandas as pd
    def _tab(name, df):
        return X.RawTable(name=name, columns=[{"name": c, "type": ("text" if df[c].dtype == object else "numeric")} for c in df.columns],
                          n_rows=len(df), frame=df)
    hr = _tab("external_hazard_ratios", pd.DataFrame(
        {"variable": ["age", "bmi"], "hazard_ratio": [1.2, 0.8], "ci_lower": [1.0, 0.6], "ci_upper": [1.4, 1.0]}))
    raw = {"tables": [{"table": "external_hazard_ratios", "role": "coefficients", "name_column": "variable",
                       "coefficient_column": "hazard_ratio", "coefficient_scale": "log_hazard_ratio"}]}
    asg, iss = X.check_assignment([hr], raw)
    check(asg[0]["coefficient_scale"] == "hazard_ratio" and any(i["code"] == "scale_from_header" for i in iss),
          "a column headed hazard_ratio is a hazard ratio whatever the model wrote, and the issue is recorded",
          str(iss)[:100])
    vc = _tab("external_model.vcov", pd.DataFrame({"name": ["age", "bmi"], "age": [1.0, 0.1], "bmi": [0.1, 1.0]}))
    raw = {"tables": [{"table": "external_model.vcov", "role": "precision", "name_column": "name"}]}
    asg, iss = X.check_assignment([vc], raw)
    check(asg[0]["role"] == "covariance" and any(i["code"] == "matrix_role_from_name" for i in iss),
          "a table named vcov is a covariance whatever the model wrote", str(iss)[:100])
    # the repair: an escaped single quote inside a string
    class _Msg2:
        content = '{"reasoning": "the \\\'external_cohort\\\' table", "answer": "x"}'
    class _Choice2:
        finish_reason = "stop"
        def __init__(self): self.message = _Msg2()
    class _Comp2:
        def __init__(self): self.choices = [_Choice2()]; self.usage = _Usage()
    class _Fake2:
        base_url = "http://localhost:1/v1"
        class chat:
            class completions:
                @staticmethod
                def create(**kw): return _Comp2()
    out = boundary._chat(_Fake2(), "fake", "sys", "u", {"type": "object"}, "explain", max_tokens=50)
    check(out.get("answer") == "x" and boundary.CALLS[-1].get("repaired") == "escaped single quote",
          "an escaped single quote is repaired once and the repair is recorded", str(out)[:80])
    boundary.call_log(clear=True)

    hdr("C. no_constrained: no response_format is sent; braces are parsed out of free text")
    seen = {}

    class _Usage:
        prompt_tokens = 10; completion_tokens = 5

    class _Msg:
        content = 'Sure! ```json\n{"reasoning": "q", "answer": "x"}\n```'

    class _Choice:
        finish_reason = "stop"
        def __init__(self): self.message = _Msg()

    class _Comp:
        def __init__(self): self.choices = [_Choice()]; self.usage = _Usage()

    class _Fake:
        base_url = "http://localhost:1/v1"
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    seen.update(kw); return _Comp()
    schema = {"type": "object", "properties": {"reasoning": {"type": "string"}, "answer": {"type": "string"}},
              "required": ["reasoning", "answer"], "additionalProperties": False}
    os.environ["BREGSURV_ABLATE"] = "no_constrained"
    out = boundary._chat(_Fake(), "fake", "sys", "user text", schema, "explain", max_tokens=50)
    check("response_format" not in seen and "JSON schema" in seen["messages"][1]["content"]
          and out == {"reasoning": "q", "answer": "x"},
          "the schema is in the prompt, not enforced; the fenced object is recovered", str(list(seen)))
    os.environ.pop("BREGSURV_ABLATE", None)
    boundary.call_log(clear=True)

    # ---- the pieces that need the R profile and the app
    try:
        import subprocess, tempfile
        rs = subprocess.run(["Rscript", "--version"], capture_output=True)
        have_r = rs.returncode == 0
    except Exception:
        have_r = False
    if not have_r:
        print("  SKIP  D-E need Rscript")
        hdr(f"RESULT: {passed}/{passed + failed} passed"); return 1 if failed else 0
    sys.path.insert(0, str(HERE))
    from test_declaration_e2e import build_fixture, profile  # noqa: E402
    from bregsurv_agent.declaration import parse_reply, DeclarationError
    td = Path(tempfile.mkdtemp(prefix="bregsurv_abl_"))
    rda = build_fixture(td)
    p = profile(rda)
    names = [c["name"] for c in p["columns"]]
    tcol = p["eligible"]["time"][0]
    ecol = "survival_event" if "survival_event" in p["eligible"]["event"] else p["eligible"]["event"][0]

    hdr("D. no_verify: a phrase as the event value, and a column the file lacks, pass through")
    ans = {"time": tcol, "event": ecol, "event_value": "1 if they died, 0 if not", "covariates": "A"}
    try:
        parse_reply(p, dict(ans)); check(False, "with the check: the phrase is refused")
    except DeclarationError as e:
        check(e.item == "3", "with the check: the phrase is refused as item 3", str(e)[:60])
    os.environ["BREGSURV_ABLATE"] = "no_verify"
    d = parse_reply(p, dict(ans))
    check(d.event_value == "1 if they died, 0 if not" and any("no_verify" in n for n in d.notes),
          "without it: the phrase reaches the declaration, with a note that says so", str(d.notes)[:120])
    ans2 = {"time": tcol, "event": ecol, "event_value": "1", "covariates": "age, bmi, no_such_column"}
    d2 = parse_reply(p, dict(ans2))
    check("no_such_column" not in d2.covariates and any("dropped silently" in n for n in d2.notes),
          "a covariate the file lacks is dropped in silence, with a note", str(d2.covariates))
    os.environ.pop("BREGSURV_ABLATE", None)

    hdr("E. no_planner_fallback: an empty plan is a dead end again")
    try:
        os.environ["BREGSURV_MEMORY"] = "off"
        import app  # noqa: E402
    except Exception as exc:
        print(f"  SKIP  app import failed ({type(exc).__name__})")
        hdr(f"RESULT: {passed}/{passed + failed} passed"); return 1 if failed else 0
    h0, s0_, *_ = app.start_session()
    ext_name = s0_.external_name
    msg_e = ("Follow-up time is in followup_days, and died is 1 if the patient died. Please "
             "fit a survival model adjusting for age, bmi and egfr, using the published "
             f"coefficients in {ext_name}.")

    class _Comp2:
        def __init__(self): self.choices = [_Choice()]; self.usage = _Usage()

    class _Fake4:
        base_url = "http://localhost:1/v1"
        class models:
            @staticmethod
            def list():
                class R: data = []
                return R()
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    name = kw["response_format"]["json_schema"]["name"]
                    if name == "intent":
                        out = {"reasoning": "q", "intents": [
                            {"kind": "multi_step", "evidence": "fit a survival model",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None},
                            {"kind": "declare_roles", "evidence": "Follow-up time is in followup_days",
                             "external_form": None, "external_name": None, "out_of_scope_reason": None}]}
                    elif name == "plan_steps":
                        out = {}
                    elif name == "role_extraction":
                        out = {"reasoning": "q", "time_column": "followup_days",
                               "time_evidence": "Follow-up time is in followup_days",
                               "event_column": "died", "event_evidence": "died is 1 if the patient died",
                               "event_value": "1", "event_value_evidence": "died is 1",
                               "covariate_columns": ["age", "bmi", "egfr"]}
                    else:
                        out = {"reasoning": "q"}
                    c = _Comp2(); c.choices[0].message = type("M", (), {"content": json.dumps(out)})(); return c
    app._client = lambda endpoint, api_key: _Fake4()
    os.environ["BREGSURV_ABLATE"] = "no_planner_fallback"
    hf, _, sf, cf, *_ = app.submit_answer(msg_e, h0, s0_, "http://localhost:1/v1", "fake", "",
                                          write_prose=False, tz_known=True)
    text_f = "\n".join(t for _, t in hf if t)
    check(cf is None and "could not turn that into steps" in text_f,
          "with the fallback removed the turn dead-ends, nothing is fitted", text_f[-100:].replace("\n", " | "))
    os.environ.pop("BREGSURV_ABLATE", None)
    hf2, _, sf2, cf2, *_ = app.submit_answer(msg_e, h0, s0_, "http://localhost:1/v1", "fake", "",
                                             write_prose=False, tz_known=True)
    check(cf2 is not None and (sf2.get("result").provenance.get("session") or {}).get("ablation") == {"removed": []},
          "with it back the run happens and the provenance records that nothing was removed")
    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
