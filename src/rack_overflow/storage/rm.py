"""Measured RM queries (`rm_measured`, D-033, D-069) on a caller's `Connection`. One row per
manual entry; soft-deleted rows (`deleted_at`) are never returned. RM-test sets are not copied
here: they are read from `set_entry` (`sessions.record_history`)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from rack_overflow.storage.schema import rm_measured


def insert_measured(
    connection: sa.Connection,
    user_id: int,
    exercise_id: int,
    *,
    n: int,
    weight_g: int,
    measured_on: str,
    created_at: str,
) -> int:
    """Store a measured nRM and return its id."""
    result = connection.execute(
        sa.insert(rm_measured).values(
            user_id=user_id,
            exercise_id=exercise_id,
            n=n,
            weight_g=weight_g,
            measured_on=measured_on,
            created_at=created_at,
        )
    )
    return int(result.inserted_primary_key[0])


def _live(user_id: int) -> sa.ColumnElement[bool]:
    return sa.and_(rm_measured.c.user_id == user_id, rm_measured.c.deleted_at.is_(None))


def measured_of(connection: sa.Connection, user_id: int, exercise_id: int) -> Sequence[sa.Row]:
    """The live measured RMs of the exercise, by `measured_on` then id."""
    query = (
        sa.select(rm_measured)
        .where(_live(user_id), rm_measured.c.exercise_id == exercise_id)
        .order_by(rm_measured.c.measured_on, rm_measured.c.id)
    )
    return connection.execute(query).all()


def get_measured(connection: sa.Connection, user_id: int, measured_id: int) -> sa.Row | None:
    """The live measured RM `measured_id` of `user_id`, or None."""
    query = sa.select(rm_measured).where(rm_measured.c.id == measured_id, _live(user_id))
    return connection.execute(query).first()


def soft_delete_measured(connection: sa.Connection, measured_id: int, deleted_at: str) -> None:
    """Mark the measured RM deleted: it stays in the database."""
    connection.execute(
        sa.update(rm_measured).where(rm_measured.c.id == measured_id).values(deleted_at=deleted_at)
    )
