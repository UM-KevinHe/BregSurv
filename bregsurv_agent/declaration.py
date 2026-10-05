"""The role-declaration protocol.

The agent never infers which column is what. The analyst declares it, and the
harness makes declaring cheap by supplying facts and then checking the answer
against the data.

The reasoning, settled 2026-08-17: an analyst who cannot say which column is
their outcome should not be running this analysis, and if the agent has to guess,
everything downstream is guesswork. The supporting evidence is that a pre-filled
suggestion changes what people write AND what they believe (N=1,506), so "the
analyst confirmed it" is weak evidence that the column was right.

Everything in this module is deterministic. The language model is not involved in
rendering the question, parsing the reply, or verifying it. That is the point: the
design does not depend on a 7B being good at extraction. The model has exactly one
optional job, on the path where the analyst already stated the roles in prose --
it proposes an extraction, and :func:`verify` echoes the consequences back before
anything is fitted, so a wrong extraction is seen rather than trusted.

What the analyst must declare, never inferred:
  * the follow-up-time column
  * the event column
  * WHICH VALUE of the event column means the event occurred
  * the covariate set
  * which published external model is being used
  * whether follow-up is recorded in DISCRETE INTERVALS, and if so the
    interval width and the horizon K -- or that the time column already is
    the interval index 1..K. Asked only when the data gives a reason (a time
    column on a coarse grid, `profile.possible_discrete`) or when the analyst
    answers it unasked; never read off the external file (ruling 6). The
    answer chooses the discrete-time row of the library, whose members are
    never ranked against the Cox row (ruling 4). Binning follow-up into the
    declared intervals is part of the model, computed by the harness and
    disclosed on the card (ruling 1) -- not data processing.

Three paths, chosen by how much the analyst supplied:
  1. a data dictionary is present -> it NARROWS the lists; it does not decide.
     Only when it leaves exactly one eligible time column and exactly one
     eligible event column may the question be skipped. (:func:`from_dictionary`)
  2. the analyst stated the roles in the request -> the model extracts, the
     harness verifies against the data.
  3. nothing stated -> :func:`render_question` asks once, with eligibility-
     filtered numbered lists, and :func:`parse_reply` reads the answer.

DECIDE, RUN, DISCLOSE. The analyst is asked only
what neither the request nor the data can settle. :func:`complete` takes what
was stated, fills each remaining role by a deterministic rule where the data
leaves exactly one possibility, and lists what is still open; the run starts
as soon as that list is empty. Every role then carries a SOURCE -- `quoted`
(the analyst named it), `inferred: <rule>` (the harness settled it from a data
fact), or the checkbox/reply that answered it -- printed on the consequence
card and in the report, so a wrong inference is seen and corrected by one more
message rather than approved in advance. The two rules the analyst accepted:
an unstated event value on a 0/1 (or TRUE/FALSE) column is 1 (TRUE); an
unstated covariate set is every usable numeric column that is not an outcome
column. The model still never fills a gap; a null from boundary 1 is what
`complete` fills, and the corpus that measures boundary 1 is unchanged.

Why path 1 is a narrowing and not a shortcut. Measured against the dictionary
this protocol was designed around (162 variables): `role = primary_outcome`
covers EIGHT variables, including survival_time_days and survival_time_years (the
same quantity in different units) and survival_event and survival_censored (exact
complements), and `role = outcome` carries a second complete time/event pair on a
different horizon. Thirteen columns are marked outcome-ish and they contain at
least three valid (time, event) pairs. Reading roles and proceeding would mean
choosing among them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# One message, not five questions. Structured checklist prompts beat turn-by-turn
# clarification (7.50/8 against 6.67/8, with fewer tokens), and single-turn
# batched asking beat iterative asking by about 40% while shortening the dialogue.
_MAX_LIST = 25


class DeclarationError(ValueError):
    """The reply could not be resolved to a declaration, with the reason why.

    `item` is the numbered item the analyst would correct ("3" for the event
    value, "4" for the covariates, ...), or None when the refusal is not about
    one item. Until 2026-09-13 the refusal said only "Reply by number to
    correct it"; in the MIUM run the simulated analyst then corrected item 4
    three times for an event value the model had extracted as the whole phrase
    "1 if they died, 0 if not" (19 of Qwen2.5's 100 prompts ended there).
    """

    def __init__(self, message: str, item: Optional[str] = None):
        super().__init__(message)
        self.item = item


@dataclass
class Declaration:
    """A fully resolved role declaration. Every field came from the analyst."""
    time_col: Optional[str]          # None IS the nested case-control declaration
    event_col: str
    event_value: str
    covariates: List[str]
    source: str                      # "dictionary" | "reply" | "model_extraction"
    stratum_col: Optional[str] = None
    # The external cohort's RAW DATA, when the analyst has it rather than only
    # a published coefficient vector. `external_data_expr` addresses the table
    # (in the same file, or in `external_data_path` if it has its own). Its
    # columns must be the internal ones, by name and in order -- checked in R,
    # because fit_cox_indi.R compares only ncol and a silent column-order
    # mismatch attaches every borrowed coefficient to the wrong variable.
    external_data_expr: Optional[str] = None
    external_data_path: Optional[str] = None
    external_model: Optional[str] = None
    covariates_time_zero: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    # role -> how it was settled: "quoted", "inferred: <rule>", "checkbox",
    # "reply". Provenance, not configuration (pipeline._DECL_PROVENANCE_ONLY).
    sources: Dict[str, str] = field(default_factory=dict)
    # THE DISCRETE-TIME DECLARATION. `n_intervals` set means the
    # internal outcome is in discrete intervals: interval k covers
    # [(k-1)*width, k*width) of the time column, subjects observed beyond
    # K*width are censored at interval K (the horizon), and with
    # `time_is_interval_index` the column already holds k in 1..K and no
    # binning is done. All three are configuration: hashed, traced, replayed.
    interval_width: Optional[float] = None
    n_intervals: Optional[int] = None
    time_is_interval_index: bool = False
    # THE ANALYST'S OWN TEST DATA: a second file
    # the analyst SUPPLIES and names as their test set -- never a split the
    # agent draws, never default. Same columns as the cohort (time, event,
    # the covariates, the stratum if any). Every member is fitted on the
    # cohort as before and then evaluated ONCE on these rows (C-index, loss,
    # IBS, time-dependent AUC); the selection among members is unchanged
    # (cross-validated loss on the cohort). Configuration: hashed by the
    # file's fingerprint, traced, replayed.
    test_data_path: Optional[str] = None
    test_data_expr: Optional[str] = None

    @property
    def has_test_data(self) -> bool:
        return bool(self.test_data_expr)

    def test_spec(self) -> Optional[Dict[str, Any]]:
        """What the R side needs to evaluate on the test rows, or None."""
        if not self.has_test_data:
            return None
        return {"path": self.test_data_path, "expr": self.test_data_expr,
                "time_col": self.time_col, "event_col": self.event_col,
                "covariates": list(self.covariates),
                "stratum_col": self.stratum_col}

    @property
    def discrete(self) -> bool:
        """Whether the discrete-time row was declared."""
        return self.n_intervals is not None

    @property
    def outcome_scale(self) -> str:
        return "discrete intervals" if self.discrete else "continuous"

    def discrete_spec(self) -> Optional[Dict[str, Any]]:
        """What the R side needs to bin, or None on the continuous scale."""
        if not self.discrete:
            return None
        return {"n_intervals": int(self.n_intervals),
                "width": (None if self.time_is_interval_index
                          else float(self.interval_width)),
                "time_is_index": bool(self.time_is_interval_index)}

    @property
    def design(self) -> str:
        """THE DESIGN IS READ OFF WHAT WAS DECLARED, not asserted separately.

        A matched design has no follow-up duration -- the library's own canonical
        representation sets time to a constant 1 and delta to the case indicator
        -- so the absence of a declared time column IS the declaration of a
        nested case-control study. This is exactly the discriminator
        run_candidates.R uses (`is_ncc <- !is.null(input$y_expr)`), so the two
        derivations cannot drift.

        Note what this deliberately does NOT do: it does not treat the presence
        of a stratum as the design. A STRATIFIED COHORT has both a follow-up time
        and a stratum, and it is a different analysis from a matched one.
        """
        return "full cohort" if self.time_col else "nested case-control"

    def as_exprs(self, data_expr: str) -> Dict[str, str]:
        """R expressions for the dispatcher, given the table's own expression."""
        # `drop = FALSE`: one declared covariate is a legitimate analysis, and
        # without it R hands the gate a bare vector ("incorrect number of
        # dimensions", hard set H075, 2026-09-15) instead of a one-column table
        out = {
            "z_expr": f"{data_expr}[, c({', '.join(_rq(c) for c in self.covariates)}), drop = FALSE]",
        }
        if self.time_col is None:
            # Matched design: the case/control indicator travels as `y`, and the
            # matched set is not optional -- run_candidates.R stops without it.
            out["y_expr"] = f"{data_expr}[[{_rq(self.event_col)}]]"
            out["stratum_expr"] = f"{data_expr}[[{_rq(self.stratum_col)}]]"
        else:
            out["time_expr"] = f"{data_expr}[[{_rq(self.time_col)}]]"
            out["delta_expr"] = f"{data_expr}[[{_rq(self.event_col)}]]"
            # A stratified cohort. Optional, and previously unreachable:
            # as_exprs never emitted it, so every cohort run was unstratified
            # whatever the analyst declared.
            if self.stratum_col:
                out["stratum_expr"] = f"{data_expr}[[{_rq(self.stratum_col)}]]"

        # The external cohort, addressed the same way and by the same column
        # names. One set of names for both tables is a real constraint, and it
        # is the one that makes the linkage checkable instead of positional.
        xd = self.external_data_expr
        if xd:
            cols = ", ".join(_rq(c) for c in self.covariates)
            out["z_ext_expr"] = f"{xd}[, c({cols}), drop = FALSE]"
            if self.time_col is None:
                out["y_ext_expr"] = f"{xd}[[{_rq(self.event_col)}]]"
                out["stratum_ext_expr"] = f"{xd}[[{_rq(self.stratum_col)}]]"
            else:
                out["time_ext_expr"] = f"{xd}[[{_rq(self.time_col)}]]"
                out["delta_ext_expr"] = f"{xd}[[{_rq(self.event_col)}]]"
                if self.stratum_col:
                    out["stratum_ext_expr"] = f"{xd}[[{_rq(self.stratum_col)}]]"
        return out


def _rq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _by_name(profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {c["name"]: c for c in profile.get("columns", [])}


def _fmt_col(c: Dict[str, Any], show_values: bool = False) -> str:
    bits = [c["type"]]
    s = c.get("summary")
    if s:
        bits.append(f"min {_n(s['min'])} / median {_n(s['median'])} / max {_n(s['max'])}")
    elif show_values and c.get("values"):
        bits.append("values " + " and ".join(str(v) for v in c["values"]))
    else:
        bits.append(f"{c['n_distinct']} distinct")
    if c.get("n_missing"):
        bits.append(f"{c['n_missing']} missing ({c['pct_missing']}%)")
    return ", ".join(bits)


def _n(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


# ----------------------------------------------------------------- the question
def render_question(profile: Dict[str, Any],
                    only: Optional[List[str]] = None,
                    time_col: Optional[str] = None) -> str:
    """Return the single message that asks for everything at once.

    `only` restricts it to the numbered items still open ("0".."6"), keeping
    the numbers stable so a reply is parsed the same way either way.
    `time_col` is the SETTLED follow-up column when item 7 is asked, so the
    time-scale question describes that column alone (found on MIUM 2026-09-12:
    without it the question listed eleven covariates on a 0.1 grid as "the
    shape a grouped follow-up time has").
    """
    cols = _by_name(profile)
    elig = profile.get("eligible", {})
    out: List[str] = []

    def want(k: str) -> bool:
        return only is None or k in only

    if only is None:
        out.append(f"Before anything is fitted I need you to tell me what the "
                   f"columns are. The file has {profile['n_rows']} rows and "
                   f"{profile['n_columns']} columns. Tell me in a sentence, or "
                   f"by number. What you leave out I fill in only where the "
                   f"data leaves one possibility, and I say so in the report.")
    else:
        out.append("I still need the following before anything is fitted; "
                   "reply by number.")
    out.append("")

    dic = profile.get("dictionary", {})
    if dic.get("present") and dic.get("outcome_ish"):
        out.append(f"The data dictionary marks {len(dic['outcome_ish'])} columns as "
                   f"outcome-related, which is what shortened the lists below. It "
                   f"does not say which is the follow-up time and which is the "
                   f"event, so those are still yours to state.")
        out.append("")

    def _list(title: str, names: List[str], show_values: bool = False) -> None:
        out.append(title)
        if not names:
            out.append("   (nothing in this file qualifies -- name a column and I "
                       "will tell you why it was excluded)")
            out.append("")
            return
        for i, nm in enumerate(names[:_MAX_LIST], start=1):
            out.append(f"  {i:>2}. {nm}   [{_fmt_col(cols[nm], show_values)}]")
        if len(names) > _MAX_LIST:
            out.append(f"      ... and {len(names) - _MAX_LIST} more; name it "
                       f"directly if it is not listed")
        out.append("")

    # The design question comes FIRST, and only when the data gives a reason
    # to ask it. Over-asking costs one line; not asking means a matched study is
    # analysed as a cohort, which is silently wrong and which nothing
    # downstream can detect.
    if profile.get("possible_ncc") and want("0"):
        cand = list(elig.get("stratum", []))
        out.append("0) STUDY DESIGN -- is this a nested case-control study?")
        for nm in cand[:_MAX_LIST]:
            k = cols[nm]["n_distinct"]
            out.append(f"   '{nm}' has {k} groups of about "
                       f"{round(profile['n_rows'] / max(1, k))} rows each, which "
                       f"is the shape a 1:m matched sample has.")
        out.append("   If YES: name the matched-set column, and LEAVE QUESTION 1 "
                   "BLANK -- a matched design has no follow-up duration.")
        out.append("   If NO: ignore this and answer 1 and 2 as usual. If the "
                   "column above is a stratum in an ordinary cohort, name it "
                   "here AND answer question 1; that is a stratified analysis, "
                   "which is a different thing.")
        out.append("")

    if want("1"):
        _list("1) FOLLOW-UP TIME -- how long each subject was observed"
              + (" (leave blank for a matched design):"
                 if profile.get("possible_ncc") else ":"),
              list(elig.get("time", [])))
    if want("2"):
        _list("2) EVENT INDICATOR -- whether the event happened:",
              list(elig.get("event", [])), show_values=True)

        # the complement warning belongs next to the event question, where it
        # lands
        for pair in profile.get("complementary_pairs", []):
            a, b = pair[0], pair[1]
            out.append(f"   Note: '{a}' and '{b}' are exact complements -- one "
                       f"is 1 wherever the other is 0. They describe opposite "
                       f"things, so which one you name changes the analysis "
                       f"completely.")
            out.append("")

    if want("3"):
        out.append("3) WHICH VALUE of the event column means the event occurred "
                   "(for example 1, or 'Dead'):")
        out.append("")

    ext = profile.get("external", {})
    presets = _presets(profile)
    if want("4"):
        out.append("4) COVARIATES -- reply with a letter, or a list of column "
                   "names:")
        if ext.get("present"):
            out.append(f"   A. the {len(presets['A'])} columns the external "
                       f"model covers: "
                       f"{', '.join(presets['A']) or '(none matched)'}")
        out.append(f"   B. all {len(presets['B'])} usable numeric columns")
        if presets["A"] and presets["B"] != presets["A"]:
            out.append("   You can also write 'A plus <name>' or 'A minus "
                       "<name>'.")
        out.append("")

        q = profile.get("quarantined", [])
        if q:
            out.append(f"Set aside for now ({len(q)}); say so if any of these "
                       f"should be used after all:")
            for e in q[:_MAX_LIST]:
                out.append(f"   - {e['name']}: {e['reason']}")
            out.append("")

        if ext.get("present") and ext.get("unmatched"):
            out.append(f"The external model also has {len(ext['unmatched'])} "
                       f"predictor(s) this file does not: "
                       f"{', '.join(ext['unmatched'])}. They will be dropped, "
                       f"and the report will say so.")
            out.append("")

    if want("5"):
        out.append("5) Do you have the EXTERNAL cohort's raw patient data, "
                   "rather than only its published coefficients? (leave blank "
                   "if not)")
        out.append("   If you do, say where the table is. Borrowing from the "
                   "rows themselves is a different and usually better-behaved "
                   "estimator than borrowing from a published summary, so it "
                   "is worth asking. The external table must carry the same "
                   "covariate columns, with the same names.")
        out.append("")

    if want("6"):
        out.append("6) Was every covariate value above known AT THE START of "
                   "follow-up, for every subject? (yes / no)")
        out.append("   This cannot be checked from the data -- a "
                   "one-row-per-subject table looks identical either way -- "
                   "and getting it wrong can reverse the direction of an "
                   "effect rather than just blur it, so I have to ask. If you "
                   "are unsure, say so and we will stop here.")

    # THE TIME-SCALE QUESTION, asked only when the data gives a
    # reason: the DECLARED follow-up time column sits on a coarse grid. Like
    # the design question it is a trigger, never an answer -- integer months
    # may be a continuous time rounded to months, and only the analyst knows.
    # It is not in the opening list: eligibility for "time" is deliberately
    # broad (any non-negative number with more than two values), so on an
    # EHR extract some integer column is always on a grid -- a site code, an
    # age in years -- and asking on that basis would put the question on
    # every file. Since 2026-09-12 the harness never raises it at all --
    # continuous time is the default and `complete` discloses that default
    # when the settled column is coarse; the analyst asks for the discrete
    # row by answering "7) <width> <K>" (or "7) index"), before or after a
    # run. The presence of a baseline hazard in the external file never
    # raises it (ruling 6).
    if only is not None and "7" in only and want("7"):
        out.append("")
        out.append("7) TIME SCALE -- is follow-up recorded in DISCRETE INTERVALS "
                   "(weeks, months, visits) rather than as a continuous time?")
        grid = [(c["name"], c.get("time_grid") or {}) for c in profile.get("columns", [])
                if c.get("time_grid") and (c["time_grid"].get("coarse"))
                and (time_col is None or c["name"] == time_col)]
        for nm, g in grid[:_MAX_LIST]:
            out.append(f"   '{nm}' takes {g.get('n_distinct')} distinct values, all "
                       f"multiples of {_n(g.get('step'))}, which is the shape "
                       f"a grouped follow-up time has.")
        out.append("   If NO: answer 'no' (a continuous-time analysis; the "
                   "default when this is not asked).")
        out.append("   If YES: give the interval WIDTH in the units of the time "
                   "column and the number of intervals K, for example "
                   "'7 53' for 53 weekly intervals of a time in days. "
                   "Interval k then covers [(k-1) x width, k x width), and a "
                   "subject observed beyond K x width is censored at "
                   "interval K. If the column already IS the interval index "
                   "1..K, answer 'index' (optionally followed by K).")
    return "\n".join(out).rstrip()


# ------------------------------------------------------------- completion
@dataclass
class Completion:
    """What :func:`complete` settled, how, and what is still open."""
    answers: Dict[str, str]          # for parse_reply; may still be incomplete
    sources: Dict[str, str]          # role -> "inferred: <rule>" for what it set
    missing: List[str]               # numbered items still to ask: "0".."6"

    @property
    def ready(self) -> bool:
        return not self.missing


def complete(profile: Dict[str, Any], given: Dict[str, Optional[str]],
             fallback: Optional["Declaration"] = None,
             remembered: Optional[Dict[str, Any]] = None,
             sources: Optional[Dict[str, str]] = None) -> Completion:
    """Fill what the analyst left out, where the data leaves one possibility.

    Deterministic. `given` holds the parse_reply keys the analyst has supplied
    so far (a None or empty value is "not stated"). `fallback` is what
    :func:`from_dictionary` settled, used for the outcome columns only.
    `sources` says how each given key was settled ("reply" when the analyst
    answered by number); it decides only whether the design question below
    is raised on a follow-up time that has the shape of a matched set.

    What is NEVER filled here: the time-zero answer (question 6). It cannot be
    read off the data and the gate refuses without it, so it is the one thing
    that always comes from a person -- by reply or by the checkbox.
    """
    cols = _by_name(profile)
    elig = profile.get("eligible", {})
    ans: Dict[str, str] = {k: str(v).strip() for k, v in (given or {}).items()
                           if v is not None and str(v).strip()}
    src: Dict[str, str] = {}
    missing: List[str] = []

    # ---- component 4: what the analyst declared for this SAME file before --
    # Applied before any data rule, after what was said now: a role the
    # analyst states in this message wins; a role they leave out is taken from
    # their own earlier declaration of the same file (matched by sha256) and
    # disclosed as such. `time_zero` is never in `remembered` -- see memory.py.
    if remembered and isinstance(remembered.get("answers"), dict):
        when = remembered.get("date") or "an earlier session"
        for k, v in remembered["answers"].items():
            if k == "time_zero" or not v or ans.get(k):
                continue
            ans[k] = str(v).strip()
            src[k] = f"remembered: you declared this for the same file on {when}"

    # ---- a follow-up time that is the matched-set column ----------------
    # The reading can name the set identifier as the follow-up time
    # ("Matched set = set_id" read as a duration: synth200 F08_1 and F20_8,
    # 2026-09-15). The name is in the message, so the backing check passes,
    # and the matched study would then be analysed as a cohort with the set
    # number as its follow-up -- silently wrong, and nothing downstream can
    # detect it. The data can: the column is the one the profile flags as
    # matched-set-shaped AND regular (nearly every group the same size, the
    # shape of a 1:m matched sample -- a follow-up time on a coarse grid is
    # set-shaped too but its groups vary: `regular_sets` in the profile). So a
    # follow-up time that is such a column, with no stratum declared, does not
    # stand on the reading alone; the design question is asked, and the
    # analyst either names the set (leaving the time blank) or says NO and
    # answers item 1 by number, which is the one source ("reply") this rule
    # does not reopen.
    if (ans.get("time") and not ans.get("stratum") and profile.get("possible_ncc")
            and (sources or {}).get("time") != "reply"):
        try:
            named = _resolve_one(profile, "time", ans["time"])
        except DeclarationError:
            named = None
        # regular group sizes, OR one case in every group (the profile's
        # joint fact; random controls leave late sets short -- 2026-09-30)
        if (named is not None and named in set(elig.get("stratum", []))
                and (cols.get(named, {}).get("regular_sets")
                     or cols.get(named, {}).get("one_case_per_set"))):
            src["design"] = (f"'{named}' was named as the follow-up time, but it has "
                             f"the shape of a matched-set column, so the study design "
                             f"is asked before anything is settled from it.")
            ans.pop("time", None)

    # ---- follow-up time / design ---------------------------------------
    if not ans.get("time") and not ans.get("stratum"):
        if profile.get("possible_ncc"):
            # the design question cannot be settled by omission
            missing += ["0", "1"]
        elif fallback is not None and fallback.time_col:
            ans["time"] = fallback.time_col
            src["time"] = ("inferred: the data dictionary leaves one eligible "
                           "follow-up time column")
        else:
            times = list(elig.get("time", []))
            if len(times) == 1:
                ans["time"] = times[0]
                src["time"] = ("inferred: the only column in the file that "
                               "qualifies as a follow-up time")
            else:
                missing.append("1")

    # ---- event column --------------------------------------------------
    if not ans.get("event"):
        events = list(elig.get("event", []))
        live = set(events)
        # a complement pair still on the table is a choice, never a fact
        contested = any(events and events[0] in (p[0], p[1])
                        and (p[1] if events[0] == p[0] else p[0]) in live
                        for p in profile.get("complementary_pairs", []))
        if fallback is not None and fallback.event_col:
            ans["event"] = fallback.event_col
            src["event"] = ("inferred: the data dictionary leaves one eligible "
                            "event column")
        elif len(events) == 1 and not contested:
            ans["event"] = events[0]
            src["event"] = ("inferred: the only column in the file that "
                            "qualifies as an event indicator")
        else:
            missing.append("2")
            if not ans.get("event_value"):
                missing.append("3")

    # ---- event value: the first accepted default -----------------------
    if ans.get("event") and not ans.get("event_value"):
        # resolve the way parse_reply will (an index into the list, or a
        # name in any case); a column the file lacks is left for parse_reply
        # to refuse BY NAME -- asking for its event value first would send
        # the analyst round twice
        try:
            ev_col = _resolve_one(profile, "event", ans["event"])
        except DeclarationError:
            ev_col = None
        levels = ([str(v) for v in (cols[ev_col].get("values") or [])]
                  if ev_col in cols else [])
        up = sorted(v.upper() for v in levels)
        if ev_col is None:
            pass
        elif str((sources or {}).get("event_value") or "").startswith("ask:"):
            # 2026-10-01: the message's own wording of the coding contradicts
            # the value the model read (boundary._event_coding_conflict); the
            # value is asked, never filled by the rules below
            missing.append("3")
        elif sorted(levels) == ["0", "1"]:
            ans["event_value"] = "1"
            src["event_value"] = "inferred: the column is 0/1, and 1 is the event"
        elif up == ["FALSE", "TRUE"]:
            ans["event_value"] = next(v for v in levels if v.upper() == "TRUE")
            src["event_value"] = ("inferred: the column is TRUE/FALSE, and TRUE "
                                  "is the event")
        else:
            missing.append("3")

    # ---- covariates: the second accepted default ------------------------
    if not ans.get("covariates"):
        if _presets(profile)["B"]:
            ans["covariates"] = "B"
            src["covariates"] = ("inferred: every usable numeric column that is "
                                 "not an outcome column")
        else:
            missing.append("4")

    # ---- time zero: always a person ------------------------------------
    if not ans.get("time_zero"):
        missing.append("6")

    # ---- time scale: CONTINUOUS TIME IS THE
    # DEFAULT and item 7 is never asked by the harness. a design decision after the
    # MIUM smoke (343 subjects, one-year administrative censoring, 34 distinct
    # days -- "coarse" by the old rule, and the question went out on every
    # prompt): the Cox row runs unless the analyst ASKS for discrete intervals
    # (a "7) <width> <K>" reply, before or after a run). When the settled time
    # column does sit on a coarse grid the default is DISCLOSED with the fact
    # that raised it, so the analyst can ask; an earlier answer for the same
    # file is remembered (above); a matched design has no time to bin.
    if ans.get("time") and not ans.get("discrete"):
        try:
            tcol = _resolve_one(profile, "time", ans["time"])
        except DeclarationError:
            tcol = None
        grid = (cols.get(tcol) or {}).get("time_grid") or {}
        if grid.get("coarse"):
            ans["discrete"] = "no"
            src["discrete"] = (f"default: continuous time; '{tcol}' takes "
                               f"{grid.get('n_distinct')} distinct values on a step of "
                               f"{_n(grid.get('step'))} -- reply '7) <width> <K>' (or "
                               f"'7) index') to analyse it as discrete intervals")

    return Completion(answers=ans, sources=src, missing=missing)


def _presets(profile: Dict[str, Any]) -> Dict[str, List[str]]:
    """Covariate presets. Computed from name-matching and type, not judgement."""
    cols = _by_name(profile)
    usable = [n for n in profile.get("eligible", {}).get("covariate", [])]
    matched = [n for n in usable if cols[n].get("matches_external")]
    return {"A": matched, "B": usable}


# -------------------------------------------------------------------- the reply
_LETTER = re.compile(r"^\s*([AB])\s*$", re.I)
_A_EDIT = re.compile(r"^\s*([AB])\s*(plus|minus|\+|-)\s*(.+)$", re.I)


def _resolve_one(profile: Dict[str, Any], kind: str, text: str) -> str:
    """Resolve a reply to a single column: an index into the list, or a name."""
    names = list(profile.get("eligible", {}).get(kind, []))
    all_names = list(_by_name(profile))
    item = {"stratum": "0", "time": "1", "event": "2"}.get(kind)
    t = (text or "").strip().strip(".,;")
    if not t:
        raise DeclarationError(f"no answer given for the {kind} column", item)
    if t.isdigit():
        i = int(t)
        if not (1 <= i <= len(names)):
            raise DeclarationError(
                f"'{t}' is not one of the {len(names)} options offered for the "
                f"{kind} column; reply with a number in range or the column name", item)
        return names[i - 1]
    exact = [n for n in all_names if n == t]
    if exact:
        return exact[0]
    ci = [n for n in all_names if n.lower() == t.lower()]
    if len(ci) == 1:
        return ci[0]
    if len(ci) > 1:
        raise DeclarationError(f"'{t}' matches more than one column: {ci}", item)
    raise DeclarationError(
        f"there is no column called '{t}'. The {kind} candidates are: "
        f"{', '.join(names) or '(none)'}", item)


def _resolve_covariates(profile: Dict[str, Any], text: str
                        ) -> Tuple[List[str], List[str], bool]:
    presets = _presets(profile)
    all_names = list(_by_name(profile))
    notes: List[str] = []
    t = (text or "").strip()
    if not t:
        raise DeclarationError("no answer given for the covariate set", "4")

    m = _LETTER.match(t)
    if m:
        key = m.group(1).upper()
        chosen = list(presets[key])
        if not chosen:
            raise DeclarationError(f"preset {key} is empty for this file; list the "
                                   f"column names you want instead", "4")
        return chosen, [f"covariates from preset {key}"], True

    m = _A_EDIT.match(t)
    if m:
        key, op, rest = m.group(1).upper(), m.group(2).lower(), m.group(3)
        chosen = list(presets[key])
        edits = [x.strip().strip(".,;") for x in re.split(r"[,;]| and ", rest) if x.strip()]
        for name in edits:
            hit = [n for n in all_names if n.lower() == name.lower()]
            if not hit:
                raise DeclarationError(f"there is no column called '{name}'", "4")
            if op in ("plus", "+"):
                if hit[0] not in chosen:
                    chosen.append(hit[0])
            else:
                if hit[0] not in chosen:
                    raise DeclarationError(
                        f"'{hit[0]}' is not in preset {key}, so it cannot be removed", "4")
                chosen.remove(hit[0])
        notes.append(f"preset {key} {op} {', '.join(edits)}")
        return chosen, notes, True

    names = [x.strip().strip(".,;") for x in re.split(r"[,;\n]| and ", t) if x.strip()]
    chosen = []
    for name in names:
        hit = [n for n in all_names if n.lower() == name.lower()]
        if not hit:
            from . import ablation
            if ablation.on("no_verify"):
                # ablation cell: the name the file lacks is dropped in silence
                notes.append(f"ablation no_verify: '{name}' is not a column and was dropped silently")
                continue
            raise DeclarationError(
                f"there is no column called '{name}'. Reply with a preset letter "
                f"or a comma-separated list of column names.", "4")
        if hit[0] not in chosen:
            chosen.append(hit[0])
    if not chosen:
        raise DeclarationError("no covariates could be resolved from that reply", "4")
    return chosen, notes + ["covariates listed explicitly"], False


_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _resolve_discrete(profile: Dict[str, Any], text: str, time_col: Optional[str]
                      ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Item 7; every refusal it raises names item 7 (see DeclarationError)."""
    try:
        return _resolve_discrete_(profile, text, time_col)
    except DeclarationError as exc:
        raise DeclarationError(str(exc), "7") from None


def _resolve_discrete_(profile: Dict[str, Any], text: str,
                      time_col: Optional[str]
                      ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Read the answer to item 7. Returns (spec, notes); spec is None for a
    continuous-time answer. Deterministic; the model is not involved.

    Accepted: 'no' / 'continuous'; '<width> <K>' in any wording that carries
    two numbers in that order ('7 53', 'width 7, 53 intervals'); 'index' or
    'index <K>' when the time column already holds the interval number.
    Words like 'weekly' are refused: the width must be in the units of the
    time column, which only the analyst knows.
    """
    t = (text or "").strip().strip(".,;").lower()
    if not t:
        raise DeclarationError("no answer given for the time scale (item 7)")
    if t in ("no", "n", "continuous", "not discrete", "none"):
        return None, ["time scale: continuous (item 7 answered no)"]
    if time_col is None:
        raise DeclarationError("a discrete-time analysis needs a follow-up "
                               "time column; a matched design has none")
    nums = [float(x) for x in _NUM.findall(t)]
    cols = _by_name(profile)
    if t.startswith("index") or "already" in t or "interval number" in t:
        summ = (cols.get(time_col) or {}).get("summary") or {}
        k = int(nums[0]) if nums else (int(round(float(summ["max"])))
                                       if summ.get("max") is not None else None)
        if k is None:
            raise DeclarationError("give the number of intervals K after 'index'")
        if k < 2:
            raise DeclarationError(f"K = {k}: a discrete-time model needs at "
                                   f"least two intervals")
        if summ and float(summ["max"]) > k + 1e-9:
            raise DeclarationError(
                f"'{time_col}' reaches {_n(summ['max'])} but K is {k}; an interval "
                f"index must lie in 1..K. Give the width instead if the column "
                f"is a time to be binned.")
        return ({"width": None, "n_intervals": k, "time_is_index": True},
                [f"time scale: '{time_col}' is the interval index 1..{k}"])
    if any(w in t for w in ("week", "month", "year", "day", "visit")) and len(nums) < 2:
        raise DeclarationError(
            "give the interval width IN THE UNITS OF THE TIME COLUMN and the "
            "number of intervals, e.g. '7 53' for 53 weekly intervals of a time "
            "in days; I cannot convert 'weekly' without knowing the unit")
    if len(nums) < 2:
        raise DeclarationError("item 7 needs two numbers: the interval width "
                               "(in the units of the time column) and the "
                               "number of intervals K, e.g. '7 53' -- or "
                               "'index' if the column already is the interval "
                               "number, or 'no' for a continuous time")
    width, k = nums[0], nums[1]
    if width <= 0:
        raise DeclarationError(f"the interval width must be positive (got {_n(width)})")
    if abs(k - round(k)) > 1e-9 or k < 2:
        raise DeclarationError(f"K must be a whole number of at least 2 (got {_n(k)})")
    return ({"width": width, "n_intervals": int(round(k)), "time_is_index": False},
            [f"time scale: {int(round(k))} intervals of width {_n(width)} on "
             f"'{time_col}'; interval k covers [(k-1) x {_n(width)}, k x "
             f"{_n(width)}), beyond the horizon censored at interval {int(round(k))}"])


def parse_reply(profile: Dict[str, Any], answers: Dict[str, str]) -> Declaration:
    """Turn the analyst's answers into a Declaration. No model involvement.

    `answers` keys: time, event, event_value, covariates, time_zero,
    external_model (optional), discrete (item 7, optional: absent means the
    continuous-time analysis).
    """
    # THE DESIGN IS DECLARED BY WHAT IS ANSWERED. Leaving the follow-up-time
    # question blank and naming a matched set is the nested case-control
    # declaration; answering both is a stratified cohort; answering time alone
    # is a plain cohort. There is no separate "which design is this?" field to
    # contradict the roles, which is the same reason time-zero is a question and
    # not a model output.
    t_ans = (answers.get("time") or "").strip()
    s_ans = (answers.get("stratum") or "").strip()
    if not t_ans and not s_ans:
        raise DeclarationError(
            "no answer given for the follow-up time column. If this is a nested "
            "case-control study there is no follow-up duration -- name the "
            "matched-set column instead and leave the time answer blank.", "1")
    stratum_col = _resolve_one(profile, "stratum", s_ans) if s_ans else None
    time_col = _resolve_one(profile, "time", t_ans) if t_ans else None
    event_col = _resolve_one(profile, "event", answers.get("event", ""))
    if time_col is None and stratum_col == event_col:
        raise DeclarationError(
            f"'{event_col}' was named as both the matched set and the "
            f"case indicator.")
    covariates, notes, from_preset = _resolve_covariates(
        profile, answers.get("covariates", ""))

    ev = (answers.get("event_value") or "").strip().strip(".,;")
    if not ev:
        raise DeclarationError("no answer given for which value means the event "
                              "occurred", "3")
    levels = [str(v) for v in (_by_name(profile)[event_col].get("values") or [])]
    from . import ablation
    if levels and ev not in levels and not ablation.on("no_verify"):
        raise DeclarationError(
            f"'{ev}' does not occur in '{event_col}'. Its values are "
            f"{' and '.join(levels)}.", "3")
    if levels and ev not in levels:
        notes.append(f"ablation no_verify: event value '{ev}' occurs nowhere in "
                     f"'{event_col}' and was passed on unchecked")

    tz = (answers.get("time_zero") or "").strip().lower() or None
    if tz is not None and tz not in ("yes", "no", "unsure"):
        raise DeclarationError("answer the time-zero question with yes, no, or "
                              "unsure", "6")

    # The presets are computed from the profile alone, before anyone has said
    # which column is the outcome, so "every usable numeric column" necessarily
    # includes the follow-up time and the event indicator. Drop them here.
    #
    # This is arithmetic, not inference -- a column cannot be both the outcome
    # and a predictor of itself. But it applies ONLY to a preset. An analyst who
    # typed the outcome column into an explicit list has made a real mistake, and
    # `verify` refuses it rather than quietly correcting them.
    if from_preset:
        # the matched set is structure, not a predictor; it joins the outcome
        # columns as something a preset must not sweep in
        overlap = [c for c in covariates
                   if c is not None and c in (time_col, event_col, stratum_col)]
        if overlap:
            covariates = [c for c in covariates if c not in overlap]
            notes.append("the outcome columns (" + ", ".join(overlap) +
                         ") were excluded from the preset")

    if time_col is None:
        notes.append("declared as a nested case-control design: no follow-up "
                     f"duration, matched sets in '{stratum_col}'")
    elif stratum_col:
        notes.append(f"stratified cohort: strata in '{stratum_col}'")

    # item 7: absent means continuous; "no" is recorded as a note so
    # the card shows the question was answered
    disc: Optional[Dict[str, Any]] = None
    if (answers.get("discrete") or "").strip():
        disc, dn = _resolve_discrete(profile, answers["discrete"], time_col)
        notes += dn

    return Declaration(time_col=time_col, event_col=event_col, event_value=ev,
                       covariates=covariates, source="reply",
                       stratum_col=stratum_col,
                       external_data_expr=(answers.get("external_data_expr")
                                           or None),
                       external_data_path=(answers.get("external_data_path")
                                           or None),
                       external_model=answers.get("external_model"),
                       covariates_time_zero=tz, notes=notes,
                       interval_width=(disc or {}).get("width"),
                       n_intervals=(disc or {}).get("n_intervals"),
                       time_is_interval_index=bool((disc or {}).get("time_is_index")))


# ------------------------------------------------------------------- path 1
def from_dictionary(profile: Dict[str, Any]) -> Optional[Declaration]:
    """Skip the question ONLY when the dictionary leaves no choice to make.

    Returns None whenever a judgement would be required, which on real
    dictionaries is the usual case -- see the module docstring.
    """
    dic = profile.get("dictionary", {})
    if not dic.get("present"):
        return None
    # A dictionary can narrow the outcome columns; it cannot answer the design
    # question, and skipping the question on data that looks matched would
    # decide the design by omission.
    if profile.get("possible_ncc"):
        return None
    outcome_ish = set(dic.get("outcome_ish", []))
    if not outcome_ish:
        return None
    elig = profile.get("eligible", {})
    times = [n for n in elig.get("time", []) if n in outcome_ish]
    events = [n for n in elig.get("event", []) if n in outcome_ish]
    if len(times) != 1 or len(events) != 1:
        return None
    # A complement pair is only a choice while BOTH members are still on the
    # table. If the dictionary set one of them aside -- as a quality flag, say --
    # then it has resolved the ambiguity and there is nothing left to choose.
    still_eligible = set(elig.get("event", []))
    for pair in profile.get("complementary_pairs", []):
        if events[0] in (pair[0], pair[1]):
            other = pair[1] if events[0] == pair[0] else pair[0]
            if other in still_eligible:
                return None
    levels = [str(v) for v in (_by_name(profile)[events[0]].get("values") or [])]
    if sorted(levels) != ["0", "1"]:
        return None
    covariates = _presets(profile)["A"] or _presets(profile)["B"]
    # The presets are computed from the profile alone, BEFORE anyone has said
    # which column is the outcome, so "every usable numeric column" necessarily
    # contains the follow-up time and the event indicator. `parse_reply` strips
    # them; this path did not, so every declaration it produced was refused by
    # verify with `outcome_used_as_covariate` -- the dictionary shortcut could
    # not produce a runnable analysis at all. Arithmetic, not inference: a
    # column cannot be both the outcome and a predictor of itself.
    notes = ["the data dictionary left exactly one eligible time column and one "
             "eligible 0/1 event column, so nothing had to be chosen"]
    overlap = [c for c in covariates if c in (times[0], events[0])]
    if overlap:
        covariates = [c for c in covariates if c not in overlap]
        notes.append("the outcome columns (" + ", ".join(overlap) +
                     ") were excluded from the preset")
    if not covariates:
        return None
    return Declaration(
        time_col=times[0], event_col=events[0], event_value="1",
        covariates=covariates, source="dictionary", notes=notes)


# ------------------------------------------------------------------ verification
@dataclass
class Verification:
    """The consequence card, plus whatever the gate refused."""
    admissible: bool
    card: List[str]
    refusals: List[Dict[str, Any]] = field(default_factory=list)
    advisories: List[Dict[str, Any]] = field(default_factory=list)
    gate: Optional[Dict[str, Any]] = None

    def render(self) -> str:
        out = list(self.card)
        if self.refusals:
            out.append("")
            out.append("This cannot be analysed as declared:")
            for r in self.refusals:
                out.append(f"  - {r['message']}")
                d = r.get("detail")
                if d:
                    out.append(f"    ({d})")
        for a in self.advisories:
            out.append("")
            out.append(f"Note: {a['message']}")
        return "\n".join(out)


def _own_checks(profile: Dict[str, Any], decl: Declaration) -> List[Dict[str, Any]]:
    """Refusals the gate cannot see, because they are about the DECLARATION."""
    bad: List[Dict[str, Any]] = []
    if decl.time_col is None and not decl.stratum_col:
        # run_candidates.R stops on this, but AFTER the analyst has approved a
        # configuration -- which inverts the whole fail-before-you-fit design.
        bad.append({"code": "matched_set_undeclared",
                    "message": "No follow-up time was declared, which declares a "
                               "matched design, but no matched-set column was "
                               "named. A matched analysis cannot be fitted "
                               "without knowing which rows belong together.",
                    "detail": None})
    if decl.stratum_col and decl.stratum_col in (decl.time_col, decl.event_col):
        # Placed in _own_checks rather than parse_reply so it also covers a
        # Declaration built directly or by from_dictionary. A column cannot be
        # both the grouping and the thing grouped: as a matched set it would put
        # every subject with the same outcome in one set, which the conditional
        # likelihood then estimates nothing from.
        bad.append({"code": "stratum_is_outcome",
                    "message": f"'{decl.stratum_col}' was named as both the "
                               f"grouping column and one of the outcome "
                               f"columns.",
                    "detail": None})
    if decl.time_col is not None and decl.time_col == decl.event_col:
        bad.append({"code": "time_is_event",
                    "message": f"'{decl.time_col}' was named as both the "
                               f"follow-up time and the event indicator.",
                    "detail": None})
    if decl.has_test_data and decl.time_col is None:
        # test_eval is the Cox family's evaluator; the matched design has no
        # follow-up time and no held-out evaluator in the library
        bad.append({"code": "test_data_needs_cohort",
                    "message": "Test data was supplied for a matched design; "
                               "the held-out evaluation exists for the "
                               "full-cohort family only.",
                    "detail": None})
    if decl.discrete and decl.has_test_data:
        bad.append({"code": "test_data_needs_cox_row",
                    "message": "Test data was supplied with a discrete-time "
                               "declaration; the held-out evaluation exists for "
                               "the continuous-time (Cox) row only.",
                    "detail": None})
    if decl.discrete:
        # the discrete-time row exists for cohort designs only: there is no
        # follow-up time to bin in a matched design, and no grouped
        # conditional-likelihood estimator in the library
        if decl.time_col is None:
            bad.append({"code": "discrete_needs_followup_time",
                        "message": "A discrete-time analysis was declared but "
                                   "no follow-up time column: a matched design "
                                   "has no duration to cut into intervals.",
                        "detail": None})
        if decl.n_intervals is not None and decl.n_intervals < 2:
            bad.append({"code": "discrete_k_too_small",
                        "message": f"K = {decl.n_intervals}: a discrete-time "
                                   f"model needs at least two intervals.",
                        "detail": None})
        if (not decl.time_is_interval_index
                and (decl.interval_width is None or decl.interval_width <= 0)):
            bad.append({"code": "discrete_width_invalid",
                        "message": "The interval width must be a positive "
                                   "number in the units of the time column.",
                        "detail": None})
    overlap = [c for c in decl.covariates
               if c is not None and c in (decl.time_col, decl.event_col)]
    if overlap:
        # The gate never catches this: a numeric outcome column is a perfectly
        # valid-looking covariate, and using the outcome to predict itself would
        # produce a spectacular, meaningless fit.
        bad.append({"code": "outcome_used_as_covariate",
                    "message": "The outcome is also listed among the predictors, "
                               "so the model would be predicting the outcome from "
                               "itself.",
                    "detail": ", ".join(overlap)})
    # The strata column is not the outcome (2026-09-30: the refusal used to say it
    # was). It is constant within each stratum, so once every stratum has its own
    # baseline hazard its effect cannot be estimated.
    if decl.stratum_col is not None and decl.stratum_col in decl.covariates:
        bad.append({"code": "stratum_used_as_covariate",
                    "message": "The column that defines the strata (or matched sets) "
                               "is also listed among the predictors. It is constant "
                               "within each stratum, so its effect cannot be estimated "
                               "once each stratum has its own baseline hazard.",
                    "detail": decl.stratum_col})
    for pair in profile.get("complementary_pairs", []):
        if decl.event_col in (pair[0], pair[1]):
            other = pair[1] if decl.event_col == pair[0] else pair[0]
            # not a refusal: one of the two IS correct. Say it out loud instead.
            bad.append({"code": "_advisory_complement",
                        "message": f"'{decl.event_col}' is the exact complement of "
                                   f"'{other}'. Check the event count below: if it "
                                   f"is the wrong way round you have the other "
                                   f"column.",
                        "detail": None})
    return bad


def verify(profile: Dict[str, Any], decl: Declaration, data_path: str,
           data_expr: str, run_r=None,
           external_baseline: Optional[Dict[str, List[float]]] = None
           ) -> Verification:
    """Check a declaration against the data and produce the consequence card.

    Declaration is not blind acceptance. The card states the consequences as
    numbers the analyst can falsify -- "200 subjects, 50 events (25%)" -- and that,
    not the column name, is the safety mechanism. An analyst who named the
    complement of the event column sees 75% and rejects it instantly.

    `run_r` is injected so this is testable without the MCP server; it defaults to
    the server's own dispatcher. `external_baseline` is the external
    model's baseline hazard as M5 read it (`{time, hazard, cumhaz}`), used by
    the gate ONLY to check that it covers the declared horizon when the
    discrete-time row was declared; it never raises the question.
    """
    cols = _by_name(profile)
    own = _own_checks(profile, decl)
    refusals = [r for r in own if not r["code"].startswith("_advisory")]
    advisories = [{"code": r["code"][10:], "message": r["message"]}
                  for r in own if r["code"].startswith("_advisory")]

    n = profile["n_rows"]
    # a declared column that is not in the profile is a refusal, not a crash
    ev = cols.get(decl.event_col) or {"type": "unknown", "n_distinct": 0}
    ncc = decl.time_col is None

    def how(role: str) -> str:
        # the source of each role, when the harness settled any of them
        s = (decl.sources or {}).get(role)
        return f"   <- {s}" if s else ""

    card = [
        ("This is what was settled, and what it means for the data:"
         if decl.sources else
         "This is what you have declared, and what it means for the data:"),
        "",
        f"  study design      {decl.design}",
    ]
    if ncc:
        # The column may be absent, and this is EXACTLY the declaration
        # `_own_checks` exists to refuse: no follow-up time (so, matched) and no
        # matched set either. Looking it up unguarded raised KeyError(None) and
        # took the whole verify call down -- so the refusal that was written
        # for this case could never reach the analyst, and what they saw was a
        # stack trace instead of a sentence telling them what to fix.
        if decl.stratum_col:
            card.append(f"  matched set       {decl.stratum_col}   "
                        f"[{_fmt_col(cols[decl.stratum_col])}]")
        else:
            card.append("  matched set       (not declared)")
        card.append(f"  case indicator    {decl.event_col}   "
                    f"[{_fmt_col(ev, show_values=True)}]{how('event')}")
        card.append(f"  a case is {decl.event_col} = {decl.event_value}"
                    f"{how('event_value')}")
    else:
        card.append((f"  follow-up time    {decl.time_col}   "
                     f"[{_fmt_col(cols[decl.time_col])}]"
                     if decl.time_col in cols else
                     f"  follow-up time    {decl.time_col}   (not in this file)")
                    + how("time"))
        card.append(f"  event indicator   {decl.event_col}   "
                    f"[{_fmt_col(ev, show_values=True)}]{how('event')}")
        card.append(f"  event occurred when {decl.event_col} = {decl.event_value}"
                    f"{how('event_value')}")
        if decl.stratum_col and decl.stratum_col in cols:
            card.append(f"  strata            {decl.stratum_col}   "
                        f"[{_fmt_col(cols[decl.stratum_col])}]{how('stratum')}")
        if decl.discrete:
            # THE GRID IS PART OF THE MODEL (ruling 1): stated on the card
            # like the event value, with the binning rule, so the analyst
            # can falsify it from the counts the gate adds below
            if decl.time_is_interval_index:
                card.append(f"  time scale        discrete: '{decl.time_col}' "
                            f"is the interval index 1..{decl.n_intervals}"
                            f"{how('discrete')}")
            else:
                w = _n(decl.interval_width)
                card.append(f"  time scale        discrete: {decl.n_intervals} "
                            f"intervals of width {w}; interval k covers "
                            f"[(k-1) x {w}, k x {w}) of '{decl.time_col}'; "
                            f"beyond {decl.n_intervals} x {w} censored at "
                            f"interval {decl.n_intervals}{how('discrete')}")
        elif ((cols.get(decl.time_col) or {}).get("time_grid") or {}).get("coarse"):
            # the default, disclosed where the data could have suggested
            # otherwise
            card.append(f"  time scale        continuous (the default){how('discrete')}")
    card += [
        f"  predictors        {len(decl.covariates)}: "
        f"{', '.join(decl.covariates[:12])}"
        + (f", ... (+{len(decl.covariates) - 12} more)"
           if len(decl.covariates) > 12 else "") + how("covariates"),
        f"  subjects          {n}",
    ]
    if decl.covariates_time_zero:
        card.append(f"  known at time zero  {decl.covariates_time_zero}"
                    f"{how('time_zero')}")

    gate = None
    if run_r is None:
        try:
            from .rbridge import _run_r as run_r
        except Exception:
            run_r = None

    # A declaration that failed its OWN checks is not taken to the data.
    # `_own_checks` refuses things that are wrong about the declaration itself
    # -- the outcome listed as its own predictor, a matched design with no
    # matched set -- and such a declaration cannot even be turned into R
    # expressions: `as_exprs` builds `D[[None]]` and dies. The analyst then got
    # a stack trace instead of the sentence that was written to tell them what
    # to fix. Nothing is lost by stopping here: the gate answers questions about
    # the DATA, and there is no coherent question to ask yet.
    if run_r is not None and not refusals:
        exprs = decl.as_exprs(data_expr)
        payload = {"data_path": data_path, **exprs,
                   "event_value": decl.event_value}
        if decl.covariates_time_zero:
            payload["covariates_time_zero"] = decl.covariates_time_zero
        if decl.has_test_data:
            payload["test_data"] = decl.test_spec()
        if decl.discrete:
            payload["discrete"] = decl.discrete_spec()
            if external_baseline and external_baseline.get("time"):
                payload["baseline_inline"] = {
                    "time": list(external_baseline["time"]),
                    "cumhaz": list(external_baseline["cumhaz"])}
        gate = run_r("check_admissibility.R", payload)
        if gate.get("status") == "ok":
            s = gate.get("summary", {})
            if s.get("n_events") is not None:
                rate = s.get("event_rate")
                label = "cases" if decl.time_col is None else "events"
                card.append(f"  {label:<17} {s['n_events']} of {s['n_obs']}"
                            + (f" ({rate * 100:.0f}%)" if rate is not None else ""))
            fu = s.get("followup")
            if fu:
                card.append(f"  follow-up         median {_n(fu['median'])} "
                            f"(range {_n(fu['min'])} to {_n(fu['max'])})")
            # THE FALSIFICATION NUMBER FOR A MATCHED DESIGN.
            # Under a cohort, the analyst catches a complement mix-up from the
            # event RATE -- 25% against 75%. Under a matched design the rate is
            # the sampling ratio, fixed by the study's own construction, so it
            # cannot falsify anything: naming the wrong column still gives a
            # plausible-looking number. What the wrong column DOES break is the
            # one-case-per-set structure, and that is checkable.
            # Only under a MATCHED design. The gate populates `matched_sets`
            # for a stratified cohort too -- it has strata, so the numbers
            # exist -- but "sets with exactly one case" is a statement about 1:m
            # sampling and means nothing for a cohort that happens to be
            # stratified by centre. Printing it there would invite an analyst to
            # reject a perfectly good declaration.
            td = s.get("test_data") if decl.has_test_data else None
            if td:
                # the held-out rows the analyst supplied: how many, how many
                # events -- the number that says whether the file is what
                # they think it is (a test file with two events cannot carry
                # a C-index anyone should read)
                import os as _os
                card.append(f"  test data         "
                            f"{_os.path.basename(str(decl.test_data_path or decl.test_data_expr))}: "
                            f"{td['n_obs']} subjects, {td['n_events']} events"
                            + (f" ({td['event_rate'] * 100:.0f}%)" if td.get("event_rate") is not None else "")
                            + "   <- supplied by you; used only to report held-out "
                              "performance, never to choose the model")
            ds = s.get("discrete") if decl.discrete else None
            if ds:
                # the falsification numbers for the grid: how many were cut
                # off at the horizon, how the events spread over the intervals
                card.append(f"  intervals         {ds['n_intervals']}; "
                            f"{ds['n_beyond_horizon']} subject(s) observed past "
                            f"the horizon and censored at interval "
                            f"{ds['n_intervals']}; events per interval "
                            f"{_n(ds['events_min'])} to {_n(ds['events_max'])}"
                            + (f"; {len(ds['intervals_without_events'])} "
                               f"interval(s) with no event"
                               if ds.get("intervals_without_events") else ""))
                bc = ds.get("baseline")
                if bc:
                    card.append(f"  external baseline {bc['status']}: "
                                f"{bc['detail']}")
            ms = s.get("matched_sets") if decl.time_col is None else None
            if ms:
                card.append(f"  matched sets      {ms['n_strata']}, sizes "
                            f"{_n(ms['min_size'])} to {_n(ms['max_size'])} "
                            f"(median {_n(ms['median_size'])})")
                card.append(f"  sets with exactly one case   "
                            f"{ms['n_one_case']} of {ms['n_strata']}")
            refusals += gate.get("refusals", [])
            advisories += gate.get("advisories", [])
        else:
            refusals.append({"code": "gate_failed",
                             "message": "The data could not be checked: "
                                        + str(gate.get("message"))[:200],
                             "detail": None})

    if decl.notes:
        card.append("")
        card.append("  (" + "; ".join(decl.notes) + ")")

    return Verification(admissible=not refusals, card=card, refusals=refusals,
                        advisories=advisories, gate=gate)
