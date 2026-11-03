"""Unit tests of `domain/sessions` (D-061 to D-063, D-065)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from rack_overflow.domain.catalog import CatalogError, FieldKind, FieldParams
from rack_overflow.domain.sessions import (
    Item,
    PlanSlot,
    RowRef,
    SessionError,
    SessionField,
    SetFacts,
    current_item,
    default_location,
    display_sequence,
    following,
    local_start,
    matches_location,
    prefill,
    raw_texts,
    set_draft,
    set_types,
    setting_draft,
    settings_prefill,
    start_plan,
    step_values,
    stepped,
    templates_for,
    variable_field,
)
from rack_overflow.domain.templates import Target

BRUSSELS = ZoneInfo("Europe/Brussels")

REPS = SessionField("reps", FieldKind("int"), FieldParams(required=True, increment=1), core_quantity="reps")
WEIGHT = SessionField(
    "weight", FieldKind("weight"), FieldParams(required=True, increment=2500), core_quantity="weight"
)
DURATION = SessionField(
    "duration", FieldKind("duration"), FieldParams(increment=30), core_quantity="duration"
)
DISTANCE = SessionField(
    "distance", FieldKind("distance"), FieldParams(increment=100), core_quantity="distance"
)
RESISTANCE = SessionField("var_7", FieldKind("int"), FieldParams(), variable_id=7)
GRIP = SessionField("var_8", FieldKind("enum", enum_keys=("prone", "neutral")), FieldParams(), variable_id=8)
STRAPS = SessionField("var_9", FieldKind("bool"), FieldParams(), variable_id=9)
NOTE = SessionField("var_10", FieldKind("text"), FieldParams(), variable_id=10)
SEAT = SessionField("var_11", FieldKind("int"), FieldParams(default_int=4), variable_id=11)
BELL = SessionField(
    "weight", FieldKind("weight"), FieldParams(discrete_values=(16000, 20000, 24000)), core_quantity="weight"
)
STRENGTH = (REPS, WEIGHT)


def work(reps: int, weight: int) -> SetFacts:
    return SetFacts("work", {"reps": reps, "weight": weight})


def warmup(reps: int, weight: int) -> SetFacts:
    return SetFacts("warmup", {"reps": reps, "weight": weight})


# --- start


def test_local_start_late_evening_utc_is_the_next_local_day() -> None:
    assert local_start(datetime(2026, 11, 3, 23, 30, tzinfo=UTC), BRUSSELS) == (
        "2026-11-04",
        "Europe/Brussels",
    )


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 3, 28, 23, 30, tzinfo=UTC), "2026-03-29"),  # winter: UTC+1
        (datetime(2026, 3, 29, 21, 59, tzinfo=UTC), "2026-03-29"),  # after the switch: UTC+2
        (datetime(2026, 3, 29, 22, 0, tzinfo=UTC), "2026-03-30"),
        (datetime(2026, 10, 25, 22, 59, tzinfo=UTC), "2026-10-25"),  # back to UTC+1
        (datetime(2026, 10, 25, 23, 0, tzinfo=UTC), "2026-10-26"),
    ],
)
def test_local_start_across_daylight_saving_changes(moment: datetime, expected: str) -> None:
    assert local_start(moment, BRUSSELS)[0] == expected


def test_local_start_names_a_fixed_zone() -> None:
    assert local_start(datetime(2026, 1, 1, tzinfo=UTC), UTC) == ("2026-01-01", "UTC")


@pytest.mark.parametrize(
    ("last", "expected"), [(None, "gym"), ("home", "home"), ("gym", "gym"), ("x", "gym")]
)
def test_default_location(last: str | None, expected: str) -> None:
    assert default_location(last) == expected


def test_templates_for_keeps_both_and_the_order() -> None:
    templates = [("A", "gym"), ("Home", "home"), ("Cardio", "both"), ("B", "gym")]
    assert templates_for("gym", templates) == ["A", "Cardio", "B"]
    assert templates_for("home", templates) == ["Home", "Cardio"]
    assert matches_location("both", "home") and not matches_location("gym", "home")


def test_start_plan() -> None:
    slots = [
        PlanSlot(1, False, (10,)),
        PlanSlot(2, False, ()),  # archived fixed exercise: skipped
        PlanSlot(3, True, ()),  # every option archived: skipped
        PlanSlot(4, True, (20,)),  # one available option: picked
        PlanSlot(5, True, (30, 31, 32)),
    ]
    plan = start_plan(slots)
    assert plan.rows == ((1, 10), (4, 20))
    assert plan.pending == (5,)
    assert slots[1].skipped and not slots[0].skipped


# --- plan order


def test_display_sequence_follows_the_template_then_added_rows() -> None:
    slots = [
        PlanSlot(1, False, (10,)),
        PlanSlot(2, True, (20, 21)),
        PlanSlot(3, True, (30, 31)),
        PlanSlot(4, True, ()),
    ]
    rows = [
        RowRef(100, 1, 0),
        RowRef(101, None, 1),  # added
        RowRef(102, 3, 2),  # menu 3 picked
        RowRef(103, 99, 3),  # slot removed from the template since
        RowRef(104, 1, 4),  # second row of slot 1
    ]
    assert display_sequence(slots, rows) == [
        Item(row_id=100),
        Item(row_id=104),
        Item(menu_slot_id=2),
        Item(row_id=102),
        Item(row_id=101),
        Item(row_id=103),
    ]


def test_display_sequence_moves_with_the_template_order() -> None:
    rows = [RowRef(100, 1, 0), RowRef(101, 2, 1)]
    swapped = [PlanSlot(2, False, (20,)), PlanSlot(1, False, (10,))]
    assert display_sequence(swapped, rows) == [Item(row_id=101), Item(row_id=100)]


def test_display_sequence_keeps_rows_of_skipped_slots() -> None:
    assert display_sequence([PlanSlot(1, False, ())], [RowRef(5, 1, 0)]) == [Item(row_id=5)]
    assert display_sequence([PlanSlot(1, False, ())], []) == []


def test_current_item() -> None:
    sequence = [Item(row_id=1), Item(menu_slot_id=7), Item(row_id=2)]
    assert current_item(sequence, None, None) == Item(row_id=1)
    assert current_item(sequence, 2, None) == Item(row_id=2)
    assert current_item(sequence, 2, Item(menu_slot_id=7)) == Item(menu_slot_id=7)
    assert current_item(sequence, 2, Item(row_id=99)) == Item(row_id=2)  # unknown: default rule
    assert current_item(sequence, 99, None) == Item(row_id=1)
    assert current_item([], None, Item(row_id=1)) is None
    assert Item(menu_slot_id=7).is_menu and not Item(row_id=1).is_menu


def test_following() -> None:
    sequence = [Item(row_id=1), Item(menu_slot_id=7)]
    assert following(sequence, Item(row_id=1)) == Item(menu_slot_id=7)
    assert following(sequence, Item(menu_slot_id=7)) is None
    assert following(sequence, Item(row_id=5)) is None


# --- prefill


def test_first_set_ever_takes_the_target_then_the_defaults() -> None:
    target = Target(sets=4, reps_min=6, reps_max=8, duration_s=30)
    facts = prefill(0, [], [], target, STRENGTH)
    assert facts == SetFacts("work", {"reps": 6})  # duration not a field, no weight default
    seat_default = prefill(0, [], [], None, (REPS, SEAT))
    assert seat_default.values == {"var_11": 4}
    assert prefill(0, [], [], None, (DURATION, DISTANCE)) == SetFacts("work", {})
    assert prefill(0, [], [], Target(duration_s=1800, distance_m=5000), (DURATION, DISTANCE)).values == {
        "duration": 1800,
        "distance": 5000,
    }


def test_last_performance_gives_set_n() -> None:
    last = [warmup(10, 40000), work(8, 60000), work(8, 62500)]
    assert prefill(0, [], last, None, STRENGTH) == warmup(10, 40000)
    # set 2: last performance says work, today's previous is a warm-up: last performance N
    assert prefill(1, [warmup(10, 40000)], last, None, STRENGTH) == work(8, 60000)


def test_today_same_type_carries_forward() -> None:
    last = [work(8, 60000), work(8, 60000), work(8, 60000)]
    today = [work(8, 60000), work(8, 62500)]
    assert prefill(2, today, last, None, STRENGTH) == work(8, 62500)


def test_beyond_last_performance_repeats_today() -> None:
    today = [work(8, 60000)]
    assert prefill(1, today, [work(8, 50000)], None, STRENGTH) == work(8, 60000)
    # last performance had fewer sets and today's previous is a warm-up: same values, its type
    assert prefill(1, [warmup(10, 40000)], [], None, STRENGTH) == warmup(10, 40000)


def test_warm_up_values_do_not_leak_into_work_sets() -> None:
    last = [warmup(10, 40000), work(8, 60000)]
    assert prefill(1, [warmup(12, 45000)], last, None, STRENGTH) == work(8, 60000)


def test_prefill_drops_unlinked_variables() -> None:
    last = [SetFacts("work", {"duration": 1800, "var_7": 8, "var_99": 3})]
    assert prefill(0, [], last, None, (DURATION, RESISTANCE)).values == {"duration": 1800, "var_7": 8}


def test_settings_prefill() -> None:
    assert settings_prefill({7: 5}, (RESISTANCE, SEAT, NOTE)) == {7: 5, 11: 4}
    assert settings_prefill({11: 6}, (SEAT,)) == {11: 6}


# --- steppers


@pytest.mark.parametrize(
    ("value", "direction", "expected"),
    [
        (60000, "up", 62500),
        (60000, "down", 57500),
        (None, "up", 2500),
        (None, "down", None),
        (0, "down", 0),
        (1000, "down", 0),
        (61000, "up", 62500),  # off the grid: next grid value up
        (61000, "down", 60000),
        (2500, "down", 0),
    ],
)
def test_stepped_weight(value: int | None, direction: str, expected: int | None) -> None:
    assert stepped(WEIGHT.params, value, direction) == expected


def test_stepped_without_increment_or_direction() -> None:
    assert stepped(FieldParams(), 5, "up") == 5
    assert stepped(DURATION.params, 90, "sideways") == 90
    assert stepped(DURATION.params, 90, "up") == 120


def test_step_values_moves_one_field_in_display_units() -> None:
    raw = {"reps": "8", "weight": "60"}
    assert step_values(STRENGTH, raw, "weight:up") == {"reps": "8", "weight": "62,5"}
    assert step_values(STRENGTH, raw, "reps:down") == {"reps": "7", "weight": "60"}
    assert step_values((DURATION,), {"duration": "29:45"}, "duration:up") == {"duration": "30:00"}
    assert step_values(STRENGTH, {"weight": ""}, "weight:up") == {"weight": "2,5"}
    assert step_values(STRENGTH, {"weight": ""}, "weight:down") == {"weight": None}


@pytest.mark.parametrize("step", ["weight:left", "nothing:up", "var_7:up", None, ""])
def test_step_values_ignores_unknown_steps(step: str | None) -> None:
    raw = {"weight": "60", "var_7": "3"}
    assert step_values((*STRENGTH, RESISTANCE), raw, step) == raw


def test_step_values_leaves_unreadable_text() -> None:
    assert step_values(STRENGTH, {"weight": "abc"}, "weight:up") == {"weight": "abc"}


def test_raw_texts_round_trip_with_set_draft() -> None:
    fields = (*STRENGTH, DISTANCE, GRIP, STRAPS, NOTE)
    values = {"reps": 8, "weight": 62500, "distance": 400, "var_8": "neutral", "var_9": 1, "var_10": "bas"}
    texts = raw_texts(fields, values)
    assert texts == {
        "reps": "8",
        "weight": "62,5",
        "distance": "400 m",
        "var_8": "neutral",
        "var_9": "1",
        "var_10": "bas",
    }
    assert set_draft("strength", fields, "work", texts).values == values


# --- set and settings forms


def test_set_types_by_category() -> None:
    assert set_types("strength") == ("warmup", "work", "rm_test")
    assert set_types("kettlebell") == ("warmup", "work")


def test_set_draft_parses_display_units() -> None:
    facts = set_draft("strength", STRENGTH, "rm_test", {"reps": " 3 ", "weight": "102,5"})
    assert facts == SetFacts("rm_test", {"reps": 3, "weight": 102500})


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[tuple[str, str]]:
    return [(problem.field, problem.code) for problem in error.value.problems]


@pytest.mark.parametrize(
    ("raw_type", "raw", "expected"),
    [
        ("work", {"reps": "", "weight": "60"}, [("reps", "required")]),
        ("work", {"reps": "8", "weight": "6,2501"}, [("weight", "too_many_decimals")]),
        ("work", {"reps": "huit", "weight": "-5"}, [("reps", "not_a_number"), ("weight", "negative")]),
        (None, {"reps": "8", "weight": "60"}, [("type", "required")]),
        ("rest", {"reps": "8", "weight": "60"}, [("type", "invalid_choice")]),
    ],
)
def test_set_draft_refusals(
    raw_type: str | None, raw: dict[str, str], expected: list[tuple[str, str]]
) -> None:
    with pytest.raises(CatalogError) as error:
        set_draft("strength", STRENGTH, raw_type, raw)
    assert codes(error) == expected


def test_rm_test_only_for_strength() -> None:
    with pytest.raises(CatalogError) as error:
        set_draft("kettlebell", (BELL,), "rm_test", {"weight": "16"})
    assert codes(error) == [("type", "invalid_choice")]


def test_discrete_field_accepts_a_value_off_the_list() -> None:
    assert set_draft("kettlebell", (BELL,), "work", {"weight": "18"}).values == {"weight": 18000}


def test_empty_set_is_refused_on_the_form() -> None:
    with pytest.raises(CatalogError) as error:
        set_draft("cardio", (DURATION, DISTANCE), "work", {"duration": "", "distance": " "})
    assert codes(error) == [("set", "empty_set")]


@pytest.mark.parametrize(
    ("field", "raw", "code"),
    [
        (GRIP, "diagonal", "invalid_choice"),
        (STRAPS, "yes", "invalid_choice"),
        (NOTE, "x" * 41, "too_long"),
        (DURATION, "1:75", "bad_duration"),
    ],
)
def test_variable_refusals(field: SessionField, raw: str, code: str) -> None:
    with pytest.raises(CatalogError) as error:
        set_draft("cardio", (field,), "work", {field.name: raw})
    assert codes(error) == [(field.name, code)]


def test_setting_draft() -> None:
    fields = (SEAT, GRIP, STRAPS)
    assert setting_draft(fields, {"var_11": "5", "var_8": "prone", "var_9": "0"}) == {11: 5, 8: "prone", 9: 0}
    assert setting_draft(fields, {"var_11": ""}) == {11: None, 8: None, 9: None}
    required = SessionField("var_12", FieldKind("int"), FieldParams(required=True), variable_id=12)
    with pytest.raises(CatalogError) as error:
        setting_draft((required, GRIP), {"var_12": "", "var_8": "x"})
    assert codes(error) == [("var_12", "required"), ("var_8", "invalid_choice")]


def test_field_helpers() -> None:
    assert variable_field(7) == "var_7"
    assert WEIGHT.stepped and not BELL.stepped and not GRIP.stepped
    assert SetFacts("work").is_empty and SetFacts("work", {"reps": 1}).value("reps") == 1


def test_session_error_code() -> None:
    assert SessionError("session_closed").code == "session_closed"


# --- edge cases (tester)

LEVEL = SessionField("var_12", FieldKind("decimal", scale=1), FieldParams(increment=5), variable_id=12)


@pytest.mark.parametrize(
    ("fields", "raw", "step", "expected"),
    [
        ((LEVEL,), {"var_12": "2,5"}, "var_12:up", "3,0"),  # decimal keeps its scale
        ((LEVEL,), {"var_12": "0,3"}, "var_12:down", "0,0"),  # off the grid, floored at 0
        ((DISTANCE,), {"distance": "900 m"}, "distance:up", "1"),  # crosses 1 km: km text
        ((DISTANCE,), {"distance": "1"}, "distance:down", "900 m"),
        ((DURATION,), {"duration": "59:45"}, "duration:up", "1:00:00"),  # off the grid: snaps
        ((DURATION,), {"duration": "0:10"}, "duration:down", "0:00"),
    ],
)
def test_step_values_round_trip_through_the_parser(
    fields: tuple[SessionField, ...], raw: dict[str, str], step: str, expected: str
) -> None:
    name = fields[0].name
    moved = step_values(fields, raw, step)
    assert moved[name] == expected
    assert set_draft("cardio", fields, "work", {name: expected}).values.get(name, 0) >= 0


def test_target_is_ignored_once_a_last_performance_exists() -> None:
    target = Target(sets=3, reps_min=10, reps_max=12)
    assert prefill(0, [], [work(5, 100000)], target, STRENGTH) == work(5, 100000)


def test_prefill_beyond_the_last_performance_keeps_todays_type() -> None:
    # no last performance and today's previous set is a work set: work again, same values
    assert prefill(3, [warmup(10, 40000), work(8, 60000), work(8, 60000)], [], None, STRENGTH) == work(
        8, 60000
    )
    # last performance shorter than today: its type no longer drives the next set
    assert prefill(2, [work(8, 60000), warmup(5, 30000)], [work(8, 60000)], None, STRENGTH) == warmup(
        5, 30000
    )


def test_prefill_of_a_last_performance_missing_a_field_takes_no_default() -> None:
    weighted = SessionField(
        "weight", FieldKind("weight"), FieldParams(required=True, default_int=20000), core_quantity="weight"
    )
    found = prefill(0, [], [SetFacts("work", {"reps": 8})], None, (REPS, weighted))
    assert found.values == {"reps": 8}
