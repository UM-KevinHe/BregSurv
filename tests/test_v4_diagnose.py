"""V4 work item 3: the transfer-diagnostics card, on seven synthetic fixtures of the synth200 benchmark.

Declarations are built the way the benchmark's reference builds them (abl_golden.py): the heuristic release
reader, all non-outcome columns as covariates, the fixture's own event value. Checks that the card carries
what the planner needs and that its numbers point the right way where the fixture's truth says which way
(an external model close to the truth against one far from it). Needs R; no model.
  python mcp/test_v4_diagnose.py
"""
import json, re, sys
from pathlib import Path

V4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V4))
from bregsurv_agent.rbridge import _run_r  # noqa: E402
from bregsurv_agent import pipeline, external as X  # noqa: E402
from bregsurv_agent.declaration import Declaration  # noqa: E402

FX = Path("/home/ybshao/jobs/synth200/fixtures")
OUT = Path("/home/ybshao/jobs/v4/diagnose_cards"); OUT.mkdir(parents=True, exist_ok=True)
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def data_expr_for(path):
    return re.sub(r"[^A-Za-z0-9._]", ".", Path(path).stem)


def card_for(fid):
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
    kw = ext.pipeline_kwargs() if ext is not None else {}
    kw = {k: v for k, v in kw.items() if k.startswith("external_")}
    card = pipeline.diagnose(train, data_expr_for(train), decl, run_r=_run_r, **kw)
    (OUT / f"{fid}.json").write_text(json.dumps(card, indent=1))
    return spec, card


cards = {}
for fid in ("F01", "F02", "F04", "F05", "F07", "F18", "F23"):
    try:
        cards[fid] = card_for(fid)
    except Exception as e:  # noqa: BLE001
        cards[fid] = (None, {"status": "error", "message": f"{type(e).__name__}: {e}"})
    spec, c = cards[fid]
    check(f"{fid} the card is produced", c.get("status") == "ok", c.get("message", ""))

ok = {k: v[1] for k, v in cards.items() if v[1].get("status") == "ok"}

if "F01" in ok:
    c = ok["F01"]
    check("F01 facts: n, events, p, events per parameter", all(k in c["facts"] for k in ("n", "n_events", "p", "events_per_parameter")))
    check("F01 outcome: tie fraction and the time grid", "tie_fraction" in c["outcome"] and "coarse" in c["outcome"]["time_grid"])
    check("F01 outcome: whether the exact tie correction can be computed",
          isinstance(c["outcome"].get("exact_ties", {}).get("feasible"), bool), str(c["outcome"].get("exact_ties")))
    check("F01 every released term is compared", len(c["terms"]) == c["external"]["n_covered"] > 0)
    check("F01 the release's calibration and both endpoints' CV losses",
          c["external"].get("calibration", {}).get("slope") is not None
          and c["external"].get("cv_loss_released_unchanged") is not None
          and c["external"].get("cv_loss_target_only_ridge") is not None)
if "F01" in ok and "F02" in ok:
    a, b = ok["F01"]["external"], ok["F02"]["external"]
    check("F01 (close) vs F02 (far): the far release is calibrated worse on the cohort",
          abs(a["calibration"]["slope"] - 1) < abs(b["calibration"]["slope"] - 1),
          f"slopes {a['calibration']['slope']} vs {b['calibration']['slope']}")
    check("F01 vs F02: the far release disagrees more with the target-only fit",
          a["heterogeneity"]["median_abs_difference_per_sd"] < b["heterogeneity"]["median_abs_difference_per_sd"]
          or a["heterogeneity"]["n_sign_disagreements"] < b["heterogeneity"]["n_sign_disagreements"],
          f"{a['heterogeneity']} vs {b['heterogeneity']}")
    check("F02 (coded 1/2, far): the released model does worse than the target-only fit in CV, F01 does not",
          b["cv_loss_released_unchanged"] > b["cv_loss_target_only_ridge"]
          and a["cv_loss_released_unchanged"] <= a["cv_loss_target_only_ridge"] + 0.05,
          f"F01 {a.get('cv_loss_released_unchanged')}/{a.get('cv_loss_target_only_ridge')}  F02 {b.get('cv_loss_released_unchanged')}/{b.get('cv_loss_target_only_ridge')}")
if "F04" in ok:
    m = ok["F04"]["external"].get("matrix") or {}
    check("F04 (covariance): the matrix's condition number is reported", m.get("condition_number") is not None and m.get("n", 0) > 0)
if "F05" in ok:
    r = ok["F05"].get("records") or {}
    check("F05 (records): external size, events and the covariate shift",
          r.get("n_external", 0) > 0 and r.get("max_abs_standardised_mean_difference") is not None)
    check("F05 (records): the external cohort's own fit is compared term by term", len(ok["F05"]["terms"]) > 0)
if "F07" in ok:
    c = ok["F07"]
    check("F07 (matched): sets and one case per set", c["outcome"].get("sets_with_one_case") == c["outcome"].get("n_sets"))
    check("F07 (matched): the release's slope by conditional likelihood", c["external"].get("calibration", {}).get("slope") is not None)
if "F18" in ok:
    c = ok["F18"]
    check("F18 (baseline, months): the baseline is reported and the time grid is coarse",
          (c.get("baseline") or {}).get("available") is True and c["outcome"]["time_grid"]["coarse"] is True)
if "F23" in ok:
    c = ok["F23"]
    check("F23 (no release): form none, no terms, nothing invented", c["external"]["form"] == "none" and c["terms"] == [])

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
