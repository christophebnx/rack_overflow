"""Rules of session logging (D-061 to D-063, D-065): start, plan order, current item, prefill,
steppers and the validation of a set or settings form.

Pure: the clock value, the time zone and every stored fact are passed in. Field values are
canonical integers (`domain/units`) or text (enum keys, free text), keyed by the field's form name:
a core quantity (`reps`, `weight`, `duration`, `distance`) or `var_<variable id>`. Refusals are
`domain.catalog.CatalogError`s, rendered by `web/` like every catalog form.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from rack_overflow.domain import units
from rack_overflow.domain.catalog import (
    BOOL,
    BOOL_VALUES,
    ENUM,
    TEXT,
    TEXT_DEFAULT_MAX,
    FieldKind,
    FieldParams,
    Problem,
    choice_input,
    raise_if,
)
from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.templates import Target
from rack_overflow.domain.vocabulary import SESSION_LOCATIONS, SET_TYPES

DEFAULT_LOCATION = "gym"
BOTH = "both"
WARMUP, WORK, RM_TEST = SET_TYPES
RM_TEST_CATEGORIES: tuple[str, ...] = ("strength",)
"""Categories offering the « Test RM » set type."""
VARIABLE_PREFIX = "var_"
EMPTY_SET_FIELD = "set"
UP, DOWN = "up", "down"
STEP_DIRECTIONS: tuple[str, ...] = (UP, DOWN)

type FieldValue = int | str


class SessionError(DomainError):
    """A session action refused for a reason other than an input (`code` is stable, e.g.
    `session_closed`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --- start ---------------------------------------------------------------------------------------


def local_start(now: datetime, tz: tzinfo) -> tuple[str, str]:
    """The local date (`YYYY-MM-DD`) of `now` in `tz` and the zone's IANA name (D-065)."""
    local = now.astimezone(tz)
    return local.date().isoformat(), str(getattr(tz, "key", None) or tz)


def default_location(last_location: str | None) -> str:
    """The location preselected at start: the last session's, else the gym (D-061)."""
    return last_location if last_location in SESSION_LOCATIONS else DEFAULT_LOCATION


def matches_location(template_location: str, location: str) -> bool:
    """True when a template of `template_location` is offered for a session at `location`."""
    return template_location in (location, BOTH)


def templates_for[T](location: str, templates: Iterable[tuple[T, str]]) -> list[T]:
    """The templates offered at `location`, in the given order: `(template, its location)` pairs
    of non-archived templates whose location is `location` or `both`."""
    return [item for item, place in templates if matches_location(place, location)]


@dataclass(frozen=True)
class PlanSlot:
    """A live template slot as a session sees it: `menu` or not, and the exercise ids it can
    offer (non-archived; a fixed slot has at most one)."""

    id: int
    menu: bool
    choices: tuple[int, ...]

    @property
    def skipped(self) -> bool:
        """True when nothing can be logged from it (D-058)."""
        return not self.choices


@dataclass(frozen=True)
class StartPlan:
    """What starting a session from a template writes: `(slot id, exercise id)` rows in slot
    order, and the menus left to pick."""

    rows: tuple[tuple[int, int], ...]
    pending: tuple[int, ...]


def start_plan(slots: Sequence[PlanSlot]) -> StartPlan:
    """Fixed slots and menus with one available option become rows; other menus are pending;
    slots offering nothing are skipped (D-058, D-061)."""
    rows: list[tuple[int, int]] = []
    pending: list[int] = []
    for slot in slots:
        if slot.skipped:
            continue
        if not slot.menu or len(slot.choices) == 1:
            rows.append((slot.id, slot.choices[0]))
        else:
            pending.append(slot.id)
    return StartPlan(tuple(rows), tuple(pending))


# --- plan order ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RowRef:
    """A session row (`session_exercise`) as ordering sees it."""

    id: int
    slot_id: int | None
    position: int


@dataclass(frozen=True)
class Item:
    """One item of the session plan: a row, or a pending menu (`menu_slot_id`)."""

    row_id: int | None = None
    menu_slot_id: int | None = None

    @property
    def is_menu(self) -> bool:
        """True for a menu still to pick."""
        return self.row_id is None


def display_sequence(slots: Sequence[PlanSlot], rows: Sequence[RowRef]) -> list[Item]:
    """The plan in display order (D-061): the template's live slots in order, each with its rows
    or, for a menu without row that can still offer something, its pending card; then every other
    row (added exercises, rows of removed slots) by position."""
    ordered = sorted(rows, key=lambda row: (row.position, row.id))
    by_slot: dict[int, list[RowRef]] = {}
    for row in ordered:
        if row.slot_id is not None:
            by_slot.setdefault(row.slot_id, []).append(row)
    items: list[Item] = []
    placed: set[int] = set()
    for slot in slots:
        slot_rows = by_slot.get(slot.id, [])
        items.extend(Item(row_id=row.id) for row in slot_rows)
        placed.update(row.id for row in slot_rows)
        if not slot_rows and slot.menu and not slot.skipped:
            items.append(Item(menu_slot_id=slot.id))
    items.extend(Item(row_id=row.id) for row in ordered if row.id not in placed)
    return items


def current_item(
    sequence: Sequence[Item], latest_set_row_id: int | None, requested: Item | None
) -> Item | None:
    """The item shown expanded: `requested` when it is in the plan, else the row of the latest
    live set, else the first item (None for an empty plan)."""
    if requested is not None and requested in sequence:
        return requested
    latest = Item(row_id=latest_set_row_id)
    if latest_set_row_id is not None and latest in sequence:
        return latest
    return sequence[0] if sequence else None


def following(sequence: Sequence[Item], item: Item) -> Item | None:
    """The item after `item` in the plan (None at the end or when absent)."""
    if item not in sequence:
        return None
    index = sequence.index(item) + 1
    return sequence[index] if index < len(sequence) else None


# --- fields and prefill --------------------------------------------------------------------------


def variable_field(variable_id: int) -> str:
    """Form name of a variable's field."""
    return f"{VARIABLE_PREFIX}{variable_id}"


@dataclass(frozen=True)
class SessionField:
    """A live field of the exercise as the set or settings form uses it: its form `name`, kind
    and parameters, and its source (core quantity or variable id)."""

    name: str
    kind: FieldKind
    params: FieldParams
    core_quantity: str | None = None
    variable_id: int | None = None

    @property
    def stepped(self) -> bool:
        """True for a numeric field with an increment (a stepper)."""
        return self.kind.numeric and self.params.increment is not None


@dataclass(frozen=True)
class SetFacts:
    """A set's type and values (field name → canonical value; an absent name is empty)."""

    type: str
    values: Mapping[str, FieldValue] = field(default_factory=dict)

    def value(self, name: str) -> FieldValue | None:
        """The value of field `name`, None when empty."""
        return self.values.get(name)

    @property
    def is_empty(self) -> bool:
        """True when no value is set."""
        return not self.values


def set_types(category: str) -> tuple[str, ...]:
    """Set types offered for an exercise of `category` (« Test RM » for strength only)."""
    return SET_TYPES if category in RM_TEST_CATEGORIES else (WARMUP, WORK)


def _kept(values: Mapping[str, FieldValue], fields: Sequence[SessionField]) -> dict[str, FieldValue]:
    names = {item.name for item in fields}
    return {name: value for name, value in values.items() if name in names}


def _target_values(target: Target | None, fields: Sequence[SessionField]) -> dict[str, FieldValue]:
    """The target parts matching the exercise's fields (reps = the range's low end, D-059)."""
    if target is None:
        return {}
    parts = {"reps": target.reps_min, "duration": target.duration_s, "distance": target.distance_m}
    found: dict[str, FieldValue] = {}
    for item in fields:
        value = parts.get(item.core_quantity or "")
        if value is not None:
            found[item.name] = value
    return found


def _defaults(fields: Sequence[SessionField]) -> dict[str, FieldValue]:
    found: dict[str, FieldValue] = {}
    for item in fields:
        default = item.params.default_int if item.params.default_int is not None else item.params.default_text
        if default is not None:
            found[item.name] = default
    return found


def prefill(
    position: int,
    today: Sequence[SetFacts],
    last: Sequence[SetFacts],
    target: Target | None,
    fields: Sequence[SessionField],
) -> SetFacts:
    """The next set's prefill (D-062). `position` is the 0-based count of today's live sets,
    `today` those sets in order, `last` the last performance, `fields` the live measure fields."""
    previous = today[-1] if today else None
    planned = last[position] if position < len(last) else None
    kind = planned.type if planned else previous.type if previous else WORK
    if previous is not None and previous.type == kind:
        source = previous.values
    elif planned is not None:
        source = planned.values
    elif previous is not None:
        source = previous.values
    else:
        source = {**_defaults(fields), **_target_values(target, fields)}
    return SetFacts(kind, _kept(source, fields))


def settings_prefill(last: Mapping[int, FieldValue], fields: Sequence[SessionField]) -> dict[int, FieldValue]:
    """Settings shown for a row without stored settings (D-062): per variable, its latest value
    in an earlier session (`last`), else the field default."""
    found: dict[int, FieldValue] = {}
    for item in fields:
        assert item.variable_id is not None
        value = last.get(item.variable_id)
        if value is None:
            value = _defaults([item]).get(item.name)
        if value is not None:
            found[item.variable_id] = value
    return found


# --- steppers ------------------------------------------------------------------------------------


def stepped(params: FieldParams, value: int | None, direction: str) -> int | None:
    """`value` moved one increment `up` or `down` (D-063): empty + up → one increment, empty +
    down stays empty, never below 0 nor above `units.MAX_VALUE` (the largest value `units.parse`
    reads back), a value off the increment grid snaps to the next grid value in that direction. A
    field without increment keeps its value."""
    step = params.increment
    if step is None or direction not in STEP_DIRECTIONS:
        return value
    if value is None:
        return step if direction == UP else None
    below, rest = divmod(value, step)
    if direction == UP:
        return min(units.MAX_VALUE, (below + 1) * step)
    return max(0, (below if rest else below - 1) * step)


# --- form validation -----------------------------------------------------------------------------


def _parsed(problems: list[Problem], item: SessionField, raw: str | None) -> FieldValue | None:
    """The canonical value of one input, None when empty; a refusal is added to `problems`."""
    text = (raw or "").strip()
    if not text:
        if item.params.required:
            problems.append(Problem(item.name, "required"))
        return None
    kind = item.kind
    if kind.numeric:
        try:
            return units.parse(kind.kind, text, scale=kind.scale)
        except units.UnitError as error:
            problems.append(Problem(item.name, error.code, {"value": text}))
            return None
    if kind.kind == BOOL:
        return _choice(problems, item.name, BOOL_VALUES.get(text))
    if kind.kind == ENUM:
        return _choice(problems, item.name, text if text in kind.enum_keys else None)
    if kind.kind == TEXT and len(text) > TEXT_DEFAULT_MAX:
        problems.append(Problem(item.name, "too_long", {"max": TEXT_DEFAULT_MAX}))
        return None
    return text


def _choice(problems: list[Problem], name: str, value: FieldValue | None) -> FieldValue | None:
    if value is None:
        problems.append(Problem(name, "invalid_choice"))
    return value


def _values(
    problems: list[Problem], fields: Sequence[SessionField], raw_values: Mapping[str, str | None]
) -> dict[str, FieldValue]:
    found: dict[str, FieldValue] = {}
    for item in fields:
        value = _parsed(problems, item, raw_values.get(item.name))
        if value is not None:
            found[item.name] = value
    return found


def set_draft(
    category: str,
    fields: Sequence[SessionField],
    raw_type: str | None,
    raw_values: Mapping[str, str | None],
) -> SetFacts:
    """Validate a set form typed in display units (D-063): the type among `set_types(category)`,
    each measure field through `domain/units` and its kind; a set needs one value (`empty_set`)."""
    problems: list[Problem] = []
    kind = choice_input(problems, "type", raw_type, set_types(category))
    values = _values(problems, fields, raw_values)
    if not values and not problems:
        problems.append(Problem(EMPTY_SET_FIELD, "empty_set"))
    raise_if(problems)
    assert kind is not None
    return SetFacts(kind, values)


def setting_draft(
    fields: Sequence[SessionField], raw_values: Mapping[str, str | None]
) -> dict[int, FieldValue | None]:
    """Validate a settings form: variable id → canonical value, None for a cleared setting."""
    problems: list[Problem] = []
    values = _values(problems, fields, raw_values)
    raise_if(problems)
    result: dict[int, FieldValue | None] = {}
    for item in fields:
        assert item.variable_id is not None
        result[item.variable_id] = values.get(item.name)
    return result


def raw_texts(fields: Sequence[SessionField], values: Mapping[str, FieldValue]) -> dict[str, str]:
    """Canonical values as the inputs show them (`units.input_text` for numbers, keys and text
    as stored, booleans as `1` / `0`): the text a set form posts back unchanged."""
    texts: dict[str, str] = {}
    for item in fields:
        value = values.get(item.name)
        if value is None:
            continue
        if item.kind.numeric and isinstance(value, int):
            texts[item.name] = units.input_text(item.kind.kind, value, scale=item.kind.scale)
        else:
            texts[item.name] = str(value)
    return texts


def step_values(
    fields: Sequence[SessionField], raw_values: Mapping[str, str | None], step: str | None
) -> dict[str, str | None]:
    """The form's texts after one stepper tap `<field>:<up|down>` (D-063): the stepped field is
    parsed, moved and shown again; an unreadable value or an unknown step leaves the texts as
    typed (the ✓ will report the problem)."""
    texts = dict(raw_values)
    name, _, direction = (step or "").partition(":")
    item = next((f for f in fields if f.name == name and f.stepped), None)
    if item is None or direction not in STEP_DIRECTIONS:
        return texts
    problems: list[Problem] = []
    current = _parsed(problems, SessionField(item.name, item.kind, FieldParams()), texts.get(name))
    if problems or (current is not None and not isinstance(current, int)):
        return texts
    moved = stepped(item.params, current, direction)
    texts[name] = None if moved is None else units.input_text(item.kind.kind, moved, scale=item.kind.scale)
    return texts
