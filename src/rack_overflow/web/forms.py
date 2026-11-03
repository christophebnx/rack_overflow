"""Catalog form helpers shared by the routes (D-050): JSON form values as json-enc sends them, and
refused input (`domain.catalog.CatalogError`) turned into messages per field."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from rack_overflow.domain.catalog import CatalogError, Problem
from rack_overflow.web.locale import Catalog

ERROR_KEY_PREFIX = "catalog.error."


def as_list(value: str | Sequence[str] | None) -> list[str]:
    """A repeated form value as a list: json-enc sends one value as a string, several as a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def checked(value: str | Sequence[str] | None) -> bool:
    """A checkbox is sent only when checked."""
    return bool(as_list(value))


@dataclass(frozen=True)
class FormErrors:
    """Messages of a refused form by input id, the first invalid input, the first message."""

    messages: Mapping[str, str] = field(default_factory=dict)
    first_id: str | None = None
    first_message: str | None = None

    def __bool__(self) -> bool:
        return bool(self.messages)

    def get(self, input_id: str) -> str:
        """The message of `input_id`, or an empty string."""
        return self.messages.get(input_id, "")


NO_ERRORS = FormErrors()


def problem_text(catalog: Catalog, problem: Problem) -> str:
    """The French message of one problem (`catalog.error.<code>`; a missing key shows the key)."""
    return catalog.text(ERROR_KEY_PREFIX + problem.code, **problem.params)


def form_errors(catalog: Catalog, error: CatalogError, ids: Mapping[str, str], fallback: str) -> FormErrors:
    """Messages per input id: each problem's field is mapped through `ids` (else `fallback`);
    several messages for one input are joined; the order follows the problems."""
    messages: dict[str, str] = {}
    for problem in error.problems:
        input_id = ids.get(problem.field, fallback)
        text = problem_text(catalog, problem)
        messages[input_id] = f"{messages[input_id]} {text}" if input_id in messages else text
    first = next(iter(messages), None)
    return FormErrors(messages, first, messages[first] if first else None)
