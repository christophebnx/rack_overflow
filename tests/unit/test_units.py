"""Canonical integers <-> user text (D-020, D-055)."""

from __future__ import annotations

import pytest

from rack_overflow.domain import units
from rack_overflow.domain.units import Display, UnitError


@pytest.mark.parametrize(
    ("kind", "raw", "value"),
    [
        ("int", "12", 12),
        ("int", " 0 ", 0),
        ("weight", "16", 16000),
        ("weight", "2,5", 2500),
        ("weight", "1.25", 1250),
        ("weight", "0,125", 125),
        ("weight", "2,500", 2500),
        ("distance", "5,2", 5200),
        ("distance", "5,2 km", 5200),
        ("distance", "5.2KM", 5200),
        ("distance", "400 m", 400),
        ("distance", "400m", 400),
        ("distance", "0,4", 400),
        ("duration", "90", 90),
        ("duration", "1:30", 90),
        ("duration", "0:45", 45),
        ("duration", "59:59", 3599),
        ("duration", "1:00:00", 3600),
        ("duration", "1:02:03", 3723),
    ],
)
def test_parse(kind: str, raw: str, value: int) -> None:
    assert units.parse(kind, raw) == value


@pytest.mark.parametrize(
    ("scale", "raw", "value"), [(1, "2,5", 25), (2, "2,5", 250), (3, "0,001", 1), (2, "3", 300)]
)
def test_parse_decimal_uses_the_scale(scale: int, raw: str, value: int) -> None:
    assert units.parse("decimal", raw, scale=scale) == value


@pytest.mark.parametrize(
    ("kind", "raw", "code"),
    [
        ("int", "", "not_a_number"),
        ("int", "abc", "not_a_number"),
        ("int", ",", "not_a_number"),
        ("int", "2,5", "too_many_decimals"),
        ("int", "-3", "negative"),
        ("weight", "-2,5", "negative"),
        ("weight", "1,2345", "too_many_decimals"),
        ("weight", "1000001", "too_large"),
        ("int", "1000000001", "too_large"),
        ("int", "123456789012345", "too_large"),
        ("distance", "400,5 m", "too_many_decimals"),
        ("distance", "km", "not_a_number"),
        ("duration", "1:5", "bad_duration"),
        ("duration", "1:60", "bad_duration"),
        ("duration", "1:00:60", "bad_duration"),
        ("duration", "1:2:3:4", "bad_duration"),
        ("duration", "1,5", "bad_duration"),
        ("duration", "abc", "bad_duration"),
        ("duration", "99999999999", "too_large"),
        ("duration", "99999999999:00", "too_large"),
    ],
)
def test_parse_refusals(kind: str, raw: str, code: str) -> None:
    with pytest.raises(UnitError) as caught:
        units.parse(kind, raw)
    assert caught.value.code == code


def test_parse_decimal_refuses_more_decimals_than_the_scale() -> None:
    with pytest.raises(UnitError, match="too_many_decimals"):
        units.parse("decimal", "2,55", scale=1)


@pytest.mark.parametrize(
    ("kind", "value", "shown"),
    [
        ("int", 12, Display("12", None)),
        ("weight", 16000, Display("16", "unit.kg")),
        ("weight", 2500, Display("2,5", "unit.kg")),
        ("weight", 1250, Display("1,25", "unit.kg")),
        ("weight", 1, Display("0,001", "unit.kg")),
        ("distance", 999, Display("999", "unit.m")),
        ("distance", 1000, Display("1", "unit.km")),
        ("distance", 5200, Display("5,2", "unit.km")),
        ("duration", 45, Display("0:45", None)),
        ("duration", 3599, Display("59:59", None)),
        ("duration", 3600, Display("1:00:00", None)),
        ("duration", 3723, Display("1:02:03", None)),
    ],
)
def test_format(kind: str, value: int, shown: Display) -> None:
    assert units.format(kind, value) == shown


def test_format_decimal_keeps_exactly_scale_decimals() -> None:
    assert units.format("decimal", 250, scale=2) == Display("2,50", None)
    assert units.format("decimal", 5, scale=1) == Display("0,5", None)


@pytest.mark.parametrize(
    ("kind", "value", "scale"),
    [
        ("int", 7, None),
        ("weight", 2500, None),
        ("distance", 100, None),
        ("distance", 5250, None),
        ("duration", 3723, None),
        ("decimal", 125, 2),
    ],
)
def test_input_text_round_trips(kind: str, value: int, scale: int | None) -> None:
    assert units.parse(kind, units.input_text(kind, value, scale=scale), scale=scale) == value


def test_input_text_of_short_distance_carries_metres() -> None:
    assert units.input_text("distance", 400) == "400 m"


def test_kind_of_quantity_and_label_units() -> None:
    assert [units.kind_of_quantity(q) for q in ("reps", "weight", "duration", "distance")] == [
        "int",
        "weight",
        "duration",
        "distance",
    ]
    assert units.input_unit_key("weight") == "unit.kg"
    assert units.input_unit_key("distance") == "unit.km"
    assert units.input_unit_key("duration") == "unit.duration"
    assert units.input_unit_key("int") is None


# --- round trips over whole ranges and boundaries (tester, L2)


@pytest.mark.parametrize("kind", ["int", "weight", "distance", "duration"])
@pytest.mark.parametrize(
    "value",
    [
        0,
        1,
        9,
        10,
        59,
        60,
        99,
        100,
        125,
        999,
        1000,
        1001,
        1250,
        2500,
        3599,
        3600,
        3601,
        5200,
        86399,
        86400,
        10**9,
    ],
)
def test_every_value_reads_back_from_its_input_text(kind: str, value: int) -> None:
    assert units.parse(kind, units.input_text(kind, value)) == value


@pytest.mark.parametrize("scale", [1, 2, 3])
@pytest.mark.parametrize("value", [0, 1, 5, 10, 99, 100, 101, 12345])
def test_decimal_values_read_back_at_every_scale(scale: int, value: int) -> None:
    text = units.input_text("decimal", value, scale=scale)
    assert len(text.split(",")[1]) == scale
    assert units.parse("decimal", text, scale=scale) == value


def test_weight_grid_round_trips() -> None:
    for grams in range(0, 50001, 125):
        shown = units.format("weight", grams)
        assert shown.unit_key == units.UNIT_KG
        assert units.parse("weight", shown.number_text) == grams
        assert units.parse("weight", shown.number_text.replace(",", ".")) == grams


def test_distance_switches_unit_at_one_kilometre() -> None:
    assert units.format("distance", 999) == Display("999", units.UNIT_M)
    assert units.format("distance", 1000) == Display("1", units.UNIT_KM)
    assert units.format("distance", 1001) == Display("1,001", units.UNIT_KM)
    for metres in range(0, 3001, 7):
        assert units.parse("distance", units.input_text("distance", metres)) == metres


def test_duration_switches_format_at_one_hour() -> None:
    assert units.format("duration", 3599).number_text == "59:59"
    assert units.format("duration", 3600).number_text == "1:00:00"
    for seconds in range(0, 7400, 13):
        text = units.format("duration", seconds).number_text
        assert units.parse("duration", text) == seconds


@pytest.mark.parametrize(
    ("kind", "raw", "value"),
    [
        ("weight", "\u00a02,5\u00a0", 2500),
        ("weight", "007", 7000),
        ("distance", "5,2KM", 5200),
        ("distance", "5,2\u00a0km", 5200),
        ("distance", "400 M", 400),
        ("distance", ",5", 500),
        ("duration", "0:00", 0),
        ("duration", "10:00:00", 36000),
        ("duration", "120:00", 7200),
        ("weight", "1000000", 10**9),
    ],
)
def test_parse_tolerates_spacing_case_and_leading_zeros(kind: str, raw: str, value: int) -> None:
    assert units.parse(kind, raw) == value


@pytest.mark.parametrize(
    ("kind", "raw", "code"),
    [
        ("weight", "1000000,001", "too_large"),
        ("weight", "2,5 kg", "not_a_number"),
        ("weight", "2,5,0", "not_a_number"),
        ("weight", "1 000", "not_a_number"),
        ("weight", "\u0661\u0662", "not_a_number"),
        ("weight", "+5", "not_a_number"),
        ("weight", "1e3", "not_a_number"),
        ("weight", "-0", "negative"),
        ("distance", "-400 m", "negative"),
        ("distance", "5 mi", "not_a_number"),
        ("distance", "400,5 m", "too_many_decimals"),
        ("distance", "1,0005", "too_many_decimals"),
        ("duration", "1:5", "bad_duration"),
        ("duration", "1:60", "bad_duration"),
        ("duration", "1:00:60", "bad_duration"),
        ("duration", "1:00:00:00", "bad_duration"),
        ("duration", ":30", "bad_duration"),
        ("duration", "1,5", "bad_duration"),
        ("duration", "", "bad_duration"),
        ("duration", "1000000001", "too_large"),
        ("int", "2,5", "too_many_decimals"),
        ("int", "", "not_a_number"),
    ],
)
def test_parse_refuses_with_a_stable_code(kind: str, raw: str, code: str) -> None:
    with pytest.raises(UnitError) as refused:
        units.parse(kind, raw)
    assert refused.value.code == code


@pytest.mark.parametrize(
    ("seconds", "key", "params"),
    [
        (0, units.COMPACT_SECONDS, {"seconds": "0"}),
        (45, units.COMPACT_SECONDS, {"seconds": "45"}),
        (60, units.COMPACT_MINUTES, {"minutes": "1"}),
        (1800, units.COMPACT_MINUTES, {"minutes": "30"}),
        (90, units.COMPACT_MINUTES_SECONDS, {"minutes": "1", "seconds": "30"}),
        (65, units.COMPACT_MINUTES_SECONDS, {"minutes": "1", "seconds": "05"}),
        (3600, units.COMPACT_HOURS, {"hours": "1"}),
        (4500, units.COMPACT_HOURS_MINUTES, {"hours": "1", "minutes": "15"}),
        (3900, units.COMPACT_HOURS_MINUTES, {"hours": "1", "minutes": "05"}),
        (4530, None, {"text": "1:15:30"}),
    ],
)
def test_compact_duration(seconds: int, key: str | None, params: dict[str, str]) -> None:
    assert units.compact_duration(seconds) == units.CompactDuration(key, params)
