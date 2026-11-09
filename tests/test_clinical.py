#!/usr/bin/env python3
"""The clinical summary (clinical.py + clinical_summary.R).

Peripheral to the analysis, so this checks that it is correct and cannot break a run, not the
agent's behaviour: a full Cox run saved with the section in place; the R script on a stratified Cox
and on the grouped-time row; the cases where it does not apply; a failing R call leaving the report
untouched; and the arithmetic the section shows (groups partition the cohort, the reclassification
table counts every subject, predicted survival falls with time and rises from high to low risk).
No language model anywhere.
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent.rbridge import _run_r  # noqa: E402
from bregsurv_agent import pipeline, clinical  # noqa: E402
from bregsurv_agent.declaration import parse_reply  # noqa: E402
from test_pipeline_e2e import build_fixture  # noqa: E402

failed = 0


def check(ok, label, note=""):
    global failed
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))
    if not ok:
        failed += 1


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        rda = build_fixture(tdp)
        prof = _run_r("profile_columns.R", {"data_path": rda, "data_expr": "D",
                                            "external_beta_expr": "beta_ext"})
        times, events = prof["eligible"]["time"], prof["eligible"]["event"]
        decl = parse_reply(prof, {"time": str(times.index("followup_days") + 1),
                                  "event": str(events.index("died") + 1),
                                  "event_value": "1", "covariates": "B", "time_zero": "yes"})

        print("A. a full Cox run, saved")
        res = pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                           external_beta_expr="beta_ext", profile=prof, nlambda=12, run_r=_run_r)
        out = tdp / "run"
        paths = res.save(str(out))
        check(all(k in paths for k in ("clinical_csv", "clinical_pdf", "clinical_png")),
              "the three clinical files are among the artifacts", ", ".join(sorted(paths)))
        check(all(Path(paths[k]).is_file() for k in ("clinical_csv", "clinical_pdf", "clinical_png")
                  if k in paths), "and they exist on disk")
        rep = (out / "report.md").read_text(encoding="utf-8")
        a, s6 = rep.find(clinical.START), rep.find("\n## 6.")
        check(a > 0 and rep.find("## 5.") < a < s6, "the section sits at the end of section 5")
        check(rep.count(clinical.START) == 1 and "### For clinical use" in rep, "it appears once")
        check("![Observed survival by predicted risk group](clinical_groups.png)" in rep,
              "the figure is linked by its file name")
        check("optimistic" in rep, "the section says it is computed on the fitted data")
        print("    " + "\n    ".join(rep[a:rep.find(clinical.END)].splitlines()[:40]))

        # the numbers, from the R result itself
        r = _run_r("clinical_summary.R", clinical.payload(res, tdp / "again"))
        check(r.get("status") == "ok", "the R script returns ok", r.get("reason", ""))
        n = r["n"]
        g = r["groups"]
        check(sum(x["n"] for x in g) == n and len(g) == 3, "three groups partition the cohort",
              f"{[x['n'] for x in g]} of {n}")
        check(sum(x["n_events"] for x in g) == r["n_events"], "and their events add up")
        mid_i = r["horizons"].index(r["middle_horizon"])
        pred_mid = [x["predicted"][mid_i] for x in g]
        check(pred_mid[0] > pred_mid[1] > pred_mid[2], "predicted survival falls from low to high risk",
              str([round(p, 3) for p in pred_mid]))
        check(all(x["predicted"][i] >= x["predicted"][i + 1] - 1e-12 for x in g
                  for i in range(len(r["horizons"]) - 1)), "and falls with time within each group")
        rc = r.get("reclassification")
        check(rc is not None and sum(sum(row) for row in rc["counts"]) == n,
              "the reclassification table counts every subject",
              "" if rc is None else f"{rc['n_moved_up']} up, {rc['n_moved_down']} down")
        with open(r["csv"], newline="") as fh:
            rows = list(csv.DictReader(fh))
        check(len(rows) == n and "risk_group" in rows[0]
              and sum(1 for k in rows[0] if k.startswith("survival_at_")) == len(r["horizons"]),
              "the CSV has one row per subject and one column per horizon", f"{len(rows)} rows")
        check(all(0.0 <= float(x[k]) <= 1.0 for x in rows for k in x if k.startswith("survival_at_")),
              "every predicted probability lies in [0, 1]")
        hr = {h["variable"]: h for h in r["hazard_ratios"]}
        b = res.candidates["selected"]["beta"]
        v = next(iter(b))
        check(abs(hr[v]["hr"] - __import__("math").exp(b[v])) < 1e-9 or hr[v]["flagged"],
              "a hazard ratio is exp of its coefficient", v)

        print("B. a stratified Cox model")
        p = clinical.payload(res, tdp / "strat")
        # the fixture's `site` is constant; two strata made in the data expression instead
        p["data_expr"] = "transform(D, grp = ifelse(age > 0, 'a', 'b'))"
        p["stratum_col"] = "grp"
        r2 = _run_r("clinical_summary.R", p)
        check(r2.get("status") == "ok", "a stratum column is accepted", r2.get("reason", ""))
        if r2.get("status") == "ok":
            sm = r2["calculator"]["survival_at_means"]
            check(len(sm) > 1 and all(s["stratum"] is not None for s in sm),
                  "the risk calculator gives one baseline per stratum", f"{len(sm)} strata")
            check(sum(x["n"] for x in r2["groups"]) == r2["n"], "the groups still partition the cohort")

        print("C. the grouped-time row")
        p = clinical.payload(res, tdp / "disc")
        p["row"] = "discrete"
        p["edges"] = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 4000]
        p["gamma"] = [-3.0] * 11
        r3 = _run_r("clinical_summary.R", p)
        check(r3.get("status") == "ok", "an interval baseline is accepted", r3.get("reason", ""))
        if r3.get("status") == "ok":
            check(all(h in p["edges"] for h in r3["horizons"]), "horizons fall on interval ends",
                  str(r3["horizons"]))
            check(r3.get("reclassification") is None, "no reclassification on this row")

        print("D. where it does not apply")
        ncc = SimpleNamespace(declaration=SimpleNamespace(time_col=None, event_col="case"),
                              candidates={"selected": {"key": "internal", "beta": {"x": 1.0}}})
        check(clinical.not_applicable(ncc) is not None, "a matched sample", clinical.not_applicable(ncc))
        nn = SimpleNamespace(declaration=decl, candidates={"selected": {"key": "diskd", "beta": {}}})
        check(clinical.not_applicable(nn) is not None, "a network winner", clinical.not_applicable(nn))
        check(clinical.attach(nn, tdp / "nn", _run_r) == {}, "attach writes nothing for it")

        print("E. a failing R call leaves the report alone")
        out2 = tdp / "run2"
        out2.mkdir()
        (out2 / "report.md").write_text(res.report, encoding="utf-8")
        got = clinical.attach(res, out2, lambda *a, **k: {"status": "error", "reason": "boom"})
        check(got == {} and (out2 / "report.md").read_text(encoding="utf-8") == res.report,
              "no paths, report unchanged")

        def boom(*a, **k):
            raise RuntimeError("Rscript died")
        orig = pipeline._default_run_r
        pipeline._default_run_r = lambda: boom
        try:
            p3 = res.save(str(tdp / "run3"))
            check("report" in p3 and "clinical_csv" not in p3, "save() still writes the four artifacts")
        finally:
            pipeline._default_run_r = orig

        print("F. rendering and placement")
        once = clinical.insert(res.report, "X")
        twice = clinical.insert(clinical.insert(res.report, clinical.START + "a" + clinical.END),
                                clinical.START + "b" + clinical.END)
        check(once.find("X") < once.find("\n## 6."), "inserted before section 6")
        check(twice.count(clinical.START) == 1 and "b" + clinical.END in twice,
              "a second insert replaces the first")
        bare = dict(r)
        bare["reclassification"] = None
        md = clinical.render(bare, {k: float(v) for k, v in b.items()})
        check("Against the external model" not in md and md.startswith(clinical.START),
              "renders without a reclassification")

    print(f"\n{'ALL PASSED' if not failed else f'{failed} FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
