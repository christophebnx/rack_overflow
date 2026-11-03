"""The one text normalisation of the project (D-056): search, aliases, name uniqueness, codes.

`normalise` folds case and accents and turns every run of non-alphanumeric characters into one
space, so « Développé-couché » and « developpe couche » compare equal. `slug` derives stable keys.
"""

from __future__ import annotations

import re
import unicodedata

_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae"})
_WORDS = re.compile(r"[^\W_]+")


def normalise(text: str) -> str:
    """NFKD, combining marks removed, casefolded, ligatures expanded, words joined by one space."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = bare.casefold().translate(_LIGATURES)
    return " ".join(_WORDS.findall(folded))


def is_digits(text: str) -> bool:
    """True for non-empty ASCII decimal digits, the only text read as an integer id or count
    (`str.isdigit` alone also accepts « ² », which `int` then refuses)."""
    return text.isascii() and text.isdigit()


def slug(text: str) -> str:
    """`normalise(text)` with spaces turned into `_` (variable codes, enum keys); may be empty."""
    return normalise(text).replace(" ", "_")
