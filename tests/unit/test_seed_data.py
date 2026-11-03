"""The packaged seed data (D-057): the 41 exercises of brief section 6.1, valid for the domain."""

from __future__ import annotations

import pytest

from rack_overflow.domain import catalog
from rack_overflow.domain.catalog import FieldParams
from rack_overflow.storage import seed
from rack_overflow.storage.errors import StorageError

BRIEF_NAMES = {
    "Squat au rack (barre)",
    "Développé couché (barre)",
    "Rowing barre au rack",
    "Rowing assis machine",
    "Tirage horizontal poulie",
    "Fentes haltères",
    "Split squat bulgare",
    "Presse à cuisses",
    "Curl barre EZ",
    "Planche",
    "Crunch poulie haute",
    "Relevé de jambes suspendu",
    "Soulevé de terre roumain (RDL)",
    "Développé militaire haltères",
    "Tirage vertical poulie",
    "Tractions assistées machine",
    "Tractions",
    "Développé incliné à la Smith",
    "Leg curl allongé",
    "Hip thrust à la Smith",
    "Extension lombaire",
    "Extension triceps poulie",
    "Barre au front EZ",
    "Dips",
    "Kettlebell swing",
    "Goblet squat kettlebell",
    "Pompes",
    "Développé haltères au sol",
    "Développé militaire kettlebell",
    "Rowing haltère un bras",
    "Curl marteau haltères",
    "Turkish get-up kettlebell",
    "Course extérieure",
    "Tapis de course",
    "Vélo",
    "Rameur",
    "Elliptique",
    "Squat à la Smith",
    "Développé couché haltères",
    "Leg extension",
    "Mollets debout machine",
}
ITEMS = seed.load_exercises()


def test_seed_holds_exactly_the_brief_names() -> None:
    names = [item["name"] for item in ITEMS]
    assert len(names) == 41 == len(set(names))
    assert set(names) == BRIEF_NAMES


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item["name"])
def test_seed_item_validates_through_the_domain(item: dict) -> None:
    draft = catalog.exercise_draft(
        name=item["name"],
        category=item["category"],
        movement_pattern=item["movement_pattern"],
        equipment=item["equipment"],
        location=item["location"],
    )
    assert draft.name == item["name"]
    for field in item["fields"]:
        values = field.get("discrete_values")
        params = FieldParams(field["required"], field.get("increment"), tuple(values) if values else None)
        catalog.check_field(catalog.core_kind(field["quantity"]), params)
    catalog.check_measures(catalog.FieldSource(core_quantity=f["quantity"]) for f in item["fields"])
    seen: list[str] = []
    for alias in item["aliases"]:
        seen.append(catalog.alias_draft(alias, draft.name, seen).alias)


def test_unreadable_or_malformed_seed_raises_storage_error() -> None:
    with pytest.raises(StorageError):
        seed.load_exercises(name="seed_data/missing.json")
    with pytest.raises(StorageError):
        seed.load_exercises(package="rack_overflow.web", name="static/vendor/manifest.json")
