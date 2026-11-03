import pytest

from rack_overflow import __version__
from rack_overflow.cli import main


def test_hello_prints_a_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["hello", "Ada"]) == 0
    assert capsys.readouterr().out == "Hello, Ada!\n"


def test_domain_error_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["hello", " "]) == 1
    assert capsys.readouterr().err == "rack: error: name is empty\n"


def test_no_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_unknown_command_exits_2() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["nope"])
    assert exit_info.value.code == 2


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"rack {__version__}"
