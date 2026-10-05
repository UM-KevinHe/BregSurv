"""M2 -- comparing two runs of the same session, by the harness.

"Run it with the one-year and the three-year model and tell me the
difference", "run it again without bmi and tell me what changed": the second
half of each is a comparison of two fitted objects, and it is computed here,
by the harness, with every number taken from the two `RunResult`s. The model
may then explain the comparison under boundary 2's rules -- named references
only, no digit -- from the reference set `references` builds, which
suffixes every reference of each run with `_a` / `_b` and adds the
differences.

What is compared: the configuration (external release, covariates, event,
time), every candidate's cross-validated loss side by side, the selected
member of each run, and the selected members' coefficients variable by
variable. What is NOT done: no test, no interval, no judgement of which run
is "better" beyond restating each run's own selection -- the two losses are
on the same scale only when the declaration and the partition are the same,
and the text says so when they are not.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import report_v3


def _cfg(res: Any) -> Dict[str, Any]:
    d = res.declaration
    prov = res.provenance or {}
    ext = (prov.get("external") or {})
    return {
        "external": ext.get("file") or ("none" if not res.external_beta_inline
                                        and not res.external_beta_expr else "inline"),
        "external_form": res.candidates["facts"].get("external_form"),
        "time": d.time_col, "event": f"{d.event_col} = {d.event_value}",
        "covariates": list(d.covariates or []),
        "seed": res.candidates["partition"].get("seed"),
        "nfolds": res.candidates["partition"].get("nfolds"),
        "sha256": res.config_sha256,
    }


def compare_runs(a: Any, b: Any, label_a: str = "run A",
                 label_b: str = "run B") -> Dict[str, Any]:
    """Two RunResults -> {config, candidates, selected, coefficients, text}."""
    ca, cb = _cfg(a), _cfg(b)
    same_partition = (ca["seed"], ca["nfolds"], ca["time"], ca["event"],
                      sorted(ca["covariates"])) == (
                      cb["seed"], cb["nfolds"], cb["time"], cb["event"],
                      sorted(cb["covariates"]))
    by_a = {c["key"]: c for c in a.candidates["candidates"]}
    by_b = {c["key"]: c for c in b.candidates["candidates"]}
    keys = list(dict.fromkeys(list(by_a) + list(by_b)))
    rows = []
    for k in keys:
        x, y = by_a.get(k), by_b.get(k)
        la, lb = (x or {}).get("loss"), (y or {}).get("loss")
        rows.append({"key": k, "label": (x or y or {}).get("label", k),
                     "loss_a": la, "loss_b": lb,
                     "delta": (None if la is None or lb is None else lb - la),
                     "status_a": (x or {}).get("status"), "status_b": (y or {}).get("status")})
    sel_a, sel_b = a.candidates["selected"], b.candidates["selected"]
    coef_a = {c["variable"]: c for c in a.candidates.get("coefficients", [])}
    coef_b = {c["variable"]: c for c in b.candidates.get("coefficients", [])}
    variables = list(dict.fromkeys(list(coef_a) + list(coef_b)))
    coefs = []
    for v in variables:
        pa, pb = (coef_a.get(v) or {}).get("beta_selected"), (coef_b.get(v) or {}).get("beta_selected")
        coefs.append({"variable": v, "beta_a": pa, "beta_b": pb,
                      "delta": (None if pa is None or pb is None else pb - pa)})
    out = {"labels": (label_a, label_b), "config": {"a": ca, "b": cb},
           "same_partition": same_partition, "candidates": rows,
           "selected": {"a": sel_a, "b": sel_b}, "coefficients": coefs}
    out["text"] = render(out)
    return out


def _f(x: Any, nd: int = 4) -> str:
    return "" if x is None else f"{float(x):.{nd}f}"


def render(cmp: Dict[str, Any]) -> str:
    la, lb = cmp["labels"]
    ca, cb = cmp["config"]["a"], cmp["config"]["b"]
    out = [f"## Comparison: {la} vs {lb}", ""]
    diffs = [k for k in ("external", "external_form", "time", "event", "covariates")
             if ca[k] != cb[k]]
    if diffs:
        out.append("What differs in the configuration: " + ", ".join(
            f"{k} ({ca[k]} -> {cb[k]})" if k != "covariates" else
            f"covariates (+{sorted(set(cb[k]) - set(ca[k]))} -{sorted(set(ca[k]) - set(cb[k]))})"
            for k in diffs) + ".")
    else:
        out.append("The two runs have the same configuration.")
    if cmp["same_partition"]:
        out.append("Both runs used the same cross-validation partition and the same "
                   "declaration, so their losses are on the same scale.")
    else:
        out.append("The two runs differ in declaration or partition, so a loss in one is "
                   "not directly comparable to a loss in the other; compare within a run, "
                   "and compare the selections.")
    out += ["", f"| method | loss, {la} | loss, {lb} | difference |", "|---|---|---|---|"]
    for r in cmp["candidates"]:
        mark = ""
        if r["key"] == cmp["selected"]["a"]["key"]:
            mark += f" <- selected in {la}"
        if r["key"] == cmp["selected"]["b"]["key"]:
            mark += f" <- selected in {lb}"
        out.append(f"| {r['label']}{mark} | {_f(r['loss_a'])} | {_f(r['loss_b'])} | {_f(r['delta'])} |")
    out += ["", f"Selected: {la} -> {cmp['selected']['a']['label']}; "
                f"{lb} -> {cmp['selected']['b']['label']}."]
    if cmp["coefficients"]:
        out += ["", f"| variable | selected coefficient, {la} | selected coefficient, {lb} | difference |",
                "|---|---|---|---|"]
        for c in cmp["coefficients"]:
            out.append(f"| {c['variable']} | {_f(c['beta_a'])} | {_f(c['beta_b'])} | {_f(c['delta'])} |")
    return "\n".join(out)


def references(a: Any, b: Any) -> Dict[str, Any]:
    """The closed reference set for a model explanation of the comparison:
    every reference of each run, suffixed, plus the differences."""
    ra, rb = report_v3.build_references(a.candidates), report_v3.build_references(b.candidates)
    refs: Dict[str, Any] = {}
    for k, v in ra.items():
        refs[f"{k}_a"] = v
    for k, v in rb.items():
        refs[f"{k}_b"] = v
    for k in ("loss_best", "loss_internal", "loss_external", "n_candidates"):
        va, vb = ra.get(k), rb.get(k)
        refs[f"{k}_delta"] = (None if va is None or vb is None else vb - va)
    refs["same_selection"] = ra.get("selected_label") == rb.get("selected_label")
    return refs
