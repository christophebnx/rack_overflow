"""Session, session row, set and setting queries (SQLAlchemy Core) on a caller's `Connection`.

No rule is decided here: `domain/sessions` and `domain/indicators` decide, `services/sessions`
orchestrates. Soft-deleted sessions and sets (`deleted_at`, D-021) are never returned, except by
`has_facts`, which counts history. A value is stored in `value_int` when it is an integer (numbers,
booleans), else in `value_text` (enum keys, text; D-032).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import sqlalchemy as sa

from rack_overflow.domain.indicators import RECORD_TYPES
from rack_overflow.storage import positions
from rack_overflow.storage.db import guarded_write
from rack_overflow.storage.errors import SessionOpenError
from rack_overflow.storage.schema import (
    exercise,
    exercise_setting,
    session,
    session_exercise,
    set_entry,
    set_value,
)

type StoredValue = int | str
CORE_COLUMNS: dict[str, str] = {
    "reps": "reps",
    "weight": "weight_g",
    "duration": "duration_s",
    "distance": "distance_m",
}
"""Core quantity → its `set_entry` column (D-018)."""


def _value_columns(value: StoredValue) -> dict[str, object]:
    if isinstance(value, int):
        return {"value_int": value, "value_text": None}
    return {"value_int": None, "value_text": value}


def _stored(row: sa.Row) -> StoredValue:
    return row.value_int if row.value_int is not None else str(row.value_text)


def _live_session(user_id: int) -> sa.ColumnElement[bool]:
    return sa.and_(session.c.user_id == user_id, session.c.deleted_at.is_(None))


# --- sessions


def insert_session(
    connection: sa.Connection,
    user_id: int,
    *,
    local_date: str,
    time_zone: str,
    started_at: str,
    location: str,
    template_id: int | None,
) -> int:
    """Insert an open session and return its id; another open session → `SessionOpenError`."""
    statement = sa.insert(session).values(
        user_id=user_id,
        local_date=local_date,
        time_zone=time_zone,
        started_at=started_at,
        location=location,
        template_id=template_id,
        status="open",
    )
    result = guarded_write(
        connection, lambda: connection.execute(statement), SessionOpenError("a session is already open")
    )
    return int(result.inserted_primary_key[0])


def get_session(connection: sa.Connection, user_id: int, session_id: int) -> sa.Row | None:
    """The non-deleted session `session_id` of `user_id`, or None."""
    query = sa.select(session).where(session.c.id == session_id, _live_session(user_id))
    return connection.execute(query).first()


def open_session(connection: sa.Connection, user_id: int) -> sa.Row | None:
    """The user's open session, or None."""
    query = sa.select(session).where(_live_session(user_id), session.c.status == "open")
    return connection.execute(query).first()


def latest_session(connection: sa.Connection, user_id: int) -> sa.Row | None:
    """The user's most recent non-deleted session (by `started_at`, then id), or None: its
    location and template preselect the next start."""
    query = (
        sa.select(session)
        .where(_live_session(user_id))
        .order_by(session.c.started_at.desc(), session.c.id.desc())
        .limit(1)
    )
    return connection.execute(query).first()


def close_session(connection: sa.Connection, session_id: int, ended_at: str) -> bool:
    """Close the session when it is open; whether it was written."""
    result = connection.execute(
        sa.update(session)
        .where(session.c.id == session_id, session.c.status == "open")
        .values(status="closed", ended_at=ended_at)
    )
    return result.rowcount == 1


# --- session rows


def insert_session_exercise(
    connection: sa.Connection, session_id: int, exercise_id: int, slot_id: int | None
) -> int:
    """Append a row (last position) and return its id."""
    position = positions.next_position(
        connection, session_exercise.c.position, session_exercise.c.session_id == session_id
    )
    result = connection.execute(
        sa.insert(session_exercise).values(
            session_id=session_id, exercise_id=exercise_id, template_slot_id=slot_id, position=position
        )
    )
    return int(result.inserted_primary_key[0])


_ROW_COLUMNS = (
    session_exercise,
    exercise.c.name.label("exercise_name"),
    exercise.c.category,
    exercise.c.equipment,
    exercise.c.archived_at.label("exercise_archived_at"),
)


def session_exercises(connection: sa.Connection, session_id: int) -> Sequence[sa.Row]:
    """The session's rows by position, each with its exercise's name, category, equipment and
    `exercise_archived_at`."""
    query = (
        sa.select(*_ROW_COLUMNS)
        .join(exercise, exercise.c.id == session_exercise.c.exercise_id)
        .where(session_exercise.c.session_id == session_id)
        .order_by(session_exercise.c.position, session_exercise.c.id)
    )
    return connection.execute(query).all()


def set_session_exercise_exercise(connection: sa.Connection, row_id: int, exercise_id: int) -> None:
    """Point the row to another exercise (a pick changed before any fact)."""
    connection.execute(
        sa.update(session_exercise).where(session_exercise.c.id == row_id).values(exercise_id=exercise_id)
    )


def has_facts(connection: sa.Connection, row_id: int) -> bool:
    """True when the row holds any set (soft-deleted included) or setting."""
    for query in (
        sa.select(set_entry.c.id).where(set_entry.c.session_exercise_id == row_id),
        sa.select(exercise_setting.c.id).where(exercise_setting.c.session_exercise_id == row_id),
    ):
        if connection.execute(query.limit(1)).first() is not None:
            return True
    return False


# --- sets


def _core_values(core: Mapping[str, int | None]) -> dict[str, int | None]:
    return {column: core.get(quantity) for quantity, column in CORE_COLUMNS.items()}


def insert_set(
    connection: sa.Connection,
    row_id: int,
    *,
    set_type: str,
    core: Mapping[str, int | None],
    completed_at: str,
) -> int:
    """Append a set to the row (last position among every set, deleted included); its id.
    `core` maps core quantities to canonical values."""
    position = positions.next_position(
        connection, set_entry.c.position, set_entry.c.session_exercise_id == row_id
    )
    result = connection.execute(
        sa.insert(set_entry).values(
            session_exercise_id=row_id,
            position=position,
            type=set_type,
            completed_at=completed_at,
            **_core_values(core),
        )
    )
    return int(result.inserted_primary_key[0])


def insert_set_values(connection: sa.Connection, set_id: int, values: Mapping[int, StoredValue]) -> None:
    """Store the set's variable values (variable id → value)."""
    rows = [
        {"set_entry_id": set_id, "variable_id": variable_id, **_value_columns(value)}
        for variable_id, value in values.items()
    ]
    if rows:
        connection.execute(sa.insert(set_value), rows)


def sets_of(connection: sa.Connection, row_ids: Sequence[int]) -> Sequence[sa.Row]:
    """The live sets of the rows, by row then position."""
    if not row_ids:
        return []
    query = (
        sa.select(set_entry)
        .where(set_entry.c.session_exercise_id.in_(row_ids), set_entry.c.deleted_at.is_(None))
        .order_by(set_entry.c.session_exercise_id, set_entry.c.position, set_entry.c.id)
    )
    return connection.execute(query).all()


def values_of(connection: sa.Connection, set_ids: Iterable[int]) -> dict[int, dict[int, StoredValue]]:
    """Set id → its variable values (variable id → value)."""
    ids = list(set_ids)
    found: dict[int, dict[int, StoredValue]] = {}
    if not ids:
        return found
    query = sa.select(set_value).where(set_value.c.set_entry_id.in_(ids)).order_by(set_value.c.id)
    for row in connection.execute(query):
        found.setdefault(row.set_entry_id, {})[row.variable_id] = _stored(row)
    return found


def get_set(connection: sa.Connection, user_id: int, set_id: int) -> sa.Row | None:
    """The live set `set_id` of a non-deleted session of `user_id` with its row's `session_id`,
    `exercise_id` and the session's `status`; None otherwise."""
    query = (
        sa.select(
            set_entry,
            session_exercise.c.session_id,
            session_exercise.c.exercise_id,
            session.c.status,
        )
        .join(session_exercise, session_exercise.c.id == set_entry.c.session_exercise_id)
        .join(session, session.c.id == session_exercise.c.session_id)
        .where(set_entry.c.id == set_id, set_entry.c.deleted_at.is_(None), _live_session(user_id))
    )
    return connection.execute(query).first()


def update_set(
    connection: sa.Connection, set_id: int, *, set_type: str, core: Mapping[str, int | None]
) -> None:
    """Replace the set's type and core values."""
    connection.execute(
        sa.update(set_entry).where(set_entry.c.id == set_id).values(type=set_type, **_core_values(core))
    )


def replace_set_values(
    connection: sa.Connection,
    set_id: int,
    values: Mapping[int, StoredValue],
    variable_ids: Iterable[int],
) -> None:
    """Replace the set's values of the variables `variable_ids` (the exercise's current fields)
    by `values`; the stored values of any other variable (archived or unlinked since) are kept
    (invariant 8)."""
    scope = list(variable_ids)
    connection.execute(
        sa.delete(set_value).where(set_value.c.set_entry_id == set_id, set_value.c.variable_id.in_(scope))
    )
    insert_set_values(connection, set_id, {key: value for key, value in values.items() if key in scope})


def soft_delete_set(connection: sa.Connection, set_id: int, deleted_at: str) -> None:
    """Mark the set deleted (D-021): it stays in the database."""
    connection.execute(sa.update(set_entry).where(set_entry.c.id == set_id).values(deleted_at=deleted_at))


# --- per-exercise reads (index of revision 0004)


def _exercise_sets(user_id: int, exercise_id: int) -> sa.Select:
    return (
        sa.select(set_entry, session_exercise.c.session_id)
        .join(session_exercise, session_exercise.c.id == set_entry.c.session_exercise_id)
        .join(session, session.c.id == session_exercise.c.session_id)
        .where(
            session_exercise.c.exercise_id == exercise_id,
            set_entry.c.deleted_at.is_(None),
            _live_session(user_id),
        )
    )


def last_performance(
    connection: sa.Connection, user_id: int, exercise_id: int, except_session_id: int
) -> Sequence[sa.Row]:
    """The live sets of the exercise in the most recent other non-deleted session holding one
    (by `started_at`, then id), by row position then set position (D-062)."""
    latest = (
        sa.select(session.c.id)
        .join(session_exercise, session_exercise.c.session_id == session.c.id)
        .join(set_entry, set_entry.c.session_exercise_id == session_exercise.c.id)
        .where(
            session_exercise.c.exercise_id == exercise_id,
            set_entry.c.deleted_at.is_(None),
            session.c.id != except_session_id,
            _live_session(user_id),
        )
        .order_by(session.c.started_at.desc(), session.c.id.desc())
        .limit(1)
    )
    found = connection.execute(latest).scalar_one_or_none()
    if found is None:
        return []
    query = (
        sa.select(set_entry)
        .join(session_exercise, session_exercise.c.id == set_entry.c.session_exercise_id)
        .where(
            session_exercise.c.session_id == found,
            session_exercise.c.exercise_id == exercise_id,
            set_entry.c.deleted_at.is_(None),
        )
        .order_by(session_exercise.c.position, set_entry.c.position, set_entry.c.id)
    )
    return connection.execute(query).all()


def last_settings(
    connection: sa.Connection, user_id: int, exercise_id: int, except_session_id: int
) -> dict[int, StoredValue]:
    """Per variable, the latest setting value of the exercise in the user's other non-deleted
    sessions (by `started_at`, then row id)."""
    query = (
        sa.select(exercise_setting)
        .join(session_exercise, session_exercise.c.id == exercise_setting.c.session_exercise_id)
        .join(session, session.c.id == session_exercise.c.session_id)
        .where(
            session_exercise.c.exercise_id == exercise_id,
            session.c.id != except_session_id,
            _live_session(user_id),
        )
        .order_by(session.c.started_at.desc(), session.c.id.desc(), session_exercise.c.id.desc())
    )
    found: dict[int, StoredValue] = {}
    for row in connection.execute(query):
        found.setdefault(row.variable_id, _stored(row))
    return found


def settings_of(connection: sa.Connection, row_id: int) -> dict[int, StoredValue]:
    """The row's stored settings (variable id → value)."""
    query = sa.select(exercise_setting).where(exercise_setting.c.session_exercise_id == row_id)
    return {row.variable_id: _stored(row) for row in connection.execute(query)}


def upsert_settings(connection: sa.Connection, row_id: int, values: Mapping[int, StoredValue | None]) -> None:
    """Write the row's settings: insert or update each value, delete a cleared one (None)."""
    stored = settings_of(connection, row_id)
    for variable_id, value in values.items():
        where = (
            exercise_setting.c.session_exercise_id == row_id,
            exercise_setting.c.variable_id == variable_id,
        )
        if value is None:
            connection.execute(sa.delete(exercise_setting).where(*where))
        elif variable_id in stored:
            connection.execute(sa.update(exercise_setting).where(*where).values(**_value_columns(value)))
        else:
            connection.execute(
                sa.insert(exercise_setting).values(
                    session_exercise_id=row_id, variable_id=variable_id, **_value_columns(value)
                )
            )


def record_history(connection: sa.Connection, user_id: int, exercise_id: int) -> Sequence[sa.Row]:
    """The exercise's live work and RM-test sets across the user's non-deleted sessions, by
    `(completed_at, id)`, each with its `session_id` (D-064)."""
    query = _exercise_sets(user_id, exercise_id).where(set_entry.c.type.in_(RECORD_TYPES))
    return connection.execute(query.order_by(set_entry.c.completed_at, set_entry.c.id)).all()


def recent_exercise_ids(connection: sa.Connection, user_id: int) -> list[int]:
    """Exercise ids by their latest non-deleted session (by `started_at`), newest first."""
    latest = sa.func.max(session.c.started_at)
    query = (
        sa.select(session_exercise.c.exercise_id)
        .join(session, session.c.id == session_exercise.c.session_id)
        .where(_live_session(user_id))
        .group_by(session_exercise.c.exercise_id)
        .order_by(latest.desc(), session_exercise.c.exercise_id)
    )
    return list(connection.execute(query).scalars())
