"""Variable operations (D-030, D-032, D-054), one transaction each.

A variable is shared: its one row is edited, so every linked exercise sees the change. Type,
scope and scale freeze once values exist; delete only without values, archive otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog
from rack_overflow.domain.catalog import CatalogError, FieldSource, Problem, ValueInput, VariableDraft
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.timestamps import to_text
from rack_overflow.storage import exercises as exercise_queries
from rack_overflow.storage import variables as queries
from rack_overflow.storage.errors import NameTakenError


@dataclass(frozen=True)
class VariableForm:
    """A variable form as typed (only the attributes of the chosen type are read)."""

    label: str | None
    var_type: str | None
    scope: str | None
    unit: str | None = None
    scale: str | None = None
    values: Sequence[ValueInput] = ()


@dataclass(frozen=True)
class VariableSummary:
    """One row of the variable list."""

    id: int
    draft: VariableDraft
    archived: bool
    linked_count: int


@dataclass(frozen=True)
class LinkedExercise:
    """An exercise linking a variable."""

    id: int
    name: str
    archived: bool


@dataclass(frozen=True)
class VariableDetail:
    """A variable with what its page needs: links, whether values exist, which enum keys are used."""

    id: int
    draft: VariableDraft
    archived: bool
    has_values: bool
    used_enum_keys: frozenset[str]
    linked: tuple[LinkedExercise, ...]


def _row(connection: sa.Connection, user_id: int, variable_id: int) -> sa.Row:
    row = queries.get(connection, user_id, variable_id)
    if row is None:
        raise NotFoundError(f"no variable {variable_id}")
    return row


def _draft(form: VariableForm, current: VariableDraft | None = None) -> VariableDraft:
    return catalog.variable_draft(
        label=form.label,
        var_type=form.var_type,
        scope=form.scope,
        unit=form.unit,
        scale=form.scale,
        values=form.values,
        existing=current.enum_values or () if current is not None else (),
        retired=current.retired_keys if current is not None else (),
    )


def _check_links(connection: sa.Connection, variable_id: int, field_name: str, scope: str | None) -> None:
    """Every exercise linking the variable keeps a measure once its scope is `scope` (None: the
    variable is deleted), checked in the caller's transaction before any write (D-054)."""
    linked = []
    for link in queries.linked_exercises(connection, variable_id):
        sources = [
            FieldSource(row.core_quantity, scope if row.variable_id == variable_id else row.scope)
            for row in exercise_queries.fields_of(connection, link.id)
            if row.variable_id != variable_id or scope is not None
        ]
        linked.append((link.name, sources))
    catalog.check_linked_measures(field_name, linked)


def create(engine: Engine, user_id: int, form: VariableForm) -> int:
    """Create a variable (code derived from the label once) and return its id."""
    draft = _draft(form)
    with engine.begin() as connection:
        code = catalog.variable_code(draft.label, queries.codes(connection, user_id))
        try:
            return queries.insert(connection, user_id, code, draft)
        except NameTakenError as error:
            raise CatalogError([Problem("label", "name_taken")]) from error


def update(engine: Engine, user_id: int, variable_id: int, form: VariableForm) -> VariableDraft:
    """Edit the shared variable; field parameters its new kind refuses are cleared on its links."""
    with engine.begin() as connection:
        current = queries.draft_of(_row(connection, user_id, variable_id))
        draft = _draft(form, current)
        catalog.variable_change(
            current,
            draft,
            has_values=queries.has_values(connection, variable_id),
            used_enum_keys=queries.used_enum_keys(connection, variable_id),
        )
        _check_links(connection, variable_id, "scope", draft.scope)
        queries.update(connection, variable_id, draft)
        kind = catalog.variable_kind(draft)
        for field in exercise_queries.fields_of_variable(connection, variable_id):
            params = exercise_queries.params_of(field)
            cleared = catalog.cleared_for(kind, params)
            if cleared != params:
                exercise_queries.update_field(connection, field.id, cleared)
    return draft


def set_archived(engine: Engine, user_id: int, variable_id: int, now: datetime | None) -> None:
    """Archive the variable at `now`, or restore it when `now` is None; always allowed."""
    with engine.begin() as connection:
        _row(connection, user_id, variable_id)
        queries.set_archived(connection, variable_id, to_text(now) if now is not None else None)


def delete(engine: Engine, user_id: int, variable_id: int) -> None:
    """Delete a variable without values, with its links; with values: `variable_in_use`."""
    with engine.begin() as connection:
        _row(connection, user_id, variable_id)
        if queries.has_values(connection, variable_id):
            raise CatalogError([Problem("delete", "variable_in_use")])
        _check_links(connection, variable_id, "delete", None)
        queries.delete(connection, variable_id)


def get_detail(engine: Engine, user_id: int, variable_id: int) -> VariableDetail:
    """The variable, its linked exercises, and whether values were stored."""
    with engine.begin() as connection:
        row = _row(connection, user_id, variable_id)
        linked = tuple(
            LinkedExercise(link.id, link.name, link.archived_at is not None)
            for link in queries.linked_exercises(connection, variable_id)
        )
        return VariableDetail(
            id=row.id,
            draft=queries.draft_of(row),
            archived=row.archived_at is not None,
            has_values=queries.has_values(connection, variable_id),
            used_enum_keys=frozenset(queries.used_enum_keys(connection, variable_id)),
            linked=linked,
        )


def list_variables(engine: Engine, user_id: int, *, include_archived: bool = False) -> list[VariableSummary]:
    """The user's variables (archived ones on demand), by normalised label."""
    with engine.begin() as connection:
        rows = queries.list_all(connection, user_id, include_archived=include_archived)
    summaries = [
        VariableSummary(row.id, queries.draft_of(row), row.archived_at is not None, row.linked_count)
        for row in rows
    ]
    return sorted(summaries, key=lambda summary: (catalog.sort_key(summary.draft.label), summary.id))
