"""Catalog form helpers shared by the routes (D-050): row ids within the database's integer range,
JSON form values as json-enc sends them, and refused input (`domain.catalog.CatalogError`) turned
into messages per field."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel

from rack_overflow.domain.catalog import CatalogError, Problem
from rack_overflow.web.locale import Catalog

ERROR_KEY_PREFIX = "catalog.error."
MAX_ID = 2**63 - 1  # largest SQLite INTEGER / Postgres BIGINT


def in_id_range(value: int) -> bool:
    """Whether `value` can be a row id (1..`MAX_ID`): a larger one cannot even be bound to a query."""
    return 0 < value <= MAX_ID


def row_id(value: int) -> int:
    """`value` when it can be a row id, else a 404: no row has it (never a 500 from the driver)."""
    if not in_id_range(value):
        raise HTTPException(status_code=404)
    return value


# A path id: an integer (else 422) that can be a row id (else 404, raised through the validator)
RowId = Annotated[int, AfterValidator(row_id)]


class MoveBody(BaseModel):
    """JSON body of every « Monter » / « Descendre » button: `direction` `up` or `down` (else 422)."""

    direction: Literal["up", "down"]


def move_focus(prefix: str, direction: str, index: int, total: int) -> str:
    """Id of the button that keeps the focus after a move: the same one (`{prefix}-monter` /
    `{prefix}-descendre`), or the other one when the moved row reached that end (L2 rule)."""
    up = direction == "up"
    if (up and index == 0) or (not up and index == total - 1):
        up = not up
    return f"{prefix}-monter" if up else f"{prefix}-descendre"


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
