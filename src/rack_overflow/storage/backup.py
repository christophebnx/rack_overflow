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
    """True when `PRAGMA integrity_check` answers `ok` on the database."""
    if not database_path.is_file():
        raise BackupError(f"database not found: {database_path}")
    engine = db.create_engine(database_path)
    try:
        connection = engine.raw_connection()
        try:
            return _integrity(connection.driver_connection)
        finally:
            connection.close()
    except (sqlite3.DatabaseError, DBAPIError):  # not a database at all
        return False
    finally:
        engine.dispose()


def _integrity(connection: sqlite3.Connection) -> bool:
    try:
        return connection.execute("PRAGMA integrity_check").fetchall() == INTEGRITY_OK
    except sqlite3.DatabaseError:
        return False


def _copy_is_sound(path: Path) -> bool:
    """Integrity of a fresh copy, opened read-only so the check leaves no side file."""
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return _integrity(connection)
    finally:
        connection.close()


def list_snapshots(backups_dir: Path) -> list[Path]:
    """Snapshots in `backups_dir`, oldest first (names that do not parse are ignored)."""
    if not backups_dir.is_dir():
        return []
    found = [(rules.parse_snapshot_time(path.name), path) for path in backups_dir.iterdir()]
    return [path for moment, path in sorted((m, p) for m, p in found if m is not None)]


def take_snapshot(database_path: Path, backups_dir: Path, now: datetime) -> Path:
    """Write a checked `VACUUM INTO` copy of the database as `backups_dir/rack-<UTC time>.sqlite`."""
    if not check_integrity(database_path):
        raise CorruptDatabaseError("database failed the integrity check; not backed up")
    backups_dir.mkdir(parents=True, exist_ok=True)
    existing = [path.name for path in backups_dir.iterdir()]
    target = backups_dir / rules.snapshot_name(now, existing)
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
    except (sqlite3.Error, DBAPIError) as error:
        raise BackupError(f"snapshot failed: {error}") from error
    finally:
        engine.dispose()
    return target


def prune(backups_dir: Path, now: datetime, retention_days: int) -> list[Path]:
    """Delete the snapshots `domain.backups.expired` selects; return the deleted paths."""
    names = [path.name for path in list_snapshots(backups_dir)]
    deleted = [backups_dir / name for name in rules.expired(names, now, retention_days)]
    for path in deleted:
        path.unlink()
    return deleted
