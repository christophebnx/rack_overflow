import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_commit_message.py"
spec = importlib.util.spec_from_file_location("check_commit_message", TOOL)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

VALID = "feat(domain): add the greeting rule\n\nWhy and what.\n\nMilestone: M1\n"


def test_valid_message() -> None:
    assert check.problems(VALID) == []


def test_comments_and_trailing_blank_lines_are_ignored() -> None:
    assert check.problems(VALID + "\n# Please enter the commit message\n\n") == []


@pytest.mark.parametrize(
    ("message", "fragment"),
    [
        ("add stuff\n\nMilestone: M1", "first line"),
        ("feature(domain): add stuff\n\nMilestone: M1", "first line"),
        ("feat(domain): " + "x" * 60 + "\n\nMilestone: M1", "at most 72"),
        ("feat(domain): add stuff\nbody\n\nMilestone: M1", "second line"),
        ("feat(domain): add stuff\n\nbody", "Milestone"),
        ("", "first line"),
    ],
)
def test_invalid_messages(message: str, fragment: str) -> None:
    assert any(fragment in problem for problem in check.problems(message))


@pytest.mark.parametrize("message", ["Merge branch 'dev'", 'Revert "feat(x): y"', "fixup! feat(x): y"])
def test_git_generated_messages_pass(message: str) -> None:
    assert check.problems(message) == []


def test_main_reads_the_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("bad", encoding="utf-8")
    assert check.main([str(message)]) == 1
    assert "commit message:" in capsys.readouterr().err
    message.write_text(VALID, encoding="utf-8")
    assert check.main([str(message)]) == 0
