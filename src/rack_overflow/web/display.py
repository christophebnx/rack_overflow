"""Values as shown in pages (D-055): numbers from `domain.units` joined to their unit text, lists
of proposed values, unit labels. Registered as template globals by `rendering`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from zoneinfo import ZoneInfo

from rack_overflow.domain import units
from rack_overflow.domain.catalog import BOOL, ENUM, TEXT
from rack_overflow.domain.indicators import DURATION_TOTAL, MANUAL, RmRow, Series, Volume
from rack_overflow.domain.sessions import FieldValue, SetFacts
from rack_overflow.domain.templates import Target
from rack_overflow.domain.timestamps import from_text
from rack_overflow.services.sessions import FieldInfo
from rack_overflow.web.locale import Catalog

VALUE_SEPARATOR = " · "
TARGET_PART_SEPARATOR = " / "
# core quantity -> its word (the one map, read only by `Display.quantity`)
QUANTITY_KEYS = {
    "reps": "quantity.reps",
    "weight": "quantity.weight",
    "duration": "quantity.duration",
    "distance": "quantity.distance",
}
LOAD_CATEGORIES = ("strength", "kettlebell")
BOOL_KEYS = {1: "field.yes", 0: "field.no"}
WEEKDAY_KEYS = tuple(f"date.weekday.{day}" for day in range(1, 8))
"""Abbreviated weekday keys, ISO order (Monday first)."""
MONTH_KEYS = tuple(f"date.month.{month}" for month in range(1, 13))
"""Month name keys, January first."""
FORMULA_KEYS = {
    "epley": "rm.formula.epley",
    "brzycki": "rm.formula.brzycki",
    "lombardi": "rm.formula.lombardi",
    "oconner": "rm.formula.oconner",
    "wathan": "rm.formula.wathan",
}
"""1RM formula → its name (the one map; `domain.indicators.RM_FORMULAS` order)."""
FORMULA_TEXT_KEYS = {key: f"rm.formula_text.{key}" for key in FORMULA_KEYS}
SERIES_KEYS = {
    "e1rm": "progress.series.e1rm",
    "measured_1rm": "progress.series.measured_1rm",
    "load": "progress.series.load",
    "max_reps": "progress.series.max_reps",
    "max_duration": "progress.series.max_duration",
    "distance": "progress.series.distance",
    "duration": "progress.series.duration",
    "rounds": "progress.series.rounds",
}
"""Chart series key → its label (legend, tooltip)."""
SUM_SERIES = frozenset({"duration"})
# data-table column kind → the unit key its header carries (cells then hold the number only)
COLUMN_UNIT_KEYS = {units.WEIGHT: "unit.kg", units.DISTANCE: "unit.km", units.PACE: "progress.col.unit_pace"}
"""Series whose points are a day's sum of durations, shown compact (« 30 min »)."""
TYPED_UNIT_KEYS = {"weight": units.UNIT_KG, "distance": units.UNIT_KM, "duration": units.UNIT_DURATION}


class Display:
    """Display helpers bound to one string catalog."""

    CHIP_LIMIT = 12
    """Above this many values a choice is a select instead of chips (docs/ui-spec.md "L4")."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def _join(self, number: str, unit: str | None) -> str:
        return self._catalog.text("unit.with_value", number=number, unit=unit) if unit else number

    def value(self, kind: str, value: int, scale: int | None = None, free_unit: str | None = None) -> str:
        """One canonical value in display units with its unit: « 2,5 kg », « 400 m », « 1:30 »."""
        shown = units.format(kind, value, scale=scale)
        unit = self._catalog.text(shown.unit_key) if shown.unit_key else free_unit
        return self._join(shown.number_text, unit)

    def values(
        self, kind: str, values: Sequence[int], scale: int | None = None, free_unit: str | None = None
    ) -> str:
        """Proposed values with the unit once at the end when they share it: « 16 · 20 · 24 kg »."""
        shown = [units.format(kind, value, scale=scale) for value in values]
        keys = {item.unit_key for item in shown}
        if len(keys) == 1:
            key = keys.pop()
            unit = self._catalog.text(key) if key else free_unit
            return self._join(VALUE_SEPARATOR.join(item.number_text for item in shown), unit)
        return VALUE_SEPARATOR.join(self.value(kind, value, scale, free_unit) for value in values)

    def input_text(self, kind: str, value: int | None, scale: int | None = None) -> str:
        """A canonical value as an input's text (parsed back by `domain.units.parse`); empty for None."""
        return "" if value is None else units.input_text(kind, value, scale=scale)

    def input_texts(self, kind: str, values: Sequence[int] | None, scale: int | None = None) -> str:
        """Proposed values as one input's text, separated by spaces: « 16 20 24 »."""
        return " ".join(units.input_text(kind, value, scale=scale) for value in values or ())

    def unit(self, kind: str, free_unit: str | None = None) -> str:
        """The unit shown in a label or a list: kg, km, m:ss, or the free unit (empty when none)."""
        key = TYPED_UNIT_KEYS.get(kind)
        return self._catalog.text(key) if key else (free_unit or "")

    def quantity(self, core_quantity: str) -> str:
        """The word of a core quantity: « Répétitions », « Charge »…"""
        return self._catalog.text(QUANTITY_KEYS[core_quantity])

    def duration_compact(self, seconds: int) -> str:
        """A duration in the compact form of targets: « 45 s », « 30 min », « 1 h 15 »."""
        compact = units.compact_duration(seconds)
        return self._catalog.text(compact.key, **compact.params) if compact.key else compact.params["text"]

    def target(self, target: Target) -> str:
        """The one text of an indicative target (D-059; examples in docs/ui-spec.md "L3 — Target
        text"): sets, then the parts in the order duration, distance, reps joined by « / », then the
        note; « Séries : 4 » for sets alone; empty when nothing is set."""
        parts: list[str] = []
        if target.duration_s is not None:
            parts.append(self.duration_compact(target.duration_s))
        if target.distance_m is not None:
            parts.append(self.value(units.DISTANCE, target.distance_m))
        if target.reps_min is not None and target.reps_max is not None:
            low, high = target.reps_min, target.reps_max
            parts.append(
                str(low) if low == high else self._catalog.text("target.reps_range", min=low, max=high)
            )
        text = TARGET_PART_SEPARATOR.join(parts)
        if target.sets is not None:
            key = "target.sets_times" if parts else "target.sets_only"
            text = self._catalog.text(key, sets=target.sets, parts=text)
        if target.note:
            text = (
                self._catalog.text("target.with_note", target=text, note=target.note) if text else target.note
            )
        return text

    # --- session logging (L4, docs/ui-spec.md "L4 — Session page")

    def yes_no(self, value: int) -> str:
        """« Oui » for 1, « Non » otherwise: the one reading of a `bool` value (`BOOL_KEYS`)."""
        return self._catalog.text(BOOL_KEYS.get(value, BOOL_KEYS[0]))

    def field_value(self, field: FieldInfo, value: FieldValue) -> str:
        """A set or setting value as read: number with unit, enum label, « Oui » / « Non », text."""
        kind = field.field.kind
        if kind.kind == BOOL:
            return self.yes_no(int(value))
        if kind.kind == ENUM:
            return field.enum_label(value)
        if kind.kind == TEXT or not isinstance(value, int):
            return str(value)
        return self.value(kind.kind, value, kind.scale, field.unit)

    def set_text(self, facts: SetFacts, fields: Sequence[FieldInfo]) -> str:
        """One set as a line: « 8 x 62,5 kg », « 12 rép. », « 30:00 · 5,2 km », measures appended
        (« · Résistance 8 »); values of fields no longer shown are left out."""
        reps, weight = facts.value("reps"), facts.value("weight")
        parts: list[str] = []
        if isinstance(reps, int) and isinstance(weight, int):
            shown = self.value(units.WEIGHT, weight)
            parts.append(self._catalog.text("session.set.reps_weight", reps=reps, weight=shown))
        elif isinstance(reps, int):
            parts.append(self._catalog.text("session.set.reps", reps=reps))
        elif isinstance(weight, int):
            parts.append(self.value(units.WEIGHT, weight))
        for quantity in (units.DURATION, units.DISTANCE):
            value = facts.value(quantity)
            if isinstance(value, int):
                parts.append(self.value(quantity, value))
        for field in fields:
            value = facts.value(field.name)
            if field.core_quantity is None and value is not None:
                text = self.field_value(field, value)
                parts.append(self._catalog.text("session.set.variable", label=field.label, value=text))
        return VALUE_SEPARATOR.join(parts)

    def local_time(self, utc_text: str, tz_name: str) -> str:
        """A stored UTC timestamp as a local time in the session's zone: « 18:42 » (D-065)."""
        return from_text(utc_text).astimezone(ZoneInfo(tz_name)).strftime("%H:%M")

    def local_date(self, local_date_text: str) -> str:
        """A session's local date `YYYY-MM-DD` as « 03/11/2026 »."""
        day = date.fromisoformat(local_date_text)
        return self._catalog.text(
            "date.numeric", day=f"{day.day:02d}", month=f"{day.month:02d}", year=day.year
        )

    def short_date(self, local_date_text: str) -> str:
        """A local date `YYYY-MM-DD` as « 03/11 » (history weeks and items, chart labels; L5)."""
        day = date.fromisoformat(local_date_text)
        return self._catalog.text("date.short", day=f"{day.day:02d}", month=f"{day.month:02d}")

    def weekday(self, local_date_text: str) -> str:
        """The abbreviated weekday of a local date: « lun. » (ISO, Monday = 1)."""
        return self._catalog.text(WEEKDAY_KEYS[date.fromisoformat(local_date_text).isoweekday() - 1])

    def month(self, month_key: str) -> str:
        """A month `YYYY-MM` as « novembre 2026 » (lowercase; headings capitalise through CSS)."""
        year, month = month_key.split("-")
        name = self._catalog.text(MONTH_KEYS[int(month) - 1])
        return self._catalog.text("history.month_heading", month=name, year=year)

    def decimal1(self, tenths: int) -> str:
        """A number given in tenths with one decimal and a comma: 28 → « 2,8 »."""
        return units.format(units.DECIMAL, tenths, scale=1).number_text

    def elapsed(self, start_text: str, end_text: str) -> str:
        """The compact duration between two stored timestamps: « 1 h 09 »."""
        seconds = int((from_text(end_text) - from_text(start_text)).total_seconds())
        return self.duration_compact(max(seconds, 0))

    def volume(self, volume: Volume) -> str:
        """The volume of an exercise as its summary reads it (docs/ui-spec.md "L4 — Session
        summary"): load for strength and kettlebell, reps (+ load, durations) for bodyweight,
        distance and duration for cardio, rounds and duration for intervals. A zero part is left
        out: no counted set (warm-ups only) gives an empty text."""
        parts: list[str] = []
        if not volume.sets:
            return ""
        load = self._catalog.text("session.summary.volume", value=self.value(units.WEIGHT, volume.load_g))
        if volume.category in LOAD_CATEGORIES and volume.load_g:
            parts.append(load)
        elif volume.category == "bodyweight":
            if volume.reps:
                parts.append(self._catalog.text("session.summary.reps", count=volume.reps))
            if volume.load_g:
                parts.append(load)
        elif volume.category == "cardio" and volume.distance_m:
            distance = self.value(units.DISTANCE, volume.distance_m)
            parts.append(self._catalog.text("session.summary.distance", value=distance))
        elif volume.category == "intervals":
            parts.append(self._catalog.text("session.summary.rounds", count=volume.sets))
        if volume.duration_s and volume.category in ("bodyweight", "cardio", "intervals"):
            duration = self.duration_compact(volume.duration_s)
            parts.append(self._catalog.text("session.summary.duration", value=duration))
        return VALUE_SEPARATOR.join(parts)

    def choices(self, field: FieldInfo, current: str) -> list[tuple[str, str]]:
        """`(input value, text)` of a chip group: « Oui » / « Non », enum labels, or discrete
        values in display units; a current value off the list is added, an optional field gets
        an empty choice « — » first."""
        kind = field.field.kind
        if kind.kind == BOOL:
            items = [(str(key), self.yes_no(key)) for key in BOOL_KEYS]
        elif kind.kind == ENUM:
            items = [(value.key, value.label) for value in field.enum_values]
        else:
            texts = [
                units.input_text(kind.kind, v, scale=kind.scale)
                for v in field.field.params.discrete_values or ()
            ]
            items = [(text, text) for text in texts]
        if current and current not in {value for value, _ in items}:
            items.append((current, current))
        if not field.field.params.required:
            items.insert(0, ("", self._catalog.text("session.no_value")))
        return items

    # --- tracking (L5, docs/ui-spec.md "L5 — Progress of an exercise", "L5 — Units of computed values")

    def rate(self, kind: str, value: int) -> str:
        """A computed value with its unit: pace « 5:20 /km », speed « 11,3 km/h », density
        « 12,5 rép./min » (`domain.units` kinds `pace`, `speed`, `density`)."""
        shown = units.format(kind, value)
        assert shown.unit_key is not None
        return self._catalog.text(shown.unit_key, value=shown.number_text)

    def cell(self, kind: str, value: int | None) -> str:
        """A value of the chart's data table or of a record by its kind: « — » when absent,
        a day's sum of durations compact, a pace, else `value`."""
        if value is None:
            return self._catalog.text("session.no_value")
        if kind == DURATION_TOTAL:
            return self.duration_compact(value)
        if kind in (units.PACE, units.SPEED, units.DENSITY):
            return self.rate(kind, value)
        if kind == units.INT:
            return str(value)
        return self.value(kind, value)

    def column_unit(self, kind: str) -> str | None:
        """The unit a data-table column header carries (« kg », « km », « min/km »), None when
        its cells keep their own (counts, m:ss, compact day sums)."""
        key = COLUMN_UNIT_KEYS.get(kind)
        return self._catalog.text(key) if key else None

    def column_cell(self, kind: str, value: int | None) -> str:
        """A data-table value under a header carrying its unit (`column_unit`): the number only,
        « 117,5 », « 0,4 », « 5:20 »; other kinds as `cell` writes them."""
        if value is None or kind not in COLUMN_UNIT_KEYS:
            return self.cell(kind, value)
        return units.column_number(kind, value)

    def series_value(self, series: Series, value: int) -> str:
        """A point of a chart series as the caption reads it."""
        return self.cell(DURATION_TOTAL if series.key in SUM_SERIES else series.unit_kind, value)

    def formula(self, key: str) -> str:
        """The name of a 1RM formula: « Epley »."""
        return self._catalog.text(FORMULA_KEYS[key])

    def formula_text(self, key: str) -> str:
        """The expression of a 1RM formula: « charge x (1 + rép. / 30) »."""
        return self._catalog.text(FORMULA_TEXT_KEYS[key])

    def series_label(self, series: Series, formula: str) -> str:
        """The label of a chart series: « 1RM estimé (Epley) », « 16 kg », « Distance »."""
        key = SERIES_KEYS[series.key]
        if series.load_g is not None:
            return self._catalog.text(key, load=self.value(units.WEIGHT, series.load_g))
        return self._catalog.text(key, formula=self.formula(formula))

    def rm_origin(self, row: RmRow, formula: str) -> str:
        """Where an RM row's shown value comes from: « Mesuré · saisie du 01/10/2026 »,
        « Mesuré · test en séance du … » or « Estimé (Epley) · d'après 5 x 92,5 kg du … »."""
        if row.measured is not None:
            key = "rm.origin.manual" if row.measured.origin == MANUAL else "rm.origin.rm_test"
            return self._catalog.text(key, date=self.local_date(row.measured.local_date))
        assert row.estimate is not None
        source = row.estimate.source
        lifted = self._catalog.text(
            "session.set.reps_weight", reps=source.reps, weight=self.value(units.WEIGHT, source.weight_g or 0)
        )
        return self._catalog.text(
            "rm.origin.estimated",
            formula=self.formula(formula),
            set=lifted,
            date=self.local_date(source.local_date),
        )
