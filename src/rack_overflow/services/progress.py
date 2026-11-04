"""Progress operations (D-068, D-069), one transaction each, `user_id`, `now` and `today` passed
in: the progression index, an exercise's progress (last performance, RM table, records, chart
series and data table), the measured RM entries and the 1RM formula setting. Every indicator is
computed by `domain/indicators` from stored facts on each read (invariant 9); nothing is cached.
Unknown or foreign ids raise `NotFoundError`; refused input raises `CatalogError`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import indicators
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.indicators import (
    MANUAL,
    STRENGTH,
    Bests,
    DayTable,
    LoggedSet,
    RmMeasure,
    RmRow,
    Series,
)
from rack_overflow.domain.progress import RmDraft, check_rm_exercise, formula_draft, rm_draft
from rack_overflow.domain.timestamps import to_text
from rack_overflow.services.sessions import (
    ExerciseInfo,
    FieldInfo,
    SessionInfo,
    SetView,
    exercise_fields,
    logged_set,
    session_info,
    set_views,
)
from rack_overflow.storage import app_settings, rm
from rack_overflow.storage import exercises as exercise_queries
from rack_overflow.storage import sessions as queries

RM_FORMULA_KEY = "rm.formula"


@dataclass(frozen=True)
class ProgressItem:
    """An exercise of the progression index."""

    exercise: ExerciseInfo
    last_date: str
    session_count: int


@dataclass(frozen=True)
class LastPerformance:
    """The live sets of the exercise's most recent non-deleted session holding one (D-062)."""

    session: SessionInfo
    sets: tuple[SetView, ...]


@dataclass(frozen=True)
class RmView:
    """The RM section of a strength exercise (D-069): the formula, the table rows and the live
    manual entries newest first; `available` is False for another category."""

    exercise_id: int
    available: bool
    formula: str
    rows: tuple[RmRow, ...]
    measures: tuple[RmMeasure, ...]


@dataclass(frozen=True)
class ProgressView:
    """The progress page of an exercise (D-068)."""

    exercise: ExerciseInfo
    fields: tuple[FieldInfo, ...]
    last: LastPerformance | None
    rm: RmView
    series: tuple[Series, ...]
    table: DayTable
    bests: Bests
    formula: str


@dataclass(frozen=True)
class ChartData:
    """What the chart's JSON route needs: the exercise's category, formula and series."""

    category: str
    formula: str
    series: tuple[Series, ...]


@dataclass(frozen=True)
class RmSaved:
    """A measured RM just stored, and the RM section after it."""

    view: RmView
    draft: RmDraft


@dataclass(frozen=True)
class _Facts:
    """One read of an exercise's facts inside a transaction."""

    exercise: ExerciseInfo
    fields: tuple[FieldInfo, ...]
    history: tuple[LoggedSet, ...]
    formula: str
    rm: RmView

    @property
    def quantities(self) -> set[str]:
        """The exercise's core quantities."""
        return {item.core_quantity for item in self.fields if item.core_quantity is not None}

    @property
    def measures(self) -> list[RmMeasure]:
        """Every measured RM: manual entries and RM-test sets (D-033)."""
        return [*self.rm.measures, *indicators.rm_test_measures(self.history)]


# --- formula


def _formula(connection: sa.Connection, user_id: int) -> str:
    return indicators.formula_of(app_settings.get(connection, user_id, RM_FORMULA_KEY))


def formula(engine: Engine, user_id: int) -> str:
    """The 1RM formula in use (absent or unknown stored value → Epley, D-069)."""
    with engine.begin() as connection:
        return _formula(connection, user_id)


def set_formula(engine: Engine, user_id: int, raw: str | None) -> str:
    """Store the chosen formula (`invalid_choice` otherwise) and return it; measured RMs are
    never touched, estimates follow on the next read."""
    chosen = formula_draft(raw)
    with engine.begin() as connection:
        app_settings.put(connection, user_id, RM_FORMULA_KEY, chosen)
    return chosen


# --- reading helpers


def _exercise(connection: sa.Connection, user_id: int, exercise_id: int) -> ExerciseInfo:
    row = exercise_queries.get(connection, user_id, exercise_id)
    if row is None:
        raise NotFoundError(f"no exercise {exercise_id}")
    return ExerciseInfo(row.id, row.name, row.category, row.equipment, row.archived_at is not None)


def _history(connection: sa.Connection, user_id: int, exercise_id: int) -> tuple[LoggedSet, ...]:
    rows = queries.record_history(connection, user_id, exercise_id)
    return tuple(logged_set(row, row.session_id, row.local_date) for row in rows)


def _manual(row: sa.Row) -> RmMeasure:
    return RmMeasure(row.n, row.weight_g, row.measured_on, MANUAL, row.id)


def _rm_view(
    connection: sa.Connection,
    user_id: int,
    exercise: ExerciseInfo,
    history: Sequence[LoggedSet],
    formula: str,
) -> RmView:
    if exercise.category != STRENGTH:
        return RmView(exercise.id, False, formula, (), ())
    manual = [_manual(row) for row in rm.measured_of(connection, user_id, exercise.id)]
    measures = [*manual, *indicators.rm_test_measures(history)]
    rows = indicators.rm_table(formula, measures, history)
    newest_first = sorted(manual, key=lambda item: (item.local_date, item.measured_id), reverse=True)
    return RmView(exercise.id, True, formula, rows, tuple(newest_first))


def _facts(connection: sa.Connection, user_id: int, exercise_id: int) -> _Facts:
    exercise = _exercise(connection, user_id, exercise_id)
    history = _history(connection, user_id, exercise_id)
    chosen = _formula(connection, user_id)
    fields = exercise_fields(connection, exercise_id)[0]
    return _Facts(exercise, fields, history, chosen, _rm_view(connection, user_id, exercise, history, chosen))


def _series(facts: _Facts) -> tuple[Series, ...]:
    category = facts.exercise.category
    return indicators.main_series(category, facts.history, facts.formula, facts.quantities, facts.measures)


def _last(connection: sa.Connection, user_id: int, exercise: ExerciseInfo) -> LastPerformance | None:
    rows = queries.last_performance(connection, user_id, exercise.id, None)
    if not rows:
        return None
    found = queries.get_session(connection, user_id, rows[0].session_id)
    assert found is not None
    return LastPerformance(session_info(connection, found), set_views(connection, user_id, exercise, rows))


# --- pages


def progress_index(engine: Engine, user_id: int) -> tuple[ProgressItem, ...]:
    """Exercises with a live set in a non-deleted session, most recent first (D-068)."""
    with engine.begin() as connection:
        rows = queries.exercises_with_history(connection, user_id)
    return tuple(
        ProgressItem(
            ExerciseInfo(row.id, row.name, row.category, None, row.archived_at is not None),
            row.last_date,
            row.session_count,
        )
        for row in rows
    )


def exercise_progress(engine: Engine, user_id: int, exercise_id: int) -> ProgressView:
    """The progress page of any exercise of the user, archived included (D-068)."""
    with engine.begin() as connection:
        facts = _facts(connection, user_id, exercise_id)
        last = _last(connection, user_id, facts.exercise)
    category = facts.exercise.category
    return ProgressView(
        exercise=facts.exercise,
        fields=facts.fields,
        last=last,
        rm=facts.rm,
        series=_series(facts),
        table=indicators.day_table(category, facts.history, facts.formula, facts.quantities, facts.measures),
        bests=indicators.bests(category, facts.history),
        formula=facts.formula,
    )


def chart_data(engine: Engine, user_id: int, exercise_id: int) -> ChartData:
    """The series of the exercise's chart (the JSON route, D-068)."""
    with engine.begin() as connection:
        facts = _facts(connection, user_id, exercise_id)
    return ChartData(facts.exercise.category, facts.formula, _series(facts))


# --- RM entries


def rm_view(engine: Engine, user_id: int, exercise_id: int) -> RmView:
    """The RM section of the exercise as stored."""
    with engine.begin() as connection:
        return _facts(connection, user_id, exercise_id).rm


def add_measured_rm(
    engine: Engine,
    user_id: int,
    exercise_id: int,
    raw_n: str | None,
    raw_weight: str | None,
    raw_date: str | None,
    *,
    now: datetime,
    today: str,
) -> RmSaved:
    """Store a measured nRM typed in the RM form (D-069): strength only (`rm_not_strength`),
    `domain.progress.rm_draft` rules; `created_at = now`."""
    with engine.begin() as connection:
        exercise = _exercise(connection, user_id, exercise_id)
        check_rm_exercise(exercise.category)
        draft = rm_draft(raw_n, raw_weight, raw_date, today)
        rm.insert_measured(
            connection,
            user_id,
            exercise_id,
            n=draft.n,
            weight_g=draft.weight_g,
            measured_on=draft.measured_on,
            created_at=to_text(now),
        )
        return RmSaved(_facts(connection, user_id, exercise_id).rm, draft)


@dataclass(frozen=True)
class RmDeleted:
    """The RM section after a manual entry was deleted, and the entry listed after it (newest
    first; None when it was the last)."""

    view: RmView
    next_id: int | None


def delete_measured_rm(engine: Engine, user_id: int, measured_id: int, now: datetime) -> RmDeleted:
    """Soft delete a live manual RM entry of the user; the RM section of its exercise."""
    with engine.begin() as connection:
        found = rm.get_measured(connection, user_id, measured_id)
        if found is None:
            raise NotFoundError(f"no measured RM {measured_id}")
        listed = [item.measured_id for item in _facts(connection, user_id, found.exercise_id).rm.measures]
        position = listed.index(measured_id)
        rm.soft_delete_measured(connection, measured_id, to_text(now))
        following = listed[position + 1] if position + 1 < len(listed) else None
        return RmDeleted(_facts(connection, user_id, found.exercise_id).rm, following)
