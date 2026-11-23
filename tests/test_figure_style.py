#!/usr/bin/env python3
"""Changing how a figure looks (figures.py, restyle_figure.R, figure_lib.R).

The one place the language model writes code, and the code is style terms for a figure the harness drew.
This suite checks the boundary, not the model: the figures are objects a restyle can be added to; the
checker accepts style terms and draws them, writing a script that redraws the figure with R alone; it
refuses every way of changing what a figure shows (data, axes, legend labels), every function outside
the vocabulary, every escape from it, and every way of making the figure unreadable, each for its own
reason and with the figure's files untouched; changes accumulate and are checked together; a refused
answer goes back to the model with its problems and three refusals leave the figure as it was; the
routing; and a turn of the app. The model is a fake that returns fixed answers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from bregsurv_agent.rbridge import _run_r, _find_rscript  # noqa: E402
from bregsurv_agent import actions, figures, intent, policy  # noqa: E402
from bregsurv_agent.state import Phase  # noqa: E402

failed = 0


def check(ok, label, note=""):
    global failed
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"   {note}" if note else ""))
    if not ok:
        failed += 1


def hdr(t):
    print(f"\n{t}")


def md5(p) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def cohort_with_sex(td: Path) -> Path:
    """The demo cohort with a two-level column, so the curve can be split into named groups."""
    src = REPO / "demo" / "kidney_cohort.csv"
    rows = list(csv.DictReader(open(src, newline="")))
    out = td / "cohort.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) + ["sex"])
        w.writeheader()
        for r in rows:
            r["sex"] = "F" if int(r["patient_id"]) % 2 == 0 else "M"
            w.writerow(r)
    return out


def km(data: Path, out_base: Path, group: str = "") -> dict:
    return _run_r("plot_km.R", {"data_path": str(data), "data_expr": "", "time_col": "followup_days",
                                "event_col": "died", "event_value": "1", "stratum_col": "",
                                "group_col": group, "out_base": str(out_base)}, timeout_s=180)


def restyle(fig_base: Path, steps, render=True) -> dict:
    return _run_r("restyle_figure.R", {"figure_rds": str(fig_base) + ".figure.rds", "steps": steps,
                                       "out_base": str(fig_base), "render": render}, timeout_s=180)


def codes_of(r: dict):
    return {p.get("code") for p in (r.get("problems") or [])}


class FakeClient:
    """Answers a constrained call from a queue per schema name, and keeps what it was sent."""
    base_url = "http://fake"

    def __init__(self, answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.sent = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        name = kw["response_format"]["json_schema"]["name"]
        self.sent.append((name, kw["messages"][-1]["content"]))
        q = self.answers.get(name) or [{}]
        out = q.pop(0) if len(q) > 1 else q[0]
        msg = NS(content=json.dumps(out), reasoning_content=None, model_extra={})
        return NS(choices=[NS(message=msg, finish_reason="stop")],
                  usage=NS(prompt_tokens=100, completion_tokens=50))


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="figstyle_"))
    try:
        return run(td)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def run(td: Path) -> int:
    data = cohort_with_sex(td)

    # ------------------------------------------------------------------ A
    hdr("A. the default figures are objects a restyle can be added to")
    one = td / "pooled" / "km_curve"; one.parent.mkdir()
    r1 = km(data, one)
    check(r1.get("status") == "ok" and all(Path(str(one) + e).is_file() for e in
                                            (".png", ".pdf", ".figure.rds", ".figure.json")),
          "plot_km.R draws the pooled curve (PNG, PDF) and keeps it as an object (.figure.rds/.json)",
          str(r1.get("reason") or ""))
    d1 = json.loads(Path(str(one) + ".figure.json").read_text())
    check(d1.get("kind") == "km_curve" and d1.get("groups") == ["All"]
          and d1.get("labels", {}).get("x") == "Follow-up (followup_days)",
          "its description names the kind, the one group and the axis titles", json.dumps(d1)[:200])
    two = td / "bysex" / "km_curve"; two.parent.mkdir()
    r2 = km(data, two, "sex")
    d2 = json.loads(Path(str(two) + ".figure.json").read_text())
    check(r2.get("status") == "ok" and r2.get("n_strata") == 2 and d2.get("groups") == ["F", "M"]
          and d2.get("colours", {}).get("F") == "#1f4e79",
          "split by a column: two groups, the first in the default palette", json.dumps(d2.get("colours")))
    figs = figures.available([str(one.parent), str(two.parent)])
    check(set(figs) == {"km_curve"} and figs["km_curve"].groups == ["F", "M"],
          "figures.available keeps the newest figure of each kind (the latest folder first)")

    # ------------------------------------------------------------------ B
    hdr("B. style terms are accepted, drawn, and written as a script that redraws the figure")
    good = ('p + theme_classic(base_size = 13) + scale_colour_manual(values = c(F = "black", M = "grey45")) '
            '+ scale_linetype_manual(values = c(F = "solid", M = "dashed")) '
            '+ labs(title = "Survival by sex", colour = "Sex", linetype = "Sex") '
            '+ theme(legend.position = "bottom") + line_width(1.2) + point_size(2)')
    before = md5(str(two) + ".png")
    rb = restyle(two, [{"code": good, "message": "black and grey, dashed for men, title it"}])
    check(rb.get("status") == "ok", "a colour, line-type, title, theme and size change is accepted",
          str(rb.get("problems") or rb.get("reason") or ""))
    check(md5(str(two) + ".png") != before, "the figure's PNG is redrawn in place (the report shows it)")
    cur = rb.get("current") or {}
    check(cur.get("colours", {}).get("M", "").lower() in ("grey45", "#737373")
          and cur.get("linetypes", {}).get("M") == "dashed"
          and (cur.get("labels") or {}).get("title") == "Survival by sex",
          "the look after the change is reported (what the model is shown next time)", json.dumps(cur)[:200])
    check(set(rb.get("changes") or []) >= {"the colours", "the line types", "titles and labels",
                                           "the line width", "the size of the censoring marks"},
          "the reply's list of changes is the checker's, not the model's", str(rb.get("changes")))
    sr = Path(rb.get("style_r") or "")
    text = sr.read_text() if sr.is_file() else ""
    check(sr.is_file() and "fig_survival <- function" in text and "p <- p + scale_colour_manual" in text
          and "fig_set_size(p, fig$meta$layers, \"line_width\", 1.2)" in text,
          "km_curve.style.R carries the harness's figure code and the restyle, step by step")
    rep = td / "replay"; shutil.copytree(two.parent, rep)
    for f in rep.glob("km_curve.p*"):
        f.unlink()
    env = dict(os.environ)
    pr = subprocess.run([_find_rscript(), "--no-save", "--no-restore", "km_curve.style.R"], cwd=rep,
                        capture_output=True, text=True, timeout=180, env=env, stdin=subprocess.DEVNULL)
    check(pr.returncode == 0 and (rep / "km_curve.png").is_file() and (rep / "km_curve.pdf").is_file(),
          "the style script redraws the figure with R alone, from the .figure.rds", pr.stderr[-300:])
    rw = restyle(two, [{"code": "p + line_width(2)", "message": "thicker"}], render=False)
    check(rw.get("status") == "ok", "a line width alone is a visible change (the harness's own layers are not altered)",
          str(rw.get("problems")))
    ok1 = restyle(one, [{"code": 'p + scale_colour_manual(values = c(All = "black")) + theme_minimal()',
                         "message": "make it black"}])
    check(ok1.get("status") == "ok", "one curve: its colour and a whole theme", str(ok1.get("problems")))
    ok4 = restyle(two, [{"code": 'p + scale_colour_manual(values = c(F = "black", M = "red"), name = "Sex") + theme_minimal()',
                         "message": "black and red, legend Sex"}], render=False)
    lab4 = (ok4.get("current") or {}).get("labels") or {}
    check(ok4.get("status") == "ok" and lab4.get("colour") == "Sex" == lab4.get("linetype"),
          "a new legend title on one scale is given to the other, so the legend stays one", json.dumps(lab4))
    ok2 = restyle(two, [{"code": 'p + scale_colour_brewer(palette = "Dark2")', "message": "Dark2 colours"}],
                  render=False)
    check(ok2.get("status") == "ok", "a ColorBrewer palette (its digit is a palette name, not a number)",
          str(ok2.get("problems")))
    ok5 = restyle(two, [{"code": "p + labs(x = 'Days since transplant', y = 'Survival probability') "
                                 "+ theme(text = element_text(size = 14, family = 'serif'))",
                         "message": "rename the axes, bigger serif font"}], render=False)
    check(ok5.get("status") == "ok", "axis titles that keep the units and the meaning, and a font change",
          str(ok5.get("problems")))
    ok3 = restyle(two, [{"code": 'p + labs(title = "Survival over 5 years")',
                         "message": "add the title Survival over 5 years"}], render=False)
    check(ok3.get("status") == "ok", "a number in a title is allowed when the analyst wrote it",
          str(ok3.get("problems")))

    # ------------------------------------------------------------------ C
    hdr("C. every way of changing what the figure shows, or of escaping the vocabulary, is refused")
    msg = "change the plot"
    bad = [
        ('p + geom_hline(yintercept = 0.5)', "function_not_allowed", "a new line drawn on the figure"),
        ('p + annotate("text", x = 100, y = 0.5, label = "here")', "function_not_allowed", "text written onto it"),
        ('p + coord_cartesian(ylim = c(0.5, 1))', "function_not_allowed", "a zoomed axis"),
        ('p + scale_y_continuous(limits = c(0.5, 1))', "function_not_allowed", "an axis scale"),
        ('p + xlim(0, 1000)', "function_not_allowed", "an axis limit"),
        ('p + scale_colour_manual(values = c(F = "red", M = "blue"), labels = c("M", "F"))',
         "argument_not_allowed", "groups relabelled through a scale"),
        ('p + scale_colour_manual(values = c(F = "red", M = "blue"), breaks = "M")',
         "argument_not_allowed", "a group dropped through a scale's breaks"),
        ('p + labs(title = "5-year survival is 80%")', "number_in_text", "a number the analyst did not write"),
        ('p + theme(axis.text = element_blank())', "axis_hidden", "the axis numbers removed"),
        ('p + theme(axis.title.x = element_blank())', "axis_hidden", "an axis title removed"),
        ('p + theme(legend.position = "none")', "legend_removed", "the legend removed by the theme"),
        ('p + guides(colour = "none", linetype = "none")', "legend_removed", "the legend removed by guides"),
        ('p + scale_colour_manual(values = c(F = "black", M = "black")) + '
         'scale_linetype_manual(values = c(F = "solid", M = "solid"))', "groups_look_the_same",
         "two groups drawn alike"),
        ('p + scale_colour_manual(values = c(F = "white", M = "black"))', "curve_invisible",
         "a curve in the background's colour"),
        ('p + scale_colour_manual(values = c(F = "#FF000033", M = "black"))', "transparent_colour",
         "a see-through colour"),
        ('p + scale_colour_manual(values = c(F = "red", Q = "blue"))', "unknown_group", "a group that does not exist"),
        ('p + scale_colour_manual(values = c(F = "red"))', "group_left_out", "a group left out"),
        ('p + scale_colour_manual(values = c(F = "nocolour", M = "blue"))', "not_a_colour", "not a colour"),
        ('p + scale_linetype_manual(values = c(F = "blank", M = "solid"))', "not_a_line_type",
         "a blank line type (an invisible curve)"),
        ('p + scale_colour_brewer(palette = "Nope")', "not_a_palette", "a palette that does not exist"),
        ('p + scale_fill_manual(values = c(F = "red", M = "blue"))', "no_such_scale",
         "a fill scale on a figure told apart by colour"),
        ('p + theme(text = element_text(size = 3))', "text_too_small", "text too small to read"),
        ('p + line_width(10)', "value_not_allowed", "a line width out of range"),
        ('p + ggplot2::theme_bw()', "not_a_style_term", "`::`"),
        ('p + theme_bw(base_family = system("id"))', "function_not_allowed", "a system call inside an argument"),
        ('p + theme(text = element_text(colour = x))', "name_not_allowed", "a name other than p"),
        ('p + theme_bw(); system("id")', "not_one_expression", "a second expression"),
        ('p$layers <- NULL', "must_start_with_p", "an assignment"),
        ('theme_bw()', "must_start_with_p", "no p"),
        ('p', "no_change", "p alone"),
        ('p +', "not_valid_r", "not R"),
        ('p + scale_colour_manual(c(F = "red", M = "blue"))', "argument_unnamed", "an unnamed argument"),
        ('p + theme(plot.title = element_text(face = function(x) x))', "function_not_allowed",
         "a function inside an argument"),
        ("p + theme(base_size = 14)", "argument_not_allowed",
         "a theme part that does not exist (ggplot2 would ignore it and nothing would change)"),
        ("p + theme(legend.title = element_text(label = 'Risk'))", "argument_not_allowed",
         "an argument element_text() does not take (it would be ignored)"),
        ("p + theme(text = element_text('serif'))", "argument_unnamed", "an unnamed element argument"),
        ("p + labs(x = 'Years since transplant')", "axis_title_unit",
         "a time axis drawn in days retitled in years"),
        ("p + labs(y = 'Cumulative mortality')", "axis_title_meaning",
         "the survival axis retitled as its complement"),
        ("p + theme_bw(base_size = 11) + theme(panel.grid = element_blank(), "
         "plot.title = element_text(size = rel(1), face = 'plain', hjust = 0.5), "
         "legend.background = element_blank(), legend.key = element_blank(), "
         "legend.position = 'top', legend.justification = 'left')", "no_effect",
         "a change that leaves the figure exactly as it was"),
        ("p + scale_colour_manual(values = c(F = 'red', M = 'blue'))) + theme_bw(", "not_valid_r",
         "a broken expression, with the hint to write strings in single quotes"),
    ]
    png0, pdf0 = md5(str(two) + ".png"), md5(str(two) + ".pdf")
    for code, want, what in bad:
        r = restyle(two, [{"code": code, "message": msg}])
        check(r.get("status") == "rejected" and want in codes_of(r), f"refused: {what}",
              f"{code}  ->  {r.get('status')} {sorted(codes_of(r))} {r.get('reason') or ''}")
    check(md5(str(two) + ".png") == png0 and md5(str(two) + ".pdf") == pdf0,
          "no refused change touched the figure's files")

    # ------------------------------------------------------------------ D
    hdr("D. changes accumulate, and every one is checked against the harness's figure")
    s1 = {"code": good, "message": "black and grey"}
    rd = restyle(two, [s1, {"code": 'p + theme(legend.position = "top")', "message": "legend on top"}])
    check(rd.get("status") == "ok" and "restyle 2" in Path(rd.get("style_r")).read_text(),
          "a second change applies on top of the first; the script has both", str(rd.get("problems")))
    rx = restyle(two, [s1, {"code": 'p + geom_point()', "message": "x"}])
    check(rx.get("status") == "rejected"
          and any("the new code" in (p.get("detail") or "") for p in rx.get("problems") or []),
          "a refused second change is named as the new code")
    rrep = restyle(two, [s1, s1], render=False)
    check(rrep.get("status") == "rejected" and "no_effect" in codes_of(rrep),
          "writing an accepted change again is refused as having no effect")
    rbad = restyle(two, [{"code": 'p + labs(title = "80% survive")', "message": "x"},
                         {"code": 'p + theme_bw()', "message": "y"}], render=False)
    check(rbad.get("status") == "rejected", "an earlier step is checked again with its own message")

    # ------------------------------------------------------------------ E
    hdr("E. the box plots of an evaluation by repeated splits")
    sp = td / "splits"; sp.mkdir()
    vals = sp / "values.csv"
    with open(vals, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["split", "key", "measure", "value"])
        for s in range(1, 21):
            for k, base in (("internal", 0.62), ("kl", 0.66), ("cv_selected", 0.65)):
                w.writerow([s, k, "cindex", base + 0.01 * ((s * 7) % 5)])
                w.writerow([s, k, "loss", 5.1 - base + 0.02 * ((s * 3) % 4)])
    rs = _run_r("plot_splits.R", {"values_csv": str(vals), "measures": ["cindex", "loss"],
                                  "labels": {"internal": "Internal only", "kl": "Kullback-Leibler",
                                             "cv_selected": "CV-selected"},
                                  "order": ["internal", "kl", "cv_selected"], "selected_key": "cv_selected",
                                  "out_base": str(sp / "splits_boxplot")})
    check(rs.get("status") == "ok" and (sp / "splits_boxplot.figure.json").is_file(),
          "plot_splits.R draws the box plots and keeps them as an object", str(rs.get("message") or ""))
    sb = sp / "splits_boxplot"
    r = restyle(sb, [{"code": 'p + scale_fill_manual(values = c("CV-selected" = "firebrick", '
                              '"Other methods" = "grey85")) + theme_minimal(base_size = 12) + line_width(0.6)',
                      "message": "red for the selected one"}])
    check(r.get("status") == "ok", "the box plots: their fill, a theme and the boxes' line width",
          str(r.get("problems") or r.get("reason")))
    r = restyle(sb, [{"code": 'p + scale_fill_manual(values = c("CV-selected" = "grey85", '
                              '"Other methods" = "grey85"))', "message": "grey"}])
    check(r.get("status") == "rejected" and "groups_look_the_same" in codes_of(r),
          "the CV-selected box must still stand out")
    r = restyle(sb, [{"code": 'p + facet_wrap(~ measure, ncol = 1)', "message": "one column"}])
    check(r.get("status") == "rejected", "re-faceting is refused")

    # ------------------------------------------------------------------ F
    hdr("F. figures.restyle: a refused answer goes back with its problems; three refusals leave it")
    three = td / "loop" / "km_curve"; three.parent.mkdir()
    km(data, three, "sex")
    figs = figures.available([str(three.parent)])
    png0 = md5(str(three) + ".png")
    fake = FakeClient({"figure_style": [
        {"reasoning": "q", "figure": "km_curve", "code": 'p + geom_hline(yintercept = 0.5)'},
        {"reasoning": "q", "figure": "km_curve",
         "code": 'p + scale_colour_manual(values = c(F = "black", M = "firebrick"))'}]})
    oc = figures.restyle(fake, "m", "make the curves black and red, and mark one half", figs, _run_r)
    check(oc.accepted and len(oc.attempts) == 2 and oc.attempts[0]["verdict"] == "returned",
          "a refused first answer, then an accepted second", json.dumps(oc.attempts)[:300])
    check(len(fake.sent) == 2 and "Your earlier answer to this message was not used" in fake.sent[1][1]
          and "geom_hline() is not allowed" in fake.sent[1][1],
          "the second call carries the refused code and the checker's problems by name")
    check("p already carries them" not in fake.sent[0][1] and '"F" #1f4e79' in fake.sent[0][1],
          "the model is shown the figure's groups and their colours")
    sj = json.loads(Path(str(three) + ".style.json").read_text())
    check(len(sj["steps"]) == 1 and sj["steps"][0]["code"].startswith("p + scale_colour_manual")
          and sj["current"]["colours"]["M"] in ("firebrick", "#B22222"),
          "the accepted step and the look after it are recorded in km_curve.style.json")
    check(oc.png_for_chat and oc.png_for_chat.endswith(".style1.png") and Path(oc.png_for_chat).is_file()
          and figures.is_style_png(oc.png_for_chat),
          "the chat gets its own copy of the picture (a later change will not alter it)")
    figs = figures.available([str(three.parent)])
    check(len(figs["km_curve"].steps) == 1 and "p already carries them" in figures.describe(figs),
          "the next request sees the change already made")
    t = figures.reply_text(oc)
    check(t.startswith(figures.MARK) and "I changed the Kaplan-Meier curve" in t
          and "exactly as before" in t and "km_curve.style.R" in t,
          "the reply is the harness's: what changed, what did not, where the code is")
    png1 = md5(str(three) + ".png")
    fake2 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "km_curve",
                                          "code": 'p + coord_cartesian(ylim = c(0.5, 1))'}]})
    oc2 = figures.restyle(fake2, "m", "zoom into the top half", figs, _run_r)
    check(not oc2.accepted and len(oc2.attempts) == figures.MAX_CALLS == 3 and len(fake2.sent) == 3,
          "three refusals in a row: not accepted, and no fourth call")
    check(md5(str(three) + ".png") == png1 and len(figures.available([str(three.parent)])["km_curve"].steps) == 1,
          "and the figure and its record are as they were")
    t2 = figures.reply_text(oc2)
    check(t2.startswith(figures.MARK) and "I did not change the Kaplan-Meier curve" in t2
          and "never what it shows" in t2, "the analyst is told why, in plain words", t2[:160])
    fake3 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "risk_groups", "code": "p + theme_bw()"}]})
    oc3 = figures.restyle(fake3, "m", "x", figs, _run_r, max_calls=1)
    check(not oc3.accepted and oc3.problems and oc3.problems[0]["code"] == "no_such_figure",
          "a figure that is not shown is refused before anything runs")
    check(png0 != png1, "(the accepted change did redraw the figure)")
    fake4 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "km_curve", "code": "",
                                          "not_possible": "zoom the y axis to 0.5 to 1"}]})
    oc4 = figures.restyle(fake4, "m", "Please zoom the y axis to 0.5 to 1.", figs, _run_r)
    t4 = figures.reply_text(oc4)
    check(oc4.declined and not oc4.accepted and len(fake4.sent) == 1
          and md5(str(three) + ".png") == png1
          and 'You asked for "zoom the y axis to 0.5 to 1"' in t4 and "never what it shows" in t4,
          "an empty code is a declined request: one call, the figure untouched, the analyst's words quoted")
    fake5 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "km_curve",
                                          "code": "p + line_width(1.5)",
                                          "not_possible": "add a line at the median"}]})
    oc5 = figures.restyle(fake5, "m", "Thicker lines, and add a line at the median.", figs, _run_r)
    t5 = figures.reply_text(oc5)
    check(oc5.accepted and 'What I did not do: "add a line at the median"' in t5,
          "a partly possible request: the possible part is made, the rest named in the reply",
          json.dumps(oc5.attempts)[:400])
    fake6 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "km_curve", "code": "",
                                          "not_possible": "something the analyst never wrote"}]})
    oc6 = figures.restyle(fake6, "m", "Zoom in please.", figs, _run_r)
    check(oc6.declined and oc6.not_possible is None and "something the analyst" not in figures.reply_text(oc6),
          "words the analyst did not write are never quoted back as theirs")
    png5 = md5(str(three) + ".png")
    fake7 = FakeClient({"figure_style": [
        {"reasoning": "q", "figure": "km_curve",
         "code": "p + scale_colour_manual(values = c('F' = '#1f4e79', 'M' = 'white'))"},
        {"reasoning": "q", "figure": "km_curve", "code": "", "not_possible": "Make the M curve white"}]})
    oc7 = figures.restyle(fake7, "m", "Make the M curve white.", figs, _run_r)
    t7 = figures.reply_text(oc7)
    check(oc7.declined and len(fake7.sent) == 2 and md5(str(three) + ".png") == png5
          and "Never put a different change in its place" in fake7.sent[1][1]
          and 'What you asked for ("Make the M curve white") cannot be done here: a curve would hardly show' in t7,
          "a refused request the analyst asked for exactly: the return says not to swap in another change, "
          "the decline names what the check found", t7[:200])
    fake8 = FakeClient({"figure_style": [
        {"reasoning": "q", "figure": "km_curve", "code": "p + line_width(1.5)"},
        {"reasoning": "q", "figure": "km_curve", "code": "", "not_possible": None}]})
    oc8 = figures.restyle(fake8, "m", "Thicker lines please.", figs, _run_r)
    t8 = figures.reply_text(oc8)
    check(oc8.declined and oc8.already and "may already look the way you asked" in t8
          and "already looks the way the code sets it" in fake8.sent[1][1]
          and md5(str(three) + ".png") == png5,
          "a change that would alter nothing, then a decline: the analyst is told it may already look so")
    moved = td / "moved"; shutil.copytree(three.parent, moved)
    fm = figures.available([str(moved)])["km_curve"]
    check(fm.base.startswith(str(moved)) and fm.rds.startswith(str(moved)) and len(fm.steps) == 2,
          "a copied run folder resolves its figure from where it is now, with its restyles")
    fake9 = FakeClient({"figure_style": [{"reasoning": "q", "figure": "km_curve",
                                          "code": "p + theme(legend.position = 'bottom')",
                                          "not_possible": "swap the names in the legend"}]})
    oc9 = figures.restyle(fake9, "m", "Swap the names F and M in the legend.", figs, _run_r)
    t9 = figures.reply_text(oc9)
    check(oc9.accepted and oc9.partial and oc9.not_possible is None
          and "may not have been possible here" in t9 and "swap the names in the legend" not in t9,
          "a change made while the model says, in other words, that part cannot be done: the reply "
          "says so without quoting words the analyst did not write", t9[:300])

    # ------------------------------------------------------------------ G
    hdr("G. routing: the intent kind, the act, the budget, the policy")
    its = intent.validate("Please make the curves black and the font bigger.",
                          {"intents": [{"kind": "restyle_figure", "evidence": "make the curves black",
                                        "external_form": None, "external_name": None,
                                        "out_of_scope_reason": None, "km_by": None}]})
    check([i.kind for i in its] == ["restyle_figure"] and its[0].evidence_verified,
          "M1's new kind is kept, with its evidence checked")
    sess = NS(phase=Phase.DONE, declaration=object(), pending=None, external=None, has_result=True)
    a1 = actions.plan(sess, its)
    check(a1 == [actions.Act.RESTYLE_FIGURE] and not actions.check(sess, a1),
          "a restyle request plans one act, legal after a result")
    mk = lambda k: intent.Intent(kind=k, evidence="x")  # noqa: E731
    a2 = actions.plan(NS(phase=Phase.PROFILED, declaration=None, pending=None, external=None,
                         has_result=False), [mk("declare_roles"), mk("kaplan_meier"), mk("restyle_figure")])
    check(a2 == [actions.Act.PROPOSE_ROLES, actions.Act.DRAW_KM, actions.Act.COMPLETE,
                 actions.Act.RESTYLE_FIGURE],
          "with a declaration and a KM request: run, draw, then restyle", str([a.value for a in a2]))
    check(actions.model_calls_in([actions.Act.RESTYLE_FIGURE]) == 1 and actions.figure_calls() == 3,
          "its calls are a bounded loop of their own (three), outside the per-turn count")
    check(actions.SPECS[actions.Act.RESTYLE_FIGURE].proposer == "model:figure_style"
          and "figure_style" in policy.NAMES and "restyle_figure" in policy.load("intent"),
          "the act, its policy and M1's description of the kind")
    check("restyle_figure" in intent.KINDS and "it can change how those figures look"
          in intent.REFUSALS["figure_requested"],
          "a new kind of figure is still refused, and the refusal says looks can change")

    # ------------------------------------------------------------------ H
    hdr("H. the app: a restyle turn after a run")
    import app
    h, s, *_ = app.start_session()
    out = app.submit_answer("1) followup_days\n2) died\n3) 1\n4) A\n6) yes", h, s, "", "", "")
    h, _, s, *_ = out
    run_dir = Path(s.temp[-1])
    check((run_dir / "km_curve.figure.json").is_file() and (run_dir / "clinical_groups.figure.json").is_file(),
          "a run keeps the KM curve and the risk-group figure as objects",
          ", ".join(sorted(p.name for p in run_dir.glob("*.figure.json"))))
    app._client = lambda endpoint, api_key: FakeClient({
        "intent": [{"reasoning": "q", "intents": [{"kind": "restyle_figure", "evidence": "make the curve black",
                                                   "external_form": None, "external_name": None,
                                                   "out_of_scope_reason": None, "km_by": None}]}],
        "figure_style": [{"reasoning": "q", "figure": "km_curve",
                          "code": 'p + scale_colour_manual(values = c(All = "black")) + theme_classic(base_size = 13)'}]})
    km0 = md5(run_dir / "km_curve.png")
    n0 = len(h)
    h2, _, s2, *rest = app.submit_answer("Please make the curve black and use a cleaner look.", h, s,
                                         "http://localhost:1/v1", "fake", "")
    new = h2[n0:]
    texts = [b for _, b in new if isinstance(b, str)]
    files = [str(b[0]) for _, b in new if isinstance(b, (tuple, list)) and b]
    check(any(t.startswith(figures.MARK) and "I changed the Kaplan-Meier curve" in t for t in texts),
          "the reply says what changed", " | ".join(t[:80] for t in texts))
    check(any(figures.is_style_png(f) for f in files) and any(f.endswith(".pdf") for f in files),
          "the restyled picture is shown, and the report PDF is rebuilt with it", ", ".join(files))
    check(md5(run_dir / "km_curve.png") != km0 and (run_dir / "km_curve.style.R").is_file(),
          "the report's own figure is redrawn and its style script written")
    log = [a for a in s2.actions if a.get("route") == "restyle_figure"]
    check(bool(log) and log[-1].get("accepted") is True and log[-1].get("figure") == "km_curve"
          and log[-1].get("code", "").startswith("p + scale_colour_manual"),
          "the session's action log records the restyle and the model's code")
    app._client = lambda endpoint, api_key: None
    h3, _, s3, *_ = app.submit_answer("Please make the curve black.", h2, s2, "", "", "")
    check("I changed" not in str(h3[-1][1]), "with no model configured nothing is restyled")

    print(f"\nRESULT: {'all passed' if not failed else f'{failed} failed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
