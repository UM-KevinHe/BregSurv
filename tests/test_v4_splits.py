#!/usr/bin/env python3
"""V4: evaluation by repeated random train/test splits, on request.

A. the harness half, no R: the request reader's checks (a number the analyst did not write
   is dropped), the decline rules, M1's new kind, the act, the policy.
B. the app with a FAKE model on the demo cohort and release (needs R and gradio): one message
   declares the analysis and asks for 3 random 70/30 splits with box plots; the analysis runs
   first, then the splits. The splits redraw identically from the seed; split 1's numbers equal
   a direct pipeline.run on that split's files to 1e-9; the table agrees with the per-split
   record; the figures exist; replay_splits.R reproduces.
C. the analyst's own test file: the training rows are resampled (the share the analyst wrote)
   and every replicate is scored on the analyst's file; a number of splits the model returns
   that the message does not contain is dropped.

    python mcp/test_v4_splits.py
"""
from __future__ import annotations

import csv
import dataclasses
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("BREGSURV_PLANNER", "off")
os.environ.setdefault("BREGSURV_MEMORY", "off")

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


MSG = ("Follow-up time is in followup_days, and died is 1 if the patient died. Adjust for age, "
       "bmi and egfr. Then evaluate the methods on 3 random 70/30 splits and show box plots of "
       "the C-index and the Brier score for each method.")


def raw_req(**kw):
    out = {"reasoning": "q", "n_splits": None, "n_splits_evidence": None,
           "n_splits_if_unstated": None, "test_fraction": None, "test_fraction_evidence": None,
           "subsample_fraction": None, "subsample_fraction_evidence": None,
           "measures": [], "figure": False}
    out.update(kw)
    return out


def part_a():
    from bregsurv_agent import splits, intent, actions, policy
    from bregsurv_agent.declaration import Declaration
    from bregsurv_agent.state import Session

    hdr("A. reading the request: what the analyst wrote, and nothing else")
    r = splits.validate(MSG, raw_req(n_splits=3, n_splits_evidence="3 random 70/30 splits",
                                      test_fraction=0.3, test_fraction_evidence="70/30",
                                      measures=["cindex", "ibs"], figure=True), "split")
    check(r.n_splits == 3 and r.n_splits_source.startswith("stated") and not r.n_splits_chosen,
          "a stated number of splits is kept, with its words", r.n_splits_source)
    check(abs(r.fraction - 0.3) < 1e-12 and r.fraction_source.startswith("stated"),
          "70/30 is a test share of three tenths", r.fraction_source)
    check(r.measures == ["cindex", "ibs"] and r.figure and not r.dropped,
          "the two measures named and the box plots are kept", str(r.as_dict()))

    r = splits.validate(MSG, raw_req(n_splits=500, n_splits_evidence="3 random 70/30 splits"),
                        "split")
    check(r.n_splits == splits.DEFAULT_SPLITS and any(d["field"] == "n_splits" for d in r.dropped),
          "a number of splits not inside its evidence span is dropped", str(r.dropped))
    r = splits.validate(MSG, raw_req(n_splits=3, n_splits_evidence="three hundred splits"),
                        "split")
    check(any(d["field"] == "n_splits" and "not in the message" in d["why"] for d in r.dropped),
          "an evidence span that is not in the message drops the number", str(r.dropped))
    r = splits.validate(MSG, raw_req(test_fraction=0.7, test_fraction_evidence="70/30"), "split")
    check(abs(r.fraction - splits.DEFAULT_TEST_FRACTION) < 1e-12
          and any(d["field"] == "test_fraction" for d in r.dropped),
          "70/30 read as a test share of seven tenths is dropped (the pair decides)")
    r = splits.validate(MSG, raw_req(measures=["cindex", "tdauc"], figure=True), "split")
    check(r.measures == ["cindex"] and any(d["value"] == "tdauc" for d in r.dropped),
          "a measure the message does not name is dropped", f"{r.measures} {r.dropped}")
    r = splits.validate("Evaluate the methods on 20 random splits.",
                        raw_req(n_splits=20, n_splits_evidence="20 random splits", figure=True),
                        "split")
    check(r.figure is False and any(d["field"] == "figure" for d in r.dropped)
          and r.measures == list(splits.MEASURES),
          "no figure word, no figure; no measure named, all four")
    m2 = "How stable is this? Evaluate it on repeated random splits."
    r = splits.validate(m2, raw_req(n_splits_if_unstated=40), "split")
    check(r.n_splits == 40 and r.n_splits_chosen and r.n_splits_source.startswith("chosen"),
          "no number stated: the model's choice is used and recorded as chosen",
          r.n_splits_source)
    r = splits.validate(m2, raw_req(n_splits_if_unstated=5000), "split")
    check(r.n_splits == splits.DEFAULT_SPLITS and not r.n_splits_chosen
          and r.n_splits_source.startswith("default"),
          "a choice above the cap is dropped and the default used")
    r = splits.validate("Evaluate on 5,000 splits.", raw_req(n_splits=5000,
                                                              n_splits_evidence="5,000 splits"),
                        "split")
    check(r.n_splits == splits.MAX_SPLITS and "more than" in r.n_splits_source,
          "a stated number above the cap is capped, and said so", r.n_splits_source)
    m3 = "Resample the training data 50 times, keeping 80% of the training rows each time."
    r = splits.validate(m3, raw_req(n_splits=50, n_splits_evidence="50 times",
                                     subsample_fraction=0.8,
                                     subsample_fraction_evidence="keeping 80% of the training rows"),
                        "subsample")
    check(r.mode == "subsample" and r.n_splits == 50 and abs(r.fraction - 0.8) < 1e-12,
          "the analyst's test file: the share of training rows kept, as written")
    r = splits.validate(m3, raw_req(n_splits=50, n_splits_evidence="50 times"), "subsample")
    check(abs(r.fraction - splits.DEFAULT_KEEP_FRACTION) < 1e-12
          and r.fraction_source.startswith("default"),
          "no share stated: seven tenths of the training rows, disclosed as the default")

    hdr("A2. what is declined, and how the act is planned")
    d = Declaration(time_col="t", event_col="d", event_value="1", covariates=["x"], source="reply")
    check(splits.declined_reason(d) is None, "a continuous-time cohort is evaluated")
    check("discrete-time" in (splits.declined_reason(d, {"row": "discrete"}) or ""),
          "the discrete-time row is declined in plain words")
    dm = Declaration(time_col=None, event_col="case", event_value="1", covariates=["x"], source="reply",
                     stratum_col="set")
    check("matched" in (splits.declined_reason(dm) or ""), "a matched design is declined")
    check("evaluate_by_splits" in intent.KINDS and "evaluate_by_splits" in policy.load("intent"),
          "M1 offers the kind and its policy describes it")
    its = intent.validate(MSG, {"intents": [
        {"kind": "evaluate_by_splits", "evidence": "evaluate the methods on 3 random 70/30 splits"},
        {"kind": "declare_roles", "evidence": "Follow-up time is in followup_days"}]},
        result_present=False)
    its = intent.dispatch_order(its)
    check([i.kind for i in its] == ["declare_roles", "evaluate_by_splits"]
          and all(i.evidence_verified for i in its),
          "M1 keeps both intents; the declaration is dispatched first")
    sess = Session(profile={"columns": []})
    acts = actions.plan(sess, its)
    check(acts[-1] is actions.Act.EVALUATE_BY_SPLITS and actions.Act.COMPLETE in acts
          and acts.index(actions.Act.COMPLETE) < acts.index(actions.Act.EVALUATE_BY_SPLITS),
          "the act follows the run the turn makes", str([a.value for a in acts]))
    check(not actions.check(sess, acts) and actions.model_calls_in(acts) <= actions.MODEL_CALLS_PER_TURN,
          "the plan is legal and within the per-turn budget")
    spec = actions.SPECS[actions.Act.EVALUATE_BY_SPLITS]
    check(spec.proposer == "model:split_request" and "split_request" in policy.NAMES,
          "the act is proposed under its own policy, hashed with the others")
    check(list(splits.SCHEMA["properties"])[0] == "reasoning"
          and "`reasoning`" in policy.sections("split_request")["## Before you decide"],
          "reasoning first, its purpose stated in the policy")


# ------------------------------------------------------------------- fake model
class _Msg:
    content = None


class _Choice:
    finish_reason = "stop"

    def __init__(self):
        self.message = _Msg()


class _Usage:
    prompt_tokens = 300
    completion_tokens = 60


class _Comp:
    def __init__(self):
        self.choices = [_Choice()]
        self.usage = _Usage()


def make_fake(intents, roles, request):
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
                            dict({"external_form": None, "external_name": None,
                                  "out_of_scope_reason": None}, **i) for i in intents]}
                    elif name == "role_extraction":
                        out = dict({"reasoning": "q", "stratum_column": None}, **roles)
                    elif name == "split_request":
                        out = request
                    else:
                        out = {"reasoning": "q"}
                    c = _Comp()
                    c.choices[0].message.content = json.dumps(out)
                    return c
    return _Fake()


def _rows_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def part_b():
    hdr("B. one message: declare, run, then 3 random 70/30 splits with box plots")
    try:
        import app
        from bregsurv_agent.rbridge import _find_rscript, _run_r
        have = _find_rscript() is not None
    except Exception as exc:  # pragma: no cover
        print(f"  SKIP  app import failed ({type(exc).__name__}: {exc})")
        return None
    if not have:
        print("  SKIP  needs Rscript")
        return None
    from bregsurv_agent import pipeline, splits

    roles = {"time_column": "followup_days", "time_evidence": "Follow-up time is in followup_days",
             "event_column": "died", "event_evidence": "died is 1 if the patient died",
             "event_value": "1", "event_value_evidence": "died is 1",
             "covariate_columns": ["age", "bmi", "egfr"]}
    app._client = lambda endpoint, api_key: make_fake(
        [{"kind": "declare_roles", "evidence": "Follow-up time is in followup_days"},
         {"kind": "evaluate_by_splits", "evidence": "evaluate the methods on 3 random 70/30 splits"}],
        roles,
        raw_req(n_splits=3, n_splits_evidence="3 random 70/30 splits", test_fraction=0.3,
                test_fraction_evidence="70/30", measures=["cindex", "ibs"], figure=True))
    h0, s0, *_ = app.start_session()
    out = app.submit_answer(MSG, h0, s0, "http://localhost:1/v1", "fake", "",
                            write_prose=False, tz_known=True)
    check(len(out) == 11, "submit_answer still returns eleven values", str(len(out)))
    h, _, s, cand, *rest = out
    files = rest[-1]
    text = "\n".join(t for _, t in h if t)
    check(s.result is not None and len(s.results) == 1 and cand is not None,
          "the analysis ran first", text[-300:].replace("\n", " | "))
    ev = [a for a in s.actions if a.get("route") == "evaluate_by_splits"]
    check(ev and ev[-1].get("ran") and ev[-1].get("n_splits") == 3,
          "the evaluation is in the typed action log", json.dumps(ev[-1] if ev else {})[:300])
    check(any(c.get("name") == "split_request" for c in s.model_calls),
          "the request reading is a recorded model call")
    check("Evaluation by repeated splits" in text and "± " in text
          and "no model wrote any of them" in text,
          "the reply carries the harness-rendered table", text[-400:].replace("\n", " | "))
    if not files:
        check(False, "the split files are in the last output slot")
        return None
    byname = {Path(f).name: f for f in files}
    check(set(byname) >= {"splits_table.md", "splits_table.csv", "splits_boxplot.pdf",
                          "splits_boxplot.png", "splits.json", "replay_splits.R"},
          "table (CSV, Markdown), box plots (PDF, PNG), record and replay are delivered",
          str(sorted(byname)))
    check(all(Path(f).stat().st_size > 0 for f in files), "no delivered file is empty")
    check("Evaluation by repeated splits" not in s.result.report,
          "the report itself is untouched")
    rec = json.loads(Path(byname["splits.json"]).read_text())
    check(rec["n_splits"] == 3 and rec["mode"] == "split" and rec["rng_kind"].startswith("Mersenne")
          and len(rec["splits"]) == 3 and all(x["status"] == "ok" for x in rec["splits"]),
          "the record: three splits, Mersenne-Twister, every split analysed")
    n = rec["n"]
    t0 = rec["splits"][0]
    check(len(t0["rows"]) == round(0.3 * rec["n_events"]) + round(0.3 * (n - rec["n_events"])),
          "each test part is event-stratified: three tenths of the events and of the non-events",
          f"{len(t0['rows'])} of {n}")

    # ---- the splits redraw identically from the seed
    with tempfile.TemporaryDirectory() as td:
        draw = dict(rec["draw"], data_path=s.result.data_path, data_expr=s.result.data_expr,
                    outdir=str(Path(td) / "s"))
        d2 = _run_r("draw_splits.R", draw)
        check(d2.get("status") == "ok"
              and [sp["rows"] for sp in d2["splits"]] == [x["rows"] for x in rec["splits"]],
              "the splits are identical when redrawn from the seed")
        draw_b = dict(draw, seed=rec["seed"] + 1, outdir=str(Path(td) / "t"))
        d3 = _run_r("draw_splits.R", draw_b)
        check([sp["rows"] for sp in d3["splits"]] != [x["rows"] for x in rec["splits"]],
              "another seed draws other splits (the check can fail)")

    # ---- split 1 against a direct pipeline call on that split's files
    sp1 = Path(byname["splits.json"]).parent / "splits" / "split_0001"
    res = s.result
    ext_kw = {k: v for k, v in (("external_beta_inline", res.external_beta_inline),
                                ("external_Q_inline", res.external_Q_inline)) if v}
    direct = pipeline.run(str(sp1 / "train.csv"), "train",
                          dataclasses.replace(res.declaration, test_data_path=str(sp1 / "test.csv"),
                                              test_data_expr="test"),
                          run_r=_run_r, **ext_kw)
    worst = 0.0
    same_status = True
    for c in direct.candidates["candidates"]:
        m = t0["members"].get(c["key"])
        if m is None or m["status"] != c["status"]:
            same_status = False
            continue
        if c["status"] != "ok":
            continue
        worst = max(worst, abs(m["cv_loss"] - float(c["loss"])))
        for k in splits.MEASURES:
            a, b = m["holdout"].get(k), (c.get("holdout") or {}).get(k)
            if a is None or b is None:
                same_status = same_status and (a is None and b is None)
            else:
                worst = max(worst, abs(a - float(b)))
    check(same_status and worst <= 1e-9
          and direct.candidates["selected"]["key"] == t0["selected"],
          "split 1 equals a direct pipeline.run on its files, every member, to 1e-9",
          f"worst {worst:.2e}, selected {direct.candidates['selected']['key']} vs {t0['selected']}")

    # ---- the table against the per-split record
    tab = {r["key"]: r for r in _rows_csv(byname["splits_table.csv"])}
    ok = True
    for key, row in tab.items():
        for m in ("cindex", "ibs"):
            if key == splits.SELECTED_KEY:
                vals = [x["selected_holdout"][m] for x in rec["splits"]
                        if x["selected_holdout"][m] is not None]
            else:
                vals = [x["members"][key]["holdout"][m] for x in rec["splits"]
                        if x["members"].get(key, {}).get("status") == "ok"
                        and x["members"][key]["holdout"][m] is not None]
            if vals and abs(float(row[f"{m}_mean"]) - statistics.fmean(vals)) > 1e-12:
                ok = False
            if len(vals) > 1 and abs(float(row[f"{m}_sd"]) - statistics.stdev(vals)) > 1e-12:
                ok = False
    nsel = sum(int(r["n_selected"]) for k, r in tab.items() if k != splits.SELECTED_KEY)
    check(ok and nsel == 3 and splits.SELECTED_KEY in tab
          and set(rec["measures"]) == {"cindex", "ibs"},
          "table means, sds and selection counts agree with the per-split record",
          f"n_selected total {nsel}")

    # ---- the replay script
    env = dict(os.environ, BREGSURV_R_SCRIPTS=str(REPO / "mcp" / "r_scripts"))
    rp = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                         byname["replay_splits.R"], s.result.data_path, byname["splits.json"]],
                        capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env,
                        timeout=3600)
    check(rp.returncode == 0 and "split membership REPRODUCED" in rp.stdout
          and "evaluation by splits REPRODUCED" in rp.stdout,
          "replay_splits.R redraws the splits and reproduces every number",
          (rp.stdout + rp.stderr)[-500:].replace("\n", " | "))
    # and it fails when a recorded number is changed
    bad = json.loads(Path(byname["splits.json"]).read_text())
    k0 = next(k for k, m in bad["splits"][0]["members"].items() if m["status"] == "ok")
    bad["splits"][0]["members"][k0]["holdout"]["cindex"] += 0.01
    with tempfile.TemporaryDirectory() as td:
        bp = Path(td) / "splits.json"
        bp.write_text(json.dumps(bad))
        rb = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "--no-init-file",
                             byname["replay_splits.R"], s.result.data_path, str(bp), "1"],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env,
                            timeout=1800)
    check(rb.returncode != 0 and "differ" in (rb.stdout + rb.stderr),
          "a changed recorded number makes the replay stop (the check can fail)")

    # ---- a follow-up on the same session, about the analysis already run
    app._client = lambda endpoint, api_key: make_fake(
        [{"kind": "evaluate_by_splits", "evidence": "evaluate it on 2 splits"}], roles,
        raw_req(n_splits=2, n_splits_evidence="2 splits"))
    out2 = app.submit_answer("Now evaluate it on 2 splits.", h, s, "http://localhost:1/v1",
                             "fake", "", write_prose=False, tz_known=True)
    h2, _, s2, *rest2 = out2
    check(len(s2.results) == 1 and rest2[-1]
          and json.loads(Path([f for f in rest2[-1] if f.endswith("splits.json")][0]
                              ).read_text())["n_splits"] == 2,
          "after a run, a request alone evaluates the analysis already run (no refit of it)")
    app._purge(s2)
    return True


def part_c():
    hdr("C. the analyst's test file: resample the training rows, score on the file")
    try:
        import app
        import pandas as pd
        from bregsurv_agent.rbridge import _run_r
    except Exception as exc:  # pragma: no cover
        print(f"  SKIP  ({type(exc).__name__}: {exc})")
        return
    from bregsurv_agent import pipeline, splits
    td = Path(tempfile.mkdtemp(prefix="v4_splits_"))
    df = pd.read_csv(app.DEMO_COHORT)
    p_tr, p_te = str(td / "cohort_train.csv"), str(td / "cohort_test.csv")
    df.iloc[:60].to_csv(p_tr, index=False)
    df.iloc[60:].to_csv(p_te, index=False)
    msg = ("Follow-up time is in followup_days, and died is 1 if the patient died. Adjust for "
           "age, bmi and egfr. Then resample the training data, keeping 80% of the training rows "
           "each time, and report the C-index.")
    roles = {"time_column": "followup_days", "time_evidence": "Follow-up time is in followup_days",
             "event_column": "died", "event_evidence": "died is 1 if the patient died",
             "event_value": "1", "event_value_evidence": "died is 1",
             "covariate_columns": ["age", "bmi", "egfr"]}
    app._client = lambda endpoint, api_key: make_fake(
        [{"kind": "declare_roles", "evidence": "Follow-up time is in followup_days"},
         {"kind": "evaluate_by_splits", "evidence": "resample the training data"}],
        roles,
        # 12 is in no part of the message: dropped, the default (patched to 2 here) is used
        raw_req(n_splits=12, n_splits_evidence="12 resamples", subsample_fraction=0.8,
                subsample_fraction_evidence="keeping 80% of the training rows",
                measures=["cindex"]))
    saved = splits.DEFAULT_SPLITS
    splits.DEFAULT_SPLITS = 2
    try:
        h0, s0, *_ = app.start_session(p_tr, str(app.DEMO_COEFS), test_uploaded=p_te)
        out = app.submit_answer(msg, h0, s0, "http://localhost:1/v1", "fake", "",
                                write_prose=False, tz_known=True)
    finally:
        splits.DEFAULT_SPLITS = saved
    h, _, s, *rest = out
    files = rest[-1] or []
    text = "\n".join(t for _, t in h if t)
    rp = [f for f in files if f.endswith("splits.json")]
    check(s.result is not None and rp, "the analysis ran and the evaluation was delivered",
          text[-300:].replace("\n", " | "))
    if not rp:
        return
    rec = json.loads(Path(rp[0]).read_text())
    req = rec["request"]
    check(rec["mode"] == "subsample" and rec["n_splits"] == 2
          and any(d["field"] == "n_splits" and d["value"] == 12 for d in req["dropped"])
          and "Set aside" in text,
          "a number of splits the message does not contain is dropped, and the reply says so",
          json.dumps(req["dropped"]))
    check(abs(rec["fraction"] - 0.8) < 1e-12 and rec["measures"] == ["cindex"],
          "the share of training rows kept is the one the analyst wrote")
    n_ev = rec["n_events"]
    want = round(0.8 * n_ev) + round(0.8 * (rec["n"] - n_ev))
    sdir = Path(rp[0]).parent / "splits"
    check(rec["n"] == 60 and all(len(x["rows"]) == want and max(x["rows"]) <= 60
                                  for x in rec["splits"])
          and not any((sdir / f"split_{k:04d}" / "test.csv").exists() for k in (1, 2)),
          "each replicate keeps rows of the training data only; no test part is cut",
          f"{[len(x['rows']) for x in rec['splits']]} vs {want}")
    check(all(x.get("n_test") == len(df) - 60 for x in rec["splits"]),
          "every replicate is scored on the analyst's test file")
    sp1 = sdir / "split_0001"
    res = s.result
    direct = pipeline.run(str(sp1 / "train.csv"), "train", res.declaration, run_r=_run_r,
                          external_beta_inline=res.external_beta_inline)
    worst = 0.0
    for c in direct.candidates["candidates"]:
        m = rec["splits"][0]["members"].get(c["key"])
        if c["status"] == "ok" and m and m["status"] == "ok":
            for k in splits.MEASURES:
                a, b = m["holdout"].get(k), (c.get("holdout") or {}).get(k)
                if a is not None and b is not None:
                    worst = max(worst, abs(a - float(b)))
    check(worst <= 1e-9, "replicate 1 equals a direct pipeline.run on it, scored on the file",
          f"worst {worst:.2e}")
    app._purge(s)


def main() -> int:
    part_a()
    if part_b():
        part_c()
    hdr(f"RESULT: {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
