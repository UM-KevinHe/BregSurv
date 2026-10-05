"""What the prose writer and the explanation call are told. Until then the model saw
reference NAMES only and wrote stock sentences: "not all variables were covered" on a fully covered
release, the selected member misnamed, a count used for the wrong quantity (report rubric of
2026-09-15; rubric smoke of 2026-10-01). It is now given what each reference is and the facts of the
run in words. No R and no model: a fake client records the prompt.

Run: python mcp/test_prose_facts.py
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
    passed += bool(ok); failed += not ok
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))


def _res(design="full cohort", form="coefficients alone", internal_only=0, dropped=(), test=False):
    cands = [{"key": "internal", "label": "Internal only", "status": "ok", "loss": 7.2},
             {"key": "mahalanobis_lasso", "label": "Mahalanobis, lasso", "status": "ok", "loss": 7.0,
              "eta": 3.0, "lambda": 0.01, "n_nonzero": 7},
             {"key": "external", "label": "External model, unchanged", "status": "ok", "loss": 7.1}]
    sel = dict(cands[1])
    if test:
        sel["holdout"] = {"cindex": 0.71, "loss": 5.7, "ibs": 0.1, "tdauc": 0.7}
    res = {"facts": {"design": design, "external_form": form, "n": 600, "n_events": 120, "p": 10,
                     "p_covered": 10 - internal_only, "p_internal_only": internal_only},
           "candidates": cands, "selected": sel, "criteria": "V&VH",
           "partition": {"nfolds": 5, "seed": 20260818},
           "linkage": {"dropped": list(dropped)}}
    if test:
        res["test_data"] = {"n": 300, "n_events": 60}
    return res


class _Fake:
    """An OpenAI-shaped client that records the user message and returns a fixed draft."""
    def __init__(self, reply):
        self.reply, self.user = reply, None
        self.chat = self; self.completions = self

    def create(self, **kw):
        self.user = kw["messages"][-1]["content"]
        msg = type("M", (), {"content": json.dumps(self.reply), "model_extra": {}})()
        ch = type("C", (), {"message": msg, "finish_reason": "stop"})()
        use = type("U", (), {"prompt_tokens": 100, "completion_tokens": 20})()
        return type("R", (), {"choices": [ch], "usage": use, "model": "fake"})()


def main():
    from bregsurv_agent import report_v3 as R, boundary as B
    for name, res in [("cohort, full coverage", _res()),
                      ("cohort, partial coverage", _res(internal_only=3, dropped=["hla"])),
                      ("matched design", _res(design="nested case-control")),
                      ("no external", _res(form="none")),
                      ("test file", _res(test=True))]:
        refs = R.build_references(res)
        facts = R.prose_facts(res, refs)
        gl = R.reference_glossary(refs)
        text = " ".join(facts + gl)
        check(not R.check_no_digits(" ".join(facts)), f"{name}: the facts contain no digit", str(facts))
        check(len(gl) == len(R.prose_references(refs)) and all(g.split("]: ")[1] and "_" not in g.split("]: ")[1] for g in gl),
              f"{name}: every reference offered has a meaning in words")
        names = set(R._REF.findall(" ".join(facts)))
        check(names <= set(refs), f"{name}: the facts name only references that exist", str(names - set(refs)))
        check("Mahalanobis, lasso" in text, f"{name}: the selected method is named")
    f_full = " ".join(R.prose_facts(_res(), R.build_references(_res())))
    f_part = " ".join(R.prose_facts(_res(internal_only=3, dropped=["hla"]),
                                    R.build_references(_res(internal_only=3, dropped=["hla"]))))
    check("covers every predictor" in f_full and "does not cover" not in f_full,
          "a fully covered release is stated as fully covered")
    check("does not cover every predictor" in f_part and "set aside" in f_part,
          "a partial release is stated as partial, with the set-aside terms")
    f_ncc = " ".join(R.prose_facts(_res(design="nested case-control"),
                                   R.build_references(_res(design="nested case-control"))))
    check("cases" in f_ncc and "no censoring" in f_ncc, "a matched design is described as cases and controls")
    f_none = " ".join(R.prose_facts(_res(form="none"), R.build_references(_res(form="none"))))
    check("covers" not in f_none, "no coverage sentence when there is no external information")
    f_test = " ".join(R.prose_facts(_res(test=True), R.build_references(_res(test=True))))
    check("did not use it" in f_test, "a test file is described as unused by the selection")

    rf = R.build_references(_res())
    check("[p_internal_only]" not in " ".join(R.reference_glossary(rf))
          and "[p_dropped]" not in " ".join(R.reference_glossary(rf)) and "p_internal_only" in rf,
          "a zero count is not offered to the prose writer but stays in the closed set")
    rp = R.build_references(_res(internal_only=3, dropped=["hla"]))
    check("[p_internal_only]" in " ".join(R.reference_glossary(rp)),
          "a non-zero count is offered")
    out_pct = R.resolve("an event rate of [event_rate]% and [event_rate] again", rf)
    check("%%" not in out_pct and out_pct.count("%") == 2, "the event rate carries one percent sign", out_pct)

    fake = _Fake({"reasoning": "data and linkage", "data": "There were [n] subjects.",
                  "linkage": "The external model covers every predictor.", "candidates": "x",
                  "comparison": "y", "selected": "z"})
    B.write_prose(fake, "fake")({"references": R.build_references(_res()), "result": _res()})
    check(fake.user and "[n_nonzero]: non-zero coefficients in the selected model" in fake.user and "[p_internal_only]" not in fake.user
          and "Facts of this analysis" in fake.user and "covers every predictor" in fake.user,
          "the prose call carries the glossary and the facts")
    fake2 = _Fake({"reasoning": "r", "answer": "It had the lowest loss, [loss_best]."})
    res_ncc = _res(design="nested case-control")
    del res_ncc["candidates"][2]
    out = B.explain(fake2, "fake", "why that one?", {"references": R.build_references(res_ncc), "result": res_ncc})
    check("Facts of this analysis" in fake2.user and "[loss_external]" not in fake2.user,
          "the explanation call carries the facts and names no reference this run lacks")
    check(out.get("answer") and "lowest loss" in out["answer"], "the explanation still resolves", str(out))
    print(f"\nRESULT: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
