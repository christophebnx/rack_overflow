"""Template, slot and menu-option queries (SQLAlchemy Core) on a caller's `Connection`.

No rule is decided here: `domain/templates` validates, `services/templates` orchestrates. A taken
template name or an exercise offered twice in one menu raises `NameTakenError`. Slots are soft
deleted (`deleted_at`, D-058): every slot read below sees live slots only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from rack_overflow.domain.templates import Target, TemplateDraft
from rack_overflow.storage import positions
from rack_overflow.storage.db import guarded_write
from rack_overflow.storage.errors import NameTakenError
from rack_overflow.storage.schema import exercise, template, template_slot, template_slot_option

_EXERCISE_COLUMNS = (
    exercise.c.name.label("exercise_name"),
    exercise.c.movement_pattern.label("exercise_pattern"),
    exercise.c.archived_at.label("exercise_archived_at"),
)


# --- templates


def insert(connection: sa.Connection, user_id: int, draft: TemplateDraft, position: int) -> int:
    """Insert a template and return its id; a taken name → `NameTakenError`."""
    statement = sa.insert(template).values(
        user_id=user_id, name=draft.name, location=draft.location, position=position
    )
    result = guarded_write(
        connection, lambda: connection.execute(statement), NameTakenError(f'template "{draft.name}" exists')
    )
    return int(result.inserted_primary_key[0])


def update(connection: sa.Connection, template_id: int, draft: TemplateDraft) -> None:
    """Replace the template's name and location; a taken name → `NameTakenError`."""
    statement = (
        sa.update(template)
        .where(template.c.id == template_id)
        .values(name=draft.name, location=draft.location)
    )
    guarded_write(
        connection, lambda: connection.execute(statement), NameTakenError(f'template "{draft.name}" exists')
    )


def get(connection: sa.Connection, user_id: int, template_id: int) -> sa.Row | None:
    """The template `template_id` of `user_id`, or None."""
    query = sa.select(template).where(template.c.id == template_id, template.c.user_id == user_id)
    return connection.execute(query).first()


def list_all(connection: sa.Connection, user_id: int, *, include_archived: bool) -> Sequence[sa.Row]:
    """The user's templates by position, each with `slot_count` (live slots)."""
    count = sa.func.count(template_slot.c.id).label("slot_count")
    query = (
        sa.select(template, count)
        .outerjoin(
            template_slot,
            sa.and_(template_slot.c.template_id == template.c.id, template_slot.c.deleted_at.is_(None)),
        )
        .where(template.c.user_id == user_id)
        .group_by(template.c.id)
        .order_by(template.c.position, template.c.id)
    )
    if not include_archived:
        query = query.where(template.c.archived_at.is_(None))
    return connection.execute(query).all()


def names(connection: sa.Connection, user_id: int, *, except_id: int | None = None) -> list[str]:
    """Names of the user's templates (archived included), except `except_id`."""
    query = sa.select(template.c.name).where(template.c.user_id == user_id)
    if except_id is not None:
        query = query.where(template.c.id != except_id)
    return list(connection.execute(query).scalars())


def active_ids(connection: sa.Connection, user_id: int) -> list[int]:
    """Ids of the user's non-archived templates, in order."""
    query = (
        sa.select(template.c.id)
        .where(template.c.user_id == user_id, template.c.archived_at.is_(None))
        .order_by(template.c.position, template.c.id)
    )
    return list(connection.execute(query).scalars())


def next_position(connection: sa.Connection, user_id: int) -> int:
    """The position after the user's last non-archived template."""
    return positions.next_position(
        connection, template.c.position, template.c.user_id == user_id, template.c.archived_at.is_(None)
    )


def set_archived(
    connection: sa.Connection, template_id: int, archived_at: str | None, position: int | None = None
) -> None:
    """Archive (`archived_at` set) or restore (None, at `position`) the template."""
    values: dict[str, object] = {"archived_at": archived_at}
    if position is not None:
        values["position"] = position
    connection.execute(sa.update(template).where(template.c.id == template_id).values(**values))


# --- slots


def target_values(target: Target) -> dict[str, object]:
    """The `template_slot` target columns of a domain `Target`."""
    return {
        "target_sets": target.sets,
        "target_reps_min": target.reps_min,
        "target_reps_max": target.reps_max,
        "target_duration_s": target.duration_s,
        "target_distance_m": target.distance_m,
        "target_note": target.note,
    }


def target_of(row: sa.Row) -> Target:
    """The domain `Target` of a slot row."""
    return Target(
        row.target_sets,
        row.target_reps_min,
        row.target_reps_max,
        row.target_duration_s,
        row.target_distance_m,
        row.target_note,
    )


def slots_of(connection: sa.Connection, template_id: int) -> Sequence[sa.Row]:
    """The template's live slots by position, each with its exercise's name, pattern and
    `archived_at` (null for a menu)."""
    query = (
        sa.select(template_slot, *_EXERCISE_COLUMNS)
        .outerjoin(exercise, exercise.c.id == template_slot.c.exercise_id)
        .where(template_slot.c.template_id == template_id, template_slot.c.deleted_at.is_(None))
        .order_by(template_slot.c.position, template_slot.c.id)
    )
    return connection.execute(query).all()


def next_slot_position(connection: sa.Connection, template_id: int) -> int:
    """The position after the template's last live slot."""
    return positions.next_position(
        connection,
        template_slot.c.position,
        template_slot.c.template_id == template_id,
        template_slot.c.deleted_at.is_(None),
    )


def insert_slot(
    connection: sa.Connection,
    template_id: int,
    *,
    exercise_id: int | None = None,
    label: str | None = None,
    target: Target | None = None,
) -> int:
    """Append a slot (an exercise, or a menu named `label`) and return its id."""
    statement = sa.insert(template_slot).values(
        template_id=template_id,
        position=next_slot_position(connection, template_id),
        exercise_id=exercise_id,
        movement_pattern=label,
        **target_values(target or Target()),
    )
    return int(connection.execute(statement).inserted_primary_key[0])


def update_slot(
    connection: sa.Connection,
    slot_id: int,
    *,
    target: Target,
    exercise_id: int | None = None,
    label: str | None = None,
) -> None:
    """Set the slot's target, and its exercise (fixed slot) or its label (menu) when given."""
    values = target_values(target)
    if exercise_id is not None:
        values["exercise_id"] = exercise_id
    if label is not None:
        values["movement_pattern"] = label
    connection.execute(sa.update(template_slot).where(template_slot.c.id == slot_id).values(**values))


def soft_delete_slot(connection: sa.Connection, slot_id: int, deleted_at: str) -> None:
    """Remove the slot from the template (`deleted_at`); its options and history stay."""
    connection.execute(
        sa.update(template_slot).where(template_slot.c.id == slot_id).values(deleted_at=deleted_at)
    )


# --- menu options


def options_of(connection: sa.Connection, slot_ids: Sequence[int]) -> Sequence[sa.Row]:
    """The options of the slots, by slot then position, each with its exercise's name, pattern
    and `archived_at`."""
    query = (
        sa.select(template_slot_option, *_EXERCISE_COLUMNS)
        .join(exercise, exercise.c.id == template_slot_option.c.exercise_id)
        .where(template_slot_option.c.template_slot_id.in_(list(slot_ids)))
        .order_by(
            template_slot_option.c.template_slot_id,
            template_slot_option.c.position,
            template_slot_option.c.id,
        )
    )
    return connection.execute(query).all()


def insert_option(connection: sa.Connection, slot_id: int, exercise_id: int) -> int:
    """Append an option to the menu and return its id; the same exercise twice → `NameTakenError`."""
    position = positions.next_position(
        connection, template_slot_option.c.position, template_slot_option.c.template_slot_id == slot_id
    )
    statement = sa.insert(template_slot_option).values(
        template_slot_id=slot_id, exercise_id=exercise_id, position=position
    )
    result = guarded_write(
        connection, lambda: connection.execute(statement), NameTakenError("exercise already in the menu")
    )
    return int(result.inserted_primary_key[0])


def delete_option(connection: sa.Connection, option_id: int) -> None:
    """Delete the option row (menu configuration, not history)."""
    connection.execute(sa.delete(template_slot_option).where(template_slot_option.c.id == option_id))
