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


# --- edge cases (tester, L5)


@pytest.mark.parametrize(("raw", "n"), [("1", 1), ("12", 12), ("012", 12), (" 7 ", 7)])
def test_rm_draft_reps_boundaries(raw: str, n: int) -> None:
    assert rm_draft(raw, "100", TODAY, TODAY).n == n


@pytest.mark.parametrize("raw", ["-1", "1.5", "1,0", "+3", "1e1", "99999999999999999999"])
def test_rm_draft_reps_refused(raw: str) -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft(raw, "100", TODAY, TODAY)
    assert codes(error) == [("n", "rm_reps_range")]


@pytest.mark.xfail(
    strict=True,
    reason="bug: domain/progress.py:30 `str.isdigit` accepts « ² » and `int` then raises a plain "
    "ValueError instead of the `rm_reps_range` refusal",
)
def test_rm_draft_superscript_digit_is_a_refusal() -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft("²", "100", TODAY, TODAY)
    assert codes(error) == [("n", "rm_reps_range")]


@pytest.mark.parametrize(
    ("raw", "grams"), [("0,1", 100), ("0,001", 1), ("92,5", 92500), ("92.5", 92500), ("300", 300000)]
)
def test_rm_draft_weight_in_integer_grams(raw: str, grams: int) -> None:
    assert rm_draft("1", raw, TODAY, TODAY).weight_g == grams


@pytest.mark.parametrize("raw", ["0,0", "0,000"])
def test_rm_draft_zero_weight_in_any_spelling(raw: str) -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft("1", raw, TODAY, TODAY)
    assert codes(error) == [("weight", "must_be_positive")]


@pytest.mark.parametrize(
    "raw", ["2026-02-30", "2026-13-01", "2026-11-3", "2026-11-03T00:00", "2026-307", "  ", "today"]
)
def test_rm_draft_bad_dates(raw: str) -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft("1", "100", raw, TODAY)
    expected = "required" if not raw.strip() else "bad_date"
    assert codes(error) == [("date", expected)]


@pytest.mark.xfail(
    strict=True,
    reason="bug: domain/progress.py:58 `date.fromisoformat` accepts the ISO week form « 2026-W44-1 » "
    "(10 characters, passes the length check); the form takes `YYYY-MM-DD` only",
)
def test_rm_draft_iso_week_date_is_refused() -> None:
    with pytest.raises(CatalogError) as error:
        rm_draft("1", "100", "2026-W44-1", TODAY)
    assert codes(error) == [("date", "bad_date")]


def test_rm_draft_dates_around_today_and_leap_days() -> None:
    assert rm_draft("1", "100", "2024-02-29", TODAY).measured_on == "2024-02-29"
    assert rm_draft("1", "100", "2026-12-31", "2026-12-31").measured_on == "2026-12-31"
    with pytest.raises(CatalogError) as error:
        rm_draft("1", "100", "2027-01-01", "2026-12-31")
    assert codes(error) == [("date", "date_in_future")]


@pytest.mark.parametrize("raw", ["epley", "brzycki", "lombardi", "oconner", "wathan"])
def test_formula_draft_accepts_each_stable_key(raw: str) -> None:
    assert formula_draft(raw) == raw


@pytest.mark.parametrize("raw", ["Epley", "EPLEY", "O'Conner", "o_conner"])
def test_formula_draft_takes_keys_not_labels(raw: str) -> None:
    with pytest.raises(CatalogError) as error:
        formula_draft(raw)
    assert codes(error) == [("rm_formula", "invalid_choice")]


@pytest.mark.parametrize("category", ["kettlebell", "bodyweight", "cardio", "intervals"])
def test_rm_refused_for_every_other_category(category: str) -> None:
    with pytest.raises(CatalogError):
        check_rm_exercise(category)


def test_month_key_across_a_year() -> None:
    assert month_key("2026-12-31") == "2026-12" and month_key("2027-01-01") == "2027-01"
