"""Clinical summary -- what the recommended model gives a clinician (V4).

Peripheral, not part of the analysis. Called from `RunResult.save()` after the four artifacts are
written, like the Kaplan-Meier figure: it fits nothing, selects nothing, calls no language model and
enters neither the approval hash nor the replay. `clinical_summary.R` derives everything from the
recommended model's coefficients (and, on the grouped-time row, its interval baseline), with the
survival probabilities computed by the library. A failure never fails the artifacts: the report then
simply has no clinical section.

What it adds to section 5 of the report, under "For clinical use":

* hazard ratios of the recommended model beside the external model's, per unit as coded;
* every subject's predicted probability of remaining event-free at a few horizons (a CSV);
* risk groups of equal size by predicted risk, with predicted against observed survival and a figure;
* how the same subjects would be grouped by the external model (Cox rows, coefficient releases);
* a risk calculator: the covariate means and the survival at the means.

All of it is apparent -- computed on the data the model was fitted to -- and the section says so.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

NETWORK_KEYS = ("internal_nn", "diskd")
START, END = "<!-- clinical -->", "<!-- /clinical -->"
FILE_BASE = "clinical"


def not_applicable(res: Any) -> Optional[str]:
    """None when a clinical summary can be computed for this run, else why it cannot."""
    dec = res.declaration
    sel = (res.candidates or {}).get("selected") or {}
    if not dec.time_col or not dec.event_col:
        return "a matched sample has no follow-up time to predict over"
    if sel.get("key") in NETWORK_KEYS or not sel.get("beta"):
        return "the recommended model is a neural network, which has no coefficients"
    return None


def payload(res: Any, out_base: Path, n_groups: int = 3) -> Dict[str, Any]:
    c = res.candidates
    sel = c["selected"]
    dec = res.declaration
    discrete = (c.get("facts") or {}).get("outcome_scale") == "discrete intervals"
    ext = {r["variable"]: r["beta_external"] for r in (c.get("coefficients") or [])
           if r.get("covered_by_external") and isinstance(r.get("beta_external"), (int, float))}
    p: Dict[str, Any] = {
        "data_path": res.data_path, "data_expr": res.data_expr,
        "time_col": dec.time_col, "event_col": dec.event_col, "event_value": str(dec.event_value),
        "stratum_col": dec.stratum_col or "", "beta": sel["beta"],
        "row": "discrete" if discrete else "cox",
        "external_beta": ext,
        "selected_is_registry": str(sel.get("key") or "").startswith("external"),
        "n_groups": n_groups, "out_base": str(out_base)}
    if discrete:
        p["gamma"] = sel.get("gamma") or []
        p["edges"] = (c.get("discrete") or {}).get("edges") or []
    return p


# ------------------------------------------------------------------ rendering
def _g(x: Any) -> str:
    if not isinstance(x, (int, float)):
        return "-"
    if abs(x) >= 100:
        return f"{x:,.0f}"          # times and medians: 1,100, never 1.1e+03
    return f"{x:.3g}"


def _pct(x: Any) -> str:
    return "-" if not isinstance(x, (int, float)) else f"{100 * x:.0f}%"


def _table(head: List[str], rows: List[List[str]], align: str) -> List[str]:
    sep = ["---:" if a == "r" else ":---" for a in align]
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join(sep) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out + [""]


def render(cs: Dict[str, Any], beta: Dict[str, float]) -> str:
    """The markdown for section 5's "For clinical use", from clinical_summary.R's result."""
    t = cs["time_col"]
    hz = cs["horizons"]
    mid = cs["middle_horizon"]
    means = (cs.get("calculator") or {}).get("means") or {}
    o: List[str] = [START, "### For clinical use", ""]
    o.append(f"Derived from the recommended model; nothing was refitted or reselected. Time is in the "
             f"units of `{t}`. Every figure below is computed on the data the model was fitted to, so "
             f"it is optimistic: a held-out file gives the honest version.")
    o.append("")

    # hazard ratios
    o.append("**Hazard ratios.** Per one unit of each variable as it is coded in your file. A "
             "coefficient too large to be an effect is not exponentiated.")
    o.append("")
    rows = []
    for h in cs.get("hazard_ratios") or []:
        v = h["variable"]
        rows.append([v, "flagged" if h.get("flagged") else _g(h.get("hr")), _g(h.get("hr_registry")),
                     _g(beta.get(v)), _g(means.get(v)), _g(h.get("sd"))])
    o += _table(["variable", "hazard ratio", "external model's", "coefficient", "mean", "SD"],
                rows, "lrrrrr")

    # predicted survival
    hz_txt = ", ".join(_g(x) for x in hz)
    o.append(f"**Predicted survival.** Every subject's probability of remaining event-free at "
             f"{hz_txt}, with their risk score and risk group, is in `{Path(cs['csv']).name}` "
             f"(rows numbered as in your file).")
    o.append("")

    # risk groups
    groups = cs.get("groups") or []
    o.append(f"**Risk groups.** The cohort divided into {len(groups)} groups of equal size by the "
             f"predicted risk of an event by {_g(mid)}; within each group, the predicted and the "
             f"observed (Kaplan-Meier) proportion event-free.")
    o.append("")
    head = ["group", f"risk by {_g(mid)}", "subjects", "events"]
    head += [f"at {_g(x)}: predicted / observed" for x in hz] + ["median survival"]
    rows = []
    for g in groups:
        r = [g["group"], f"{_pct(g['risk_from'])} to {_pct(g['risk_to'])}", str(g["n"]), str(g["n_events"])]
        r += [f"{_pct(p)} / {_pct(q)}" for p, q in zip(g.get("predicted") or [], g.get("observed") or [])]
        r.append("not reached" if g.get("median_survival") is None else _g(g["median_survival"]))
        rows.append(r)
    o += _table(head, rows, "lrrr" + "r" * len(hz) + "r")
    o.append(f"![Observed survival by predicted risk group]({Path(cs['png']).name})")
    o.append("")

    # against the external model
    rc = cs.get("reclassification")
    if rc:
        labs = rc["groups"]
        o.append(f"**Against the external model.** The same risk thresholds applied to the external "
                 f"model's own prediction for the same subjects (rows), against the recommended "
                 f"model's (columns): {rc['n_moved_up']} of {rc['n']} subjects move to a higher group "
                 f"and {rc['n_moved_down']} to a lower one.")
        o.append("")
        rows = [[f"external: {labs[i]}"] + [str(x) for x in rc["counts"][i]] for i in range(len(labs))]
        o += _table(["", *[f"recommended: {x}" for x in labs]], rows, "l" + "r" * len(labs))

    # risk calculator
    sm = (cs.get("calculator") or {}).get("survival_at_means") or []
    if sm:
        o.append("**Risk calculator.** For a new patient with values x, the probability of remaining "
                 "event-free at time t is S(t)^exp(sum of coefficient x (x - mean)), with the "
                 "coefficients and means of the hazard-ratio table and S(t) the survival at the means:")
        o.append("")
        head = ["stratum" if sm[0].get("stratum") is not None else ""] + [f"S({_g(x)})" for x in hz]
        rows = [[str(s.get("stratum") or "all")] + [_pct(v) for v in s.get("survival") or []] for s in sm]
        o += _table(head, rows, "l" + "r" * len(hz))
    o.append(END)
    return "\n".join(o)


def insert(report_md: str, block: str) -> str:
    """Put the block at the end of section 5, replacing an earlier one."""
    a, b = report_md.find(START), report_md.find(END)
    if a >= 0 and b > a:
        return report_md[:a] + block + report_md[b + len(END):]
    k = report_md.find("\n## 6.")
    return (report_md[:k + 1] + block + "\n\n" + report_md[k + 1:]) if k >= 0 \
        else report_md + "\n\n" + block + "\n"


def attach(res: Any, d: Path, run_r: Callable) -> Dict[str, str]:
    """Compute the summary, write its files beside the report and add its section to report.md.
    Returns the paths written; empty when the summary does not apply or failed."""
    if not_applicable(res):
        return {}
    d = Path(d)
    r = run_r("clinical_summary.R", payload(res, d / FILE_BASE), timeout_s=180)
    if not (isinstance(r, dict) and r.get("status") == "ok"):
        return {}
    beta = {k: float(v) for k, v in (res.candidates["selected"].get("beta") or {}).items()}
    md = d / "report.md"
    rep = md.read_text(encoding="utf-8") if md.is_file() else res.report
    md.write_text(insert(rep, render(r, beta)), encoding="utf-8")
    return {"clinical_csv": r["csv"], "clinical_pdf": r["pdf"], "clinical_png": r["png"]}
