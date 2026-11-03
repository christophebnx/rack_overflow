"""The packaged seed data (D-057, D-060): French exercise and template data shipped inside
the package, read through `importlib.resources` so it works from a source tree and from an
installed wheel."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from rack_overflow.storage.errors import StorageError

PACKAGE = "rack_overflow.storage"
EXERCISES = "seed_data/exercises.json"
TEMPLATES = "seed_data/templates.json"


def load_exercises(package: str = PACKAGE, name: str = EXERCISES) -> list[dict[str, Any]]:
    """The seed exercises: a list of `{key, name, category, movement_pattern, equipment, location,
    fields: [{quantity, required, increment | discrete_values}], aliases}` (canonical integers;
    `key` is the stable seed identity, D-060). An unreadable or malformed file raises `StorageError`."""
    return _load(package, name)


def load_templates(package: str = PACKAGE, name: str = TEMPLATES) -> list[dict[str, Any]]:
    """The seed templates: a list of `{name, location, slots: [{exercise: key} | {menu: label,
    options: [key, …]}, each with target: {sets, reps_min, reps_max, duration_s, distance_m,
    note}]}` (canonical integers, every target part optional). Unreadable or malformed →
    `StorageError`."""
    return _load(package, name)


def _load(package: str, name: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(resources.files(package).joinpath(name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StorageError(f"cannot read seed data {name}: {error}") from None
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise StorageError(f"seed data {name} is not a list of objects")
    return data
