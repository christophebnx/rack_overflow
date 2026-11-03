"""The PreToolUse hook, run as Claude Code runs it: JSON on stdin, exit code 2 blocks."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / ".claude" / "hooks" / "guard_paths.py"
SECRET = ".e" + "nv"  # spelled apart so this file never trips the hook when Claude reads it
CONFIG = "config" + ".toml"
spec = importlib.util.spec_from_file_location("guard_paths", HOOK)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def run_hook(tool: str, **tool_input: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("name", [SECRET, CONFIG, f"./{SECRET}", str(REPO / CONFIG)])
def test_reading_a_secret_file_is_blocked(name: str) -> None:
    result = run_hook("Read", file_path=name)
    assert result.returncode == 2
    assert "Blocked by guard_paths" in result.stderr


def test_protected_folder_is_blocked() -> None:
    assert run_hook("Read", file_path=".local/credentials/token.json").returncode == 2
    assert run_hook("Grep", path=".local/credentials").returncode == 2


@pytest.mark.parametrize("name", ["README.md", f"{SECRET}.example", "src/x/config.py", ".local/dev-data/a"])
def test_ordinary_paths_pass(name: str) -> None:
    assert run_hook("Read", file_path=name).returncode == 0


@pytest.mark.parametrize("command", [f"cat {SECRET}", f"grep key {CONFIG}", "ls .local/credentials"])
def test_commands_naming_secrets_are_blocked(command: str) -> None:
    assert run_hook("Bash", command=command).returncode == 2


@pytest.mark.parametrize("command", [f"cat {SECRET}.example", "uv run pytest -q", "git status"])
def test_ordinary_commands_pass(command: str) -> None:
    assert run_hook("Bash", command=command).returncode == 0


@pytest.mark.parametrize(
    ("args", "branch", "blocked"),
    [
        (" origin main", "dev", True),
        (" origin dev:main", "dev", True),
        (" origin HEAD", "main", True),
        ("", "main", True),
        (" -u origin dev", "dev", False),
        (" origin feature/x", "main", False),
        ("", "dev", False),
    ],
)
def test_push_to_a_protected_branch(args: str, branch: str, blocked: bool) -> None:
    assert guard.pushes_protected(args, branch) is blocked
