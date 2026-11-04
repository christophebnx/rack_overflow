"""Backup snapshot rules (D-045): naming, due-ness and age-based retention; the name of a database
kept aside by a restore (D-075). Pure: `now` is passed in."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

PREFIX = "rack-"
SUFFIX = ".sqlite"
TIME_FORMAT = "%Y%m%dT%H%M%SZ"
INTERVAL = timedelta(hours=24)
ASIDE_MARK = ".before-restore-"
SIDE_SUFFIXES = ("-wal", "-shm", "-journal")
"""SQLite files beside a database (`<name>-wal`…): they move with it, never left beside another file."""
SNAPSHOT_SIDE_SUFFIXES = ("-wal", "-journal")
"""Side files that hold rows of a database (its `-shm` is only an index SQLite rebuilds): a
restore copies them with the snapshot so its latest committed rows are kept."""
_NAME = re.compile(r"^rack-(?P<time>\d{8}T\d{6}Z)(?:_(?P<rank>\d{2,}))?\.sqlite$")


def snapshot_name(now: datetime, existing: Iterable[str]) -> str:
    """`rack-<UTC YYYYMMDDTHHMMSSZ>.sqlite`, then `_02`, `_03`… if that name is already taken."""
    taken = set(existing)
    base = f"{PREFIX}{now.astimezone(UTC).strftime(TIME_FORMAT)}"
    name = f"{base}{SUFFIX}"
    rank = 2
    while name in taken:
        name = f"{base}_{rank:02d}{SUFFIX}"
        rank += 1
    return name


def _parse(name: str) -> tuple[datetime, int] | None:
    match = _NAME.match(name)
    if match is None:
        return None
    try:
        moment = datetime.strptime(match["time"], TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None
    return moment, int(match["rank"] or 1)


def parse_snapshot_time(name: str) -> datetime | None:
    """The UTC time encoded in a snapshot name, or None when `name` is not a snapshot name."""
    parsed = _parse(name)
    return parsed[0] if parsed else None


def ordered(names: Iterable[str]) -> list[str]:
    """Snapshot names among `names`, oldest first by time then rank (`_100` after `_99`); others dropped."""
    parsed = [(key, name) for name in names if (key := _parse(name)) is not None]
    return [name for _, name in sorted(parsed)]


def newest(names: Iterable[str]) -> str | None:
    """The newest snapshot name among `names` (names that do not parse are ignored)."""
    snapshots = ordered(names)
    return snapshots[-1] if snapshots else None


def is_due(latest: datetime | None, now: datetime) -> bool:
    """True when no snapshot exists yet or the latest one is at least 24 hours old."""
    return latest is None or now - latest >= INTERVAL


def expired(names: Iterable[str], now: datetime, retention_days: int) -> list[str]:
    """Snapshot names older than `retention_days`, never the newest one, never a name that does not parse."""
    names = list(names)
    keep = newest(names)
    limit = now - timedelta(days=retention_days)
    return [
        name
        for name in ordered(names)
        if name != keep and (moment := parse_snapshot_time(name)) is not None and moment < limit
    ]


def aside_name(database_name: str, now: datetime, existing: Iterable[str]) -> str:
    """`<database name>.before-restore-<UTC YYYYMMDDTHHMMSSZ>`, then `_02`, `_03`… when that name
    or one of its side files (`SIDE_SUFFIXES`) is taken. Never a snapshot name: `prune` ignores it."""
    taken = set(existing)
    base = f"{database_name}{ASIDE_MARK}{now.astimezone(UTC).strftime(TIME_FORMAT)}"
    name, rank = base, 2
    while any(f"{name}{suffix}" in taken for suffix in ("", *SIDE_SUFFIXES)):
        name = f"{base}_{rank:02d}"
        rank += 1
    return name
