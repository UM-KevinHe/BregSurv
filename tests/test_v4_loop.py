"""V4 work item 4: the analyst loop (bregsurv_agent/analyst.py) and the reuse of fitted members.

A  no R: the options, the schemas, the default grids against run_candidates.R, the situations on
   saved diagnostics cards, and run_loop with a scripted planner and a fake fitter -- refused plans
   go back with the problems, the fallback, refinements priced by what they change, reuse of the rest
B  R: a scripted planner over the real fitter on a synthetic fixture -- the refined member is
   refitted and the others are reused, the final run with every row reused equals one run of the
   final plan with nothing reused, the planner never sees a held-out number, a reused row whose
   partition differs is refused, and repro.R replays the final plan with no model
C  the app: a run through `submit_answer` with the planner on (a scripted proposer), the planner's
   decisions in the trace and the action log
  python mcp/test_v4_loop.py            (C needs gradio: run under app-env)
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

V4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V4))
os.environ["BREGSURV_PLANNER"] = "on"     # this suite tests the planner; the V3 suites run with it off
from bregsurv_agent import analyst as A, plan as P  # noqa: E402

FX = Path("/home/ybshao/jobs/synth200/fixtures")
CARDS = Path("/home/ybshao/jobs/v4/diagnose_cards")
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class D:   # a minimal declaration for the pure tests
    def __init__(self, covs, design="full cohort", discrete=None):
        self.covariates = covs; self.design = design; self.discrete = discrete
        self.external_data_expr = None; self.time_col = "t"; self.event_col = "d"
        self.event_value = "1"; self.stratum_col = None


COV = ["age", "bmi", "egfr", "donor_age", "cold_ischemia"]
EXT = {"external_beta_inline": {"age": 0.5, "bmi": -0.4, "egfr": 0.3}}

# ---- A. pure -------------------------------------------------------------------------------------
o = A.options_for(D(COV), EXT)
check("A coefficients alone: the standard row and the tie-corrected row",
      list(o.rows) == ["cox", "cox_ties"] and o.rows["cox"][0] == "internal" and "external" in o.rows["cox"],
      str(o.rows))
check("A covered terms are the release's names among the covariates", o.covered == ["age", "bmi", "egfr"])
o2 = A.options_for(D(COV), {**EXT, "external_Q_inline": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]})
check("A a covariance adds the Euclidean members", "euclidean_lasso" in o2.rows["cox"] and o2.has_Q)
o3 = A.options_for(D(COV, discrete={"n_intervals": 5}), EXT)
check("A a declared discrete time scale settles the row", list(o3.rows) == ["discrete"], str(o3.rows))
o4 = A.options_for(D(COV, design="nested case-control"), EXT)
check("A a matched design has no tie-corrected row", list(o4.rows) == ["cox"], str(o4.rows))
sch = A.plan_schema(o2)
br = {b["properties"]["row"]["enum"][0]: b for b in sch["properties"]["analysis"]["anyOf"]}
check("A the plan schema: reasoning first, then one branch per row",
      list(sch["properties"])[0] == "reasoning" and set(br) == set(o2.rows), str(list(br)))
check("A each row's branch lists that row's members only, so a plan cannot mix rows (smoke F18)",
      all(set(b["properties"]["members"]["items"]["properties"]["key"]["enum"]) == set(o2.rows[r])
          for r, b in br.items())
      and br["cox_ties"]["properties"]["ties"].get("enum") == list(P.TIES)
      and br["cox"]["properties"]["ties"] == {"type": "null"})
check("A a refinement's members come from the plan's row only",
      set(A.next_step_schema(o2, "cox_ties")["properties"]["members"]["anyOf"][0]["items"]["properties"]["key"]["enum"])
      == set(o2.rows["cox_ties"]))
# smoke 2: exact ties only where the library can enumerate them; few ties named
import dataclasses as _dc
card_inf = {"outcome": {"tie_fraction": 0.05, "exact_ties": {"feasible": False}}}
check("A only Breslow is offered (BregSurv 1.3.0)",
      A.ties_allowed(card_inf) == ("breslow",) and A.ties_allowed({"outcome": {}}) == ("breslow",))
o_inf = _dc.replace(o2, ties_allowed=A.ties_allowed(card_inf))
br_inf = {b["properties"]["row"]["enum"][0]: b for b in A.plan_schema(o_inf)["properties"]["analysis"]["anyOf"]}
check("A the schema offers only the feasible tie corrections", br_inf["cox_ties"]["properties"]["ties"]["enum"] == ["breslow"])
pl_x, pr_x, _ = A._validate({"row": "cox_ties", "ties": "exact", "members": [{"key": "internal_ties"}]}, o_inf, 10 ** 6)
check("A an exact plan is refused by name",
      pl_x is None and any(p["code"] == "ties_unknown" for p in pr_x), str(pr_x))
check("A few ties: the few-ties note, not the tied-times note",
      "few_ties" in A.situations(card_inf, o2) and "tied_times" not in A.situations(card_inf, o2)
      and any(n == "few-ties" for n, _ in A.playbook(["few_ties"])))
check("A the tie-corrected row is described as the same members on Breslow's likelihood",
      "same members as the standard row" in A._lost_on_ties(o2))
check("A a tie member is described as its standard member with Breslow ties",
      A.member_label("mahalanobis_lasso_ties", True) == A.member_label("mahalanobis_lasso", True) + ", Breslow ties")
check("A the next-step schema: reasoning first, finish or refine",
      list(A.next_step_schema(o2)["properties"])[0] == "reasoning"
      and A.next_step_schema(o2)["properties"]["action"]["enum"] == ["finish", "refine"])
# the default grids described to the planner are the ones run_candidates.R fits
rsrc = (V4 / "mcp" / "r_scripts" / "run_candidates.R").read_text()
consts = dict(re.findall(r"^\s*(ETAS\w*)\s*<-\s*log_eta\(([^)]*)\)", rsrc, flags=re.M))
def _lg(a):
    hi, n = [float(x) for x in a.split(",")[:2]]; return (0.01, hi, int(n))
use = {"kl": "ETAS", "kl_ridge": "ETAS_PEN", "kl_lasso": "ETAS_PEN", "mahalanobis": "ETAS_MDTL",
       "euclidean": "ETAS_MDTL", "mahalanobis_ridge": "ETAS_MDTL_RIDGE", "euclidean_ridge": "ETAS_MDTL_RIDGE",
       "mahalanobis_lasso": "ETAS_MDTL_ENET", "euclidean_lasso": "ETAS_MDTL_ENET"}
check("A the default grids described to the planner match run_candidates.R",
      all(_lg(consts[c]) == A.DEFAULT_GRIDS[k] for k, c in use.items()), str(consts))
# a grid given by its range
ok, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                    {"key": "kl", "grid": {"from": 1, "to": 1000, "points": 4}}]},
                       design="full cohort", external_form="coefficients alone", has_baseline=False,
                       covariates=COV, covered=["age", "bmi", "egfr"])
kl = next(m for m in ok["members"] if m["key"] == "kl") if ok else {}
check("A a grid range is expanded on the log scale and kept beside its values",
      kl.get("etas") == [1.0, 10.0, 100.0, 1000.0] and kl.get("grid") == {"from": 1.0, "to": 1000.0, "points": 4},
      str(kl))
_, pr, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                   {"key": "kl", "grid": {"from": 0, "to": 10, "points": 4}}]},
                      design="full cohort", external_form="coefficients alone", has_baseline=False,
                      covariates=COV, covered=["age"])
check("A a range starting at zero is refused", any(p["code"] == "grid_invalid" for p in pr))
ok2, pr2, _ = P.validate(ok, design="full cohort", external_form="coefficients alone", has_baseline=False,
                         covariates=COV, covered=["age", "bmi", "egfr"])
check("A a checked plan checks again to itself (a refinement re-checks the whole plan)", ok2 == ok, str(pr2))
_, pr3, _ = P.validate({"members": [{"key": "internal"}, {"key": "external"},
                                    {"key": "kl", "grid": {"from": 1, "to": 1000, "points": 4}, "etas": [1, 2]}]},
                       design="full cohort", external_form="coefficients alone", has_baseline=False,
                       covariates=COV, covered=["age"])
check("A a range and different values together are refused", any(p["code"] == "grid_twice" for p in pr3))
# situations on saved cards
if CARDS.exists():
    f01, f02 = (json.loads((CARDS / f"{x}.json").read_text()) for x in ("F01", "F02"))
    o10 = A.options_for(D([t["term"] for t in f01["terms"]]), {"external_beta_inline": {t["term"]: 0 for t in f01["terms"]}})
    s01, s02 = A.situations(f01, o10), A.situations(f02, o10)
    check("A a close release reads strong, a far one weak", "strong_release" in s01 and "weak_release" in s02,
          f"{s01} / {s02}")
    f18 = json.loads((CARDS / "F18.json").read_text())
    check("A frequent ties raise the tied-times note", "tied_times" in A.situations(f18, o10))
    txt = A.render_task(D([t["term"] for t in f02["terms"]]), f02, o10, "please borrow carefully")
    check("A the task text carries the diagnostics, the costs, the budget and the analyst's words",
          "calibration slope" in txt and "cost 2" in txt and "budget: 20 units" in txt
          and "please borrow carefully" in txt, txt[:300])
    check("A the playbook notes are retrieved by situation", "[weak-release]" in A.render_notes(s02)
          and "[strong-release]" not in A.render_notes(s02))
    os.environ["BREGSURV_ABLATE"] = "no_diagnostics"
    txt_nd = A.render_task(D([t["term"] for t in f02["terms"]]), f02, o10, "please borrow carefully")
    check("A ablation no_diagnostics: no card in the task, the rest kept",
          "TRANSFER DIAGNOSTICS" not in txt_nd and "calibration slope" not in txt_nd
          and "per term:" not in txt_nd and "cost 2" in txt_nd and "please borrow carefully" in txt_nd)
    os.environ["BREGSURV_ABLATE"] = "no_playbook"
    check("A ablation no_playbook: no note reaches the planner", A.render_notes(s02) == ""
          and "TRANSFER DIAGNOSTICS" in A.render_task(D([t["term"] for t in f02["terms"]]), f02, o10, "x"))
    os.environ.pop("BREGSURV_ABLATE")


# a scripted planner and a fake fitter
def scripted(answers):
    calls = []
    def propose(policy_name, user, schema, call_name, max_tokens):
        calls.append({"name": call_name, "user": user})
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    return propose, calls


def fake_fitter():
    log = []
    def fit(pl, reuse):
        log.append({"plan": pl, "reuse": reuse})
        rows = []
        for m in pl["members"]:
            ru = next((r for r in (reuse or {}).get("rows", []) if r["key"] == m["key"]), None)
            rows.append(ru or {"key": m["key"], "status": "ok", "loss": 7.0 - 0.01 * len(rows),
                               "eta": (None if m["key"] in ("internal", "external") else
                                       max(m.get("etas", [200.0]))),
                               "eta_at_grid_max": m["key"] == "kl", "lambda": None, "n_nonzero": 5})
        return {"candidates": rows, "partition": {"folds": [1, 2, 3], "rng_kind": "Mersenne-Twister"}}
    return fit, log


M = lambda key, **kw: {"key": key, "grid": None, "covariates": None, "mask": None, "pad_absent": None,
                       "reason": kw.pop("reason", "r"), **kw}
card = {"facts": {"n": 400, "n_events": 200, "p": 5, "events_per_parameter": 40.0},
        "outcome": {"tie_fraction": 0.01}, "external": {"n_covered": 3}, "terms": []}
bad_plan = {"reasoning": "x", "row": "cox", "ties": None, "members": [M("kl")], "reason": "only kl"}
good_plan = {"reasoning": "x", "row": "cox", "ties": None,
             "members": [M("internal"), M("external"), M("kl"), M("kl_lasso")], "reason": "plan"}
refine = {"reasoning": "y", "action": "refine",
          "members": [M("kl", grid={"from": 1, "to": 10000, "points": 20})], "reason": "top of grid"}
finish = {"reasoning": "z", "action": "finish", "members": None, "reason": "done"}
prop, calls = scripted([bad_plan, good_plan, refine, finish])
fit, flog = fake_fitter()
r = A.run_loop(prop, fit, declaration=D(COV), card=card, opts=o, words="")
check("A a refused plan goes back with the harness's problems by name",
      "protected_member_missing" in calls[1]["user"] and "YOUR LAST PROPOSAL WAS REFUSED" in calls[1]["user"])
check("A the accepted plan is fitted, then refined once, then finished",
      [c["name"] for c in calls] == ["analysis_plan", "analysis_plan", "next_step", "next_step"]
      and len(flog) == 2, str([c["name"] for c in calls]))
check("A the refinement refits the changed member only and reuses the rest",
      sorted(x["key"] for x in flog[1]["reuse"]["rows"]) == ["internal", "kl_lasso"]
      and flog[1]["reuse"]["partition"]["folds"] == [1, 2, 3])
fits = [s for s in r.steps if s["step"] == "fit"]
check("A units: the plan's cost, then the refined member's", [s["units"] for s in fits] == [4, 1],
      str([s["units"] for s in fits]))
check("A the planner sees the selected weight at the top of the grid", "TOP of its grid" in calls[2]["user"])
check("A the final plan carries the refined grid", next(m for m in r.plan["members"] if m["key"] == "kl")
      .get("grid") == {"from": 1.0, "to": 10000.0, "points": 20})
check("A the final reuse holds every fitted member but the released model",
      sorted(x["key"] for x in r.reuse["rows"]) == ["internal", "kl", "kl_lasso"])
check("A the loop's calls are counted", r.n_calls == 4 and r.n_calls <= A.MAX_CALLS)
# over budget and nothing-changes are refused, then the loop finishes
big = {"reasoning": "y", "action": "refine", "members": [M("mahalanobis_ridge"), M("mahalanobis_lasso"),
       M("kl_ridge"), M("internal_ridge"), M("internal_lasso"), M("mahalanobis"),
       M("kl", grid={"from": 2, "to": 3, "points": 2}), M("kl_lasso", grid={"from": 2, "to": 3, "points": 2}),
       ], "reason": "everything"}
same = {"reasoning": "y", "action": "refine", "members": [M("kl_lasso")], "reason": "again"}
prop, calls = scripted([good_plan, big, same, finish])
fit, flog = fake_fitter()
o_small = A.options_for(D(COV), EXT, budget=8)
r = A.run_loop(prop, fit, declaration=D(COV), card=card, opts=o_small, words="", max_refinements=1)
probs = [p["code"] for s in r.steps for p in s.get("problems") or []]
check("A a refinement over the budget is refused with its cost", "over_budget" in probs, str(probs))
check("A a refinement that changes nothing is refused", "nothing_changes" in probs, str(probs))
check("A ... and the loop finishes with nothing refitted", len(flog) == 1)
# three refusals: the default plan, recorded
prop, calls = scripted([bad_plan, bad_plan, ValueError("no answer"), finish])
fit, flog = fake_fitter()
r = A.run_loop(prop, fit, declaration=D(COV), card=card, opts=o, words="", max_refinements=0)
check("A three refusals (one a failed call): the fixed default plan, and the fallback is recorded",
      r.fallback and sorted(m["key"] for m in r.plan["members"]) == sorted(o.rows["cox"])
      and any(p["code"] == "no_answer" for s in r.steps for p in s.get("problems") or []), r.fallback)
# ---- 4b: the discrete row when the time scale is open
class DD(D):
    def __init__(self, covs, src=None, test=False):
        super().__init__(covs); self.sources = {"discrete": src} if src else {}
        self.has_test_data = test; self.interval_width = None; self.n_intervals = None
        self.time_is_interval_index = False
EXTB = {**EXT, "external_baseline_inline": {"time": [1, 2, 3], "cumhaz": [0.1, 0.2, 0.3]}}
ob = A.options_for(DD(COV, "default: continuous time; ..."), EXTB)
_brb = {b["properties"]["row"]["enum"][0]: b for b in A.plan_schema(ob)["properties"]["analysis"]["anyOf"]}
check("A 4b: with the time scale left to the default, the discrete row is offered and its grid is open",
      "discrete" in ob.rows and ob.intervals_open and _brb["discrete"]["properties"]["intervals"] == A.INTERVALS_SCHEMA
      and _brb["cox"]["properties"]["intervals"] == {"type": "null"}, str(ob.rows))
check("A 4b: an analyst's reply settles the time scale: no discrete row",
      "discrete" not in A.options_for(DD(COV, "reply"), EXTB).rows)
check("A 4b: a test file keeps the discrete row out (it has no held-out scorer)",
      "discrete" not in A.options_for(DD(COV, None, test=True), EXTB).rows)
check("A 4b: without an open grid no row's branch has an intervals field",
      all("intervals" not in b["properties"] for b in A.plan_schema(o)["properties"]["analysis"]["anyOf"])
      and not o.intervals_open)
nested = {"reasoning": "x", "analysis": {"row": "cox", "ties": None, "members": [M("internal"), M("external")]},
          "reason": "nested"}
prop, calls = scripted([nested, finish])
fit, flog = fake_fitter()
r = A.run_loop(prop, fit, declaration=D(COV), card=card, opts=o, words="")
check("A a plan in the branched form is read: row and members from `analysis`, the reason from the top",
      r.plan["row"] == "cox" and [m["key"] for m in r.plan["members"]] == ["internal", "external"]
      and r.plan.get("reason") == "nested", str(r.plan))
check("A 4b: a release without a baseline hazard offers no discrete row (it could borrow nothing there)",
      "discrete" not in A.options_for(DD(COV, "default: x"), EXT).rows)
KWB = dict(design="full cohort", external_form="coefficients alone", has_baseline=True, covariates=COV,
           covered=["age", "bmi", "egfr"])
dplan = {"row": "discrete", "members": [{"key": "internal_discrete"}, {"key": "external_discrete"},
                                        {"key": "discretekl"}]}
_, pr, _ = P.validate(dplan, **KWB, intervals_open=True)
check("A 4b: the discrete row without intervals is refused when the grid is open",
      any(p["code"] == "intervals_missing" for p in pr), str(pr))
okd, pr, _ = P.validate({**dplan, "intervals": {"width": 1, "n_intervals": 12, "time_is_index": False}}, **KWB,
                        intervals_open=True)
check("A 4b: ... with a width and a number it is accepted, the grid kept in the plan",
      okd is not None and okd["intervals"] == {"width": 1.0, "n_intervals": 12, "time_is_index": False}, str(pr))
_, pr, _ = P.validate({**dplan, "intervals": {"width": 1, "n_intervals": 12, "time_is_index": False}}, **KWB)
check("A 4b: intervals on a declared time scale are refused", any(p["code"] == "intervals_declared" for p in pr))
_, pr, _ = P.validate({"row": "cox", "members": [{"key": "internal"}, {"key": "external"}],
                       "intervals": {"width": 1, "n_intervals": 12, "time_is_index": False}}, **KWB, intervals_open=True)
check("A 4b: intervals on the Cox row are refused", any(p["code"] == "intervals_not_applicable" for p in pr))
am = A.amend_declaration(DD(COV, "default: x"), {**okd, "reason": "coarse monthly follow-up"})
check("A 4b: the amended declaration carries the grid and names the planner as its source",
      am.n_intervals == 12 and am.interval_width == 1.0 and am.sources["discrete"].startswith("planned: coarse"))
dp = lambda k: {"reasoning": "x", "row": "discrete", "ties": None,
                "intervals": {"width": 1, "n_intervals": k, "time_is_index": False},
                "members": [M("internal_discrete"), M("external_discrete"), M("discretekl")], "reason": "grouped"}
prop, calls = scripted([dp(150), dp(12), finish])
fit, flog = fake_fitter()
seen = []
r = A.run_loop(prop, fit, declaration=DD(COV, "default: x"), card=card, opts=ob, words="",
               check_intervals=lambda pl: (seen.append(pl["intervals"]["n_intervals"]) or
                                           ([{"code": "intervals_refused:discrete_horizon_unreached",
                                              "message": "no subject reaches interval 150"}]
                                            if pl["intervals"]["n_intervals"] > 99 else [])))
check("A 4b: a planned grid the gate refuses goes back with the gate's reason; the next is fitted",
      seen == [150, 12] and "discrete_horizon_unreached" in calls[1]["user"] and len(flog) == 1
      and r.plan["intervals"]["n_intervals"] == 12, str(seen))
check("A 4b: the discrete row is not refined (its members are fitted together)",
      [c["name"] for c in calls] == ["analysis_plan", "analysis_plan"], str([c["name"] for c in calls]))
# a refinement on another row is not possible: the row is the plan's
check("A the next-step schema has no row field", "row" not in A.next_step_schema(o)["properties"])

# ---- B. with R -------------------------------------------------------------------------------------
from bregsurv_agent.rbridge import _run_r  # noqa: E402
from bregsurv_agent import pipeline, external as X  # noqa: E402
from bregsurv_agent.declaration import Declaration  # noqa: E402

spec = json.loads((FX / "F02" / "spec.json").read_text()); d = FX / "F02" / "data"
train, test, rel = str(d / spec["train"]), str(d / spec["test"]), str(d / spec["release_file"])
header = [h.strip().strip('"') for h in Path(train).read_text().splitlines()[0].split(",")]
ext = X.read_external(rel, run_r=_run_r, cohort_columns=header, cohort_outcome=(spec["time_col"], spec["event_col"]))
kw = {k: v for k, v in ext.pipeline_kwargs().items() if k.startswith("external_")}
expr = re.sub(r"[^A-Za-z0-9._]", ".", Path(train).stem)
decl = Declaration(time_col=spec["time_col"], event_col=spec["event_col"], event_value=str(spec["event_value"]),
                   covariates=[h for h in header if h not in (spec["time_col"], spec["event_col"])],
                   source="reply", covariates_time_zero="yes")
decl.test_data_path = test
decl.test_data_expr = re.sub(r"[^A-Za-z0-9._]", ".", Path(test).stem)
prof = _run_r("profile_columns.R", {"data_path": train, "data_expr": expr,
                                    "external_beta_inline": kw["external_beta_inline"]})
card = pipeline.diagnose(train, expr, decl, run_r=_run_r, **kw)
check("B the diagnostics card is computed", card.get("status") == "ok", str(card.get("message")))
opts = A.options_for(decl, kw)
narrow = {"reasoning": "x", "row": "cox", "ties": None,
          "members": [M("internal"), M("external"), M("kl", grid={"from": 0.01, "to": 0.1, "points": 5}),
                      M("kl_lasso", grid={"from": 0.01, "to": 1, "points": 5}), M("internal_lasso")],
          "reason": "a weak release: keep the weights small"}
widen = {"reasoning": "y", "action": "refine",
         "members": [M("kl", grid={"from": 0.01, "to": 100, "points": 12})], "reason": "the kl weight sat at the top"}
prop, calls = scripted([narrow, widen, finish])
fitted = []


def real_fit(pl, reuse):
    res = pipeline.fit_plan(train, expr, decl, pl, reuse=reuse, run_r=_run_r, **kw)
    fitted.append(res)
    return res


loop = A.run_loop(prop, real_fit, declaration=decl, card=card, opts=opts, words="")
check("B two fits: the plan, then the refinement", len(fitted) == 2, str(len(fitted)))
r1 = {c["key"]: c for c in fitted[0]["candidates"]}
r2 = {c["key"]: c for c in fitted[1]["candidates"]}
check("B the intermediate fits read no test file: no held-out numbers",
      all("holdout" not in c for f in fitted for c in f["candidates"]))
check("B the planner was never shown a held-out number", not any("holdout" in c["user"] or "C-index" in c["user"]
                                                                  for c in calls))
check("B the refined member was refitted, the others reused unchanged",
      not r2["kl"].get("reused") and all(r2[k].get("reused") for k in ("internal", "kl_lasso", "internal_lasso"))
      and all(r2[k]["loss"] == r1[k]["loss"] and r2[k]["seconds"] == r1[k]["seconds"]
              for k in ("internal", "kl_lasso", "internal_lasso")))
check("B the same partition across the two calls", fitted[0]["partition"]["folds"] == fitted[1]["partition"]["folds"])
check("B the refitted member ran on its new grid", abs(float(r2["kl"]["eta_grid_max"]) - 100.0) < 1e-6
      and abs(float(r1["kl"]["eta_grid_max"]) - 0.1) < 1e-6, f"{r1['kl'].get('eta_grid_max')} -> {r2['kl'].get('eta_grid_max')}")
# the final run with every row reused equals one run of the final plan with nothing reused
rr_reuse = pipeline.run(train, expr, decl, profile=prof, run_r=_run_r, plan=loop.plan, reuse=loop.reuse,
                        plan_steps=loop.steps, **kw)
rr_fresh = pipeline.run(train, expr, decl, profile=prof, run_r=_run_r, plan=loop.plan, **kw)
cr = {c["key"]: c for c in rr_reuse.candidates["candidates"]}
cf = {c["key"]: c for c in rr_fresh.candidates["candidates"]}
same = all(abs((cr[k].get("loss") or 0) - (cf[k].get("loss") or 0)) < 1e-9
           and (cr[k].get("eta") == cf[k].get("eta") or abs(float(cr[k]["eta"]) - float(cf[k]["eta"])) < 1e-9)
           for k in cf)
check("B the merged table equals one fresh run of the final plan, member by member", same,
      str({k: (cr[k].get("loss"), cf[k].get("loss")) for k in cf}))
check("B ... the same selection and coefficients",
      rr_reuse.candidates["selected"]["key"] == rr_fresh.candidates["selected"]["key"]
      and max(abs(a["beta_selected"] - b["beta_selected"]) for a, b in
              zip(rr_reuse.candidates["coefficients"], rr_fresh.candidates["coefficients"])) < 1e-9)
check("B the final run scores every member on the test file, reused ones included",
      all(c.get("holdout") for c in rr_reuse.candidates["candidates"] if c["status"] == "ok")
      and abs(cr[rr_fresh.candidates["selected"]["key"]]["holdout"]["cindex"]
              - cf[rr_fresh.candidates["selected"]["key"]]["holdout"]["cindex"]) < 1e-9)
check("B the trace keeps the planner's steps and the units spent",
      rr_reuse.provenance["plan"]["units_spent"] == sum(s["units"] for s in loop.steps if s["step"] == "fit")
      and any(s.get("step") == "next" for s in rr_reuse.provenance["plan"]["steps"]))
check("B the plan's hash is the same with or without reuse", rr_reuse.config_sha256 == rr_fresh.config_sha256)
rep = rr_reuse.report
check("B the report says how the analysis was planned, what it cost, and why",
      "### How the analysis was planned" in rep and "**5** were fitted" in rep
      and "Computing used **7** of **20** cost units" in rep
      and "a weak release: keep the weights small" in rep and "refitted `kl`" in rep, rep[rep.find("## 3."):][:1500])
check("B the report no longer says every admissible method was fitted", "and all of them were fitted" not in rep)
# a reused row from another partition is refused
bad = json.loads(json.dumps(loop.reuse))
f = bad["partition"]["folds"]; f[0], f[1] = f[1], f[0]
if f[0] == f[1]:
    f[0] = (f[0] % 5) + 1
try:
    pipeline.fit_plan(train, expr, decl, {**loop.plan, "members": loop.plan["members"]},
                      reuse={"rows": [r for r in bad["rows"] if r["key"] != "kl"], "partition": bad["partition"]},
                      run_r=_run_r, **kw)
    check("B a reused row scored on another partition is refused", False, "no refusal")
except pipeline.PipelineRefusal as exc:
    check("B a reused row scored on another partition is refused", "different partition" in str(exc.refusals), str(exc.refusals))
# repro.R replays the final plan with no model and no reuse
out = Path(tempfile.mkdtemp(prefix="v4loop_"))
paths = rr_reuse.save(str(out))
env = dict(os.environ, BREGSURV_R_SCRIPTS=str(V4 / "mcp" / "r_scripts"))
p = subprocess.run(["Rscript", paths["repro"], train], cwd=str(out), capture_output=True, text=True,
                   timeout=3600, env=env)
o_ = p.stdout + p.stderr
sel = rr_reuse.candidates["selected"]
mm = re.search(r"selected: (.+?) \(loss ([-\d.eE]+)\)", o_)
check("B repro.R replays the final plan: same partition, same selection, same loss",
      "fold assignment REPRODUCED" in o_ and mm is not None and mm.group(1).strip() == str(sel["label"]).strip()
      and abs(float(mm.group(2)) - float(sel["loss"])) < 5e-6, o_[-500:])

# 4b with R: the planner sets the discrete grid on F18 (monthly follow-up, heavy ties, a baseline hazard)
spec18 = json.loads((FX / "F18" / "spec.json").read_text()); d18 = FX / "F18" / "data"
tr18 = str(d18 / spec18["train"])
h18 = [h.strip().strip('"') for h in Path(tr18).read_text().splitlines()[0].split(",")]
e18 = X.read_external(str(d18 / spec18["release_file"]), run_r=_run_r, cohort_columns=h18,
                      cohort_outcome=(spec18["time_col"], spec18["event_col"]))
kw18 = {k: v for k, v in e18.pipeline_kwargs().items() if k.startswith("external_")}
x18 = re.sub(r"[^A-Za-z0-9._]", ".", Path(tr18).stem)
dc18 = Declaration(time_col=spec18["time_col"], event_col=spec18["event_col"], event_value="1",
                   covariates=[h for h in h18 if h not in (spec18["time_col"], spec18["event_col"])],
                   source="reply", covariates_time_zero="yes")
dc18.sources = {"discrete": "default: continuous time"}
p18 = _run_r("profile_columns.R", {"data_path": tr18, "data_expr": x18,
                                   "external_beta_inline": kw18["external_beta_inline"]})
from bregsurv_agent.declaration import verify  # noqa: E402
def chk18(pl):
    v2 = verify(p18, A.amend_declaration(dc18, pl), tr18, x18, run_r=_run_r,
                external_baseline=kw18.get("external_baseline_inline"))
    return [{"code": "intervals_refused:" + str(r.get("code")), "message": str(r.get("message"))} for r in v2.refusals]
o18 = A.options_for(dc18, kw18)
check("B 4b: F18 offers the discrete row (a baseline hazard, the time scale left open)",
      "discrete" in o18.rows and o18.intervals_open, str(o18.rows))
c18 = pipeline.diagnose(tr18, x18, dc18, run_r=_run_r, **kw18)
prop, calls = scripted([dp(150), dp(12), finish])
lp18 = A.run_loop(prop, lambda pl, ru: pipeline.fit_plan(tr18, x18, A.amend_declaration(dc18, pl), pl, reuse=ru,
                                                          run_r=_run_r, **kw18),
                  declaration=dc18, card=c18, opts=o18, words="", check_intervals=chk18)
probs18 = [p["code"] for s in lp18.steps for p in s.get("problems") or []]
check("B 4b: the gate refuses a grid the data cannot fill, by its own code", any("discrete_horizon" in c for c in probs18),
      str(probs18))
rr18 = pipeline.run(tr18, x18, A.amend_declaration(dc18, lp18.plan), profile=p18, run_r=_run_r, plan=lp18.plan,
                    reuse=lp18.reuse, plan_steps=lp18.steps, **kw18)
check("B 4b: the run is on the discrete row with the planned grid, and its source names the planner",
      str(rr18.candidates["facts"].get("outcome_scale")).startswith("discrete") and rr18.declaration.n_intervals == 12
      and rr18.declaration.sources["discrete"].startswith("planned:")
      and sorted(c["key"] for c in rr18.candidates["candidates"]) == ["discretekl", "external_discrete", "internal_discrete"],
      str(rr18.candidates["facts"]))
check("B 4b: the report says the planner set the grid", "a grid the planner set" in rr18.report)

# ---- C. the app -------------------------------------------------------------------------------------
try:
    import app  # noqa: E402
except Exception as exc:  # gradio missing: C is skipped, not failed
    print(f"SKIP C (app not importable: {type(exc).__name__})")
else:
    plan_c = {"reasoning": "x", "row": "cox", "ties": None,
              "members": [M("internal"), M("external"), M("kl"), M("mahalanobis_lasso")], "reason": "a small plan"}
    prop, calls = scripted([plan_c, finish])
    A.model_proposer = lambda client, model: prop
    h, s, *_ = app.start_session()
    out_c = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) A\n6) yes", h, s,
                              "http://localhost:1/v1", "fake", "", write_prose=False)
    hc, _, sc, cand, *_ = out_c
    keys = sorted(cand["method"]) if cand is not None else []
    check("C the app fits the planned members only", cand is not None and len(cand) == 4, str(keys))
    tr = json.loads(Path(out_c[6]).read_text()) if out_c[6] else {}
    check("C the trace keeps the plan, its reasons and the steps",
          (tr.get("provenance", {}).get("plan", {}).get("plan", {}).get("reason") == "a small plan"
           and tr["provenance"]["plan"].get("steps")), str(tr.get("provenance", {}).get("plan"))[:300])
    acts = [a for a in sc.actions if isinstance(a, dict) and a.get("route") == "analysis_planned"]
    check("C the action log records what was planned and what it cost",
          acts and acts[-1]["members"] == ["internal", "kl", "mahalanobis_lasso", "external"]
          and acts[-1]["units"] == 4, str(acts))
    check("C the card says the models are being planned", "Planning which models to fit" in hc[-2][1])

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
