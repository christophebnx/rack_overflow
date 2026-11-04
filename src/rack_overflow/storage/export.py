"""What an export holds and the dump of the database (D-072): every table of `schema.metadata`,
parents before children, every row by id (archived and soft-deleted included), every column in
schema order except the credential hashes `SECRET_COLUMNS`. The one definition of an export's
contents, shared by the JSON and the CSV formats."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from rack_overflow.storage import schema

SECRET_COLUMNS = frozenset({("device", "token_hash"), ("pairing_code", "code_hash")})
"""Credential material (D-049): no training fact, never exported; backups keep it for restore."""


def _tables() -> list[sa.Table]:
    return list(schema.metadata.sorted_tables)


def exported_columns() -> dict[str, list[str]]:
    """`{table: [column]}` of an export, parents before children, columns in schema order."""
    return {
        table.name: [
            column.name for column in table.columns if (table.name, column.name) not in SECRET_COLUMNS
        ]
        for table in _tables()
    }


def dump(connection: sa.Connection) -> dict[str, list[dict[str, Any]]]:
    """Every exported row of every table, ordered by id: JSON columns decoded, booleans as
    `bool`, integers and text as stored, `NULL` as None. Run it in one transaction."""
    columns = exported_columns()
    result: dict[str, list[dict[str, Any]]] = {}
    for table in _tables():
        selected = [table.c[name] for name in columns[table.name]]
        rows = connection.execute(sa.select(*selected).order_by(table.c.id))
        result[table.name] = [dict(row._mapping) for row in rows]
    return result
