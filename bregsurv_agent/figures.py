"""Changing how a figure looks, at the analyst's request (V4).

The analyst says "make the curves black and dashed", "a bigger font", "call the x axis Days since
transplant", and the figure changes. This is the one place the language model writes code, and the
code is not statistical: it is ggplot2 style terms added to a figure the harness already drew from the
fitted analysis. "The language model writes no statistical code" holds as before.

Who does what:

* the harness draws every figure (`plot_km.R`, `clinical_summary.R`, `plot_splits.R`, through
  `figure_lib.R`) and keeps it as an object, `<base>.figure.rds`, beside the PNG and the PDF, with a
  description, `<base>.figure.json`: the groups and their colours, the titles;
* the model reads the request once (`read_request`, policy `figure_style`): which figure, and one R
  expression, `p + term + ...`, from a closed list of style functions;
* the harness decides whether the code is used (`restyle_figure.R`): it reads the code without running
  it (only the listed functions and arguments, plain values, colours R knows, no number in a label the
  analyst did not write), runs it with nothing else in reach, and compares the result with its own
  figure -- every layer's data, the axes' ranges and the legend's labels must be unchanged, and the
  axes, their titles and the legend must still be shown. A refused answer goes back to the model with
  the problems named, at most `MAX_CALLS` calls in all; after that the figure stays as it was and the
  analyst is told why;
* an accepted change is drawn into the same files, so the report shows it, and recorded:
  `<base>.style.json` (every accepted step, the message that asked for it, the model's code) and
  `<base>.style.R`, which redraws the figure from the .rds with R alone.

Changes accumulate: the model's code is applied on top of the changes made before, and every check is
against the harness's own figure. A figure drawn anew (a new analysis, the curve split by another
column) starts from the default look.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import boundary, policy

# the figures, as the analyst and the model know them
LABELS = {"km_curve": "the Kaplan-Meier curve",
          "risk_groups": "the survival curves by predicted risk group",
          "splits_boxplot": "the box plots of the evaluation by repeated splits"}
SHOWS = {"km_curve": "the curves, the censoring marks, the numbers at risk and the axes",
         "risk_groups": "the curves, the censoring marks, the numbers at risk and the axes",
         "splits_boxplot": "every box, every method's values and the axes"}
IN_REPORT = ("km_curve", "risk_groups")   # drawn into report.md; the box plots sit beside it

MAX_CALLS = 3          # one reading and at most two returns, like the planner's bounded loop

# the start of every reply about a figure's look: the chat keeps these when it folds a turn that also
# ran an analysis into one summary (an HTML comment, not shown)
MARK = "<!-- figure style -->"


def is_style_png(path: str) -> bool:
    """A picture of a restyled figure, as the chat shows it (`<base>.style<n>.png`)."""
    import re
    return re.search(r"\.style\d+\.png$", path or "") is not None

_SYSTEM = policy.load("figure_style")


def schema_for(ids: Sequence[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {"type": "string"},
            "figure": {"type": "string", "enum": list(ids)},
            "code": {"type": "string", "maxLength": 1500},
            "not_possible": {"anyOf": [{"type": "string", "maxLength": 300}, {"type": "null"}]},
        },
        "required": ["reasoning", "figure", "code", "not_possible"],
    }


@dataclass
class Figure:
    kind: str
    base: str                      # <dir>/<name>, without an extension
    rds: str
    png: str
    pdf: str
    title: str
    groups: List[str]
    colours: Dict[str, str]
    legend_title: Optional[str]
    labels: Dict[str, Optional[str]]
    steps: List[Dict[str, Any]] = field(default_factory=list)   # accepted restyles, in order
    current: Dict[str, Any] = field(default_factory=dict)       # the look after them

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, self.title)

    def style_json(self) -> Path:
        return Path(self.base + ".style.json")


def _load(path: Path) -> Optional[Figure]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get("kind") or not d.get("base"):
        return None
    # the files sit beside the description: resolved from where it is now, so a run folder that was
    # moved or copied (a restored session) still points at its own figure
    base = str(path.parent / Path(str(d["base"])).name)
    if not Path(base + ".figure.rds").is_file():
        return None
    groups = d.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    fig = Figure(kind=str(d["kind"]), base=base, rds=base + ".figure.rds", png=base + ".png",
                 pdf=base + ".pdf", title=str(d.get("title") or ""), groups=[str(g) for g in groups],
                 colours={str(k): str(v) for k, v in (d.get("colours") or {}).items()},
                 legend_title=d.get("legend_title"), labels=dict(d.get("labels") or {}))
    sj = fig.style_json()
    if sj.is_file():
        try:
            s = json.loads(sj.read_text(encoding="utf-8"))
            fig.steps = list(s.get("steps") or [])
            fig.current = dict(s.get("current") or {})
        except Exception:
            pass
    return fig


def available(dirs: Sequence[str]) -> Dict[str, Figure]:
    """The figures the session holds, the newest of each kind: every `<base>.figure.json` in the
    session's run folders, latest folder first."""
    out: Dict[str, Figure] = {}
    for d in reversed([str(x) for x in (dirs or []) if x]):
        p = Path(d)
        if not p.is_dir():
            continue
        for j in sorted(p.glob("*.figure.json")):
            f = _load(j)
            if f is not None and f.kind in LABELS and f.kind not in out:
                out[f.kind] = f
    return out


def describe(figs: Dict[str, Figure]) -> str:
    """What the model is shown of each figure: its groups and how they look now, its titles, and the
    changes already made to it."""
    parts = []
    for kind, f in figs.items():
        cur = f.current or {}
        cols = cur.get("colours") or f.colours
        lts = cur.get("linetypes") or {}
        labels = cur.get("labels") or f.labels
        aes = "fill" if kind == "splits_boxplot" else "colour"
        lines = [f"{kind} -- {f.label}"]
        lines.append(f"  groups ({aes}): " + ", ".join(
            f'"{g}" {cols.get(g, "?")}' + (f" {lts[g]}" if g in lts else "") for g in f.groups))
        if kind != "splits_boxplot":
            lt = labels.get("colour") or f.legend_title
            lines.append("  legend title: " + ("none (one curve, no legend)" if len(f.groups) < 2
                                               else f'"{lt}"' if lt else "none"))
        for k, name in (("title", "title"), ("x", "x axis title"), ("y", "y axis title")):
            if labels.get(k):
                lines.append(f'  {name}: "{labels[k]}"')
        if f.steps:
            lines.append("  changes already made (p already carries them):")
            for s in f.steps:
                lines.append(f"    {s.get('code')}")
        else:
            lines.append("  changes already made: none")
        parts.append("\n".join(lines))
    return "Figures you can change:\n\n" + "\n\n".join(parts)


def read_request(client, model: str, message: str, figs: Dict[str, Figure],
                 previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One constrained generation (policy `figure_style`). `previous`, on a return: the code that was
    refused and the problems the harness found in it."""
    user = describe(figs) + "\n\n"
    if previous:
        probs = "\n".join(f"  - {p}" for p in previous.get("problems") or [])
        user += (f"Your earlier answer to this message was not used.\n  figure: {previous.get('figure')}\n"
                 f"  code: {previous.get('code')}\n  problems:\n{probs}\n"
                 "Write it again without these problems. If what was refused is exactly what the analyst "
                 "asked for -- a white curve, a hidden legend, time in other units -- it cannot be done: "
                 "write an empty code and copy the analyst's words into not_possible. Never put a "
                 "different change in its place, and never add a term the analyst did not ask for to get "
                 "past a problem. A colour the analyst named that is too pale to show is drawn in a darker "
                 "shade of itself ('darkgreen' for 'green').\n\n")
    user += f"The analyst wrote:\n{message}"
    return boundary._chat(client, model, _SYSTEM, user, schema_for(list(figs)), "figure_style",
                          max_tokens=900)


@dataclass
class Outcome:
    accepted: bool
    figure: Optional[Figure] = None
    code: Optional[str] = None
    changes: List[str] = field(default_factory=list)
    problems: List[Dict[str, str]] = field(default_factory=list)
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    png_for_chat: Optional[str] = None
    style_r: Optional[str] = None
    reasoning: str = ""
    declined: bool = False                 # the model wrote no code: nothing asked for can be done
    not_possible: Optional[str] = None     # the part of the request it could not do, as the analyst wrote it
    already: bool = False                  # declined after its code was found to change nothing
    partial: bool = False                  # made a change, but said in other words that part could not be done


def _problem_lines(problems: List[Dict[str, Any]]) -> List[str]:
    return [str(p.get("detail") or p.get("code")) for p in problems or []]


def restyle(client, model: str, message: str, figs: Dict[str, Figure],
            run_r: Callable[..., Dict[str, Any]], max_calls: int = MAX_CALLS) -> Outcome:
    """Read the request, check the code, draw the figure; a refused answer goes back with its problems.

    Never raises for a refused or failing change: the outcome says what happened, and the figure files
    are touched only when a change is accepted."""
    attempts: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    last_problems: List[Dict[str, str]] = []
    import time
    from . import textmatch
    for _ in range(max_calls):
        t0 = time.time()
        try:
            raw = read_request(client, model, message, figs, previous)
        except Exception as exc:
            attempts.append({"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            last_problems = [{"code": "no_answer", "detail": "the model gave no usable answer"}]
            break
        kind = str(raw.get("figure") or "")
        code = str(raw.get("code") or "").strip()
        np_ = str(raw.get("not_possible") or "").strip()
        # shown to the analyst only as their own words
        np_ = np_ if np_ and textmatch.phrase_in(message, np_) else ("" if not np_ else "(unquoted)")
        rec: Dict[str, Any] = {"figure": kind, "code": code, "not_possible": np_ or None,
                               "reasoning": str(raw.get("reasoning") or "")[:1000],
                               "model_seconds": round(time.time() - t0, 1)}
        fig = figs.get(kind)
        if not code:
            # nothing the terms can do: the model says so rather than change something else
            rec["verdict"] = "declined"
            attempts.append(rec)
            quoted = np_ if np_ and np_ != "(unquoted)" else None
            # a decline after a return: the analyst is told what the check found, in plain words
            already = bool(last_problems) and not quoted and all(
                p.get("code") == "no_effect" for p in last_problems)
            return Outcome(accepted=False, declined=True, figure=fig, attempts=attempts,
                           not_possible=quoted, reasoning=rec["reasoning"],
                           problems=list(last_problems), already=already)
        if fig is None:
            probs = [{"code": "no_such_figure",
                      "detail": f'"{kind}" is not one of the figures: {", ".join(figs)}'}]
        else:
            steps = [{"code": s.get("code"), "message": s.get("message")} for s in fig.steps]
            steps.append({"code": code, "message": message})
            t1 = time.time()
            try:
                r = run_r("restyle_figure.R", {"figure_rds": fig.rds, "steps": steps,
                                               "out_base": fig.base, "render": True}, timeout_s=180)
            except Exception as exc:
                r = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
            rec["check_seconds"] = round(time.time() - t1, 1)
            if isinstance(r, dict) and r.get("status") == "ok":
                rec["verdict"] = "accepted"
                attempts.append(rec)
                n = len(fig.steps) + 1
                step = {"code": code, "message": message, "reasoning": rec["reasoning"],
                        "changes": list(r.get("changes") or [])}
                fig.steps.append(step)
                fig.current = dict(r.get("current") or {})
                fig.style_json().write_text(json.dumps(
                    {"figure": fig.kind, "rds": Path(fig.rds).name,
                     "what": "restyles the analyst asked for, each checked by restyle_figure.R: "
                             "the figure's data, axes' ranges and legend labels are unchanged",
                     "steps": fig.steps, "current": fig.current}, indent=2, ensure_ascii=False),
                    encoding="utf-8")
                # the chat shows a copy under its own name: a later restyle redraws the report's
                # file, and must not change the picture an earlier message shows
                chat_png = None
                try:
                    chat_png = f"{fig.base}.style{n}.png"
                    shutil.copyfile(r["png"], chat_png)
                except Exception:
                    chat_png = r.get("png")
                return Outcome(accepted=True, figure=fig, code=code,
                               changes=list(r.get("changes") or []), attempts=attempts,
                               png_for_chat=chat_png, style_r=r.get("style_r"),
                               reasoning=rec["reasoning"],
                               not_possible=np_ if np_ and np_ != "(unquoted)" else None,
                               partial=np_ == "(unquoted)")
            if isinstance(r, dict) and r.get("status") == "rejected":
                probs = list(r.get("problems") or [])
            else:
                probs = [{"code": "did_not_run",
                          "detail": str((r or {}).get("reason") if isinstance(r, dict) else r)[:400]}]
        rec["verdict"] = "returned"
        rec["problems"] = probs
        attempts.append(rec)
        last_problems = probs
        previous = {"figure": kind, "code": code, "problems": _problem_lines(probs)}
    return Outcome(accepted=False, problems=last_problems, attempts=attempts,
                   figure=figs.get(attempts[-1].get("figure")) if attempts else None)


# ------------------------------------------------------------------ what the analyst reads
_PLAIN = {
    "function_not_allowed": "it would change what the figure shows, not only how it looks",
    "data_changed": "it would change what the figure shows, not only how it looks",
    "layers_changed": "it would change what the figure shows, not only how it looks",
    "axis_range_changed": "it would change the range of an axis",
    "legend_labels_changed": "it would rename the groups in the legend",
    "argument_not_allowed": "it uses an option this system does not allow on a figure (a scale's labels, breaks or limits, for example)",
    "number_in_text": "a title or label would carry a number you did not write",
    "legend_removed": "the figure would lose the legend that tells its groups apart",
    "axis_hidden": "the figure would lose its axis numbers or titles",
    "text_too_small": "its text would become too small to read",
    "groups_look_the_same": "two groups would look the same",
    "curve_invisible": "a curve would hardly show against the background",
    "transparent_colour": "a colour would be see-through",
    "argument_unnamed": "the code it wrote could not be checked",
    "no_effect": "the code it wrote would have left the figure exactly as it was",
    "axis_title_unit": "an axis title would name units of time the data are not in",
    "axis_title_meaning": "the y axis title would describe something other than what the axis shows",
}

_NOT_DONE = ("which would change what the figure shows, not only how it looks; this system changes how "
             "a figure looks -- colours, line types and widths, fonts, titles, the legend -- and never "
             "what it shows")


def _reasons(problems: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for p in problems or []:
        w = _PLAIN.get(str(p.get("code")))
        if w and w not in out:
            out.append(w)
    return out


def _q(words: str) -> str:
    """The analyst's words inside quotes, without the sentence's own closing stop."""
    return str(words).strip().rstrip(" .!;,")


def reply_text(out: Outcome) -> str:
    """The harness's own words for the outcome; the model's reasoning is not shown."""
    if out.declined:
        label = out.figure.label if out.figure is not None else "the figure"
        if out.already:
            return (f"{MARK}**I did not change {label}.** The change your request asks for would leave "
                    "the figure exactly as it is, so it may already look the way you asked. The figure "
                    "is as it was.")
        reasons = _reasons(out.problems)
        if reasons:
            what = (f'What you asked for ("{_q(out.not_possible)}")' if out.not_possible
                    else "What you asked for")
            return (f"{MARK}**I did not change {label}.** {what} cannot be done here: "
                    f"{'; '.join(reasons)}. This system changes how a figure looks -- colours, line types "
                    "and widths, fonts, titles, the legend -- and never what it shows. The figure is as "
                    "it was.")
        what = (f'You asked for "{_q(out.not_possible)}", ' if out.not_possible
                else "What you asked for is something ")
        return f"{MARK}**I did not change {label}.** {what}{_NOT_DONE}. The figure is as it was."
    if out.accepted and out.figure is not None:
        what = ", ".join(out.changes) if out.changes else "its look"
        where = (" It is updated in the report." if out.figure.kind in IN_REPORT else
                 f" It is updated in `{Path(out.figure.png).name}`.")
        if out.not_possible:
            skipped = f' What I did not do: "{_q(out.not_possible)}", {_NOT_DONE}.'
        elif out.partial:
            # the model said something could not be done, in words that are not the analyst's
            skipped = (" Part of your request may not have been possible here: the change above is the "
                       "only one made.")
        else:
            skipped = ""
        return (f"{MARK}I changed {out.figure.label}: {what}. Everything it shows -- "
                f"{SHOWS.get(out.figure.kind, 'its data and axes')} -- is exactly as before; "
                f"the harness checked that before using the change.{where}{skipped} The code that made "
                f"the change is in `{Path(out.style_r or out.figure.base + '.style.R').name}`, and "
                "redraws the figure with R alone.")
    label = out.figure.label if out.figure is not None else "the figure"
    reasons = _reasons(out.problems)
    why = ("; ".join(reasons) if reasons else
           "the change could not be checked against the figure as drawn")
    detail = "\n".join(f"- {p.get('detail') or p.get('code')}" for p in out.problems[:6])
    return (f"{MARK}**I did not change {label}:** {why}. This system changes how a figure looks -- "
            "colours, line types and widths, fonts, titles, the legend -- and never what it shows. "
            "The figure is as it was."
            + (f"\n\n<details><summary>What the check found</summary>\n\n{detail}\n</details>"
               if detail else ""))
