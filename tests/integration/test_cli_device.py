"""`rack device add | list | revoke` in-process, on a migrated temporary database."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rack_overflow import cli
from rack_overflow.cli import main

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
ADDED = re.compile(
    r'^device "iPhone" added; pairing code (\d{4} \d{4}), valid until 2026-11-03T18:14:05Z \(10 minutes\)\n'
    r"open http://testserver:8765/appairage on the device and type the code\n$"
)


@pytest.fixture
def config(settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    """A migrated settings file; the CLI clock is fixed."""
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert main(["migrate", "--config", str(settings_file)]) == 0
    capsys.readouterr()
    return str(settings_file)


def test_add_prints_the_code_and_the_pairing_url(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["device", "add", "iPhone", "--config", config]) == 0
    assert ADDED.match(capsys.readouterr().out)


def test_pairing_url_uses_https_when_configured(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = settings_file.read_text(encoding="utf-8").replace("[storage]", "https = true\n\n[storage]")
    settings_file.write_text(text, encoding="utf-8")
    assert main(["migrate", "--config", str(settings_file)]) == 0
    capsys.readouterr()
    assert main(["device", "add", "iPhone", "--config", str(settings_file)]) == 0
    assert "open https://testserver:8765/appairage " in capsys.readouterr().out


def test_list_and_revoke(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["device", "list", "--config", config]) == 0
    assert capsys.readouterr().out == "no devices\n"
    assert main(["device", "add", "iPhone", "--config", config]) == 0
    assert main(["device", "add", "Mac de bureau", "--config", config]) == 0
    assert main(["device", "revoke", "iPhone", "--config", config]) == 0
    capsys.readouterr()
    assert main(["device", "list", "--config", config]) == 0
    assert capsys.readouterr().out == (
        "NAME           STATE    CREATED               LAST SEEN\n"
        "iPhone         revoked  2026-11-03T18:04:05Z  -\n"
        "Mac de bureau  pending  2026-11-03T18:04:05Z  -\n"
    )


def test_revoke_prints_a_confirmation(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    main(["device", "add", "iPhone", "--config", config])
    capsys.readouterr()
    assert main(["device", "revoke", "iPhone", "--config", config]) == 0
    assert capsys.readouterr().out == 'device "iPhone" revoked\n'


def test_duplicate_name_exits_1(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    main(["device", "add", "iPhone", "--config", config])
    capsys.readouterr()
    assert main(["device", "add", "iPhone", "--config", config]) == 1
    assert capsys.readouterr().err == 'rack: error: device "iPhone" already exists; revoke it first\n'


def test_revoke_unknown_exits_1(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["device", "revoke", "iPhone", "--config", config]) == 1
    assert capsys.readouterr().err == 'rack: error: no active device named "iPhone"\n'


def test_invalid_name_exits_1(config: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["device", "add", " ", "--config", config]) == 1
    assert capsys.readouterr().err == "rack: error: device name must not be empty\n"


@pytest.mark.parametrize("action", [["add", "iPhone"], ["list"], ["revoke", "iPhone"]])
def test_unmigrated_database_is_refused(
    settings_file: Path, action: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    (settings_file.parent / "data").mkdir()
    assert main(["device", *action, "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err == "rack: error: database is not up to date; run rack migrate\n"
    assert list((settings_file.parent / "data").iterdir()) == []


@pytest.mark.parametrize("argv", [["device"], ["device", "nope"], ["device", "add"], ["device", "list", "x"]])
def test_usage_errors_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2


def test_help_lists_the_device_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "device" in capsys.readouterr().out
