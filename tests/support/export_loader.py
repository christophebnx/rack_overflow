"""Test-only readers of an export (D-072, D-073): insert the parsed JSON tables into a fresh
database, and parse the CSV zip back with the schema's column types. V1 ships no import; these
prove that an export re-reads without loss."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa

from rack_overflow.domain import export as rules
from rack_overflow.storage import schema
from rack_overflow.storage.export import SECRET_COLUMNS

PLACEHOLDER = "not-exported"


def _placeholders(table: sa.Table, row: Mapping[str, Any]) -> dict[str, Any]:
    """The row with its secret columns filled (NULL when allowed, else a unique placeholder) and
    an absent JSON value as SQL `NULL` (not the JSON text `null`), as `storage` writes it."""
    filled = {
        key: sa.null() if value is None and isinstance(table.c[key].type, sa.JSON) else value
        for key, value in row.items()
    }
    for table_name, column in SECRET_COLUMNS:
        if table_name == table.name:
            filled[column] = None if table.c[column].nullable else f"{PLACEHOLDER}-{row['id']}"
    return filled


def load(connection: sa.Connection, tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    """Insert every exported row, parents before children (the export's own order)."""
    for name, rows in tables.items():
        table = schema.metadata.tables[name]
        if rows:
            connection.execute(sa.insert(table), [_placeholders(table, row) for row in rows])


def _typed(column: sa.Column[Any], cell: str) -> object:
    if cell == "":
        return None
    if isinstance(column.type, sa.Boolean):
        return {"1": True, "0": False}[cell]
    if isinstance(column.type, sa.JSON):
        return json.loads(cell)
    if isinstance(column.type, sa.Integer):
        return int(cell)
    return cell


def read_csv_zip(data: bytes) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """The header of a CSV export and its tables, cells typed by the schema (empty cell ≡ NULL)."""
    zipped = zipfile.ZipFile(io.BytesIO(data))
    header = json.loads(zipped.read(rules.HEADER_ENTRY))
    tables: dict[str, list[dict[str, Any]]] = {}
    for entry in zipped.namelist():
        if entry == rules.HEADER_ENTRY:
            continue
        name = entry.removesuffix(".csv")
        table = schema.metadata.tables[name]
        text = zipped.read(entry).decode(rules.CSV_ENCODING)
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=rules.CSV_DELIMITER)
        tables[name] = [{key: _typed(table.c[key], cell) for key, cell in row.items()} for row in reader]
    return header, tables
