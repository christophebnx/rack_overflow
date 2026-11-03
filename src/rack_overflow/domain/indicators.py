"""Indicators computed from stored set facts, never stored themselves (D-021, D-033, D-064).

L4 uses the record rule (⭐) and the volume of a session; L5 extends this module (e1RM, max load
per rep count, history indicators). Only work and RM-test sets count; warm-ups never do.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

RECORD_TYPES: tuple[str, ...] = ("work", "rm_test")
"""Set types counted by records and volume."""
INTERVALS = "intervals"
CARDIO = "cardio"


@dataclass(frozen=True)
class LoggedSet:
    """A live set as the indicators see it: type, core quantities (None when not set) and the
    session it belongs to."""

    type: str
    reps: int | None = None
    weight_g: int | None = None
    duration_s: int | None = None
    distance_m: int | None = None
    session_id: int = 0

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
