from pathlib import Path

import pytest

from rack_overflow import __version__
from rack_overflow.cli import main


def test_migrate_creates_the_database_and_is_idempotent(
    settings_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = settings_file.parent / "data" / "rack.sqlite"
    assert main(["migrate", "--config", str(settings_file)]) == 0
    first = capsys.readouterr().out
    assert first == f"database {database} at revision 0001\n"
    assert main(["migrate", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out == first


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
