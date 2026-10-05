"""Did the analyst actually write this column name?  One predicate, two users.

The elicitation corpus is built on the rule "a column name appears in a request
if and only if the key names it" (`eval/verify_corpus.py`), and the runtime
check at boundary 1 applies the same rule to what the model returns: a name the
request does not contain is not `quoted`, whatever the model says. The corpus
builder and the harness therefore import ONE function, so the standard the
evaluation scores is the standard the product enforces (master memory
section, build order 0).

The rule is deliberately narrow. Exactly three spellings of a column name count
as writing it: the name itself, underscores as spaces, underscores as hyphens.
No stemming, no edit distance, no synonyms. Loosening it is a product decision
that must leave `verify_corpus.py --quiet` passing on the unchanged corpus.
"""
from __future__ import annotations

import re
from typing import Iterable, List


def variants(name: str) -> List[str]:
    """The written forms of a column name a person might use, longest first."""
    v = {name, name.replace("_", " "), name.replace("_", "-")}
    return sorted(v, key=len, reverse=True)


def _pattern(form: str) -> str:
    # word boundaries that treat digits and underscores as word characters, so
    # `age` does not match inside `donor_age` and `1` does not match in `2011`
    return rf"(?<![a-z0-9_]){re.escape(form)}(?![a-z0-9_])"


def names_mentioned(text: str, columns: Iterable[str]) -> List[str]:
    """Which of `columns` the text actually names, longest match first.

    Every spelling of a matched name is masked before shorter names are tried,
    so `age` cannot match inside `donor_age` or inside `donor age`.
    """
    low = text.lower()
    found = []
    for col in sorted(set(columns), key=len, reverse=True):
        hit = False
        for form in variants(col.lower()):
            pat = _pattern(form)
            if re.search(pat, low):
                hit = True
                low = re.sub(pat, " \x00 ", low)
        if hit:
            found.append(col)
    return found


def mentions(text: str, name: str, columns: Iterable[str]) -> bool:
    """Does the text write `name`?  `name` is added to the candidate list, so a
    ghost column (named by the analyst, absent from the file) matches too and
    can be refused BY NAME downstream instead of being silently dropped."""
    if not name or not str(name).strip():
        return False
    cands = set(columns) | {str(name)}
    return str(name) in names_mentioned(text, cands)


def value_mentioned(text: str, value: str) -> bool:
    """Does the text write this event value (`1`, `TRUE`, `Dead`, ...)?"""
    if value is None or not str(value).strip():
        return False
    return re.search(_pattern(str(value).strip().lower()), text.lower()) is not None


def phrase_in(text: str, phrase: str) -> bool:
    """Is `phrase` in `text` word for word (case and whitespace normalised)?
    The rule M1 applies to an intent's evidence and the backing check applies
    to the phrase a described role was read from."""
    norm = lambda x: " ".join(str(x).lower().split())  # noqa: E731
    ph = norm(phrase)
    return bool(ph) and ph in norm(text)
