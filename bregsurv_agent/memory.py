"""Component 4 -- what the agent remembers beyond one session, and what it does not.

Two memories, both small on purpose.

1. **A catalogue of published models**, in the repository and versioned:
   `bregsurv_agent/registry/published_models.json`. Metadata only -- what a
   release is (organ, population, outcome, horizon, release cycle), what it
   contains, how the analyst obtains it, and the checksums of files that were
   published. The agent never downloads: the SRTR
   releases sit in a Shiny application behind a session-scoped link and a
   reCAPTCHA, a scraper would be brittle and would put a browser into an
   air-gapped deployment, and none of it has anything to do with the model.
   What the model does here is one constrained call: given the analyst's
   description of the external model, propose the matching catalogue ids from
   the enum, with a verbatim span as evidence, and the harness renders the
   entry -- what it is, how to obtain it, how to reduce it -- and waits for
   the upload. A file that is later uploaded is matched to the catalogue by
   checksum, which pins its provenance without trusting anyone's description.

2. **A local store**, per user, for what the analyst has already told the
   agent about a file: the verified declaration, keyed by the data file's
   sha256, so the same file is not asked the same questions twice; and one
   preference (`write_prose`). Off on a shared host (`DEPLOYMENT_MODE=demo`)
   and whenever `BREGSURV_MEMORY=off`, because remembering one visitor's column
   names for the next would break the banner's promise. Location
   `~/.bregsurv/memory.json`, or the path in `BREGSURV_MEMORY`.

   A remembered role is a SOURCE like any other -- the card and the report
   say `remembered: you declared this for the same file on <date>` -- and one
   message edits it. The time-zero answer is never remembered: it is the
   one question that stays with a person every time (master memory section
   3d, the automation ruling), and a remembered "yes" would be exactly the
   pre-filled suggestion the protocol avoids.

Never stored: rows, values, the external file, model calls, prompts.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import policy

CATALOGUE_PATH = Path(__file__).resolve().parent / "registry" / "published_models.json"

REMEMBERED_ROLES = ("time", "event", "event_value", "covariates", "stratum",
                    "external_data_expr",
                    "discrete")               # never "time_zero"


# ----------------------------------------------------------------- catalogue
def _load_catalogue() -> Dict[str, Any]:
    return json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))


def catalogue() -> List[Dict[str, Any]]:
    return list(_load_catalogue().get("models", []))


def sources() -> Dict[str, Any]:
    return dict(_load_catalogue().get("sources", {}))


def catalogue_ids() -> List[str]:
    return [m["id"] for m in catalogue()]


def entry(model_id: str) -> Optional[Dict[str, Any]]:
    for m in catalogue():
        if m["id"] == model_id:
            return m
    return None


def listing() -> str:
    """One line per entry, for the prompt: id, then what it is."""
    lines = []
    for m in catalogue():
        lines.append(f"  {m['id']}: {m['source']} {m['organ']}, {m['donor_type']}, "
                     f"{m['population']}; {m['outcome']}; {m['horizon']}; "
                     f"release {m['release']}; contains " + ", ".join(m["contents"]))
    return "\n".join(lines)


def render_entry(m: Dict[str, Any]) -> List[str]:
    """The card the analyst sees: what it is, how to obtain it, how to reduce it."""
    src = sources().get(m["source"], {})
    where = ", ".join(x for x in (m.get("organ"), m.get("donor_type"), m.get("population"))
                      if x and x != "not applicable")
    out = [f"{m['id']}",
           f"  {m['source']} {m['model_class']} model: {where}",
           f"  outcome: {m['outcome']}; horizon: {m['horizon']}; release {m['release']}",
           f"  the release contains: " + ", ".join(m["contents"])]
    for f in m.get("files", []):
        lay = f.get("layout")
        lay = ", ".join(lay) if isinstance(lay, list) else str(lay)
        rows = f"{f['rows']} rows" if f.get("rows") else "row count not recorded"
        out.append(f"    {f['name']}: {lay}; {rows}")
    if m.get("notes"):
        out.append(f"  note: {m['notes']}")
    steps = src.get("how_to_obtain", [])
    if steps:
        out.append("  how to obtain it (the agent does not download):")
        out += [f"    {i}. {s}" for i, s in enumerate(steps, 1)]
    if src.get("reduction_note"):
        out.append("  before uploading: " + src["reduction_note"])
    return out


def match_file(sha256: Optional[str]) -> Optional[Dict[str, Any]]:
    """Which published file, if any, an uploaded file is byte-identical to."""
    if not sha256:
        return None
    for m in catalogue():
        for f in m.get("files", []):
            pre = f.get("sha256_prefix")
            if pre and sha256.startswith(pre):
                return {"id": m["id"], "file": f["name"], "release": m["release"],
                        "source": m["source"]}
    return None


# ------------------------------------------------------- the model's one call
def propose_schema() -> Dict[str, Any]:
    """Built per call so the enum is always the current catalogue."""
    ids = catalogue_ids()
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {"type": "string"},
            "matches": {
                "type": "array", "maxItems": 3,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "evidence": {"type": "string"},
                    },
                    "required": ["id", "evidence"],
                },
            },
        },
        "required": ["reasoning", "matches"],
    }


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


_HORIZON_WORDS = {
    "1 year after transplant": ("1 year", "1-year", "one year", "one-year", "1y", "12 month", "12-month"),
    "3 years after transplant": ("3 year", "3-year", "three year", "three-year", "3y", "36 month"),
    "10 years": ("10 year", "10-year", "ten year", "ten-year"),
    "3 months": ("3 month", "3-month", "three month", "three-month", "90 day", "90-day"),
}
_OUTCOME_WORDS = {
    "graft": ("graft", "allograft"),
    "patient survival": ("patient survival", "mortality", "death", "died", "all-cause", "survival"),
    "transplant rate": ("transplant rate", "transplantation rate", "time to transplant"),
    "pre-transplant mortality": ("pre-transplant mortality", "pretransplant mortality",
                                 "waiting-list mortality", "waitlist mortality", "death on the list"),
    "cardiovascular": ("cardiovascular", "cvd", "heart attack", "stroke", "coronary", "heart disease"),
    "recurrence": ("recurrence", "relapse", "recurrence-free", "disease-free"),
}
# the organ field of the literature entries is a domain word the analyst would write
_ORGAN_WORDS = {
    "cardiovascular": ("cardiovascular", "cvd", "heart", "cardiac"),
    "critical care": ("icu", "intensive care", "critical care", "critically ill", "seriously ill", "hospitalised", "hospitalized"),
    "breast": ("breast",),
}


def supported_by(message: str, m: Dict[str, Any]) -> bool:
    """Do the analyst's OWN words carry the entry's organ, outcome and horizon?
    A deterministic check that does not depend on how the model quotes: the
    2026-09-11 Qwen3 run matched the right ids but copied the catalogue line
    as evidence, and a match the message supports must not be lost to that."""
    msg = _norm(message)
    organ = _norm(m.get("organ", ""))
    if not any(w in msg for w in _ORGAN_WORDS.get(organ, (organ,))):
        return False
    outcome = _norm(m.get("outcome", ""))
    key = next((k for k in _OUTCOME_WORDS if k in outcome), None)
    if key is None:
        return False
    words = _OUTCOME_WORDS[key]
    if key == "patient survival":
        # "survival" alone supports a patient-survival entry only when the
        # message is not about graft survival (the SRTR pair)
        words = tuple(w for w in words if w != "survival")
        if not any(w in msg for w in words) and not ("survival" in msg and "graft" not in msg):
            return False
    elif not any(w in msg for w in words):
        return False
    words = _HORIZON_WORDS.get(m.get("horizon", ""))
    if words and not any(w in msg for w in words):
        return False
    return True


def validate_proposal(message: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keep only ids that exist and that the message backs: either the
    model's evidence is a substring of the message, or the message itself
    carries the entry's organ, outcome and horizon (`supported_by`). The
    record says which. Deterministic; the model's say-so is never enough."""
    ids = set(catalogue_ids())
    msg = _norm(message)
    out, seen = [], set()
    for item in (raw.get("matches") or [])[:3]:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        ev = str(item.get("evidence") or "")
        if mid not in ids or mid in seen:
            continue
        if ev and _norm(ev) in msg:
            how = "evidence"
        elif supported_by(message, entry(mid) or {}):
            how = "message keywords"
        else:
            continue
        seen.add(mid)
        out.append({"id": mid, "evidence": ev, "verified_by": how})
    # Siblings the message supports equally: when the analyst's words
    # fit more than one entry of the same organ -- the one-year and three-year
    # releases, graft and patient survival when neither is named, two donor
    # risk indices -- the model tends to name one. Every other entry the
    # message's own keywords support is listed beside it, deterministically,
    # so the analyst sees the choice rather than a silent pick.
    kept = [entry(o["id"]) or {} for o in out]
    sources = {k.get("source") for k in kept}
    organs = {_norm(k.get("organ", "")) for k in kept}
    for m in catalogue():
        if m["id"] in seen or _norm(m.get("organ", "")) not in organs:
            continue
        same_family = m.get("source") in sources
        named = any(_norm(a) in msg for a in m.get("aliases", []))
        if (same_family or named) and supported_by(message, m):
            seen.add(m["id"])
            out.append({"id": m["id"], "evidence": "", "verified_by": "message keywords (sibling)"})
    return out[:3]


def propose_model(client, model: str, message: str) -> Dict[str, Any]:
    """One constrained call: which catalogue entries the analyst's words name.
    Returns {"matches": [...validated...], "raw": ..., "_call": record}."""
    from . import boundary
    user = ("Published models this system knows of:\n" + listing()
            + "\n\nThe analyst wrote:\n" + message.strip())
    raw = boundary._chat(client, model, policy.load("published_model"), user,
                         propose_schema(), "published_model", max_tokens=500)
    rec = boundary.CALLS[-1] if boundary.CALLS else {}
    return {"matches": validate_proposal(message, raw), "raw": raw, "_call": rec}


# ------------------------------------------------------------------- store
class Store:
    """The per-user memory file. Every method is safe to call when disabled or
    when the file is missing or unreadable: memory must never break a run."""

    def __init__(self, path: Optional[str] = None, enabled: Optional[bool] = None):
        env = os.environ.get("BREGSURV_MEMORY", "").strip()
        if enabled is None:
            enabled = (os.environ.get("DEPLOYMENT_MODE", "local").lower() != "demo"
                       and env.lower() != "off")
        self.enabled = bool(enabled)
        if path:
            self.path = Path(path)
        elif env and env.lower() != "off":
            self.path = Path(env).expanduser()
        else:
            self.path = Path.home() / ".bregsurv" / "memory.json"

    # -- file
    def _read(self) -> Dict[str, Any]:
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
        return {"declarations": {}, "preferences": {}}

    def _write(self, d: Dict[str, Any]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except Exception:
            return False

    # -- declarations
    def recall_declaration(self, data_sha256: Optional[str]) -> Optional[Dict[str, Any]]:
        if not self.enabled or not data_sha256:
            return None
        rec = self._read().get("declarations", {}).get(data_sha256)
        if not isinstance(rec, dict) or not isinstance(rec.get("answers"), dict):
            return None
        rec = dict(rec)
        rec["answers"] = {k: v for k, v in rec["answers"].items()
                          if k in REMEMBERED_ROLES and v}
        return rec if rec["answers"] else None

    def remember_declaration(self, data_sha256: str, answers: Dict[str, Any],
                             sources: Dict[str, str], file_name: str = "",
                             columns: Optional[List[str]] = None) -> bool:
        """Store the verified declaration for this exact file. `time_zero` and
        anything that is not a role are dropped here, not by the reader."""
        if not self.enabled or not data_sha256:
            return False
        d = self._read()
        d.setdefault("declarations", {})[data_sha256] = {
            "answers": {k: str(v) for k, v in (answers or {}).items()
                        if k in REMEMBERED_ROLES and v},
            "sources": {k: str(v) for k, v in (sources or {}).items()
                        if k in REMEMBERED_ROLES},
            "file": file_name,
            "n_columns": len(columns or []),
            "date": _dt.date.today().isoformat(),
        }
        return self._write(d)

    def forget_declaration(self, data_sha256: str) -> bool:
        if not self.enabled:
            return False
        d = self._read()
        d.get("declarations", {}).pop(data_sha256, None)
        return self._write(d)

    # -- preferences
    def preference(self, key: str, default: Any = None) -> Any:
        if not self.enabled:
            return default
        return self._read().get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any) -> bool:
        if not self.enabled:
            return False
        d = self._read()
        d.setdefault("preferences", {})[key] = value
        return self._write(d)

    def describe(self) -> Dict[str, Any]:
        """For provenance: where memory lives and whether it was on."""
        return {"enabled": self.enabled, "path": str(self.path) if self.enabled else None}
