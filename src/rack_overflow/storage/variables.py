"""Variable queries (SQLAlchemy Core) on a caller's `Connection`. Enum values are stored as a JSON
list of `{"key", "label"}` in their display order (D-032); no rule is decided here."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from rack_overflow.domain.catalog import EnumValue, VariableDraft
from rack_overflow.storage.db import guarded_write
from rack_overflow.storage.errors import NameTakenError
from rack_overflow.storage.schema import (
    exercise,
    exercise_field,
    exercise_setting,
    set_value,
    variable,
)


def _values(draft: VariableDraft) -> dict[str, object]:
    enum: object = sa.null()
    if draft.enum_values is not None:
        enum = [{"key": value.key, "label": value.label} for value in draft.enum_values]
    return {
        "label": draft.label,
        "type": draft.type,
        "scope": draft.scope,
        "unit": draft.unit,
        "decimal_scale": draft.decimal_scale,
        "enum_values": enum,
    }


def draft_of(row: sa.Row) -> VariableDraft:
    """The domain view of a `variable` row (or of a row carrying the same column names)."""
    enum = None
    if row.enum_values is not None:
        enum = tuple(EnumValue(str(item["key"]), str(item["label"])) for item in row.enum_values)
    return VariableDraft(row.label, row.type, row.scope, row.unit, row.decimal_scale, enum)


def insert(connection: sa.Connection, user_id: int, code: str, draft: VariableDraft) -> int:
    """Insert a variable and return its id; a code already taken raises `NameTakenError`."""
    statement = sa.insert(variable).values(user_id=user_id, code=code, **_values(draft))
    refusal = NameTakenError(f'variable code "{code}" is taken')
    result = guarded_write(connection, lambda: connection.execute(statement), refusal)
    return int(result.inserted_primary_key[0])


def update(connection: sa.Connection, variable_id: int, draft: VariableDraft) -> None:
    """Replace the variable's attributes (its code never changes)."""
    connection.execute(sa.update(variable).where(variable.c.id == variable_id).values(**_values(draft)))


def get(connection: sa.Connection, user_id: int, variable_id: int) -> sa.Row | None:
    """The variable `variable_id` of `user_id`, or None."""
    query = sa.select(variable).where(variable.c.id == variable_id, variable.c.user_id == user_id)
    return connection.execute(query).first()


def codes(connection: sa.Connection, user_id: int) -> list[str]:
    """Every code of the user's variables, archived included."""
    return list(connection.execute(sa.select(variable.c.code).where(variable.c.user_id == user_id)).scalars())


def list_all(connection: sa.Connection, user_id: int, *, include_archived: bool) -> Sequence[sa.Row]:
    """The user's variables with `linked_count` (number of exercises linking each), by id."""
    linked = (
        sa.select(sa.func.count())
        .select_from(exercise_field)
        .where(exercise_field.c.variable_id == variable.c.id)
        .scalar_subquery()
    )
    query = sa.select(variable, linked.label("linked_count")).where(variable.c.user_id == user_id)
    if not include_archived:
        query = query.where(variable.c.archived_at.is_(None))
    return connection.execute(query.order_by(variable.c.id)).all()


def set_archived(connection: sa.Connection, variable_id: int, archived_at: str | None) -> None:
    """Archive (`archived_at` set) or restore (None) the variable."""
    connection.execute(
        sa.update(variable).where(variable.c.id == variable_id).values(archived_at=archived_at)
    )


def delete(connection: sa.Connection, variable_id: int) -> None:
    """Delete the variable and its `exercise_field` links (the caller checked it has no values)."""
    connection.execute(sa.delete(exercise_field).where(exercise_field.c.variable_id == variable_id))
    connection.execute(sa.delete(variable).where(variable.c.id == variable_id))


def has_values(connection: sa.Connection, variable_id: int) -> bool:
    """True when any `set_value` or `exercise_setting` row references the variable (soft-deleted
    sets included: history is history)."""
    for table in (set_value, exercise_setting):
        query = sa.select(table.c.id).where(table.c.variable_id == variable_id).limit(1)
        if connection.execute(query).first() is not None:
            return True
    return False


def used_enum_keys(connection: sa.Connection, variable_id: int) -> set[str]:
    """Every text value stored for the variable (the enum keys used in history)."""
    keys: set[str] = set()
    for table in (set_value, exercise_setting):
        query = sa.select(table.c.value_text).where(
            table.c.variable_id == variable_id, table.c.value_text.is_not(None)
        )
        keys.update(connection.execute(query.distinct()).scalars())
    return keys


def linked_exercises(connection: sa.Connection, variable_id: int) -> Sequence[sa.Row]:
    """`id`, `name`, `archived_at` of the exercises linking the variable, by name."""
    query = (
        sa.select(exercise.c.id, exercise.c.name, exercise.c.archived_at)
        .join(exercise_field, exercise_field.c.exercise_id == exercise.c.id)
        .where(exercise_field.c.variable_id == variable_id)
        .order_by(exercise.c.name, exercise.c.id)
    )
    return connection.execute(query).all()
