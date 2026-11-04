"""`rack restore` (D-075): restoring a backup on a blank instance yields identical data (roadmap
L6), the current database is kept aside with its side files, refusals change nothing, an older
snapshot is migrated, an interrupted swap completes on a rerun. In-process CLI, temporary folders,
the server probe replaced (no real port)."""

from __future__ import annotations

import hashlib
import os
import socket
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from support.migrations import upgrade_to
from support.populated import populate

from rack_overflow import cli
from rack_overflow.cli import main
from rack_overflow.config import Settings, load_settings
from rack_overflow.ops import restore as restore_guard
from rack_overflow.ops import supervise
from rack_overflow.services import seed
from rack_overflow.storage import backup, db, migrate, schema
from rack_overflow.storage.errors import BackupError, MigrationError

NOW = datetime(2026, 11, 3, 18, 42, tzinfo=UTC)
ASIDE = "rack.sqlite.before-restore-20261103T184200Z"
SETTINGS = """\
[server]
host = "0.0.0.0"
port = 8765
public_host = "testserver"

[storage]
data_dir = "data"
"""


def _settings_file(folder: Path) -> Path:
    folder.mkdir()
    path = folder / "settings.toml"
    path.write_text(SETTINGS, encoding="utf-8")
    return path


def _refused(address: tuple[str, int], timeout: float) -> socket.socket:
    del address, timeout
    raise ConnectionRefusedError


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixed CLI clock; no server answers (the probe never opens a real connection)."""
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    monkeypatch.setattr(restore_guard, "_connect", _refused)


@pytest.fixture
def source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Settings:
    """A migrated, populated instance."""
    path = _settings_file(tmp_path / "source")
    assert main(["migrate", "--config", str(path)]) == 0
    settings = load_settings(path)
    engine = db.create_engine(settings.database_path)
    try:
        populate(engine)
    finally:
        engine.dispose()
    capsys.readouterr()
    return settings


@pytest.fixture
def snapshot(source: Settings, capsys: pytest.CaptureFixture[str]) -> Path:
    """`rack backup` of the source."""
    assert main(["backup", "--config", str(source.storage.data_dir.parent / "settings.toml")]) == 0
    return Path(capsys.readouterr().out.strip())


@pytest.fixture
def target(tmp_path: Path) -> Iterator[Path]:
    """The settings file of a blank instance (its data folder does not exist)."""
    yield _settings_file(tmp_path / "target")


def dump(path: Path) -> list[str]:
    """Every statement of the database: tables, indexes, rows, `alembic_version`, secrets."""
    connection = sqlite3.connect(path)
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def restore(config: Path, snapshot: Path | str) -> int:
    return main(["restore", str(snapshot), "--config", str(config)])


# --- the roadmap criterion


def test_restore_on_a_blank_instance_yields_identical_data(
    source: Settings, snapshot: Path, target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sha(snapshot)
    assert restore(target, snapshot) == 0
    restored = load_settings(target).database_path
    assert capsys.readouterr().out == (
        f"restored {snapshot} as {restored} at revision {migrate.head_revision()}\n"
    )
    assert dump(restored) == dump(source.database_path)
    connection = sqlite3.connect(restored)
    try:  # backups keep the credential hashes (unlike the export): paired devices stay paired
        assert connection.execute("SELECT count(*) FROM device WHERE token_hash IS NOT NULL").fetchone() == (
            1,
        )
    finally:
        connection.close()
    assert sha(snapshot) == before
    assert names(restored.parent) == ["rack.sqlite", "supervise.lock"]


def test_a_bare_name_is_found_in_the_backups_folder(
    source: Settings, snapshot: Path, target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backups_dir = load_settings(target).backups_dir
    backups_dir.mkdir(parents=True)
    (backups_dir / snapshot.name).write_bytes(snapshot.read_bytes())
    assert restore(target, snapshot.name) == 0
    assert f"restored {backups_dir / snapshot.name} as" in capsys.readouterr().out
    assert dump(load_settings(target).database_path) == dump(source.database_path)


def test_the_current_database_is_kept_aside(
    source: Settings, snapshot: Path, target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["migrate", "--config", str(target)]) == 0
    current = load_settings(target).database_path
    fresh = dump(current)
    capsys.readouterr()
    assert restore(target, snapshot) == 0
    aside = current.parent / ASIDE
    assert capsys.readouterr().out.splitlines()[0] == f"kept {aside}"
    assert dump(current) == dump(source.database_path)
    assert dump(aside) == fresh
    assert backup.list_snapshots(current.parent / "backups") == []  # never mistaken for a snapshot


def test_side_files_move_aside_with_the_latest_rows(
    snapshot: Path, target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["migrate", "--config", str(target)]) == 0
    current = load_settings(target).database_path
    engine = db.create_engine(current)
    connection = engine.raw_connection()
    try:
        connection.driver_connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.driver_connection.execute(
            "INSERT INTO app_setting (user_id, key, value) VALUES (1, 'latest', 'in the wal')"
        )
        assert (current.parent / "rack.sqlite-wal").stat().st_size > 0
        capsys.readouterr()
        assert restore(target, snapshot) == 0
    finally:
        connection.close()
        engine.dispose()
    out = capsys.readouterr().out
    assert f"kept {current.parent / ASIDE}-wal" in out
    aside = sqlite3.connect(current.parent / ASIDE)
    try:
        assert aside.execute("SELECT value FROM app_setting WHERE key = 'latest'").fetchone() == (
            "in the wal",
        )
    finally:
        aside.close()


def test_restored_database_serves(snapshot: Path, target: Path) -> None:
    assert restore(target, snapshot) == 0
    engine = cli._open_current_database(load_settings(target))
    engine.dispose()


# --- an older snapshot


def test_an_older_snapshot_is_migrated_and_keeps_its_data(
    tmp_path: Path, target: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tmp_path / "old.sqlite"
    engine = db.create_engine(old)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0003"))
            migrate.upgrade_to_head(engine)
        seed.seed_catalog(engine, 1)
        with engine.begin() as connection:
            connection.execute(sa.insert(schema.app_setting).values(user_id=1, key="kept", value="yes"))
            count = connection.execute(sa.select(sa.func.count()).select_from(schema.exercise)).scalar_one()
    finally:
        engine.dispose()
    snapshot = backup.take_snapshot(old, tmp_path / "snaps", NOW)
    capsys.readouterr()
    assert restore(target, snapshot) == 0
    restored = load_settings(target).database_path
    assert capsys.readouterr().out == (
        f"restored {snapshot} as {restored} at revision 0003\n"
        f"database {restored} at revision {migrate.head_revision()}\n"
    )
    engine = db.create_engine(restored)
    try:
        assert migrate.is_up_to_date(engine)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.select(schema.app_setting.c.value).where(schema.app_setting.c.key == "kept")
                ).scalar_one()
                == "yes"
            )
            assert (
                connection.execute(sa.select(sa.func.count()).select_from(schema.exercise)).scalar_one()
                == count
            )
    finally:
        engine.dispose()


# --- refusals change nothing


@pytest.fixture
def current(target: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """The target with a migrated database."""
    assert main(["migrate", "--config", str(target)]) == 0
    capsys.readouterr()
    return load_settings(target).database_path


def assert_untouched(database: Path, statements: list[str], digest: str) -> None:
    assert sha(database) == digest
    assert dump(database) == statements
    assert [
        name for name in names(database.parent) if "before-restore" in name or name.startswith(".tmp-")
    ] == []


def _foreign(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    connection.commit()
    connection.close()
    return path


def _unknown_revision(snapshot: Path, folder: Path) -> Path:
    path = folder / "newer.sqlite"
    path.write_bytes(snapshot.read_bytes())
    connection = sqlite3.connect(path)
    connection.execute("UPDATE alembic_version SET version_num = '9999'")
    connection.commit()
    connection.close()
    return path


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda snapshot, folder: folder / "missing.sqlite", "snapshot not found"),
        (lambda snapshot, folder: _garbage(folder), "snapshot failed the integrity check"),
        (lambda snapshot, folder: _truncated(snapshot, folder), "snapshot failed the integrity check"),
        (lambda snapshot, folder: _foreign(folder / "foreign.sqlite"), "not a Rack Overflow database"),
        (
            lambda snapshot, folder: _unknown_revision(snapshot, folder),
            f"snapshot is at revision 9999, unknown to this version (head {migrate.head_revision()}); "
            "update the code first",
        ),
    ],
)
def test_bad_snapshots_are_refused(
    snapshot: Path,
    current: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    make: object,
    message: str,
) -> None:
    bad = make(snapshot, tmp_path)  # type: ignore[operator]
    statements, digest = dump(current), sha(current)
    bad_digest = sha(bad) if bad.exists() else None
    assert restore(current.parent.parent / "settings.toml", bad) == 1
    assert message in capsys.readouterr().err
    assert_untouched(current, statements, digest)
    if bad_digest is not None:
        assert sha(bad) == bad_digest


def _garbage(folder: Path) -> Path:
    path = folder / "garbage.sqlite"
    path.write_bytes(os.urandom(8192))
    return path


def _truncated(snapshot: Path, folder: Path) -> Path:
    path = folder / "truncated.sqlite"
    path.write_bytes(snapshot.read_bytes()[: snapshot.stat().st_size // 2])
    return path


def test_the_database_itself_is_refused(current: Path, capsys: pytest.CaptureFixture[str]) -> None:
    statements, digest = dump(current), sha(current)
    assert restore(current.parent.parent / "settings.toml", current) == 1
    assert "the snapshot is the database itself" in capsys.readouterr().err
    assert_untouched(current, statements, digest)


def test_running_supervisor_is_refused(
    snapshot: Path, current: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    statements, digest = dump(current), sha(current)
    held = supervise.acquire_lock(current.parent)
    try:
        assert restore(current.parent.parent / "settings.toml", snapshot) == 1
    finally:
        os.close(held)
    assert (
        capsys.readouterr().err
        == "rack: error: rack supervise is running on this data folder; stop it first\n"
    )
    assert_untouched(current, statements, digest)


def test_answering_server_is_refused(
    snapshot: Path, current: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    probed: list[tuple[str, int]] = []

    def answering(address: tuple[str, int], timeout: float) -> socket.socket:
        del timeout
        probed.append(address)
        left, right = socket.socketpair()
        right.close()
        return left

    monkeypatch.setattr(restore_guard, "_connect", answering)
    statements, digest = dump(current), sha(current)
    assert restore(current.parent.parent / "settings.toml", snapshot) == 1
    assert capsys.readouterr().err == "rack: error: a server answers on 127.0.0.1:8765; stop it first\n"
    assert probed == [("127.0.0.1", 8765)]
    assert_untouched(current, statements, digest)


# --- interrupted swap


def test_an_interrupted_swap_completes_on_a_rerun(
    source: Settings,
    snapshot: Path,
    current: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh = dump(current)
    config = current.parent.parent / "settings.toml"

    def power_cut(source_path: object, target_path: object) -> None:
        del source_path, target_path
        raise OSError(5, "Input/output error")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", power_cut)
        assert restore(config, snapshot) == 1
    err = capsys.readouterr().err
    assert "restore interrupted" in err and f"kept aside: {current.parent / ASIDE}" in err
    assert not current.exists()
    assert main(["serve", "--config", str(config)]) == 1
    assert "database is not up to date; run rack migrate" in capsys.readouterr().err
    assert not current.exists()
    assert restore(config, snapshot) == 0
    assert dump(current) == dump(source.database_path)
    assert dump(current.parent / ASIDE) == fresh


def test_storage_refuses_a_missing_snapshot_without_side_effects(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="snapshot not found"):
        backup.restore_snapshot(tmp_path / "none.sqlite", tmp_path / "rack.sqlite", NOW)
    assert list(tmp_path.iterdir()) == []


def test_revision_of_file(snapshot: Path, tmp_path: Path) -> None:
    before = sha(snapshot)
    assert migrate.revision_of_file(snapshot) == migrate.head_revision()
    assert sha(snapshot) == before
    assert names(snapshot.parent) == [snapshot.name]  # no -wal / -shm left beside it
    assert migrate.revision_of_file(_foreign(tmp_path / "f.sqlite")) is None
    with pytest.raises(MigrationError):
        migrate.revision_of_file(_garbage(tmp_path))


def test_revision_order() -> None:
    assert migrate.known_revisions() == ["0001", "0002", "0003", "0004"]
    assert [migrate.revision_order(name) for name in ("0001", "0003", "0004", "0005", "x")] == [
        "older",
        "older",
        "head",
        "unknown",
        "unknown",
    ]


def test_a_failed_migration_leaves_the_restored_revision(
    tmp_path: Path, target: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tmp_path / "old.sqlite"
    engine = db.create_engine(old)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0003"))
            migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
    snapshot = backup.take_snapshot(old, tmp_path / "snaps", NOW)

    def failing(engine: object) -> str:
        del engine
        raise MigrationError("migration failed: disk full")

    monkeypatch.setattr(migrate, "upgrade_to_head", failing)
    assert restore(target, snapshot) == 1
    assert capsys.readouterr().err == (
        "rack: error: migration failed: disk full; "
        "the restored database is at revision 0003; run rack migrate\n"
    )
    assert migrate.revision_of_file(load_settings(target).database_path) == "0003"
