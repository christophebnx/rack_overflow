"""`web/display.Display` helpers of session logging (docs/ui-spec.md "L4 — Session page", "L4 —
Session summary")."""

from __future__ import annotations

import pytest

from rack_overflow.domain.catalog import EnumValue, FieldKind, FieldParams
from rack_overflow.domain.indicators import Volume
from rack_overflow.domain.sessions import SessionField, SetFacts
from rack_overflow.services.sessions import FieldInfo
from rack_overflow.web.app import CATALOG
from rack_overflow.web.display import Display
from rack_overflow.web.locale import load_catalog

SHOW = Display(load_catalog(CATALOG))
NBSP = "\u00a0"
TIMES = f"{NBSP}\u00d7{NBSP}"


def core(quantity: str, kind: str, **params: object) -> FieldInfo:
    return FieldInfo(SessionField(quantity, FieldKind(kind), FieldParams(**params), core_quantity=quantity))  # type: ignore[arg-type]


def variable(variable_id: int, label: str, kind: FieldKind, **params: object) -> FieldInfo:
    rule = SessionField(f"var_{variable_id}", kind, FieldParams(**params), variable_id=variable_id)  # type: ignore[arg-type]
    values = tuple(EnumValue(key, key.title()) for key in kind.enum_keys)
    return FieldInfo(rule, label, None, values)


REPS, WEIGHT = core("reps", "int"), core("weight", "weight")
DURATION, DISTANCE = core("duration", "duration"), core("distance", "distance")
RESISTANCE = variable(7, "Résistance", FieldKind("int"))
GRIP = variable(8, "Prise", FieldKind("enum", enum_keys=("neutre", "pronation")))
STRAPS = variable(9, "Sangles", FieldKind("bool"), required=True)


@pytest.mark.parametrize(
    ("values", "text"),
    [
        ({"reps": 8, "weight": 62500}, f"8{TIMES}62,5{NBSP}kg"),
        ({"reps": 12}, f"12{NBSP}rép."),
        ({"weight": 24000}, f"24{NBSP}kg"),
        ({"duration": 45}, "0:45"),
        ({"duration": 1800, "distance": 5200}, f"30:00 · 5,2{NBSP}km"),
        ({"duration": 1800, "var_7": 8}, f"30:00 · Résistance{NBSP}8"),
        ({"reps": 10, "var_8": "neutre", "var_9": 1}, f"10{NBSP}rép. · Prise{NBSP}Neutre · Sangles{NBSP}Oui"),
        ({"reps": 10, "var_99": 3}, f"10{NBSP}rép."),
    ],
)
def test_set_text(values: dict[str, int | str], text: str) -> None:
    fields = (REPS, WEIGHT, DURATION, DISTANCE, RESISTANCE, GRIP, STRAPS)
    assert SHOW.set_text(SetFacts("work", values), fields) == text


def test_local_time_date_and_elapsed() -> None:
    assert SHOW.local_time("2026-11-03T17:42:00Z", "Europe/Brussels") == "18:42"
    assert SHOW.local_time("2026-07-03T17:42:00Z", "Europe/Brussels") == "19:42"
    assert SHOW.local_date("2026-11-03") == "03/11/2026"
    assert SHOW.elapsed("2026-11-03T17:42:00Z", "2026-11-03T18:51:00Z") == f"1{NBSP}h{NBSP}09"


@pytest.mark.parametrize(
    ("volume", "text"),
    [
        (Volume("strength", load_g=1920000, reps=32, sets=4), f"Volume{NBSP}: 1920{NBSP}kg"),
        (Volume("bodyweight", reps=36, sets=3), f"Répétitions{NBSP}: 36"),
        (
            Volume("bodyweight", load_g=360000, reps=36, sets=3),
            f"Répétitions{NBSP}: 36 · Volume{NBSP}: 360{NBSP}kg",
        ),
        (Volume("bodyweight", duration_s=90, sets=2), f"Durée{NBSP}: 1{NBSP}min{NBSP}30"),
        (
            Volume("cardio", duration_s=1800, distance_m=5200, sets=1),
            f"Distance{NBSP}: 5,2{NBSP}km · Durée{NBSP}: 30{NBSP}min",
        ),
        (Volume("intervals", duration_s=240, sets=8), f"Tours{NBSP}: 8 · Durée{NBSP}: 4{NBSP}min"),
        (Volume("strength"), ""),  # warm-ups only: no zero part
        (Volume("intervals"), ""),
        (Volume("kettlebell", reps=30, sets=3), ""),  # no load logged
    ],
)
def test_volume(volume: Volume, text: str) -> None:
    assert SHOW.volume(volume) == text


def test_choices() -> None:
    bell = core("weight", "weight", discrete_values=(16000, 20000, 24000), required=True)
    assert SHOW.choices(bell, "20") == [("16", "16"), ("20", "20"), ("24", "24")]
    assert SHOW.choices(bell, "18") == [("16", "16"), ("20", "20"), ("24", "24"), ("18", "18")]
    assert SHOW.choices(GRIP, "") == [("", "—"), ("neutre", "Neutre"), ("pronation", "Pronation")]
    assert SHOW.choices(STRAPS, "1") == [("1", "Oui"), ("0", "Non")]


def test_field_value() -> None:
    assert SHOW.field_value(GRIP, "pronation") == "Pronation"
    assert SHOW.field_value(STRAPS, 0) == "Non"
    assert SHOW.field_value(RESISTANCE, 8) == "8"
    assert SHOW.field_value(WEIGHT, 2500) == f"2,5{NBSP}kg"
