"""The catalog seed in `rack migrate` (D-057): content, idempotence, user edits respected."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.cli import main
from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.search import Candidate, rank
from rack_overflow.services import exercises, seed
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.storage import app_settings, db
from rack_overflow.storage import schema as s
from rack_overflow.storage.errors import StorageError

USER = 1
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def counts(engine: Engine) -> tuple[int, int, int]:
    with engine.begin() as connection:
        return tuple(  # type: ignore[return-value]
            connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in (s.exercise, s.exercise_field, s.exercise_alias)
        )


def by_name(engine: Engine, name: str) -> exercises.ExerciseDetail:
    found = [e for e in exercises.list_exercises(engine, USER, include_archived=True) if e.draft.name == name]
    assert len(found) == 1
    return exercises.get_detail(engine, USER, found[0].id)


def test_seed_creates_the_catalog_once(migrated_engine: Engine) -> None:
    assert seed.seed_catalog(migrated_engine, USER) == 41
    first = counts(migrated_engine)
    assert first[0] == 41
    with migrated_engine.begin() as connection:
        assert app_settings.get(connection, USER, seed.VERSION_KEY) == "1"
    assert seed.seed_catalog(migrated_engine, USER) == 0
    assert counts(migrated_engine) == first


def test_seeded_content(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    swing = by_name(migrated_engine, "Kettlebell swing")
    assert swing.draft.location == "home" and swing.draft.category == "kettlebell"
    assert [(f.core_quantity, f.params.discrete_values) for f in swing.fields] == [
        ("reps", None),
        ("weight", (16000, 20000, 24000)),
    ]
    assert [a.alias for a in swing.aliases] == ["Swing", "KB swing"]
    bike = by_name(migrated_engine, "Vélo")
    assert [(f.core_quantity, f.params.required, f.params.increment) for f in bike.fields] == [
        ("duration", True, 60),
        ("distance", False, 100),
    ]
    pull_ups = by_name(migrated_engine, "Tractions")
    assert [(f.core_quantity, f.params.required) for f in pull_ups.fields] == [
        ("reps", True),
        ("weight", False),
    ]
    assert by_name(migrated_engine, "Planche").fields[0].params.increment == 15


@pytest.mark.parametrize("query", ["DC", "bench", "developpe"])
def test_roadmap_queries_on_the_seed(migrated_engine: Engine, query: str) -> None:
    seed.seed_catalog(migrated_engine, USER)
    assert (
        exercises.search_exercises(migrated_engine, USER, query)[0].draft.name == "Développé couché (barre)"
    )


def test_existing_names_are_kept_and_renamed_seeds_not_recreated(migrated_engine: Engine) -> None:
    mine = exercises.create(migrated_engine, USER, ExerciseForm("planche", "bodyweight", "home"))
    assert seed.seed_catalog(migrated_engine, USER) == 40
    planks = [e for e in exercises.list_exercises(migrated_engine, USER) if e.draft.name.lower() == "planche"]
    assert [p.id for p in planks] == [mine]
    bike = by_name(migrated_engine, "Vélo")
    exercises.update(migrated_engine, USER, bike.id, ExerciseForm("Vélo appartement", "cardio", "home"))
    rower = by_name(migrated_engine, "Rameur")
    exercises.set_archived(migrated_engine, USER, rower.id, NOW)
    assert seed.seed_catalog(migrated_engine, USER) == 0
    assert not [e for e in exercises.list_exercises(migrated_engine, USER) if e.draft.name == "Vélo"]


def test_seed_steps_above_the_version_run_in_one_transaction(migrated_engine: Engine) -> None:
    ran: list[int] = []

    def step(number: int) -> seed.Step:
        def run(connection: sa.Connection, user_id: int) -> int:
            del connection, user_id
            ran.append(number)
            return number

        return run

    with migrated_engine.begin() as connection:
        app_settings.put(connection, USER, seed.VERSION_KEY, "1")
    assert seed.seed_catalog(migrated_engine, USER, {1: step(1), 2: step(2), 3: step(3)}) == 5
    assert ran == [2, 3]

    def failing(connection: sa.Connection, user_id: int) -> int:
        app_settings.put(connection, user_id, "other", "x")
        raise StorageError("boom")

    with pytest.raises(StorageError):
        seed.seed_catalog(migrated_engine, USER, {4: failing})
    with migrated_engine.begin() as connection:
        assert app_settings.get(connection, USER, seed.VERSION_KEY) == "3"
        assert app_settings.get(connection, USER, "other") is None


def test_invalid_seed_data_rolls_back(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    good = {
        "name": "A",
        "category": "strength",
        "location": "gym",
        "fields": [{"quantity": "reps", "required": True, "increment": 1}],
    }
    bad_field = {**good, "name": "B", "fields": [{"quantity": "reps", "required": True, "increment": 0}]}
    monkeypatch.setattr(seed.seed, "load_exercises", lambda: [good, bad_field])
    with pytest.raises(CatalogError):
        seed.seed_catalog(migrated_engine, USER)
    monkeypatch.setattr(seed.seed, "load_exercises", lambda: [good, {"name": "C"}])
    with pytest.raises(StorageError):
        seed.seed_catalog(migrated_engine, USER)
    assert counts(migrated_engine) == (0, 0, 0)


def test_rack_migrate_seeds_once(settings_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate", "--config", str(settings_file)]) == 0
    first = capsys.readouterr()
    assert first.out.endswith("\nseeded 41 exercises\n") and first.err == ""
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert "seeded" not in capsys.readouterr().out
    engine = db.create_engine(settings_file.parent / "data" / "rack.sqlite")
    try:
        assert counts(engine)[0] == 41
    finally:
        engine.dispose()


def test_rank_on_seed_data_alone() -> None:
    from rack_overflow.storage.seed import load_exercises

    candidates = [
        Candidate(index, item["name"], tuple(item["aliases"])) for index, item in enumerate(load_exercises())
    ]
    names = {c.id: c.name for c in candidates}
    for query in ("DC", "bench", "developpe"):
        assert names[rank(query, candidates)[0]] == "Développé couché (barre)"
