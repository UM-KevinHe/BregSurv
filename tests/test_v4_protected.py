"""V4 protected core when the cohort has more covariates than events: the protected
target-only member is the lasso one; otherwise the unpenalized one, as before."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bregsurv_agent import plan as P, analyst as A
ok = 0; bad = 0
def check(name, cond):
    global ok, bad
    print(("PASS " if cond else "FAIL ") + name); ok += bool(cond); bad += (not cond)
keys = P.admissible_keys("cox", "full cohort", "coefficients alone", False)
check("default core = internal + external", P.protected_core("cox", keys) == ["internal", "external"])
check("p > events core = internal_lasso + external", P.protected_core("cox", keys, True) == ["internal_lasso", "external"])
tk = P.admissible_keys("cox_ties", "full cohort", "coefficients alone", False)
check("ties row p > events", P.protected_core("cox_ties", tk, True)[0] == "internal_lasso_ties")
dk = P.admissible_keys("discrete", "full cohort", "coefficients alone", True)
check("discrete row unchanged", P.protected_core("discrete", dk, True)[0] == "internal_discrete")
covs = ["a", "b"]
plan = {"row": "cox", "members": [{"key": "internal_lasso"}, {"key": "kl_lasso"}, {"key": "external"}]}
_, pr, _ = P.validate(plan, design="full cohort", external_form="coefficients alone", has_baseline=False,
                      covariates=covs, covered=covs, penalise_target=True)
check("plan without unpenalized internal accepted when p > events", not pr)
_, pr, _ = P.validate(plan, design="full cohort", external_form="coefficients alone", has_baseline=False,
                      covariates=covs, covered=covs)
check("same plan refused otherwise", any(x["code"] == "protected_member_missing" for x in pr))
check("card rule", A.penalise_target({"facts": {"p": 48, "n_events": 32}}) and
      not A.penalise_target({"facts": {"p": 20, "n_events": 100}}) and not A.penalise_target({}))

# p >= n: the unpenalized members leave the set, on every row the cox design has
from bregsurv_agent import pipeline as PL
full = PL.derive_candidate_keys("full cohort", "coefficients alone")
w = PL.derive_candidate_keys("full cohort", "coefficients alone", wide=True)
check("wide set = full set minus the unpenalized members", w == [k for k in full if k not in PL.UNPENALIZED] and "external" in w)
wc = PL.derive_candidate_keys("full cohort", "coefficients and covariance", wide=True)
check("wide covariance set keeps ridge and lasso of every family", all(k in wc for k in ("euclidean_ridge", "euclidean_lasso", "mahalanobis_lasso", "kl_ridge")) and not any(k in wc for k in PL.UNPENALIZED))
check("wide records set", PL.derive_candidate_keys("full cohort", "individual-level data", wide=True) == ["internal_lasso", "indi_lasso", "indi_ridge", "internal_ridge"])
check("ties row follows", P.admissible_keys("cox_ties", "full cohort", "coefficients alone", False, wide=True) == [k if k == "external" else k + "_ties" for k in w])
import csv, tempfile, os
from bregsurv_agent.declaration import Declaration
td = tempfile.mkdtemp(); f = os.path.join(td, "x.csv")
with open(f, "w", newline="") as fh:
    wr = csv.writer(fh); wr.writerow(["time", "event"] + [f"g{i}" for i in range(30)])
    for i in range(20): wr.writerow([i + 1, i % 2] + [0] * 30)
d = Declaration(time_col="time", event_col="event", event_value="1", covariates=[f"g{i}" for i in range(30)], source="reply")
check("wide_design reads p >= n off the file", PL.wide_design(f, d) and not PL.wide_design(f, Declaration(time_col="time", event_col="event", event_value="1", covariates=["g1"], source="reply")))
print(f"{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
