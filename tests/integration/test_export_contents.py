"""The export holds every stored fact and re-reads without loss (roadmap L6; D-072, D-073)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from support.export_loader import load, read_csv_zip
from support.populated import NOW, populate

from rack_overflow.domain import export as rules
from rack_overflow.domain.export import ExportError
from rack_overflow.services import export
from rack_overflow.storage import db, migrate
from rack_overflow.storage import export as contents
from rack_overflow.storage.export import SECRET_COLUMNS

VERSION = "1.0.0"


@pytest.fixture
def populated(migrated_engine: Engine) -> Engine:
    populate(migrated_engine)
    return migrated_engine


def _dump(engine: Engine) -> dict[str, list[dict[str, object]]]:
    with engine.begin() as connection:
        return contents.dump(connection)


def _database_columns(engine: Engine) -> dict[str, list[str]]:
    """Tables and columns of the migrated database itself (not of `schema.py`)."""
    with engine.connect() as connection:
        names = [
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND name != 'alembic_version'"
            )
        ]
        return {
            name: [row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({name})")]
            for name in names
        }


def test_every_table_and_column_is_exported_except_the_secrets(migrated_engine: Engine) -> None:
    columns = contents.exported_columns()
    stored = _database_columns(migrated_engine)
    assert set(columns) == set(stored)
    for name, names in stored.items():
        expected = [column for column in names if (name, column) not in SECRET_COLUMNS]
        assert columns[name] == expected, name
    assert "token_hash" not in columns["device"]
    assert "code_hash" not in columns["pairing_code"]


def test_tables_come_parents_first() -> None:
    order = list(contents.exported_columns())
    assert order.index("session") < order.index("session_exercise") < order.index("set_entry")
    assert order.index("set_entry") < order.index("set_value")
    assert order.index("device") < order.index("pairing_code")


def test_population_fills_every_table(populated: Engine) -> None:
    assert all(_dump(populated).values())


def test_json_export_reads_back_as_the_dump(populated: Engine) -> None:
    file = export.export(populated, "json", NOW, VERSION)
    meta, tables = rules.read_json(file.data)
    assert meta == rules.ExportMeta(1, VERSION, migrate.head_revision(), NOW)
    assert tables == _dump(populated)
    assert file.rows == sum(len(rows) for rows in tables.values())
    assert file.file_name == "rack-overflow-20261103T184200Z.json"
    assert file.media_type == "application/json; charset=utf-8"


def test_json_export_holds_no_secret(populated: Engine) -> None:
    with populated.connect() as connection:
        hashes = [
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT token_hash FROM device WHERE token_hash IS NOT NULL "
                "UNION SELECT code_hash FROM pairing_code"
            )
        ]
    data = export.export(populated, "json", NOW, VERSION).data.decode()
    assert hashes
    assert not any(value in data for value in hashes)


def test_soft_deleted_and_archived_rows_are_exported(populated: Engine) -> None:
    tables = rules.read_json(export.export(populated, "json", NOW, VERSION).data)[1]
    for name in ("session", "set_entry", "template_slot", "rm_measured"):
        assert any(row["deleted_at"] for row in tables[name]), name
    for name in ("exercise", "variable", "template"):
        assert any(row["archived_at"] for row in tables[name]), name
    assert any(row["revoked_at"] for row in tables["device"])


def test_json_export_loads_into_a_fresh_database_without_loss(populated: Engine, tmp_path: Path) -> None:
    tables = rules.read_json(export.export(populated, "json", NOW, VERSION).data)[1]
    fresh = db.create_engine(tmp_path / "fresh.sqlite")
    try:
        migrate.upgrade_to_head(fresh)
        with fresh.begin() as connection:
            load(connection, tables)
        assert _dump(fresh) == _dump(populated)
    finally:
        fresh.dispose()


def test_csv_export_reads_back_as_the_dump(populated: Engine) -> None:
    file = export.export(populated, "csv", NOW, VERSION)
    header, tables = read_csv_zip(file.data)
    assert header["format"] == rules.FORMAT
    assert header["schema_revision"] == migrate.head_revision()
    assert list(tables) == list(contents.exported_columns())
    assert tables == _dump(populated)
    assert file.file_name == "rack-overflow-20261103T184200Z-csv.zip"
    assert file.media_type == "application/zip"


def test_empty_database_exports(migrated_engine: Engine) -> None:
    tables = rules.read_json(export.export(migrated_engine, "json", NOW, VERSION).data)[1]
    assert set(tables) == set(contents.exported_columns())
    assert not any(tables.values())


def test_export_is_deterministic(populated: Engine) -> None:
    first = export.export(populated, "json", NOW, VERSION).data
    assert first == export.export(populated, "json", NOW, VERSION).data
    assert json.loads(first)["app_version"] == VERSION


def test_unknown_format_is_refused(migrated_engine: Engine) -> None:
    with pytest.raises(ExportError) as caught:
        export.export(migrated_engine, "xml", NOW, VERSION)
    assert caught.value.code == "unknown_format"
