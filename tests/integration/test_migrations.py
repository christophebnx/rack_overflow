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


def upgrade_to(target: str) -> Any:
    """A replacement of `command.upgrade` that stops at `target` instead of the head."""

    def upgrade(config: Config, revision: str, **kwargs: Any) -> None:
        del revision
        REAL_UPGRADE(config, target, **kwargs)

    return upgrade


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
    engine = db.create_engine(settings.database_path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0001"))
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
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0002"))
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


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns(table)}


def _unique_indexes(engine: Engine, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(engine).get_indexes(table) if index["unique"]}


def test_0003_upgrades_a_0002_database_with_exercises(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = db.create_engine(settings.database_path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0002"))
            migrate.upgrade_to_head(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO exercise (user_id, name, category, location) VALUES "
                "(1, 'Squat', 'strength', 'gym'), (1, 'Dips', 'bodyweight', 'gym')"
            )
            connection.exec_driver_sql(
                "INSERT INTO exercise_field (exercise_id, core_quantity, position, required) "
                "VALUES (1, 'reps', 0, 1)"
            )
        migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) == "0004"
        assert "deleted_at" in _columns(engine, "template_slot")
        assert "seed_key" in _columns(engine, "exercise")
        assert "uq_exercise_user_id_seed_key" in _unique_indexes(engine, "exercise")
        assert "uq_template_user_id_name" in _unique_indexes(engine, "template")
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            rows = connection.execute(sa.select(schema.exercise.c.name, schema.exercise.c.seed_key))
            assert rows.all() == [("Squat", None), ("Dips", None)]
            connection.execute(
                sa.update(schema.exercise).where(schema.exercise.c.id == 1).values(seed_key="squat")
            )
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(
                    sa.update(schema.exercise).where(schema.exercise.c.id == 2).values(seed_key="squat")
                )
    finally:
        engine.dispose()


def test_template_names_are_unique_per_user(migrated_engine: Engine) -> None:
    row = {"user_id": 1, "name": "Salle A", "location": "gym", "position": 0}
    with migrated_engine.begin() as connection:
        connection.execute(sa.insert(schema.template).values(row))
        connection.execute(sa.insert(schema.template).values({**row, "user_id": 2}))
    with pytest.raises(sa.exc.IntegrityError), migrated_engine.begin() as connection:
        connection.execute(sa.insert(schema.template).values({**row, "position": 1}))


def test_0003_downgrades_to_0002(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        driver = connection.connection.driver_connection
        driver.execute("PRAGMA foreign_keys = OFF")
        try:
            with connection.begin():
                migrate.command.downgrade(migrate._config(connection), "0002")
        finally:
            driver.execute("PRAGMA foreign_keys = ON")
    assert migrate.current_revision(migrated_engine) == "0002"
    assert "deleted_at" not in _columns(migrated_engine, "template_slot")
    assert "seed_key" not in _columns(migrated_engine, "exercise")
    assert "uq_template_user_id_name" not in _unique_indexes(migrated_engine, "template")
    migrate.upgrade_to_head(migrated_engine)
    assert migrate.current_revision(migrated_engine) == "0004"


def _indexes(engine: Engine, table: str) -> dict[str, list[str]]:
    return {index["name"]: index["column_names"] for index in sa.inspect(engine).get_indexes(table)}


def test_0004_indexes_session_rows_by_exercise(migrated_engine: Engine) -> None:
    assert _indexes(migrated_engine, "session_exercise")["ix_session_exercise_exercise_id"] == ["exercise_id"]


def test_0004_upgrades_a_seeded_0003_database_with_sessions(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = db.create_engine(settings.database_path)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0003"))
            migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) == "0003"
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO exercise (user_id, name, category, location) "
                "VALUES (1, 'Squat', 'strength', 'gym')"
            )
            connection.exec_driver_sql(
                "INSERT INTO session (user_id, local_date, time_zone, started_at, location, status) "
                "VALUES (1, '2026-11-02', 'Europe/Brussels', '2026-11-02T17:00:00Z', 'gym', 'open')"
            )
            connection.exec_driver_sql(
                "INSERT INTO session_exercise (session_id, exercise_id, position) VALUES (1, 1, 0)"
            )
            connection.exec_driver_sql(
                "INSERT INTO set_entry (session_exercise_id, position, type, reps, weight_g) "
                "VALUES (1, 0, 'work', 8, 60000)"
            )
        migrate.upgrade_to_head(engine)
        assert migrate.current_revision(engine) == "0004"
        assert "ix_session_exercise_exercise_id" in _indexes(engine, "session_exercise")
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute(sa.select(schema.set_entry.c.weight_g)).scalars().all() == [60000]
    finally:
        engine.dispose()


def test_0004_downgrades_to_0003(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection, connection.begin():
        migrate.command.downgrade(migrate._config(connection), "0003")
    assert migrate.current_revision(migrated_engine) == "0003"
    assert "ix_session_exercise_exercise_id" not in _indexes(migrated_engine, "session_exercise")
    migrate.upgrade_to_head(migrated_engine)
    assert "ix_session_exercise_exercise_id" in _indexes(migrated_engine, "session_exercise")
