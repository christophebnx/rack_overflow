"""Session logging operations (D-061 to D-066), one transaction each, `user_id`, `now` and the
time zone passed in.

Rules live in `domain/sessions` (plan, prefill, steppers, forms) and `domain/indicators` (records,
volume); queries in `storage/sessions`. Unknown, foreign or deleted ids raise `NotFoundError`; a
write on a closed session raises `SessionError("session_closed")`; refused input raises
`CatalogError`. Records and volume are computed on every read, never stored (D-021, D-064).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import catalog, search
from rack_overflow.domain import sessions as rules
from rack_overflow.domain.catalog import CatalogError, EnumValue, Problem
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.indicators import LoggedSet, Volume, records, volume
from rack_overflow.domain.sessions import FieldValue, Item, SessionError, SessionField, SetFacts
from rack_overflow.domain.templates import MENU, Target
from rack_overflow.domain.timestamps import to_text
from rack_overflow.domain.vocabulary import SESSION_LOCATIONS
from rack_overflow.services import exercises as exercise_services
from rack_overflow.services.templates import SlotView, slots_for_session
from rack_overflow.storage import exercises as exercise_queries
from rack_overflow.storage import sessions as queries
from rack_overflow.storage import templates as template_queries
from rack_overflow.storage.errors import SessionOpenError
from rack_overflow.storage.sessions import CORE_COLUMNS

SESSION_CLOSED = "session_closed"
RECENT_LIMIT = 20
SETTING_SCOPE = "setting"


# --- views


@dataclass(frozen=True)
class ExerciseInfo:
    """An exercise as a session row, a menu option or a search result shows it."""

    id: int
    name: str
    category: str
    equipment: str | None
    archived: bool


@dataclass(frozen=True)
class FieldInfo:
    """A live field of a row's exercise: its rule view and what display needs (label of a
    variable, free unit, enum values)."""

    field: SessionField
    label: str | None = None
    unit: str | None = None
    enum_values: tuple[EnumValue, ...] = ()

    @property
    def name(self) -> str:
        """Form name (`reps`… or `var_<id>`)."""
        return self.field.name

    @property
    def core_quantity(self) -> str | None:
        """The core quantity, None for a variable."""
        return self.field.core_quantity

    @property
    def visible(self) -> bool:
        """Core quantities and required fields are always shown; optional variables are folded."""
        return self.field.core_quantity is not None or self.field.params.required

    def enum_label(self, key: FieldValue) -> str:
        """The label of an enum key (the key itself when unknown)."""
        return next((value.label for value in self.enum_values if value.key == key), str(key))


@dataclass(frozen=True)
class SetView:
    """A live set of today: its number in the row, its facts and whether it is a record."""

    id: int
    number: int
    facts: SetFacts
    record: bool


@dataclass(frozen=True)
class FormState:
    """The next-set form as shown: its set type and the text of each input (display units)."""

    type: str
    texts: Mapping[str, str | None]
    open_more: bool = False


@dataclass(frozen=True)
class RowCard:
    """A row as its plan card shows it."""

    id: int
    exercise: ExerciseInfo
    slot_id: int | None
    target: Target | None
    set_count: int
    record_count: int


class RowFacts:
    """What the set edit and settings forms read from a row, shared by an open session's block
    (`RowView`) and a closed session's exercise (`SummaryRow`, the L5 detail)."""

    fields: tuple[FieldInfo, ...]
    setting_fields: tuple[FieldInfo, ...]
    settings: Mapping[int, FieldValue]
    sets: tuple[SetView, ...]

    @property
    def settings_texts(self) -> dict[str, str]:
        """The settings as their inputs show them (display units, keys)."""
        values = {
            item.name: self.settings[item.field.variable_id]
            for item in self.setting_fields
            if item.field.variable_id in self.settings
        }
        return rules.raw_texts([item.field for item in self.setting_fields], values)

    def set_texts(self, item: SetView) -> dict[str, str]:
        """A set's values as its edit form shows them."""
        return rules.raw_texts([field.field for field in self.fields], item.facts.values)

    def set(self, set_id: int) -> SetView | None:
        """The row's live set `set_id`, None when absent."""
        return next((item for item in self.sets if item.id == set_id), None)


@dataclass(frozen=True)
class RowView(RowFacts):
    """The current row expanded: fields, settings, today's sets with records, the next-set form
    and what a pick change can offer."""

    card: RowCard
    menu_label: str | None
    fields: tuple[FieldInfo, ...]
    setting_fields: tuple[FieldInfo, ...]
    settings: Mapping[int, FieldValue]
    sets: tuple[SetView, ...]
    form: FormState
    has_facts: bool
    change_options: tuple[ExerciseInfo, ...]
    types: tuple[str, ...]

    @property
    def id(self) -> int:
        """The row id."""
        return self.card.id

    @property
    def exercise(self) -> ExerciseInfo:
        """The row's exercise."""
        return self.card.exercise

    @property
    def number(self) -> int:
        """Number of the next set (live sets + 1)."""
        return len(self.sets) + 1

    @property
    def more_fields(self) -> tuple[FieldInfo, ...]:
        """Optional variables folded under « Autres valeurs »."""
        return tuple(item for item in self.fields if not item.visible)


@dataclass(frozen=True)
class MenuView:
    """A pending menu: its label, target and the available options in menu order."""

    slot_id: int
    label: str
    target: Target
    options: tuple[ExerciseInfo, ...]


@dataclass(frozen=True)
class SessionInfo:
    """A session's own attributes."""

    id: int
    title: str | None
    location: str
    local_date: str
    time_zone: str
    started_at: str
    ended_at: str | None

    @property
    def closed(self) -> bool:
        """True once the session is closed."""
        return self.ended_at is not None


@dataclass(frozen=True)
class SessionView:
    """An open session: the plan in display order, cards, pending menus and the current item,
    expanded in `block` when it is a row."""

    session: SessionInfo
    items: tuple[Item, ...]
    cards: Mapping[int, RowCard]
    menus: Mapping[int, MenuView]
    current: Item | None
    block: RowView | None

    def name_of(self, item: Item) -> str:
        """The exercise name of a row, the label of a menu."""
        if item.row_id is not None:
            return self.cards[item.row_id].exercise.name
        assert item.menu_slot_id is not None
        return self.menus[item.menu_slot_id].label

    def number_of(self, item: Item) -> int:
        """1-based display number of the item."""
        return self.items.index(item) + 1

    def next_after(self, item: Item | None) -> Item | None:
        """The item following `item` in the plan."""
        return rules.following(self.items, item) if item is not None else None


@dataclass(frozen=True)
class SummaryRow(RowFacts):
    """One exercise of a closed session with at least one live set (or the row just corrected,
    L5): its live sets with ⭐, stored settings, fields and volume; the detail's correction forms
    read it like an open block (`RowFacts`)."""

    id: int
    exercise: ExerciseInfo
    fields: tuple[FieldInfo, ...]
    setting_fields: tuple[FieldInfo, ...]
    settings: Mapping[int, FieldValue]
    sets: tuple[SetView, ...]
    volume: Volume
    types: tuple[str, ...]

    @property
    def warmups(self) -> int:
        """Number of warm-up sets."""
        return sum(1 for item in self.sets if item.facts.type == rules.WARMUP)

    @property
    def records(self) -> int:
        """Number of record sets."""
        return sum(1 for item in self.sets if item.record)


@dataclass(frozen=True)
class SummaryView:
    """A closed session: per exercise its sets, volume and records, then the totals."""

    session: SessionInfo
    rows: tuple[SummaryRow, ...]

    def row(self, row_id: int) -> SummaryRow | None:
        """The exercise of row `row_id`, None when absent."""
        return next((item for item in self.rows if item.id == row_id), None)

    @property
    def total_sets(self) -> int:
        """Counted (work and RM-test) sets."""
        return sum(row.volume.sets for row in self.rows)

    @property
    def total_load_g(self) -> int:
        """Σ reps * load of every exercise, grams."""
        return sum(row.volume.load_g for row in self.rows)

    @property
    def total_records(self) -> int:
        """Record sets of the session."""
        return sum(row.records for row in self.rows)


@dataclass(frozen=True)
class StartTemplate:
    """A template offered at start."""

    id: int
    name: str
    location: str
    last_used: bool


@dataclass(frozen=True)
class OpenSession:
    """The open session as home shows it."""

    session: SessionInfo
    exercises: int
    sets: int


@dataclass(frozen=True)
class StartPage:
    """Home: the open session, or the start choices (preselected location, templates)."""

    open: OpenSession | None
    location: str
    templates: tuple[StartTemplate, ...] = ()

    def offered(self, location: str) -> bool:
        """True when a template is offered at `location`."""
        return any(rules.matches_location(item.location, location) for item in self.templates)


@dataclass(frozen=True)
class SearchResults:
    """Exercises to add: with an empty query the recent ones then the others by name, else one
    ranked list (`ranked`)."""

    query: str
    recent: tuple[ExerciseInfo, ...] = ()
    others: tuple[ExerciseInfo, ...] = ()
    ranked: tuple[ExerciseInfo, ...] = ()

    @property
    def count(self) -> int:
        """Number of results."""
        return len(self.recent) + len(self.others) + len(self.ranked)


@dataclass(frozen=True)
class SetRef:
    """Where a set lives: its session, its row, whether the session is closed."""

    session_id: int
    row_id: int
    closed: bool


@dataclass(frozen=True)
class _Context:
    """One read of a session's plan inside a transaction."""

    session: SessionInfo
    template_id: int | None
    slots: tuple[SlotView, ...]
    rows: tuple[sa.Row, ...]
    sets: Mapping[int, tuple[sa.Row, ...]]
    items: tuple[Item, ...] = field(default=())


# --- reading helpers


def session_info(connection: sa.Connection, row: sa.Row) -> SessionInfo:
    """A session row's own attributes, with its template's name as title (None: free session)."""
    title = None
    if row.template_id is not None:
        template = template_queries.get(connection, row.user_id, row.template_id)
        title = template.name if template is not None else None
    return SessionInfo(
        row.id, title, row.location, row.local_date, row.time_zone, row.started_at, row.ended_at
    )


def _session_row(connection: sa.Connection, user_id: int, session_id: int, *, writable: bool) -> sa.Row:
    row = queries.get_session(connection, user_id, session_id)
    if row is None:
        raise NotFoundError(f"no session {session_id}")
    if writable and row.status != "open":
        raise SessionError(SESSION_CLOSED)
    return row


def _exercise(row: sa.Row) -> ExerciseInfo:
    return ExerciseInfo(
        row.exercise_id, row.exercise_name, row.category, row.equipment, row.exercise_archived_at is not None
    )


def _plan_slot(slot: SlotView) -> rules.PlanSlot:
    if slot.exercise is not None:
        choices = () if slot.exercise.archived else (slot.exercise.id,)
    else:
        choices = tuple(option.exercise.id for option in slot.options if not option.exercise.archived)
    return rules.PlanSlot(slot.id, slot.kind == MENU, choices)


def _context(connection: sa.Connection, row: sa.Row) -> _Context:
    slots = tuple(slots_for_session(connection, row.template_id)) if row.template_id is not None else ()
    rows = tuple(queries.session_exercises(connection, row.id))
    by_row: dict[int, list[sa.Row]] = {}
    for item in queries.sets_of(connection, [r.id for r in rows]):
        by_row.setdefault(item.session_exercise_id, []).append(item)
    refs = [rules.RowRef(r.id, r.template_slot_id, r.position) for r in rows]
    items = tuple(rules.display_sequence([_plan_slot(slot) for slot in slots], refs))
    return _Context(
        session_info(connection, row),
        row.template_id,
        slots,
        rows,
        {key: tuple(value) for key, value in by_row.items()},
        items,
    )


def _slot(context: _Context, slot_id: int | None) -> SlotView | None:
    return next((slot for slot in context.slots if slot.id == slot_id), None)


def _menu_view(connection: sa.Connection, user_id: int, slot: SlotView) -> MenuView:
    options = []
    for option in slot.options:
        if not option.exercise.archived:
            row = exercise_queries.get(connection, user_id, option.exercise.id)
            assert row is not None
            options.append(ExerciseInfo(row.id, row.name, row.category, row.equipment, False))
    return MenuView(slot.id, slot.label or "", slot.target, tuple(options))


def exercise_fields(
    connection: sa.Connection, exercise_id: int
) -> tuple[tuple[FieldInfo, ...], tuple[FieldInfo, ...]]:
    """The exercise's live measure fields and setting fields (archived variables left out)."""
    measures: list[FieldInfo] = []
    settings: list[FieldInfo] = []
    for view in exercise_services.field_views(connection, exercise_id):
        if view.variable is None:
            quantity = view.core_quantity
            assert quantity is not None
            measures.append(FieldInfo(SessionField(quantity, view.kind, view.params, core_quantity=quantity)))
        elif not view.variable.archived:
            draft = view.variable.draft
            rule = SessionField(
                rules.variable_field(view.variable.id), view.kind, view.params, variable_id=view.variable.id
            )
            info = FieldInfo(rule, draft.label, draft.unit, draft.enum_values or ())
            (settings if draft.scope == SETTING_SCOPE else measures).append(info)
    return tuple(measures), tuple(settings)


def _facts(row: sa.Row, values: Mapping[int, FieldValue]) -> SetFacts:
    found: dict[str, FieldValue] = {}
    for quantity, column in CORE_COLUMNS.items():
        if row._mapping[column] is not None:
            found[quantity] = row._mapping[column]
    for variable_id, value in values.items():
        found[rules.variable_field(variable_id)] = value
    return SetFacts(row.type, found)


def logged_set(row: sa.Row, session_id: int, local_date: str = "") -> LoggedSet:
    """A stored set as the indicators read it (`domain.indicators.LoggedSet`)."""
    return LoggedSet(
        row.type, row.reps, row.weight_g, row.duration_s, row.distance_m, session_id, local_date, row.id
    )


def _starred(
    connection: sa.Connection, user_id: int, exercise: ExerciseInfo, set_ids: Sequence[int]
) -> set[int]:
    """Ids among `set_ids` that are records, from the exercise's whole history (D-064)."""
    if not set_ids:
        return set()
    history = queries.record_history(connection, user_id, exercise.id)
    index = {row.id: position for position, row in enumerate(history)}
    wanted = {index[set_id] for set_id in set_ids if set_id in index}
    found = records(exercise.category, [logged_set(row, row.session_id) for row in history], wanted)
    return {history[position].id for position in found}


def set_views(
    connection: sa.Connection, user_id: int, exercise: ExerciseInfo, rows: Sequence[sa.Row]
) -> tuple[SetView, ...]:
    """Live sets of one row (or one session's sets of an exercise) numbered, with ⭐ from the
    exercise's whole history."""
    values = queries.values_of(connection, [row.id for row in rows])
    stars = _starred(connection, user_id, exercise, [row.id for row in rows])
    return tuple(
        SetView(row.id, number, _facts(row, values.get(row.id, {})), row.id in stars)
        for number, row in enumerate(rows, start=1)
    )


def _card(
    connection: sa.Connection, user_id: int, context: _Context, row: sa.Row, *, with_records: bool
) -> RowCard:
    sets = context.sets.get(row.id, ())
    slot = _slot(context, row.template_slot_id)
    exercise = _exercise(row)
    stars = _starred(connection, user_id, exercise, [item.id for item in sets]) if with_records else set()
    return RowCard(
        row.id, exercise, row.template_slot_id, slot.target if slot else None, len(sets), len(stars)
    )


def _change_options(
    connection: sa.Connection, user_id: int, slot: SlotView | None, exercise_id: int
) -> tuple[ExerciseInfo, ...]:
    if slot is None or slot.kind != MENU:
        return ()
    menu = _menu_view(connection, user_id, slot)
    return tuple(option for option in menu.options if option.id != exercise_id)


def _prefill_form(
    connection: sa.Connection,
    user_id: int,
    context: _Context,
    row: sa.Row,
    fields: Sequence[FieldInfo],
    sets: Sequence[SetView],
    target: Target | None,
) -> FormState:
    last_rows = queries.last_performance(connection, user_id, row.exercise_id, context.session.id)
    last_values = queries.values_of(connection, [item.id for item in last_rows])
    last = [_facts(item, last_values.get(item.id, {})) for item in last_rows]
    rule_fields = [item.field for item in fields]
    facts = rules.prefill(len(sets), [item.facts for item in sets], last, target, rule_fields)
    return FormState(facts.type, rules.raw_texts(rule_fields, facts.values))


def _settings(
    connection: sa.Connection, user_id: int, context: _Context, row: sa.Row, fields: Sequence[FieldInfo]
) -> dict[int, FieldValue]:
    """The row's stored settings over the prefill of the missing ones (D-062)."""
    if not fields:
        return {}
    last = queries.last_settings(connection, user_id, row.exercise_id, context.session.id)
    shown = rules.settings_prefill(last, [item.field for item in fields])
    shown.update(queries.settings_of(connection, row.id))
    return shown


def _row_view(
    connection: sa.Connection, user_id: int, context: _Context, row: sa.Row, form: FormState | None
) -> RowView:
    exercise = _exercise(row)
    slot = _slot(context, row.template_slot_id)
    fields, setting_fields = exercise_fields(connection, exercise.id)
    sets = set_views(connection, user_id, exercise, context.sets.get(row.id, ()))
    target = slot.target if slot is not None else None
    has_facts = queries.has_facts(connection, row.id)
    card = RowCard(row.id, exercise, row.template_slot_id, target, len(sets), sum(s.record for s in sets))
    return RowView(
        card=card,
        menu_label=slot.label if slot is not None and slot.kind == MENU else None,
        fields=fields,
        setting_fields=setting_fields,
        settings=_settings(connection, user_id, context, row, setting_fields),
        sets=sets,
        form=form or _prefill_form(connection, user_id, context, row, fields, sets, target),
        has_facts=has_facts,
        change_options=() if has_facts else _change_options(connection, user_id, slot, exercise.id),
        types=rules.set_types(exercise.category),
    )


def _row(context: _Context, row_id: int) -> sa.Row:
    found = next((row for row in context.rows if row.id == row_id), None)
    if found is None:
        raise NotFoundError(f"no row {row_id} in session {context.session.id}")
    return found


def _latest_set_row(context: _Context) -> int | None:
    latest = max(
        (item for rows in context.sets.values() for item in rows),
        key=lambda item: (item.completed_at or "", item.id),
        default=None,
    )
    return latest.session_exercise_id if latest is not None else None


def _view(
    connection: sa.Connection,
    user_id: int,
    context: _Context,
    requested: Item | None,
    *,
    form: FormState | None = None,
    with_records: bool = True,
) -> SessionView:
    current = rules.current_item(context.items, _latest_set_row(context), requested)
    cards = {
        row.id: _card(connection, user_id, context, row, with_records=with_records) for row in context.rows
    }
    menus = {
        item.menu_slot_id: _menu_view(connection, user_id, slot)
        for item in context.items
        if item.menu_slot_id is not None and (slot := _slot(context, item.menu_slot_id)) is not None
    }
    block = None
    if current is not None and current.row_id is not None:
        block = _row_view(connection, user_id, context, _row(context, current.row_id), form)
        cards[block.id] = block.card
    return SessionView(context.session, context.items, cards, menus, current, block)


def _block(
    connection: sa.Connection, user_id: int, session_row: sa.Row, row_id: int, form: FormState | None = None
) -> SessionView:
    """The view answering an action on one row: that row current and expanded, cards without
    record counts (the fragment holds only the block)."""
    context = _context(connection, session_row)
    _row(context, row_id)
    return _view(connection, user_id, context, Item(row_id=row_id), form=form, with_records=False)


# --- start, home, page


def start_page(engine: Engine, user_id: int) -> StartPage:
    """Home: the open session with its counts, else the preselected location (last session's,
    else gym), the non-archived templates in order and which one was used last (D-061)."""
    with engine.begin() as connection:
        found = queries.open_session(connection, user_id)
        if found is not None:
            context = _context(connection, found)
            logged = [rows for rows in context.sets.values() if rows]
            sets = sum(len(rows) for rows in logged)
            return StartPage(OpenSession(context.session, len(logged), sets), found.location)
        latest = queries.latest_session(connection, user_id)
        last_template = latest.template_id if latest is not None else None
        templates = template_queries.list_all(connection, user_id, include_archived=False)
        return StartPage(
            None,
            rules.default_location(latest.location if latest is not None else None),
            tuple(StartTemplate(t.id, t.name, t.location, t.id == last_template) for t in templates),
        )


def start(
    engine: Engine, user_id: int, template_id: int | None, location: str | None, now: datetime, tz: tzinfo
) -> int:
    """Start a session (empty, or from a non-archived template of the user) and return its id;
    with a session already open, return that one instead (double tap, second device, D-061)."""
    with engine.begin() as connection:
        found = queries.open_session(connection, user_id)
        if found is not None:
            return int(found.id)
        problems: list[Problem] = []
        clean_location = catalog.choice_input(problems, "location", location, SESSION_LOCATIONS)
        slots = _start_slots(connection, user_id, template_id, problems)
        catalog.raise_if(problems)
        assert clean_location is not None
        local_date, zone = rules.local_start(now, tz)
        try:
            session_id = queries.insert_session(
                connection,
                user_id,
                local_date=local_date,
                time_zone=zone,
                started_at=to_text(now),
                location=clean_location,
                template_id=template_id,
            )
        except SessionOpenError:
            raced = queries.open_session(connection, user_id)
            assert raced is not None
            return int(raced.id)
        for slot_id, exercise_id in rules.start_plan([_plan_slot(slot) for slot in slots]).rows:
            queries.insert_session_exercise(connection, session_id, exercise_id, slot_id)
        return session_id


def _start_slots(
    connection: sa.Connection, user_id: int, template_id: int | None, problems: list[Problem]
) -> list[SlotView]:
    if template_id is None:
        return []
    template = template_queries.get(connection, user_id, template_id)
    if template is None or template.archived_at is not None:
        problems.append(Problem("template_id", "template_unavailable"))
        return []
    return slots_for_session(connection, template_id)


def show(
    engine: Engine, user_id: int, session_id: int, requested: Item | None = None
) -> SessionView | SummaryView:
    """The session page: the open session's plan with its current item (`requested` when valid),
    or the summary of a closed session."""
    with engine.begin() as connection:
        row = _session_row(connection, user_id, session_id, writable=False)
        if row.status != "open":
            return _summary(connection, user_id, row)
        return _view(connection, user_id, _context(connection, row), requested)


def _summary_row(connection: sa.Connection, user_id: int, context: _Context, row: sa.Row) -> SummaryRow:
    exercise = _exercise(row)
    stored = context.sets.get(row.id, ())
    fields, setting_fields = exercise_fields(connection, exercise.id)
    logged = [logged_set(entry, context.session.id) for entry in stored]
    return SummaryRow(
        fields=fields,
        setting_fields=setting_fields,
        settings=queries.settings_of(connection, row.id),
        sets=set_views(connection, user_id, exercise, stored),
        id=row.id,
        exercise=exercise,
        volume=volume(exercise.category, logged),
        types=rules.set_types(exercise.category),
    )


def _summary(
    connection: sa.Connection, user_id: int, session_row: sa.Row, keep_row: int | None = None
) -> SummaryView:
    """The closed session's exercises with a live set, plan order; `keep_row` stays even when its
    last set was just deleted (the detail keeps the section the user worked in, L5)."""
    context = _context(connection, session_row)
    rows = [
        _summary_row(connection, user_id, context, _row(context, item.row_id))
        for item in context.items
        if item.row_id is not None and (context.sets.get(item.row_id) or item.row_id == keep_row)
    ]
    return SummaryView(context.session, tuple(rows))


def _answer(
    connection: sa.Connection, user_id: int, session_row: sa.Row, row_id: int
) -> SessionView | SummaryView:
    """The answer to a correction of row `row_id`: its block while the session is open, the
    closed session's detail otherwise (D-067)."""
    if session_row.status == "open":
        return _block(connection, user_id, session_row, row_id)
    return _summary(connection, user_id, session_row, keep_row=row_id)


# --- plan changes


def _pending_menu(context: _Context, slot_id: int) -> SlotView:
    slot = _slot(context, slot_id)
    if slot is None or slot.kind != MENU:
        raise NotFoundError(f"no menu {slot_id} in session {context.session.id}")
    if any(row.template_slot_id == slot_id for row in context.rows):
        raise CatalogError([Problem("exercise_id", "slot_already_picked")])
    return slot


def _offered(connection: sa.Connection, user_id: int, slot: SlotView | None, exercise_id: int | None) -> int:
    """`exercise_id` when the menu `slot` offers it (any non-archived exercise without slot)."""
    if exercise_id is None:
        raise CatalogError([Problem("exercise_id", "required")])
    if slot is not None:
        available = {option.id for option in _menu_view(connection, user_id, slot).options}
        if exercise_id not in available:
            raise CatalogError([Problem("exercise_id", "exercise_unavailable")])
        return exercise_id
    row = exercise_queries.get(connection, user_id, exercise_id)
    if row is None or row.archived_at is not None:
        raise CatalogError([Problem("exercise_id", "exercise_unavailable")])
    return exercise_id


def pick(
    engine: Engine, user_id: int, session_id: int, slot_id: int | None, exercise_id: int | None
) -> SessionView:
    """Pick the exercise of a pending menu (`slot_id`), or add one outside the template; the plan
    with the new row current."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=True)
        context = _context(connection, session_row)
        slot = _pending_menu(context, slot_id) if slot_id is not None else None
        chosen = _offered(connection, user_id, slot, exercise_id)
        row_id = queries.insert_session_exercise(connection, session_id, chosen, slot_id)
        return _view(connection, user_id, _context(connection, session_row), Item(row_id=row_id))


def change_exercise(
    engine: Engine, user_id: int, session_id: int, row_id: int, exercise_id: int | None
) -> SessionView:
    """Change the exercise of a row holding no fact (`exercise_has_sets` otherwise): another
    available option of its menu, or any non-archived exercise for an added row."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=True)
        context = _context(connection, session_row)
        row = _row(context, row_id)
        if queries.has_facts(connection, row_id):
            raise CatalogError([Problem("exercise_id", "exercise_has_sets")])
        slot = _slot(context, row.template_slot_id)
        menu = slot if slot is not None and slot.kind == MENU else None
        if row.template_slot_id is not None and menu is None:
            raise CatalogError([Problem("exercise_id", "exercise_unavailable")])
        chosen = _offered(connection, user_id, menu, exercise_id)
        queries.set_session_exercise_exercise(connection, row_id, chosen)
        return _view(connection, user_id, _context(connection, session_row), Item(row_id=row_id))


def search_exercises(engine: Engine, user_id: int, session_id: int, query: str) -> SearchResults:
    """Exercises to add (non-archived): an empty query lists the 20 most recent then the rest by
    name; otherwise the ranking of `domain/search` with the recent ones first among ties."""
    with engine.begin() as connection:
        _session_row(connection, user_id, session_id, writable=False)
        rows = {row.id: row for row in exercise_queries.list_all(connection, user_id, include_archived=False)}
        recent = [i for i in queries.recent_exercise_ids(connection, user_id) if i in rows]
        candidates = exercise_queries.search_candidates(connection, user_id, include_archived=False)

    def info(exercise_id: int) -> ExerciseInfo:
        row = rows[exercise_id]
        return ExerciseInfo(row.id, row.name, row.category, row.equipment, False)

    text = query.strip()
    if text:
        return SearchResults(
            text, ranked=tuple(info(i) for i in search.rank(text, candidates, recent=recent))
        )
    head = recent[:RECENT_LIMIT]
    rest = sorted((i for i in rows if i not in head), key=lambda i: (catalog.sort_key(rows[i].name), i))
    return SearchResults("", recent=tuple(info(i) for i in head), others=tuple(info(i) for i in rest))


# --- sets


def set_form(
    engine: Engine,
    user_id: int,
    session_id: int,
    row_id: int,
    raw_type: str | None,
    raw_values: Mapping[str, str | None],
    step: str | None = None,
) -> SessionView:
    """The row's block with the form as typed after one stepper tap (no write, D-063); also the
    re-render of a refused form (`step` None)."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=True)
        context = _context(connection, session_row)
        fields, _ = exercise_fields(connection, _row(context, row_id).exercise_id)
        texts = rules.step_values([item.field for item in fields], raw_values, step)
        stepped_name = (step or "").partition(":")[0]
        open_more = any(
            item.name == stepped_name or raw_values.get(item.name) for item in fields if not item.visible
        )
        form = FormState(raw_type or rules.WORK, texts, open_more)
        return _view(connection, user_id, context, Item(row_id=row_id), form=form, with_records=False)


def _split(
    facts: SetFacts, fields: Sequence[FieldInfo]
) -> tuple[dict[str, int | None], dict[int, FieldValue]]:
    core: dict[str, int | None] = {}
    variables: dict[int, FieldValue] = {}
    for item in fields:
        value = facts.value(item.name)
        if item.core_quantity is not None:
            core[item.core_quantity] = value if isinstance(value, int) else None
        elif value is not None and item.field.variable_id is not None:
            variables[item.field.variable_id] = value
    return core, variables


@dataclass(frozen=True)
class Confirmed:
    """A confirmed set: the row's block (next form prefilled) and the new set."""

    view: SessionView
    set: SetView


def confirm_set(
    engine: Engine,
    user_id: int,
    session_id: int,
    row_id: int,
    raw_type: str | None,
    raw_values: Mapping[str, str | None],
    now: datetime,
) -> Confirmed:
    """Record one set (D-064): validated by `domain/sessions.set_draft`, appended with its
    variable values. Settings (D-062 and its L4 UI refinement): the variables the row holds no
    setting fact for (never touched, or cleared since) are written from the server's prefill.
    Checked on every ✓, so in practice the first ✓ writes them and later ones find nothing
    missing; a stored setting is never overwritten."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=True)
        context = _context(connection, session_row)
        row = _row(context, row_id)
        fields, setting_fields = exercise_fields(connection, row.exercise_id)
        facts = rules.set_draft(row.category, [item.field for item in fields], raw_type, raw_values)
        core, variables = _split(facts, fields)
        set_id = queries.insert_set(
            connection, row_id, set_type=facts.type, core=core, completed_at=to_text(now)
        )
        queries.insert_set_values(connection, set_id, variables)
        _write_missing_settings(connection, user_id, context, row, setting_fields)
        view = _block(connection, user_id, session_row, row_id)
        assert view.block is not None
        confirmed = view.block.set(set_id)
        assert confirmed is not None
        return Confirmed(view, confirmed)


def _write_missing_settings(
    connection: sa.Connection, user_id: int, context: _Context, row: sa.Row, fields: Sequence[FieldInfo]
) -> None:
    """Store the prefill of the row's settings that have no fact yet (missing variables only)."""
    if not fields:
        return
    stored = queries.settings_of(connection, row.id)
    shown = _settings(connection, user_id, context, row, fields)
    missing = {key: value for key, value in shown.items() if key not in stored}
    if missing:
        queries.upsert_settings(connection, row.id, missing)


def _located(connection: sa.Connection, user_id: int, set_id: int, *, require_open: bool) -> sa.Row:
    found = queries.get_set(connection, user_id, set_id)
    if found is None:
        raise NotFoundError(f"no set {set_id}")
    if require_open and found.status != "open":
        raise SessionError(SESSION_CLOSED)
    return found


def locate_set(engine: Engine, user_id: int, set_id: int) -> SetRef:
    """The session and row of a live set of the user (`NotFoundError` otherwise)."""
    with engine.begin() as connection:
        found = _located(connection, user_id, set_id, require_open=False)
        return SetRef(found.session_id, found.session_exercise_id, found.status != "open")


def update_set(
    engine: Engine,
    user_id: int,
    set_id: int,
    raw_type: str | None,
    raw_values: Mapping[str, str | None],
    *,
    require_open: bool = True,
) -> SessionView | SummaryView:
    """Correct a live set of a non-deleted session (L4 while open; L5 history passes
    `require_open=False`, D-066, D-067); the block of its row, or the closed session's detail."""
    with engine.begin() as connection:
        found = _located(connection, user_id, set_id, require_open=require_open)
        session_row = _session_row(connection, user_id, found.session_id, writable=False)
        category = exercise_queries.get(connection, user_id, found.exercise_id).category
        fields, _ = exercise_fields(connection, found.exercise_id)
        facts = rules.set_draft(category, [item.field for item in fields], raw_type, raw_values)
        core, variables = _split(facts, fields)
        queries.update_set(connection, set_id, set_type=facts.type, core=core)
        current = [item.field.variable_id for item in fields if item.field.variable_id is not None]
        queries.replace_set_values(connection, set_id, variables, current)
        return _answer(connection, user_id, session_row, found.session_exercise_id)


def delete_set(
    engine: Engine, user_id: int, set_id: int, now: datetime, *, require_open: bool = True
) -> SessionView | SummaryView:
    """Soft delete a live set (D-021, D-066); the block of its row, or the closed session's
    detail (D-067)."""
    with engine.begin() as connection:
        found = _located(connection, user_id, set_id, require_open=require_open)
        session_row = _session_row(connection, user_id, found.session_id, writable=False)
        queries.soft_delete_set(connection, set_id, to_text(now))
        return _answer(connection, user_id, session_row, found.session_exercise_id)


def save_settings(
    engine: Engine,
    user_id: int,
    session_id: int,
    row_id: int,
    raw_values: Mapping[str, str | None],
    *,
    require_open: bool = True,
) -> SessionView | SummaryView:
    """Write the row's settings (one fact per row and variable, a cleared one removed); the
    block of the row, or the closed session's detail (`require_open=False`, L5 history, D-067)."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=require_open)
        context = _context(connection, session_row)
        row = _row(context, row_id)
        _, setting_fields = exercise_fields(connection, row.exercise_id)
        values = rules.setting_draft([item.field for item in setting_fields], raw_values)
        queries.upsert_settings(connection, row_id, values)
        return _answer(connection, user_id, session_row, row_id)


def block(engine: Engine, user_id: int, session_id: int, row_id: int) -> SessionView:
    """The row's block as stored (re-render after a refused edit or settings form)."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=True)
        return _block(connection, user_id, session_row, row_id)


def detail(engine: Engine, user_id: int, session_id: int, row_id: int | None = None) -> SummaryView:
    """A closed session's detail as stored (`row_id` kept even without a live set): the re-render
    after a refused correction (L5)."""
    with engine.begin() as connection:
        session_row = _session_row(connection, user_id, session_id, writable=False)
        if session_row.status == "open":
            raise SessionError("session_open")
        if row_id is not None:
            _row(_context(connection, session_row), row_id)
        return _summary(connection, user_id, session_row, keep_row=row_id)


def delete_session(engine: Engine, user_id: int, session_id: int, now: datetime) -> None:
    """Soft delete a session, open or closed (D-067): only `session.deleted_at` is written; every
    reader ignores it from now on (history, indicators, prefill, the one open session)."""
    with engine.begin() as connection:
        _session_row(connection, user_id, session_id, writable=False)
        queries.soft_delete_session(connection, session_id, to_text(now))


# --- close


def unlogged_count(engine: Engine, user_id: int, session_id: int) -> int:
    """Items without a live set (rows and pending menus), shown before closing."""
    with engine.begin() as connection:
        context = _context(connection, _session_row(connection, user_id, session_id, writable=True))
        return sum(1 for item in context.items if item.row_id is None or not context.sets.get(item.row_id))


def close(engine: Engine, user_id: int, session_id: int, now: datetime) -> None:
    """Close the session (`ended_at = now`); closing a closed session changes nothing."""
    with engine.begin() as connection:
        _session_row(connection, user_id, session_id, writable=False)
        queries.close_session(connection, session_id, to_text(now))
