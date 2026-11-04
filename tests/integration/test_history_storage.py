"""History, progress and RM queries of `storage/sessions` and `storage/rm` (D-067 to D-070) on a
migrated database: keyset pages, sets of a page, session dates, exercises with history, soft
delete of a session, last performance of any session, local dates of record history, measured
RM rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.timestamps import to_text
from rack_overflow.services import exercises
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.storage import rm
from rack_overflow.storage import schema as s
from rack_overflow.storage import sessions as queries

USER = 1
OTHER = 2
T0 = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)


def make(engine: Engine, name: str, category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def session_with(
    connection: sa.Connection,
    started: datetime,
    sets: dict[int, list[tuple[str, int, int]]],
    user: int = USER,
    *,
    close: bool = True,
) -> int:
    """A session started at `started` holding, per exercise, sets `(type, reps, weight_g)`."""
    session_id = queries.insert_session(
        connection,
        user,
        local_date=started.date().isoformat(),
        time_zone="Europe/Brussels",
        started_at=to_text(started),
        location="gym",
        template_id=None,
    )
    for exercise_id, items in sets.items():
        row = queries.insert_session_exercise(connection, session_id, exercise_id, None)
        for number, (kind, reps, weight) in enumerate(items):
            queries.insert_set(
                connection,
                row,
                set_type=kind,
                core={"reps": reps, "weight": weight},
                completed_at=to_text(started + timedelta(minutes=number)),
            )
    if close:
        queries.close_session(connection, session_id, to_text(started + timedelta(hours=1)))
    return session_id


def test_history_page_keyset_newest_first(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    with migrated_engine.begin() as connection:
        ids = [
            session_with(connection, T0 + timedelta(days=i), {squat: [("work", 5, 100000)]}) for i in range(5)
        ]
        session_with(connection, T0, {}, user=OTHER)
        first = queries.history_page(connection, USER, None, 2)
        second = queries.history_page(connection, USER, first[-1].id, 2)
        queries.soft_delete_session(connection, ids[2], to_text(T0))
        after_delete = queries.history_page(connection, USER, ids[3], 2)
        assert queries.history_page(connection, USER, 10**9, 2) == []
    assert [row.id for row in first] == [ids[4], ids[3]]
    assert [row.id for row in second] == [ids[2], ids[1]]
    assert [row.id for row in after_delete] == [ids[1], ids[0]]
    assert first[0].template_name is None


def test_history_page_same_start_orders_by_id(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        a = session_with(connection, T0, {})
        b = session_with(connection, T0, {})
        page = queries.history_page(connection, USER, None, 1)
        rest = queries.history_page(connection, USER, page[0].id, 5)
    assert [row.id for row in page] == [b] and [row.id for row in rest] == [a]


def test_sets_for_sessions_live_only(migrated_engine: Engine) -> None:
    squat, bench = make(migrated_engine, "Squat"), make(migrated_engine, "Bench")
    with migrated_engine.begin() as connection:
        sid = session_with(
            connection, T0, {squat: [("warmup", 8, 40000), ("work", 5, 100000)], bench: [("work", 5, 80000)]}
        )
        found = queries.sets_for_sessions(connection, [sid])
        queries.soft_delete_set(connection, found[0].id, to_text(T0))
        after = queries.sets_for_sessions(connection, [sid])
        assert queries.sets_for_sessions(connection, []) == []
    assert [(row.exercise_name, row.type) for row in found] == [
        ("Squat", "warmup"),
        ("Squat", "work"),
        ("Bench", "work"),
    ]
    assert len(after) == 2 and after[0].category == "strength" and after[0].session_id == sid


def test_session_dates_need_a_live_set_and_a_live_session(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    with migrated_engine.begin() as connection:
        session_with(connection, T0, {squat: [("work", 5, 100000)]})
        session_with(connection, T0 + timedelta(days=1), {})
        deleted = session_with(connection, T0 + timedelta(days=2), {squat: [("work", 5, 100000)]})
        session_with(connection, T0 - timedelta(days=30), {squat: [("work", 5, 100000)]})
        session_with(connection, T0 + timedelta(days=3), {squat: [("work", 5, 100000)]}, close=False)
        queries.soft_delete_session(connection, deleted, to_text(T0))
        dates = queries.session_dates(connection, USER, "2026-09-15")
    assert dates == ["2026-10-01", "2026-10-04"]


def test_exercises_with_history(migrated_engine: Engine) -> None:
    squat, bench, row = (
        make(migrated_engine, "Squat"),
        make(migrated_engine, "Bench"),
        make(migrated_engine, "Row"),
    )
    with migrated_engine.begin() as connection:
        session_with(connection, T0, {squat: [("work", 5, 100000)], bench: [("work", 5, 80000)]})
        session_with(connection, T0 + timedelta(days=2), {squat: [("work", 5, 100000)], row: []})
        gone = session_with(connection, T0 + timedelta(days=4), {bench: [("work", 5, 80000)]})
        queries.soft_delete_session(connection, gone, to_text(T0))
        found = queries.exercises_with_history(connection, USER)
    assert [(r.name, r.last_date, r.session_count) for r in found] == [
        ("Squat", "2026-10-03", 2),
        ("Bench", "2026-10-01", 1),
    ]


def test_soft_delete_session_keeps_the_rows(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    with migrated_engine.begin() as connection:
        sid = session_with(connection, T0, {squat: [("work", 5, 100000)]}, close=False)
        assert queries.soft_delete_session(connection, sid, to_text(T0))
        assert not queries.soft_delete_session(connection, sid, to_text(T0))
        assert queries.get_session(connection, USER, sid) is None
        assert queries.open_session(connection, USER) is None
        stored = connection.execute(
            sa.select(s.session.c.deleted_at).where(s.session.c.id == sid)
        ).scalar_one()
        sets = connection.execute(sa.select(sa.func.count()).select_from(s.set_entry)).scalar_one()
    assert stored == to_text(T0) and sets == 1


def test_last_performance_of_any_session_and_local_dates(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    with migrated_engine.begin() as connection:
        first = session_with(connection, T0, {squat: [("work", 5, 100000)]})
        latest = session_with(
            connection, T0 + timedelta(days=1), {squat: [("rm_test", 1, 120000)]}, close=False
        )
        any_session = queries.last_performance(connection, USER, squat, None)
        other = queries.last_performance(connection, USER, squat, latest)
        history = queries.record_history(connection, USER, squat)
    assert [row.session_id for row in any_session] == [latest]
    assert [row.session_id for row in other] == [first]
    assert [(row.local_date, row.type) for row in history] == [
        ("2026-10-01", "work"),
        ("2026-10-02", "rm_test"),
    ]


def test_measured_rm_rows(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    other = make(migrated_engine, "Squat", user=OTHER)
    with migrated_engine.begin() as connection:
        late = rm.insert_measured(
            connection, USER, squat, n=1, weight_g=105000, measured_on="2026-10-12", created_at="x"
        )
        early = rm.insert_measured(
            connection, USER, squat, n=5, weight_g=92500, measured_on="2026-10-01", created_at="x"
        )
        foreign = rm.insert_measured(
            connection, OTHER, other, n=1, weight_g=1000, measured_on="2026-10-01", created_at="x"
        )
        assert [row.id for row in rm.measured_of(connection, USER, squat)] == [early, late]
        assert rm.get_measured(connection, USER, foreign) is None
        assert rm.get_measured(connection, USER, late).weight_g == 105000
        rm.soft_delete_measured(connection, late, "2026-11-03T18:00:00Z")
        assert rm.get_measured(connection, USER, late) is None
        assert [row.id for row in rm.measured_of(connection, USER, squat)] == [early]
        total = connection.execute(sa.select(sa.func.count()).select_from(s.rm_measured)).scalar_one()
    assert total == 3
