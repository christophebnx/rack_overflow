"""The catalog seed (D-057, D-060), applied by `rack migrate` after the schema upgrade.

Numbered steps (1: the exercises of brief section 6.1; 2: its four templates) run when above the
user's `seed.version`, then the version is stored, all in one transaction: a second run adds
nothing, and a seeded exercise or template the user renamed or archived never comes back. Within
a step, an exercise or template whose normalised name exists is skipped. Seed exercises carry a
stable `seed_key`; templates reference exercises by key. The data goes through the UI's validators.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog, templates
from rack_overflow.domain.catalog import FieldParams
from rack_overflow.domain.templates import Target, TemplateDraft
from rack_overflow.domain.text import is_digits, normalise
from rack_overflow.storage import app_settings, seed
from rack_overflow.storage import exercises as queries
from rack_overflow.storage import templates as template_queries
from rack_overflow.storage.errors import StorageError

VERSION_KEY = "seed.version"


@dataclass(frozen=True)
class SeedReport:
    """What a seed run created."""

    exercises: int = 0
    templates: int = 0

    def __add__(self, other: SeedReport) -> SeedReport:
        return SeedReport(self.exercises + other.exercises, self.templates + other.templates)


Step = Callable[[sa.Connection, int], SeedReport]


@contextmanager
def _malformed(kind: str) -> Iterator[None]:
    """A missing or mistyped attribute of the seed data becomes `StorageError`; a refusal of the
    domain validators (`CatalogError`) propagates as is."""
    try:
        yield
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, catalog.CatalogError):
            raise
        raise StorageError(f"malformed seed {kind}: {error!r}") from None


# --- step 1: exercises


def _field(item: Mapping[str, Any]) -> tuple[str, FieldParams]:
    quantity = str(item["quantity"])
    values = item.get("discrete_values")
    params = FieldParams(
        required=bool(item["required"]),
        increment=item.get("increment"),
        discrete_values=tuple(sorted(int(value) for value in values)) if values is not None else None,
    )
    catalog.check_field(catalog.core_kind(quantity), params)
    return quantity, params


def _attach_keys(connection: sa.Connection, user_id: int, items: Sequence[Mapping[str, Any]]) -> None:
    """Give each seed key without exercise to the unkeyed exercise of the item's normalised name
    (an exercise the user created, or one seeded before keys existed); the only name match."""
    keyed = queries.ids_by_seed_key(connection, user_id)
    unkeyed = queries.unkeyed_by_name(connection, user_id)
    for item in items:
        key = str(item["key"])
        exercise_id = unkeyed.pop(normalise(str(item["name"])), None)
        if key not in keyed and exercise_id is not None:
            queries.set_seed_key(connection, exercise_id, key)
            keyed[key] = exercise_id


def _seed_exercise(connection: sa.Connection, user_id: int, item: Mapping[str, Any]) -> bool:
    """Insert one seed exercise unless its normalised name exists; True when inserted. It carries
    its key unless another exercise already holds it."""
    draft = catalog.exercise_draft(
        name=item["name"],
        category=item["category"],
        movement_pattern=item.get("movement_pattern"),
        equipment=item.get("equipment"),
        location=item["location"],
    )
    if catalog.name_taken(draft.name, queries.names(connection, user_id)):
        return False
    fields = [_field(field) for field in item["fields"]]
    catalog.check_measures(catalog.FieldSource(core_quantity=quantity) for quantity, _ in fields)
    draft = catalog.with_known_spellings(
        draft, queries.movement_patterns(connection, user_id), queries.equipments(connection, user_id)
    )
    key = str(item["key"])
    free = key not in queries.ids_by_seed_key(connection, user_id)
    exercise_id = queries.insert(connection, user_id, draft, seed_key=key if free else None)
    for quantity, params in fields:
        queries.insert_field(connection, exercise_id, core_quantity=quantity, params=params)
    aliases: list[str] = []
    for raw in item.get("aliases", []):
        alias = catalog.alias_draft(raw, draft.name, aliases)
        queries.insert_alias(connection, exercise_id, alias)
        aliases.append(alias.alias)
    return True


def _exercises_step(connection: sa.Connection, user_id: int) -> SeedReport:
    items = seed.load_exercises()
    with _malformed("exercise"):
        _attach_keys(connection, user_id, items)
        return SeedReport(exercises=sum(_seed_exercise(connection, user_id, item) for item in items))


# --- step 2: templates


@dataclass(frozen=True)
class _SeedSlot:
    """A validated seed slot: one exercise key, or a menu label and its option keys."""

    keys: tuple[str, ...]
    label: str | None
    target: Target


@dataclass(frozen=True)
class _SeedTemplate:
    draft: TemplateDraft
    slots: tuple[_SeedSlot, ...]


def _target(raw: Mapping[str, Any]) -> Target:
    value = Target(
        sets=raw.get("sets"),
        reps_min=raw.get("reps_min"),
        reps_max=raw.get("reps_max"),
        duration_s=raw.get("duration_s"),
        distance_m=raw.get("distance_m"),
        note=raw.get("note"),
    )
    templates.check_target(value)
    return value


def _slot(raw: Mapping[str, Any]) -> _SeedSlot:
    target = _target(raw.get("target", {}))
    if "menu" in raw:
        keys = tuple(str(key) for key in raw["options"])
        if not keys:
            raise ValueError(f"menu {raw['menu']!r} without option")
        return _SeedSlot(keys, templates.menu_label(raw["menu"]), target)
    return _SeedSlot((str(raw["exercise"]),), None, target)


def _validated_template(raw: Mapping[str, Any]) -> _SeedTemplate:
    draft = templates.template_draft(name=raw["name"], location=raw["location"])
    slots = tuple(_slot(slot) for slot in raw["slots"])
    if len(slots) > templates.MAX_SLOTS:
        raise ValueError(f"template {draft.name!r} has too many slots")
    return _SeedTemplate(draft, slots)


def _seed_template(connection: sa.Connection, user_id: int, seeded: _SeedTemplate) -> bool:
    """Insert one seed template unless its normalised name exists; True when inserted. Keys
    without exercise are dropped, and a slot left without exercise is not created (D-060)."""
    if catalog.name_taken(seeded.draft.name, template_queries.names(connection, user_id)):
        return False
    ids = queries.ids_by_seed_key(connection, user_id)
    position = template_queries.next_position(connection, user_id)
    template_id = template_queries.insert(connection, user_id, seeded.draft, position)
    for slot in seeded.slots:
        resolved = [ids[key] for key in slot.keys if key in ids]
        if not resolved:
            continue
        if slot.label is None:
            template_queries.insert_slot(connection, template_id, exercise_id=resolved[0], target=slot.target)
            continue
        slot_id = template_queries.insert_slot(connection, template_id, label=slot.label, target=slot.target)
        offered: list[int] = []
        for exercise_id in resolved:
            templates.check_option_added(offered, exercise_id)
            template_queries.insert_option(connection, slot_id, exercise_id)
            offered.append(exercise_id)
    return True


def _templates_step(connection: sa.Connection, user_id: int) -> SeedReport:
    exercise_items = seed.load_exercises()
    template_items = seed.load_templates()
    with _malformed("template"):
        _attach_keys(connection, user_id, exercise_items)
        validated = [_validated_template(item) for item in template_items]
        return SeedReport(templates=sum(_seed_template(connection, user_id, item) for item in validated))


STEPS: dict[int, Step] = {1: _exercises_step, 2: _templates_step}


def _stored_version(connection: sa.Connection, user_id: int) -> int:
    """The user's seed version (0 when never seeded); an unreadable one raises `StorageError`."""
    stored = app_settings.get(connection, user_id, VERSION_KEY)
    if stored is None:
        return 0
    if not is_digits(stored):
        raise StorageError(f"unreadable {VERSION_KEY}: {stored!r}")
    return int(stored)


def seed_catalog(engine: Engine, user_id: int, steps: Mapping[int, Step] = STEPS) -> SeedReport:
    """Run the seed steps above the user's stored version, in one transaction; what they created."""
    report = SeedReport()
    with engine.begin() as connection:
        version = _stored_version(connection, user_id)
        pending = sorted(step for step in steps if step > version)
        for step in pending:
            report += steps[step](connection, user_id)
        if pending:
            app_settings.put(connection, user_id, VERSION_KEY, str(pending[-1]))
    return report
