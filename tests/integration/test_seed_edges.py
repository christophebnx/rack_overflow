"""Seed idempotence across repeated `rack migrate` and version bumps (D-057)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.cli import main
from rack_overflow.services import exercises, seed
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.storage import app_settings, db
from rack_overflow.storage import schema as s
from rack_overflow.storage.errors import StorageError

USER = 1


def counts(engine: Engine) -> tuple[int, int, int]:
    with engine.begin() as connection:
        return tuple(  # type: ignore[return-value]
            connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in (s.exercise, s.exercise_field, s.exercise_alias)
        )


def stored_version(engine: Engine) -> str | None:
    with engine.begin() as connection:
        return app_settings.get(connection, USER, seed.VERSION_KEY)


def set_version(engine: Engine, value: str) -> None:
    with engine.begin() as connection:
        app_settings.put(connection, USER, seed.VERSION_KEY, value)


def test_three_migrates_seed_once(settings_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for _ in range(3):
        assert main(["migrate", "--config", str(settings_file)]) == 0
    out = capsys.readouterr().out
    assert out.count("seeded 41 exercises") == out.count("seeded 4 templates") == 1
    assert out.count("seeded") == 2
    engine = db.create_engine(settings_file.parent / "data" / "rack.sqlite")
    try:
        assert counts(engine)[0] == 41
        assert stored_version(engine) == "2"
        with engine.begin() as connection:
            rows = connection.execute(sa.select(sa.func.count()).select_from(s.app_setting)).scalar_one()
        assert rows == 1
    finally:
        engine.dispose()


def test_a_new_step_runs_once_and_only_it(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    before = counts(migrated_engine)
    calls: list[int] = []

    def step_three(connection: sa.Connection, user_id: int) -> seed.SeedReport:
        calls.append(user_id)
        return seed.SeedReport()

    steps = {**seed.STEPS, 3: step_three}
    assert seed.seed_catalog(migrated_engine, USER, steps) == seed.SeedReport()
    assert seed.seed_catalog(migrated_engine, USER, steps) == seed.SeedReport()
    assert calls == [USER]
    assert stored_version(migrated_engine) == "3"
    assert counts(migrated_engine) == before


def test_a_failing_new_step_keeps_the_old_version(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)

    def broken(connection: sa.Connection, user_id: int) -> seed.SeedReport:
        exercises_table_insert(connection)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        seed.seed_catalog(migrated_engine, USER, {**seed.STEPS, 3: broken})
    assert stored_version(migrated_engine) == "2"
    assert counts(migrated_engine)[0] == 41


def exercises_table_insert(connection: sa.Connection) -> None:
    connection.execute(
        sa.insert(s.exercise).values(user_id=USER, name="Partiel", category="strength", location="gym")
    )


def test_a_version_above_every_step_seeds_nothing(migrated_engine: Engine) -> None:
    set_version(migrated_engine, "9")
    assert seed.seed_catalog(migrated_engine, USER) == seed.SeedReport()
    assert counts(migrated_engine) == (0, 0, 0)
    assert stored_version(migrated_engine) == "9"


@pytest.mark.parametrize("garbage", ["", "abc", "-1", "1.0"])
def test_an_unreadable_version_is_refused_and_changes_nothing(migrated_engine: Engine, garbage: str) -> None:
    seed.seed_catalog(migrated_engine, USER)
    before = counts(migrated_engine)
    set_version(migrated_engine, garbage)
    with pytest.raises(StorageError, match=r"seed\.version"):
        seed.seed_catalog(migrated_engine, USER)
    assert counts(migrated_engine) == before
    assert stored_version(migrated_engine) == garbage


def test_user_changes_survive_a_rerun(migrated_engine: Engine) -> None:
    from datetime import UTC, datetime

    seed.seed_catalog(migrated_engine, USER)
    listed = {e.draft.name: e.id for e in exercises.list_exercises(migrated_engine, USER)}
    swing = listed["Kettlebell swing"]
    plank = listed["Planche"]
    exercises.set_archived(migrated_engine, USER, swing, datetime(2026, 11, 3, tzinfo=UTC))
    exercises.update(migrated_engine, USER, plank, ExerciseForm("Gainage ventral", "bodyweight", "both"))
    set_version(migrated_engine, "0")
    created = seed.seed_catalog(migrated_engine, USER).exercises
    # the archived one is still there (skipped); the renamed one comes back once under its seed name
    names = [e.draft.name for e in exercises.list_exercises(migrated_engine, USER, include_archived=True)]
    assert names.count("Kettlebell swing") == 1
    assert exercises.get_detail(migrated_engine, USER, swing).archived
    assert created == names.count("Planche") == 1


def test_seed_is_per_user(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    assert seed.seed_catalog(migrated_engine, 2) == seed.SeedReport(exercises=41, templates=4)
    assert len(exercises.list_exercises(migrated_engine, 2)) == 41
    assert len(exercises.list_exercises(migrated_engine, USER)) == 41


def test_seeded_patterns_follow_existing_spellings(migrated_engine: Engine) -> None:
    exercises.create(
        migrated_engine,
        USER,
        ExerciseForm("Mon squat", "strength", "gym", movement_pattern="SQUAT", equipment="barre"),
    )
    seed.seed_catalog(migrated_engine, USER)
    patterns = exercises.suggestions(migrated_engine, USER)
    assert "Squat" not in patterns.movement_patterns and "SQUAT" in patterns.movement_patterns
    assert "Barre" not in patterns.equipments and "barre" in patterns.equipments
