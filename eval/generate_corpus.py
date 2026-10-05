"""Generate the elicitation corpus: sentences an analyst might write, with the
correct reading of each one worked out at the same time.

GROUND TRUTH IS BUILT WITH THE SENTENCE, NOT ANNOTATED AFTER IT. That is the
whole reason this file exists. Hand-annotating 500 sentences would be slow,
unreviewable, and -- worse -- would put a second judgement call between the
corpus and the truth. Here the generator decides "this sentence names the
follow-up column" and then writes a sentence that does, so the key cannot
disagree with the item.

WHAT IS BEING MEASURED, and it is narrower than it looks. Boundary 1 does ONE
job: report which column the analyst named for which role. It is a quoting task,
not a modelling one. So the corpus varies how a person might write, and asks
whether the quoting survives it.

THE AXES, and why each one is here:

  profile        six column lists (see profiles.py)
  stated         which of the four roles the sentence actually mentions. The
                 items that mention FEWER are the important ones: the correct
                 answer is null, and a guess is the worst failure this system
                 has, because everything downstream inherits it silently.
  reference      how a role is pointed at -- the exact column name, a loosened
                 form ("donor age" for `donor_age`), a description with no name
                 at all, or a set-valued phrase ("everything the registry
                 covers"). The last two have no honest answer, so null is right.
  perturbation   something in the sentence that must NOT move the answer: a
                 false claim about the study design, a false claim about the
                 event coding, an external model that does not exist, sixty
                 words of irrelevant clinical context, a named column the file
                 does not contain.
  register       terse / narrative / bulleted / email / clinical note. Held
                 separate from the rest because it should change NOTHING, and
                 the point of five of them is to show that it does not.

DELIBERATE CHOICES A READER WILL WANT NAMED:

* A column the file does not have is QUOTED, not dropped. The model's job is to
  report what was said; `declaration._resolve_covariates` then refuses it by
  name. Silently dropping it would let the model overrule the analyst with no
  trace anywhere.
* A false claim about the study design must not move the extraction, and cannot:
  there is no design field in the schema to put it in. The item exists to prove
  the claim does not leak into the other fields.
* A false claim about the event CODING is quoted faithfully. The model is not
  asked to check it against the data -- the consequence card does that, with an
  event count the analyst can contradict at a glance.

Usage:
    python generate_corpus.py --out corpus.json --scale 500
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from profiles import ALL_PROFILES  # noqa: E402
from bank_profiles import BANK_PROFILES  # noqa: E402

# ---------------------------------------------------------------- the axes
STATED_SETS = {
    "all":         ("time", "event", "event_value", "covariates"),
    "no_cov":      ("time", "event", "event_value"),
    "no_outcome":  ("covariates",),
    "no_value":    ("time", "event", "covariates"),
    "time_only":   ("time",),
    "nothing":     (),
}

REFERENCE_STYLES = ("exact", "loose", "described", "set_valued")

PERTURBATIONS = ("none", "false_design", "false_coding", "false_external",
                 "padding", "ghost_column")

REGISTERS = ("terse", "narrative", "bulleted", "email", "note")

# Every word here is checked against every profile's column list by the
# self-check in build. "the case notes were re-abstracted" was the first
# draft and it collides with the `case` column in the matched profile -- which
# would have turned sixty words of irrelevance into an accidental mention of
# the outcome column.
_PADDING = (
    "The cohort was assembled from our transplant service over an eleven-year "
    "period and the records were re-abstracted by two coordinators, so the "
    "measurements are about as clean as we are going to get. We presented some "
    "of this at a regional meeting already and the feedback was mostly about "
    "how we handled the immunosuppression protocol changes."
)


def _loosen(name: str) -> str:
    """`donor_age` -> `donor age`. What a person types when not copying."""
    return name.replace("_", " ")


def _describe(role: str, profile_id: str) -> str:
    """Point at a role WITHOUT naming a column.

    These phrasings are load-bearing and the obvious ones are wrong. The
    first draft said "whether the patient died" -- and the kidney profile's
    outcome column is called `died`, so an item whose entire purpose was that no
    column is named was naming one. The self-check in build catches this class
    now; the wording below is what survives it across all six profiles.
    """
    return {
        "time": "how long each person was observed",
        "event": "whether the endpoint was reached",
        "covariates": "the usual set of baseline measurements",
    }[role]


# --------------------------------------------------- rendering one sentence
def _phrases(p: Dict[str, Any], stated, style: str, perturbation: str):
    """Return (phrases, ground truth) for one template instance.

    The two are produced together and cannot disagree; that is the point.
    """
    t = p["truth"]
    gt: Dict[str, Any] = {"time_column": None, "event_column": None,
                          "event_value": None, "covariate_columns": None}
    ph: List[str] = []
    # the clause each role was referred to by, for the few-shot bank:
    # a named role's clause carries the name, a described role's clause carries
    # the description, an unstated role has none
    spans: Dict[str, Optional[str]] = {"time": None, "event": None,
                                       "event_value": None, "covariates": None}

    # `set_valued` is a COVARIATE style and nothing else. It used to fall
    # through to the descriptive branch here too, which meant an item labelled
    # `all.set_valued` named no column at all -- a bucket whose name said
    # "everything was stated" while its ground truth was null throughout. The
    # axis is meant to isolate ONE field, so time and event stay exact.
    _named = style in ("exact", "loose", "set_valued")
    _loose = style == "loose"

    if "time" in stated and t["time"] is not None:
        if _named:
            nm = _loosen(t["time"]) if _loose else t["time"]
            ph.append(f"follow-up time is in {nm}")
            gt["time_column"] = t["time"]
        else:
            # a description with no column named: there is no honest answer
            ph.append(f"we know {_describe('time', p['id'])}")
        spans["time"] = ph[-1]

    if "event" in stated:
        if _named:
            nm = _loosen(t["event"]) if _loose else t["event"]
            ph.append(f"{nm} marks the outcome")
            gt["event_column"] = t["event"]
        else:
            ph.append(f"we know {_describe('event', p['id'])}")
        spans["event"] = ph[-1]

    if "event_value" in stated and gt["event_column"] is not None:
        ph.append("and it is 1 when the event happened")
        gt["event_value"] = "1"
        spans["event_value"] = ph[-1]

    if "covariates" in stated:
        cov = list(t["covariates"])
        if style == "exact":
            ph.append("please adjust for " + ", ".join(cov))
            gt["covariate_columns"] = cov
        elif style == "loose":
            ph.append("please adjust for " + ", ".join(_loosen(c) for c in cov))
            gt["covariate_columns"] = cov
        elif style == "described":
            ph.append(f"please adjust for {_describe('covariates', p['id'])}")
        else:  # set_valued -- no list of names exists for this
            ph.append("please adjust for everything the registry model covers")
        spans["covariates"] = ph[-1]

    # ---- perturbations: none of them may move the ground truth ----------
    note = ""
    if perturbation == "false_design":
        ph.append("this is a nested case-control study")
        note = "a false design claim; there is no design field to put it in"
    elif perturbation == "false_coding":
        if gt["event_column"] is not None:
            ph.append("note that the outcome column is 1 for the survivors")
            gt["event_value"] = "1"
            note = ("a false claim about the coding; quoted faithfully, and the "
                    "consequence card is what contradicts it")
    elif perturbation == "false_external":
        ph.append("we also have published coefficients from a larger registry")
        note = "an external model the file does not carry; must not move a role"
    elif perturbation == "padding":
        ph.append(_PADDING)
        note = "sixty words of irrelevant context"
    elif perturbation == "ghost_column":
        if gt["covariate_columns"] is not None:
            gt["covariate_columns"] = gt["covariate_columns"] + ["hla_mismatch"]
            ph[-1] = ph[-1] + " and hla_mismatch"
            spans["covariates"] = ph[-1]
            note = ("a column the file does not have. QUOTED, not dropped -- the "
                    "harness refuses it by name, which leaves a trace; silently "
                    "dropping it would let the model overrule the analyst")

    # every field non-null means everything was readable from the request
    gt["stated_explicitly"] = all(gt[k] is not None for k in
                                  ("time_column", "event_column",
                                   "event_value", "covariate_columns"))
    return ph, gt, note, spans


def _render(ph: List[str], register: str, profile_note: str,
            domain: str = "a transplant cohort") -> str:
    if not ph:
        return "Can you have a look at this dataset for me?"
    body = [s[0].upper() + s[1:] for s in ph]
    if register == "terse":
        return ". ".join(body) + "."
    if register == "narrative":
        return (f"We have {domain} and I would like a survival model: "
                + "; ".join(s[0].lower() + s[1:] for s in body) + ".")
    if register == "bulleted":
        return "Survival analysis, please.\n" + "\n".join(f"- {s}" for s in body)
    if register == "email":
        return ("Hi -- could you help with our cohort? "
                + " ".join(s + "." for s in body)
                + " Thanks, and no rush on this one.")
    return ("CLINICAL NOTE / analysis request. "
            + " ".join(s + "." for s in body))


# ------------------------------------------------------------- the corpus
def _meaningful(pid: str, stated_key: str, style: str, pert: str) -> bool:
    """Drop combinations that cannot test what they claim to."""
    stated = STATED_SETS[stated_key]
    if not stated and (style != "exact" or pert not in ("none", "padding")):
        return False                      # "nothing stated" has one useful form
    if pert == "ghost_column" and ("covariates" not in stated
                                   or style not in ("exact", "loose")):
        # nowhere to put the ghost: `described` and `set_valued` both leave the
        # covariate field null, so the item would carry the label and not the
        # thing. Found by spot-reading the generated corpus, not by the tests.
        return False
    if pert == "false_coding" and style == "described":
        # `described` leaves the event column unnamed, so there is no coding
        # claim to contradict. Excluded HERE rather than rejected after the
        # fact, so the template pool is not diluted by combinations that can
        # never produce the item they are named after.
        return False
    if pert == "false_coding" and "event_value" not in stated:
        # The false-coding sentence says "the outcome column is 1 for the
        # SURVIVORS". Where the analyst has ALSO said "it is 1 when the event
        # happened", quoting 1 is right and the contradiction is for the
        # consequence card to expose. Where they have NOT, that sentence is the
        # only thing said about the value -- and it does not say which value
        # means the EVENT. The honest key would be null, but the item then
        # tests nothing the plain `no_value` items do not already test, and
        # asserting "1" would simply be wrong. Excluded rather than fudged.
        return False
    if style == "set_valued" and "covariates" not in stated:
        return False
    if pid == "matched" and pert == "false_design":
        # Two reasons, either sufficient. The claim "this is a nested
        # case-control study" is TRUE on this profile, so it is not a false
        # design claim at all. And the word "case" IS a column here, so the
        # sentence would name the outcome column while the key withholds it --
        # which the generator's self-check caught, and which is exactly the leak
        # the self-check was added for.
        return False
    if pid == "matched" and stated_key == "time_only":
        # The matched profile has no follow-up duration, so `_phrases` simply
        # emits no time clause and the key stays null -- there is nothing to
        # exclude. This rule used to drop EVERY matched combination that
        # mentioned time, which left the profile contributing five identical
        # copies of "have a look at this dataset" and never exercising the thing
        # it was built for: `case` as the outcome column with `set_id` and
        # `site` sitting beside it as decoys. Only the degenerate case is
        # dropped now: `time_only` on a file with no time is just `nothing`.
        return False
    if pid == "opaque" and style in ("exact", "loose") and pert == "none":
        return False                      # covered by the other profiles
    return True


def _self_check(item: Dict[str, Any]) -> List[str]:
    """A column name may appear in the request IFF the ground truth names it.

    Run on every item at generation time, not only after a rewrite. A generator
    can violate this exactly as easily as a paraphrasing model can, and it did.
    """
    from verify_corpus import check_item
    ok, problems = check_item(item)
    return [] if ok else problems


# ------------------------------------------------- the few-shot bank
# Which described roles a bank profile can RESOLVE: True when exactly one
# column of the profile can plausibly be the role, so the example shows the
# resolution with its phrase; False when two columns could be it, so the
# example shows the honest null. Decided by reading the column lists, not
# computed -- the point of an example is to show judgement, and the judgement
# is the same one `complete` makes from eligibility at run time.
BANK_DESCRIBABLE = {
    "srtr_waitlist": {"time": True, "event": False},   # died_on_list vs removed_for_tx
    "srtr_posttx":   {"time": False, "event": False},  # days_to_death vs gf_days; pt_died vs graft_failed
    "ckd_ehr":       {"time": True, "event": True},
    "tx_center_ehr": {"time": True, "event": True},
    "heart_failure": {"time": True, "event": True},
}

_ROLE_LABEL = {"time": "the follow-up time column", "event": "the event column",
               "event_value": "the value that marks the event",
               "covariates": "the covariates"}


def bank_example(p: Dict[str, Any], gt: Dict[str, Any], spans: Dict[str, Any],
                 style: str) -> Dict[str, Any]:
    """The answer in the role-extraction schema's own shape, with a deterministic
    `reasoning` line assembled from the spans. `gt` is the corpus key (a
    described role is null there: nothing is NAMED); the example resolves a
    described role only where BANK_DESCRIBABLE says one column can be it."""
    t = p["truth"]
    desc = BANK_DESCRIBABLE.get(p["id"], {"time": False, "event": False})
    described = style == "described"
    out: Dict[str, Any] = {"reasoning": "", "time_column": gt["time_column"],
                           "time_evidence": None, "event_column": gt["event_column"],
                           "event_evidence": None, "event_value": gt["event_value"],
                           "event_value_evidence": None,
                           "covariate_columns": gt["covariate_columns"]}
    parts: List[str] = []
    unstated: List[str] = []
    for role, col_key, ev_key in (("time", "time_column", "time_evidence"),
                                  ("event", "event_column", "event_evidence")):
        sp = spans.get(role)
        if sp is None:
            unstated.append(_ROLE_LABEL[role])
            continue
        if gt[col_key] is not None:
            out[ev_key] = sp
            parts.append(f'"{sp}" names {_ROLE_LABEL[role]}')
        elif described and desc.get(role) and t[role] is not None:
            out[col_key] = t[role]
            out[ev_key] = sp
            parts.append(f'"{sp}" describes {_ROLE_LABEL[role]} without naming it, '
                         f'and {t[role]} is the only column that can be it')
        else:
            parts.append(f'"{sp}" describes {_ROLE_LABEL[role]} but more than one '
                         f'column could be it, so it stays null')
    sp = spans.get("event_value")
    if sp is not None and gt["event_value"] is not None:
        out["event_value_evidence"] = sp
        parts.append(f'"{sp}" gives {_ROLE_LABEL["event_value"]}')
    elif sp is None:
        unstated.append(_ROLE_LABEL["event_value"])
    sp = spans.get("covariates")
    if sp is None:
        unstated.append(_ROLE_LABEL["covariates"])
    elif gt["covariate_columns"] is not None:
        ghost = [c for c in gt["covariate_columns"] if c not in p["columns"]]
        parts.append(f'"{sp}" lists {_ROLE_LABEL["covariates"]}')
        if ghost:
            parts.append(f"{', '.join(ghost)} is named although the file has no such "
                         f"column; it is quoted as written")
    elif style == "set_valued":
        parts.append(f'"{sp}" refers to a set of columns without naming any, so '
                     f'covariate_columns is null')
    else:
        parts.append(f'"{sp}" describes {_ROLE_LABEL["covariates"]} without naming '
                     f'any, so covariate_columns is null')
    if unstated:
        parts.append("nothing in the request refers to " + " or ".join(unstated)
                     + ", so " + ("it is" if len(unstated) == 1 else "they are") + " null")
    out["reasoning"] = "; ".join(parts) + "."
    out["reasoning"] = out["reasoning"][0].upper() + out["reasoning"][1:]
    return out


def build(scale: int, seed: int = 20260819,
          profiles: Optional[Dict[str, Dict[str, Any]]] = None,
          id_prefix: str = "S", bank: bool = False) -> List[Dict[str, Any]]:
    profiles = profiles or ALL_PROFILES
    rng = random.Random(seed)
    templates = []
    for pid, sk, st, pe in itertools.product(
            profiles, STATED_SETS, REFERENCE_STYLES, PERTURBATIONS):
        if _meaningful(pid, sk, st, pe):
            templates.append((pid, sk, st, pe))
    rng.shuffle(templates)

    items: List[Dict[str, Any]] = []
    rejected: List[Any] = []
    ti = 0
    while len(items) < scale and templates:
        pid, sk, st, pe = templates[ti % len(templates)]
        ti += 1
        p = profiles[pid]
        ph, gt, note, spans = _phrases(p, STATED_SETS[sk], st, pe)
        tid = f"{pid}.{sk}.{st}.{pe}"
        for reg in REGISTERS:
            if len(items) >= scale:
                break
            it = {
                "id": f"{id_prefix}{len(items) + 1:04d}",
                "template_id": tid,
                "profile": pid,
                "axes": {"stated": sk, "reference": st, "perturbation": pe,
                         "register": reg},
                "request": _render(ph, reg, p["note"], p.get("domain", "a transplant cohort")),
                "expect": gt,
                "tests": note or p["note"],
                "source": "generated",
            }
            if bank:
                # the rendered clause: `_render` capitalises the first letter of
                # each clause in most registers and lower-cases it in the
                # narrative one; spans are matched case-insensitively downstream
                it["spans"] = {k: v for k, v in spans.items()}
                it["example"] = bank_example(p, gt, spans, st)
            # A LABEL WITHOUT THE THING IS WORSE THAN NO LABEL. `_meaningful`
            # decides whether a combination is worth generating from the STATED
            # set, while `_phrases` decides whether the perturbation can be
            # applied from the resulting GROUND TRUTH -- and the two can
            # disagree. When they did, items appeared tagged `ghost_column` with
            # no ghost in them, and the axis table reported a rate for a test
            # that was never run. `note` is non-empty exactly when a
            # perturbation was actually applied, so this closes the gap.
            bad = _self_check(it)
            if pe != "none" and not note:
                bad = bad + [f"labelled perturbation {pe!r} but it was not "
                             f"applied to this item"]
            if bad:
                rejected.append((tid, reg, bad))
                continue
            items.append(it)
    if rejected:
        print(f"REJECTED {len(rejected)} items that named a column their ground "
              f"truth withholds:", file=sys.stderr)
        for tid, reg, bad in rejected[:5]:
            print(f"  {tid}/{reg}: {bad[0]}", file=sys.stderr)
    return items


BANK_SEED = 20260912
BANK_OUT = HERE.parent / "bregsurv_agent" / "examples" / "fewshot_bank.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--scale", type=int, default=None)
    ap.add_argument("--bank", action="store_true",
                    help="generate the few-shot example bank (3d.11): the bank "
                         "profiles, seed %d, ids B####, schema-shaped answers" % BANK_SEED)
    a = ap.parse_args()
    if a.bank:
        out = a.out or str(BANK_OUT)
        scale = a.scale or 300
        items = build(scale, seed=BANK_SEED, profiles=BANK_PROFILES, id_prefix="B", bank=True)
        seed = BANK_SEED
    else:
        out = a.out or str(HERE / "corpus.json")
        scale = a.scale or 500
        items = build(scale)
        seed = 20260819
    a.out = out

    n_templates = len({i["template_id"] for i in items})
    by_axis: Dict[str, Dict[str, int]] = {}
    for i in items:
        for k, v in i["axes"].items():
            by_axis.setdefault(k, {}).setdefault(v, 0)
            by_axis[k][v] += 1
    null_items = sum(1 for i in items
                     if not i["expect"]["stated_explicitly"])

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"generated_by": "eval/generate_corpus.py" + (" --bank" if a.bank else ""),
         "seed": seed, "purpose": ("few-shot example bank for boundary 1 (3d.11)"
                                   if a.bank else "elicitation corpus"),
         "n_items": len(items), "n_templates": n_templates,
         "items": items}, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"{len(items)} items from {n_templates} templates -> {a.out}")
    print(f"  {null_items} items ({100*null_items/len(items):.0f}%) have at "
          f"least one field whose correct answer is NULL")
    for k, v in by_axis.items():
        print(f"  {k:14} " + "  ".join(f"{a}={n}" for a, n in sorted(v.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
