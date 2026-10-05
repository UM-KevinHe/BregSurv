"""Check that rewriting the corpus into natural prose did not change its meaning.

WHY THIS IS DETERMINISTIC AND NOT ANOTHER MODEL. The rewrite is done by a
language model, and the failure it is prone to is a HELPFUL one: an item whose
whole purpose is that no column is named ("adjust for the baseline variables")
gets rewritten as "adjust for age, bmi and egfr", because that is what a helpful
writer does. If that slips through, the item silently stops testing the thing it
exists to test -- and the corpus reports a better score for it.

The rule that catches this is exact and needs no judgement:

    A COLUMN NAME MAY APPEAR IN THE REQUEST IF AND ONLY IF THE GROUND TRUTH
    NAMES IT.

Leaks and drops are both violations of the same rule, from opposite directions.

One implementation detail that is not optional: names are matched LONGEST FIRST
and masked out as they are found. Without that, `age` matches inside `donor_age`
(there is a word boundary before "age" in "donor age") and every item mentioning
the donor's age looks like it also mentions the recipient's.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from profiles import ALL_PROFILES  # noqa: E402
from bank_profiles import BANK_PROFILES  # noqa: E402


# ONE predicate for the corpus and the harness. The matcher moved to
# `bregsurv_agent/textmatch.py` so the standard the corpus is
# built on is the standard boundary 1 enforces at runtime; the names below
# are kept so every caller in eval/ is unchanged.
sys.path.insert(0, str(HERE.parent))
from bregsurv_agent.textmatch import names_mentioned, variants as _variants  # noqa: E402,F401


def profile_of(item: Dict[str, Any]) -> Dict[str, Any]:
    """The corpus profiles first, then the few-shot bank's."""
    pid = item["profile"]
    return ALL_PROFILES[pid] if pid in ALL_PROFILES else BANK_PROFILES[pid]


def check_item(item: Dict[str, Any]) -> Tuple[bool, List[str]]:
    p = profile_of(item)
    gt = item["expect"]
    req = item["request"]

    expected = set()
    for k in ("time_column", "event_column"):
        if gt.get(k):
            expected.add(gt[k])
    for c in (gt.get("covariate_columns") or []):
        if c in p["columns"]:
            expected.add(c)

    mentioned = set(names_mentioned(req, p["columns"]))
    problems = []
    for missing in sorted(expected - mentioned):
        problems.append(f"ground truth names {missing!r} but the request no "
                        f"longer does")
    for leaked in sorted(mentioned - expected):
        problems.append(f"the request names {leaked!r}, which the ground truth "
                        f"does not -- the rewrite supplied a column the original "
                        f"deliberately withheld")

    # a ghost covariate is not in the profile, so the scan above cannot see it
    for c in (gt.get("covariate_columns") or []):
        if c not in p["columns"] and c.lower() not in req.lower():
            problems.append(f"ground truth names {c!r} (absent from the file) "
                            f"but the request does not")
    return (not problems), problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(HERE / "corpus.json"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    d = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    items = d["items"]
    bad = []
    for it in items:
        ok, problems = check_item(it)
        if not ok:
            bad.append((it, problems))

    print(f"{len(items) - len(bad)}/{len(items)} items preserve their meaning")
    if bad and not a.quiet:
        by_axis: Dict[str, int] = {}
        for it, _ in bad:
            k = f"{it['axes']['stated']}/{it['axes']['reference']}"
            by_axis[k] = by_axis.get(k, 0) + 1
        print("\nwhere the failures are:")
        for k, n in sorted(by_axis.items(), key=lambda kv: -kv[1]):
            print(f"  {k:26} {n}")
        print("\nfirst five:")
        for it, problems in bad[:5]:
            print(f"\n  {it['id']}  {it['template_id']}")
            print(f"    request: {it['request'][:170]}")
            for pr in problems:
                print(f"    !! {pr}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
