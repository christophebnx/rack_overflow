"""Database snapshots by `VACUUM INTO` through the atomic writer, and their pruning (D-037, D-045).

A corrupt database is never backed up, moved or deleted. Only names that `domain.backups` parses
are listed or pruned: temp files, `.corrupt-*` and foreign files are never touched.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import DBAPIError

from rack_overflow.domain import backups as rules
from rack_overflow.storage import db, files
from rack_overflow.storage.errors import BackupError, CorruptDatabaseError

INTEGRITY_OK = [("ok",)]


def check_integrity(database_path: Path) -> bool:
    """True when `PRAGMA integrity_check` answers `ok` on the database.

    The database is opened without the engine pragmas (never switched to WAL) and read-write only
    so that SQLite removes the `-wal` / `-shm` files it creates when the check closes; a read-only
    connection cannot remove them and would leave them beside a WAL database.
    """
    if not database_path.is_file():
        raise BackupError(f"database not found: {database_path}")
    return _is_sound(database_path, read_only=False)


def _copy_is_sound(path: Path) -> bool:
    """Integrity of a fresh `VACUUM INTO` copy (rollback journal), opened read-only."""
    return _is_sound(path, read_only=True)


def _is_sound(path: Path, *, read_only: bool) -> bool:
    """Integrity of the database at `path` through a bare `sqlite3` connection (no engine)."""
    mode = "ro" if read_only else "rw"
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode={mode}", uri=True)
    except sqlite3.Error:
        return False
    try:
        return connection.execute("PRAGMA integrity_check").fetchall() == INTEGRITY_OK
    except sqlite3.DatabaseError:  # not a database at all
        return False
    finally:
        connection.close()


def _names(backups_dir: Path) -> list[str]:
    try:
        return [path.name for path in backups_dir.iterdir()]
    except OSError as error:
        raise BackupError(f"cannot list backups folder {backups_dir}: {error.strerror}") from error


def list_snapshots(backups_dir: Path) -> list[Path]:
    """Snapshots in `backups_dir`, oldest first in `domain.backups` order (other names are ignored)."""
    if not backups_dir.is_dir():
        return []
    return [backups_dir / name for name in rules.ordered(_names(backups_dir))]


def take_snapshot(database_path: Path, backups_dir: Path, now: datetime) -> Path:
    """Write a checked `VACUUM INTO` copy of the database as `backups_dir/rack-<UTC time>.sqlite`."""
    if not check_integrity(database_path):
        raise CorruptDatabaseError("database failed the integrity check; not backed up")
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BackupError(f"cannot create backups folder {backups_dir}: {error.strerror}") from error
    target = backups_dir / rules.snapshot_name(now, _names(backups_dir))
    engine = db.create_engine(database_path)
    try:

        def vacuum_into(temp: Path) -> None:
            connection = engine.raw_connection()  # autocommit: VACUUM cannot run in a transaction
            try:
                connection.driver_connection.execute("VACUUM INTO ?", (str(temp),))
            finally:
                connection.close()
            if not _copy_is_sound(temp):
                raise BackupError(f"snapshot copy failed the integrity check: {target.name}")

        files.atomic_produce(target, vacuum_into)
    except (sqlite3.Error, DBAPIError, OSError) as error:
        raise BackupError(f"snapshot failed: {error}") from error
    finally:
        engine.dispose()
    return target


def prune(backups_dir: Path, now: datetime, retention_days: int) -> list[Path]:
    """Delete the snapshots `domain.backups.expired` selects; return the deleted paths."""
    names = [path.name for path in list_snapshots(backups_dir)]
    deleted = [backups_dir / name for name in rules.expired(names, now, retention_days)]
    for path in deleted:
        try:
            path.unlink()
        except OSError as error:
            raise BackupError(f"cannot delete expired snapshot {path}: {error.strerror}") from error
    return deleted
