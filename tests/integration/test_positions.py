"""`storage/positions`: `set_positions`, the one writer of `position` after a move or removal, and
`next_position`, the one computation of the position of an appended row."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.storage import positions
from rack_overflow.storage import schema as s


def test_set_positions_renumbers_in_the_given_order(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        for position, name in enumerate(["A", "B", "C"]):
            connection.execute(
                sa.insert(s.template).values(user_id=1, name=name, location="gym", position=position * 5)
            )
        positions.set_positions(connection, s.template, [3, 1])
        rows = connection.execute(sa.select(s.template.c.id, s.template.c.position).order_by(s.template.c.id))
        assert rows.all() == [(1, 1), (2, 5), (3, 0)]


def test_next_position_is_zero_when_no_row_matches(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        assert positions.next_position(connection, s.template.c.position, s.template.c.user_id == 1) == 0


def test_next_position_follows_the_last_matching_row(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        for position, name in [(4, "A"), (9, "B")]:
            connection.execute(
                sa.insert(s.template).values(user_id=1, name=name, location="gym", position=position)
            )
        connection.execute(sa.update(s.template).where(s.template.c.name == "B").values(archived_at="x"))
        live = s.template.c.archived_at.is_(None)
        assert positions.next_position(connection, s.template.c.position, s.template.c.user_id == 1) == 10
        assert positions.next_position(connection, s.template.c.position, live) == 5
