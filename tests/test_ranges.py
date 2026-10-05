"""A covariate RANGE the analyst writes ("x1 to x10", "v11 through v50") is expanded by the
backing check to every column of the file between its endpoints (2026-09-14, found by the hard
request set: the model quoted the two endpoints, both were in the message, and the analysis ran
on two covariates instead of ten with nothing refusing it).

Run: python mcp/test_ranges.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

passed = failed = 0


def check(ok, label, note=""):
    global passed, failed
    passed += bool(ok); failed += not ok
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))


def main():
    from bregsurv_agent import boundary as B
    cols = [f"x{i}" for i in range(1, 11)] + [f"v{i}" for i in range(11, 51)] + ["os_mo", "status2"]
    prof = {"columns": [{"name": c} for c in cols],
            "eligible": {"time": ["os_mo"], "event": ["status2"], "covariate": cols[:50]}}
    r = B._ranges_in("Please use x1 through x10 as the predictors.", cols)
    check(r and r[0][0] == "x1" and r[0][1] == "x10" and len(r[0][2]) == 10, "x1 through x10 -> the ten columns", str(r)[:80])
    check(B._ranges_in("use x1, x2 and x10", cols) == [], "a list of names is not a range")
    check(B._ranges_in("x1 to x99", cols) == [], "an endpoint the file lacks is not a range")
    for phrase in ("x1 to x10", "x1..x10", "x1-x10", "x1 through x10", "x1 until x10"):
        check(len(B._ranges_in(f"take {phrase} please", cols)) == 1, f"'{phrase}' is read as a range")
    r = B._ranges_in("x1 to x10 and v11 to v50", cols)
    check(len(r) == 2 and len(r[1][2]) == 40, "two ranges in one message", str([(a, b, len(m)) for a, b, m in r]))
    # the backing check: the model quoted the endpoints; the check expands them and says so
    msg = "os_mo is the time in months and status2 = 1 is the event. Please use x1 through x10 as the predictors."
    ext = {"time_column": "os_mo", "event_column": "status2", "event_value": "1", "covariate_columns": ["x1", "x10"]}
    backed, unbacked, sources = B._backed_roles_checked(msg, prof, ext)
    got = backed.get("covariates", "").split(", ")
    check(got == cols[:10], "the endpoints the model quoted are expanded to the ten columns", str(got))
    check("range x1 to x10 expanded" in sources.get("covariates", ""), "the source line says the range was expanded", sources.get("covariates"))
    ext2 = dict(ext, covariate_columns=["x1", "x2"])
    backed2, _, sources2 = B._backed_roles_checked("os_mo is time, status2 = 1. Use x1, x2.", prof, ext2)
    check(backed2.get("covariates") == "x1, x2" and sources2.get("covariates") == "quoted", "no range in the message: nothing is expanded")
    # a range with one endpoint the file lacks: the name is kept, to be refused by name
    check(B._broken_range_endpoints("x1 to x10 and v11 to v51", cols) == ["v51"],
          "the misnamed endpoint of a broken range is found", str(B._broken_range_endpoints("x1 to x10 and v11 to v51", cols)))
    check(B._broken_range_endpoints("x1 to x10 and v11 to v50", cols) == [], "a complete range has no broken endpoint")
    msg3 = "os_mo is the time and status2 = 1 is the event. Please use all fifty predictors, x1 to x10 and v11 to v51."
    ext3 = dict(ext, covariate_columns=["x1", "x10", "v11"])
    backed3, _, _ = B._backed_roles_checked(msg3, prof, ext3)
    got3 = backed3.get("covariates", "").split(", ")
    check("v51" in got3 and got3[:10] == cols[:10], "the broken range keeps its missing endpoint for the refusal by name", str(got3)[:120])
    from bregsurv_agent.declaration import parse_reply, DeclarationError
    prof2 = dict(prof, n_rows=100, n_columns=len(cols),
                 columns=[{"name": c, "type": "numeric", "can_be_covariate": c not in ("os_mo", "status2"),
                           "can_be_time": c == "os_mo", "can_be_event": c == "status2", "n_distinct": 5,
                           "values": (["0", "1"] if c == "status2" else None)} for c in cols])
    try:
        parse_reply(prof2, {"time": "os_mo", "event": "status2", "event_value": "1",
                            "covariates": backed3["covariates"], "time_zero": "yes"})
        check(False, "the declaration with v51 is refused by name", "it was accepted")
    except DeclarationError as exc:
        check("v51" in str(exc), "the declaration with v51 is refused by name", str(exc)[:100])
    except Exception as exc:
        check(False, "the declaration with v51 is refused by name", f"{type(exc).__name__}: {exc}"[:120])
    # zero-padded names: "lab_01 to lab_40" (hard set H004)
    labs = [f"lab_{i:02d}" for i in range(1, 41)] + ["followup_days", "died"]
    rl = B._ranges_in("lab_01 to lab_40 are the lab values", labs)
    check(rl and rl[0][0] == "lab_01" and len(rl[0][2]) == 40, "a zero-padded range is read as written", str(rl)[:60])
    # "everything else, including site": the written name beside the unwritten rest
    prof4 = {"columns": [{"name": c} for c in ["age", "bmi", "egfr", "followup_days", "died", "site"]],
             "eligible": {"time": ["followup_days"], "event": ["died"], "covariate": ["age", "bmi", "egfr", "site"]}}
    msg4 = "Follow-up is followup_days, died is 1 for death. Everything else, including the site column, should go in as a predictor."
    ext4 = {"time_column": "followup_days", "event_column": "died", "event_value": "1", "covariate_columns": ["age", "bmi", "egfr", "site"]}
    b4, u4, s4 = B._backed_roles_checked(msg4, prof4, ext4)
    check(b4.get("covariates") == "B" and u4.get("covariates") == ["age", "bmi", "egfr"] and "every usable column" in s4.get("covariates", ""),
          "'everything else, including site' -> the every-usable-column preset, the unwritten names on record", str(b4.get("covariates")) + " / " + str(s4.get("covariates"))[:60])
    msg6 = "Follow-up is followup_days, died is 1 for death. All other columns are predictors; add recipient_cmv_status as a covariate."
    ext6 = dict(ext4, covariate_columns=["age", "bmi", "egfr", "site", "recipient_cmv_status"])
    b6, u6, _ = B._backed_roles_checked(msg6, prof4, ext6)
    check("recipient_cmv_status" in (b6.get("covariates") or "") and b6.get("covariates") != "B",
          "a ghost column the analyst wrote is kept for the refusal by name, not swallowed by the preset", str(b6.get("covariates")))
    msg5 = "Follow-up is followup_days, died is 1 for death. Use site as the predictor."
    b5, u5, _ = B._backed_roles_checked(msg5, prof4, ext4)
    check(b5.get("covariates") == "site" and u5.get("covariates") == ["age", "bmi", "egfr"],
          "without such a phrase the written name stands alone and the rest is dropped", str(b5.get("covariates")))
    print(f"\nRESULT: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
