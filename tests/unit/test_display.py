import pytest

from rack_overflow.domain.templates import Target
from rack_overflow.domain.vocabulary import CORE_QUANTITIES
from rack_overflow.web.app import CATALOG
from rack_overflow.web.display import QUANTITY_KEYS, Display
from rack_overflow.web.locale import load_catalog


def test_every_core_quantity_has_a_word() -> None:
    catalog = load_catalog(CATALOG)
    show = Display(catalog)
    assert set(QUANTITY_KEYS) == set(CORE_QUANTITIES)
    for quantity in CORE_QUANTITIES:
        assert show.quantity(quantity) == catalog.text(QUANTITY_KEYS[quantity])
        assert show.quantity(quantity) != QUANTITY_KEYS[quantity]


NBSP = "\u00a0"
TIMES = f"{NBSP}\u00d7{NBSP}"
EN_DASH = "\u2013"


@pytest.mark.parametrize(
    ("target", "text"),
    [
        (Target(sets=4, note="par côté"), f"Séries{NBSP}: 4 · par côté"),
        (Target(sets=20, reps_min=1, reps_max=100), f"20{TIMES}1{EN_DASH}100"),
        (
            Target(sets=2, duration_s=90, distance_m=400, reps_min=5, reps_max=5),
            f"2{TIMES}1{NBSP}min{NBSP}30 / 400{NBSP}m / 5",
        ),
        (Target(duration_s=86400), f"24{NBSP}h"),
        (Target(duration_s=59), f"59{NBSP}s"),
        (Target(duration_s=3660), f"1{NBSP}h{NBSP}01"),
    ],
)
def test_target_text_edges(target: Target, text: str) -> None:
    assert Display(load_catalog(CATALOG)).target(target) == text
