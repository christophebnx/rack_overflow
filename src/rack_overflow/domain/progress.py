"""Rules of the L5 forms (D-067, D-069): the measured RM entry, the formula setting and the month
grouping of the history. Refusals are `catalog.CatalogError` problems, like every form (D-050)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rack_overflow.domain import units
from rack_overflow.domain.catalog import CatalogError, Problem, choice_input, raise_if
from rack_overflow.domain.indicators import MAX_ESTIMATION_REPS, RM_FORMULAS, STRENGTH
from rack_overflow.domain.text import is_digits

RM_NOT_STRENGTH = "rm_not_strength"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


@dataclass(frozen=True)
class RmDraft:
    """A valid measured RM: n (1 to 12), the load in grams and the local date of the test."""

    n: int
    weight_g: int
    measured_on: str


def _reps(problems: list[Problem], raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        problems.append(Problem("n", "required"))
        return None
    if not is_digits(text) or not 1 <= int(text) <= MAX_ESTIMATION_REPS:
        problems.append(Problem("n", "rm_reps_range"))
        return None
    return int(text)


def _weight(problems: list[Problem], raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        problems.append(Problem("weight", "required"))
        return None
    try:
        value = units.parse(units.WEIGHT, text)
    except units.UnitError as error:
        problems.append(Problem("weight", error.code))
        return None
    if value <= 0:
        problems.append(Problem("weight", "must_be_positive"))
        return None
    return value


def _iso_day(text: str) -> date | None:
    """The date of `YYYY-MM-DD` text (ASCII digits, no other ISO form), else None."""
    if not _ISO_DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _date(problems: list[Problem], raw: str | None, today: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        problems.append(Problem("date", "required"))
        return None
    day = _iso_day(text)
    if day is None:
        problems.append(Problem("date", "bad_date"))
        return None
    if day > date.fromisoformat(today):
        problems.append(Problem("date", "date_in_future"))
        return None
    return day.isoformat()


def rm_draft(raw_n: str | None, raw_weight: str | None, raw_date: str | None, today: str) -> RmDraft:
    """The measured RM typed in the RM form (D-069): n 1 to 12 (`rm_reps_range`), a load in kg
    (unit codes, `must_be_positive`), an ISO date (`bad_date`) not after `today`
    (`date_in_future`); every problem at once (`CatalogError`)."""
    problems: list[Problem] = []
    n = _reps(problems, raw_n)
    weight = _weight(problems, raw_weight)
    measured_on = _date(problems, raw_date, today)
    raise_if(problems)
    assert n is not None and weight is not None and measured_on is not None
    return RmDraft(n, weight, measured_on)


def check_rm_exercise(category: str) -> None:
    """Only strength exercises have RMs (`rm_not_strength`)."""
    if category != STRENGTH:
        raise CatalogError([Problem("n", RM_NOT_STRENGTH)])


def formula_draft(raw: str | None) -> str:
    """The chosen 1RM formula, one of `indicators.RM_FORMULAS` (else `invalid_choice`)."""
    problems: list[Problem] = []
    formula = choice_input(problems, "rm_formula", raw, RM_FORMULAS)
    raise_if(problems)
    assert formula is not None
    return formula


def month_key(local_date: str) -> str:
    """The month of a local date, `YYYY-MM` (history grouping)."""
    return local_date[:7]
