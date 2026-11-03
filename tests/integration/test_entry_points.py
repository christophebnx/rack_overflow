"""The installed entry points, run as a user runs them (a subprocess, not `main([...])`)."""

import http.client
import socket
import subprocess
import sys
import time
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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_home(port: int, deadline: float) -> int:
    while True:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/", headers={"Accept": "text/html"})
            return connection.getresponse().status
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)
        finally:
            connection.close()


def test_serve_answers_the_home_page(settings_file: Path) -> None:
    port = _free_port()
    settings_file.write_text(
        settings_file.read_text(encoding="utf-8").replace("port = 8765", f"port = {port}"), encoding="utf-8"
    )
    assert run_cli("migrate", "--config", str(settings_file)).returncode == 0
    server = subprocess.Popen(
        [sys.executable, "-m", "rack_overflow", "serve", "--config", str(settings_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        assert _get_home(port, time.monotonic() + 20) == 200
    finally:
        server.terminate()
        server.communicate(timeout=10)


def test_serve_refuses_an_unmigrated_database(settings_file: Path) -> None:
    result = run_cli("serve", "--config", str(settings_file))
    assert result.returncode == 1
    assert result.stderr == "rack: error: database is not up to date; run rack migrate\n"
