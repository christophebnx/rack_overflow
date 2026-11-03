"""The catalog seed (D-057), applied by `rack migrate` after the schema upgrade.

Numbered steps (1: the exercises of brief section 6.1; L3 adds 2: templates) run when above the
user's `seed.version`, then the version is stored, all in one transaction: a second run adds
nothing, and a seeded exercise the user renamed or archived never comes back. Within a step, an
exercise whose normalised name exists is skipped. The data goes through the UI's validators.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog
from rack_overflow.domain.catalog import FieldParams
from rack_overflow.storage import app_settings, seed
from rack_overflow.storage import exercises as queries
from rack_overflow.storage.errors import StorageError

VERSION_KEY = "seed.version"

Step = Callable[[sa.Connection, int], int]


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


def _seed_exercise(connection: sa.Connection, user_id: int, item: Mapping[str, Any]) -> bool:
    """Insert one seed exercise unless its normalised name exists; True when inserted."""
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
    exercise_id = queries.insert(connection, user_id, draft)
    for quantity, params in fields:
        queries.insert_field(connection, exercise_id, core_quantity=quantity, params=params)
    aliases: list[str] = []
    for raw in item.get("aliases", []):
        alias = catalog.alias_draft(raw, draft.name, aliases)
        queries.insert_alias(connection, exercise_id, alias)
        aliases.append(alias.alias)
    return True


def _exercises_step(connection: sa.Connection, user_id: int) -> int:
    items = seed.load_exercises()
    try:
        return sum(_seed_exercise(connection, user_id, item) for item in items)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, catalog.CatalogError):
            raise
        raise StorageError(f"malformed seed exercise: {error!r}") from None


STEPS: dict[int, Step] = {1: _exercises_step}


def seed_catalog(engine: Engine, user_id: int, steps: Mapping[int, Step] = STEPS) -> int:
    """Run the seed steps above the user's stored version, in one transaction; the number of
    exercises created."""
    created = 0
    with engine.begin() as connection:
        stored = app_settings.get(connection, user_id, VERSION_KEY)
        version = int(stored) if stored is not None and stored.isdigit() else 0
        pending = sorted(step for step in steps if step > version)
        for step in pending:
            created += steps[step](connection, user_id)
        if pending:
            app_settings.put(connection, user_id, VERSION_KEY, str(pending[-1]))
    return created
