"""L5 operations through `services.history`, `services.progress` and `services.sessions` on a
migrated database (D-067 to D-070): history pages, consistency, session delete and its effect on
every reader, closed-session corrections, the progress page, RM entries and the formula."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.sessions import SessionError
from rack_overflow.services import exercises, history, progress, sessions, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.sessions import SessionView, SummaryView
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import app_settings
from rack_overflow.storage import schema as s

USER = 1
OTHER = 2
TZ = ZoneInfo("Europe/Brussels")
T0 = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)
DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)


def make(engine: Engine, name: str, category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def logged(
    engine: Engine,
    when: datetime,
    sets: dict[int, list[tuple[str, dict[str, str]]]],
    *,
    close: bool = True,
    settings: dict[str, str | None] | None = None,
) -> int:
    """A free session at `when` with the given sets (and settings) per exercise, closed an hour
    later."""
    session_id = sessions.start(engine, USER, None, "gym", when, TZ)
    for exercise_id, items in sets.items():
        block = sessions.pick(engine, USER, session_id, None, exercise_id).block
        assert block is not None
        if settings:
            sessions.save_settings(engine, USER, session_id, block.id, settings)
        for number, (kind, values) in enumerate(items, start=1):
            sessions.confirm_set(engine, USER, session_id, block.id, kind, values, when + number * MINUTE)
    if close:
        sessions.close(engine, USER, session_id, when + 60 * MINUTE)
    return session_id


def lift(reps: int, kg: str) -> dict[str, str]:
    return {"reps": str(reps), "weight": kg}


def summary(engine: Engine, session_id: int) -> SummaryView:
    found = sessions.show(engine, USER, session_id)
    assert isinstance(found, SummaryView)
    return found


# --- history


def test_history_pages_months_volumes_and_tags(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat, bench = make(engine, "Squat"), make(engine, "Bench")
    ids = [
        logged(engine, T0 + i * 2 * DAY, {squat: [("warmup", lift(8, "40")), ("work", lift(5, "100"))]})
        for i in range(21)
    ]
    empty = logged(engine, T0 + 50 * DAY, {})
    both = logged(
        engine, T0 + 51 * DAY, {squat: [("work", lift(5, "100"))], bench: [("work", lift(5, "80"))]}
    )
    current = logged(engine, T0 + 52 * DAY, {}, close=False)
    first = history.history_page(engine, USER)
    assert first.count == 20 and not first.continues_month and first.next_before is not None
    items = [item for group in first.months for item in group.items]
    assert [item.id for item in items[:3]] == [current, both, empty]
    assert items[0].open and not items[1].open
    assert items[1].exercises == ("Squat", "Bench") and items[1].sets == 2 and items[1].load_g == 900000
    assert items[2].exercises == () and items[2].sets == 0
    assert items[3].sets == 1 and items[3].load_g == 500000  # the warm-up is not counted
    assert [group.key for group in first.months] == ["2026-11", "2026-10"]
    second = history.history_page(engine, USER, first.next_before)
    assert second.next_before is None and second.count == 4
    assert second.continues_month and second.months[0].key == "2026-10"
    assert [item.id for group in second.months for item in group.items][-1] == ids[0]


def test_history_empty(migrated_engine: Engine) -> None:
    page = history.history_page(migrated_engine, USER)
    assert page.months == () and page.next_before is None and page.count == 0


def test_consistency_counts_sessions_with_a_live_set(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    logged(engine, datetime(2026, 11, 2, 17, tzinfo=UTC), {squat: [("work", lift(5, "100"))]})
    logged(engine, datetime(2026, 11, 3, 8, tzinfo=UTC), {squat: [("work", lift(5, "100"))]})
    logged(engine, datetime(2026, 11, 3, 9, tzinfo=UTC), {})
    logged(engine, datetime(2026, 10, 27, 17, tzinfo=UTC), {squat: [("warmup", lift(5, "50"))]})
    found = history.consistency(engine, USER, "2026-11-04")
    assert len(found.weeks) == 12 and found.this_week == 2
    assert found.weeks[-2].count == 1  # a warm-up is a live set
    assert found.average_tenths == 3


# --- session delete


def test_deleting_a_session_removes_it_from_every_reader_but_keeps_it(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    seat = variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting"))
    exercises.add_field(engine, USER, squat, variable_id=seat)
    old = logged(engine, T0, {squat: [("work", lift(5, "100"))]}, settings={f"var_{seat}": "3"})
    best = logged(engine, T0 + DAY, {squat: [("work", lift(5, "140"))]}, settings={f"var_{seat}": "7"})
    before = progress.exercise_progress(engine, USER, squat)
    assert before.rm.rows[0].estimate_g == 163300 and before.last is not None
    sessions.delete_session(engine, USER, best, T0 + 2 * DAY)
    assert [item.id for g in history.history_page(engine, USER).months for item in g.items] == [old]
    assert sum(week.count for week in history.consistency(engine, USER, "2026-10-03").weeks) == 1
    after = progress.exercise_progress(engine, USER, squat)
    assert after.rm.rows[0].estimate_g == 116700
    assert after.last is not None and after.last.session.id == old
    assert dict(after.bests.by_reps)[5].value == 100000
    assert [p.value for p in after.series[0].points] == [116700]
    with pytest.raises(NotFoundError):
        sessions.show(engine, USER, best)
    with pytest.raises(NotFoundError):
        sessions.delete_session(engine, USER, best, T0 + 2 * DAY)
    nxt = sessions.start(engine, USER, None, "home", T0 + 3 * DAY, TZ)
    block = sessions.pick(engine, USER, nxt, None, squat).block
    assert block is not None
    assert block.form.texts["weight"] == "100" and block.settings[seat] == 3
    with engine.begin() as connection:
        stored = connection.execute(
            sa.select(s.session.c.deleted_at).where(s.session.c.id == best)
        ).scalar_one()
    assert stored is not None
    sessions.close(engine, USER, nxt, T0 + 4 * DAY)
    assert sessions.start_page(engine, USER).location == "home"
    assert [item.exercise.id for item in progress.progress_index(engine, USER)] == [squat]


def test_deleting_the_open_session_frees_the_start(migrated_engine: Engine) -> None:
    engine = migrated_engine
    current = sessions.start(engine, USER, None, "gym", T0, TZ)
    sessions.delete_session(engine, USER, current, T0)
    assert sessions.start_page(engine, USER).open is None
    assert sessions.start(engine, USER, None, "gym", T0 + MINUTE, TZ) != current


def test_delete_session_of_another_user_is_not_found(migrated_engine: Engine) -> None:
    other = sessions.start(migrated_engine, OTHER, None, "gym", T0, TZ)
    with pytest.raises(NotFoundError):
        sessions.delete_session(migrated_engine, USER, other, T0)


# --- corrections of a closed session


def test_correcting_a_closed_set_changes_the_indicators(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    first = logged(engine, T0, {squat: [("work", lift(5, "100"))]})
    closed = logged(engine, T0 + DAY, {squat: [("work", lift(5, "90")), ("work", lift(5, "95"))]})
    set_id = summary(engine, closed).rows[0].sets[0].id
    with pytest.raises(SessionError):
        sessions.update_set(engine, USER, set_id, "work", lift(5, "120"))
    answer = sessions.update_set(engine, USER, set_id, "work", lift(5, "120"), require_open=False)
    assert isinstance(answer, SummaryView)
    corrected = answer.rows[0]
    assert corrected.sets[0].record and corrected.volume.load_g == 1075000
    page = progress.exercise_progress(engine, USER, squat)
    assert page.rm.rows[0].estimate_g == 140000
    assert dict(page.bests.by_reps)[5].value == 120000
    assert [p.value for p in progress.chart_data(engine, USER, squat).series[0].points] == [116700, 140000]
    deleted = sessions.delete_set(engine, USER, set_id, T0 + 2 * DAY, require_open=False)
    assert isinstance(deleted, SummaryView) and len(deleted.rows[0].sets) == 1
    last = sessions.delete_set(engine, USER, deleted.rows[0].sets[0].id, T0 + 2 * DAY, require_open=False)
    assert isinstance(last, SummaryView) and last.rows[0].sets == () and last.row(last.rows[0].id) is not None
    assert summary(engine, closed).rows == ()
    assert progress.exercise_progress(engine, USER, squat).last.session.id == first  # type: ignore[union-attr]


def test_correcting_a_closed_setting(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    seat = variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting"))
    exercises.add_field(engine, USER, squat, variable_id=seat)
    closed = logged(engine, T0, {squat: [("work", lift(5, "100"))]}, settings={f"var_{seat}": "3"})
    row = summary(engine, closed).rows[0]
    assert row.settings == {seat: 3} and row.setting_fields and row.types == ("warmup", "work", "rm_test")
    with pytest.raises(SessionError):
        sessions.save_settings(engine, USER, closed, row.id, {f"var_{seat}": "5"})
    answer = sessions.save_settings(engine, USER, closed, row.id, {f"var_{seat}": "5"}, require_open=False)
    assert isinstance(answer, SummaryView) and answer.rows[0].settings == {seat: 5}
    assert sessions.detail(engine, USER, closed, row.id).rows[0].settings_texts == {f"var_{seat}": "5"}


def test_open_session_corrections_still_answer_the_block(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    current = logged(engine, T0, {squat: [("work", lift(5, "100"))]}, close=False)
    found = sessions.show(engine, USER, current)
    assert isinstance(found, SessionView) and found.block is not None
    answer = sessions.update_set(engine, USER, found.block.sets[0].id, "work", lift(5, "105"))
    assert isinstance(answer, SessionView)
    with pytest.raises(SessionError):
        sessions.detail(engine, USER, current)


# --- progress


def test_progress_page_of_each_category(migrated_engine: Engine) -> None:
    engine = migrated_engine
    run, swing = make(engine, "Run", "cardio"), make(engine, "Swing", "kettlebell")
    logged(engine, T0, {run: [("work", {"duration": "25:00", "distance": "5"})]})
    logged(engine, T0 + DAY, {swing: [("work", lift(15, "16")), ("work", lift(12, "24"))]})
    page = progress.exercise_progress(engine, USER, run)
    assert not page.rm.available and page.series[0].key == "distance"
    assert page.bests.singles["best_pace"].value == 300
    assert page.table.columns[0] == ("distance", "distance")
    bell = progress.exercise_progress(engine, USER, swing)
    assert [series.load_g for series in bell.series] == [16000, 24000]
    empty = progress.exercise_progress(engine, USER, make(engine, "Bench"))
    assert empty.last is None and empty.series == () and empty.rm.rows == () and empty.bests.empty
    with pytest.raises(NotFoundError):
        progress.exercise_progress(engine, USER, make(engine, "Theirs", user=OTHER))


def test_rm_entries_and_measured_wins(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    logged(engine, T0 + 10 * DAY, {squat: [("work", lift(5, "100")), ("rm_test", lift(3, "105"))]})
    saved = progress.add_measured_rm(
        engine, USER, squat, "1", "110", "2026-10-05", now=T0, today="2026-11-03"
    )
    assert saved.draft.weight_g == 110000
    one = saved.view.rows[0]
    assert one.measured is not None and one.shown_g == 110000 and one.estimate_g == 116700 and one.flagged
    assert [(row.n, row.measured.origin) for row in saved.view.rows if row.measured] == [
        (1, "manual"),
        (3, "rm_test"),
    ]
    measure = saved.view.measures[0]
    with pytest.raises(CatalogError):
        progress.add_measured_rm(engine, USER, squat, "13", "0", "2026-12-01", now=T0, today="2026-11-03")
    with pytest.raises(NotFoundError):
        progress.delete_measured_rm(engine, OTHER, measure.measured_id, T0)
    deleted = progress.delete_measured_rm(engine, USER, measure.measured_id, T0)
    after = deleted.view
    assert deleted.next_id is None
    assert after.measures == () and after.rows[0].measured is None
    with pytest.raises(NotFoundError):
        progress.delete_measured_rm(engine, USER, measure.measured_id, T0)
    with engine.begin() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(s.rm_measured)).scalar_one() == 1


def test_rm_refused_outside_strength_and_for_foreign_exercises(migrated_engine: Engine) -> None:
    engine = migrated_engine
    run = make(engine, "Run", "cardio")
    with pytest.raises(CatalogError) as error:
        progress.add_measured_rm(engine, USER, run, "1", "100", "2026-10-05", now=T0, today="2026-11-03")
    assert error.value.problems[0].code == "rm_not_strength"
    assert not progress.rm_view(engine, USER, run).available
    with pytest.raises(NotFoundError):
        progress.add_measured_rm(
            engine, USER, make(engine, "X", user=OTHER), "1", "1", "2026-10-05", now=T0, today="2026-11-03"
        )


def test_formula_setting_changes_estimates_only(migrated_engine: Engine) -> None:
    engine = migrated_engine
    squat = make(engine, "Squat")
    logged(engine, T0 + 10 * DAY, {squat: [("work", lift(10, "80"))]})
    progress.add_measured_rm(engine, USER, squat, "1", "100", "2026-10-01", now=T0, today="2026-11-03")
    assert progress.formula(engine, USER) == "epley"
    before = progress.rm_view(engine, USER, squat).rows[0]
    assert progress.set_formula(engine, USER, "lombardi") == "lombardi"
    after = progress.rm_view(engine, USER, squat).rows[0]
    assert after.measured == before.measured and after.estimate_g != before.estimate_g
    with pytest.raises(CatalogError):
        progress.set_formula(engine, USER, "magic")
    with engine.begin() as connection:
        app_settings.put(connection, USER, progress.RM_FORMULA_KEY, "future")
    assert progress.formula(engine, USER) == "epley"
    with engine.begin() as connection:
        assert app_settings.get(connection, USER, progress.RM_FORMULA_KEY) == "future"
