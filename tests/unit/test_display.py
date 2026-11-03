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
