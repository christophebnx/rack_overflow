"""The L3 "Done when" of docs/roadmap.md as end-to-end scenarios through the public entry points
(`rack migrate` through `cli.main`, the pages through the TestClient), and the upgrade of a
populated L2 database (revision 0002, seed version 1, no seed keys) to 0003 (D-058, D-060)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.cli import main
from rack_overflow.config import Settings
from rack_overflow.services import seed, templates
from rack_overflow.storage import app_settings, db, migrate
from rack_overflow.storage import schema as s

USER = 1
HTMX = {"hx-request": "true"}
PAGE = {"accept": "text/html"}
SEED_NAMES = [
    "Salle A — Squat & poussée horizontale",
    "Salle B — Charnière & poussée verticale",
    "Maison — Kettlebell, barre EZ, haltères",
    "Cardio — Course 30 min",
]
REAL_UPGRADE = migrate.command.upgrade


def _stop_at(target: str) -> Any:
    def upgrade(config: Config, revision: str, **kwargs: Any) -> None:
        del revision
        REAL_UPGRADE(config, target, **kwargs)

    return upgrade


def _seed_items() -> list[dict[str, Any]]:
    text = resources.files("rack_overflow.storage").joinpath("seed_data/exercises.json").read_text("utf-8")
    return json.loads(text)


def l2_database(settings: Settings, monkeypatch: pytest.MonkeyPatch, renames: dict[str, str]) -> None:
    """A database as L2 left it: revision 0002, the 41 seed exercises (some renamed or replaced by
    the user's spelling), `seed.version = 1`, no template."""
    engine = db.create_engine(settings.database_path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", _stop_at("0002"))
            migrate.upgrade_to_head(engine)
        with engine.begin() as connection:
            for item in _seed_items():
                connection.execute(
                    sa.text(
                        "INSERT INTO exercise (user_id, name, category, movement_pattern, equipment,"
                        " location) VALUES (1, :name, :category, :pattern, :equipment, :location)"
                    ),
                    {
                        "name": renames.get(item["name"], item["name"]),
                        "category": item["category"],
                        "pattern": item.get("movement_pattern"),
                        "equipment": item.get("equipment"),
                        "location": item["location"],
                    },
                )
            connection.execute(
                sa.text(
                    "INSERT INTO exercise (user_id, name, category, location) "
                    "VALUES (1, 'Squat bulgare maison', 'strength', 'home')"
                )
            )
            connection.execute(
                sa.text("UPDATE exercise SET archived_at = '2026-10-01T00:00:00Z' WHERE name = 'Dips'")
            )
            connection.execute(
                sa.text("INSERT INTO app_setting (user_id, key, value) VALUES (1, 'seed.version', '1')")
            )
        assert migrate.current_revision(engine) == "0002"
    finally:
        engine.dispose()


def _keys(engine: Engine) -> dict[str, str | None]:
    with engine.begin() as connection:
        return {row.name: row.seed_key for row in connection.execute(sa.select(s.exercise))}


def _menu(engine: Engine, template_name: str, label: str) -> list[tuple[str, bool]]:
    found = next(t for t in templates.list_templates(engine, USER) if t.draft.name == template_name)
    slot = next(x for x in templates.get_detail(engine, USER, found.id).slots if x.label == label)
    return [(o.exercise.name, o.exercise.archived) for o in slot.options]


def test_upgrade_of_a_populated_l2_database_through_rack_migrate(
    settings: Settings,
    settings_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # « Rameur » renamed before keys existed (its key cannot be found), « Planche » created by the
    # user before the L2 seed (lower case spelling, so the seed skipped its own)
    l2_database(settings, monkeypatch, {"Rameur": "Rameur Concept2", "Planche": "planche"})
    assert main(["migrate", "--config", str(settings_file)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("backup ")  # snapshot before the pending revision
    assert "at revision 0004" in out
    assert out.endswith("seeded 4 templates\n") and "exercises" not in out.splitlines()[-1]
    engine = db.create_engine(settings.database_path)
    try:
        keys = _keys(engine)
        assert len(keys) == 42  # nothing inserted by step 1 again
        assert keys["planche"] == "planche" and keys["Rameur Concept2"] is None
        assert keys["Squat bulgare maison"] is None
        assigned = [key for key in keys.values() if key is not None]
        assert len(assigned) == len(set(assigned)) == 40
        assert [t.draft.name for t in templates.list_templates(engine, USER)] == SEED_NAMES
        assert _menu(engine, SEED_NAMES[3], "Cardio") == [
            ("Course extérieure", False),
            ("Tapis de course", False),
            ("Vélo", False),
        ]
        assert ("planche", False) in _menu(engine, SEED_NAMES[0], "Gainage")
        assert ("planche", False) in _menu(engine, SEED_NAMES[2], "Gainage")
        assert ("Dips", True) in _menu(engine, SEED_NAMES[1], "Triceps")  # archived, kept, flagged
        with engine.begin() as connection:
            assert app_settings.get(connection, USER, "seed.version") == "2"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            counts = [
                connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
                for table in (s.template, s.template_slot, s.template_slot_option)
            ]
    finally:
        engine.dispose()

    assert main(["migrate", "--config", str(settings_file)]) == 0
    again = capsys.readouterr().out
    assert "seeded" not in again and "backup" not in again
    engine = db.create_engine(settings.database_path)
    try:
        with engine.begin() as connection:
            assert [
                connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
                for table in (s.template, s.template_slot, s.template_slot_option)
            ] == counts
        assert len(_keys(engine)) == 42
    finally:
        engine.dispose()


def test_a_renamed_seed_exercise_replaced_by_a_user_one_gets_the_key_by_name(
    settings: Settings, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L2 user renamed « Planche » then created a new « Planche »: the name match (the only one,
    D-060) gives the key to the exercise now called « Planche »."""
    l2_database(settings, monkeypatch, {"Planche": "Planche ventrale"})
    engine = db.create_engine(settings.database_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO exercise (user_id, name, category, location)"
                    " VALUES (1, 'Planche', 'bodyweight', 'home')"
                )
            )
    finally:
        engine.dispose()
    assert main(["migrate", "--config", str(settings_file)]) == 0
    engine = db.create_engine(settings.database_path)
    try:
        keys = _keys(engine)
        assert keys["Planche"] == "planche" and keys["Planche ventrale"] is None
        assert ("Planche", False) in _menu(engine, SEED_NAMES[0], "Gainage")
        assert ("Planche ventrale", False) not in _menu(engine, SEED_NAMES[0], "Gainage")
    finally:
        engine.dispose()


def test_seeding_twice_from_empty_creates_no_duplicate(
    settings_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for _ in range(3):
        assert main(["migrate", "--config", str(settings_file)]) == 0
    out = capsys.readouterr().out
    assert out.count("seeded 4 templates") == 1 and out.count("seeded 41 exercises") == 1
    engine = db.create_engine(settings_file.parent / "data" / "rack.sqlite")
    try:
        assert [
            t.draft.name for t in templates.list_templates(engine, USER, include_archived=True)
        ] == SEED_NAMES
        with engine.begin() as connection:
            names = connection.execute(sa.select(s.exercise.c.name)).scalars().all()
        assert len(names) == len(set(names)) == 41
    finally:
        engine.dispose()


def test_roadmap_scenario_on_a_migrated_database(client: TestClient, migrated_engine: Engine) -> None:
    """Create « Salle 1 » with a « Tirage » menu offering three exercises, reorder slots, archive."""
    seed.seed_catalog(migrated_engine, USER)
    names = {e.name: e.id for e in _exercises(migrated_engine)}
    created = client.post("/seances-types", json={"name": "Salle 1", "location": "gym"}, headers=HTMX)
    assert created.status_code == 204
    path = created.headers["hx-redirect"]
    salle = int(path.rsplit("/", 1)[1])
    squat = client.post(
        f"{path}/blocs",
        json={"kind": "exercise", "exercise_id": str(names["Squat au rack (barre)"])},
        headers=HTMX,
    )
    assert squat.status_code == 200
    menu_body = {"kind": "menu", "label": "Tirage", "exercise_id": str(names["Rowing barre au rack"])}
    assert client.post(f"{path}/blocs", json=menu_body, headers=HTMX).status_code == 200
    detail = templates.get_detail(migrated_engine, USER, salle)
    menu = detail.slots[1].id
    for name in ("Rowing assis machine", "Tirage horizontal poulie"):
        added = client.post(
            f"{path}/blocs/{menu}/options", json={"exercise_id": str(names[name])}, headers=HTMX
        )
        assert added.status_code == 200
    moved = client.post(f"{path}/blocs/{menu}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert moved.status_code == 200
    detail = templates.get_detail(migrated_engine, USER, salle)
    assert [x.name for x in detail.slots] == ["Tirage", "Squat au rack (barre)"]
    assert [o.exercise.name for o in detail.slots[0].options] == [
        "Rowing barre au rack",
        "Rowing assis machine",
        "Tirage horizontal poulie",
    ]
    assert client.post(f"{path}/archive", json={}, headers=HTMX).status_code == 200
    listed = client.get("/seances-types", headers=PAGE).text
    assert f'href="{path}"' not in listed
    assert f'href="{path}"' in client.get("/seances-types?archivees=1", headers=PAGE).text
    assert client.get(path, headers=PAGE).status_code == 200  # still viewable
    with migrated_engine.begin() as connection:
        archived = connection.execute(
            sa.select(s.template.c.archived_at).where(s.template.c.id == salle)
        ).scalar_one()
    assert archived is not None and datetime.fromisoformat(archived.replace("Z", "+00:00")).tzinfo == UTC


def _exercises(engine: Engine) -> list[Any]:
    with engine.begin() as connection:
        return list(connection.execute(sa.select(s.exercise.c.id, s.exercise.c.name)))


def test_invalid_seed_templates_fail_migrate_after_the_schema_upgrade(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Design note, error handling: exit 1, schema at the head, the seed transaction rolled back."""
    too_long = {"name": "Longue", "location": "gym", "slots": [{"exercise": "planche"}] * 31}
    monkeypatch.setattr(seed.seed, "load_templates", lambda: [too_long])
    assert main(["migrate", "--config", str(settings_file)]) == 1
    capsys.readouterr()
    engine = db.create_engine(settings_file.parent / "data" / "rack.sqlite")
    try:
        assert migrate.current_revision(engine) == "0004"
        with engine.begin() as connection:
            assert app_settings.get(connection, USER, "seed.version") is None
            assert connection.execute(sa.select(sa.func.count()).select_from(s.exercise)).scalar_one() == 0
            assert connection.execute(sa.select(sa.func.count()).select_from(s.template)).scalar_one() == 0
    finally:
        engine.dispose()
    monkeypatch.undo()
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out.endswith("seeded 41 exercises\nseeded 4 templates\n")


def test_seed_templates_with_the_same_folded_name_are_created_once(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = {"name": "Salle A", "location": "gym", "slots": [{"exercise": "planche"}]}
    second = {**first, "name": "SALLÉ a", "location": "home"}
    monkeypatch.setattr(seed.seed, "load_templates", lambda: [first, second])
    assert seed.seed_catalog(migrated_engine, USER) == seed.SeedReport(exercises=41, templates=1)
    assert [(t.draft.name, t.slot_count) for t in templates.list_templates(migrated_engine, USER)] == [
        ("Salle A", 1)
    ]
