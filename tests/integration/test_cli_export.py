"""`rack export PATH [--format json|csv]` in-process, on a populated temporary database."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from support.populated import populate

from rack_overflow import __version__, cli
from rack_overflow.cli import main
from rack_overflow.config import load_settings
from rack_overflow.domain import export as rules
from rack_overflow.storage import db

NOW = datetime(2026, 11, 3, 18, 42, tzinfo=UTC)


@pytest.fixture
def config(settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    """A migrated, populated settings file; the CLI clock is fixed."""
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert main(["migrate", "--config", str(settings_file)]) == 0
    engine = db.create_engine(load_settings(settings_file).database_path)
    try:
        populate(engine)
    finally:
        engine.dispose()
    capsys.readouterr()
    return str(settings_file)


def test_json_export_is_written(config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "out.json"
    assert main(["export", str(target), "--config", config]) == 0
    meta, tables = rules.read_json(target.read_bytes())
    rows = sum(len(rows) for rows in tables.values())
    assert capsys.readouterr().out == f"exported {rows} rows to {target}\n"
    assert meta.app_version == __version__
    assert meta.exported_at == NOW
    assert tables["session"]
    assert [path.name for path in tmp_path.iterdir() if path.name.startswith(".tmp-")] == []


def test_csv_export_is_a_zip(config: str, tmp_path: Path) -> None:
    target = tmp_path / "out.zip"
    assert main(["export", str(target), "--format", "csv", "--config", config]) == 0
    names = zipfile.ZipFile(target).namelist()
    assert names[0] == "export.json"
    assert "set_entry.csv" in names


def test_existing_path_is_refused(config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "keep.txt"
    target.write_text("mine", encoding="utf-8")
    assert main(["export", str(target), "--config", config]) == 1
    assert capsys.readouterr().err == f"rack: error: {target} already exists; choose a new file name\n"
    assert target.read_text(encoding="utf-8") == "mine"


def test_missing_folder_is_refused(config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "nope" / "out.json"
    assert main(["export", str(target), "--config", config]) == 1
    assert capsys.readouterr().err == f"rack: error: folder not found: {target.parent}\n"
    assert not target.parent.exists()


def test_stale_database_is_refused(
    settings_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (settings_file.parent / "data").mkdir()
    target = tmp_path / "out.json"
    assert main(["export", str(target), "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err == "rack: error: database is not up to date; run rack migrate\n"
    assert not target.exists()


def test_export_while_another_engine_holds_the_database(config: str, tmp_path: Path) -> None:
    engine = db.create_engine(load_settings(Path(config)).database_path)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT count(*) FROM session").fetchall()
            connection.commit()  # the server's connection stays open between its short transactions
            assert main(["export", str(tmp_path / "out.json"), "--config", config]) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("argv", [["export"], ["export", "x.json", "--format", "xml"]])
def test_usage_errors_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2
