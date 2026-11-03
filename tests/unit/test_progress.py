"""Unit tests of `domain/progress` (D-067, D-069): RM entry, formula setting, month key."""

from __future__ import annotations

import pytest

from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.progress import RmDraft, check_rm_exercise, formula_draft, month_key, rm_draft

TODAY = "2026-11-03"


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[tuple[str, str]]:
    return [(problem.field, problem.code) for problem in error.value.problems]


def test_rm_draft_valid() -> None:
    assert rm_draft("5", "92,5", "2026-10-01", TODAY) == RmDraft(5, 92500, "2026-10-01")
    assert rm_draft(" 1 ", "100", TODAY, TODAY) == RmDraft(1, 100000, TODAY)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (("", "", ""), [("n", "required"), ("weight", "required"), ("date", "required")]),
        (("0", "10", TODAY), [("n", "rm_reps_range")]),
        (("13", "10", TODAY), [("n", "rm_reps_range")]),
        (("x", "10", TODAY), [("n", "rm_reps_range")]),
        (("1", "abc", TODAY), [("weight", "not_a_number")]),
        (("1", "1,2345", TODAY), [("weight", "too_many_decimals")]),
        (("1", "0", TODAY), [("weight", "must_be_positive")]),
        (("1", "-5", TODAY), [("weight", "negative")]),
        (("1", "10", "03/11/2026"), [("date", "bad_date")]),
        (("1", "10", "20261103"), [("date", "bad_date")]),
        (("1", "10", "2026-11-04"), [("date", "date_in_future")]),
    ],
)
def test_rm_draft_refusals(raw: tuple[str, str, str], expected: list[tuple[str, str]]) -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft(*raw, TODAY)
    assert codes(error) == expected


def test_rm_only_for_strength() -> None:
    check_rm_exercise("strength")
    with pytest.raises(CatalogError) as error:
        check_rm_exercise("cardio")
    assert codes(error) == [("n", "rm_not_strength")]


def test_formula_draft() -> None:
    assert formula_draft("brzycki") == "brzycki"
    for raw, code in ((None, "required"), ("magic", "invalid_choice")):
        with pytest.raises(CatalogError) as error:
            formula_draft(raw)
        assert codes(error) == [("rm_formula", code)]


def test_month_key() -> None:
    assert month_key("2026-11-03") == "2026-11"
