"""The installed entry points, run as a user runs them (a subprocess, not `main([...])`)."""

import subprocess
import sys
from pathlib import Path

from rack_overflow import __version__


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "rack_overflow", *args], capture_output=True, text=True, check=False
    )


def test_python_dash_m_prints_the_version() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout == f"rack {__version__}\n"


def test_migrate_in_a_subprocess(settings_file: Path) -> None:
    result = run_cli("migrate", "--config", str(settings_file))
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("at revision 0001\n")
    assert (settings_file.parent / "data" / "rack.sqlite").is_file()
