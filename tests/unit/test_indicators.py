"""Unit tests of `domain/indicators` (D-064)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from rack_overflow.domain.indicators import (
    RECORD_TYPES,
    LoggedSet,
    Volume,
    is_record,
    records,
    round_count,
    volume,
)


def lift(reps: int, kg: float, kind: str = "work", session: int = 1) -> LoggedSet:
    return LoggedSet(kind, reps=reps, weight_g=int(kg * 1000), session_id=session)


def run(minutes: int, metres: int | None, session: int = 1) -> LoggedSet:
    return LoggedSet("work", duration_s=minutes * 60, distance_m=metres, session_id=session)


def before(*items: LoggedSet) -> list[LoggedSet]:
    """`items` as sets of an earlier session (D-064 refinement: no star in the first session)."""
    return [replace(item, session_id=-1) for item in items]


def test_record_types() -> None:
    assert RECORD_TYPES == ("work", "rm_test")
    assert lift(1, 1).counted and lift(1, 1, "rm_test").counted and not lift(1, 1, "warmup").counted


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (lift(8, 62.5), True),  # heavier at the same reps
        (lift(9, 60), True),  # more reps at the same load
        (lift(8, 60), False),  # tie
        (lift(7, 60), False),  # dominated
        (lift(3, 100), True),  # heavier, fewer reps: not dominated
        (lift(8, 62.5, "warmup"), False),  # warm-ups never count
        (lift(8, 62.5, "rm_test"), True),
    ],
)
def test_strength_records(candidate: LoggedSet, expected: bool) -> None:
    previous = before(lift(8, 60), lift(5, 80), lift(12, 70, "warmup"))
    assert is_record("strength", candidate, previous) is expected


def test_first_counted_set_is_never_a_record() -> None:
    assert not is_record("strength", lift(8, 60), [])
    assert not is_record("strength", lift(8, 60), [lift(10, 100, "warmup")])


def test_no_record_during_the_first_session_of_an_exercise() -> None:
    first = [lift(8, 60), lift(8, 70)]
    assert records("strength", first) == set()  # heavier later in the very first session
    assert records("intervals", rounds(1, 3)) == set()


def test_dominance_includes_today_once_an_earlier_session_exists() -> None:
    history = [*before(lift(8, 60)), lift(8, 70), lift(8, 65), lift(8, 72.5)]
    assert records("strength", history) == {1, 3}  # today's 70 kg set dominates the 65 kg one


def test_bodyweight_and_holds() -> None:
    plank = before(LoggedSet("work", duration_s=45))
    assert is_record("bodyweight", LoggedSet("work", duration_s=50), plank)
    assert not is_record("bodyweight", LoggedSet("work", duration_s=45), plank)
    dips = before(LoggedSet("work", reps=10))
    assert is_record("bodyweight", LoggedSet("work", reps=8, weight_g=5000), dips)
    assert is_record("kettlebell", lift(10, 24), before(lift(12, 20)))


def test_cardio_distance_and_speed() -> None:
    previous = before(run(30, 5000))
    assert is_record("cardio", run(30, 5200), previous)  # farther and faster
    assert is_record("cardio", run(35, 5100), previous)  # farther, slower: not dominated
    assert is_record("cardio", run(20, 4000), previous)  # shorter, faster: not dominated
    assert not is_record("cardio", run(30, 5000), previous)  # tie
    assert not is_record("cardio", run(40, 4000), previous)  # shorter and slower


def test_cardio_single_quantity() -> None:
    assert is_record("cardio", run(40, None), before(run(30, None)))
    assert is_record("cardio", LoggedSet("work", distance_m=6000), before(LoggedSet("work", distance_m=5000)))
    assert not is_record(
        "cardio", LoggedSet("work", distance_m=5000), before(LoggedSet("work", distance_m=5000))
    )
    # earlier set without duration has no speed: a timed run of the same distance is a record
    assert is_record("cardio", run(30, 5000), before(LoggedSet("work", distance_m=5000)))


def rounds(session: int, count: int, kind: str = "work") -> list[LoggedSet]:
    return [LoggedSet(kind, duration_s=30, session_id=session) for _ in range(count)]


def test_intervals_record_is_the_round_beating_every_earlier_session() -> None:
    history = rounds(1, 8) + rounds(2, 6) + rounds(3, 9)
    stars = records("intervals", history)
    assert stars == {22}  # the 9th round of session 3
    assert not is_record("intervals", LoggedSet("work", duration_s=30, session_id=1), [])


def test_intervals_warm_up_rounds_do_not_count() -> None:
    history = rounds(1, 2) + rounds(2, 2, "warmup") + rounds(2, 3)
    assert records("intervals", history) == {6}


def test_records_checks_only_the_wanted_indexes() -> None:
    history = [lift(8, 60, session=1), lift(8, 62.5, session=2), lift(8, 65, session=3)]
    assert records("strength", history) == {1, 2}
    assert records("strength", history, wanted={2}) == {2}
    assert records("strength", history, wanted=set()) == set()


def test_editing_an_earlier_set_changes_later_stars() -> None:
    history = [*before(lift(8, 60)), lift(8, 62.5)]
    assert records("strength", history) == {1}
    history[0] = before(lift(8, 70))[0]
    assert records("strength", history) == set()


def test_volume_per_category() -> None:
    sets = [lift(10, 40, "warmup"), lift(8, 60), lift(8, 62.5), lift(3, 100, "rm_test")]
    assert volume("strength", sets) == Volume(
        "strength", load_g=8 * 60000 + 8 * 62500 + 300000, reps=19, sets=3
    )
    weighted = [LoggedSet("work", reps=10), LoggedSet("work", reps=8, weight_g=10000)]
    assert volume("bodyweight", weighted) == Volume("bodyweight", load_g=80000, reps=18, sets=2)
    assert volume("cardio", [run(30, 5200)]) == Volume("cardio", duration_s=1800, distance_m=5200, sets=1)
    assert volume("intervals", rounds(1, 8) + rounds(1, 2, "warmup")).duration_s == 240
    assert volume("strength", []) == Volume("strength")


def test_round_count() -> None:
    assert round_count(rounds(1, 8) + rounds(1, 2, "warmup")) == 8


# --- edge cases (tester)


def test_intervals_equal_round_count_is_not_a_record() -> None:
    history = rounds(1, 4) + rounds(2, 4)
    assert records("intervals", history) == set()
    assert records("intervals", history + rounds(2, 1)) == {8}  # the 5th round of session 2


def test_intervals_first_session_has_no_record() -> None:
    assert records("intervals", rounds(1, 10)) == set()


def test_rm_test_and_work_sets_compare_with_each_other() -> None:
    assert not is_record("strength", lift(1, 100), before(lift(1, 100, "rm_test")))
    assert is_record("strength", lift(1, 102.5, "rm_test"), before(lift(1, 100)))


def test_missing_quantities_read_as_zero() -> None:
    # a hold with added load against an unloaded hold: more load, same duration
    hold = before(LoggedSet("work", duration_s=60))[0]
    assert is_record("bodyweight", LoggedSet("work", duration_s=60, weight_g=5000), [hold])
    assert not is_record("bodyweight", LoggedSet("work", duration_s=30), [hold])


def test_cardio_duration_only_against_a_timed_distance() -> None:
    assert not is_record("cardio", LoggedSet("work", duration_s=1800), before(run(30, 5000)))
    assert is_record("cardio", LoggedSet("work", duration_s=1860), before(run(30, 5000)))


def test_volume_ignores_warm_ups_and_empty_values() -> None:
    assert volume("kettlebell", [LoggedSet("warmup", reps=10, weight_g=16000)]) == Volume("kettlebell")
    assert volume(
        "bodyweight", [LoggedSet("work", duration_s=45), LoggedSet("work", duration_s=50)]
    ) == Volume("bodyweight", duration_s=95, sets=2)
