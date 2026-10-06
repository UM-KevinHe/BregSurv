"""M5: reading external information. Flexible about FORMAT, rigid about MEANING.

The pipeline takes external information in exactly one shape
(:class:`ExternalObject`). Analysts hand it over in every shape there is: a
two-column csv, a paper's table with hazard ratios and confidence intervals, an
xlsx with the covariance on a second sheet, an R list saved as .rds, a JSON
dictionary, the SRTR release tables, another cohort's rows. This module turns
any of those into the one shape, in three steps:

  1. READ      deterministic. Any supported file -> a list of raw tables, each
               described by column names, types and ranges. Nothing else.
  2. ASSIGN    the model, once, by constrained decoding: for each table, what
               it is (coefficients / covariance / precision / baseline hazard /
               individual-level data / ignore) and which column holds what
               (the name, the coefficient, whether that is a hazard ratio or a
               log hazard ratio, a standard error, a confidence interval, a
               time, a hazard). It names columns; it never reads a number, and
               it is never shown a row.
  3. VERIFY    deterministic. Every column the model named must exist. Names
               unique. Numbers finite. A hazard ratio positive before it is
               logged. A confidence interval must bracket its estimate. A
               covariance must be square, symmetric, positive semidefinite and
               carry the coefficient names. A cumulative hazard must be
               monotone and equal to the running sum of the hazard. Any failure
               REFUSES the whole object with the reason; nothing is repaired.

Scope: the agent does not do data processing. It does
not put the external information on the cohort's scale, rebuild a spline
basis, or reduce a per-level table to per-variable coefficients; the analyst
does that before uploading, and a file that has not been reduced is refused
with a message that says so. Two conversions ARE done here because they are
two printings of the same number, not two numbers: a published hazard ratio is
logged, and a published covariance is inverted to the precision matrix the
Mahalanobis penalty takes (`cox_MDTL` documents `Q` as a precision matrix).
Both are recorded in the object's provenance and disclosed in the report. A
standard-error column is recorded and disclosed; it is NOT turned into a
diagonal covariance, because that would assert independence the analyst never
claimed.

`read_external` is the single entry point. Without a model it falls back to
:func:`heuristic_assignment`, which accepts only the shapes it can name without
guessing (a two-column table; recognisable headers) and refuses the rest.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import policy

FORMS = ("coefficients", "coefficients_with_covariance",
         "coefficients_with_baseline_hazard", "individual_level_data")
ROLES = ("coefficients", "covariance", "precision", "baseline_hazard",
         "individual_level_data", "ignore")
SCALES = ("log_hazard_ratio", "hazard_ratio")
_MAX_TABLES = 8
_REL_TOL = 1e-6


class ExternalRefusal(ValueError):
    """The file could not be read as external information, and why not."""

    def __init__(self, reasons: List[Dict[str, Any]]):
        self.reasons = reasons
        super().__init__("; ".join(r["message"] for r in reasons))


# ------------------------------------------------------------------ 1. READ
@dataclass
class RawTable:
    name: str
    columns: List[Dict[str, Any]]
    n_rows: int
    frame: Any = field(repr=False)          # a pandas DataFrame
    source: str = ""                        # sheet / object / key it came from

    def col(self, name: Optional[str]):
        if name is None or name not in self.frame.columns:
            return None
        return self.frame[name]


def _describe(df) -> List[Dict[str, Any]]:
    """Column facts the model is shown: name, type, missing, distinct, range.
    Never a row."""
    import pandas as pd
    out = []
    for c in df.columns:
        v = df[c]
        rec: Dict[str, Any] = {"name": str(c), "n_missing": int(v.isna().sum()),
                               "n_distinct": int(v.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(v):
            rec["type"] = "numeric"
            vv = v.dropna()
            if len(vv):
                rec["summary"] = {"min": float(vv.min()),
                                  "median": float(vv.median()),
                                  "max": float(vv.max())}
        else:
            rec["type"] = "text"
            rec["max_len"] = int(v.dropna().astype(str).str.len().max()) if len(v.dropna()) else 0
        out.append(rec)
    return out


def _table(name: str, df, source: str = "") -> RawTable:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return RawTable(name=name, columns=_describe(df), n_rows=int(len(df)),
                    frame=df, source=source)


def _from_json(obj: Any, name: str) -> List[RawTable]:
    import pandas as pd
    out: List[RawTable] = []
    if isinstance(obj, dict):
        if obj and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       for v in obj.values()):
            df = pd.DataFrame({"name": list(obj), "value": list(obj.values())})
            out.append(_table(name, df, "json object of numbers"))
        elif obj and all(isinstance(v, dict) for v in obj.values()):
            # {"age": {"coef": ..., "se": ...}, ...} -> one row per key
            df = pd.DataFrame.from_dict(obj, orient="index").reset_index()
            df = df.rename(columns={"index": "name"})
            out.append(_table(name, df, "json object of records"))
        else:
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    out.extend(_from_json(v, f"{name}.{k}"))
    elif isinstance(obj, list) and obj and all(isinstance(r, dict) for r in obj):
        out.append(_table(name, pd.DataFrame(obj), "json list of records"))
    elif isinstance(obj, list) and obj and all(isinstance(r, list) for r in obj):
        out.append(_table(name, pd.DataFrame(obj), "json list of rows"))
    return out


def read_tables(path: str, run_r=None) -> List[RawTable]:
    """Every table a file holds, with column facts. Deterministic.

    csv / tsv / txt -> one table. xlsx / xls -> one per sheet. json -> one per
    object of numbers, of records, or list of records. rds / rda / RData -> one
    per data.frame, matrix or named vector found (one level into lists), via
    `read_external.R`. parquet if pyarrow is installed. Anything else, or a pdf,
    is refused with a message naming what to export instead.
    """
    import pandas as pd
    p = Path(path)
    if not p.exists():
        raise ExternalRefusal([{"code": "file_missing",
                                "message": f"the file does not exist: {path}"}])
    ext = p.suffix.lower().lstrip(".")
    stem = p.stem
    tables: List[RawTable] = []
    try:
        if ext in ("csv", "tsv", "txt"):
            df = pd.read_csv(p, sep=None, engine="python")
            tables.append(_table(stem, df, f"{ext} file"))
        elif ext in ("xlsx", "xlsm", "xls"):
            try:
                sheets = pd.read_excel(p, sheet_name=None)
            except ImportError as exc:
                raise ExternalRefusal([{"code": "reader_missing",
                                        "message": "reading .xlsx needs the "
                                                   "openpyxl package: "
                                                   f"{exc}"}])
            for sname, df in sheets.items():
                tables.append(_table(f"{stem}:{sname}", df, f"sheet {sname!r}"))
        elif ext == "json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            tables.extend(_from_json(obj, stem))
        elif ext == "parquet":
            try:
                tables.append(_table(stem, pd.read_parquet(p), "parquet file"))
            except ImportError as exc:
                raise ExternalRefusal([{"code": "reader_missing",
                                        "message": "reading .parquet needs "
                                                   f"pyarrow: {exc}"}])
        elif ext in ("rds", "rda", "rdata"):
            if run_r is None:
                from .rbridge import _run_r as run_r
            td = tempfile.mkdtemp(prefix="bregsurv_ext_")
            res = run_r("read_external.R", {"path": str(p), "out_dir": td})
            if res.get("status") != "ok":
                raise ExternalRefusal([{"code": "r_read_failed",
                                        "message": "R could not read the file: "
                                                   + str(res.get("message"))[:300]}])
            for t in res.get("tables", []):
                df = pd.read_csv(t["csv"])
                tables.append(_table(f"{stem}:{t['name']}", df,
                                     f"R {t['kind']} {t['name']!r}"))
        elif ext == "pdf":
            raise ExternalRefusal([{"code": "unsupported_format",
                                    "message": "pdf is not read; export the "
                                               "table to csv or xlsx and upload "
                                               "that"}])
        else:
            raise ExternalRefusal([{"code": "unsupported_format",
                                    "message": f"'.{ext}' is not a format this "
                                               "reads: csv, tsv, xlsx, json, "
                                               "rds, rda, parquet"}])
    except ExternalRefusal:
        raise
    except Exception as exc:                     # a parser error, verbatim
        raise ExternalRefusal([{"code": "parse_failed",
                                "message": f"the file could not be parsed as "
                                           f".{ext}: {type(exc).__name__}: "
                                           f"{str(exc)[:200]}"}])
    tables = [t for t in tables if t.n_rows > 0 and len(t.columns) > 0]
    if not tables:
        raise ExternalRefusal([{"code": "no_tables",
                                "message": "no table with rows was found in "
                                           "the file"}])
    if len(tables) > _MAX_TABLES:
        raise ExternalRefusal([{"code": "too_many_tables",
                                "message": f"the file holds {len(tables)} "
                                           f"tables; at most {_MAX_TABLES} are "
                                           "read -- keep the ones that matter"}])
    return tables


def _fmt_num(x: float) -> str:
    return f"{x:g}"


def summarize(tables: List[RawTable]) -> str:
    """What the model is shown. Column facts only."""
    out = []
    for t in tables:
        out.append(f"Table {t.name!r} ({t.source}; {t.n_rows} rows, "
                   f"{len(t.columns)} columns):")
        for c in t.columns:
            bits = [c["type"]]
            if c.get("summary"):
                s = c["summary"]
                bits.append(f"min {_fmt_num(s['min'])} / median "
                            f"{_fmt_num(s['median'])} / max {_fmt_num(s['max'])}")
            else:
                bits.append(f"{c['n_distinct']} distinct")
            if c.get("n_missing"):
                bits.append(f"{c['n_missing']} missing")
            out.append(f"  - {c['name']}   [{', '.join(bits)}]")
    return "\n".join(out)


# ---------------------------------------------------------------- 2. ASSIGN
def _nullable(enum: Optional[Tuple[str, ...]] = None) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": "string"}
    if enum:
        s["enum"] = list(enum)
    return {"anyOf": [s, {"type": "null"}]}


_COLUMN_FIELDS = ("name_column", "coefficient_column", "se_column",
                  "ci_lower_column", "ci_upper_column", "time_column",
                  "hazard_column", "cumulative_hazard_column", "event_column")

ASSIGNMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "tables": {
            "type": "array", "minItems": 1, "maxItems": _MAX_TABLES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "table": {"type": "string"},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "name_column": _nullable(),
                    "coefficient_column": _nullable(),
                    "coefficient_scale": _nullable(SCALES),
                    "se_column": _nullable(),
                    "ci_lower_column": _nullable(),
                    "ci_upper_column": _nullable(),
                    "time_column": _nullable(),
                    "hazard_column": _nullable(),
                    "cumulative_hazard_column": _nullable(),
                    "event_column": _nullable(),
                    "event_value": _nullable(),
                },
                "required": ["table", "role", "name_column", "coefficient_column",
                             "coefficient_scale", "se_column", "ci_lower_column",
                             "ci_upper_column", "time_column", "hazard_column",
                             "cumulative_hazard_column", "event_column",
                             "event_value"],
            },
        },
    },
    "required": ["reasoning", "tables"],
}

# Component 2: policies/external_roles.md.
_ASSIGN_SYSTEM = policy.load("external_roles")


def assignment_schema_for(tables: List[RawTable]) -> Dict[str, Any]:
    """The assignment schema with `table` an enum of the file's own table
    names. An R object's tables are named `file:object$element`, which the
    model reproduced wrongly on every .rds fixture (release-reading
    experiment, 2026-09-14: 9 of 15 .rds files refused as `unknown_table`);
    the grammar now admits only names that exist, as the intent schema does
    for the loaded releases."""
    import copy
    sch = copy.deepcopy(ASSIGNMENT_SCHEMA)
    names = [t.name for t in tables]
    if names:
        sch["properties"]["tables"]["items"]["properties"]["table"] = {"type": "string", "enum": names}
    return sch


def assign_roles(client, model: str, tables: List[RawTable]) -> Dict[str, Any]:
    """One constrained call. A proposal; :func:`check_assignment` verifies it."""
    from . import boundary
    from . import release_examples
    summ = summarize(tables)
    prefix, rec = release_examples.for_tables(summ)
    user = prefix + "Tables in the file:\n\n" + summ
    return boundary._chat(client, model, _ASSIGN_SYSTEM, user, assignment_schema_for(tables),
                          "external_roles", max_tokens=900,
                          extra_record={"release_examples": rec} if rec else None)


_NAME_HEADS = ("variable", "term", "name", "covariate", "predictor", "parameter",
               "feature", "var")
_COEF_HEADS = ("coefficient", "coef", "beta", "estimate", "loghr", "log_hr",
               "log_hazard_ratio", "value", "est")
_HR_HEADS = ("hr", "hazard_ratio", "hazardratio", "exp(coef)", "exp_coef")
_SE_HEADS = ("se", "std_error", "std.error", "stderr", "se(coef)", "std_err")
_LOW_HEADS = ("lower", "ci_lower", "lcl", "low", "2.5%", "lower95", "ci_low")
_UPP_HEADS = ("upper", "ci_upper", "ucl", "high", "97.5%", "upper95", "ci_high")


def _match_head(cols: List[str], heads: Tuple[str, ...]) -> Optional[str]:
    norm = {re.sub(r"[\s_\-.()%]", "", c.lower()): c for c in cols}
    for h in heads:
        k = re.sub(r"[\s_\-.()%]", "", h.lower())
        if k in norm:
            return norm[k]
    return None


def _match_sub(cols: List[str], subs: Tuple[str, ...]) -> Optional[str]:
    """A header CONTAINING one of `subs` ("95% CI lower" -> lower)."""
    for c in cols:
        k = re.sub(r"[\s_\-.()%]", "", c.lower())
        if any(sub in k for sub in subs):
            return c
    return None


def heuristic_assignment(tables: List[RawTable],
                         cohort_columns: Optional[List[str]] = None,
                         cohort_outcome: Optional[Tuple[str, str]] = None) -> Dict[str, Any]:
    """The no-model path: only what can be named without guessing.

    A single table with exactly two columns, one text and one numeric, is a
    coefficient table on the log scale (today's behaviour). A table whose
    headers are recognisable (`variable`/`coef`/`hr`/`se`/`lower`/`upper`,
    `time`/`hazard`/`cumulative_hazard`) is typed from them. A table that
    carries the cohort's own outcome columns by name and only columns of the
    cohort (or, when the outcome columns are not known, most of the cohort's
    columns), with more rows than columns, is another cohort's records (2026-09-13,
    for the model-free reference of the ablation benchmark; `cohort_outcome`
    = (time column, event column) of the declaring cohort, and the table's
    outcome columns are taken to be the same). Everything else is `ignore`,
    and :func:`canonicalise` then refuses for want of a coefficient table --
    with the advice to configure a model or reduce the file to two columns.
    """
    out = []
    for t in tables:
        cols = [c["name"] for c in t.columns]
        types = {c["name"]: c["type"] for c in t.columns}
        rec: Dict[str, Any] = {"table": t.name, "role": "ignore",
                               **{f: None for f in _COLUMN_FIELDS},
                               "coefficient_scale": None, "event_value": None}
        shared = sum(1 for c in cohort_columns if c in cols) if cohort_columns else 0
        carries_outcome = bool(cohort_outcome) and all(c in cols for c in cohort_outcome if c)
        laid_out_like_ours = bool(cohort_columns) and all(c in cohort_columns for c in cols)
        if (cohort_columns and len(cols) >= 3 and t.n_rows > len(cols)
                and (shared >= 0.8 * len(cohort_columns)
                     or (carries_outcome and (laid_out_like_ours or shared >= 0.5 * len(cohort_columns))))):
            # another cohort's records: its outcome columns are the declaring cohort's when
            # those are known, else the recognisable headers (time / event, status, died,
            # death, case, delta); `canonicalise` refuses if either is missing.
            # A table that carries our outcome columns by name is another cohort laid out
            # like ours when its every column is one of ours (however few of our covariates
            # it carries: METABRIC's NPI release has 3 of 12) or when it shares at least half
            # of our columns (Rotterdam's 8 of GBSG's 11, plus a term GBSG lacks) -- 2026-09-21,
            # the public benchmarks: a registry covers a subset of the target's variables,
            # which is the setting itself
            # a matched design declares (None, event): its records carry no duration, and
            # another matched sample laid out like it has none either
            matched = bool(cohort_outcome) and cohort_outcome[0] is None
            oc = (cohort_outcome if (cohort_outcome and all(c in cols for c in cohort_outcome if c))
                  else None)
            tcol_i = (None if matched else oc[0] if oc else
                      _match_head(cols, ("time", "t", "day", "days", "followup", "follow_up",
                                         "time_to_event", "survival_time", "os", "os_mo")))
            ecol_i = oc[1] if oc else _match_head(cols, ("event", "status", "died", "death", "case",
                                                         "delta", "event_flag", "outcome", "dead"))
            rec.update(role="individual_level_data", time_column=tcol_i, event_column=ecol_i)
            out.append(rec)
            continue
        tcol = _match_head(cols, ("time", "t", "day", "days"))
        hcol = _match_head(cols, ("hazard", "h", "baseline_hazard"))
        chcol = _match_head(cols, ("cumulative_hazard", "cumhaz", "cum_hazard",
                                   "cumulative"))
        ncol = _match_head(cols, _NAME_HEADS)
        ccol = _match_head(cols, _COEF_HEADS)
        hrcol = _match_head(cols, _HR_HEADS)
        if tcol and (hcol or chcol):
            rec.update(role="baseline_hazard", time_column=tcol,
                       hazard_column=hcol, cumulative_hazard_column=chcol)
        elif ncol and (ccol or hrcol):
            rec.update(role="coefficients", name_column=ncol,
                       coefficient_column=ccol or hrcol,
                       coefficient_scale=("log_hazard_ratio" if ccol
                                          else "hazard_ratio"),
                       se_column=_match_head(cols, _SE_HEADS),
                       ci_lower_column=(_match_head(cols, _LOW_HEADS)
                                        or _match_sub(cols, ("lower", "lcl"))),
                       ci_upper_column=(_match_head(cols, _UPP_HEADS)
                                        or _match_sub(cols, ("upper", "ucl"))))
        elif len(cols) == 2 and sorted(types[c] for c in cols) == ["numeric", "text"]:
            nm = next(c for c in cols if types[c] == "text")
            vc = next(c for c in cols if types[c] == "numeric")
            rec.update(role="coefficients", name_column=nm, coefficient_column=vc,
                       coefficient_scale="log_hazard_ratio")
        elif (len(cols) >= 2 and t.n_rows == sum(1 for c in cols if types[c] == "numeric")
              and (len(cols) == t.n_rows or
                   (len(cols) == t.n_rows + 1 and any(types[c] == "text" for c in cols)))):
            # square numeric block, optionally with a name column
            rec.update(role="covariance",
                       name_column=next((c for c in cols if types[c] == "text"), None))
        out.append(rec)
    return {"reasoning": "heuristic: recognisable headers only", "tables": out}


def check_assignment(tables: List[RawTable], raw: Dict[str, Any]
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Every column the model named must exist in that table. Deterministic.

    Returns (assignments, issues). An entry naming an unknown table is
    dropped; an entry naming an unknown column has that column set to null and
    the issue recorded, so that `canonicalise` refuses for the right reason
    ("no coefficient column") rather than crashing on a name.
    """
    by_name = {t.name: t for t in tables}
    issues: List[Dict[str, Any]] = []
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in (raw.get("tables") or []):
        if not isinstance(item, dict):
            continue
        tname = item.get("table")
        if tname not in by_name or tname in seen:
            issues.append({"code": "unknown_table", "table": tname,
                           "message": f"the model named a table that is not "
                                      f"in the file: {tname!r}"})
            continue
        seen.add(tname)
        cols = set(by_name[tname].frame.columns)
        rec = dict(item)
        if rec.get("role") not in ROLES:
            rec["role"] = "ignore"
        for f in _COLUMN_FIELDS:
            v = rec.get(f)
            if v is not None and v not in cols:
                issues.append({"code": "unknown_column", "table": tname,
                               "field": f, "message":
                               f"the model named {v!r} as the {f} of table "
                               f"{tname!r}, which has no such column"})
                rec[f] = None
        if rec.get("coefficient_scale") not in SCALES:
            rec["coefficient_scale"] = None
        # The headers are evidence the model does not get to overrule
        # (2026-09-13, ablation fixtures F13 and F04 under Qwen2.5). A column
        # headed `hazard_ratio` IS on the hazard-ratio scale, whatever the
        # model wrote; a table named `vcov` / `covariance` IS a covariance and
        # one named `precision` / `information` a precision. Each correction is
        # an issue in the provenance, so the report can say it happened.
        cc = rec.get("coefficient_column")
        if rec.get("role") == "coefficients" and cc:
            head_hr = _match_head([cc], _HR_HEADS) is not None
            head_log = _match_head([cc], _COEF_HEADS) is not None and not head_hr
            said = rec.get("coefficient_scale")
            if head_hr and said != "hazard_ratio":
                issues.append({"code": "scale_from_header", "table": tname,
                               "message": f"column {cc!r} is headed as a hazard ratio; the model "
                                          f"called it {said!r}, the header decides"})
                rec["coefficient_scale"] = "hazard_ratio"
            elif head_log and said == "hazard_ratio":
                issues.append({"code": "scale_from_header", "table": tname,
                               "message": f"column {cc!r} is headed as a coefficient on the log "
                                          f"scale; the model called it a hazard ratio, the header decides"})
                rec["coefficient_scale"] = "log_hazard_ratio"
            try:
                vals = by_name[tname].frame[cc].dropna().astype(float)
                if rec.get("coefficient_scale") == "hazard_ratio" and (vals <= 0).any():
                    issues.append({"code": "scale_impossible", "table": tname,
                                   "message": f"column {cc!r} holds values <= 0, which a hazard ratio cannot"})
            except (ValueError, TypeError, KeyError):
                pass
        if rec.get("role") in ("covariance", "precision"):
            tn = re.sub(r"[\s_\-.()]", "", str(tname).lower().split(".")[-1])
            by_name_cov = any(k in tn for k in ("vcov", "covariance", "cov"))
            by_name_prec = any(k in tn for k in ("precision", "information", "fisher", "inverse"))
            if by_name_cov and not by_name_prec and rec["role"] != "covariance":
                issues.append({"code": "matrix_role_from_name", "table": tname,
                               "message": f"table {tname!r} is named as a covariance; the model called "
                                          f"it a precision, the name decides"})
                rec["role"] = "covariance"
            elif by_name_prec and not by_name_cov and rec["role"] != "precision":
                issues.append({"code": "matrix_role_from_name", "table": tname,
                               "message": f"table {tname!r} is named as a precision; the model called "
                                          f"it a covariance, the name decides"})
                rec["role"] = "precision"
        out.append(rec)
    for t in tables:                      # tables the model did not mention
        if t.name not in seen:
            out.append({"table": t.name, "role": "ignore",
                        **{f: None for f in _COLUMN_FIELDS},
                        "coefficient_scale": None, "event_value": None})
    return out, issues


# ---------------------------------------------------------------- 3. VERIFY
@dataclass
class ExternalObject:
    """The one shape the pipeline takes. Built only by :func:`canonicalise`."""
    form: str
    scale: str                                   # always "log_hazard_ratio"
    terms: Dict[str, float]
    provenance: Dict[str, Any]
    Q: Optional[List[List[float]]] = None        # precision, in `terms` order
    Q_from: Optional[str] = None                 # "precision as published" | "inverse of the published covariance"
    se: Optional[Dict[str, float]] = None        # disclosed, never used
    baseline_hazard: Optional[Dict[str, List[float]]] = None
    individual_data: Optional[Dict[str, Any]] = None
    linkage: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def pipeline_kwargs(self) -> Dict[str, Any]:
        """What `pipeline.run` takes. The precision travels BY VALUE so the C3
        hash covers the numbers, exactly as the coefficients do."""
        kw: Dict[str, Any] = {}
        if self.individual_data:
            return kw            # the declaration carries the path and exprs
        kw["external_beta_inline"] = dict(self.terms)
        if self.Q is not None:
            kw["external_Q_inline"] = [list(r) for r in self.Q]
        if self.baseline_hazard:
            # : by value too; the discrete-time row is what reads it
            kw["external_baseline_inline"] = {
                "time": list(self.baseline_hazard["time"]),
                "cumhaz": list(self.baseline_hazard["cumhaz"])}
        return kw

    def card(self) -> List[str]:
        """The consequence lines: what was read, what will be used."""
        p = self.provenance
        out = [f"  external information  {self.form.replace('_', ' ')}",
               f"  read from             {p.get('file')}  ({p.get('format')}; "
               f"{p.get('n_tables')} table(s))"]
        if self.individual_data:
            d = self.individual_data
            if d.get("outcome_from_declaration") and not d.get("event_column"):
                out.append(f"  external cohort       table {d['table']!r}: "
                           f"{len(d['columns'])} columns in your file's layout; its "
                           f"time and event columns follow your declaration")
            else:
                out.append(f"  external cohort       table {d['table']!r}: time "
                           f"{d['time_column'] or 'none (a matched sample)'}, event {d['event_column']} = "
                           f"{d['event_value']}, {len(d['columns'])} columns")
        else:
            out.append(f"  coefficients          {len(self.terms)} terms on the "
                       f"log hazard-ratio scale"
                       + ("   <- converted from hazard ratios"
                          if p.get("converted_from") == "hazard_ratio" else "")
                       + (f"   (scale taken from the column header: {p['scale_overridden']})"
                          if p.get("scale_overridden") else ""))
            if self.Q is not None:
                out.append(f"  precision matrix      {len(self.Q)} x {len(self.Q)}"
                           f"   <- {self.Q_from}")
            if self.se:
                out.append(f"  standard errors       {len(self.se)} recorded, not "
                           "used (no covariance was published)")
            if self.baseline_hazard:
                out.append(f"  baseline hazard       "
                           f"{len(self.baseline_hazard['time'])} time points, "
                           "recorded; used only if follow-up is declared to be "
                           "in discrete intervals (item 7)")
        L = self.linkage
        if L:
            out.append(f"  matched to your data  {len(L.get('matched', []))} of "
                       f"{len(self.terms) if self.terms else len(self.individual_data.get('columns', []))}"
                       + (f"; not in your data: {', '.join(L['unmatched'])}"
                          if L.get("unmatched") else ""))
        for n in self.notes:
            out.append(f"  ({n})")
        return out


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _coefficients(t: RawTable, a: Dict[str, Any], reasons: List[Dict[str, Any]]
                  ) -> Tuple[Dict[str, float], Optional[Dict[str, float]],
                             Optional[str]]:
    """Names -> log hazard ratios, with the checks. Appends refusals."""
    nm, cc = a.get("name_column"), a.get("coefficient_column")
    if not nm or not cc:
        reasons.append({"code": "coefficient_columns_unnamed", "table": t.name,
                        "message": f"table {t.name!r}: the name column and the "
                                   "coefficient column could not be identified"})
        return {}, None, None
    names = [str(x).strip() if x == x and x is not None else "" for x in t.frame[nm]]
    if any(n == "" or n.lower() in ("nan", "none") for n in names):
        reasons.append({"code": "empty_name", "table": t.name,
                        "message": f"table {t.name!r}: column {nm!r} has empty "
                                   "variable names"})
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        reasons.append({"code": "names_not_unique", "table": t.name,
                        "message": f"table {t.name!r}: column {nm!r} repeats "
                                   f"{len(dup)} name(s) ({', '.join(dup[:5])}"
                                   f"{', ...' if len(dup) > 5 else ''}). This "
                                   "reads one row per variable. A per-level "
                                   "table (predictor / level / coefficient) "
                                   "must be reduced to per-variable "
                                   "coefficients on your own derived columns "
                                   "before it is uploaded."})
    vals = [_f(x) for x in t.frame[cc]]
    if any(v is None for v in vals):
        bad = [names[i] for i, v in enumerate(vals) if v is None][:5]
        reasons.append({"code": "coefficient_not_numeric", "table": t.name,
                        "message": f"table {t.name!r}: column {cc!r} is not a "
                                   f"finite number for {', '.join(bad)}"})
    if reasons:
        return {}, None, None
    scale = a.get("coefficient_scale") or "log_hazard_ratio"
    # The file's own header outranks the assignment's claim about the scale
    # (2026-09-13, ablation fixture F13: Qwen2.5 assigned the column headed
    # `hazard_ratio` as log hazard ratios, and 1.63 would have entered the
    # penalty as a log coefficient). A header that says hazard ratio is read as
    # hazard ratios; one that says coefficient / beta / log HR is read on the
    # log scale; the override is recorded, and a header that says nothing
    # leaves the assignment as it was.
    head = str(cc).strip().lower()
    if head in _HR_HEADS and scale != "hazard_ratio":
        a["scale_overridden"] = f"assignment said {scale}; column is headed {cc!r}"
        scale = "hazard_ratio"
    elif head in _COEF_HEADS and head not in ("value", "est", "estimate") and scale != "log_hazard_ratio":
        a["scale_overridden"] = f"assignment said {scale}; column is headed {cc!r}"
        scale = "log_hazard_ratio"
    converted = None
    est = list(vals)
    if scale == "hazard_ratio":
        if any(v <= 0 for v in est):
            reasons.append({"code": "hazard_ratio_not_positive", "table": t.name,
                            "message": f"table {t.name!r}: column {cc!r} was read "
                                       "as hazard ratios but holds values <= 0"})
            return {}, None, None
        converted = "hazard_ratio"
    # a confidence interval must bracket its estimate, on the published scale
    lo, hi = a.get("ci_lower_column"), a.get("ci_upper_column")
    if lo and hi:
        L = [_f(x) for x in t.frame[lo]]
        U = [_f(x) for x in t.frame[hi]]
        bad = [names[i] for i in range(len(est))
               if L[i] is not None and U[i] is not None
               and not (L[i] - 1e-9 <= est[i] <= U[i] + 1e-9)]
        if bad:
            reasons.append({"code": "ci_does_not_bracket", "table": t.name,
                            "message": f"table {t.name!r}: the interval "
                                       f"[{lo}, {hi}] does not bracket "
                                       f"{cc!r} for {', '.join(bad[:5])} -- "
                                       "either the columns were mis-identified "
                                       "or the file contradicts itself"})
            return {}, None, None
    if scale == "hazard_ratio":
        est = [math.log(v) for v in est]
    terms = dict(zip(names, est))
    se = None
    if a.get("se_column"):
        S = [_f(x) for x in t.frame[a["se_column"]]]
        if all(s is not None and s >= 0 for s in S):
            se = dict(zip(names, S))
    return terms, se, converted


def _matrix_kind(M: List[List[float]], terms: Dict[str, float],
                 se: Optional[Dict[str, float]], table_name: str) -> Optional[str]:
    """What the square table IS: "covariance" when its diagonal equals the squared
    standard errors of the coefficient table (relative 1e-4), "precision" when the
    diagonal of its inverse does; without standard errors, by the table's name;
    None when nothing decides."""
    import numpy as np
    names = list(terms)
    if se and all(n in se for n in names):
        s2 = np.array([float(se[n]) ** 2 for n in names])
        d = np.array([float(M[i][i]) for i in range(len(names))])
        if np.allclose(d, s2, rtol=1e-4, atol=0):
            return "covariance"
        try:
            dinv = np.diag(np.linalg.inv(np.array(M, dtype=float)))
            if np.allclose(dinv, s2, rtol=1e-4, atol=0):
                return "precision"
        except np.linalg.LinAlgError:
            pass
    nm = str(table_name).lower()
    if any(k in nm for k in ("vcov", "covariance", "cov")):
        return "covariance"
    if any(k in nm for k in ("precision", "information", "fisher", "hessian")):
        return "precision"
    return None


def _square(t: RawTable, a: Dict[str, Any], terms: Dict[str, float],
            reasons: List[Dict[str, Any]]) -> Optional[List[List[float]]]:
    """A covariance or precision table -> matrix in `terms` order, checked."""
    import numpy as np
    df = t.frame
    nm = a.get("name_column")
    num_cols = [c for c in df.columns if c != nm]
    if nm is None and len(df.columns) == len(df) + 1:
        # the name column was not pointed at; the one text column is it
        text = [c for c in df.columns
                if not np.issubdtype(df[c].dtype, np.number)]
        if len(text) == 1:
            nm = text[0]
            num_cols = [c for c in df.columns if c != nm]
    if len(num_cols) != len(df):
        reasons.append({"code": "matrix_not_square", "table": t.name,
                        "message": f"table {t.name!r}: {len(df)} rows against "
                                   f"{len(num_cols)} numeric columns; a "
                                   "covariance must be square"})
        return None
    col_names = [str(c).strip() for c in num_cols]
    row_names = ([str(x).strip() for x in df[nm]] if nm else col_names)
    if set(col_names) != set(terms) or set(row_names) != set(terms):
        missing = sorted(set(terms) - set(col_names))
        extra = sorted(set(col_names) - set(terms))
        reasons.append({"code": "matrix_names_mismatch", "table": t.name,
                        "message": f"table {t.name!r}: its names do not match "
                                   "the coefficient names"
                                   + (f"; missing {', '.join(missing[:5])}"
                                      if missing else "")
                                   + (f"; extra {', '.join(extra[:5])}"
                                      if extra else "")})
        return None
    try:
        M = df[num_cols].to_numpy(dtype=float)
    except (TypeError, ValueError):
        reasons.append({"code": "matrix_not_numeric", "table": t.name,
                        "message": f"table {t.name!r}: non-numeric entries"})
        return None
    if not np.all(np.isfinite(M)):
        reasons.append({"code": "matrix_not_numeric", "table": t.name,
                        "message": f"table {t.name!r}: non-finite entries"})
        return None
    order = list(terms)
    ri = [row_names.index(n) for n in order]
    ci = [col_names.index(n) for n in order]
    M = M[np.ix_(ri, ci)]
    scale = max(1.0, float(np.abs(M).max()))
    if not np.allclose(M, M.T, atol=1e-8 * scale, rtol=1e-6):
        reasons.append({"code": "matrix_not_symmetric", "table": t.name,
                        "message": f"table {t.name!r}: not symmetric"})
        return None
    ev = np.linalg.eigvalsh((M + M.T) / 2)
    if ev.min() < -1e-8 * scale:
        reasons.append({"code": "matrix_not_psd", "table": t.name,
                        "message": f"table {t.name!r}: not positive "
                                   f"semidefinite (smallest eigenvalue "
                                   f"{ev.min():.3g})"})
        return None
    return M.tolist()


# the shrinkage of the precision matrix toward the identity, after scaling to
# unit mean diagonal (the MIUM/SRTR convention; 0 = the raw inverse, 1 = the
# identity, i.e. the coefficients-alone member)
Q_SHRINK = 0.10


def _condition(Q: List[List[float]]) -> Tuple[List[List[float]], Dict[str, Any]]:
    """Scale Q to mean(diag) = 1 and shrink Q_SHRINK toward the identity.
    Returns the matrix and the record of what was done."""
    import numpy as np
    A = np.array(Q, dtype=float)
    kappa_raw = float(np.linalg.cond(A))
    scale = float(np.mean(np.diag(A)))
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    A = A / scale
    A = (1.0 - Q_SHRINK) * A + Q_SHRINK * np.eye(A.shape[0])
    A = (A + A.T) / 2
    return A.tolist(), {"scaled_by": scale, "shrink_toward_identity": Q_SHRINK,
                        "kappa_raw": kappa_raw, "kappa_final": float(np.linalg.cond(A)),
                        "mean_diagonal_final": float(np.mean(np.diag(A)))}


def _invert(M: List[List[float]], t: RawTable, reasons: List[Dict[str, Any]]
            ) -> Optional[List[List[float]]]:
    import numpy as np
    A = np.array(M, dtype=float)
    cond = np.linalg.cond(A)
    if not np.isfinite(cond) or cond > 1e12:
        reasons.append({"code": "covariance_singular", "table": t.name,
                        "message": f"table {t.name!r}: the covariance is "
                                   f"singular or near-singular (condition "
                                   f"number {cond:.3g}); supply the precision "
                                   "matrix instead"})
        return None
    Q = np.linalg.inv(A)
    return ((Q + Q.T) / 2).tolist()


def _baseline(t: RawTable, a: Dict[str, Any], reasons: List[Dict[str, Any]]
              ) -> Optional[Dict[str, List[float]]]:
    tc, hc, cc = (a.get("time_column"), a.get("hazard_column"),
                  a.get("cumulative_hazard_column"))
    if not tc or not (hc or cc):
        reasons.append({"code": "baseline_columns_unnamed", "table": t.name,
                        "message": f"table {t.name!r}: a time column and a "
                                   "hazard or cumulative-hazard column are "
                                   "needed"})
        return None
    T = [_f(x) for x in t.frame[tc]]
    if any(v is None for v in T) or any(T[i] >= T[i + 1] for i in range(len(T) - 1)):
        reasons.append({"code": "time_not_increasing", "table": t.name,
                        "message": f"table {t.name!r}: {tc!r} must be numeric "
                                   "and strictly increasing"})
        return None
    H = [_f(x) for x in t.frame[hc]] if hc else None
    C = [_f(x) for x in t.frame[cc]] if cc else None
    if H is not None and (any(v is None or v < 0 for v in H)):
        reasons.append({"code": "hazard_negative", "table": t.name,
                        "message": f"table {t.name!r}: {hc!r} must be "
                                   "non-negative"})
        return None
    if C is not None and (any(v is None for v in C)
                          or any(C[i] > C[i + 1] + 1e-12 for i in range(len(C) - 1))):
        reasons.append({"code": "cumhaz_not_monotone", "table": t.name,
                        "message": f"table {t.name!r}: {cc!r} must be "
                                   "non-decreasing"})
        return None
    if H is not None and C is not None:
        run, dev = 0.0, 0.0
        for h, c in zip(H, C):
            run += h
            dev = max(dev, abs(run - c))
        if dev > _REL_TOL * max(1.0, max(C)):
            reasons.append({"code": "cumhaz_not_running_sum", "table": t.name,
                            "message": f"table {t.name!r}: {cc!r} is not the "
                                       f"running sum of {hc!r} (max deviation "
                                       f"{dev:.3g})"})
            return None
    if H is None:
        H = [C[0]] + [C[i] - C[i - 1] for i in range(1, len(C))]
    if C is None:
        run, C = 0.0, []
        for h in H:
            run += h
            C.append(run)
    return {"time": T, "hazard": H, "cumhaz": C}


_SET_HEADS = ("set_id", "setid", "set", "stratum", "strata", "pair_id", "pair",
              "matched_set", "matchset", "risk_set", "riskset", "cluster")


def canonicalise(tables: List[RawTable], assignment: List[Dict[str, Any]],
                 provenance: Dict[str, Any],
                 cohort_columns: Optional[List[str]] = None,
                 matched_design: bool = False) -> ExternalObject:
    """Verify and build. Raises :class:`ExternalRefusal` with every reason
    found, so the analyst fixes the file once."""
    by_name = {t.name: t for t in tables}
    roles: Dict[str, List[Dict[str, Any]]] = {}
    for a in assignment:
        roles.setdefault(a["role"], []).append(a)
    reasons: List[Dict[str, Any]] = []
    notes: List[str] = []

    indi = roles.get("individual_level_data", [])
    coef = roles.get("coefficients", [])
    if len(coef) > 1:
        reasons.append({"code": "several_coefficient_tables",
                        "message": "the file holds more than one coefficient "
                                   "table (" + ", ".join(a["table"] for a in coef)
                                   + "); keep the one that applies"})
    if not coef and not indi:
        raise ExternalRefusal(reasons + [{
            "code": "no_coefficient_table",
            "message": "no table was identified as coefficients or as another "
                       "cohort's data. A coefficient table has one row per "
                       "variable: a name column and a coefficient column"}])
    if reasons:
        raise ExternalRefusal(reasons)

    # ---- individual-level data ------------------------------------------
    if indi and not coef:
        a = indi[0]
        t = by_name[a["table"]]
        tc, ec = a.get("time_column"), a.get("event_column")
        if matched_design:
            tc = None
        set_like = any(str(c).lower() in _SET_HEADS for c in t.frame.columns)
        columns = [str(c) for c in t.frame.columns]
        # Another cohort's records in the SAME layout as the analyst's own
        # file (another matched sample `set_id, cc_status, Z1..Z20`: simulation
        # prompt search, 2026-09-30), whose outcome columns the reading could
        # not name because their headers say nothing about their role. The
        # release is read before any declaration exists; the line-up check at
        # declaration requires the external outcome columns to carry the
        # declaration's names anyway. So when the table holds at least 80 % of
        # the cohort's columns (the rule `heuristic_assignment` already uses)
        # and no event column was named, the outcome columns are left to the
        # declaration: filled there by name, checked there, and disclosed.
        same_layout = bool(cohort_columns) and (
            sum(c in set(columns) for c in cohort_columns) >= 0.8 * len(cohort_columns))
        if not ec and same_layout:
            link = {"matched": [c for c in cohort_columns if c in columns],
                    "unmatched": [c for c in cohort_columns if c not in columns]}
            notes.append("the table carries your cohort's own columns; its follow-up "
                         "time and event columns are taken from your declaration, "
                         "by name")
            return ExternalObject(
                form="individual_level_data", scale="log_hazard_ratio", terms={},
                provenance=provenance,
                individual_data={"path": provenance.get("path"), "table": t.name,
                                 "time_column": None if matched_design else tc,
                                 "event_column": None, "event_value": None,
                                 "columns": columns, "outcome_from_declaration": True},
                linkage=link, notes=notes)
        if not ec or (not tc and not (matched_design or set_like)):
            raise ExternalRefusal([{"code": "individual_roles_unnamed",
                                    "table": t.name,
                                    "message": f"table {t.name!r}: the follow-up "
                                               "time and event columns could "
                                               "not be identified"}])
        if not tc:
            # Another matched case-control sample carries no follow-up time but
            # a matched-set column; the library's ncc_indi members take its
            # case indicator and its sets, both addressed by the cohort's own
            # column names through the declaration. For a full-cohort analysis
            # the fit stops in R with the missing time column named, so
            # accepting the table here decides nothing.
            tc = None
            notes.append("no follow-up time column but a matched-set column: "
                         "usable by a matched case-control analysis only")
        ev = a.get("event_value")
        levels = sorted(str(v) for v in t.frame[ec].dropna().unique())
        if ev is None:
            if levels == ["0", "1"]:
                ev = "1"
                notes.append("event value taken as 1 on a 0/1 column")
            else:
                raise ExternalRefusal([{"code": "event_value_unknown",
                                        "table": t.name,
                                        "message": f"table {t.name!r}: which "
                                                   f"value of {ec!r} means the "
                                                   "event is not stated; its "
                                                   "values are "
                                                   + ", ".join(levels[:6])}])
        elif str(ev) not in levels:
            if levels == ["0", "1"]:
                # the model named a value the column does not hold ("case",
                # "yes"); on a 0/1 column the event is 1 by the same rule that
                # applies when no value is named, and the note says what was
                # named (release-reading experiment, 2026-09-14)
                notes.append(f"event value taken as 1 on a 0/1 column (the "
                             f"reading named {str(ev)!r}, which does not occur)")
                ev = "1"
            else:
                raise ExternalRefusal([{"code": "event_value_absent",
                                        "table": t.name,
                                        "message": f"table {t.name!r}: {ev!r} does "
                                                   f"not occur in {ec!r}"}])
        columns = [str(c) for c in t.frame.columns]
        link = {}
        if cohort_columns:
            link = {"matched": [c for c in cohort_columns if c in columns],
                    "unmatched": [c for c in cohort_columns if c not in columns]}
        return ExternalObject(
            form="individual_level_data", scale="log_hazard_ratio", terms={},
            provenance=provenance,
            individual_data={"path": provenance.get("path"), "table": t.name,
                             "time_column": tc, "event_column": ec,
                             "event_value": str(ev), "columns": columns},
            linkage=link, notes=notes)

    # ---- coefficients ---------------------------------------------------
    a = coef[0]
    t = by_name[a["table"]]
    terms, se, converted = _coefficients(t, a, reasons)
    if reasons:
        raise ExternalRefusal(reasons)
    prov = dict(provenance, coefficient_table=t.name,
                name_column=a.get("name_column"),
                coefficient_column=a.get("coefficient_column"),
                converted_from=converted,
                scale_overridden=a.get("scale_overridden"))

    Q = None
    Q_from = None
    sq = roles.get("covariance", []) + roles.get("precision", [])
    if len(sq) > 1:
        reasons.append({"code": "several_matrices",
                        "message": "more than one covariance / precision table "
                                   "(" + ", ".join(x["table"] for x in sq) + ")"})
    elif sq:
        M = _square(by_name[sq[0]["table"]], sq[0], terms, reasons)
        if M is not None:
            # Covariance or precision is a FACT of the file, not a claim of the
            # reading (2026-09-13, ablation fixture F04: Qwen2.5 called the
            # `vcov` table a precision matrix and the Mahalanobis penalty took
            # the covariance uninverted). Two checks, deterministic: with
            # standard errors in the coefficient table, the diagonal of a
            # covariance equals se^2 and that of a precision does not; without
            # them, a table named vcov / cov / covariance / precision /
            # information says what it is. A contradiction overrides the
            # claim and is recorded and disclosed.
            claimed = sq[0]["role"]
            actual = _matrix_kind(M, terms, se, sq[0]["table"])
            if actual and actual != claimed:
                sq[0] = dict(sq[0], role=actual)
                prov["matrix_role_overridden"] = f"the reading said {claimed}; the file shows {actual}"
                notes.append(f"the matrix table was read as a {claimed}; it is a {actual} "
                             f"({'its diagonal equals the squared standard errors' if se else 'by its name'})")
            if sq[0]["role"] == "covariance":
                Q_raw = _invert(M, by_name[sq[0]["table"]], reasons)
                Q_from = "inverse of the published covariance"
            else:
                Q_raw, Q_from = M, "precision as published"
            if Q_raw is not None:
                # CONDITIONED, and disclosed: the matrix
                # the Mahalanobis penalty takes is scaled to unit mean
                # diagonal, so the eta grid means the same thing as with the
                # identity, and shrunk Q_SHRINK toward the identity for
                # conditioning -- the convention of the MIUM/SRTR analysis
                # (`refit_20260831/01_build_srtr_external.R`), where the raw
                # inverse had condition number 1.8e10. What was done and
                # what it changed is printed on the card and in the report.
                Q, cond = _condition(Q_raw)
                prov["matrix_conditioning"] = cond
                Q_from += (f", scaled to unit mean diagonal and shrunk "
                           f"{int(round(100 * Q_SHRINK))}% toward the identity "
                           f"(condition number {cond['kappa_raw']:.3g} -> "
                           f"{cond['kappa_final']:.3g})")
        prov["matrix_table"] = sq[0]["table"]
        prov["matrix_role"] = sq[0]["role"]

    bh = None
    bhs = roles.get("baseline_hazard", [])
    if len(bhs) > 1:
        reasons.append({"code": "several_baseline_tables",
                        "message": "more than one baseline-hazard table"})
    elif bhs:
        bh = _baseline(by_name[bhs[0]["table"]], bhs[0], reasons)
        prov["baseline_table"] = bhs[0]["table"]
    if indi:
        notes.append("a table was read as another cohort's rows but a "
                     "coefficient table is present; the coefficients are used")
    if reasons:
        raise ExternalRefusal(reasons)

    link = {}
    if cohort_columns:
        link = {"matched": [n for n in terms if n in cohort_columns],
                "unmatched": [n for n in terms if n not in cohort_columns]}
        if terms and not link["matched"]:
            # Nothing to borrow from is a refusal, not a fit. A table whose
            # names match no column of the cohort would be carried into the
            # candidate set as a vector of zeros over every covariate, and the
            # borrowing members would "win" an analysis that borrowed nothing
            # (found 2026-09-14 on a per-subject risk-score file: 1000 rows of
            # patient_id, risk_score read as 1000 coefficients, 0 matched).
            names = list(terms)[:4]
            raise ExternalRefusal([{
                "code": "no_term_matches_cohort",
                "message": (f"none of the {len(terms)} names in the coefficient "
                            f"table ({', '.join(names)}, ...) is a column of your "
                            "data, so there is nothing to borrow from. A "
                            "coefficient table has one row per variable, named "
                            "as your columns are; a table with one row per "
                            "subject (an id and a score) is not one.")}])
    form = ("coefficients_with_covariance" if Q is not None
            else "coefficients_with_baseline_hazard" if bh is not None
            else "coefficients")
    if Q is not None and bh is not None:
        notes.append("both a precision matrix and a baseline hazard were read; "
                     "the form is coefficients with covariance and the baseline "
                     "hazard is recorded")
    if se and Q is None:
        notes.append("standard errors are recorded and disclosed, not turned "
                     "into a covariance")
    return ExternalObject(form=form, scale="log_hazard_ratio", terms=terms,
                          provenance=prov, Q=Q, Q_from=Q_from, se=se,
                          baseline_hazard=bh, linkage=link, notes=notes)


# ----------------------------------------------------------------- entry
def _fingerprint(path: str) -> Dict[str, Any]:
    p = Path(path)
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"file": p.name, "path": str(p), "bytes": p.stat().st_size,
            "sha256": h.hexdigest()}


def _names_a_table(raw: Any) -> bool:
    """Does the model's assignment give any table a usable role?"""
    items = raw.get("tables") if isinstance(raw, dict) else raw
    for a in (items or []):
        if isinstance(a, dict) and a.get("role") in ("coefficients", "individual_level_data",
                                                      "covariance", "precision", "baseline_hazard"):
            return True
    return False


def read_external(path: str, client=None, model: str = "",
                  cohort_columns: Optional[List[str]] = None,
                  run_r=None, cohort_outcome: Optional[Tuple[str, str]] = None) -> ExternalObject:
    """File in, :class:`ExternalObject` out, or :class:`ExternalRefusal`.

    With a client the model assigns roles (one call); without one the
    heuristic does, and refuses what it cannot name. Either way every column
    is checked against the file and every number against the rules above.
    The assignment, the issues found with it, and the model call record go
    into the object's provenance.
    """
    tables = read_tables(path, run_r=run_r)
    prov = _fingerprint(path)
    prov["format"] = Path(path).suffix.lower().lstrip(".")
    prov["n_tables"] = len(tables)
    prov["tables"] = [{"name": t.name, "n_rows": t.n_rows,
                       "columns": [c["name"] for c in t.columns]}
                      for t in tables]
    if client is not None:
        from . import boundary
        try:
            raw = assign_roles(client, model, tables)
            prov["assigned_by"] = "model"
            prov["assignment_reasoning"] = str(raw.get("reasoning") or "")[:1000]
        except ValueError as exc:
            # The model's reading was not valid JSON (Qwen2.5 on the ablation
            # fixture F05, 2026-09-13: a stray `<tool_call>` token inside a
            # string ended the output). The reading falls back to the
            # model-free heuristic, which names only what the headers say and
            # is checked like any assignment; the fallback and the failed call
            # are recorded and the card says the file was read by rule.
            raw = heuristic_assignment(tables, cohort_columns=cohort_columns,
                                       cohort_outcome=cohort_outcome)
            prov["assigned_by"] = "heuristic (fallback: the model's reading was not valid JSON)"
            prov["model_error"] = str(exc)[:300]
        prov["model_call"] = boundary.CALLS[-1] if boundary.CALLS else None
        # Another cohort's records the model did not recognise (Qwen2.5 on a
        # matched case-control sample, synth200 F20/F21, 2026-09-14: it named
        # no table at all, so the upload was refused and the analysis ran
        # without the records). Whether a table IS the cohort's layout is a
        # fact of the headers -- at least 80 % of the cohort's columns -- that
        # the rule states without judgement; when the model names nothing
        # usable and the rule finds such a table, the rule's reading is taken
        # and the card says so. The model's reading is kept on the record.
        if cohort_columns and not _names_a_table(raw):
            byrule = heuristic_assignment(tables, cohort_columns=cohort_columns,
                                          cohort_outcome=cohort_outcome)
            if any(a.get("role") == "individual_level_data" for a in (byrule.get("tables") or [])):
                prov["model_assignment"] = raw
                raw = byrule
                prov["assigned_by"] = ("heuristic (the model named no usable table; "
                                       "the table carries the cohort's own columns)")
    else:
        raw = heuristic_assignment(tables, cohort_columns=cohort_columns,
                                   cohort_outcome=cohort_outcome)
        prov["assigned_by"] = "heuristic"
    assignment, issues = check_assignment(tables, raw)
    prov["assignment"] = assignment
    prov["assignment_issues"] = issues
    return canonicalise(tables, assignment, prov, cohort_columns=cohort_columns,
                        matched_design=bool(cohort_outcome) and cohort_outcome[0] is None)
