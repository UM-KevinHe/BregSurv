"""V4 work items 2 and 6, Python side: plan.validate, the cost units, and a plan carried through
pipeline.run -- into the approval hash, the payload, the trace and repro.R, which replays it with no model.
Needs R; no model.
  python mcp/test_v4_plan_py.py
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

V4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V4))
from bregsurv_agent.rbridge import _run_r  # noqa: E402
from bregsurv_agent import pipeline, plan as P, external as X  # noqa: E402
from bregsurv_agent.declaration import Declaration  # noqa: E402

FX = Path("/home/ybshao/jobs/synth200/fixtures")
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def codes(problems):
    return {p["code"] for p in problems}


COV = ["age", "bmi", "egfr", "donor_age", "cold_ischemia", "hla_mismatch", "dialysis_years", "diabetes",
       "hypertension", "prior_transplant"]
KW = dict(design="full cohort", external_form="coefficients alone", has_baseline=False, covariates=COV,
          covered=COV)

# ---- A. the checks ---------------------------------------------------------------------------------
ok, pr, c = P.validate({"row": "cox", "members": [{"key": "internal"}, {"key": "external"},
                                                  {"key": "kl_lasso", "etas": [10, 1, 1, 0.5]}]}, **KW)
check("A a valid plan passes, in canonical form (library order, grid sorted and deduped)",
      ok is not None and not pr and [m["key"] for m in ok["members"]] == ["internal", "kl_lasso", "external"]
      and next(m for m in ok["members"] if m["key"] == "kl_lasso")["etas"] == [0.5, 1.0, 10.0], str(pr))
check("A its cost: endpoint 0 + target-only 1 + lasso 2 = 3", c == 3, str(c))
_, pr, _ = P.validate({"members": [{"key": "kl"}, {"key": "external"}]}, **KW)
check("A a plan without the target-only fit is refused", "protected_member_missing" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "kl"}]}, **KW)
check("A a plan without the released model is refused", "protected_member_missing" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"}, {"key": "euclidean"}]}, **KW)
check("A a member the facts do not admit is refused, by name", "member_not_admissible" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                   {"key": "kl_lasso", "covariates": ["age", "creatinine"]}]}, **KW)
check("A a covariate the analyst did not declare is refused", "covariate_not_declared" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                   {"key": "mahalanobis", "mask": ["age", "rec_cmv"]}]},
                      **{**KW, "covered": COV[:6]})
check("A masking a term the release does not cover is refused", "mask_not_covered" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                   {"key": "mahalanobis", "pad_absent": True}]},
                      **{**KW, "external_form": "coefficients and covariance"})
check("A padding beside a released covariance is refused", "pad_not_applicable" in codes(pr))
ok, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                    {"key": "mahalanobis", "pad_absent": True}]}, **KW)
check("A padding an identity-metric member is accepted", ok is not None and next(m for m in ok["members"] if m["key"] == "mahalanobis").get("pad_absent") is True, str(pr))

# masks need the analyst's words: never a statistical disagreement
WORDS = "Our diabetes flag is defined differently from the registry's, so do not trust that one."
for fam in ("mahalanobis", "kl"):
    _, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                       {"key": fam, "mask": ["diabetes"]}]}, **KW, mask_evidence_text=WORDS)
    check(f"A {fam}: a mask with no evidence is refused", "mask_without_evidence" in codes(pr))
    _, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                       {"key": fam, "mask": ["diabetes"], "mask_evidence": "diabetes is unreliable"}]},
                          **KW, mask_evidence_text=WORDS)
    check(f"A {fam}: evidence the analyst did not write is refused", "mask_without_evidence" in codes(pr))
    _, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                       {"key": fam, "mask": ["diabetes", "bmi"],
                                        "mask_evidence": "Our diabetes flag is defined differently"}]},
                          **KW, mask_evidence_text=WORDS)
    check(f"A {fam}: evidence that does not name a masked term is refused", "mask_evidence_does_not_name" in codes(pr))
    ok, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                        {"key": fam, "mask": ["diabetes"],
                                         "mask_evidence": "Our diabetes flag is defined differently"}]},
                           **KW, mask_evidence_text=WORDS)
    mm = next((m for m in (ok or {}).get("members", []) if m["key"] == fam), {})
    check(f"A {fam}: a mask quoting the analyst's words is accepted and keeps them",
          ok is not None and mm.get("mask") == ["diabetes"] and mm.get("mask_evidence"), str(pr))
check("A the evidence is provenance: it does not enter the hashed plan",
      "mask_evidence" not in json.dumps(pipeline._plan_for_hash(ok)))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"}, {"key": "kl", "etas": [-1, 2]}]}, **KW)
check("A a negative eta is refused", "grid_invalid" in codes(pr))
_, pr, _ = P.validate({"members": [{"key": "internal", "etas": [1, 2]}, {"key": "external"}]}, **KW)
check("A a grid on the target-only fit is refused", "grid_not_applicable" in codes(pr))
_, pr, _ = P.validate({"row": "cox_ties", "members": [{"key": "internal_ties"}]},
                      **{**KW, "design": "nested case-control"})
check("A the tie-corrected row on a matched design is refused", "row_not_admissible" in codes(pr))
ok, pr, c = P.validate({"row": "cox_ties", "members": [{"key": "internal_ties"}, {"key": "kl_ties"},
                                                       {"key": "external"}]}, **KW)
check("A the tie-corrected row: target-only, KL and the released model", ok is not None and c == 2, str(pr))
# BregSurv 1.3.0: the tie-corrected row is the whole standard set on Breslow's likelihood
for form in ("coefficients alone", "coefficients and covariance", "individual-level data", "none"):
    std = P.admissible_keys("cox", "full cohort", form, False)
    tie = P.admissible_keys("cox_ties", "full cohort", form, False)
    check(f"A the tie-corrected row holds every standard member ({form})",
          tie == [k if k == "external" else k + "_ties" for k in std] and len(tie) == len(std), str(tie))
check("A a tie member costs what its standard member costs",
      all(P.cost(k + "_ties") == P.cost(k) for k in P.admissible_keys("cox", "full cohort", "coefficients and covariance", False) if k != "external"))
ok2, pr2, c2 = P.validate({"row": "cox_ties", "ties": "breslow", "members": [{"key": "internal_ties"}, {"key": "external"},
                          {"key": "mahalanobis_lasso_ties", "grid": {"from": 0.1, "to": 100, "points": 10}},
                          {"key": "kl_ridge_ties", "nlambda": 20}]}, **KW)
check("A a full tie plan with grids and nlambda is accepted", ok2 is not None and c2 == 5, str(pr2))
_, pr3, _ = P.validate({"row": "cox_ties", "ties": "exact", "members": [{"key": "internal_ties"}]}, **KW)
check("A the exact correction is no longer offered", "ties_unknown" in codes(pr3), str(pr3))
full_cov = P.default_plan("cox", "full cohort", "coefficients and covariance", False)
check("A the fixed-default plan with a covariance costs 20 units (the budget)", P.plan_cost(full_cov) == 20,
      str(P.plan_cost(full_cov)))
check("A the fixed-default plan with coefficients alone costs 15",
      P.plan_cost(P.default_plan("cox", "full cohort", "coefficients alone", False)) == 15)
check("A the discrete row with networks costs 12",
      P.plan_cost(P.default_plan("discrete", "full cohort", "coefficients alone", True)) == 12)
big = {"members": full_cov["members"] + []}
_, pr, c = P.validate(big, **{**KW, "external_form": "coefficients and covariance"}, budget=19)
check("A a plan over the budget is refused, with its cost", "over_budget" in codes(pr) and c == 20, str(c))

# ---- B. a plan through pipeline.run: hash, payload, trace, repro.R ---------------------------------------
spec = json.loads((FX / "F01" / "spec.json").read_text()); d = FX / "F01" / "data"
train = str(d / spec["train"]); rel = str(d / spec["release_file"])
header = [h.strip().strip('"') for h in Path(train).read_text().splitlines()[0].split(",")]
ext = X.read_external(rel, run_r=_run_r, cohort_columns=header, cohort_outcome=(spec["time_col"], spec["event_col"]))
kw = {k: v for k, v in ext.pipeline_kwargs().items() if k.startswith("external_")}
expr = re.sub(r"[^A-Za-z0-9._]", ".", Path(train).stem)
decl = Declaration(time_col=spec["time_col"], event_col=spec["event_col"], event_value=str(spec["event_value"]),
                   covariates=[h for h in header if h not in (spec["time_col"], spec["event_col"])],
                   source="reply", covariates_time_zero="yes")
prof = _run_r("profile_columns.R", {"data_path": train, "data_expr": expr,
                                    "external_beta_inline": kw["external_beta_inline"]})
pl, pr, _ = P.validate({"row": "cox", "reason": "test", "members": [
    {"key": "internal"}, {"key": "external"}, {"key": "kl", "etas": [0.5, 2, 8], "reason": "test"},
    {"key": "mahalanobis_lasso", "covariates": spec["covariates_sub"]}]},
    design="full cohort", external_form="coefficients alone", has_baseline=False,
    covariates=decl.covariates, covered=list(kw["external_beta_inline"]))
check("B the test plan is valid", pl is not None, str(pr))
rc0 = pipeline.resolve_config(train, expr, decl, **kw)
rc1 = pipeline.resolve_config(train, expr, decl, plan=pl, **kw)
check("B the plan enters the approval hash", rc0["sha256"] != rc1["sha256"])
check("B the candidate set is the plan's members", rc1["candidate_keys"] == ["internal", "kl", "mahalanobis_lasso", "external"]
      or sorted(rc1["candidate_keys"]) == sorted(["internal", "kl", "mahalanobis_lasso", "external"]), str(rc1["candidate_keys"]))
pl2 = json.loads(json.dumps(pl)); pl2["members"][1]["reason"] = "another reason"
check("B a different reason does not change the hash", pipeline.resolve_config(train, expr, decl, plan=pl2, **kw)["sha256"] == rc1["sha256"])
rr = pipeline.run(train, expr, decl, profile=prof, run_r=_run_r, approved_config_sha256=rc1["sha256"], plan=pl, **kw)
got = sorted(c["key"] for c in rr.candidates["candidates"])
check("B the run fits exactly the plan's members", got == sorted(["internal", "kl", "mahalanobis_lasso", "external"]), str(got))
check("B the trace carries the plan with its reasons and its cost",
      rr.provenance.get("plan", {}).get("plan", {}).get("reason") == "test" and rr.provenance["plan"]["cost_units"] == 4)
out = Path(tempfile.mkdtemp(prefix="v4plan_"))
paths = rr.save(str(out))
repro = Path(paths["repro"]) if isinstance(paths, dict) and "repro" in paths else out / "repro.R"
check("B repro.R carries the plan", "plan        = jsonlite::fromJSON(" in repro.read_text())
env = dict(os.environ, BREGSURV_R_SCRIPTS=str(V4 / "mcp" / "r_scripts"))
p = subprocess.run(["Rscript", str(repro), train], cwd=str(out), capture_output=True, text=True, timeout=3600, env=env)
o = p.stdout + p.stderr
sel = rr.candidates["selected"]
check("B repro.R replays the plan with no model: same partition", "fold assignment REPRODUCED" in o, o[-400:])
m = re.search(r"selected: (.+?) \(loss ([-\d.eE]+)\)", o)
check("B ... and the same selection at the same loss",
      m is not None and m.group(1).strip() == str(sel["label"]).strip() and abs(float(m.group(2)) - float(sel["loss"])) < 5e-6,
      (m.group(0) if m else o[-300:]))

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
