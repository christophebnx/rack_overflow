"""The export format (D-072, D-073): one JSON document, or a zip of one CSV per table.

Pure: bytes in, bytes out; the export time is passed in. `tables` is an ordered
`{table: [row dict]}` (parents before children, rows by id) and `columns` an ordered
`{table: [column]}`; values are the stored facts (canonical integers, keys, UTC text, JSON
columns as nested values, booleans), never a computed indicator.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.timestamps import TimestampError, from_text, to_text

FORMAT = "rack-overflow-export"
FORMAT_VERSION = 1
UNITS = {"weight": "g", "duration": "s", "distance": "m"}
JSON_KIND = "json"
CSV_KIND = "csv"
HEADER_ENTRY = "export.json"
CSV_DELIMITER = ";"
CSV_LINE_END = "\r\n"
CSV_ENCODING = "utf-8-sig"  # with BOM: Excel otherwise reads accents as Latin-1
FILE_TIME_FORMAT = "%Y%m%dT%H%M%SZ"
ENTRY_MODE = 0o644 << 16  # rw-r--r-- for the unzipped files

Tables = Mapping[str, Sequence[Mapping[str, Any]]]
Columns = Mapping[str, Sequence[str]]


class ExportError(DomainError):
    """An export could not be written or read (`code` is stable: `unknown_format`, `not_json`,
    `not_an_export`, `unsupported_version`, `malformed`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExportMeta:
    """The header of an export: format version, app version, schema revision, UTC export time."""

    format_version: int
    app_version: str
    schema_revision: str
    exported_at: datetime


def _header(meta: ExportMeta) -> dict[str, Any]:
    """The document keys before `tables`, in their fixed order."""
    return {
        "format": FORMAT,
        "format_version": meta.format_version,
        "app_version": meta.app_version,
        "schema_revision": meta.schema_revision,
        "exported_at": to_text(meta.exported_at),
        "units": dict(UNITS),
    }


def _dumps(document: Mapping[str, Any]) -> bytes:
    """UTF-8 JSON, accents kept raw, two-space indent, keys in the given order."""
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def to_json(meta: ExportMeta, tables: Tables) -> bytes:
    """The JSON export: same `meta` and `tables` → same bytes."""
    document = _header(meta)
    document["tables"] = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    return _dumps(document)


def _object(data: bytes) -> dict[str, Any]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExportError("not_json") from None
    if not isinstance(document, dict):
        raise ExportError("not_an_export")
    return document


def _meta(document: Mapping[str, Any]) -> ExportMeta:
    if document.get("format") != FORMAT:
        raise ExportError("not_an_export")
    version = document.get("format_version")
    if isinstance(version, bool) or version != FORMAT_VERSION:
        raise ExportError("unsupported_version")
    app_version, revision = document.get("app_version"), document.get("schema_revision")
    if not isinstance(app_version, str) or not isinstance(revision, str):
        raise ExportError("malformed")
    try:
        exported_at = from_text(str(document.get("exported_at")))
    except TimestampError:
        raise ExportError("malformed") from None
    return ExportMeta(version, app_version, revision, exported_at)


def _tables(value: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        raise ExportError("malformed")
    for rows in value.values():
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ExportError("malformed")
    return value


def read_json(data: bytes) -> tuple[ExportMeta, dict[str, list[dict[str, Any]]]]:
    """The reference reader of the JSON export (version 1 only): its header and its tables."""
    document = _object(data)
    return _meta(document), _tables(document.get("tables"))


def csv_cell(value: object) -> str:
    """A stored value as CSV text: `NULL` empty, booleans `1` / `0`, JSON columns as JSON text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _csv(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator=CSV_LINE_END)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([csv_cell(row[column]) for column in columns])
    return buffer.getvalue().encode(CSV_ENCODING)


def _entry(zipped: zipfile.ZipFile, name: str, data: bytes, moment: datetime) -> None:
    info = zipfile.ZipInfo(name, date_time=moment.astimezone(UTC).timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ENTRY_MODE
    zipped.writestr(info, data)


def to_csv_zip(meta: ExportMeta, tables: Tables, columns: Columns) -> bytes:
    """The CSV export: `export.json` (the header) then one `<table>.csv` per table of `columns`,
    entries dated `exported_at`; same inputs → same bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        _entry(zipped, HEADER_ENTRY, _dumps(_header(meta)), meta.exported_at)
        for name, names in columns.items():
            _entry(zipped, f"{name}.csv", _csv(names, tables.get(name, ())), meta.exported_at)
    return buffer.getvalue()


def file_name(kind: str, exported_at: datetime) -> str:
    """`rack-overflow-<UTC YYYYMMDDTHHMMSSZ>.json` or `rack-overflow-<…>-csv.zip`."""
    stamp = exported_at.astimezone(UTC).strftime(FILE_TIME_FORMAT)
    if kind == JSON_KIND:
        return f"rack-overflow-{stamp}.json"
    if kind == CSV_KIND:
        return f"rack-overflow-{stamp}-csv.zip"
    raise ExportError("unknown_format")
