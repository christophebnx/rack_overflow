"""Exercise operations (D-031, D-054, D-056): exercises, their fields and aliases, search, one
transaction each. Exercises are archived, never deleted (invariant 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog, ordering, search
from rack_overflow.domain.catalog import (
    CatalogError,
    ExerciseDraft,
    FieldKind,
    FieldParams,
    FieldSource,
    Problem,
    VariableDraft,
)
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.ordering import DOWN as DOWN  # re-exported for the routes
from rack_overflow.domain.ordering import UP as UP
from rack_overflow.domain.timestamps import to_text
from rack_overflow.domain.vocabulary import CORE_QUANTITIES
from rack_overflow.storage import exercises as queries
from rack_overflow.storage import variables as variable_queries
from rack_overflow.storage.errors import NameTakenError


@dataclass(frozen=True)
class ExerciseForm:
    """An exercise form as typed."""

    name: str | None
    category: str | None
    location: str | None
    movement_pattern: str | None = None
    equipment: str | None = None


@dataclass(frozen=True)
class ExerciseSummary:
    """One row of the exercise list or of the search results."""

    id: int
    draft: ExerciseDraft
    archived: bool


@dataclass(frozen=True)
class VariableRef:
    """A variable as a field or the add-field list shows it."""

    id: int
    draft: VariableDraft
    archived: bool


@dataclass(frozen=True)
class FieldView:
    """A field of an exercise: a core quantity or a variable, its kind and parameters."""

    id: int
    position: int
    core_quantity: str | None
    variable: VariableRef | None
    kind: FieldKind
    params: FieldParams


@dataclass(frozen=True)
class AliasView:
    """An alias of an exercise."""

    id: int
    alias: str


@dataclass(frozen=True)
class ExerciseDetail:
    """An exercise with its fields, aliases, history flag and what can still be added."""

    id: int
    draft: ExerciseDraft
    archived: bool
    has_history: bool
    fields: tuple[FieldView, ...]
    aliases: tuple[AliasView, ...]
    addable_quantities: tuple[str, ...]
    addable_variables: tuple[VariableRef, ...]


@dataclass(frozen=True)
class FieldForm:
    """A field form as typed in display units (only the input of the chosen mode is passed)."""

    required: bool = False
    increment: str | None = None
    discrete_values: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class Suggestions:
    """Existing movement patterns and equipments, for the form's suggestions."""

    movement_patterns: tuple[str, ...]
    equipments: tuple[str, ...]


def _row(connection: sa.Connection, user_id: int, exercise_id: int) -> sa.Row:
    row = queries.get(connection, user_id, exercise_id)
    if row is None:
        raise NotFoundError(f"no exercise {exercise_id}")
    return row


def _draft_of(row: sa.Row) -> ExerciseDraft:
    return ExerciseDraft(row.name, row.category, row.movement_pattern, row.equipment, row.location)


def _summary(row: sa.Row) -> ExerciseSummary:
    return ExerciseSummary(row.id, _draft_of(row), row.archived_at is not None)


def _validated(
    connection: sa.Connection, user_id: int, form: ExerciseForm, except_id: int | None
) -> ExerciseDraft:
    """The form validated, its name unique, its pattern and equipment in their known spelling."""
    draft = catalog.exercise_draft(
        name=form.name,
        category=form.category,
        movement_pattern=form.movement_pattern,
        equipment=form.equipment,
        location=form.location,
    )
    catalog.check_name(draft.name, queries.names(connection, user_id, except_id=except_id))
    return catalog.with_known_spellings(
        draft, queries.movement_patterns(connection, user_id), queries.equipments(connection, user_id)
    )


def _name_taken() -> CatalogError:
    return CatalogError([Problem("name", "name_taken")])


def create(engine: Engine, user_id: int, form: ExerciseForm) -> int:
    """Create an exercise with the default fields of its category and return its id."""
    with engine.begin() as connection:
        draft = _validated(connection, user_id, form, None)
        try:
            exercise_id = queries.insert(connection, user_id, draft)
        except NameTakenError as error:
            raise _name_taken() from error
        for field in catalog.default_fields(draft.category):
            params = FieldParams(required=field.required, increment=field.increment)
            queries.insert_field(connection, exercise_id, core_quantity=field.quantity, params=params)
    return exercise_id


def update(engine: Engine, user_id: int, exercise_id: int, form: ExerciseForm) -> ExerciseDraft:
    """Edit the exercise's attributes (its fields stay as they are)."""
    with engine.begin() as connection:
        _row(connection, user_id, exercise_id)
        draft = _validated(connection, user_id, form, exercise_id)
        try:
            queries.update(connection, exercise_id, draft)
        except NameTakenError as error:
            raise _name_taken() from error
    return draft


def set_archived(engine: Engine, user_id: int, exercise_id: int, now: datetime | None) -> None:
    """Archive the exercise at `now`, or restore it when `now` is None; nothing else changes."""
    with engine.begin() as connection:
        _row(connection, user_id, exercise_id)
        queries.set_archived(connection, exercise_id, to_text(now) if now is not None else None)


def _variable_ref(row: sa.Row, variable_id: int, archived_at: str | None) -> VariableRef:
    return VariableRef(variable_id, variable_queries.draft_of(row), archived_at is not None)


def _field_view(row: sa.Row) -> FieldView:
    if row.variable_id is None:
        return FieldView(
            row.id,
            row.position,
            row.core_quantity,
            None,
            catalog.core_kind(row.core_quantity),
            queries.params_of(row),
        )
    ref = _variable_ref(row, row.variable_id, row.variable_archived_at)
    return FieldView(
        row.id, row.position, None, ref, catalog.variable_kind(ref.draft), queries.params_of(row)
    )


def _fields(connection: sa.Connection, exercise_id: int) -> list[FieldView]:
    return [_field_view(row) for row in queries.fields_of(connection, exercise_id)]


def get_detail(engine: Engine, user_id: int, exercise_id: int) -> ExerciseDetail:
    """The exercise page's data: attributes, fields, aliases, history flag, addable sources."""
    with engine.begin() as connection:
        row = _row(connection, user_id, exercise_id)
        fields = _fields(connection, exercise_id)
        linked = {field.variable.id for field in fields if field.variable is not None}
        variables = variable_queries.list_all(connection, user_id, include_archived=False)
        addable = sorted(
            (_variable_ref(var, var.id, None) for var in variables if var.id not in linked),
            key=lambda ref: (catalog.sort_key(ref.draft.label), ref.id),
        )
        used = {field.core_quantity for field in fields}
        return ExerciseDetail(
            id=row.id,
            draft=_draft_of(row),
            archived=row.archived_at is not None,
            has_history=queries.has_history(connection, exercise_id),
            fields=tuple(fields),
            aliases=tuple(AliasView(a.id, a.alias) for a in queries.aliases_of(connection, exercise_id)),
            addable_quantities=tuple(q for q in CORE_QUANTITIES if q not in used),
            addable_variables=tuple(addable),
        )


def list_exercises(engine: Engine, user_id: int, *, include_archived: bool = False) -> list[ExerciseSummary]:
    """The user's exercises (archived ones on demand), by normalised name."""
    with engine.begin() as connection:
        rows = queries.list_all(connection, user_id, include_archived=include_archived)
    return sorted((_summary(row) for row in rows), key=lambda s: (catalog.sort_key(s.draft.name), s.id))


def search_exercises(
    engine: Engine, user_id: int, query: str, *, include_archived: bool = False
) -> list[ExerciseSummary]:
    """Exercises matching `query` by name or alias, best first (D-056)."""
    with engine.begin() as connection:
        candidates = queries.search_candidates(connection, user_id, include_archived=include_archived)
        ids = search.rank(query, candidates)
        rows = {
            row.id: row for row in queries.list_all(connection, user_id, include_archived=include_archived)
        }
    return [_summary(rows[exercise_id]) for exercise_id in ids]


def suggestions(engine: Engine, user_id: int) -> Suggestions:
    """The user's movement patterns and equipments, first-seen spelling."""
    with engine.begin() as connection:
        return Suggestions(
            tuple(queries.movement_patterns(connection, user_id)),
            tuple(queries.equipments(connection, user_id)),
        )


# --- fields


def add_field(
    engine: Engine,
    user_id: int,
    exercise_id: int,
    *,
    core_quantity: str | None = None,
    variable_id: int | None = None,
) -> int:
    """Link a core quantity or a (non-archived) variable as the exercise's last field."""
    with engine.begin() as connection:
        _row(connection, user_id, exercise_id)
        if variable_id is not None:
            variable = variable_queries.get(connection, user_id, variable_id)
            if variable is None or variable.archived_at is not None:
                raise CatalogError([Problem("source", "invalid_choice")])
        elif core_quantity is not None:
            catalog.core_kind(core_quantity)
        else:
            raise CatalogError([Problem("source", "required")])
        try:
            return queries.insert_field(
                connection,
                exercise_id,
                core_quantity=core_quantity,
                variable_id=variable_id,
                params=FieldParams(),
            )
        except NameTakenError as error:
            raise CatalogError([Problem("source", "already_linked")]) from error


def _field(
    connection: sa.Connection, user_id: int, exercise_id: int, field_id: int
) -> tuple[FieldView, list[FieldView]]:
    _row(connection, user_id, exercise_id)
    fields = _fields(connection, exercise_id)
    for field in fields:
        if field.id == field_id:
            return field, fields
    raise NotFoundError(f"no field {field_id} on exercise {exercise_id}")


def update_field(
    engine: Engine, user_id: int, exercise_id: int, field_id: int, form: FieldForm
) -> FieldParams:
    """Set a field's parameters, typed in display units."""
    with engine.begin() as connection:
        field, _ = _field(connection, user_id, exercise_id, field_id)
        params = catalog.field_params(
            field.kind,
            required=form.required,
            increment=form.increment,
            discrete_values=form.discrete_values,
            default=form.default,
        )
        queries.update_field(connection, field_id, params)
    return params


def remove_field(engine: Engine, user_id: int, exercise_id: int, field_id: int) -> None:
    """Remove a field (its stored values stay); the last measure stays (`last_measure`)."""
    with engine.begin() as connection:
        _, fields = _field(connection, user_id, exercise_id, field_id)
        catalog.check_measures(
            FieldSource(f.core_quantity, f.variable.draft.scope if f.variable else None)
            for f in fields
            if f.id != field_id
        )
        queries.delete_field(connection, field_id)
        queries.set_positions(connection, [f.id for f in fields if f.id != field_id])


def move_field(engine: Engine, user_id: int, exercise_id: int, field_id: int, direction: str) -> int:
    """Swap the field with its neighbour (`up` / `down`) and renumber; its new index (0-based)."""
    ordering.check_direction(direction)
    with engine.begin() as connection:
        _, fields = _field(connection, user_id, exercise_id, field_id)
        ids, index = ordering.moved([f.id for f in fields], field_id, direction)
        queries.set_positions(connection, ids)
    return index


# --- aliases


def add_alias(engine: Engine, user_id: int, exercise_id: int, raw: str | None) -> str:
    """Add an alias to the exercise; returns it as stored."""
    with engine.begin() as connection:
        row = _row(connection, user_id, exercise_id)
        existing = [alias.alias for alias in queries.aliases_of(connection, exercise_id)]
        draft = catalog.alias_draft(raw, row.name, existing)
        try:
            queries.insert_alias(connection, exercise_id, draft)
        except NameTakenError as error:
            raise CatalogError([Problem("alias", "alias_taken")]) from error
    return draft.alias


def remove_alias(engine: Engine, user_id: int, exercise_id: int, alias_id: int) -> str:
    """Remove an alias of the exercise; returns its text."""
    with engine.begin() as connection:
        _row(connection, user_id, exercise_id)
        removed = queries.delete_alias(connection, exercise_id, alias_id)
    if removed is None:
        raise NotFoundError(f"no alias {alias_id} on exercise {exercise_id}")
    return removed
