"""Fold model-written rewrites into the FEW-SHOT BANK, keeping only the safe ones.

The bank is generated stiff by `generate_corpus.py --bank`, rewritten
into prose by a language model that sees the id, the request and the clause
each role was referred to by -- never the key -- and merged here under rules
stricter than the corpus's, because a bank item is also an EXAMPLE the model
will imitate:

  1. a column name appears in the request iff the key names it (the corpus rule);
  2. every returned span is a substring of the rewritten request (case-insensitive);
  3. a NAMED role's span contains that column's name (in an accepted spelling);
  4. a DESCRIBED role's span names no column of the profile at all;
  5. the event-value span still writes the value;
  6. no span is empty when the templated item had one, and none is added.

A rewrite that fails any rule is DISCARDED and the templated original kept.
The example (`example`) is rebuilt from the accepted spans so the evidence
fields are verbatim spans of the text the model will actually read.

    python eval/merge_bank.py --glob 'para/bank_para_*.json'
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from verify_corpus import check_item, profile_of  # noqa: E402
from generate_corpus import bank_example, BANK_OUT  # noqa: E402
from bregsurv_agent import textmatch  # noqa: E402


def check_spans(item: Dict[str, Any], request: str, spans: Dict[str, Any]) -> List[str]:
    p = profile_of(item)
    gt = item["expect"]
    low = request.lower()
    problems: List[str] = []
    for role in ("time", "event", "event_value", "covariates"):
        had = item["spans"].get(role) is not None
        sp = spans.get(role)
        if had and not sp:
            problems.append(f"{role}: span missing")
            continue
        if not had and sp:
            problems.append(f"{role}: span added where the original had none")
            continue
        if not had:
            continue
        sp = str(sp).strip()
        if sp.lower() not in low:
            problems.append(f"{role}: span is not a substring of the request")
            continue
        named = {"time": gt["time_column"], "event": gt["event_column"]}.get(role)
        if role in ("time", "event"):
            if named:
                if not textmatch.mentions(sp, named, p["columns"]):
                    problems.append(f"{role}: span does not carry {named!r}")
            else:
                if textmatch.names_mentioned(sp, p["columns"]):
                    problems.append(f"{role}: a described role's span names a column")
        elif role == "event_value":
            if gt["event_value"] is not None and not textmatch.value_mentioned(sp, gt["event_value"]):
                problems.append("event_value: span does not write the value")
        elif role == "covariates":
            cov = gt["covariate_columns"]
            if cov:
                for c in cov:
                    if not textmatch.mentions(sp, c, p["columns"]):
                        problems.append(f"covariates: span does not carry {c!r}")
                        break
            elif textmatch.names_mentioned(sp, p["columns"]):
                problems.append("covariates: a described/set-valued span names a column")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(BANK_OUT))
    ap.add_argument("--glob", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = json.loads(Path(a.bank).read_text(encoding="utf-8"))
    items: List[Dict[str, Any]] = d["items"]
    by_id = {it["id"]: it for it in items}
    rewrites: Dict[str, Dict[str, Any]] = {}
    for f in sorted(glob.glob(a.glob)):
        try:
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ! {Path(f).name}: unreadable ({exc})")
            continue
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        for r in rows:
            if isinstance(r, dict) and r.get("id") in by_id and r.get("request"):
                rewrites[r["id"]] = r
    print(f"{len(rewrites)} rewrites for {len(items)} items")

    accepted = rejected = 0
    why = Counter()
    for it in items:
        r = rewrites.get(it["id"])
        if r is None:
            continue
        cand = dict(it, request=str(r["request"]).strip())
        ok, problems = check_item(cand)
        spans = r.get("spans") or {}
        problems = problems + check_spans(it, cand["request"], spans)
        if problems:
            rejected += 1
            why[problems[0].split(":")[0]] += 1
            continue
        it["request"] = cand["request"]
        it["spans"] = {k: (str(spans.get(k)).strip() if spans.get(k) else None)
                       for k in ("time", "event", "event_value", "covariates")}
        it["example"] = bank_example(profile_of(it), it["expect"], it["spans"],
                                     it["axes"]["reference"])
        it["source"] = "generated+rewritten"
        accepted += 1
    print(f"accepted {accepted}, rejected {rejected} (templated original kept)")
    for k, n in why.most_common():
        print(f"  rejected on {k}: {n}")
    # every item, rewritten or not, must still pass every rule
    bad = 0
    for it in items:
        ok, problems = check_item(it)
        problems = problems + check_spans(it, it["request"], it["spans"])
        if problems:
            bad += 1
            print("  !! ", it["id"], problems[0])
    print(f"final bank: {len(items) - bad}/{len(items)} items pass every rule; "
          f"{sum(1 for i in items if i['source'] == 'generated+rewritten')} model-written")
    d["items"] = items
    out = a.out or a.bank
    Path(out).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    print("written", out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
