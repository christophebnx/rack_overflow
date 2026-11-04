"""Catalog form helpers shared by the routes (D-050): row ids within the database's integer range,
JSON form values as json-enc sends them, and refused input (`domain.catalog.CatalogError`) turned
into messages per field."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel

from rack_overflow.domain.catalog import CatalogError, Problem
from rack_overflow.domain.ordering import DIRECTIONS, DOWN, UP
from rack_overflow.domain.text import is_digits
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


def select_id(raw: str | None) -> int | None:
    """An id sent as text by a select or a button value: empty → None (refused by the service),
    not an integer → 422, beyond any row id → 404."""
    if raw is None or not raw.strip():
        return None
    if not is_digits(raw.strip()):
        raise HTTPException(status_code=422)
    return row_id(int(raw))


# A path id: an integer (else 422) that can be a row id (else 404, raised through the validator)
RowId = Annotated[int, AfterValidator(row_id)]


BUTTON_SUFFIXES = {UP: "monter", DOWN: "descendre"}  # id suffix of each move button


def _direction(value: str) -> str:
    if value not in DIRECTIONS:
        raise ValueError("direction")
    return value


class MoveBody(BaseModel):
    """JSON body of every « Monter » / « Descendre » button: `direction` one of
    `domain.ordering.DIRECTIONS` (else 422)."""

    direction: Annotated[str, AfterValidator(_direction)]


def move_focus(prefix: str, direction: str, index: int, total: int, *, alone: str | None = None) -> str:
    """Id of the element that keeps the focus after a move: the same button (`{prefix}-monter` /
    `{prefix}-descendre`), the other one when the moved row reached that end (L2 rule), or, when
    the row is alone and has no enabled move button, `alone` (default: the row's « Modifier »,
    `{prefix}-modifier`)."""
    if total <= 1:
        return alone or f"{prefix}-modifier"
    if (direction == UP and index == 0) or (direction == DOWN and index == total - 1):
        direction = DOWN if direction == UP else UP
    return f"{prefix}-{BUTTON_SUFFIXES[direction]}"


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
