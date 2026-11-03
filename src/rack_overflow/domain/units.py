"""Canonical integers ↔ user text (D-020, D-055). Storage stays in grams, seconds, metres and
scaled integers; display and input use French conventions (decimal comma).

No unit symbol and no French word here: a unit is a catalog key (`unit.kg`, `unit.km`, `unit.m`)
rendered by `web/`. L4 reuses `parse` and `format` for steppers and set display.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from rack_overflow.domain.errors import DomainError

INT = "int"
DECIMAL = "decimal"
WEIGHT = "weight"
DURATION = "duration"
DISTANCE = "distance"
NUMERIC_KINDS: tuple[str, ...] = (INT, DECIMAL, WEIGHT, DURATION, DISTANCE)
"""Kinds whose values are canonical integers typed as numbers (variable types and core quantities)."""
PACE = "pace"
SPEED = "speed"
DENSITY = "density"
"""Display kinds of computed values (L5): seconds per km, metres per hour, reps per hour."""

MAX_VALUE = 10**9
WEIGHT_DECIMALS = 3
DISTANCE_DECIMALS = 3
KILO = 1000

UNIT_KG = "unit.kg"
UNIT_KM = "unit.km"
UNIT_M = "unit.m"
UNIT_DURATION = "unit.duration"
UNIT_PACE = "unit.pace"
UNIT_SPEED = "unit.speed"
UNIT_DENSITY = "unit.density"
"""Keys of computed values: texts holding the number (« {value} /km »), not unit words."""

_NUMBER = re.compile(r"(\d*)(?:[.,](\d*))?", re.ASCII)
_DISTANCE = re.compile(r"(.*?)\s*(km|m)?", re.IGNORECASE | re.DOTALL)
_DIGITS = re.compile(r"\d+", re.ASCII)
_TWO_DIGITS = re.compile(r"\d{2}", re.ASCII)


class UnitError(DomainError):
    """A typed value could not be read; `code` is stable (`not_a_number`, `too_many_decimals`,
    `negative`, `too_large`, `bad_duration`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Display:
    """A value as shown: its number text and the catalog key of its unit (None when it has none)."""

    number_text: str
    unit_key: str | None


def kind_of_quantity(core_quantity: str) -> str:
    """Value kind of a core quantity: `reps` is an `int`, the others share their name."""
    return INT if core_quantity == "reps" else core_quantity


def input_unit_key(kind: str) -> str | None:
    """Unit key shown in an input label: kg, km, m:ss; None for kinds with a free or no unit."""
    return {WEIGHT: UNIT_KG, DISTANCE: UNIT_KM, DURATION: UNIT_DURATION}.get(kind)


def parse(kind: str, raw: str, *, scale: int | None = None) -> int:
    """The canonical integer of `raw` typed in display units for `kind` (see D-055)."""
    text = raw.strip()
    if text.startswith("-"):
        raise UnitError("negative")
    if kind == DURATION:
        value = _parse_duration(text)
    elif kind == DISTANCE:
        value = _parse_distance(text)
    elif kind == WEIGHT:
        value = _scaled(text, WEIGHT_DECIMALS)
    elif kind == DECIMAL:
        value = _scaled(text, scale if scale is not None else 0)
    else:
        value = _scaled(text, 0)
    if value > MAX_VALUE:
        raise UnitError("too_large")
    return value


def _scaled(text: str, decimals: int) -> int:
    """`text` times 10^decimals as an integer; more decimals than allowed are refused."""
    match = _NUMBER.fullmatch(text)
    if match is None or not (match.group(1) or match.group(2)):
        raise UnitError("not_a_number")
    whole, fraction = match.group(1) or "0", (match.group(2) or "").rstrip("0")
    if len(fraction) > decimals:
        raise UnitError("too_many_decimals")
    if len(whole) > len(str(MAX_VALUE)):
        raise UnitError("too_large")
    return int(whole) * 10**decimals + int(fraction.ljust(decimals, "0") or "0")


def _parse_distance(text: str) -> int:
    match = _DISTANCE.fullmatch(text)
    number, suffix = (match.group(1), match.group(2)) if match else (text, None)
    if suffix is not None and suffix.lower() == "m":
        return _scaled(number, 0)
    return _scaled(number, DISTANCE_DECIMALS)


def _parse_duration(text: str) -> int:
    parts = text.split(":")
    if len(parts) == 1:
        if not _DIGITS.fullmatch(text):
            raise UnitError("bad_duration")
        return int(text) if len(text) <= len(str(MAX_VALUE)) else MAX_VALUE + 1
    if len(parts) > 3 or not all(_DIGITS.fullmatch(part) for part in parts):
        raise UnitError("bad_duration")
    lead, *rest = parts
    if not all(_TWO_DIGITS.fullmatch(part) and int(part) < 60 for part in rest):
        raise UnitError("bad_duration")
    if len(lead) > len(str(MAX_VALUE)):
        raise UnitError("too_large")
    total = int(lead)
    for part in rest:
        total = total * 60 + int(part)
    return total


def format(kind: str, value: int, *, scale: int | None = None) -> Display:
    """`value` (canonical integer) as shown for `kind`: decimal comma, unit key apart."""
    if kind == WEIGHT:
        return Display(_decimal_text(value, WEIGHT_DECIMALS), UNIT_KG)
    if kind == DISTANCE:
        if value < KILO:
            return Display(str(value), UNIT_M)
        return Display(_decimal_text(value, DISTANCE_DECIMALS), UNIT_KM)
    if kind == DURATION:
        return Display(_duration_text(value), None)
    if kind == DECIMAL:
        return Display(_decimal_text(value, scale or 0, keep_zeros=True), None)
    if kind == PACE:
        return Display(_duration_text(value), UNIT_PACE)
    if kind == SPEED:
        return Display(_one_decimal(value, KILO), UNIT_SPEED)
    if kind == DENSITY:
        return Display(_one_decimal(value, 60), UNIT_DENSITY)
    return Display(str(value), None)


def _one_decimal(value: int, divisor: int) -> str:
    """`value / divisor` with one decimal, rounded half up: metres per hour → « 11,3 » km/h."""
    tenths = (value * 20 + divisor) // (divisor * 2)
    return _decimal_text(tenths, 1, keep_zeros=True)


def column_number(kind: str, value: int) -> str:
    """`value` as a number in its kind's one column unit, the unit left to the column header:
    kg, km (never m), m:ss per km for a pace; other kinds as `format` writes them."""
    if kind == DISTANCE:
        return _decimal_text(value, DISTANCE_DECIMALS)
    return format(kind, value).number_text


CHART_DECIMALS = 3


def chart_number(kind: str, value: int) -> float:
    """A canonical integer as a chart axis reads it (L5, D-068): kg for a weight, km for a
    distance, the count otherwise; a duration stays in seconds, the chart writes it m:ss /
    h:mm:ss (D-029)."""
    if kind in (WEIGHT, DISTANCE):
        return round(value / KILO, CHART_DECIMALS)
    return float(value)


CHART_DURATION_STEPS_S: tuple[int, ...] = (
    1,
    2,
    5,
    10,
    15,
    30,
    60,
    120,
    300,
    600,
    900,
    1800,
    3600,
    7200,
    10800,
    21600,
    43200,
    86400,
)
"""Clock-round steps between the ticks of a duration axis, in seconds (« 0:15 », « 1:00 »…)."""
CHART_DURATION_INTERVALS = 6
"""At most this many intervals between the lowest and highest value of a duration axis."""


def chart_duration_step(low_s: int, high_s: int) -> int:
    """Seconds between the ticks of a duration axis spanning `low_s` to `high_s`: the smallest
    clock-round step giving at most `CHART_DURATION_INTERVALS` intervals (D-029: ticks read
    m:ss / h:mm:ss). Equal values span a tenth of the value, as the chart pads a flat line."""
    span = high_s - low_s or high_s // 10
    return next(
        (step for step in CHART_DURATION_STEPS_S if step * CHART_DURATION_INTERVALS >= span),
        CHART_DURATION_STEPS_S[-1],
    )


def input_text(kind: str, value: int, *, scale: int | None = None) -> str:
    """`value` as text that `parse(kind, ...)` reads back: an input prefilled in display units
    (a distance under 1 km carries its `m`, since a bare number is read as km)."""
    shown = format(kind, value, scale=scale)
    if kind == DISTANCE and shown.unit_key == UNIT_M:
        return f"{shown.number_text} m"
    return shown.number_text


def _decimal_text(value: int, decimals: int, *, keep_zeros: bool = False) -> str:
    number = Decimal(value).scaleb(-decimals)
    text = f"{number:.{decimals}f}"
    if not keep_zeros and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _duration_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


COMPACT_SECONDS = "duration.compact.seconds"
COMPACT_MINUTES = "duration.compact.minutes"
COMPACT_MINUTES_SECONDS = "duration.compact.minutes_seconds"
COMPACT_HOURS = "duration.compact.hours"
COMPACT_HOURS_MINUTES = "duration.compact.hours_minutes"


@dataclass(frozen=True)
class CompactDuration:
    """A duration in the compact form of targets (« 45 s », « 30 min », « 1 h 15 »): a text key
    and its parameters; `key` is None for the rare D-055 form (`text`, « 1:15:30 »)."""

    key: str | None
    params: dict[str, str]


def compact_duration(seconds: int) -> CompactDuration:
    """`seconds` as a target reads it (D-055 refinement, L3): seconds below a minute, whole
    minutes or « min ss » below an hour, whole hours or « h mm », else `h:mm:ss`."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if not hours and not minutes:
        return CompactDuration(COMPACT_SECONDS, {"seconds": str(secs)})
    if not hours:
        if not secs:
            return CompactDuration(COMPACT_MINUTES, {"minutes": str(minutes)})
        return CompactDuration(COMPACT_MINUTES_SECONDS, {"minutes": str(minutes), "seconds": f"{secs:02d}"})
    if secs:
        return CompactDuration(None, {"text": _duration_text(seconds)})
    if not minutes:
        return CompactDuration(COMPACT_HOURS, {"hours": str(hours)})
    return CompactDuration(COMPACT_HOURS_MINUTES, {"hours": str(hours), "minutes": f"{minutes:02d}"})
