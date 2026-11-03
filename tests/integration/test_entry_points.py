"""The installed entry points, run as a user runs them (a subprocess, not `main([...])`)."""

import subprocess
import sys


def test_python_dash_m_runs_the_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "template_python", "hello", "Ada"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Hello, Ada!\n"
