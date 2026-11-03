"""The one reordering rule (`domain/ordering`, D-058)."""

from __future__ import annotations

import pytest

from rack_overflow.domain import ordering
from rack_overflow.domain.catalog import CatalogError


@pytest.mark.parametrize(
    ("item", "direction", "expected"),
    [
        (20, ordering.UP, ([20, 10, 30], 0)),
        (20, ordering.DOWN, ([10, 30, 20], 2)),
        (10, ordering.UP, ([10, 20, 30], 0)),
        (30, ordering.DOWN, ([10, 20, 30], 2)),
        (10, ordering.DOWN, ([20, 10, 30], 1)),
    ],
)
def test_moved_swaps_with_the_neighbour_and_clamps(item: int, direction: str, expected: tuple) -> None:
    assert ordering.moved([10, 20, 30], item, direction) == expected


def test_a_single_item_never_moves() -> None:
    assert ordering.moved([7], 7, ordering.UP) == ([7], 0)
    assert ordering.moved((7,), 7, ordering.DOWN) == ([7], 0)


def test_moved_does_not_touch_its_input() -> None:
    ids = [1, 2]
    ordering.moved(ids, 2, ordering.UP)
    assert ids == [1, 2]


@pytest.mark.parametrize("direction", ["left", "", "UP"])
def test_unknown_direction_is_refused(direction: str) -> None:
    with pytest.raises(CatalogError) as refused:
        ordering.moved([1, 2], 1, direction)
    assert [(p.field, p.code) for p in refused.value.problems] == [("direction", "invalid_choice")]
    with pytest.raises(CatalogError):
        ordering.check_direction(direction)


def test_unknown_item_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="not in list"):
        ordering.moved([1, 2], 3, ordering.UP)
