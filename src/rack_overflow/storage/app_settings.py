"""Per-user key / value settings (`app_setting`): the seed version (D-057), later the RM formula.
Queries on a caller's `Connection`."""

from __future__ import annotations

import sqlalchemy as sa

from rack_overflow.storage.schema import app_setting


def get(connection: sa.Connection, user_id: int, key: str) -> str | None:
    """The value of `key` for `user_id`, or None."""
    query = sa.select(app_setting.c.value).where(app_setting.c.user_id == user_id, app_setting.c.key == key)
    return connection.execute(query).scalar_one_or_none()


def put(connection: sa.Connection, user_id: int, key: str, value: str) -> None:
    """Set `key` to `value` for `user_id` (insert or update)."""
    updated = connection.execute(
        sa.update(app_setting)
        .where(app_setting.c.user_id == user_id, app_setting.c.key == key)
        .values(value=value)
    )
    if updated.rowcount == 0:
        connection.execute(sa.insert(app_setting).values(user_id=user_id, key=key, value=value))
