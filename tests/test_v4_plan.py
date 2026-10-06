"""V4 work item 1: run_candidates.R takes a plan. Needs R; no model.

Checks, on synth200 fixtures: without a plan the V3 set is fitted exactly as before (the benchmark's
reference, to 1e-9); a plan fits only the members it lists and each on the SAME partition (a member's loss
equals its loss in the full set); a member's own grid, covariate subset, mask and zero-padding take effect
and are recorded; the tie-corrected row fits its two members, records the released model as unavailable and
selects on one functional; padding a member with a released covariance is refused; the discrete row runs
the planned members only.
  python mcp/test_v4_plan.py
"""
import json, re, sys
from pathlib import Path

V4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V4))
from bregsurv_agent.rbridge import _run_r  # noqa: E402
from bregsurv_agent import pipeline, external as X  # noqa: E402
from bregsurv_agent.declaration import Declaration  # noqa: E402

FX = Path("/home/ybshao/jobs/synth200/fixtures")
GOLD = Path("/home/ybshao/jobs/synth200/golden")
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def data_expr_for(path):
    return re.sub(r"[^A-Za-z0-9._]", ".", Path(path).stem)


def payload_for(fid, discrete=False):
    spec = json.loads((FX / fid / "spec.json").read_text()); d = FX / fid / "data"
    train = str(d / spec["train"])
    rel = str(d / spec["release_file"]) if spec.get("release_file") else None
    header = [h.strip().strip('"') for h in Path(train).read_text().splitlines()[0].split(",")]
    outcome_pair = (spec.get("time_col"), spec["event_col"]) if spec.get("time_col") else None
    ext = X.read_external(rel, run_r=_run_r, cohort_columns=header, cohort_outcome=outcome_pair) if rel else None
    outcome = {spec.get("time_col"), spec["event_col"], spec.get("stratum_col")}
    decl = Declaration(time_col=spec.get("time_col"), event_col=spec["event_col"],
                       event_value=str(spec["event_value"]), covariates=[h for h in header if h not in outcome],
                       source="reply", stratum_col=spec.get("stratum_col"), covariates_time_zero="yes")
    if ext is not None and ext.individual_data:
        decl.external_data_path = rel; decl.external_data_expr = data_expr_for(rel)
    if discrete and spec.get("discrete"):
        decl.interval_width = float(spec["discrete"]["width"]); decl.n_intervals = int(spec["discrete"]["K"])
    kw = ext.pipeline_kwargs() if ext is not None else {}
    kw = {k: v for k, v in kw.items() if k.startswith("external_")}
    return spec, pipeline.build_payload(train, data_expr_for(train), decl, **kw)


def run(payload, plan=None):
    p = dict(payload)
    if plan is not None:
        p["plan"] = plan
    return _run_r("run_candidates.R", p, timeout_s=3600)


def rows(res):
    return {r["key"]: r for r in res.get("candidates", [])}


# ---- A. no plan: the V3 set, exactly the benchmark's reference ---------------------------------
spec, pay = payload_for("F01")
full = run(pay)
check("A F01 without a plan: the run completes", full.get("status") == "ok", str(full.get("message"))[:200])
gold = json.loads((GOLD / "F01_all.json").read_text())
gm = gold.get("members") or {}
R = rows(full)
diffs = [abs(R[k]["loss"] - m["cv_loss"]) for k, m in gm.items()
         if k in R and m.get("cv_loss") is not None and R[k].get("loss") is not None]
check("A every member's CV loss equals the benchmark's reference to 1e-9",
      len(diffs) == len([m for m in gm.values() if m.get("cv_loss") is not None]) and max(diffs) < 1e-9,
      f"{len(diffs)} compared, worst {max(diffs) if diffs else None}")

# ---- B. a plan of three members, on the same partition -----------------------------------------
sub = run(pay, {"row": "cox", "members": [{"key": "internal"}, {"key": "kl"}, {"key": "external"}]})
S = rows(sub)
check("B the plan fits only the three members it lists", set(S) == {"internal", "kl", "external"}, str(sorted(S)))
check("B each planned member's loss equals its loss in the full set (one partition)",
      all(abs(S[k]["loss"] - R[k]["loss"]) < 1e-9 for k in S if S[k].get("loss") is not None))
check("B the partition is the full set's", sub["partition"]["folds"] == full["partition"]["folds"])

# ---- C. a member's own grid, covariate subset, mask ----------------------------------------------
keep = spec["covariates_sub"]
plan_c = {"row": "cox", "members": [
    {"key": "internal"}, {"key": "external"},
    {"key": "kl", "etas": [0.1, 1, 10]},
    {"key": "kl_lasso", "covariates": keep},
    {"key": "mahalanobis", "mask": ["age", "bmi"]}]}
c = run(pay, plan_c)
C = rows(c)
check("C the plan with settings runs", c.get("status") == "ok", str(c.get("message"))[:200])
if c.get("status") == "ok":
    check("C kl's selected eta lies on its own grid", C["kl"]["eta"] in (0.0, 0.1, 1.0, 10.0), str(C["kl"]["eta"]))
    check("C kl_lasso was fitted on the covariate subset and records it", C["kl_lasso"]["covariates_used"] == len(keep))
    beta = C["kl_lasso"].get("beta") or {}
    left_out = [v for v in spec["covariates_all"] if v not in keep]
    check("C kl_lasso's coefficients are zero on the terms it left out",
          all(abs(beta.get(v, 0.0)) < 1e-12 for v in left_out), str({v: beta.get(v) for v in left_out}))
    check("C the masked terms are recorded", sorted(C["mahalanobis"]["masked"]) == ["age", "bmi"])
    check("C masking changes the Mahalanobis fit", abs(C["mahalanobis"]["loss"] - R["mahalanobis"]["loss"]) > 1e-9)
    check("C target-only stays at eta 0 whatever the plan", C["internal"]["eta"] in (0.0, None))

# ---- D. zero-padding an absent term, on a release that covers part of the cohort (F12) -----------
spec12, pay12 = payload_for("F12")
d0 = run(pay12, {"members": [{"key": "internal"}, {"key": "mahalanobis"}]})
d1 = run(pay12, {"members": [{"key": "internal"}, {"key": "mahalanobis", "pad_absent": True}]})
check("D F12: padding runs and is recorded", d1.get("status") == "ok" and rows(d1)["mahalanobis"]["padded"] is True,
      str(d1.get("message"))[:200])
if d0.get("status") == "ok" and d1.get("status") == "ok":
    check("D padding changes the fit (the absent terms are now pulled toward zero)",
          abs(rows(d0)["mahalanobis"]["loss"] - rows(d1)["mahalanobis"]["loss"]) > 1e-9)

# ---- E. padding beside a released covariance is refused (F04) ------------------------------------
spec4, pay4 = payload_for("F04")
e = run(pay4, {"members": [{"key": "internal"}, {"key": "mahalanobis", "pad_absent": True}]})
check("E padding a member with a released covariance is refused, by name",
      e.get("status") != "ok" and "identity-metric" in str(e.get("message")), str(e.get("message"))[:200])

# ---- F. the tie-corrected row (F03: months, many ties) -------------------------------------------
spec3, pay3 = payload_for("F03")
# BregSurv 1.3.0: the row is the whole standard set on Breslow's likelihood, the released model scored too
TIE_PLAN = {"row": "cox_ties", "ties": "breslow",
            "members": [{"key": "internal_ties"}, {"key": "kl_ties"}, {"key": "external"},
                        {"key": "mahalanobis_lasso_ties", "etas": [0.5, 5.0]}, {"key": "euclidean_ridge_ties", "nlambda": 20}]}
f = run(pay3, TIE_PLAN)
F = rows(f)
check("F the tie-corrected row runs", f.get("status") == "ok", str(f.get("message"))[:300])
if f.get("status") == "ok":
    check("F its members are the planned tie members and the released model",
          set(F) == {"internal_ties", "kl_ties", "external", "mahalanobis_lasso_ties", "euclidean_ridge_ties"}, str(sorted(F)))
    check("F every member fitted, the released model scored", all(F[k]["status"] == "ok" for k in F),
          str({k: F[k]["status"] for k in F}))
    check("F one functional, Breslow's", f.get("scorer") in (["vvh/breslow"], "vvh/breslow"), str(f.get("scorer")))
    # the same members on the standard row give different losses on these heavily tied data
    g0 = run(pay3, {"row": "cox", "members": [{"key": "internal"}, {"key": "kl"}, {"key": "external"},
                                               {"key": "mahalanobis_lasso", "etas": [0.5, 5.0]}]})
    G0 = rows(g0)
    check("F the tie row's losses differ from the standard row's (the correction reaches the fits)",
          all(abs(F[k + "_ties"]["loss"] - G0[k]["loss"]) > 1e-8 for k in ("internal", "kl", "mahalanobis_lasso"))
          and abs(F["external"]["loss"] - G0["external"]["loss"]) > 1e-8)
    # the R check of jobs/ties_dev/check_v4_ties.R recomputes two members by calling the library directly
    Path("/home/ybshao/jobs/ties_dev/v4_F03_payload.json").write_text(json.dumps(pay3))
    Path("/home/ybshao/jobs/ties_dev/v4_F03_result.json").write_text(json.dumps(f))

# ---- G. the discrete row runs the planned members only (F18) --------------------------------------
spec18, pay18 = payload_for("F18", discrete=True)
g = run(pay18, {"row": "discrete", "members": [{"key": "internal_discrete"}, {"key": "external_discrete"},
                                                {"key": "discretekl", "etas": [5, 50]}]})
G = rows(g)
check("G the discrete plan runs without the network members", g.get("status") == "ok"
      and set(G) == {"internal_discrete", "external_discrete", "discretekl"}, f"{g.get('status')} {sorted(G)} {str(g.get('message'))[:200]}")
if g.get("status") == "ok":
    check("G DiscreteKL's selected eta lies on the planned grid", G["discretekl"]["eta"] in (0.0, 5.0, 50.0), str(G["discretekl"]["eta"]))

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
