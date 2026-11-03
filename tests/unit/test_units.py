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
