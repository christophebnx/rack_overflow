"""Session template operations (D-058, D-059), one transaction each, `user_id` passed in.

Templates are archived, never deleted; slots are soft deleted; a menu's options are configuration
rows. Every reorder goes through `domain.ordering.moved`. Unknown or foreign ids (template, live
slot, option) raise `NotFoundError`; refused input raises `CatalogError`.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog, ordering, templates
from rack_overflow.domain.catalog import CatalogError, Problem
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.templates import EXERCISE, MENU, Target, TemplateDraft
from rack_overflow.domain.text import normalise
from rack_overflow.domain.timestamps import to_text
from rack_overflow.storage import exercises as exercise_queries
from rack_overflow.storage import positions
from rack_overflow.storage import templates as queries
from rack_overflow.storage.errors import NameTakenError
from rack_overflow.storage.schema import template, template_slot, template_slot_option


@dataclass(frozen=True)
class TemplateForm:
    """A template form as typed."""

    name: str | None
    location: str | None


@dataclass(frozen=True)
class SlotForm:
    """A slot form as typed: its exercise (fixed slot) or its label (menu), and its target in
    display units. Only the attribute of the slot's kind is read."""

    exercise_id: int | None = None
    label: str | None = None
    sets: str | None = None
    reps: str | None = None
    duration: str | None = None
    distance: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class TemplateSummary:
    """One row of the template list."""

    id: int
    draft: TemplateDraft
    slot_count: int
    archived: bool


@dataclass(frozen=True)
class ExerciseRef:
    """An exercise as a slot, an option or a select shows it."""

    id: int
    name: str
    movement_pattern: str | None
    archived: bool


@dataclass(frozen=True)
class ExerciseGroup:
    """Exercises sharing a movement pattern (None: no pattern), for grouped selects."""

    movement_pattern: str | None
    exercises: tuple[ExerciseRef, ...]


@dataclass(frozen=True)
class OptionView:
    """One exercise offered by a menu."""

    id: int
    exercise: ExerciseRef


@dataclass(frozen=True)
class SlotView:
    """A live slot: a fixed exercise, or a menu (`label` and its options); its target."""

    id: int
    position: int
    kind: str
    exercise: ExerciseRef | None
    label: str | None
    options: tuple[OptionView, ...]
    target: Target

    @property
    def name(self) -> str:
        """The exercise's name or the menu's label."""
        return self.exercise.name if self.exercise is not None else self.label or ""

    @property
    def skipped(self) -> bool:
        """True when a session would skip it: its exercise, or every option, is archived (D-058)."""
        if self.exercise is not None:
            return self.exercise.archived
        return all(option.exercise.archived for option in self.options)


@dataclass(frozen=True)
class TemplateDetail:
    """A template with its live slots, the exercises that can be added and the label suggestions."""

    id: int
    draft: TemplateDraft
    archived: bool
    slots: tuple[SlotView, ...]
    available: tuple[ExerciseRef, ...]
    patterns: tuple[str, ...]

    def slot(self, slot_id: int) -> SlotView:
        """The slot `slot_id` (`NotFoundError` when not live in this template)."""
        for slot in self.slots:
            if slot.id == slot_id:
                return slot
        raise NotFoundError(f"no slot {slot_id} in template {self.id}")

    def groups(self, *, exclude: Collection[int] = (), first: str | None = None) -> list[ExerciseGroup]:
        """Available exercises except `exclude`, grouped by movement pattern."""
        return exercise_groups([ref for ref in self.available if ref.id not in exclude], first=first)

    def option_groups(self, slot: SlotView) -> list[ExerciseGroup]:
        """What a menu can still offer: available exercises not in it, its own pattern first."""
        return self.groups(exclude={option.exercise.id for option in slot.options}, first=slot.label)


def exercise_groups(refs: Sequence[ExerciseRef], *, first: str | None = None) -> list[ExerciseGroup]:
    """`refs` grouped by movement pattern (patterns in name order, exercises by name, the group
    without pattern last); the group whose pattern equals `first` after normalisation leads."""
    by_pattern: dict[str | None, list[ExerciseRef]] = {}
    for ref in sorted(refs, key=lambda r: (catalog.sort_key(r.name), r.id)):
        key = normalise(ref.movement_pattern) if ref.movement_pattern else None
        by_pattern.setdefault(key, []).append(ref)
    lead = normalise(first) if first else None

    def order(key: str | None) -> tuple[int, int, str]:
        return (key != lead or key is None, key is None, key or "")

    return [
        ExerciseGroup(by_pattern[key][0].movement_pattern, tuple(by_pattern[key]))
        for key in sorted(by_pattern, key=order)
    ]


# --- helpers


def _row(connection: sa.Connection, user_id: int, template_id: int) -> sa.Row:
    row = queries.get(connection, user_id, template_id)
    if row is None:
        raise NotFoundError(f"no template {template_id}")
    return row


def _draft(row: sa.Row) -> TemplateDraft:
    return TemplateDraft(row.name, row.location)


def _ref(row: sa.Row, exercise_id: int) -> ExerciseRef:
    return ExerciseRef(
        exercise_id, row.exercise_name, row.exercise_pattern, row.exercise_archived_at is not None
    )


def slots_for_session(connection: sa.Connection, template_id: int) -> list[SlotView]:
    """The template's live slots in order with their options and targets: the one slot reader
    (template pages and session logging)."""
    rows = queries.slots_of(connection, template_id)
    options: dict[int, list[OptionView]] = {}
    for option in queries.options_of(connection, [row.id for row in rows]):
        options.setdefault(option.template_slot_id, []).append(
            OptionView(option.id, _ref(option, option.exercise_id))
        )
    return [
        SlotView(
            id=row.id,
            position=row.position,
            kind=EXERCISE if row.exercise_id is not None else MENU,
            exercise=_ref(row, row.exercise_id) if row.exercise_id is not None else None,
            label=row.movement_pattern if row.exercise_id is None else None,
            options=tuple(options.get(row.id, ())),
            target=queries.target_of(row),
        )
        for row in rows
    ]


def _slot(connection: sa.Connection, user_id: int, template_id: int, slot_id: int) -> list[SlotView]:
    """The template's live slots, checking that `slot_id` is one of them."""
    _row(connection, user_id, template_id)
    slots = slots_for_session(connection, template_id)
    if all(slot.id != slot_id for slot in slots):
        raise NotFoundError(f"no slot {slot_id} in template {template_id}")
    return slots


def _menu(connection: sa.Connection, user_id: int, template_id: int, slot_id: int) -> SlotView:
    slot = next(s for s in _slot(connection, user_id, template_id, slot_id) if s.id == slot_id)
    if slot.kind != MENU:
        raise NotFoundError(f"slot {slot_id} is not a menu")
    return slot


def _available(connection: sa.Connection, user_id: int, exercise_id: int | None) -> int:
    """`exercise_id` when it is one of the user's non-archived exercises, else a refusal."""
    if exercise_id is None:
        raise CatalogError([Problem("exercise_id", "required")])
    row = exercise_queries.get(connection, user_id, exercise_id)
    if row is None or row.archived_at is not None:
        raise CatalogError([Problem("exercise_id", "exercise_unavailable")])
    return exercise_id


def _collect[T](problems: list[Problem], check: Callable[[], T]) -> T | None:
    """`check()`, or None with its refusals added to `problems` (every problem shown at once)."""
    try:
        return check()
    except CatalogError as error:
        problems.extend(error.problems)
        return None


def _name_taken() -> CatalogError:
    return CatalogError([Problem("name", "template_name_taken")])


def _validated(
    connection: sa.Connection, user_id: int, form: TemplateForm, except_id: int | None
) -> TemplateDraft:
    draft = templates.template_draft(name=form.name, location=form.location)
    templates.check_template_name(draft.name, queries.names(connection, user_id, except_id=except_id))
    return draft


# --- templates


def create(engine: Engine, user_id: int, form: TemplateForm) -> int:
    """Create an empty template, last in the order; its id."""
    with engine.begin() as connection:
        draft = _validated(connection, user_id, form, None)
        try:
            return queries.insert(connection, user_id, draft, queries.next_position(connection, user_id))
        except NameTakenError as error:
            raise _name_taken() from error


def update(engine: Engine, user_id: int, template_id: int, form: TemplateForm) -> TemplateDraft:
    """Edit the template's name and location."""
    with engine.begin() as connection:
        _row(connection, user_id, template_id)
        draft = _validated(connection, user_id, form, template_id)
        try:
            queries.update(connection, template_id, draft)
        except NameTakenError as error:
            raise _name_taken() from error
    return draft


def set_archived(engine: Engine, user_id: int, template_id: int, now: datetime | None) -> None:
    """Archive the template at `now`, or restore it (last in the order) when `now` is None."""
    with engine.begin() as connection:
        row = _row(connection, user_id, template_id)
        if now is not None:
            queries.set_archived(connection, template_id, to_text(now))
        elif row.archived_at is not None:
            queries.set_archived(connection, template_id, None, queries.next_position(connection, user_id))


def move(engine: Engine, user_id: int, template_id: int, direction: str) -> int:
    """Move a non-archived template up or down among the others; its new index (0-based)."""
    ordering.check_direction(direction)
    with engine.begin() as connection:
        _row(connection, user_id, template_id)
        ids = queries.active_ids(connection, user_id)
        if template_id not in ids:
            raise NotFoundError(f"template {template_id} is archived")
        order, index = ordering.moved(ids, template_id, direction)
        positions.set_positions(connection, template, order)
    return index


def list_templates(engine: Engine, user_id: int, *, include_archived: bool = False) -> list[TemplateSummary]:
    """The user's templates in their order (archived ones on demand, in the same list)."""
    with engine.begin() as connection:
        rows = queries.list_all(connection, user_id, include_archived=include_archived)
    return [TemplateSummary(row.id, _draft(row), row.slot_count, row.archived_at is not None) for row in rows]


def get_detail(engine: Engine, user_id: int, template_id: int) -> TemplateDetail:
    """The template page's data: attributes, live slots, addable exercises, label suggestions."""
    with engine.begin() as connection:
        row = _row(connection, user_id, template_id)
        exercises = exercise_queries.list_all(connection, user_id, include_archived=False)
        return TemplateDetail(
            id=row.id,
            draft=_draft(row),
            archived=row.archived_at is not None,
            slots=tuple(slots_for_session(connection, template_id)),
            available=tuple(ExerciseRef(e.id, e.name, e.movement_pattern, False) for e in exercises),
            patterns=tuple(exercise_queries.movement_patterns(connection, user_id)),
        )


# --- slots


def add_slot(
    engine: Engine,
    user_id: int,
    template_id: int,
    *,
    kind: str | None,
    exercise_id: int | None,
    label: str | None = None,
) -> int:
    """Append a slot: an exercise, or a menu named `label` with `exercise_id` as its first option."""
    with engine.begin() as connection:
        _row(connection, user_id, template_id)
        problems: list[Problem] = []
        clean_kind = catalog.choice_input(problems, "kind", kind, templates.SLOT_KINDS)
        catalog.raise_if(problems)
        templates.check_slot_added(len(queries.slots_of(connection, template_id)))
        menu_label = _collect(problems, lambda: templates.menu_label(label)) if clean_kind == MENU else None
        chosen = _collect(problems, lambda: _available(connection, user_id, exercise_id))
        catalog.raise_if(problems)
        assert chosen is not None
        if clean_kind == EXERCISE:
            return queries.insert_slot(connection, template_id, exercise_id=chosen)
        slot_id = queries.insert_slot(connection, template_id, label=menu_label)
        queries.insert_option(connection, slot_id, chosen)
        return slot_id


def update_slot(engine: Engine, user_id: int, template_id: int, slot_id: int, form: SlotForm) -> SlotView:
    """Save a slot: its exercise (fixed slot; the current one is kept even when archived) or its
    label (menu), and its target; returns the slot as saved."""
    with engine.begin() as connection:
        slots = _slot(connection, user_id, template_id, slot_id)
        slot = next(s for s in slots if s.id == slot_id)
        problems: list[Problem] = []
        exercise_id = label = None
        if slot.kind == MENU:
            label = _collect(problems, lambda: templates.menu_label(form.label))
        elif slot.exercise is not None and form.exercise_id == slot.exercise.id:
            exercise_id = form.exercise_id  # unchanged: kept even when archived
        else:
            exercise_id = _collect(problems, lambda: _available(connection, user_id, form.exercise_id))
        target = _collect(
            problems,
            lambda: templates.target(
                sets=form.sets, reps=form.reps, duration=form.duration, distance=form.distance, note=form.note
            ),
        )
        catalog.raise_if(problems)
        assert target is not None
        queries.update_slot(connection, slot_id, target=target, exercise_id=exercise_id, label=label)
        return next(s for s in slots_for_session(connection, template_id) if s.id == slot_id)


def move_slot(engine: Engine, user_id: int, template_id: int, slot_id: int, direction: str) -> int:
    """Move a slot up or down; its new index (0-based)."""
    ordering.check_direction(direction)
    with engine.begin() as connection:
        slots = _slot(connection, user_id, template_id, slot_id)
        order, index = ordering.moved([slot.id for slot in slots], slot_id, direction)
        positions.set_positions(connection, template_slot, order)
    return index


def remove_slot(engine: Engine, user_id: int, template_id: int, slot_id: int, now: datetime) -> None:
    """Soft delete the slot (its options and history references stay) and renumber the others."""
    with engine.begin() as connection:
        slots = _slot(connection, user_id, template_id, slot_id)
        queries.soft_delete_slot(connection, slot_id, to_text(now))
        positions.set_positions(connection, template_slot, [s.id for s in slots if s.id != slot_id])


# --- menu options


def add_option(engine: Engine, user_id: int, template_id: int, slot_id: int, exercise_id: int | None) -> int:
    """Offer one more (non-archived) exercise in a menu, last; the option's id."""
    with engine.begin() as connection:
        slot = _menu(connection, user_id, template_id, slot_id)
        chosen = _available(connection, user_id, exercise_id)
        templates.check_option_added([option.exercise.id for option in slot.options], chosen)
        try:
            return queries.insert_option(connection, slot_id, chosen)
        except NameTakenError as error:
            raise CatalogError([Problem("exercise_id", "option_taken")]) from error


def _option_ids(slot: SlotView, option_id: int) -> list[int]:
    ids = [option.id for option in slot.options]
    if option_id not in ids:
        raise NotFoundError(f"no option {option_id} in slot {slot.id}")
    return ids


def move_option(
    engine: Engine, user_id: int, template_id: int, slot_id: int, option_id: int, direction: str
) -> int:
    """Move a menu option up or down; its new index (0-based)."""
    ordering.check_direction(direction)
    with engine.begin() as connection:
        ids = _option_ids(_menu(connection, user_id, template_id, slot_id), option_id)
        order, index = ordering.moved(ids, option_id, direction)
        positions.set_positions(connection, template_slot_option, order)
    return index


def remove_option(engine: Engine, user_id: int, template_id: int, slot_id: int, option_id: int) -> None:
    """Remove an option from a menu (never its last one, `last_option`) and renumber the others."""
    with engine.begin() as connection:
        ids = _option_ids(_menu(connection, user_id, template_id, slot_id), option_id)
        templates.check_option_removed(len(ids))
        queries.delete_option(connection, option_id)
        positions.set_positions(connection, template_slot_option, [i for i in ids if i != option_id])
