"""Template, menu and target rules (`domain/templates`, D-058, D-059)."""

from __future__ import annotations

import pytest

from rack_overflow.domain import templates
from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.templates import Target


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[tuple[str, str]]:
    return [(problem.field, problem.code) for problem in error.value.problems]


# --- templates and menus


def test_template_draft_strips_and_keeps_the_location() -> None:
    assert templates.template_draft(name="  Salle A ", location="gym") == templates.TemplateDraft(
        "Salle A", "gym"
    )


def test_template_name_length() -> None:
    assert templates.template_draft(name="x" * 60, location="both").name == "x" * 60
    with pytest.raises(CatalogError) as refused:
        templates.template_draft(name="x" * 61, location="home")
    assert codes(refused) == [("name", "too_long")]
    assert refused.value.problems[0].params == {"max": 60}


def test_template_draft_reports_every_problem() -> None:
    with pytest.raises(CatalogError) as refused:
        templates.template_draft(name="  ", location=None)
    assert codes(refused) == [("name", "required"), ("location", "required")]
    with pytest.raises(CatalogError) as refused:
        templates.template_draft(name="A", location="office")
    assert codes(refused) == [("location", "invalid_choice")]


def test_template_name_taken_folds_case_and_accents() -> None:
    templates.check_template_name("Salle A", ["Salle B"])
    with pytest.raises(CatalogError) as refused:
        templates.check_template_name("cardio — course 30 min", ["Cardio — Course 30 min"])
    assert codes(refused) == [("name", "template_name_taken")]
    with pytest.raises(CatalogError):
        templates.check_template_name("Séance", ["seance"])


def test_menu_label() -> None:
    assert templates.menu_label(" Tirage horizontal ") == "Tirage horizontal"
    assert templates.menu_label("x" * 40) == "x" * 40
    for raw, code in ((None, "required"), ("  ", "required"), ("x" * 41, "too_long")):
        with pytest.raises(CatalogError) as refused:
            templates.menu_label(raw)
        assert codes(refused) == [("label", code)]


# --- targets


@pytest.mark.parametrize(
    ("raw", "low", "high"),
    [
        ("10", 10, 10),
        ("8\u201310", 8, 10),
        ("8-10", 8, 10),
        ("8 à 10", 8, 10),
        (" 8 - 10 ", 8, 10),
        ("8—10", 8, 10),
        ("6 a 8", 6, 8),
        ("12-12", 12, 12),
    ],
)
def test_reps_input_forms(raw: str, low: int, high: int) -> None:
    parsed = templates.target(reps=raw)
    assert (parsed.reps_min, parsed.reps_max) == (low, high)
    assert templates.target(reps=templates.reps_text(low, high)) == parsed


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("abc", "target_reps_format"),
        ("8-", "target_reps_format"),
        ("8/10", "target_reps_format"),
        ("-3", "target_reps_format"),
        ("0", "target_reps_range"),
        ("101", "target_reps_range"),
        ("5-101", "target_reps_range"),
        ("10-8", "target_reps_order"),
    ],
)
def test_reps_refusals(raw: str, code: str) -> None:
    with pytest.raises(CatalogError) as refused:
        templates.target(reps=raw)
    assert codes(refused) == [("reps", code)]


@pytest.mark.parametrize(("raw", "code"), [("0", "target_sets_range"), ("21", "target_sets_range")])
def test_sets_range(raw: str, code: str) -> None:
    assert templates.target(sets="1").sets == 1
    assert templates.target(sets="20").sets == 20
    with pytest.raises(CatalogError) as refused:
        templates.target(sets=raw)
    assert codes(refused) == [("sets", code)]


def test_sets_not_a_number_keeps_the_units_code() -> None:
    with pytest.raises(CatalogError) as refused:
        templates.target(sets="trois")
    assert codes(refused) == [("sets", "not_a_number")]


def test_duration_and_distance_go_through_units() -> None:
    parsed = templates.target(duration="0:30", distance="400 m")
    assert (parsed.duration_s, parsed.distance_m) == (30, 400)
    assert templates.target(duration="30:00", distance="5").duration_s == 1800
    assert templates.target(distance="5").distance_m == 5000
    with pytest.raises(CatalogError) as refused:
        templates.target(duration="1:75", distance="abc")
    assert codes(refused) == [("duration", "bad_duration"), ("distance", "not_a_number")]
    assert refused.value.problems[0].params == {"value": "1:75"}


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ({"duration": "0"}, [("duration", "must_be_positive")]),
        ({"duration": "24:00:01"}, [("duration", "too_large")]),
        ({"distance": "0"}, [("distance", "must_be_positive")]),
        ({"note": "x" * 41}, [("note", "too_long")]),
    ],
)
def test_part_limits(parts: dict[str, str], expected: list[tuple[str, str]]) -> None:
    with pytest.raises(CatalogError) as refused:
        templates.target(**parts)
    assert codes(refused) == expected
    assert templates.target(duration="24:00:00").duration_s == 86400


def test_note_limit_and_strip() -> None:
    assert templates.target(note="  par côté ").note == "par côté"
    assert templates.target(note="x" * 40).note == "x" * 40
    with pytest.raises(CatalogError) as refused:
        templates.target(note="x" * 41)
    assert refused.value.problems[0].params == {"max": 40}


def test_every_problem_at_once() -> None:
    with pytest.raises(CatalogError) as refused:
        templates.target(sets="0", reps="x", duration="x", distance="-1", note="x" * 41)
    assert [field for field, _ in codes(refused)] == ["sets", "reps", "duration", "distance", "note"]


def test_empty_inputs_give_an_empty_target() -> None:
    empty = templates.target(sets=" ", reps="", duration=None, distance="", note="  ")
    assert empty == Target() and empty.is_empty
    assert not templates.target(note="par côté").is_empty


def test_full_target() -> None:
    assert templates.target(sets="3", reps="12", duration="0:30", note="par côté") == Target(
        3, 12, 12, 30, None, "par côté"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Target(reps_min=8), [("reps", "target_reps_format")]),
        (Target(reps_max=8), [("reps", "target_reps_format")]),
        (Target(sets=0), [("sets", "target_sets_range")]),
        (Target(duration_s=-5), [("duration", "must_be_positive")]),
        (Target(distance_m=10**9 + 1), [("distance", "too_large")]),
        (Target(note=" "), [("note", "required")]),
    ],
)
def test_check_target_on_canonical_values(value: Target, expected: list[tuple[str, str]]) -> None:
    with pytest.raises(CatalogError) as refused:
        templates.check_target(value)
    assert codes(refused) == expected


def test_reps_text() -> None:
    assert templates.reps_text(None, None) == ""
    assert templates.reps_text(10, 10) == "10"
    assert templates.reps_text(8, 10) == "8-10"


# --- slots and options


def test_slot_limit() -> None:
    templates.check_slot_added(templates.MAX_SLOTS - 1)
    with pytest.raises(CatalogError) as refused:
        templates.check_slot_added(templates.MAX_SLOTS)
    assert codes(refused) == [("kind", "too_many_slots")]


def test_option_checks() -> None:
    templates.check_option_added([1, 2], 3)
    with pytest.raises(CatalogError) as refused:
        templates.check_option_added([1, 2], 2)
    assert codes(refused) == [("exercise_id", "option_taken")]
    with pytest.raises(CatalogError) as refused:
        templates.check_option_added(list(range(templates.MAX_OPTIONS)), 99)
    assert codes(refused) == [("exercise_id", "too_many_options")]


def test_last_option_stays() -> None:
    templates.check_option_removed(2)
    for count in (1, 0):
        with pytest.raises(CatalogError) as refused:
            templates.check_option_removed(count)
        assert codes(refused) == [("option", "last_option")]
