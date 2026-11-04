"""The export format (D-072, D-073): JSON document, CSV zip, file names, reader refusals."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta, timezone

import pytest

from rack_overflow.domain import export
from rack_overflow.domain.export import ExportError, ExportMeta

AT = datetime(2026, 11, 3, 18, 42, 7, tzinfo=UTC)
META = ExportMeta(export.FORMAT_VERSION, "1.0.0", "0004", AT)
TABLES = {
    "variable": [
        {"id": 1, "label": "Prise", "enum_values": [{"key": "large", "label": "Large"}], "scale": None},
    ],
    "exercise_field": [
        {"id": 1, "required": True, "discrete_values": [8, 12]},
        {"id": 2, "required": False, "discrete_values": None},
    ],
    "session": [{"id": 1, "notes": 'a;b "c"\nd'}],
}
COLUMNS = {
    "variable": ["id", "label", "enum_values", "scale"],
    "exercise_field": ["id", "required", "discrete_values"],
    "session": ["id", "notes"],
}


def test_json_keys_in_order_and_values_as_stored() -> None:
    document = json.loads(export.to_json(META, TABLES))
    assert list(document) == [
        "format",
        "format_version",
        "app_version",
        "schema_revision",
        "exported_at",
        "units",
        "tables",
    ]
    assert document["format"] == "rack-overflow-export"
    assert document["format_version"] == 1
    assert document["exported_at"] == "2026-11-03T18:42:07Z"
    assert document["units"] == {"weight": "g", "duration": "s", "distance": "m"}
    assert document["tables"]["variable"][0]["enum_values"] == [{"key": "large", "label": "Large"}]
    assert document["tables"]["exercise_field"][0]["required"] is True
    assert document["tables"]["variable"][0]["scale"] is None


def test_json_is_deterministic_utf8_with_raw_accents() -> None:
    data = export.to_json(META, {"variable": [{"label": "Serrée"}]})
    assert data == export.to_json(META, {"variable": [{"label": "Serrée"}]})
    assert "Serrée".encode() in data
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\\u00e9" not in data


def test_json_round_trip() -> None:
    meta, tables = export.read_json(export.to_json(META, TABLES))
    assert meta == META
    assert tables == TABLES


def test_exported_at_written_in_utc() -> None:
    local = AT.astimezone(timezone(timedelta(hours=1)))
    meta = ExportMeta(1, "1.0.0", "0004", local)
    assert json.loads(export.to_json(meta, {}))["exported_at"] == "2026-11-03T18:42:07Z"


def _document(**changes: object) -> bytes:
    document = json.loads(export.to_json(META, TABLES))
    document.update(changes)
    return json.dumps(document).encode()


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xff\xfe", "not_json"),
        (b"{not json", "not_json"),
        (b"[]", "not_an_export"),
        (_document(format="other"), "not_an_export"),
        (_document(format_version=2), "unsupported_version"),
        (_document(format_version=True), "unsupported_version"),
        (_document(format_version="1"), "unsupported_version"),
        (_document(app_version=1), "malformed"),
        (_document(schema_revision=None), "malformed"),
        (_document(exported_at="yesterday"), "malformed"),
        (_document(tables=[]), "malformed"),
        (_document(tables={"session": {}}), "malformed"),
        (_document(tables={"session": [1]}), "malformed"),
    ],
)
def test_read_json_refuses(data: bytes, code: str) -> None:
    with pytest.raises(ExportError) as caught:
        export.read_json(data)
    assert caught.value.code == code


def _zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def test_csv_zip_entries_header_and_dates() -> None:
    zipped = _zip(export.to_csv_zip(META, TABLES, COLUMNS))
    assert zipped.namelist() == ["export.json", "variable.csv", "exercise_field.csv", "session.csv"]
    header = json.loads(zipped.read("export.json"))
    assert "tables" not in header
    assert header["schema_revision"] == "0004"
    assert header["exported_at"] == "2026-11-03T18:42:07Z"
    for info in zipped.infolist():
        assert info.date_time == (2026, 11, 3, 18, 42, 6)  # zip times have a 2 s resolution
        assert info.compress_type == zipfile.ZIP_DEFLATED


def test_csv_is_deterministic() -> None:
    assert export.to_csv_zip(META, TABLES, COLUMNS) == export.to_csv_zip(META, TABLES, COLUMNS)


def test_csv_bom_separator_crlf_and_quoting() -> None:
    zipped = _zip(export.to_csv_zip(META, TABLES, COLUMNS))
    raw = zipped.read("session.csv")
    assert raw.startswith(b"\xef\xbb\xbfid;notes\r\n")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=";"))
    assert rows == [["id", "notes"], ["1", 'a;b "c"\nd']]


def test_csv_cells() -> None:
    zipped = _zip(export.to_csv_zip(META, TABLES, COLUMNS))
    fields = list(
        csv.reader(io.StringIO(zipped.read("exercise_field.csv").decode("utf-8-sig")), delimiter=";")
    )
    assert fields[1:] == [["1", "1", "[8, 12]"], ["2", "0", ""]]
    variables = list(csv.reader(io.StringIO(zipped.read("variable.csv").decode("utf-8-sig")), delimiter=";"))
    assert json.loads(variables[1][2]) == [{"key": "large", "label": "Large"}]
    assert variables[1][3] == ""


def test_csv_table_without_rows_has_its_header() -> None:
    zipped = _zip(export.to_csv_zip(META, {}, {"device": ["id", "name"]}))
    assert zipped.read("device.csv") == b"\xef\xbb\xbfid;name\r\n"


@pytest.mark.parametrize(
    ("value", "text"),
    [(None, ""), (True, "1"), (False, "0"), (0, "0"), ("é", "é"), ({"a": "é"}, '{"a": "é"}')],
)
def test_csv_cell(value: object, text: str) -> None:
    assert export.csv_cell(value) == text


def test_file_names() -> None:
    assert export.file_name("json", AT) == "rack-overflow-20261103T184207Z.json"
    assert export.file_name("csv", AT) == "rack-overflow-20261103T184207Z-csv.zip"
    with pytest.raises(ExportError) as caught:
        export.file_name("xml", AT)
    assert caught.value.code == "unknown_format"
