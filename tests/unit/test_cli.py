import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from rack_overflow import __version__, cli
from rack_overflow.cli import main


def test_migrate_creates_the_database_and_is_idempotent(
    settings_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = settings_file.parent / "data" / "rack.sqlite"
    assert main(["migrate", "--config", str(settings_file)]) == 0
    first = capsys.readouterr().out
    assert first.splitlines()[0] == f"database {database} at revision 0003"
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out == f"database {database} at revision 0003\n"


def test_missing_settings_file_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.toml"
    assert main(["migrate", "--config", str(missing)]) == 1
    assert capsys.readouterr().err == f"rack: error: settings file not found: {missing}\n"


def test_no_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["nope"], ["migrate", "--bad"]])
def test_usage_errors_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"rack {__version__}"


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """`rack serve` reconfigures the root logger; put it back after the test."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_serve_runs_uvicorn_with_the_settings(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    del restore_logging
    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert main(["serve", "--config", str(settings_file)]) == 0
    [(app, kwargs)] = calls
    assert isinstance(app, FastAPI)
    assert kwargs == {
        "host": "127.0.0.1",
        "port": 8765,
        "server_header": False,
        "proxy_headers": False,
        "log_config": None,
    }
    root = logging.getLogger()
    assert root.level == logging.INFO
    assert [type(handler) for handler in root.handlers] == [logging.StreamHandler]


def test_serve_refuses_a_missing_database_without_creating_it(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: pytest.fail("served"))
    (settings_file.parent / "data").mkdir()
    assert main(["serve", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err == "rack: error: database is not up to date; run rack migrate\n"
    assert list((settings_file.parent / "data").iterdir()) == []


def test_serve_refuses_an_empty_database(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: pytest.fail("served"))
    (settings_file.parent / "data").mkdir()
    (settings_file.parent / "data" / "rack.sqlite").write_bytes(b"")
    assert main(["serve", "--config", str(settings_file)]) == 1
    assert "run rack migrate" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["migrate", "serve"])
def test_non_database_file_is_a_clean_error(
    settings_file: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    database = settings_file.parent / "data" / "rack.sqlite"
    database.parent.mkdir()
    content = b"this is not a database" * 300
    database.write_bytes(content)
    assert main([command, "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err.startswith("rack: error: ")
    assert database.read_bytes() == content
    assert not (database.parent / "backups").exists()


@pytest.mark.parametrize("command", ["migrate", "backup", "serve"])
def test_invalid_settings_exit_1_for_every_command(
    tmp_path: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("[server\n", encoding="utf-8")
    assert main([command, "--config", str(path)]) == 1
    error = capsys.readouterr().err
    assert error.startswith(f"rack: error: {path}: malformed TOML")
    assert error.count("\n") == 1


def test_default_settings_file_is_in_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["backup"]) == 1
    assert capsys.readouterr().err == f"rack: error: settings file not found: {cli.DEFAULT_CONFIG}\n"


def test_backup_without_a_database_exits_1(settings_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err.startswith("rack: error: database not found: ")


def test_migrate_creates_a_nested_data_folder(tmp_path: Path, settings_file: Path) -> None:
    text = settings_file.read_text(encoding="utf-8").replace('"data"', '"deep/er/data"')
    settings_file.write_text(text, encoding="utf-8")
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert (tmp_path / "deep" / "er" / "data" / "rack.sqlite").is_file()
    assert not (tmp_path / "deep" / "er" / "data" / "backups").exists()  # new database: no snapshot


def test_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert all(name in out for name in ("migrate", "backup", "serve"))
    assert "hello" not in out


def test_migrate_reports_a_data_folder_that_cannot_be_created(
    settings_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (settings_file.parent / "data").write_bytes(b"a file where the folder should be")
    assert main(["migrate", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err.startswith("rack: error: cannot create data folder")
