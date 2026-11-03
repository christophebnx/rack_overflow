"""Renumber the `position` column of ordered rows: the one writer of positions after a move or a
removal (exercise fields, templates, template slots, menu options)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa


def set_positions(connection: sa.Connection, table: sa.Table, ids: Sequence[int]) -> None:
    """Set `position = index` on the rows of `table` listed in `ids`, in that order (`0..n-1`)."""
    for position, row_id in enumerate(ids):
        connection.execute(sa.update(table).where(table.c.id == row_id).values(position=position))
