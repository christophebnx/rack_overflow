"""Snapshots of a real temporary database, through storage, services and the CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import isolation
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.cli import main
from rack_overflow.config import Settings
from rack_overflow.services import backups
from rack_overflow.storage import backup, db, schema
from rack_overflow.storage.errors import BackupError, CorruptDatabaseError

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def _add_exercise(engine: Engine) -> None:
    row = {"user_id": 1, "name": "Squat", "category": "strength", "location": "gym"}
    with engine.begin() as connection:
        connection.execute(sa.insert(schema.exercise).values(row))


def _count_exercises(path: Path) -> int:
    engine = db.create_engine(path)
    try:
        with engine.connect() as connection:
            return connection.execute(sa.select(sa.func.count()).select_from(schema.exercise)).scalar_one()
    finally:
        engine.dispose()


def test_snapshot_holds_the_rows_and_passes_integrity(migrated_engine: Engine, settings: Settings) -> None:
    _add_exercise(migrated_engine)
    path = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    assert path.name == "rack-20261103T180405Z.sqlite"
    assert backup.check_integrity(path)
    assert _count_exercises(path) == 1
    assert [p.name for p in settings.backups_dir.iterdir() if not p.name.startswith("rack-2026")] == []


def test_missing_database_is_an_error(settings: Settings) -> None:
    with pytest.raises(BackupError, match="database not found"):
        backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)


def test_corrupt_database_is_neither_backed_up_nor_touched(
    migrated_engine: Engine, settings: Settings
) -> None:
    _add_exercise(migrated_engine)
    migrated_engine.dispose()
    with open(settings.database_path, "r+b") as handle:  # keep the header, break the pages
        handle.seek(4096)
        handle.write(b"\xff" * 8192)
    before = isolation.snapshot(settings.storage.data_dir)
    with pytest.raises(CorruptDatabaseError):
        backups.backup_now(settings.database_path, settings.backups_dir, NOW, 30)
    assert isolation.snapshot(settings.storage.data_dir) == before


def test_prune_keeps_recent_newest_and_foreign_files(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    settings.backups_dir.mkdir()
    for day in range(1, 41):
        (settings.backups_dir / f"rack-{(NOW - timedelta(days=day)):%Y%m%dT%H%M%SZ}.sqlite").touch()
    for foreign in (".tmp-rack-x", "rack-1.sqlite.corrupt-2", "notes.txt"):
        (settings.backups_dir / foreign).touch()
    backups.backup_now(settings.database_path, settings.backups_dir, NOW, 30)
    names = {path.name for path in settings.backups_dir.iterdir()}
    assert len(backup.list_snapshots(settings.backups_dir)) == 31  # today + days 1..30
    assert {".tmp-rack-x", "rack-1.sqlite.corrupt-2", "notes.txt"} <= names


def test_backup_if_due(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    args = (settings.database_path, settings.backups_dir)
    assert backups.backup_if_due(*args, NOW, 30) is not None
    assert backups.backup_if_due(*args, NOW + timedelta(hours=23), 30) is None
    assert backups.backup_if_due(*args, NOW + timedelta(hours=24), 30) is not None


def test_rack_backup_prints_the_snapshot(
    migrated_engine: Engine, settings_file: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    del migrated_engine
    assert main(["backup", "--config", str(settings_file)]) == 0
    printed = Path(capsys.readouterr().out.strip())
    assert printed.parent == settings.backups_dir
    assert printed.is_file()


def test_rack_backup_on_a_corrupt_database_exits_1(
    settings_file: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    settings.database_path.write_bytes(b"this is not a database" * 300)
    assert main(["backup", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err == "rack: error: database failed the integrity check; not backed up\n"
    assert not settings.backups_dir.exists()


def test_migrate_snapshots_an_outdated_database_first(
    settings_file: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = db.create_engine(settings.database_path)
    with engine.connect():  # an existing database with every revision pending
        pass
    engine.dispose()
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out.startswith(f"backup {settings.backups_dir}")
    assert len(backup.list_snapshots(settings.backups_dir)) == 1
