"""User-facing strings (D-036): one flat `{key: text}` catalog per language, resolved on the server.

Imports no other project module. A malformed catalog fails at start-up; a missing key renders the
key itself and logs a warning once per key, so a gap is visible without breaking the page.
"""

from __future__ import annotations

import json
import logging
import string
from pathlib import Path

logger = logging.getLogger(__name__)
_FORMATTER = string.Formatter()


class LocaleError(Exception):
    """The catalog file is malformed, or a string was rendered without one of its parameters."""


class Catalog:
    """Read-only strings of one language with `{name}` placeholders."""

    def __init__(self, strings: dict[str, str]) -> None:
        for key, text in strings.items():
            _check_entry(key, text)
        self._strings = dict(strings)
        self._warned: set[str] = set()

    def __contains__(self, key: object) -> bool:
        return key in self._strings

    def keys(self) -> frozenset[str]:
        """Every key of the catalog."""
        return frozenset(self._strings)

    def text(self, key: str, **params: object) -> str:
        """The string of `key` with its placeholders filled; the key itself when it is missing."""
        template = self._strings.get(key)
        if template is None:
            if key not in self._warned:
                self._warned.add(key)
                logger.warning("missing string key %r", key)
            return key
        try:
            return template.format_map(params)
        except KeyError as error:
            raise LocaleError(f"string {key!r} needs parameter {error.args[0]!r}") from None


def _check_entry(key: object, text: object) -> None:
    if not isinstance(key, str) or not key:
        raise LocaleError(f"invalid key {key!r}")
    if not isinstance(text, str):
        raise LocaleError(f"value of {key!r} is not a string")
    try:
        fields = list(_FORMATTER.parse(text))
    except ValueError as error:
        raise LocaleError(f"bad placeholder in {key!r}: {error}") from None
    for _, name, spec, conversion in fields:
        if name is None:
            continue
        if not name.isidentifier() or spec or conversion:
            raise LocaleError(f"bad placeholder {{{name}}} in {key!r}: only {{name}} is allowed")


def load_catalog(path: Path) -> Catalog:
    """Read a flat JSON catalog (`utf-8-sig`); a malformed file raises `LocaleError`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise LocaleError(f"cannot read catalog {path}: {error}") from None
    if not isinstance(data, dict):
        raise LocaleError(f"catalog {path} is not a JSON object")
    return Catalog(data)
