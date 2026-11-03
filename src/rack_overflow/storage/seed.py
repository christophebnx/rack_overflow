"""The packaged seed data (D-057): French exercise data shipped inside the package, read through
`importlib.resources` so it works from a source tree and from an installed wheel."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from rack_overflow.storage.errors import StorageError

PACKAGE = "rack_overflow.storage"
EXERCISES = "seed_data/exercises.json"


def load_exercises(package: str = PACKAGE, name: str = EXERCISES) -> list[dict[str, Any]]:
    """The seed exercises: a list of `{name, category, movement_pattern, equipment, location,
    fields: [{quantity, required, increment | discrete_values}], aliases}` (canonical integers).
    An unreadable or malformed file raises `StorageError`."""
    try:
        data = json.loads(resources.files(package).joinpath(name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StorageError(f"cannot read seed data {name}: {error}") from None
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise StorageError(f"seed data {name} is not a list of objects")
    return data
