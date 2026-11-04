"""Edge cases of the snapshots (D-037, D-045): collisions, consistency, failures, retention via the CLI."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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


def _exercise_names(path: Path) -> list[str]:
    engine = db.create_engine(path)
    try:
        with engine.connect() as connection:
            return list(connection.execute(sa.select(schema.exercise.c.name).order_by("id")).scalars())
    finally:
        engine.dispose()


def _add(connection: sa.Connection, name: str) -> None:
    row = {"user_id": 1, "name": name, "category": "strength", "location": "gym"}
    connection.execute(sa.insert(schema.exercise).values(row))


def _old_snapshots(folder: Path, days: range) -> None:
    folder.mkdir(exist_ok=True)
    for day in days:
        (folder / f"rack-{(NOW - timedelta(days=day)):%Y%m%dT%H%M%SZ}.sqlite").write_bytes(b"old")


def test_two_snapshots_in_the_same_second_do_not_collide(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    first = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    second = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    third = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    assert [first.name, second.name, third.name] == [
        "rack-20261103T180405Z.sqlite",
        "rack-20261103T180405Z_02.sqlite",
        "rack-20261103T180405Z_03.sqlite",
    ]
    assert backup.list_snapshots(settings.backups_dir) == [first, second, third]


def test_snapshot_name_is_in_utc_whatever_the_clock_zone(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    paris = NOW.astimezone(ZoneInfo("Europe/Paris"))
    path = backup.take_snapshot(settings.database_path, settings.backups_dir, paris)
    assert path.name == "rack-20261103T180405Z.sqlite"


def test_snapshot_is_consistent_with_a_write_in_progress(migrated_engine: Engine, settings: Settings) -> None:
    with migrated_engine.begin() as connection:
        _add(connection, "Committed")
    with migrated_engine.connect() as writer:
        transaction = writer.begin()
        _add(writer, "Uncommitted")
        path = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
        transaction.rollback()
    assert backup.check_integrity(path)
    assert _exercise_names(path) == ["Committed"]


def test_snapshot_is_a_standalone_database(migrated_engine: Engine, settings: Settings) -> None:
    with migrated_engine.begin() as connection:
        _add(connection, "Squat")
    path = backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    migrated_engine.dispose()
    sidecars = [p.name for p in settings.backups_dir.iterdir() if p.name != path.name]
    assert sidecars == []
    assert _exercise_names(path) == ["Squat"]


def test_unsound_copy_leaves_no_file_and_prunes_nothing(
    migrated_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    _old_snapshots(settings.backups_dir, range(40, 45))
    before = isolation.snapshot(settings.backups_dir)
    monkeypatch.setattr(backup, "check_copy", lambda path: False)
    with pytest.raises(BackupError, match="failed the integrity check"):
        backups.backup_now(settings.database_path, settings.backups_dir, NOW, 30)
    assert isolation.snapshot(settings.backups_dir) == before


@pytest.mark.parametrize("content", [b"this is not a database" * 300, b"SQLite format 3\x00" + b"\x00" * 200])
def test_garbage_file_fails_the_integrity_check(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "rack.sqlite"
    path.write_bytes(content)
    assert backup.check_integrity(path) is False
    assert path.read_bytes() == content
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rack.sqlite"]


def test_corrupt_database_keeps_old_snapshots_and_the_database(
    migrated_engine: Engine, settings_file: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    migrated_engine.dispose()
    _old_snapshots(settings.backups_dir, range(1, 41))
    with open(settings.database_path, "r+b") as handle:
        handle.seek(4096)
        handle.write(b"\xff" * 8192)
    before = isolation.snapshot(settings.storage.data_dir)
    assert main(["backup", "--config", str(settings_file)]) == 1
    assert "integrity check" in capsys.readouterr().err
    assert isolation.snapshot(settings.storage.data_dir) == before


def test_rack_backup_applies_the_configured_retention(
    migrated_engine: Engine, settings_file: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8") + "\n[backup]\nretention_days = 5\n", encoding="utf-8"
    )
    monkeypatch.setattr("rack_overflow.cli._now", lambda: NOW)
    _old_snapshots(settings.backups_dir, range(1, 11))
    (settings.backups_dir / "keep-me.sqlite").write_bytes(b"foreign")
    assert main(["backup", "--config", str(settings_file)]) == 0
    kept = [path.name for path in backup.list_snapshots(settings.backups_dir)]
    assert kept[-1] == "rack-20261103T180405Z.sqlite"
    assert len(kept) == 6  # today + days 1..5
    assert (settings.backups_dir / "keep-me.sqlite").is_file()


def test_retention_of_30_keeps_the_boundary_day(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    _old_snapshots(settings.backups_dir, range(29, 32))
    deleted = backup.prune(settings.backups_dir, NOW, 30)
    assert [path.name for path in deleted] == [f"rack-{(NOW - timedelta(days=31)):%Y%m%dT%H%M%SZ}.sqlite"]


def test_only_old_snapshots_keep_the_newest(settings: Settings) -> None:
    _old_snapshots(settings.backups_dir, range(100, 103))
    deleted = backup.prune(settings.backups_dir, NOW, 30)
    assert len(deleted) == 2
    assert [path.name for path in backup.list_snapshots(settings.backups_dir)] == [
        f"rack-{(NOW - timedelta(days=100)):%Y%m%dT%H%M%SZ}.sqlite"
    ]


def test_missing_backups_folder(tmp_path: Path) -> None:
    assert backup.list_snapshots(tmp_path / "absent") == []
    assert backup.prune(tmp_path / "absent", NOW, 30) == []
    assert not (tmp_path / "absent").exists()


def test_backup_if_due_uses_the_newest_snapshot(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    _old_snapshots(settings.backups_dir, range(2, 5))
    (settings.backups_dir / f"rack-{(NOW - timedelta(hours=1)):%Y%m%dT%H%M%SZ}.sqlite").write_bytes(b"x")
    assert backups.backup_if_due(settings.database_path, settings.backups_dir, NOW, 30) is None


def test_backup_if_due_ignores_foreign_names(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    settings.backups_dir.mkdir()
    (settings.backups_dir / "rack-29991231T000000Z.sqlite.corrupt-1").write_bytes(b"x")
    (settings.backups_dir / ".tmp-rack-29991231T000000Z.sqlite").write_bytes(b"x")
    assert backups.backup_if_due(settings.database_path, settings.backups_dir, NOW, 30) is not None


def test_corrupt_database_raises_the_specific_error(settings: Settings) -> None:
    settings.database_path.write_bytes(b"x" * 4096)
    with pytest.raises(CorruptDatabaseError):
        backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    assert not settings.backups_dir.exists()


def test_list_snapshots_puts_rank_100_after_rank_99(settings: Settings) -> None:
    settings.backups_dir.mkdir()
    for rank in ("_99", "_100", ""):
        (settings.backups_dir / f"rack-20261103T180405Z{rank}.sqlite").write_bytes(b"x")
    assert [path.name for path in backup.list_snapshots(settings.backups_dir)] == [
        "rack-20261103T180405Z.sqlite",
        "rack-20261103T180405Z_99.sqlite",
        "rack-20261103T180405Z_100.sqlite",
    ]


def test_backup_if_due_reads_the_highest_rank(
    migrated_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    settings.backups_dir.mkdir()
    for rank in ("_99", "_100"):
        (settings.backups_dir / f"rack-20261103T180405Z{rank}.sqlite").write_bytes(b"x")
    seen: list[str] = []
    real = backups.rules.parse_snapshot_time
    monkeypatch.setattr(backups.rules, "parse_snapshot_time", lambda name: seen.append(name) or real(name))
    assert backups.backup_if_due(settings.database_path, settings.backups_dir, NOW, 30) is None
    assert seen == ["rack-20261103T180405Z_100.sqlite"]


def test_backups_folder_that_cannot_be_created(migrated_engine: Engine, settings: Settings) -> None:
    del migrated_engine
    settings.backups_dir.write_bytes(b"a file where the folder should be")
    with pytest.raises(BackupError, match="cannot create backups folder"):
        backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)


def test_backups_folder_that_cannot_be_listed(
    migrated_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    settings.backups_dir.mkdir()

    def refuse(self: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "iterdir", refuse)
    with pytest.raises(BackupError, match="cannot list backups folder"):
        backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)
    with pytest.raises(BackupError, match="cannot list backups folder"):
        backup.list_snapshots(settings.backups_dir)


def test_expired_snapshot_that_cannot_be_deleted(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _old_snapshots(settings.backups_dir, range(100, 102))

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "unlink", refuse)
    with pytest.raises(BackupError, match="cannot delete expired snapshot"):
        backup.prune(settings.backups_dir, NOW, 30)


def test_snapshot_write_failure_is_a_backup_error(
    migrated_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine

    def disk_full(path: Path, produce: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(backup.files, "atomic_produce", disk_full)
    with pytest.raises(BackupError, match="snapshot failed"):
        backup.take_snapshot(settings.database_path, settings.backups_dir, NOW)


def test_rack_backup_reports_an_unwritable_backups_folder(
    migrated_engine: Engine, settings_file: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    del migrated_engine
    settings.backups_dir.write_bytes(b"x")
    assert main(["backup", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err.startswith("rack: error: cannot create backups folder")


def test_integrity_check_leaves_a_rollback_journal_database_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "plain.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (x INTEGER)")
    connection.commit()
    connection.close()
    content = path.read_bytes()
    assert backup.check_integrity(path)
    assert path.read_bytes() == content
    assert sorted(p.name for p in tmp_path.iterdir()) == ["plain.sqlite"]
