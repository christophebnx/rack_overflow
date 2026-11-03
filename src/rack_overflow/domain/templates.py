"""Rules of session templates (D-058, D-059): names and locations, menu labels, indicative targets,
and the limits of slots and menu options.

Refusals are `domain.catalog.CatalogError`s carrying `Problem`s, like every catalog form, so the
web layer renders them through the same path. Targets are typed in display units (`target`) and
checked on canonical integers (`check_target`, shared with the seed).
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, fields

from rack_overflow.domain import units
from rack_overflow.domain.catalog import (
    CatalogError,
    Problem,
    choice_input,
    name_taken,
    raise_if,
    text_input,
)
from rack_overflow.domain.vocabulary import LOCATIONS

NAME_MAX = 60
LABEL_MAX = 40
NOTE_MAX = 40
MAX_SLOTS = 30
MAX_OPTIONS = 12
SETS_MIN, SETS_MAX = 1, 20
REPS_MIN, REPS_MAX = 1, 100
DURATION_MAX = 24 * 3600
EXERCISE = "exercise"
MENU = "menu"
SLOT_KINDS: tuple[str, ...] = (EXERCISE, MENU)
_PARTS = ("sets", "reps", "duration", "distance", "note")

_REPS = re.compile(r"(\d+)(?:\s*(?:-|\u2013|\u2014|à|a)\s*(\d+))?", re.ASCII | re.IGNORECASE)


@dataclass(frozen=True)
class TemplateDraft:
    """A template's validated attributes."""

    name: str
    location: str


def template_draft(*, name: str | None, location: str | None) -> TemplateDraft:
    """Validate a template form: name 1 to 60 characters, location in `vocabulary.LOCATIONS`."""
    problems: list[Problem] = []
    clean_name = text_input(problems, "name", name, NAME_MAX, required=True)
    clean_location = choice_input(problems, "location", location, LOCATIONS)
    raise_if(problems)
    assert clean_name is not None and clean_location is not None
    return TemplateDraft(clean_name, clean_location)


def check_template_name(name: str, others: Collection[str]) -> None:
    """Refuse `name` (`template_name_taken`) when another template of the user has it after
    normalisation, archived ones included."""
    if name_taken(name, others):
        raise CatalogError([Problem("name", "template_name_taken")])


def menu_label(raw: str | None) -> str:
    """A menu's name: free text, 1 to 40 characters stripped (field `label`)."""
    problems: list[Problem] = []
    label = text_input(problems, "label", raw, LABEL_MAX, required=True)
    raise_if(problems)
    assert label is not None
    return label


@dataclass(frozen=True)
class Target:
    """An indicative target in canonical integers; every part optional (D-059). A single reps
    value is stored `reps_min = reps_max`."""

    sets: int | None = None
    reps_min: int | None = None
    reps_max: int | None = None
    duration_s: int | None = None
    distance_m: int | None = None
    note: str | None = None

    @property
    def is_empty(self) -> bool:
        """True when no part is set."""
        return all(getattr(self, part.name) is None for part in fields(self))


def target(
    *,
    sets: str | None = None,
    reps: str | None = None,
    duration: str | None = None,
    distance: str | None = None,
    note: str | None = None,
) -> Target:
    """Parse a target typed in display units (« 8-10 », « 0:30 », « 400 m ») and check it."""
    problems: list[Problem] = []
    clean_sets = _number(problems, "sets", units.INT, sets)
    reps_min, reps_max = _reps(problems, reps)
    clean_duration = _number(problems, "duration", units.DURATION, duration)
    clean_distance = _number(problems, "distance", units.DISTANCE, distance)
    clean_note = text_input(problems, "note", note, NOTE_MAX, required=False)
    result = Target(clean_sets, reps_min, reps_max, clean_duration, clean_distance, clean_note)
    refused = {problem.field for problem in problems}
    problems.extend(problem for problem in _target_problems(result) if problem.field not in refused)
    raise_if(sorted(problems, key=lambda problem: _PARTS.index(problem.field)))
    return result


def _number(problems: list[Problem], name: str, kind: str, raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return units.parse(kind, text)
    except units.UnitError as error:
        problems.append(Problem(name, error.code, {"value": text}))
        return None


def _reps(problems: list[Problem], raw: str | None) -> tuple[int | None, int | None]:
    text = (raw or "").strip()
    if not text:
        return None, None
    match = _REPS.fullmatch(text)
    if match is None:
        problems.append(Problem("reps", "target_reps_format"))
        return None, None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) is not None else low
    return low, high


def check_target(value: Target) -> None:
    """The rules of a target on canonical values (UI and seed alike): sets 1 to 20, reps 1 to 100 with
    min ≤ max (both or neither), duration 1 s to 24 h, distance > 0, note ≤ 40 characters."""
    raise_if(_target_problems(value))


def _target_problems(value: Target) -> list[Problem]:
    problems: list[Problem] = []
    if value.sets is not None and not SETS_MIN <= value.sets <= SETS_MAX:
        problems.append(Problem("sets", "target_sets_range"))
    problems.extend(_reps_problems(value.reps_min, value.reps_max))
    if value.duration_s is not None:
        problems.extend(_positive("duration", value.duration_s, DURATION_MAX))
    if value.distance_m is not None:
        problems.extend(_positive("distance", value.distance_m, units.MAX_VALUE))
    if value.note is not None and not value.note.strip():
        problems.append(Problem("note", "required"))
    elif value.note is not None and len(value.note) > NOTE_MAX:
        problems.append(Problem("note", "too_long", {"max": NOTE_MAX}))
    return problems


def _reps_problems(low: int | None, high: int | None) -> list[Problem]:
    if low is None and high is None:
        return []
    if low is None or high is None:
        return [Problem("reps", "target_reps_format")]
    if not (REPS_MIN <= low <= REPS_MAX and REPS_MIN <= high <= REPS_MAX):
        return [Problem("reps", "target_reps_range")]
    if low > high:
        return [Problem("reps", "target_reps_order")]
    return []


def _positive(name: str, value: int, maximum: int) -> list[Problem]:
    if value <= 0:
        return [Problem(name, "must_be_positive")]
    if value > maximum:
        return [Problem(name, "too_large")]
    return []


def reps_text(low: int | None, high: int | None) -> str:
    """The reps input text `target` reads back: « 10 », « 8-10 », empty when unset."""
    if low is None or high is None:
        return ""
    return str(low) if low == high else f"{low}-{high}"


def check_slot_added(live_slots: int) -> None:
    """A template holds at most 30 live slots (`too_many_slots`, field `kind`)."""
    if live_slots >= MAX_SLOTS:
        raise CatalogError([Problem("kind", "too_many_slots", {"max": MAX_SLOTS})])


def check_option_added(existing_ids: Collection[int], exercise_id: int) -> None:
    """A menu offers an exercise once (`option_taken`) and at most 12 (`too_many_options`)."""
    if exercise_id in existing_ids:
        raise CatalogError([Problem("exercise_id", "option_taken")])
    if len(existing_ids) >= MAX_OPTIONS:
        raise CatalogError([Problem("exercise_id", "too_many_options", {"max": MAX_OPTIONS})])


def check_option_removed(count: int) -> None:
    """A menu keeps at least one option (`last_option`): remove the slot instead."""
    if count <= 1:
        raise CatalogError([Problem("option", "last_option")])
