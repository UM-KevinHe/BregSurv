"""End-to-end test for the V3 pipeline: profile -> declare -> verify -> gate ->
derive the candidate set -> fit all of it -> select -> report -> four artifacts.

The language model is not involved. Paths 1 and 3 of the declaration protocol are
model-free by design, the candidate set is derived from two facts, and the report
renders from the fitted objects. The model's only optional job is connective
prose, and the last block here checks that a badly behaved model cannot get a
number into it.

Run:  python test_pipeline_e2e.py
"""
from __future__ import annotations

import json
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
from bregsurv_agent import pipeline, report_v3  # noqa: E402
from bregsurv_agent.declaration import Declaration, parse_reply, render_question  # noqa: E402

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
passed = failed = 0

FIXTURE_R = r"""
args <- commandArgs(trailingOnly = TRUE)
set.seed(11)
n <- 260; p <- 8
z <- matrix(rnorm(n * p), n, p)
colnames(z) <- c("age", "bmi", "egfr", "hgb", "albumin", "dialysis_yrs",
                 "donor_age", "cold_ischemia")
lp <- z %*% c(0.6, -0.35, -0.4, 0.15, -0.2, 0.25, 0.3, 0.1)
tt <- rexp(n, exp(lp) * 0.08); cc <- rexp(n, 0.05)
D <- as.data.frame(z)
D$followup_days <- round(pmin(tt, cc) * 100) + 1
D$died <- as.numeric(tt <= cc)
D$patient_id <- sprintf("P%04d", seq_len(n))
D$site <- 1
# the external model covers five of the eight, and names one we do not have
beta_ext <- c(age = 0.55, bmi = -0.30, egfr = -0.45, donor_age = 0.28,
              cold_ischemia = 0.12, hla_mismatch = 0.2)
save(D, beta_ext, file = args[1])
cat("fixture:", n, "subjects,", sum(D$died), "events,", ncol(D), "columns\n")
"""


def check(ok, label, note=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}PASS{OFF}  {label}   {DIM}{note}{OFF}")
    else:
        failed += 1
        print(f"  {RED}FAIL{OFF}  {label}   {note}")


def build_fixture(td: Path) -> str:
    src = td / "mk.R"
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


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        rda = build_fixture(tdp)

        # ---- intake, entirely deterministic ---------------------------------
        print("\n" + "=" * 78)
        print("1. intake: facts, a numbered question, a parsed answer")
        print("=" * 78)
        prof = _run_r("profile_columns.R", {
            "data_path": rda, "data_expr": "D", "external_beta_expr": "beta_ext"})
        check(prof.get("status") == "ok", "the data is profiled",
              f"{prof.get('n_rows')} rows, {prof.get('n_columns')} columns")
        q = render_question(prof)
        check("FOLLOW-UP TIME" in q and "EVENT INDICATOR" in q and "COVARIATES" in q,
              "one batched question is rendered", f"{len(q.splitlines())} lines")
        check(prof["external"]["n_matched"] == 5
              and prof["external"]["unmatched"] == ["hla_mismatch"],
              "external coverage is reported as a fact",
              f"5 matched, unmatched={prof['external']['unmatched']}")

        times = prof["eligible"]["time"]
        events = prof["eligible"]["event"]
        decl = parse_reply(prof, {
            "time": str(times.index("followup_days") + 1),
            "event": str(events.index("died") + 1),
            "event_value": "1", "covariates": "B", "time_zero": "yes"})
        check(decl.time_col == "followup_days" and decl.event_col == "died",
              "the reply resolves with no model involved",
              f"{decl.time_col} / {decl.event_col} / {len(decl.covariates)} covariates")

        # ---- the run --------------------------------------------------------
        print("\n" + "=" * 78)
        print("2. the run: verify, gate, derive, fit every candidate, select")
        print("=" * 78)
        res = pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                           external_beta_expr="beta_ext", profile=prof,
                           nlambda=12, run_r=_run_r)
        c = res.candidates
        check(c["facts"]["design"] == "full cohort"
              and c["facts"]["external_form"] == "coefficients alone",
              "both facts are read off the data, not asked",
              f"{c['facts']['design']} | {c['facts']['external_form']}")
        check(len(c["candidates"]) == 10, "ten candidates were derived and fitted",
              ", ".join(x["key"] for x in c["candidates"]))
        ok = [x for x in c["candidates"] if x["status"] == "ok"]
        check(len(ok) == 10, "every candidate fitted",
              f"{len(ok)}/10 in {res.seconds}s")

        keys = {x["key"] for x in c["candidates"]}
        check({"internal", "external"} <= keys,
              "the set contains BOTH ways of not borrowing",
              "internal-only and external-only are both present")

        folds = c["partition"]["folds"]
        check(folds and len(folds) == c["facts"]["n"],
              "one partition is recorded for the whole comparison",
              f"{len(folds or [])} subjects, {c['partition']['nfolds']} folds")

        losses = [x["loss"] for x in ok]
        check(c["selected"]["loss"] == min(losses),
              "selection is a plain argmin of the cross-validated loss",
              f"{c['selected']['label']} at {c['selected']['loss']:.5f}")

        # ---- the report -----------------------------------------------------
        print("\n" + "=" * 78)
        print("3. the report: six sections, rendered from the fit")
        print("=" * 78)
        for i, title in enumerate(
                ["The data", "How the external model lines up",
                 "What was tried", "How they compared", "The recommended model",
                 "What this analysis does not establish"], start=1):
            check(f"## {i}. {title}" in res.report, f"section {i}: {title}")
        check("hla_mismatch" in res.report,
              "the dropped external predictor is disclosed, not silently omitted")
        for banned, why in [("IBS", "no held-out set exists"),
                            ("confidence interval", "cannot represent the borrowing"),
                            ("difference from the best", "an inference not asked for")]:
            check(banned.lower() not in res.report.lower(),
                  f"the report does not contain '{banned}'", why)

        # ---- the four artifacts ---------------------------------------------
        print("\n" + "=" * 78)
        print("4. the four artifacts")
        print("=" * 78)
        paths = res.save(str(tdp / "out"))
        for k in ("report", "trace", "repro", "candidates"):
            p = Path(paths[k])
            check(p.exists() and p.stat().st_size > 0, f"{k} written",
                  f"{p.name}, {p.stat().st_size} bytes")
        tr = json.loads(Path(paths["trace"]).read_text(encoding="utf-8"))
        check(tr["provenance"].get("bregsurv_version") and tr["provenance"].get("r_version"),
              "provenance records what produced the numbers",
              f"BregSurv {tr['provenance'].get('bregsurv_version')}, "
              f"{tr['provenance'].get('r_version','')[:24]}")
        check(tr["provenance"]["data"]["sha256"],
              "the data is fingerprinted",
              tr["provenance"]["data"]["sha256"][:16] + "...")
        check(len(res.config_sha256) == 64, "the configuration is hashed",
              res.config_sha256[:16] + "...")

        # ---- repro.R actually reproduces ------------------------------------
        print("\n" + "=" * 78)
        print("5. repro.R replays the analysis without the language model")
        print("=" * 78)
        env = {"BREGSURV_R_SCRIPTS": str(REPO / "mcp" / "r_scripts")}
        import os
        e = dict(os.environ, **env)
        r = subprocess.run([_find_rscript(), "--no-save", "--no-restore",
                            "--no-init-file", paths["repro"], rda],
                           capture_output=True, text=True, env=e,
                           stdin=subprocess.DEVNULL, timeout=1800)
        out = (r.stdout or "") + (r.stderr or "")
        check("fold assignment REPRODUCED" in out,
              "the recorded fold assignment is reproduced, not assumed",
              [l for l in out.splitlines() if "REPRODUCED" in l][:1])
        check(f"selected: {c['selected']['label']}" in out,
              "the replay selects the same model",
              c["selected"]["label"])

        # ---- C3: the approval is bound to the configuration -----------------
        print("\n" + "=" * 78)
        print("6. the approved configuration is what runs")
        print("=" * 78)
        try:
            pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                         external_beta_expr="beta_ext", profile=prof, nlambda=12,
                         run_r=_run_r, approved_config_sha256="0" * 64)
            check(False, "a changed configuration aborts", "it ran anyway")
        except pipeline.PipelineRefusal as ex:
            check(any(x["code"] == "config_changed" for x in ex.refusals),
                  "a configuration that does not match the approval aborts",
                  str(ex)[:60])

        # ---- boundary 2 cannot leak a number --------------------------------
        print("\n" + "=" * 78)
        print("7. the model writes no digits, even when it tries")
        print("=" * 78)

        def bad_model(ctx):
            return {
                "data": "This cohort has [n] subjects and [n_events] events.",
                "comparison": "The loss was 1.234 for the winner.",      # digits
                "selected": "It reached a c-index of [cindex].",          # unknown
            }

        res2 = pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                            external_beta_expr="beta_ext", profile=prof,
                            nlambda=12, run_r=_run_r, write_prose=bad_model)
        check("data" in res2.prose, "prose using named references is kept")
        check("comparison" not in res2.prose,
              "prose containing a bare number is dropped",
              "the harness renders every number")
        check("selected" not in res2.prose,
              "prose naming a quantity that does not exist is dropped",
              "'cindex' is not in the closed reference set")
        check(str(res2.candidates["facts"]["n"]) in res2.report,
              "the reference was resolved from the fit",
              f"[n] -> {res2.candidates['facts']['n']}")

        # ---- boundary 2 cannot lose the result ------------------------------
        def broken_model(ctx):
            raise ValueError("report_prose: the model's output was not valid JSON "
                             "(finish_reason=length)")

        res3 = pipeline.run(data_path=rda, data_expr="D", declaration=decl,
                            external_beta_expr="beta_ext", profile=prof,
                            nlambda=12, run_r=_run_r, write_prose=broken_model)
        check(res3.candidates["selected"]["key"] == res2.candidates["selected"]["key"],
              "a prose writer that raises does not lose the fit",
              "same selection as with a working writer")
        check(not [k for k in res3.prose if not k.startswith("_")],
              "and the report carries no prose")
        check("finish_reason=length" in str(res3.provenance.get("model", {}).get("prose_dropped")),
              "the provenance says the draft was dropped, and why")

    print("\n" + "=" * 78)
    print(f"RESULT: {passed}/{passed + failed} passed")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
