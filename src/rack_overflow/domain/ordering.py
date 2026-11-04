"""The one reordering rule of ordered lists moved by « Monter » / « Descendre » buttons (D-058):
exercise fields, templates, template slots and menu options.

A move swaps an item with its neighbour; at an end it changes nothing. Positions are then
renumbered `0..n-1` by the caller (`storage/positions.set_positions`).
"""

from __future__ import annotations

from collections.abc import Sequence

from rack_overflow.domain.catalog import CatalogError, Problem

UP = "up"
DOWN = "down"
DIRECTIONS: tuple[str, ...] = (UP, DOWN)


def check_direction(direction: str) -> None:
    """Refuse a direction other than `up` / `down` (`direction`: `invalid_choice`)."""
    if direction not in DIRECTIONS:
        raise CatalogError([Problem("direction", "invalid_choice")])


def moved(ids: Sequence[int], item_id: int, direction: str) -> tuple[list[int], int]:
    """`ids` with `item_id` swapped with its neighbour in `direction` (unchanged at an end), and
    the item's new index (0-based). `item_id` must be in `ids` (`ValueError` otherwise)."""
    check_direction(direction)
    order = list(ids)
    index = order.index(item_id)
    target = index - 1 if direction == UP else index + 1
    if 0 <= target < len(order):
        order[index], order[target] = order[target], order[index]
        index = target
    return order, index
