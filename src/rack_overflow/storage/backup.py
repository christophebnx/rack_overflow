"""Database snapshots by `VACUUM INTO` through the atomic writer, their pruning (D-037, D-045),
and the restore of a snapshot as the database (D-075).

A corrupt database is never backed up or deleted; a restore only moves it aside. Only names that
`domain.backups` parses are listed or pruned: temp files, `.corrupt-*`, `.before-restore-*` and
foreign files are never touched.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import DBAPIError

from rack_overflow.domain import backups as rules
from rack_overflow.storage import db, files, migrate
from rack_overflow.storage.errors import BackupError, CorruptDatabaseError, MigrationError

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


def check_copy(path: Path) -> bool:
    """Integrity of a database copy in rollback-journal mode (a fresh `VACUUM INTO` snapshot, a
    staged restore), opened read-only: the file is never written."""
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
            if not check_copy(temp):
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


@dataclass(frozen=True)
class Restored:
    """A restore done: the revision of the restored file and the paths kept aside, in order."""

    revision: str
    kept: list[Path]


def _check_staged(temp: Path) -> str:
    """The revision of the staged copy, once it is sound and its revision known to this code."""
    if not check_copy(temp):
        raise BackupError("snapshot failed the integrity check")
    revision = migrate.revision_of_file(temp)
    if revision is None:
        raise MigrationError("snapshot is not a Rack Overflow database (no schema revision)")
    if migrate.revision_order(revision) == migrate.UNKNOWN:
        raise MigrationError(
            f"snapshot is at revision {revision}, unknown to this version (head "
            f"{migrate.head_revision()}); update the code first"
        )
    return revision


def _vacuum_copy(source: Path, target: Path) -> None:
    """`VACUUM INTO target` from the database at `source` through a bare read-write connection
    (no engine pragmas): `target` is a single rollback-journal file holding every committed row,
    the ones still in a `-wal` included."""
    connection = sqlite3.connect(f"{source.resolve().as_uri()}?mode=rw", uri=True, isolation_level=None)
    try:
        connection.execute("VACUUM INTO ?", (str(target),))
    finally:
        connection.close()


def _stage(snapshot: Path, temp: Path) -> None:
    """Write into `temp` a checked single-file copy of the snapshot set (the file and its `-wal` /
    `-journal`). The set is copied into a scratch folder beside `temp` first, so the snapshot and
    its side files are only read (opening a WAL file, even read-only, writes its `-shm`, and the
    last read-write close checkpoints and removes its `-wal`); the scratch folder is removed."""
    with tempfile.TemporaryDirectory(prefix=".tmp-restore-", dir=temp.parent) as scratch:
        copy = Path(scratch) / "snapshot.sqlite"
        for suffix in ("", *rules.SNAPSHOT_SIDE_SUFFIXES):
            source = Path(f"{snapshot}{suffix}")
            if suffix and not source.is_file():
                continue
            try:
                shutil.copyfile(source, f"{copy}{suffix}")
            except OSError as error:
                raise BackupError(f"cannot copy {source}: {error.strerror}") from error
        if not check_integrity(copy):
            raise BackupError("snapshot failed the integrity check")
        try:
            _vacuum_copy(copy, temp)
        except sqlite3.Error as error:
            raise BackupError(f"cannot stage a copy of {snapshot}: {error}") from error


def _set_aside(database_path: Path, now: datetime) -> list[Path]:
    """Rename the database and every side file beside it to the `aside_name` set (never deleted).
    A failed rename moves the files already renamed back, so the set is never split; the error
    names what was moved and whether it is back."""
    folder = database_path.parent
    aside = rules.aside_name(database_path.name, now, _names(folder))
    kept: list[tuple[Path, Path]] = []
    for suffix in ("", *rules.SIDE_SUFFIXES):
        source = folder / f"{database_path.name}{suffix}"
        if source.exists():
            target = folder / f"{aside}{suffix}"
            try:
                os.rename(source, target)
            except OSError as error:
                raise BackupError(
                    f"cannot move {source} aside to {target}: {error.strerror}; {_roll_back(kept)}"
                ) from error
            kept.append((source, target))
    return [target for _, target in kept]


def _roll_back(moved: list[tuple[Path, Path]]) -> str:
    """Rename each `(source, target)` back, last first; a report of what is where now."""
    if not moved:
        return "nothing was moved"
    left = []
    for source, target in reversed(moved):
        try:
            os.rename(target, source)
        except OSError:
            left.append(f"{target} (was {source})")
    if left:
        return "still moved aside: " + ", ".join(reversed(left)) + "; move them back by hand"
    return "moved back: " + ", ".join(str(source) for source, _ in moved)


def restore_snapshot(snapshot: Path, database_path: Path, now: datetime) -> Restored:
    """Make a copy of `snapshot` the database (D-075): stage a single-file copy of the snapshot
    set beside the database (`VACUUM INTO` from a scratch copy, so rows in its `-wal` are kept),
    check its integrity and revision (`head` or `older`), move the current database and its side
    files aside, then rename the copy into place. The snapshot set is only read. Any refusal
    leaves the database untouched and removes the staged copy; nothing is ever deleted."""
    if not snapshot.is_file():
        raise BackupError(f"snapshot not found: {snapshot}")
    if database_path.exists() and snapshot.resolve() == database_path.resolve():
        raise BackupError("the snapshot is the database itself; choose a file from the backups folder")
    revision: list[str] = []
    kept: list[Path] = []

    def produce(temp: Path) -> None:
        _stage(snapshot, temp)
        revision.append(_check_staged(temp))
        kept.extend(_set_aside(database_path, now))

    try:
        files.atomic_produce(database_path, produce)
    except OSError as error:
        moved = ", ".join(str(path) for path in kept) or "nothing"
        raise BackupError(
            f"restore interrupted ({error.strerror}); kept aside: {moved}; run rack restore again"
        ) from error
    return Restored(revision[0], kept)
