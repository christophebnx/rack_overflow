"""Unit tests of the L5 part of `domain/indicators` (D-068 to D-070): RM estimation and table,
records by category, chart series, pace / speed / density and sessions per week."""

from __future__ import annotations

import pytest

from rack_overflow.domain.indicators import (
    DEFAULT_FORMULA,
    ESTIMATE_STEP_G,
    MANUAL,
    REPS_13_PLUS,
    RM_FORMULAS,
    Best,
    LoggedSet,
    RmMeasure,
    WeekCount,
    average_tenths,
    best_estimate,
    bests,
    density_reps_per_h,
    estimable,
    estimate_1rm,
    formula_of,
    latest_measures,
    load_for_reps,
    main_series,
    max_load_by_reps,
    max_reps_by_load,
    pace_s_per_km,
    rm_table,
    rm_test_measures,
    sessions_per_week,
    speed_m_per_h,
)


def lift(
    reps: int, kg: float, day: str = "2026-10-01", kind: str = "work", session: int = 1, set_id: int = 0
) -> LoggedSet:
    return LoggedSet(
        kind, reps=reps, weight_g=round(kg * 1000), session_id=session, local_date=day, set_id=set_id
    )


def run(seconds: int, metres: int | None, day: str = "2026-10-01", session: int = 1) -> LoggedSet:
    return LoggedSet("work", duration_s=seconds, distance_m=metres, session_id=session, local_date=day)


# --- formulas


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("epley", [100000, 116700, 133300, 140000]),
        ("brzycki", [100000, 112500, 133300, 144000]),
        ("lombardi", [100000, 117500, 125900, 128200]),
        ("oconner", [100000, 112500, 125000, 130000]),
        ("wathan", [100000, 116600, 134700, 141500]),
    ],
)
def test_estimate_1rm_reference_values(formula: str, expected: list[int]) -> None:
    assert [estimate_1rm(formula, reps, 100000) for reps in (1, 5, 10, 12)] == expected


@pytest.mark.parametrize("formula", RM_FORMULAS)
def test_a_single_is_its_own_1rm_and_inverse_round_trips(formula: str) -> None:
    assert estimate_1rm(formula, 1, 102500) == 102500
    assert load_for_reps(formula, 102500, 1) == 102500
    for reps in (3, 5, 8, 12):
        one_rm = estimate_1rm(formula, reps, 80000)
        assert abs(load_for_reps(formula, one_rm, reps) - 80000) <= ESTIMATE_STEP_G


def test_estimates_are_rounded_to_100_g() -> None:
    assert estimate_1rm("epley", 5, 92500) == 107900  # 107 916,7 g
    assert estimate_1rm("epley", 3, 60000) % ESTIMATE_STEP_G == 0
    assert load_for_reps("epley", 116700, 5) == 100000


def test_formula_of() -> None:
    assert formula_of(None) == DEFAULT_FORMULA == "epley"
    assert formula_of("future") == "epley"
    assert formula_of("wathan") == "wathan"


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (lift(5, 100), True),
        (lift(12, 50), True),
        (lift(13, 50), False),
        (lift(0, 50), False),
        (lift(5, 0), False),
        (LoggedSet("work", reps=5), False),
        (lift(5, 100, kind="warmup"), False),
        (lift(1, 100, kind="rm_test"), False),
    ],
)
def test_estimable(item: LoggedSet, expected: bool) -> None:
    assert estimable(item) is expected


def test_best_estimate_keeps_its_source_and_ignores_excluded_sets() -> None:
    sets = [
        lift(5, 100, "2026-09-01", set_id=1),
        lift(15, 100, "2026-09-02", set_id=2),
        lift(1, 150, "2026-09-03", kind="rm_test", set_id=3),
        lift(3, 140, "2026-09-04", kind="warmup", set_id=4),
        lift(1, 116.7, "2026-09-05", set_id=5),
    ]
    best = best_estimate("epley", sets)
    assert best is not None
    assert best.value_g == 116700
    assert best.source.set_id == 5  # a tie keeps the latest set
    assert best_estimate("epley", sets[1:4]) is None


# --- measured RM and table


def manual(n: int, kg: float, day: str, measured_id: int = 1) -> RmMeasure:
    return RmMeasure(n, round(kg * 1000), day, MANUAL, measured_id)


def test_rm_test_measures_read_rm_test_sets_directly() -> None:
    sets = [
        lift(1, 110, "2026-10-12", kind="rm_test", set_id=7),
        lift(1, 120, "2026-10-13"),
        lift(15, 50, kind="rm_test"),
    ]
    assert rm_test_measures(sets) == [RmMeasure(1, 110000, "2026-10-12", "rm_test", 7)]


def test_latest_measure_per_n_by_date_then_heavier() -> None:
    found = latest_measures(
        [
            manual(1, 120, "2026-09-01"),
            manual(1, 100, "2026-10-01"),
            manual(1, 105, "2026-10-01"),
            manual(5, 90, "2026-08-01"),
        ]
    )
    assert found[1].weight_g == 105000
    assert found[5].weight_g == 90000


def test_rm_table_empty_without_facts() -> None:
    assert rm_table("epley", [], [lift(15, 50)]) == ()


def test_rm_table_estimate_only() -> None:
    rows = rm_table("epley", [], [lift(5, 100, "2026-10-28")])
    assert [(row.n, row.measured, row.estimate_g, row.flagged) for row in rows] == [(1, None, 116700, False)]
    assert rows[0].shown_g == 116700


def test_measured_wins_and_an_older_test_is_flagged() -> None:
    measures = [manual(1, 105, "2026-10-12"), manual(5, 92.5, "2026-10-01", 2)]
    rows = rm_table("epley", measures, [lift(5, 95, "2026-10-28")])
    one, five = rows
    assert (one.n, one.shown_g, one.estimate_g, one.flagged) == (1, 105000, 110800, True)
    assert (five.n, five.shown_g, five.estimate_g) == (5, 92500, 95000)
    assert five.flagged


def test_an_estimate_above_a_newer_test_is_not_flagged() -> None:
    rows = rm_table("epley", [manual(1, 105, "2026-11-01")], [lift(5, 100, "2026-10-28")])
    assert rows[0].shown_g == 105000 and rows[0].estimate_g == 116700 and not rows[0].flagged


def test_same_day_estimate_is_not_later() -> None:
    rows = rm_table("epley", [manual(1, 100, "2026-10-28")], [lift(5, 100, "2026-10-28")])
    assert not rows[0].flagged


def test_formula_change_changes_estimates_only() -> None:
    measures = [manual(1, 105, "2026-10-12")]
    sets = [lift(10, 80, "2026-10-28")]
    epley, lombardi = rm_table("epley", measures, sets)[0], rm_table("lombardi", measures, sets)[0]
    assert epley.measured == lombardi.measured
    assert epley.estimate_g != lombardi.estimate_g


def test_rm_table_with_measures_and_no_estimate() -> None:
    rows = rm_table("epley", [manual(3, 100, "2026-10-12")], [])
    assert [(row.n, row.estimate_g) for row in rows] == [(3, None)]


# --- records


def test_max_load_by_reps_with_13_plus() -> None:
    sets = [
        lift(5, 100, "2026-10-01"),
        lift(5, 100, "2026-10-02", session=2),
        lift(5, 90),
        lift(15, 40),
        lift(20, 45),
        lift(5, 60, kind="warmup"),
    ]
    found = dict(max_load_by_reps(sets))
    assert found[5] == Best(100000, 1, "2026-10-01")
    assert found[REPS_13_PLUS].value == 45000
    assert set(found) == {5, REPS_13_PLUS}


def test_max_reps_by_load() -> None:
    sets = [lift(10, 16), lift(15, 16, "2026-10-02", session=2), lift(8, 24)]
    assert [(load, best.value) for load, best in max_reps_by_load(sets)] == [(16000, 15), (24000, 8)]


def test_strength_bests() -> None:
    found = bests(
        "strength", [lift(5, 100, session=1), lift(5, 100, session=1), lift(3, 120, "2026-10-02", session=2)]
    )
    assert found.singles["session_volume"] == Best(1000000, 1, "2026-10-01")
    assert dict(found.by_reps)[3].value == 120000
    assert not found.by_load


def test_kettlebell_bests_density_only_with_durations() -> None:
    plain = bests("kettlebell", [lift(10, 16)])
    assert "density" not in plain.singles and plain.by_load
    timed = bests(
        "kettlebell",
        [LoggedSet("work", reps=30, weight_g=16000, duration_s=120, session_id=1, local_date="2026-10-01")],
    )
    assert timed.singles["density"].value == 900  # 15 reps / min


def test_bodyweight_bests() -> None:
    sets = [
        LoggedSet("work", reps=12, session_id=1, local_date="2026-10-01"),
        LoggedSet("work", reps=10, weight_g=10000, session_id=1, local_date="2026-10-01"),
        LoggedSet("work", duration_s=60, session_id=2, local_date="2026-10-02"),
        LoggedSet("warmup", reps=40, session_id=2, local_date="2026-10-02"),
    ]
    found = bests("bodyweight", sets)
    assert {k: v.value for k, v in found.singles.items()} == {
        "max_reps": 12,
        "max_duration": 60,
        "max_added_load": 10000,
        "session_reps": 22,
    }


def test_cardio_bests_pace_and_speed_only_with_both() -> None:
    found = bests(
        "cardio", [run(1800, 5000), run(2400, None, "2026-10-02", 2), run(1500, 5000, "2026-10-03", 3)]
    )
    values = {k: v.value for k, v in found.singles.items()}
    assert values == {"max_distance": 5000, "max_duration": 2400, "best_pace": 300, "best_speed": 12000}
    assert found.singles["best_pace"].local_date == "2026-10-03"
    assert "best_pace" not in bests("cardio", [run(1800, None)]).singles


def test_intervals_bests_per_session() -> None:
    sets = [run(30, None, session=1), run(30, None, session=1), run(40, None, "2026-10-02", 2)]
    values = {k: v.value for k, v in bests("intervals", sets).singles.items()}
    assert values == {"session_rounds": 2, "session_work": 60}


def test_no_records() -> None:
    assert bests("strength", [lift(5, 50, kind="warmup")]).empty


def test_pace_speed_density() -> None:
    assert pace_s_per_km(5000, 1600) == 320
    assert speed_m_per_h(5000, 1600) == 11250
    assert pace_s_per_km(None, 100) is None and speed_m_per_h(100, 0) is None
    assert density_reps_per_h(25, 120) == 750 and density_reps_per_h(0, 10) is None


# --- series


def test_strength_series_best_e1rm_per_day_and_measured_points() -> None:
    sets = [
        lift(5, 100, "2026-10-01"),
        lift(5, 90, "2026-10-01"),
        lift(5, 60, "2026-10-02", kind="warmup"),
        lift(1, 120, "2026-10-03", kind="rm_test"),
    ]
    series = main_series(
        "strength",
        sets,
        "epley",
        {"reps", "weight"},
        [manual(1, 110, "2026-10-05"), manual(3, 100, "2026-10-05")],
    )
    e1rm, measured = series
    assert e1rm.key == "e1rm" and [(p.local_date, p.value) for p in e1rm.points] == [("2026-10-01", 116700)]
    assert measured.kind == "points" and measured.points[0].value == 110000
    assert e1rm.best == 116700
    assert len(main_series("strength", sets, "epley", {"reps", "weight"})) == 1


def test_kettlebell_series_per_load_capped_at_six() -> None:
    sets = [lift(10 + i, 4 * (i + 1), f"2026-10-{i + 1:02d}") for i in range(8)] + [lift(5, 4, "2026-10-20")]
    series = main_series("kettlebell", sets, "epley", {"reps", "weight"})
    assert len(series) == 6
    assert [s.load_g for s in series] == sorted(s.load_g or 0 for s in series)
    assert series[0].load_g == 4000 and [p.value for p in series[0].points] == [10, 5]


def test_bodyweight_series_reps_else_duration() -> None:
    sets = [
        LoggedSet("work", reps=10, duration_s=30, local_date="2026-10-01"),
        LoggedSet("work", reps=12, duration_s=20, local_date="2026-10-01"),
    ]
    assert main_series("bodyweight", sets, "epley", {"reps"})[0].points[0].value == 12
    holds = main_series("bodyweight", sets, "epley", {"duration"})[0]
    assert holds.key == "max_duration" and holds.points[0].value == 30


def test_cardio_series_distance_sum_else_duration() -> None:
    sets = [run(600, 2000), run(900, 3000), run(1200, None, "2026-10-02")]
    distance = main_series("cardio", sets, "epley", {"duration", "distance"})[0]
    assert distance.key == "distance" and [p.value for p in distance.points] == [5000]
    duration = main_series("cardio", sets, "epley", {"duration"})[0]
    assert duration.key == "duration" and [p.value for p in duration.points] == [1500, 1200]


def test_intervals_series_counts_rounds() -> None:
    sets = [run(30, None), run(30, None), LoggedSet("warmup", duration_s=30, local_date="2026-10-01")]
    assert main_series("intervals", sets, "epley", {"duration"})[0].points[0].value == 2


def test_no_series_without_counted_sets() -> None:
    assert main_series("cardio", [], "epley", {"duration"}) == ()


# --- consistency


def test_sessions_per_week_monday_weeks_oldest_first() -> None:
    weeks = sessions_per_week(
        ["2026-11-02", "2026-11-04", "2026-11-01", "2026-08-01", "2026-08-17"], "2026-11-05"
    )
    assert len(weeks) == 12
    assert weeks[-1] == WeekCount("2026-11-02", 2)
    assert weeks[-2] == WeekCount("2026-10-26", 1)  # Sunday 01/11 belongs to the week of Monday 26/10
    assert weeks[0] == WeekCount("2026-08-17", 1)
    assert sum(week.count for week in weeks) == 4  # 01/08 is older than 12 weeks
    assert average_tenths(weeks) == 3  # 4 / 12 = 0,33
    assert average_tenths([]) == 0


def test_sessions_per_week_empty() -> None:
    weeks = sessions_per_week([], "2026-11-02", weeks=3)
    assert weeks == (WeekCount("2026-10-19", 0), WeekCount("2026-10-26", 0), WeekCount("2026-11-02", 0))
