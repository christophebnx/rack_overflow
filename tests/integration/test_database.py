"""Schema and migrations on a real temporary SQLite database."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.domain import vocabulary
from rack_overflow.storage import db, migrate, schema


def test_upgrade_from_empty_then_no_op(settings: Settings) -> None:
    engine = db.create_engine(settings.database_path)
    try:
        assert migrate.current_revision(engine) is None
        assert not migrate.is_up_to_date(engine)
        assert migrate.upgrade_to_head(engine) == migrate.head_revision()
        assert migrate.is_up_to_date(engine)
        assert migrate.upgrade_to_head(engine) == migrate.head_revision()
    finally:
        engine.dispose()


def test_migrated_database_matches_the_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, schema.metadata) == []


def test_pragmas_on_a_fresh_connection(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        pragma = connection.connection.driver_connection.execute
        assert pragma("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert pragma("PRAGMA foreign_keys").fetchone()[0] == 1
        assert pragma("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS


def _exercise(connection: sa.Connection, name: str = "Squat", **values: object) -> int:
    row = {"user_id": 1, "name": name, "category": "strength", "location": "gym", **values}
    return connection.execute(sa.insert(schema.exercise).values(row)).inserted_primary_key[0]


@pytest.mark.parametrize("category", vocabulary.EXERCISE_CATEGORIES)
def test_each_category_is_accepted(migrated_engine: Engine, category: str) -> None:
    with migrated_engine.begin() as connection:
        _exercise(connection, category=category)


def test_unknown_category_is_refused(migrated_engine: Engine) -> None:
    with pytest.raises(sa.exc.IntegrityError), migrated_engine.begin() as connection:
        _exercise(connection, category="yoga")


def test_exercise_field_needs_exactly_one_source(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        exercise_id = _exercise(connection)
        insert = sa.insert(schema.exercise_field)
        connection.execute(insert.values(exercise_id=exercise_id, core_quantity="reps", position=1))
    with pytest.raises(sa.exc.IntegrityError), migrated_engine.begin() as connection:
        connection.execute(insert.values(exercise_id=exercise_id, position=2))


def test_one_open_session_per_user(migrated_engine: Engine) -> None:
    row = {
        "user_id": 1,
        "local_date": "2026-11-03",
        "time_zone": "Europe/Paris",
        "started_at": "2026-11-03T18:04:05Z",
        "location": "gym",
        "status": "open",
    }
    with migrated_engine.begin() as connection:
        connection.execute(sa.insert(schema.session).values(row))
    with pytest.raises(sa.exc.IntegrityError), migrated_engine.begin() as connection:
        connection.execute(sa.insert(schema.session).values(row))


def test_foreign_keys_are_enforced(migrated_engine: Engine) -> None:
    with pytest.raises(sa.exc.IntegrityError), migrated_engine.begin() as connection:
        connection.execute(
            sa.insert(schema.exercise_alias).values(exercise_id=999, alias="x", alias_normalised="x")
        )


def test_head_revision_is_shipped() -> None:
    assert migrate.head_revision() == "0001"
    assert (migrate.MIGRATIONS / "versions" / "0001_initial_schema.py").is_file()


def test_engine_uses_an_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    engine = db.create_engine(Path("relative.sqlite"))
    assert engine.url.database == str(tmp_path / "relative.sqlite")
    engine.dispose()
