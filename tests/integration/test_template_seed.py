"""Seed step 2 (D-060): seed keys, adoption by name, the four templates of brief section 6.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.cli import main
from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.templates import Target
from rack_overflow.services import exercises, seed, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.storage import app_settings, db
from rack_overflow.storage import schema as s
from rack_overflow.storage.errors import StorageError

USER = 1
SALLE_A = "Salle A — Squat & poussée horizontale"
MAISON = "Maison — Kettlebell, barre EZ, haltères"
CARDIO = "Cardio — Course 30 min"


def keys(engine: Engine) -> dict[str, str | None]:
    with engine.begin() as connection:
        rows = connection.execute(sa.select(s.exercise.c.name, s.exercise.c.seed_key))
        return {row.name: row.seed_key for row in rows}


def detail(engine: Engine, name: str) -> templates.TemplateDetail:
    found = [t for t in templates.list_templates(engine, USER, include_archived=True) if t.draft.name == name]
    assert len(found) == 1
    return templates.get_detail(engine, USER, found[0].id)


def menu_options(engine: Engine, template: str, label: str) -> list[tuple[int, str]]:
    slot = next(slot for slot in detail(engine, template).slots if slot.label == label)
    return [(option.exercise.id, option.exercise.name) for option in slot.options]


def seed_as_l2(engine: Engine) -> None:
    """A database seeded by L2: step 1 only, version 1, no seed key."""
    seed.seed_catalog(engine, USER, {1: seed.STEPS[1]})
    with engine.begin() as connection:
        connection.execute(sa.update(s.exercise).values(seed_key=None))


def test_migrate_on_an_empty_database_seeds_keys_and_templates(
    settings_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out.endswith("seeded 41 exercises\nseeded 4 templates\n")
    engine = db.create_engine(settings_file.parent / "data" / "rack.sqlite")
    try:
        assert all(keys(engine).values()) and len(keys(engine)) == 41
        listed = templates.list_templates(engine, USER)
        assert [(t.draft.name, t.slot_count) for t in listed] == [
            (SALLE_A, 6),
            ("Salle B — Charnière & poussée verticale", 6),
            (MAISON, 6),
            (CARDIO, 1),
        ]
        maison = detail(engine, MAISON)
        rowing = maison.slots[3]
        assert (rowing.name, rowing.target) == (
            "Rowing haltère un bras",
            Target(3, 10, 10, None, None, "par côté"),
        )
        assert maison.slots[5].target == Target(3, 3, 3, 30, None, "par côté")
        cardio = detail(engine, CARDIO).slots[0]
        assert [o.exercise.name for o in cardio.options] == [
            "Course extérieure",
            "Tapis de course",
            "Vélo",
            "Rameur",
        ]
        assert cardio.target == Target(sets=1, duration_s=1800)
        assert main(["migrate", "--config", str(settings_file)]) == 0
        assert "seeded" not in capsys.readouterr().out
        assert len(templates.list_templates(engine, USER)) == 4
        with engine.begin() as connection:
            assert app_settings.get(connection, USER, seed.VERSION_KEY) == "2"
    finally:
        engine.dispose()


def test_an_l2_database_gets_its_keys_then_the_templates(migrated_engine: Engine) -> None:
    seed_as_l2(migrated_engine)
    assert not any(keys(migrated_engine).values())
    assert seed.seed_catalog(migrated_engine, USER) == seed.SeedReport(templates=4)
    assert keys(migrated_engine)["Planche"] == "planche"
    assert all(keys(migrated_engine).values())
    assert len(menu_options(migrated_engine, SALLE_A, "Tirage horizontal")) == 3


def test_a_seeded_exercise_renamed_after_keys_is_still_used(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER, {1: seed.STEPS[1]})
    plank = next(e for e in exercises.list_exercises(migrated_engine, USER) if e.draft.name == "Planche")
    exercises.update(migrated_engine, USER, plank.id, ExerciseForm("Gainage ventral", "bodyweight", "both"))
    seed.seed_catalog(migrated_engine, USER)
    assert (plank.id, "Gainage ventral") in menu_options(migrated_engine, SALLE_A, "Gainage")


def test_a_user_exercise_of_the_same_name_is_adopted(migrated_engine: Engine) -> None:
    mine = exercises.create(migrated_engine, USER, ExerciseForm("planche", "bodyweight", "home"))
    assert seed.seed_catalog(migrated_engine, USER) == seed.SeedReport(exercises=40, templates=4)
    assert keys(migrated_engine)["planche"] == "planche"
    assert (mine, "planche") in menu_options(migrated_engine, SALLE_A, "Gainage")
    assert (mine, "planche") in menu_options(migrated_engine, MAISON, "Gainage")


def test_an_existing_template_name_is_kept(migrated_engine: Engine) -> None:
    mine = templates.create(migrated_engine, USER, TemplateForm("cardio — course 30 min", "home"))
    assert seed.seed_catalog(migrated_engine, USER).templates == 3
    names = [t.draft.name for t in templates.list_templates(migrated_engine, USER)]
    assert names[0] == "cardio — course 30 min" and CARDIO not in names
    assert templates.get_detail(migrated_engine, USER, mine).slots == ()


def test_an_archived_template_is_not_seeded_again(migrated_engine: Engine) -> None:
    from datetime import UTC, datetime

    seed.seed_catalog(migrated_engine, USER)
    cardio = detail(migrated_engine, CARDIO)
    templates.set_archived(migrated_engine, USER, cardio.id, datetime(2026, 11, 3, tzinfo=UTC))
    with migrated_engine.begin() as connection:
        app_settings.put(connection, USER, seed.VERSION_KEY, "1")
    assert seed.seed_catalog(migrated_engine, USER) == seed.SeedReport()
    assert len(templates.list_templates(migrated_engine, USER, include_archived=True)) == 4


def test_unresolved_keys_drop_the_option_or_the_slot(migrated_engine: Engine) -> None:
    seed_as_l2(migrated_engine)
    renamed = {"Rowing barre au rack": "Rowing pronation", "Course extérieure": "Footing"}
    renamed |= {name: f"{name} (old)" for name in ("Squat au rack (barre)", "Turkish get-up kettlebell")}
    renamed |= {name: f"{name} (old)" for name in ("Tapis de course", "Vélo", "Rameur")}
    for summary in exercises.list_exercises(migrated_engine, USER):
        if summary.draft.name in renamed:
            form = ExerciseForm(renamed[summary.draft.name], summary.draft.category, summary.draft.location)
            exercises.update(migrated_engine, USER, summary.id, form)
    assert seed.seed_catalog(migrated_engine, USER).templates == 4
    salle_a = detail(migrated_engine, SALLE_A)
    assert [slot.name for slot in salle_a.slots][:2] == ["Développé couché (barre)", "Tirage horizontal"]
    assert [name for _, name in menu_options(migrated_engine, SALLE_A, "Tirage horizontal")] == [
        "Rowing assis machine",
        "Tirage horizontal poulie",
    ]
    assert [name for _, name in menu_options(migrated_engine, MAISON, "Gainage")] == ["Planche"]
    assert detail(migrated_engine, CARDIO).slots == ()


def test_an_archived_exercise_is_kept_in_its_slot(migrated_engine: Engine) -> None:
    from datetime import UTC, datetime

    seed.seed_catalog(migrated_engine, USER, {1: seed.STEPS[1]})
    swing = next(
        e for e in exercises.list_exercises(migrated_engine, USER) if e.draft.name == "Kettlebell swing"
    )
    exercises.set_archived(migrated_engine, USER, swing.id, datetime(2026, 11, 3, tzinfo=UTC))
    seed.seed_catalog(migrated_engine, USER)
    first = detail(migrated_engine, MAISON).slots[0]
    assert first.exercise is not None and first.exercise.archived and first.skipped


def _counts(engine: Engine) -> tuple[int, ...]:
    with engine.begin() as connection:
        return tuple(
            connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in (s.exercise, s.template, s.template_slot, s.template_slot_option)
        )


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"location": "office"}, CatalogError),
        ({"slots": [{"exercise": "planche", "target": {"sets": 0}}]}, CatalogError),
        ({"slots": [{"menu": " ", "options": ["planche"], "target": {}}]}, CatalogError),
        ({"slots": [{"menu": "M", "options": [], "target": {}}]}, StorageError),
        ({"slots": [{"menu": "M", "options": ["planche", "planche"], "target": {}}]}, CatalogError),
        ({"slots": [{"target": {}}]}, StorageError),
        ({"name": None}, CatalogError),
    ],
)
def test_invalid_template_data_rolls_back_the_whole_seed(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, change: dict[str, Any], error: type[Exception]
) -> None:
    good = {"name": "Bonne", "location": "gym", "slots": [{"exercise": "planche", "target": {}}]}
    bad = {**good, "name": "Mauvaise", **change}
    monkeypatch.setattr(seed.seed, "load_templates", lambda: [good, bad])
    with pytest.raises(error):
        seed.seed_catalog(migrated_engine, USER)
    assert _counts(migrated_engine) == (0, 0, 0, 0)
    with migrated_engine.begin() as connection:
        assert app_settings.get(connection, USER, seed.VERSION_KEY) is None
