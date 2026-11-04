"""The backup operation, shared by `rack backup`, `rack migrate` and the server (D-037, D-045), and
the restore of a snapshot (`rack restore`, D-075)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rack_overflow.domain import backups as rules
from rack_overflow.storage import backup


def backup_now(database_path: Path, backups_dir: Path, now: datetime, retention_days: int) -> Path:
    """Take a snapshot, then prune expired ones; a failed snapshot raises and prunes nothing."""
    snapshot = backup.take_snapshot(database_path, backups_dir, now)
    backup.prune(backups_dir, now, retention_days)
    return snapshot


def backup_if_due(database_path: Path, backups_dir: Path, now: datetime, retention_days: int) -> Path | None:
    """`backup_now` when the newest snapshot is at least 24 hours old (or none exists), else None."""
    newest = rules.newest(path.name for path in backup.list_snapshots(backups_dir))
    latest = rules.parse_snapshot_time(newest) if newest else None
    if not rules.is_due(latest, now):
        return None
    return backup_now(database_path, backups_dir, now, retention_days)


def restore(snapshot: Path, database_path: Path, now: datetime) -> backup.Restored:
    """Restore `snapshot` as the database, the current one kept aside (the caller has stopped the
    server; an older revision is migrated by the caller, as `rack migrate` does)."""
    return backup.restore_snapshot(snapshot, database_path, now)
