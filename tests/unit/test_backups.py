from datetime import UTC, datetime, timedelta, timezone

import pytest

from rack_overflow.domain import backups

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def test_snapshot_name_in_utc() -> None:
    paris = NOW.astimezone(timezone(timedelta(hours=1)))
    assert backups.snapshot_name(paris, []) == "rack-20261103T180405Z.sqlite"


def test_snapshot_name_collisions() -> None:
    first = backups.snapshot_name(NOW, [])
    second = backups.snapshot_name(NOW, [first])
    third = backups.snapshot_name(NOW, [first, second])
    assert (second, third) == ("rack-20261103T180405Z_02.sqlite", "rack-20261103T180405Z_03.sqlite")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("rack-20261103T180405Z.sqlite", NOW),
        ("rack-20261103T180405Z_02.sqlite", NOW),
        ("rack-20261399T180405Z.sqlite", None),
        (".tmp-rack-20261103T180405Z.sqlite-ab12", None),
        ("rack-20261103T180405Z.sqlite.corrupt-20261104T000000Z", None),
        ("notes.txt", None),
    ],
)
def test_parse_snapshot_time(name: str, expected: datetime | None) -> None:
    assert backups.parse_snapshot_time(name) == expected


def test_is_due() -> None:
    assert backups.is_due(None, NOW)
    assert not backups.is_due(NOW - timedelta(hours=23, minutes=59), NOW)
    assert backups.is_due(NOW - timedelta(hours=24), NOW)


def test_expired_keeps_recent_and_ignores_foreign_names() -> None:
    names = [backups.snapshot_name(NOW - timedelta(days=day), []) for day in range(40)]
    foreign = [".tmp-x", "rack-x.sqlite.corrupt-1", "readme.txt"]
    gone = backups.expired(names + foreign, NOW, 30)
    assert gone == sorted(names[31:])


def test_expired_never_removes_the_newest() -> None:
    old = [backups.snapshot_name(NOW - timedelta(days=day), []) for day in (100, 200)]
    assert backups.expired(old, NOW, 30) == [old[1]]
    assert backups.newest([*old, "junk"]) == old[0]


def test_ordered_uses_time_then_rank() -> None:
    base = "rack-20261103T180405Z"
    names = [f"{base}_100.sqlite", f"{base}_99.sqlite", f"{base}.sqlite", "readme.txt", f"{base}_02.sqlite"]
    assert backups.ordered(names) == [
        f"{base}.sqlite",
        f"{base}_02.sqlite",
        f"{base}_99.sqlite",
        f"{base}_100.sqlite",
    ]
    assert backups.newest(names) == f"{base}_100.sqlite"


ASIDE_AT = datetime(2026, 11, 3, 19, 42, 0, tzinfo=timezone(timedelta(hours=1)))


def test_aside_name_in_utc() -> None:
    assert backups.aside_name("rack.sqlite", ASIDE_AT, []) == "rack.sqlite.before-restore-20261103T184200Z"


def test_aside_name_collisions_include_side_files() -> None:
    base = "rack.sqlite.before-restore-20261103T184200Z"
    assert backups.aside_name("rack.sqlite", ASIDE_AT, [base]) == f"{base}_02"
    assert backups.aside_name("rack.sqlite", ASIDE_AT, [f"{base}-wal"]) == f"{base}_02"
    assert backups.aside_name("rack.sqlite", ASIDE_AT, [base, f"{base}_02-shm"]) == f"{base}_03"


def test_aside_names_are_never_snapshots() -> None:
    names = [backups.aside_name("rack.sqlite", ASIDE_AT, []), "rack-20261103T184200Z.sqlite.before-restore-x"]
    assert [backups.parse_snapshot_time(name) for name in names] == [None, None]
    assert backups.ordered(names) == []
    assert backups.expired(names, ASIDE_AT + timedelta(days=400), 30) == []


def test_side_suffixes() -> None:
    assert backups.SIDE_SUFFIXES == ("-wal", "-shm", "-journal")
