"""Rules of the catalog: variables, exercises, their fields and aliases (D-030 to D-032, D-054).

Validators take what the user typed and return clean values, or raise `CatalogError` carrying
every problem of the form at once (`Problem(field, code, params)`; codes map to
`catalog.error.*` strings in `web/`). Canonical values come from `domain/units`. The seed goes
through the same validators as the UI.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from rack_overflow.domain import units
from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.text import normalise, slug
from rack_overflow.domain.vocabulary import (
    CORE_QUANTITIES,
    EXERCISE_CATEGORIES,
    LOCATIONS,
    VARIABLE_SCOPES,
    VARIABLE_TYPES,
)

LABEL_MAX = 40
UNIT_MAX = 12
SCALES: tuple[int, ...] = (1, 2, 3)
ENUM_VALUES_MAX = 50
ENUM_LABEL_MAX = 40
NAME_MAX = 80
PATTERN_MAX = 40
EQUIPMENT_MAX = 40
ALIAS_MAX = 60
DISCRETE_MAX = 30
TEXT_DEFAULT_MAX = 40
FREE_UNIT_TYPES: tuple[str, ...] = (units.INT, units.DECIMAL)
"""Variable types that carry a free unit; the typed kinds (weight…) have a fixed one (D-055)."""
INT_COLUMN_TYPES: tuple[str, ...] = ("int", "decimal", "duration", "distance", "weight", "bool")

ENUM = "enum"
BOOL = "bool"
TEXT = "text"
BOOL_VALUES: dict[str, int] = {"1": 1, "0": 0}
_VALUE_SEPARATORS = re.compile(r"[;\s]+")
_UNIT_TOKENS = frozenset({"m", "km"})


@dataclass(frozen=True)
class Problem:
    """One refused input: the form field, a stable code, and the message parameters."""

    field: str
    code: str
    params: Mapping[str, object] = field(default_factory=dict)


class CatalogError(DomainError):
    """A catalog input was refused; `problems` lists every problem found."""

    def __init__(self, problems: Sequence[Problem]) -> None:
        super().__init__(", ".join(f"{problem.field}: {problem.code}" for problem in problems))
        self.problems = tuple(problems)


def _refuse(field_name: str, code: str, **params: object) -> CatalogError:
    return CatalogError([Problem(field_name, code, params)])


def _raise_if(problems: list[Problem]) -> None:
    if problems:
        raise CatalogError(problems)


def _text(problems: list[Problem], name: str, raw: str | None, maximum: int, *, required: bool) -> str | None:
    """`raw` stripped; empty → None (or `required`), longer than `maximum` → `too_long`."""
    value = (raw or "").strip()
    if not value:
        if required:
            problems.append(Problem(name, "required"))
        return None
    if len(value) > maximum:
        problems.append(Problem(name, "too_long", {"max": maximum}))
    return value


def _choice(problems: list[Problem], name: str, raw: str | None, allowed: Sequence[str]) -> str | None:
    if not raw:
        problems.append(Problem(name, "required"))
        return None
    if raw not in allowed:
        problems.append(Problem(name, "invalid_choice"))
        return None
    return raw


# --- variables ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class EnumValue:
    """One choice of an enum variable: a stable key (stored) and an editable label (D-032)."""

    key: str
    label: str


@dataclass(frozen=True)
class ValueInput:
    """One enum value as typed: an existing one carries its key (and may be removed), a new one none."""

    label: str
    key: str | None = None
    remove: bool = False


@dataclass(frozen=True)
class VariableDraft:
    """A variable's validated attributes (its code is derived once, by `variable_code`)."""

    label: str
    type: str
    scope: str
    unit: str | None = None
    decimal_scale: int | None = None
    enum_values: tuple[EnumValue, ...] | None = None


def variable_draft(
    *,
    label: str | None,
    var_type: str | None,
    scope: str | None,
    unit: str | None = None,
    scale: str | None = None,
    values: Sequence[ValueInput] = (),
    existing: Sequence[EnumValue] = (),
) -> VariableDraft:
    """Validate a variable form; only the attributes of the chosen type are read."""
    problems: list[Problem] = []
    clean_label = _text(problems, "label", label, LABEL_MAX, required=True)
    clean_type = _choice(problems, "type", var_type, VARIABLE_TYPES)
    clean_scope = _choice(problems, "scope", scope, VARIABLE_SCOPES)
    clean_unit = None
    if clean_type in FREE_UNIT_TYPES:
        clean_unit = _text(problems, "unit", unit, UNIT_MAX, required=False)
    clean_scale = None
    if clean_type == units.DECIMAL:
        clean_scale = _scale(problems, scale)
    enum = None
    if clean_type == ENUM:
        enum = _enum_values(problems, values, existing)
    _raise_if(problems)
    assert clean_label is not None and clean_type is not None and clean_scope is not None
    return VariableDraft(clean_label, clean_type, clean_scope, clean_unit, clean_scale, enum)


def _scale(problems: list[Problem], raw: str | None) -> int | None:
    choice = _choice(problems, "decimal_scale", raw, [str(scale) for scale in SCALES])
    return int(choice) if choice is not None else None


def _enum_values(
    problems: list[Problem], values: Sequence[ValueInput], existing: Sequence[EnumValue]
) -> tuple[EnumValue, ...]:
    known = {value.key for value in existing}
    kept: list[ValueInput] = []
    for value in values:
        if value.key is not None and value.key not in known:
            problems.append(Problem("values", "invalid_choice"))
        elif not value.remove and (value.label.strip() or value.key is not None):
            kept.append(value)
    if not kept:
        problems.append(Problem("values", "values_required"))
    elif len(kept) > ENUM_VALUES_MAX:
        problems.append(Problem("values", "too_many_values", {"max": ENUM_VALUES_MAX}))
    seen: set[str] = set()
    for value in kept:
        label = _text(problems, "values", value.label, ENUM_LABEL_MAX, required=True)
        if label is not None and normalise(label) in seen:
            problems.append(Problem("values", "duplicate_value", {"value": label}))
        seen.add(normalise(label or ""))
    if problems:
        return ()
    return enum_values(kept, known)


def enum_values(values: Sequence[ValueInput], known_keys: Iterable[str] = ()) -> tuple[EnumValue, ...]:
    """Keys for the kept values: an existing value keeps its key, a new one gets `slug(label)`
    (`e` when empty), suffixed on collision with any known or given key; never reused (D-032)."""
    taken = set(known_keys) | {value.key for value in values if value.key is not None}
    result: list[EnumValue] = []
    for value in values:
        key = value.key
        if key is None:
            key = _unique(slug(value.label) or "e", taken)
            taken.add(key)
        result.append(EnumValue(key, value.label.strip()))
    return tuple(result)


def _unique(base: str, taken: Iterable[str]) -> str:
    used = set(taken)
    if base not in used:
        return base
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    return f"{base}_{suffix}"


def variable_code(label: str, taken: Iterable[str]) -> str:
    """The variable's code: `slug(label)` (`v` when empty), suffixed `_2`, `_3`… when taken."""
    return _unique(slug(label) or "v", taken)


def variable_change(
    current: VariableDraft,
    draft: VariableDraft,
    *,
    has_values: bool,
    used_enum_keys: Iterable[str] = (),
) -> VariableDraft:
    """Check an edit: type, scope and scale are frozen once values exist; a used enum key stays."""
    problems: list[Problem] = []
    if has_values:
        for name in ("type", "scope", "decimal_scale"):
            if getattr(draft, name) != getattr(current, name):
                problems.append(Problem(name, "frozen_after_use"))
    kept = {value.key for value in draft.enum_values or ()}
    if draft.type == ENUM and any(key not in kept for key in used_enum_keys):
        problems.append(Problem("values", "enum_value_in_use"))
    _raise_if(problems)
    return draft


def value_column(var_type: str) -> str:
    """Storage column kind of a variable's values: `int` (value_int) or `text` (value_text)."""
    return "int" if var_type in INT_COLUMN_TYPES else "text"


# --- exercises ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExerciseDraft:
    """An exercise's validated attributes."""

    name: str
    category: str
    movement_pattern: str | None
    equipment: str | None
    location: str


def exercise_draft(
    *,
    name: str | None,
    category: str | None,
    movement_pattern: str | None = None,
    equipment: str | None = None,
    location: str | None,
) -> ExerciseDraft:
    """Validate an exercise form (name uniqueness is checked by `name_taken` against the others)."""
    problems: list[Problem] = []
    clean_name = _text(problems, "name", name, NAME_MAX, required=True)
    clean_category = _choice(problems, "category", category, EXERCISE_CATEGORIES)
    pattern = _text(problems, "movement_pattern", movement_pattern, PATTERN_MAX, required=False)
    clean_equipment = _text(problems, "equipment", equipment, EQUIPMENT_MAX, required=False)
    clean_location = _choice(problems, "location", location, LOCATIONS)
    _raise_if(problems)
    assert clean_name is not None and clean_category is not None and clean_location is not None
    return ExerciseDraft(clean_name, clean_category, pattern, clean_equipment, clean_location)


def sort_key(text: str) -> str:
    """Order of names and labels in lists: case and accents folded."""
    return normalise(text)


def name_taken(name: str, others: Iterable[str]) -> bool:
    """True when `name` equals one of `others` after `normalise` (case and accents folded)."""
    target = normalise(name)
    return any(normalise(other) == target for other in others)


def check_name(name: str, others: Iterable[str]) -> None:
    """Refuse `name` (`name_taken`) when another exercise of the user has it, archived included."""
    if name_taken(name, others):
        raise _refuse("name", "name_taken")


def known_spelling(value: str | None, existing: Iterable[str]) -> str | None:
    """The first existing spelling equal to `value` after `normalise`, else `value` (D-054)."""
    if value is None:
        return None
    target = normalise(value)
    return next((known for known in existing if normalise(known) == target), value)


# --- fields ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DefaultField:
    """A core field created with an exercise of a category."""

    quantity: str
    required: bool
    increment: int


_DEFAULT_FIELDS: dict[str, tuple[DefaultField, ...]] = {
    "strength": (DefaultField("reps", True, 1), DefaultField("weight", True, 2500)),
    "kettlebell": (DefaultField("reps", True, 1), DefaultField("weight", True, 2500)),
    "bodyweight": (DefaultField("reps", True, 1),),
    "cardio": (DefaultField("duration", True, 30), DefaultField("distance", False, 100)),
    "intervals": (DefaultField("duration", True, 30),),
}


def default_fields(category: str) -> tuple[DefaultField, ...]:
    """The core fields a new exercise of `category` starts with (D-054)."""
    return _DEFAULT_FIELDS[category]


@dataclass(frozen=True)
class FieldKind:
    """What a field holds: a kind (`domain/units` numeric kinds, `enum`, `bool`, `text`), the
    decimal scale of a `decimal` variable and the keys of an `enum` one."""

    kind: str
    scale: int | None = None
    enum_keys: tuple[str, ...] = ()

    @property
    def numeric(self) -> bool:
        """True for kinds typed as numbers (steps and proposed values allowed)."""
        return self.kind in units.NUMERIC_KINDS


def core_kind(core_quantity: str) -> FieldKind:
    """The kind of a core quantity field."""
    if core_quantity not in CORE_QUANTITIES:
        raise _refuse("source", "invalid_choice")
    return FieldKind(units.kind_of_quantity(core_quantity))


def variable_kind(draft: VariableDraft) -> FieldKind:
    """The kind of a field linking the variable `draft`."""
    keys = tuple(value.key for value in draft.enum_values or ())
    return FieldKind(draft.type, draft.decimal_scale, keys)


@dataclass(frozen=True)
class FieldParams:
    """Parameters of an `exercise_field` row, canonical integers."""

    required: bool = False
    increment: int | None = None
    discrete_values: tuple[int, ...] | None = None
    default_int: int | None = None
    default_text: str | None = None


def field_params(
    kind: FieldKind,
    *,
    required: bool,
    increment: str | None = None,
    discrete_values: str | None = None,
    default: str | None = None,
) -> FieldParams:
    """Parse a field form typed in display units and check it (`check_field`)."""
    problems: list[Problem] = []
    step = _parse_number(problems, "increment", kind, increment)
    values = _parse_values(problems, kind, discrete_values)
    default_int, default_text = _parse_default(problems, kind, default)
    _raise_if(problems)
    ordered = tuple(sorted(values)) if values is not None else None
    params = FieldParams(required, step, ordered, default_int, default_text)
    check_field(kind, params)
    return params


def _parse_number(problems: list[Problem], name: str, kind: FieldKind, raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if not kind.numeric:
        problems.append(Problem(name, "invalid_choice"))
        return None
    try:
        return units.parse(kind.kind, text, scale=kind.scale)
    except units.UnitError as error:
        problems.append(Problem(name, error.code, {"value": text}))
        return None


def _parse_values(problems: list[Problem], kind: FieldKind, raw: str | None) -> tuple[int, ...] | None:
    tokens: list[str] = []
    for token in _VALUE_SEPARATORS.split((raw or "").strip()):
        if token.lower() in _UNIT_TOKENS and tokens:
            tokens[-1] = f"{tokens[-1]} {token}"
        elif token:
            tokens.append(token)
    if not tokens:
        return None
    if not kind.numeric:
        problems.append(Problem("discrete_values", "invalid_choice"))
        return None
    before = len(problems)
    parsed = [_parse_number(problems, "discrete_values", kind, token) for token in tokens]
    if len(problems) > before:
        return None
    return tuple(value for value in parsed if value is not None)


def _parse_default(
    problems: list[Problem], kind: FieldKind, raw: str | None
) -> tuple[int | None, str | None]:
    text = (raw or "").strip()
    if not text:
        return None, None
    if kind.numeric:
        return _parse_number(problems, "default", kind, text), None
    if kind.kind == BOOL:
        if text not in BOOL_VALUES:
            problems.append(Problem("default", "invalid_choice"))
            return None, None
        return BOOL_VALUES[text], None
    if kind.kind == TEXT and len(text) > TEXT_DEFAULT_MAX:
        problems.append(Problem("default", "too_long", {"max": TEXT_DEFAULT_MAX}))
    return None, text


def check_field(kind: FieldKind, params: FieldParams) -> None:
    """The rules of a field's parameters on canonical values (UI and seed alike)."""
    problems: list[Problem] = []
    if params.increment is not None:
        if not kind.numeric:
            problems.append(Problem("increment", "invalid_choice"))
        elif params.increment <= 0:
            problems.append(Problem("increment", "must_be_positive"))
    if params.discrete_values is not None:
        problems.extend(_values_problems(kind, params.discrete_values))
    if params.increment is not None and params.discrete_values is not None:
        problems.append(Problem("increment", "increment_with_discrete"))
    problems.extend(_default_problems(kind, params))
    _raise_if(problems)


def _values_problems(kind: FieldKind, values: Sequence[int]) -> list[Problem]:
    name = "discrete_values"
    if not kind.numeric:
        return [Problem(name, "invalid_choice")]
    if not values:
        return [Problem(name, "values_required")]
    if len(values) > DISCRETE_MAX:
        return [Problem(name, "too_many_values", {"max": DISCRETE_MAX})]
    problems = [Problem(name, "must_be_positive")] if min(values) <= 0 else []
    duplicates = sorted({value for value in values if values.count(value) > 1})
    problems.extend(
        Problem(name, "duplicate_value", {"value": units.input_text(kind.kind, value, scale=kind.scale)})
        for value in duplicates
    )
    return problems


def _default_problems(kind: FieldKind, params: FieldParams) -> list[Problem]:
    if params.default_int is not None and params.default_text is not None:
        return [Problem("default", "invalid_choice")]
    if params.default_text is not None:
        if kind.kind == ENUM and params.default_text not in kind.enum_keys:
            return [Problem("default", "invalid_choice")]
        if kind.kind not in (ENUM, TEXT):
            return [Problem("default", "invalid_choice")]
    if params.default_int is not None:
        if kind.kind == BOOL:
            return (
                [] if params.default_int in BOOL_VALUES.values() else [Problem("default", "invalid_choice")]
            )
        if not kind.numeric:
            return [Problem("default", "invalid_choice")]
        if params.discrete_values is not None and params.default_int not in params.discrete_values:
            return [Problem("default", "default_not_in_values")]
    return []


def cleared_for(kind: FieldKind, params: FieldParams) -> FieldParams:
    """`params` minus what `kind` no longer allows (a variable's type changed): step, values and
    a default that does not fit are dropped; `required` stays."""
    try:
        check_field(kind, params)
    except CatalogError:
        return FieldParams(required=params.required)
    return params


@dataclass(frozen=True)
class FieldSource:
    """A field as `check_measures` sees it: a core quantity, or a variable's scope."""

    core_quantity: str | None = None
    variable_scope: str | None = None

    @property
    def is_measure(self) -> bool:
        """A core quantity or a `set`-scope variable is a measure of the set."""
        return self.core_quantity is not None or self.variable_scope == "set"


def check_measures(fields: Iterable[FieldSource]) -> None:
    """An exercise keeps at least one measure (`last_measure` otherwise)."""
    if not any(source.is_measure for source in fields):
        raise _refuse("field", "last_measure")


# --- aliases -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasDraft:
    """A validated alias and its normalised form (stored for search)."""

    alias: str
    normalised: str


def alias_draft(raw: str | None, exercise_name: str, existing: Iterable[str]) -> AliasDraft:
    """Validate an alias of an exercise; `existing` are its other aliases (any spelling)."""
    problems: list[Problem] = []
    alias = _text(problems, "alias", raw, ALIAS_MAX, required=True)
    _raise_if(problems)
    assert alias is not None
    folded = normalise(alias)
    if not folded:
        raise _refuse("alias", "required")
    if folded == normalise(exercise_name):
        raise _refuse("alias", "alias_is_name")
    if any(normalise(other) == folded for other in existing):
        raise _refuse("alias", "alias_taken")
    return AliasDraft(alias, folded)
