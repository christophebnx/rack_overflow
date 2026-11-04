"""Exercise, field and alias queries (SQLAlchemy Core) on a caller's `Connection`.

No rule is decided here: `domain/catalog` validates, `services/exercises` orchestrates. Unique
violations (exercise name, a field linked twice, an alias twice) raise `NameTakenError`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa

from rack_overflow.domain.catalog import AliasDraft, ExerciseDraft, FieldParams
from rack_overflow.domain.search import Candidate
from rack_overflow.domain.text import normalise
from rack_overflow.storage import positions
from rack_overflow.storage.db import guarded_write
from rack_overflow.storage.errors import NameTakenError
from rack_overflow.storage.schema import (
    exercise,
    exercise_alias,
    exercise_field,
    session_exercise,
    variable,
)


def _guarded[T](connection: sa.Connection, write: Callable[[], T], message: str) -> T:
    return guarded_write(connection, write, NameTakenError(message))


def _attributes(draft: ExerciseDraft) -> dict[str, object]:
    return {
        "name": draft.name,
        "category": draft.category,
        "movement_pattern": draft.movement_pattern,
        "equipment": draft.equipment,
        "location": draft.location,
    }


# --- exercises


def insert(connection: sa.Connection, user_id: int, draft: ExerciseDraft, seed_key: str | None = None) -> int:
    """Insert an exercise (a seeded one with its `seed_key`) and return its id."""
    values = {"user_id": user_id, "seed_key": seed_key, **_attributes(draft)}
    result = _guarded(
        connection,
        lambda: connection.execute(sa.insert(exercise).values(values)),
        f'exercise "{draft.name}" exists',
    )
    return int(result.inserted_primary_key[0])


def set_seed_key(connection: sa.Connection, exercise_id: int, seed_key: str) -> None:
    """Give the exercise its seed identity (D-060)."""
    connection.execute(sa.update(exercise).where(exercise.c.id == exercise_id).values(seed_key=seed_key))


def ids_by_seed_key(connection: sa.Connection, user_id: int) -> dict[str, int]:
    """Seed key → id of the user's keyed exercises (archived included)."""
    query = sa.select(exercise.c.seed_key, exercise.c.id).where(
        exercise.c.user_id == user_id, exercise.c.seed_key.is_not(None)
    )
    return {row.seed_key: row.id for row in connection.execute(query)}


def unkeyed_by_name(connection: sa.Connection, user_id: int) -> dict[str, int]:
    """Normalised name → id of the user's exercises without seed key (archived included)."""
    query = sa.select(exercise.c.name, exercise.c.id).where(
        exercise.c.user_id == user_id, exercise.c.seed_key.is_(None)
    )
    return {normalise(row.name): row.id for row in connection.execute(query)}


def update(connection: sa.Connection, exercise_id: int, draft: ExerciseDraft) -> None:
    """Replace the exercise's attributes."""
    _guarded(
        connection,
        lambda: connection.execute(
            sa.update(exercise).where(exercise.c.id == exercise_id).values(**_attributes(draft))
        ),
        f'exercise "{draft.name}" exists',
    )


def get(connection: sa.Connection, user_id: int, exercise_id: int) -> sa.Row | None:
    """The exercise `exercise_id` of `user_id`, or None."""
    query = sa.select(exercise).where(exercise.c.id == exercise_id, exercise.c.user_id == user_id)
    return connection.execute(query).first()


def list_all(connection: sa.Connection, user_id: int, *, include_archived: bool) -> Sequence[sa.Row]:
    """The user's exercises, by id."""
    query = sa.select(exercise).where(exercise.c.user_id == user_id)
    if not include_archived:
        query = query.where(exercise.c.archived_at.is_(None))
    return connection.execute(query.order_by(exercise.c.id)).all()


def names(connection: sa.Connection, user_id: int, *, except_id: int | None = None) -> list[str]:
    """Names of the user's exercises (archived included), except `except_id`."""
    query = sa.select(exercise.c.name).where(exercise.c.user_id == user_id)
    if except_id is not None:
        query = query.where(exercise.c.id != except_id)
    return list(connection.execute(query).scalars())


def set_archived(connection: sa.Connection, exercise_id: int, archived_at: str | None) -> None:
    """Archive (`archived_at` set) or restore (None) the exercise; nothing else changes."""
    connection.execute(
        sa.update(exercise).where(exercise.c.id == exercise_id).values(archived_at=archived_at)
    )


def has_history(connection: sa.Connection, exercise_id: int) -> bool:
    """True when the exercise appears in any session."""
    query = sa.select(session_exercise.c.id).where(session_exercise.c.exercise_id == exercise_id).limit(1)
    return connection.execute(query).first() is not None


def _distinct(connection: sa.Connection, user_id: int, column: sa.Column[str]) -> list[str]:
    query = (
        sa.select(column)
        .where(exercise.c.user_id == user_id, column.is_not(None))
        .group_by(column)
        .order_by(sa.func.min(exercise.c.id))
    )
    return list(connection.execute(query).scalars())


def movement_patterns(connection: sa.Connection, user_id: int) -> list[str]:
    """Distinct movement patterns of the user's exercises, first-seen first."""
    return _distinct(connection, user_id, exercise.c.movement_pattern)


def equipments(connection: sa.Connection, user_id: int) -> list[str]:
    """Distinct equipments of the user's exercises, first-seen first."""
    return _distinct(connection, user_id, exercise.c.equipment)


def search_candidates(connection: sa.Connection, user_id: int, *, include_archived: bool) -> list[Candidate]:
    """Every exercise of the user with its aliases (one query), for `domain.search.rank`."""
    query = (
        sa.select(exercise.c.id, exercise.c.name, exercise_alias.c.alias)
        .outerjoin(exercise_alias, exercise_alias.c.exercise_id == exercise.c.id)
        .where(exercise.c.user_id == user_id)
        .order_by(exercise.c.id, exercise_alias.c.id)
    )
    if not include_archived:
        query = query.where(exercise.c.archived_at.is_(None))
    found: dict[int, tuple[str, list[str]]] = {}
    for row in connection.execute(query):
        _, aliases = found.setdefault(row.id, (row.name, []))
        if row.alias is not None:
            aliases.append(row.alias)
    return [Candidate(key, name, tuple(aliases)) for key, (name, aliases) in found.items()]


# --- fields

_FIELD_COLUMNS = (
    exercise_field,
    variable.c.label,
    variable.c.type,
    variable.c.scope,
    variable.c.unit,
    variable.c.decimal_scale,
    variable.c.enum_values,
    variable.c.archived_at.label("variable_archived_at"),
)


def fields_of(connection: sa.Connection, exercise_id: int) -> Sequence[sa.Row]:
    """The exercise's fields by position, each with its variable's columns (null for a core field)."""
    query = (
        sa.select(*_FIELD_COLUMNS)
        .outerjoin(variable, variable.c.id == exercise_field.c.variable_id)
        .where(exercise_field.c.exercise_id == exercise_id)
        .order_by(exercise_field.c.position, exercise_field.c.id)
    )
    return connection.execute(query).all()


def fields_of_variable(connection: sa.Connection, variable_id: int) -> Sequence[sa.Row]:
    """Every field linking the variable (any exercise)."""
    query = sa.select(exercise_field).where(exercise_field.c.variable_id == variable_id)
    return connection.execute(query).all()


def _params(params: FieldParams) -> dict[str, object]:
    values = list(params.discrete_values) if params.discrete_values is not None else sa.null()
    return {
        "required": params.required,
        "increment": params.increment,
        "discrete_values": values,
        "default_int": params.default_int,
        "default_text": params.default_text,
    }


def params_of(row: sa.Row) -> FieldParams:
    """The domain view of a field row's parameters."""
    values = tuple(int(value) for value in row.discrete_values) if row.discrete_values is not None else None
    return FieldParams(bool(row.required), row.increment, values, row.default_int, row.default_text)


def insert_field(
    connection: sa.Connection,
    exercise_id: int,
    *,
    core_quantity: str | None = None,
    variable_id: int | None = None,
    params: FieldParams,
) -> int:
    """Append a field (last position) and return its id; a source linked twice → `NameTakenError`."""
    values = {
        "exercise_id": exercise_id,
        "core_quantity": core_quantity,
        "variable_id": variable_id,
        "position": positions.next_position(
            connection, exercise_field.c.position, exercise_field.c.exercise_id == exercise_id
        ),
        **_params(params),
    }
    result = _guarded(
        connection,
        lambda: connection.execute(sa.insert(exercise_field).values(**values)),
        "field already linked",
    )
    return int(result.inserted_primary_key[0])


def update_field(connection: sa.Connection, field_id: int, params: FieldParams) -> None:
    """Replace the field's parameters."""
    connection.execute(
        sa.update(exercise_field).where(exercise_field.c.id == field_id).values(**_params(params))
    )


def delete_field(connection: sa.Connection, field_id: int) -> None:
    """Delete the field row only: stored set values stay (brief section 7.1)."""
    connection.execute(sa.delete(exercise_field).where(exercise_field.c.id == field_id))


def set_positions(connection: sa.Connection, field_ids: Sequence[int]) -> None:
    """Renumber the fields `0..n-1` in the order of `field_ids`."""
    positions.set_positions(connection, exercise_field, field_ids)


# --- aliases


def aliases_of(connection: sa.Connection, exercise_id: int) -> Sequence[sa.Row]:
    """The exercise's aliases, oldest first."""
    query = sa.select(exercise_alias).where(exercise_alias.c.exercise_id == exercise_id)
    return connection.execute(query.order_by(exercise_alias.c.id)).all()


def insert_alias(connection: sa.Connection, exercise_id: int, draft: AliasDraft) -> int:
    """Insert an alias and return its id; the same normalised alias twice → `NameTakenError`."""
    statement = sa.insert(exercise_alias).values(
        exercise_id=exercise_id, alias=draft.alias, alias_normalised=draft.normalised
    )
    result = _guarded(connection, lambda: connection.execute(statement), f'alias "{draft.alias}" exists')
    return int(result.inserted_primary_key[0])


def delete_alias(connection: sa.Connection, exercise_id: int, alias_id: int) -> str | None:
    """Delete the alias of this exercise; its text, or None when there was none."""
    row = connection.execute(
        sa.select(exercise_alias.c.alias).where(
            exercise_alias.c.id == alias_id, exercise_alias.c.exercise_id == exercise_id
        )
    ).first()
    if row is None:
        return None
    connection.execute(sa.delete(exercise_alias).where(exercise_alias.c.id == alias_id))
    return str(row.alias)
