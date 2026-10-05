"""Component 3 -- the state of one analysis, typed, in one place.

Everything the harness decides and everything the model is shown derives from
this object. It replaces the plain dict `app.py` used to carry between turns,
which had fourteen string keys assembled in five places and read in forty: a
missing or misspelt key was silently `None`, and one such drift was live when
this was written -- the state line told the model "external information: none"
whenever the external release was an individual-level cohort, because it read
a `coefs` key that only a coefficient table sets.

Four properties, each a design decision:

* **typed** -- fields are declared; `get`/`[]` exist for the drivers and
  tests that still index by name, but an unknown name raises instead of
  returning None;
* **derived, not stored** -- the PHASE is computed from the fields on every
  access (the same rule as `Declaration.design`), so it cannot disagree with
  them; the state line the model sees is computed the same way;
* **transitions are named** -- every change goes through a `with_*` method
  that returns a NEW session (the app never mutated the old dict either) and
  records the phase before and after in the typed action log, so the trace
  shows the walk, not just the routes;
* **serialisable** -- `to_provenance` is a JSON-safe snapshot that goes
  into `trace.json` under `provenance.session`, from which the evaluation's
  "questions per request" and "completed in one message" are read directly.

Nothing here persists across sessions (that is component 4, Memory), nothing
here involves the model, and nothing here decides anything new: the rules
that fill a gap live in `declaration.complete`, the gate in `check_admissibility.R`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional


class Phase(str, Enum):
    EMPTY = "empty"            # no cohort loaded
    PROFILED = "profiled"      # cohort profiled, nothing declared yet
    DECLARING = "declaring"    # some roles settled, at least one still open
    REFUSED = "refused"        # a declaration was verified and the gate refused it
    VERIFIED = "verified"      # a declaration verified and admissible; the run follows at once
    DONE = "done"              # a result exists


ROLE_KEYS = ("time", "event", "event_value", "covariates", "time_zero",
             "stratum", "external_data_expr",
             "discrete")                    # : item 7, the time scale


def _ext_name(ext: Any) -> str:
    """The name a loaded release goes by: its file name."""
    prov = getattr(ext, "provenance", None) or {}
    return str(prov.get("file") or prov.get("path") or "external")


@dataclass(frozen=True)
class Session:
    data_path: Optional[str] = None
    data_expr: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    dict_decl: Any = None                      # Declaration from a data dictionary, if one settles the outcome
    external: Any = None                       # external.ExternalObject -- the ACTIVE one
    externals: Dict[str, Any] = field(default_factory=dict)   # every release read, by file name (M2)
    external_refusal: Optional[List[Dict[str, Any]]] = None
    pending: Dict[str, str] = field(default_factory=dict)
    pending_sources: Dict[str, str] = field(default_factory=dict)
    declaration: Any = None                    # declaration.Declaration
    verification: Any = None                   # declaration.Verification
    result: Any = None                         # pipeline.RunResult -- the latest
    results: List[Any] = field(default_factory=list)   # every run of the session, oldest first (M2)
    model_calls: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    temp: List[str] = field(default_factory=list)
    turns: int = 0                             # analyst messages handled
    questions: int = 0                         # turns that ended in a question to the analyst
    data_sha256: Optional[str] = None          # the cohort file's fingerprint (memory key)
    remembered: Optional[Dict[str, Any]] = None  # component 4: the declaration recalled for this file
    # : the analyst's own test file, if one was supplied (never a split
    # the agent draws); carried into the declaration at verify time
    test_data_path: Optional[str] = None
    test_data_expr: Optional[str] = None

    # ------------------------------------------------------------ derived
    @property
    def phase(self) -> Phase:
        if self.profile is None:
            return Phase.EMPTY
        if self.pending:
            return Phase.DECLARING
        if self.result is not None:
            return Phase.DONE
        if self.verification is not None:
            return Phase.VERIFIED if self.verification.admissible else Phase.REFUSED
        return Phase.PROFILED

    @property
    def has_result(self) -> bool:
        return self.result is not None

    def external_line(self) -> str:
        """The external-information fact, from the object, whatever its form."""
        ext = self.external
        if ext is not None:
            form = str(getattr(ext, "form", "") or "").replace("_", " ")
            if getattr(ext, "individual_data", None):
                cols = (ext.individual_data or {}).get("columns", [])
                return f"individual-level records ({len(cols)} columns)"
            n = len(getattr(ext, "terms", {}) or {})
            extras = []
            if getattr(ext, "Q", None) is not None:
                extras.append("with precision matrix")
            if getattr(ext, "baseline_hazard", None):
                extras.append("with baseline hazard")
            return f"{form or 'coefficients'} ({n} terms" + \
                   ("; " + ", ".join(extras) if extras else "") + ")"
        if self.external_refusal:
            return "a file was uploaded and refused"
        return "none"

    def state_line(self) -> str:
        """The four facts the model is shown instead of a transcript (M1),
        plus, when several releases are loaded, their names and the active one,
        and the number of runs so far."""
        if self.declaration is not None and not self.pending:
            d = "verified" if self.phase in (Phase.VERIFIED, Phase.DONE) \
                else "declared but refused"
        elif self.pending:
            d = "partial (" + ", ".join(k for k in ROLE_KEYS if self.pending.get(k)) + ")"
        else:
            d = "none"
        extra = ""
        if len(self.externals) > 1:
            extra = (f" | external files loaded: {', '.join(self.externals)} "
                     f"(active: {self.external_name})")
        if len(self.results) > 1:
            extra += f" | runs so far: {len(self.results)}"
        if self.test_data_expr:
            # : so a question about held-out performance is typed as a
            # question about the result, not as out of scope
            extra += " | test data: supplied (held-out performance reported)"
        return (f"State: cohort loaded: {'yes' if self.profile else 'no'} | "
                f"external information: {self.external_line()} | "
                f"declaration: {d} | "
                f"result: {'present' if self.has_result else 'none'}" + extra)

    def invariants(self) -> List[str]:
        """Every violation, in words. Empty means the state is coherent."""
        bad = []
        if self.result is not None and self.declaration is None:
            bad.append("a result exists without a declaration")
        if self.result is not None and (self.verification is None
                                        or not self.verification.admissible):
            bad.append("a result exists although the declaration was not verified admissible")
        if self.verification is not None and self.declaration is None:
            bad.append("a verification exists without a declaration")
        extra = [k for k in self.pending if k not in ROLE_KEYS]
        if extra:
            bad.append(f"pending carries non-role keys: {extra}")
        extra = [k for k in self.pending_sources
                 if k not in self.pending and not str(self.pending_sources[k]).startswith("ask:")]
        if extra:
            bad.append(f"pending_sources names roles that are not pending: {extra}")
        if self.profile is None and (self.declaration is not None or self.pending):
            bad.append("roles are declared with no cohort loaded")
        if self.questions > self.turns:
            bad.append("more questions than turns")
        return bad

    # ------------------------------------------------------------ compatibility
    _ALIASES = {"_temp": "temp"}

    def get(self, key: str, default: Any = None) -> Any:
        """Read by name, for the drivers and tests that index the session.
        Unknown names raise: a typo must not read as an empty field."""
        key = self._ALIASES.get(key, key)
        if key not in self.__dataclass_fields__:
            raise KeyError(f"Session has no field {key!r}")
        val = getattr(self, key)
        return default if val is None else val

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        """`"profile" in session`: the field is known AND holds something."""
        key = self._ALIASES.get(key, key)
        if key not in self.__dataclass_fields__:
            raise KeyError(f"Session has no field {key!r}")
        val = getattr(self, key)
        return val is not None and val != {} and val != []

    # ------------------------------------------------------------ transitions
    def _step(self, name: str, **changes: Any) -> "Session":
        """Apply `changes`, record the transition with the phase before and
        after. Every state change goes through here."""
        before = self.phase
        new = replace(self, **changes)
        rec = {"transition": name, "phase": [before.value, new.phase.value]}
        return replace(new, actions=list(self.actions) + [rec])

    def with_profile(self, data_path: str, data_expr: str, profile: Dict[str, Any],
                     dict_decl: Any = None, external: Any = None,
                     external_refusal: Optional[List[Dict[str, Any]]] = None,
                     temp: Optional[List[str]] = None,
                     model_calls: Optional[List[Dict[str, Any]]] = None,
                     data_sha256: Optional[str] = None,
                     remembered: Optional[Dict[str, Any]] = None,
                     test_data_path: Optional[str] = None,
                     test_data_expr: Optional[str] = None) -> "Session":
        exts = {_ext_name(external): external} if external is not None else {}
        return self._step("profiled", data_path=data_path, data_expr=data_expr,
                          profile=profile, dict_decl=dict_decl, external=external,
                          externals=exts, external_refusal=external_refusal,
                          temp=list(temp or []), model_calls=list(model_calls or []),
                          pending={}, pending_sources={}, declaration=None,
                          verification=None, result=None, results=[],
                          data_sha256=data_sha256, remembered=remembered,
                          test_data_path=test_data_path, test_data_expr=test_data_expr)

    def with_external(self, external: Any,
                      refusal: Optional[List[Dict[str, Any]]] = None) -> "Session":
        """An external release read (or refused) after the cohort was loaded.
        A release that reads becomes the ACTIVE one and joins `externals`
        under its file name; a refusal leaves the active one alone."""
        exts = dict(self.externals)
        if external is not None:
            exts[_ext_name(external)] = external
            return self._step("external", external=external, externals=exts,
                              external_refusal=None)
        return self._step("external_refused", external_refusal=refusal)

    def select_external(self, name: str) -> "Session":
        """Make one of the loaded releases the active one (M2)."""
        if name not in self.externals:
            raise KeyError(f"no external release named {name!r}; loaded: "
                           f"{list(self.externals)}")
        return self._step("select_external", external=self.externals[name])

    @property
    def external_name(self) -> Optional[str]:
        return _ext_name(self.external) if self.external is not None else None

    def restart(self) -> "Session":
        """Start over on the same cohort and external information: nothing
        declared, nothing pending, no result, the counters reset."""
        return self._step("restarted", pending={}, pending_sources={},
                          declaration=None, verification=None, result=None,
                          results=[], turns=0, questions=0)

    def with_pending(self, answers: Dict[str, str], sources: Dict[str, str],
                     asked: Optional[List[str]] = None) -> "Session":
        """What is settled so far and its sources; `asked` are the roles put
        to the analyst on this turn, if any (counted as a question)."""
        pend = {k: v for k, v in (answers or {}).items() if v}
        # a role with no value keeps its source only when the source is an
        # open question ("ask: ..."): the message's wording contradicted the
        # value read, and a later message that does not answer it must not
        # let the 0/1 rule fill it (rubric task H063, 2026-10-02)
        src = {k: v for k, v in (sources or {}).items()
               if k in pend or str(v).startswith("ask:")}
        new = self._step("pending", pending=pend, pending_sources=src)
        if asked:
            new = replace(new, questions=new.questions + 1,
                          actions=new.actions[:-1]
                          + [dict(new.actions[-1], asked=list(asked))])
        return new

    def with_declaration(self, declaration: Any, verification: Any) -> "Session":
        return self._step("verified" if verification.admissible else "refused",
                          declaration=declaration, verification=verification,
                          pending={}, pending_sources={})

    def with_result(self, result: Any, outdir: Optional[str] = None) -> "Session":
        return self._step("done", result=result,
                          results=list(self.results) + [result],
                          temp=list(self.temp) + ([outdir] if outdir else []))

    def start_turn(self, message: str) -> "Session":
        return replace(self, turns=self.turns + 1,
                       actions=list(self.actions)
                       + [{"turn": self.turns + 1, "message": message[:4000]}])

    def log(self, **rec: Any) -> "Session":
        """A routing decision or a dropped proposal; no phase change."""
        return replace(self, actions=list(self.actions) + [rec])

    def take_calls(self, calls: List[Dict[str, Any]]) -> "Session":
        return replace(self, model_calls=list(self.model_calls) + list(calls))

    # ------------------------------------------------------------ provenance
    def phase_walk(self) -> List[str]:
        walk = []
        for a in self.actions:
            if "transition" in a:
                if not walk:
                    walk.append(a["phase"][0])
                walk.append(a["phase"][1])
        return walk or [self.phase.value]

    def to_provenance(self) -> Dict[str, Any]:
        """A JSON-safe snapshot for trace.json (`provenance.session`)."""
        decl = self.declaration
        return {
            "phase": self.phase.value,
            "phase_walk": self.phase_walk(),
            "turns": self.turns,
            "questions_asked": self.questions,
            # taken at run time (before `with_result`): the first message
            # led straight to the run, no question in between
            "completed_in_one_message": bool(self.turns == 1 and self.questions == 0),
            "external": self.external_line(),
            "test_data": bool(self.test_data_expr),
            "externals_loaded": list(self.externals),
            "active_external": self.external_name,
            "n_results": len(self.results),
            "remembered_declaration": bool(self.remembered),
            "declaration_sources": dict(getattr(decl, "sources", {}) or {}),
            "n_model_calls": len(self.model_calls),
            "n_actions": len(self.actions),
            "invariants_violated": self.invariants(),
        }
