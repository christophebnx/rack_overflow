"""The export operation (D-072 to D-074), shared by `rack export` and `GET /api/export`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Engine

from rack_overflow.domain import export as rules
from rack_overflow.storage import export as contents
from rack_overflow.storage import migrate

FORMATS = (rules.JSON_KIND, rules.CSV_KIND)
MEDIA_TYPES = {rules.JSON_KIND: "application/json; charset=utf-8", rules.CSV_KIND: "application/zip"}


@dataclass(frozen=True)
class ExportFile:
    """An export ready to save or send: its file name, media type and bytes, and its row count."""

    file_name: str
    media_type: str
    data: bytes
    rows: int


def export(engine: Engine, fmt: str, now: datetime, app_version: str) -> ExportFile:
    """The whole database as a `json` or `csv` export, read in one transaction (consistent);
    an unknown format → `ExportError("unknown_format")`, nothing read."""
    if fmt not in FORMATS:
        raise rules.ExportError("unknown_format")
    revision = migrate.current_revision(engine) or ""
    with engine.begin() as connection:
        tables = contents.dump(connection)
    meta = rules.ExportMeta(rules.FORMAT_VERSION, app_version, revision, now)
    if fmt == rules.JSON_KIND:
        data = rules.to_json(meta, tables)
    else:
        data = rules.to_csv_zip(meta, tables, contents.exported_columns())
    rows = sum(len(table_rows) for table_rows in tables.values())
    return ExportFile(rules.file_name(fmt, now), MEDIA_TYPES[fmt], data, rows)
