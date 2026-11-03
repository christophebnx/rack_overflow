"""Indicators computed from stored set facts, never stored themselves (D-021, D-033, D-064).

L4 uses the record rule (⭐) and the volume of a session; L5 adds the RM estimates and table
(D-069), the records and secondary indicators by category, the main series of the progress chart
(D-068) and the sessions per week (D-070). Only work and RM-test sets count; warm-ups never do.
Every value is a canonical integer (grams, seconds, metres, counts); display is `web/`'s.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

RECORD_TYPES: tuple[str, ...] = ("work", "rm_test")
"""Set types counted by records and volume."""
WORK = "work"
RM_TEST = "rm_test"
INTERVALS = "intervals"
CARDIO = "cardio"
STRENGTH = "strength"
KETTLEBELL = "kettlebell"
BODYWEIGHT = "bodyweight"


@dataclass(frozen=True)
class LoggedSet:
    """A live set as the indicators see it: type, core quantities (None when not set), the
    session it belongs to, the session's local date (`YYYY-MM-DD`, L5) and the set id (L5)."""

    type: str
    reps: int | None = None
    weight_g: int | None = None
    duration_s: int | None = None
    distance_m: int | None = None
    session_id: int = 0
    local_date: str = ""
    set_id: int = 0

    @property
    def counted(self) -> bool:
        """True for a work or RM-test set."""
        return self.type in RECORD_TYPES


def _quantities(item: LoggedSet) -> tuple[int, int, int, int]:
    return (item.reps or 0, item.weight_g or 0, item.duration_s or 0, item.distance_m or 0)


def _at_least_as_good(earlier: LoggedSet, candidate: LoggedSet, category: str) -> bool:
    """True when `earlier` dominates `candidate`: at least as good on every compared quantity."""
    if category != CARDIO:
        return all(e >= c for e, c in zip(_quantities(earlier), _quantities(candidate), strict=True))
    distance, duration = candidate.distance_m or 0, candidate.duration_s or 0
    e_distance, e_duration = earlier.distance_m or 0, earlier.duration_s or 0
    if distance and duration:
        faster = e_duration > 0 and e_distance * duration >= distance * e_duration
        return e_distance >= distance and faster
    if distance:
        return e_distance >= distance
    return e_duration >= duration


def _session_counts(sets: Iterable[LoggedSet]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for item in sets:
        if item.counted:
            counts[item.session_id] = counts.get(item.session_id, 0) + 1
    return counts


def is_record(category: str, candidate: LoggedSet, previous: Sequence[LoggedSet]) -> bool:
    """True when `candidate` is a record (D-064 and its 2026-11-03 refinement) given every
    earlier set of the exercise in `(completed_at, id)` order: a counted set, after at least one
    counted set of another session (never during the first session of the exercise), that no
    earlier counted set dominates, today's included (a tie is not a record). Intervals: the round
    that lifts its session's count of counted rounds above every earlier session's count."""
    if not candidate.counted:
        return False
    if category == INTERVALS:
        counts = _session_counts(previous)
        mine = counts.pop(candidate.session_id, 0) + 1
        return bool(counts) and mine == max(counts.values()) + 1
    earlier = [item for item in previous if item.counted]
    if not any(item.session_id != candidate.session_id for item in earlier):
        return False
    return not any(_at_least_as_good(item, candidate, category) for item in earlier)


def records(
    category: str, ordered_sets: Sequence[LoggedSet], wanted: Collection[int] | None = None
) -> set[int]:
    """Indexes of the records among `ordered_sets` (the exercise's history in `(completed_at,
    id)` order); only the indexes in `wanted` are checked when given (today's sets)."""
    indexes = range(len(ordered_sets)) if wanted is None else sorted(wanted)
    return {i for i in indexes if is_record(category, ordered_sets[i], ordered_sets[:i])}


@dataclass(frozen=True)
class Volume:
    """What a group of sets amounts to (counted sets only): Σ reps * load in grams, Σ reps,
    Σ durations, Σ distances, the number of counted sets (rounds of intervals)."""

    category: str
    load_g: int = 0
    reps: int = 0
    duration_s: int = 0
    distance_m: int = 0
    sets: int = 0


def volume(category: str, sets: Iterable[LoggedSet]) -> Volume:
    """The volume of `sets` for an exercise of `category` (D-064), warm-ups left out."""
    counted = [item for item in sets if item.counted]
    return Volume(
        category=category,
        load_g=sum((item.reps or 0) * (item.weight_g or 0) for item in counted),
        reps=sum(item.reps or 0 for item in counted),
        duration_s=sum(item.duration_s or 0 for item in counted),
        distance_m=sum(item.distance_m or 0 for item in counted),
        sets=len(counted),
    )


def round_count(sets: Iterable[LoggedSet]) -> int:
    """Number of counted rounds of an intervals exercise (L5's main intervals indicator)."""
    return sum(1 for item in sets if item.counted)


def _rounded_ratio(numerator: int, denominator: int) -> int:
    """`numerator / denominator` rounded half up, in integers (no float drift)."""
    return (numerator * 2 + denominator) // (denominator * 2)


# --- RM estimation (D-069)

RM_FORMULAS: tuple[str, ...] = ("epley", "brzycki", "lombardi", "oconner", "wathan")
"""The 1RM formulas, in the order the settings page lists them; stable keys (`app_setting`)."""
DEFAULT_FORMULA = "epley"
MAX_ESTIMATION_REPS = 12
ESTIMATE_STEP_G = 100
"""Estimates are rounded to 100 g, the precision shown, so comparisons and display agree."""
MANUAL = "manual"
"""Origin of a measured RM typed in the RM form (`rm_measured`); the other origin is `RM_TEST`."""

_RATIOS: dict[str, Callable[[int], float]] = {
    "epley": lambda reps: 1 + reps / 30,
    "brzycki": lambda reps: 36 / (37 - reps),
    "lombardi": lambda reps: float(reps**0.10),
    "oconner": lambda reps: 1 + reps / 40,
    "wathan": lambda reps: 100 / (48.8 + 53.8 * math.exp(-0.075 * reps)),
}
"""1RM / load for `reps` repetitions, per formula."""


def formula_of(stored: str | None) -> str:
    """The formula to use for a stored setting: absent or unknown → the default (Epley)."""
    return stored if stored in RM_FORMULAS else DEFAULT_FORMULA


def _ratio(formula: str, reps: int) -> float:
    """1RM / load for `reps` (1 to 12): a single is its own 1RM for every formula."""
    return 1.0 if reps == 1 else _RATIOS[formula_of(formula)](reps)


def _to_step(grams: float) -> int:
    return math.floor(grams / ESTIMATE_STEP_G + 0.5) * ESTIMATE_STEP_G


def estimable(item: LoggedSet) -> bool:
    """True for a set the estimate reads: a work set of 1 to 12 reps with a load (warm-ups, RM
    tests and sets above 12 reps never feed it)."""
    return (
        item.type == WORK
        and item.reps is not None
        and 1 <= item.reps <= MAX_ESTIMATION_REPS
        and (item.weight_g or 0) > 0
    )


def estimate_1rm(formula: str, reps: int, weight_g: int) -> int:
    """The estimated 1RM in grams of `reps` (1 to 12) times `weight_g`, rounded to 100 g."""
    return _to_step(weight_g * _ratio(formula, reps))


def load_for_reps(formula: str, one_rm_g: int, n: int) -> int:
    """The load in grams for `n` (1 to 12) repetitions at a 1RM of `one_rm_g`: the formula's exact
    inverse, rounded to 100 g."""
    return _to_step(one_rm_g / _ratio(formula, n))


@dataclass(frozen=True)
class Estimate:
    """The best estimated 1RM and the set it comes from."""

    value_g: int
    source: LoggedSet


def best_estimate(formula: str, sets: Iterable[LoggedSet]) -> Estimate | None:
    """The best e1RM over `sets` (history order), the latest set on a tie; None without an
    estimable set."""
    best: Estimate | None = None
    for item in sets:
        if not estimable(item):
            continue
        assert item.reps is not None and item.weight_g is not None
        value = estimate_1rm(formula, item.reps, item.weight_g)
        if best is None or value >= best.value_g:
            best = Estimate(value, item)
    return best


@dataclass(frozen=True)
class RmMeasure:
    """A measured nRM: a manual entry (`MANUAL`, `measured_id` = the `rm_measured` id) or an RM
    test set (`RM_TEST`, `measured_id` = the set id)."""

    n: int
    weight_g: int
    local_date: str
    origin: str
    measured_id: int


def rm_test_measures(sets: Iterable[LoggedSet]) -> list[RmMeasure]:
    """The measurements carried by RM-test sets (D-033, read directly): reps 1 to 12, a load."""
    return [
        RmMeasure(item.reps, item.weight_g, item.local_date, RM_TEST, item.set_id)
        for item in sets
        if item.type == RM_TEST
        and item.reps is not None
        and 1 <= item.reps <= MAX_ESTIMATION_REPS
        and item.weight_g
    ]


def latest_measures(measures: Iterable[RmMeasure]) -> dict[int, RmMeasure]:
    """For each n, the latest measurement (by date, the heavier on the same day)."""
    found: dict[int, RmMeasure] = {}
    for item in measures:
        known = found.get(item.n)
        if known is None or (item.local_date, item.weight_g) > (known.local_date, known.weight_g):
            found[item.n] = item
    return found


@dataclass(frozen=True)
class RmRow:
    """One row of the RM table: the measured value (None when none), the estimate for n and
    whether the estimate overtakes an older measurement (`flagged`)."""

    n: int
    measured: RmMeasure | None
    estimate_g: int | None
    estimate: Estimate | None
    flagged: bool = False

    @property
    def shown_g(self) -> int:
        """The value shown: a measured value wins (D-069)."""
        if self.measured is not None:
            return self.measured.weight_g
        assert self.estimate_g is not None
        return self.estimate_g


def rm_table(formula: str, measures: Iterable[RmMeasure], sets: Iterable[LoggedSet]) -> tuple[RmRow, ...]:
    """The RM table (D-069): 1RM, then each measured n ascending; empty with neither a
    measurement nor an estimable set. Flag: the estimate exceeds the measured value and its
    source set is later than the measurement."""
    latest = latest_measures(measures)
    best = best_estimate(formula, sets)
    if best is None and not latest:
        return ()
    rows: list[RmRow] = []
    for n in sorted({1, *latest}):
        measured = latest.get(n)
        estimate = load_for_reps(formula, best.value_g, n) if best is not None else None
        flagged = (
            measured is not None
            and best is not None
            and estimate is not None
            and estimate > measured.weight_g
            and best.source.local_date > measured.local_date
        )
        if measured is not None or estimate is not None:
            rows.append(RmRow(n, measured, estimate, best, flagged))
    return tuple(rows)


# --- records and secondary indicators (D-068)

REPS_13_PLUS = 13
"""Key of the « 13 et plus » row of the max load per rep count."""


@dataclass(frozen=True)
class Best:
    """A best value and where it was reached (first time on a tie)."""

    value: int
    session_id: int
    local_date: str


def _best_of(candidates: Iterable[Best], *, lowest: bool = False) -> Best | None:
    best: Best | None = None
    for item in candidates:
        if item.value <= 0:
            continue
        if best is None or (item.value < best.value if lowest else item.value > best.value):
            best = item
    return best


def _counted(sets: Iterable[LoggedSet]) -> list[LoggedSet]:
    return [item for item in sets if item.counted]


def _best_by_key(pairs: Iterable[tuple[int, int, LoggedSet]]) -> tuple[tuple[int, Best], ...]:
    """Per key, the largest value (the first set reaching it), keys ascending."""
    found: dict[int, Best] = {}
    for key, value, item in pairs:
        if key not in found or value > found[key].value:
            found[key] = Best(value, item.session_id, item.local_date)
    return tuple(sorted(found.items()))


def max_load_by_reps(sets: Iterable[LoggedSet]) -> tuple[tuple[int, Best], ...]:
    """Max load per rep count of the counted sets (1 to 12, then `REPS_13_PLUS`)."""
    return _best_by_key(
        (min(item.reps, REPS_13_PLUS), item.weight_g, item)
        for item in _counted(sets)
        if item.reps and item.weight_g
    )


def max_reps_by_load(sets: Iterable[LoggedSet]) -> tuple[tuple[int, Best], ...]:
    """Max reps in one counted set at each load, loads ascending."""
    return _best_by_key(
        (item.weight_g, item.reps, item) for item in _counted(sets) if item.reps and item.weight_g
    )


def pace_s_per_km(distance_m: int | None, duration_s: int | None) -> int | None:
    """Seconds per km of a set holding both a distance and a duration, else None."""
    if not distance_m or not duration_s:
        return None
    return _rounded_ratio(duration_s * 1000, distance_m)


def speed_m_per_h(distance_m: int | None, duration_s: int | None) -> int | None:
    """Metres per hour of a set holding both a distance and a duration, else None."""
    if not distance_m or not duration_s:
        return None
    return _rounded_ratio(distance_m * 3600, duration_s)


def density_reps_per_h(reps: int, duration_s: int) -> int | None:
    """Repetitions per hour (shown per minute) of `reps` done in `duration_s`, else None."""
    return _rounded_ratio(reps * 3600, duration_s) if reps and duration_s else None


def _per_set(sets: Sequence[LoggedSet], value: Callable[[LoggedSet], int | None]) -> list[Best]:
    found = [(value(item), item) for item in sets]
    return [Best(v, item.session_id, item.local_date) for v, item in found if v is not None]


def _per_session(sets: Sequence[LoggedSet], total: Callable[[list[LoggedSet]], int | None]) -> list[Best]:
    groups: dict[int, list[LoggedSet]] = {}
    for item in sets:
        groups.setdefault(item.session_id, []).append(item)
    found = [(total(group), group[0]) for group in groups.values()]
    return [Best(v, item.session_id, item.local_date) for v, item in found if v is not None]


def _session_density(group: list[LoggedSet]) -> int | None:
    timed = [item for item in group if item.reps and item.duration_s]
    reps = sum(item.reps or 0 for item in timed)
    return density_reps_per_h(reps, sum(item.duration_s or 0 for item in timed))


@dataclass(frozen=True)
class Bests:
    """Records of an exercise (D-068): max load per rep count (strength), max reps per load
    (kettlebell) and single bests by key, in display order; absent bests are left out."""

    category: str
    by_reps: tuple[tuple[int, Best], ...] = ()
    by_load: tuple[tuple[int, Best], ...] = ()
    singles: Mapping[str, Best] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        """True when there is no record at all."""
        return not (self.by_reps or self.by_load or self.singles)


def _session_load(group: list[LoggedSet]) -> int:
    return sum((item.reps or 0) * (item.weight_g or 0) for item in group)


def _singles(category: str, sets: Sequence[LoggedSet]) -> dict[str, Best | None]:
    load = _session_load
    if category == STRENGTH:
        return {"session_volume": _best_of(_per_session(sets, load))}
    if category == KETTLEBELL:
        return {
            "density": _best_of(_per_session(sets, _session_density)),
            "session_volume": _best_of(_per_session(sets, load)),
        }
    if category == BODYWEIGHT:
        return {
            "max_reps": _best_of(_per_set(sets, lambda i: i.reps)),
            "max_duration": _best_of(_per_set(sets, lambda i: i.duration_s)),
            "max_added_load": _best_of(_per_set(sets, lambda i: i.weight_g)),
            "session_reps": _best_of(_per_session(sets, lambda g: sum(i.reps or 0 for i in g))),
        }
    if category == CARDIO:
        return {
            "max_distance": _best_of(_per_set(sets, lambda i: i.distance_m)),
            "max_duration": _best_of(_per_set(sets, lambda i: i.duration_s)),
            "best_pace": _best_of(
                _per_set(sets, lambda i: pace_s_per_km(i.distance_m, i.duration_s)), lowest=True
            ),
            "best_speed": _best_of(_per_set(sets, lambda i: speed_m_per_h(i.distance_m, i.duration_s))),
        }
    return {
        "session_rounds": _best_of(_per_session(sets, len)),
        "session_work": _best_of(_per_session(sets, lambda g: sum(i.duration_s or 0 for i in g))),
    }


def bests(category: str, sets: Iterable[LoggedSet]) -> Bests:
    """The records of an exercise of `category` from its history (counted sets of live
    sessions, history order); warm-ups never count (D-064)."""
    counted = _counted(sets)
    singles = {key: value for key, value in _singles(category, counted).items() if value is not None}
    return Bests(
        category,
        by_reps=max_load_by_reps(counted) if category == STRENGTH else (),
        by_load=max_reps_by_load(counted) if category == KETTLEBELL else (),
        singles=singles,
    )


# --- main series of the progress chart (D-068)

LINE = "line"
POINTS = "points"
MAX_LOAD_SERIES = 6


@dataclass(frozen=True)
class Point:
    """One day of a series: the local date and a canonical integer."""

    local_date: str
    value: int


@dataclass(frozen=True)
class Series:
    """A chart series: its key (`e1rm`, `measured_1rm`, `load`, `max_reps`, `max_duration`,
    `distance`, `duration`, `rounds`), the value kind of its points (`weight`, `int`,
    `duration`, `distance`), the points by date, a line or points, the load of a `load` series."""

    key: str
    unit_kind: str
    points: tuple[Point, ...]
    kind: str = LINE
    load_g: int | None = None

    @property
    def best(self) -> int:
        """The largest value (every main indicator grows with progress)."""
        return max(point.value for point in self.points)


def _daily(
    sets: Iterable[LoggedSet], value: Callable[[LoggedSet], int | None], combine: Callable[[int, int], int]
) -> tuple[Point, ...]:
    """One point per local date: the day's values combined (max or sum), dates ascending."""
    days: dict[str, int] = {}
    for item in sets:
        found = value(item)
        if found is None:
            continue
        days[item.local_date] = combine(days[item.local_date], found) if item.local_date in days else found
    return tuple(Point(day, total) for day, total in sorted(days.items()))


def _add(first: int, second: int) -> int:
    return first + second


def _strength_series(sets: list[LoggedSet], formula: str, measures: Iterable[RmMeasure]) -> list[Series]:
    def e1rm(item: LoggedSet) -> int | None:
        if not estimable(item):
            return None
        assert item.reps is not None and item.weight_g is not None
        return estimate_1rm(formula, item.reps, item.weight_g)

    measured = [
        LoggedSet(RM_TEST, weight_g=m.weight_g, local_date=m.local_date) for m in measures if m.n == 1
    ]
    return [
        Series("e1rm", "weight", _daily(sets, e1rm, max)),
        Series("measured_1rm", "weight", _daily(measured, lambda i: i.weight_g, max), POINTS),
    ]


def _kettlebell_series(sets: list[LoggedSet]) -> list[Series]:
    loaded = [item for item in sets if item.reps and item.weight_g]
    uses: dict[int, int] = {}
    for item in loaded:
        assert item.weight_g is not None
        uses[item.weight_g] = uses.get(item.weight_g, 0) + 1
    top = sorted(sorted(uses, key=lambda load: (-uses[load], load))[:MAX_LOAD_SERIES])
    return [
        Series(
            "load",
            "int",
            _daily([i for i in loaded if i.weight_g == load], lambda i: i.reps, max),
            load_g=load,
        )
        for load in top
    ]


def main_series(
    category: str,
    sets: Iterable[LoggedSet],
    formula: str,
    quantities: Collection[str],
    measures: Iterable[RmMeasure] = (),
) -> tuple[Series, ...]:
    """The series of the progress chart of an exercise (D-068), one point per local date, the
    main one first; series without points are left out. `quantities` are the exercise's core
    quantities (`reps`, `weight`, `duration`, `distance`); `measures` the measured RMs (strength:
    the « 1RM mesuré » points). Cardio: Σ distance when the exercise has a distance field and its
    history holds one, else Σ duration (one unit per chart)."""
    counted = _counted(sets)
    if category == STRENGTH:
        found = _strength_series(counted, formula, measures)
    elif category == KETTLEBELL:
        found = _kettlebell_series(counted)
    elif category == BODYWEIGHT:
        if "reps" in quantities:
            found = [Series("max_reps", "int", _daily(counted, lambda i: i.reps, max))]
        else:
            found = [Series("max_duration", "duration", _daily(counted, lambda i: i.duration_s, max))]
    elif category == CARDIO:
        if "distance" in quantities and any(item.distance_m for item in counted):
            found = [Series("distance", "distance", _daily(counted, lambda i: i.distance_m, _add))]
        else:
            found = [Series("duration", "duration", _daily(counted, lambda i: i.duration_s, _add))]
    else:
        found = [Series("rounds", "int", _daily(counted, lambda i: 1, _add))]
    return tuple(series for series in found if series.points)


# --- data table of the chart, per day (D-068)

DURATION_TOTAL = "duration_total"
"""Column kind of a day's sum of durations (shown compact, « 30 min »), beside per-set kinds."""


@dataclass(frozen=True)
class DayRow:
    """One row of the chart's data table: the local date and one value per column (None: « — »)."""

    local_date: str
    values: tuple[int | None, ...]


@dataclass(frozen=True)
class DayTable:
    """The chart's data table: columns `(key, value kind)` after the date, rows newest first."""

    columns: tuple[tuple[str, str], ...]
    rows: tuple[DayRow, ...]


def _by_day(sets: Iterable[LoggedSet]) -> dict[str, list[LoggedSet]]:
    days: dict[str, list[LoggedSet]] = {}
    for item in sets:
        days.setdefault(item.local_date, []).append(item)
    return days


def _max_of(values: Iterable[int | None]) -> int | None:
    return max((value for value in values if value), default=None)


def _sum_of(values: Iterable[int | None]) -> int | None:
    return sum(value for value in values if value) or None


def _strength_rows(days: dict[str, list[LoggedSet]], formula: str, measures: Sequence[RmMeasure]) -> DayTable:
    measured = _by_day(LoggedSet(RM_TEST, weight_g=m.weight_g, local_date=m.local_date) for m in measures)
    columns = [("e1rm", "weight")] + ([("measured", "weight")] if measured else []) + [("volume", "weight")]
    rows = []
    for day in sorted(set(days) | set(measured), reverse=True):
        group = days.get(day, [])
        e1rm = _max_of(
            estimate_1rm(formula, item.reps or 0, item.weight_g or 0) for item in group if estimable(item)
        )
        values = [e1rm] + ([_max_of(i.weight_g for i in measured.get(day, []))] if measured else [])
        rows.append(DayRow(day, (*values, _session_load(group) or None)))
    return DayTable(tuple(columns), tuple(rows))


def _kettlebell_rows(days: dict[str, list[LoggedSet]]) -> DayTable:
    rows = []
    for day in sorted(days, reverse=True):
        loads = sorted({item.weight_g for item in days[day] if item.weight_g and item.reps})
        for load in loads:
            reps = _max_of(item.reps for item in days[day] if item.weight_g == load)
            rows.append(DayRow(day, (load, reps)))
    return DayTable((("load", "weight"), ("max_reps", "int")), tuple(rows))


def _cardio_columns(quantities: Collection[str]) -> tuple[tuple[str, str], ...]:
    if "distance" in quantities:
        return (("distance", "distance"), ("duration", DURATION_TOTAL), ("pace", "pace"))
    return (("duration", DURATION_TOTAL),)


def _cardio_values(group: list[LoggedSet], quantities: Collection[str]) -> tuple[int | None, ...]:
    duration = _sum_of(item.duration_s for item in group)
    if "distance" not in quantities:
        return (duration,)
    both = [item for item in group if item.distance_m and item.duration_s]
    pace = pace_s_per_km(
        sum(item.distance_m or 0 for item in both), sum(item.duration_s or 0 for item in both)
    )
    return (_sum_of(item.distance_m for item in group), duration, pace)


def day_table(
    category: str,
    sets: Iterable[LoggedSet],
    formula: str,
    quantities: Collection[str],
    measures: Sequence[RmMeasure] = (),
) -> DayTable:
    """The data table under the chart (docs/ui-spec.md "L5 — Progress of an exercise"), counted
    sets only: strength e1RM, measured 1RM (when any), volume; kettlebell max reps per day and
    load; bodyweight max and total reps (holds: max duration); cardio distance, duration and pace
    (distance field) or duration; intervals rounds and work."""
    days = _by_day(_counted(sets))
    if category == STRENGTH:
        return _strength_rows(days, formula, measures)
    if category == KETTLEBELL:
        return _kettlebell_rows(days)
    columns, values = _plain_columns(category, quantities)
    rows = (DayRow(day, values(days[day])) for day in sorted(days, reverse=True))
    return DayTable(columns, tuple(rows))


type _DayValues = Callable[[list[LoggedSet]], tuple[int | None, ...]]


def _reps_values(group: list[LoggedSet]) -> tuple[int | None, ...]:
    return (_max_of(item.reps for item in group), _sum_of(item.reps for item in group))


def _hold_values(group: list[LoggedSet]) -> tuple[int | None, ...]:
    return (_max_of(item.duration_s for item in group),)


def _interval_values(group: list[LoggedSet]) -> tuple[int | None, ...]:
    return (len(group), _sum_of(item.duration_s for item in group))


def _plain_columns(
    category: str, quantities: Collection[str]
) -> tuple[tuple[tuple[str, str], ...], _DayValues]:
    """Columns and per-day values of bodyweight, cardio and intervals."""
    if category == BODYWEIGHT and "reps" in quantities:
        return (("max_reps", "int"), ("total_reps", "int")), _reps_values
    if category == BODYWEIGHT:
        return (("max_duration", "duration"),), _hold_values
    if category == CARDIO:
        return _cardio_columns(quantities), lambda group: _cardio_values(group, quantities)
    return (("rounds", "int"), ("work", DURATION_TOTAL)), _interval_values


# --- consistency (D-070)

CONSISTENCY_WEEKS = 12


@dataclass(frozen=True)
class WeekCount:
    """Sessions of one ISO week (Monday `start`, `YYYY-MM-DD`)."""

    start: str
    count: int


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def sessions_per_week(
    local_dates: Iterable[str], today: str, weeks: int = CONSISTENCY_WEEKS
) -> tuple[WeekCount, ...]:
    """Sessions per ISO week (Monday first), oldest first, ending with the week of `today`;
    `local_dates` holds one date per session."""
    current = _monday(date.fromisoformat(today))
    counts: dict[date, int] = {}
    for text in local_dates:
        monday = _monday(date.fromisoformat(text))
        counts[monday] = counts.get(monday, 0) + 1
    starts = [current - timedelta(weeks=weeks - 1 - index) for index in range(weeks)]
    return tuple(WeekCount(start.isoformat(), counts.get(start, 0)) for start in starts)


def average_tenths(weeks: Sequence[WeekCount]) -> int:
    """The average sessions per week in tenths (2,8 → 28), rounded half up; 0 without weeks."""
    return _rounded_ratio(sum(week.count for week in weeks) * 10, len(weeks)) if weeks else 0
