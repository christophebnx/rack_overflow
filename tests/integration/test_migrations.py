"""Edge cases of `storage.migrate` and `storage.db` on real temporary databases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.storage import db, migrate, schema
from rack_overflow.storage.errors import MigrationError

REAL_UPGRADE = migrate.command.upgrade


def _tables(engine: Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def test_upgrade_from_empty_creates_every_table(settings: Settings) -> None:
    engine = db.create_engine(settings.database_path)
    try:
        migrate.upgrade_to_head(engine)
        assert _tables(engine) == set(schema.metadata.tables) | {"alembic_version"}
    finally:
        engine.dispose()


def test_second_upgrade_keeps_the_data(migrated_engine: Engine) -> None:
    row = {"user_id": 1, "name": "Squat", "category": "strength", "location": "gym"}
    with migrated_engine.begin() as connection:
        connection.execute(sa.insert(schema.exercise).values(row))
    migrate.upgrade_to_head(migrated_engine)
    with migrated_engine.connect() as connection:
        assert connection.execute(sa.select(schema.exercise.c.name)).scalars().all() == ["Squat"]


def test_foreign_keys_are_back_on_after_an_upgrade(settings: Settings) -> None:
    engine = db.create_engine(settings.database_path)
    try:
        migrate.upgrade_to_head(engine)
        with engine.connect() as connection:  # the pooled connection used by the upgrade
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_upgrade_breaking_a_foreign_key_is_rolled_back(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def upgrade_leaving_an_orphan(config: Config, revision: str, **kwargs: Any) -> None:
        REAL_UPGRADE(config, revision, **kwargs)
        connection: sa.Connection = config.attributes["connection"]
        connection.execute(
            sa.insert(schema.exercise_alias).values(exercise_id=999, alias="x", alias_normalised="x")
        )

    monkeypatch.setattr(migrate.command, "upgrade", upgrade_leaving_an_orphan)
    engine = db.create_engine(settings.database_path)
    try:
        with pytest.raises(MigrationError, match="1 foreign key"):
            migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) is None
        assert _tables(engine) == set()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_failing_upgrade_leaves_the_database_at_its_revision(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_upgrade(config: Config, revision: str, **kwargs: Any) -> None:
        REAL_UPGRADE(config, revision, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(migrate.command, "upgrade", failing_upgrade)
    engine = db.create_engine(settings.database_path)
    try:
        with pytest.raises(RuntimeError):
            migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) is None
        assert _tables(engine) == set()
    finally:
        engine.dispose()


def test_no_migration_shipped_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts = tmp_path / "migrations"
    (scripts / "versions").mkdir(parents=True)
    (scripts / "env.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(migrate, "MIGRATIONS", scripts)
    with pytest.raises(MigrationError, match="no migration found"):
        migrate.head_revision()


def test_unknown_synchronous_mode_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "SYNCHRONOUS", "FAST")
    engine = db.create_engine(tmp_path / "x.sqlite")
    try:
        with pytest.raises(ValueError, match="invalid synchronous mode"):
            engine.connect()
    finally:
        engine.dispose()


@pytest.mark.real_fsync(reason="checks the production synchronous pragma")
def test_synchronous_full_outside_the_test_suite(tmp_path: Path) -> None:
    engine = db.create_engine(tmp_path / "x.sqlite")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2  # FULL
    finally:
        engine.dispose()


def test_transactions_take_the_write_lock_up_front(migrated_engine: Engine, settings: Settings) -> None:
    other = db.create_engine(settings.database_path)
    try:
        with migrated_engine.begin(), other.connect() as connection:
            driver = connection.connection.driver_connection  # no SQLAlchemy autobegin
            driver.execute("PRAGMA busy_timeout = 0")
            with pytest.raises(sa.exc.OperationalError, match="locked"):
                connection.begin()
            assert driver.execute("SELECT count(*) FROM exercise").fetchone() == (0,)  # WAL: reads still pass
    finally:
        other.dispose()


def test_0002_keeps_variables_and_their_links(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    def upgrade_to_0001(config: Config, revision: str, **kwargs: Any) -> None:
        REAL_UPGRADE(config, "0001", **kwargs)

    engine = db.create_engine(settings.database_path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to_0001)
            migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) == "0001"
        variable = {"user_id": 1, "code": "band", "label": "Band", "type": "decimal", "scope": "setting"}
        exercise = {"user_id": 1, "name": "Squat", "category": "strength", "location": "gym"}
        with engine.begin() as connection:
            connection.execute(sa.insert(schema.variable).values(**variable, decimal_scale=1))
            connection.execute(sa.insert(schema.exercise).values(exercise))
            connection.execute(
                sa.insert(schema.exercise_field).values(exercise_id=1, variable_id=1, position=1)
            )
        migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) == "0002"
        with engine.connect() as connection:
            assert connection.execute(sa.select(schema.variable.c.decimal_scale)).scalars().all() == [1]
            assert (
                connection.execute(sa.select(sa.func.count()).select_from(schema.exercise_field)).scalar()
                == 1
            )
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.insert(schema.variable).values({**variable, "code": "other"}))
    finally:
        engine.dispose()


def test_unknown_revision_is_a_migration_error(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '9999'")
    assert not migrate.is_up_to_date(migrated_engine)
    with pytest.raises(MigrationError, match="Can't locate revision"):
        migrate.upgrade_to_head(migrated_engine)


def test_non_database_file_is_a_migration_error(settings: Settings) -> None:
    settings.database_path.write_bytes(b"this is not a database" * 300)
    engine = db.create_engine(settings.database_path)
    try:
        with pytest.raises(MigrationError, match="cannot be read"):
            migrate.current_revision(engine)
        with pytest.raises(MigrationError, match="cannot be read"):
            migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
