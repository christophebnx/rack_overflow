"""The `position` column of ordered rows (exercise fields, templates, template slots, menu
options): the one computation of the position after the last row, and the one writer of positions
after a move or a removal."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa


def set_positions(connection: sa.Connection, table: sa.Table, ids: Sequence[int]) -> None:
    """Set `position = index` on the rows of `table` listed in `ids`, in that order (`0..n-1`)."""
    for position, row_id in enumerate(ids):
        connection.execute(sa.update(table).where(table.c.id == row_id).values(position=position))


def next_position(connection: sa.Connection, position: sa.Column[int], *where: sa.ColumnElement[bool]) -> int:
    """The position after the last row matching `where` (`max(position) + 1`), 0 when none."""
    last = connection.execute(sa.select(sa.func.max(position)).where(*where)).scalar_one()
    return 0 if last is None else int(last) + 1
