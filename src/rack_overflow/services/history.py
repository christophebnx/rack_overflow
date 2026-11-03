"""History operations (D-067, D-070), one transaction each, `user_id` and `today` passed in: the
keyset pages of non-deleted sessions grouped by month, and the sessions per week. Volumes and
counts come from `domain/indicators` (the one place); queries from `storage/sessions`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.indicators import (
    CONSISTENCY_WEEKS,
    WeekCount,
    average_tenths,
    sessions_per_week,
    volume,
)
from rack_overflow.domain.progress import month_key
from rack_overflow.services.sessions import logged_set
from rack_overflow.storage import sessions as queries

PAGE_SIZE = 20


@dataclass(frozen=True)
class HistoryItem:
    """One session of the history list: when and where, its template name (None: free session),
    whether it is still open, the exercises holding a live set, counted sets and load volume."""

    id: int
    local_date: str
    started_at: str
    time_zone: str
    title: str | None
    location: str
    open: bool
    exercises: tuple[str, ...]
    sets: int
    load_g: int


@dataclass(frozen=True)
class MonthGroup:
    """The sessions of one month (`YYYY-MM`), newest first."""

    key: str
    items: tuple[HistoryItem, ...]


@dataclass(frozen=True)
class HistoryPage:
    """One page of history: month groups, whether its first month continues the previous page's
    last one, the id to load the next page after (None on the last page)."""

    months: tuple[MonthGroup, ...]
    continues_month: bool
    next_before: int | None

    @property
    def count(self) -> int:
        """Number of sessions on the page."""
        return sum(len(group.items) for group in self.months)


@dataclass(frozen=True)
class Consistency:
    """Sessions per ISO week, oldest first (the last is the current week), and the average in
    tenths (2,8 → 28)."""

    weeks: tuple[WeekCount, ...]
    average_tenths: int

    @property
    def this_week(self) -> int:
        """Sessions of the current week."""
        return self.weeks[-1].count


def _item(row: sa.Row, sets: Sequence[sa.Row]) -> HistoryItem:
    names: list[str] = []
    counted = load = 0
    by_exercise: dict[int, list[sa.Row]] = {}
    for entry in sets:
        by_exercise.setdefault(entry.exercise_id, []).append(entry)
        if entry.exercise_name not in names:
            names.append(entry.exercise_name)
    for entries in by_exercise.values():
        found = volume(entries[0].category, [logged_set(entry, row.id) for entry in entries])
        counted, load = counted + found.sets, load + found.load_g
    return HistoryItem(
        row.id,
        row.local_date,
        row.started_at,
        row.time_zone,
        row.template_name,
        row.location,
        row.status == "open",
        tuple(names),
        counted,
        load,
    )


def _months(items: Sequence[HistoryItem]) -> tuple[MonthGroup, ...]:
    groups: dict[str, list[HistoryItem]] = {}
    for item in items:
        groups.setdefault(month_key(item.local_date), []).append(item)
    return tuple(MonthGroup(key, tuple(found)) for key, found in groups.items())


def history_page(engine: Engine, user_id: int, before_id: int | None = None) -> HistoryPage:
    """The non-deleted sessions newest first, `PAGE_SIZE` per page after `before_id` (D-067)."""
    with engine.begin() as connection:
        rows = queries.history_page(connection, user_id, before_id, PAGE_SIZE + 1)
        shown = rows[:PAGE_SIZE]
        by_session: dict[int, list[sa.Row]] = {row.id: [] for row in shown}
        for entry in queries.sets_for_sessions(connection, list(by_session)):
            by_session[entry.session_id].append(entry)
        anchor = queries.get_session(connection, user_id, before_id) if before_id is not None else None
    items = [_item(row, by_session[row.id]) for row in shown]
    months = _months(items)
    continues = anchor is not None and bool(months) and months[0].key == month_key(anchor.local_date)
    return HistoryPage(months, continues, shown[-1].id if len(rows) > PAGE_SIZE else None)


def consistency(engine: Engine, user_id: int, today: str) -> Consistency:
    """Sessions per week over the last 12 ISO weeks ending with the week of `today` (D-070):
    non-deleted sessions holding a live set, by local date."""
    since = (date.fromisoformat(today) - timedelta(weeks=CONSISTENCY_WEEKS)).isoformat()
    with engine.begin() as connection:
        dates = queries.session_dates(connection, user_id, since)
    weeks = sessions_per_week(dates, today)
    return Consistency(weeks, average_tenths(weeks))
