import pytest

from rack_overflow.domain import vocabulary

LISTS = {name: getattr(vocabulary, name) for name in dir(vocabulary) if name.isupper()}


@pytest.mark.parametrize("name", sorted(LISTS))
def test_values_are_unique_lowercase_keys(name: str) -> None:
    values = LISTS[name]
    assert values
    assert len(set(values)) == len(values)
    assert all(value.isascii() and value == value.lower() and "'" not in value for value in values)


def test_session_locations_are_locations() -> None:
    assert set(vocabulary.SESSION_LOCATIONS) < set(vocabulary.LOCATIONS)
