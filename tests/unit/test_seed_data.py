"""The packaged seed data (D-057): the 41 exercises of brief section 6.1, valid for the domain."""

from __future__ import annotations

import re

import pytest

from rack_overflow.domain import catalog, templates
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


# --- seed keys and templates (D-060)

TEMPLATES = seed.load_templates()
KEY = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
TARGET_PARTS = ("sets", "reps_min", "reps_max", "duration_s", "distance_m", "note")


def test_seed_keys_are_unique_ascii_slugs() -> None:
    keys = [item["key"] for item in ITEMS]
    assert len(keys) == len(set(keys)) == 41
    assert all(KEY.fullmatch(key) for key in keys)


def _summary(slot: dict) -> tuple:
    names = {item["key"]: item["name"] for item in ITEMS}
    target = slot["target"]
    parts = (target.get("sets"), target.get("reps_min"), target.get("reps_max"), target.get("duration_s"))
    if "menu" in slot:
        return (slot["menu"], tuple(names[key] for key in slot["options"]), *parts, target.get("note"))
    return (names[slot["exercise"]], *parts, target.get("note"))


def test_seed_templates_are_the_four_of_the_brief() -> None:
    assert [(t["name"], t["location"]) for t in TEMPLATES] == [
        ("Salle A — Squat & poussée horizontale", "gym"),
        ("Salle B — Charnière & poussée verticale", "gym"),
        ("Maison — Kettlebell, barre EZ, haltères", "home"),
        ("Cardio — Course 30 min", "both"),
    ]
    salle_a, salle_b, maison, cardio = ([_summary(slot) for slot in t["slots"]] for t in TEMPLATES)
    assert salle_a == [
        ("Squat au rack (barre)", 4, 6, 8, None, None),
        ("Développé couché (barre)", 4, 6, 8, None, None),
        (
            "Tirage horizontal",
            ("Rowing barre au rack", "Rowing assis machine", "Tirage horizontal poulie"),
            *(3, 8, 10, None, None),
        ),
        (
            "Jambes unilatéral",
            ("Fentes haltères", "Split squat bulgare", "Presse à cuisses"),
            *(3, 10, 10, None, None),
        ),
        ("Curl barre EZ", 3, 10, 12, None, None),
        (
            "Gainage",
            ("Planche", "Crunch poulie haute", "Relevé de jambes suspendu"),
            *(3, 12, 12, 30, None),
        ),
    ]
    assert salle_b == [
        ("Soulevé de terre roumain (RDL)", 4, 8, 8, None, None),
        ("Développé militaire haltères", 4, 8, 8, None, None),
        (
            "Tirage vertical",
            ("Tirage vertical poulie", "Tractions assistées machine", "Tractions"),
            *(3, 8, 10, None, None),
        ),
        ("Développé incliné à la Smith", 3, 8, 10, None, None),
        (
            "Ischios / fessiers",
            ("Leg curl allongé", "Hip thrust à la Smith", "Extension lombaire"),
            *(3, 10, 12, None, None),
        ),
        ("Triceps", ("Extension triceps poulie", "Barre au front EZ", "Dips"), *(3, 10, 12, None, None)),
    ]
    assert maison == [
        ("Kettlebell swing", 5, 15, 15, None, None),
        ("Goblet squat kettlebell", 4, 10, 10, None, None),
        (
            "Poussée",
            ("Pompes", "Développé haltères au sol", "Développé militaire kettlebell"),
            *(3, 10, 10, None, None),
        ),
        ("Rowing haltère un bras", 3, 10, 10, None, "par côté"),
        ("Bras", ("Curl barre EZ", "Curl marteau haltères", "Barre au front EZ"), *(3, 12, 12, None, None)),
        ("Gainage", ("Planche", "Turkish get-up kettlebell"), *(3, 3, 3, 30, "par côté")),
    ]
    assert cardio == [
        (
            "Cardio",
            ("Course extérieure", "Tapis de course", "Vélo", "Rameur"),
            *(1, None, None, 1800, None),
        )
    ]


@pytest.mark.parametrize("item", TEMPLATES, ids=lambda item: item["name"])
def test_seed_template_validates_through_the_domain(item: dict) -> None:
    templates.template_draft(name=item["name"], location=item["location"])
    for slot in item["slots"]:
        target = slot["target"]
        templates.check_target(templates.Target(**{part: target.get(part) for part in TARGET_PARTS}))
        if "menu" in slot:
            assert templates.menu_label(slot["menu"]) == slot["menu"]
            assert len(set(slot["options"])) == len(slot["options"]) <= templates.MAX_OPTIONS


def test_unreadable_templates_raise_storage_error() -> None:
    with pytest.raises(StorageError):
        seed.load_templates(name="seed_data/missing.json")
