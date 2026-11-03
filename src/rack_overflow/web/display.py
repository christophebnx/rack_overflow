"""Values as shown in pages (D-055): numbers from `domain.units` joined to their unit text, lists
of proposed values, unit labels. Registered as template globals by `rendering`."""

from __future__ import annotations

from collections.abc import Sequence

from rack_overflow.domain import units
from rack_overflow.domain.templates import Target
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
TYPED_UNIT_KEYS = {"weight": units.UNIT_KG, "distance": units.UNIT_KM, "duration": units.UNIT_DURATION}


class Display:
    """Display helpers bound to one string catalog."""

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
