"""The isolation guard, checked from the outside: inner tests run in a pytest subprocess
(run once per module, so `pytester`, function-scoped, is not used).

The inner run uses a copy of `tests/isolation.py` with a fake real home and a fake repository
inside the pytester folder, so the refusals are observable without touching the real ones.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import isolation
import pytest

GUARD = Path(isolation.__file__)

INNER_CONFTEST = """
from pathlib import Path
import isolation
import pytest

ROOT = Path(__file__).parent

def pytest_configure(config):
    for name in ("real_home", "external_network", "real_fsync"):
        config.addinivalue_line("markers", f"{name}(reason): opt-out")
    isolation.install(ROOT / "home", repo=ROOT / "repo")

@pytest.fixture(autouse=True)
def _guard(request, tmp_path_factory, monkeypatch):
    yield from isolation.guard(request, tmp_path_factory, monkeypatch)

@pytest.fixture
def strict_network():
    isolation.set_strict_network(True)
    yield
    isolation.set_strict_network(False)
"""

INNER_TESTS = """
import os
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
HOME = ROOT / "home"
REPO = ROOT / "repo"

def test_write_home():
    (HOME / "note.txt").write_text("x")

def test_write_home_caught():
    try:
        (HOME / "note.txt").write_text("x")
    except AssertionError:
        pass

def test_write_home_in_thread():
    worker = threading.Thread(target=lambda: os.mkdir(HOME / "made"))
    worker.start()
    worker.join()

def test_read_secret_file():
    (REPO / ".env").read_text()

def test_read_config_file():
    (REPO / "config.toml").read_text()

def test_read_local_folder():
    os.listdir(REPO / ".local")
    (REPO / ".local" / "data.txt").read_text()

def test_public_lookup():
    import socket
    socket.getaddrinfo("example.com", 443)

def test_public_connect():
    with socket.socket() as sock:
        sock.settimeout(0.01)
        sock.connect(("192.0.2.1", 9))

def test_loopback_bind_and_connect():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.create_connection(server.getsockname(), timeout=1):
            pass

def test_write_temp_and_repo(tmp_path):
    (tmp_path / "ok.txt").write_text("x")

def test_home_is_redirected():
    assert Path.home() != HOME

@pytest.mark.real_home(reason="writes the home on purpose")
def test_real_home_marker():
    (HOME / "allowed.txt").write_text("x")

@pytest.mark.real_home
def test_marker_without_reason():
    pass

@pytest.mark.external_network(reason="resolves a public name on purpose")
def test_external_network_marker():
    try:
        socket.getaddrinfo("example.invalid", 443)
    except OSError:
        pass

def test_strict_network(strict_network):
    socket.getaddrinfo("localhost", 80)

def test_fsync_is_skipped(tmp_path):
    with open(tmp_path / "f", "wb") as handle:
        assert os.fsync(handle.fileno()) is None
"""

FAILING = {
    "test_write_home",
    "test_write_home_caught",
    "test_write_home_in_thread",
    "test_read_secret_file",
    "test_read_config_file",
    "test_read_local_folder",
    "test_public_lookup",
    "test_public_connect",
    "test_marker_without_reason",
    "test_strict_network",
}
PASSING = {
    "test_loopback_bind_and_connect",
    "test_write_temp_and_repo",
    "test_home_is_redirected",
    "test_real_home_marker",
    "test_external_network_marker",
    "test_fsync_is_skipped",
}


@pytest.fixture(scope="module")
def inner_outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """Run the inner tests once; map each test name to its reported outcomes."""
    root = tmp_path_factory.mktemp("inner")
    shutil.copy(GUARD, root / "isolation.py")
    (root / "conftest.py").write_text(INNER_CONFTEST, encoding="utf-8")
    (root / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    for folder in ("home", "repo/.local"):
        (root / folder).mkdir(parents=True)
    for name in (".env", "config.toml", ".local/data.txt"):
        (root / "repo" / name).write_text("secret", encoding="utf-8")
    return _run_inner(root)


def _run_inner(root: Path) -> dict[str, set[str]]:
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist", "-rA", "-q"]
    temp = root / "tmp"  # the system temp folder is an allowed root: keep the fake home out of it
    temp.mkdir()
    result = subprocess.run(
        [*command, "--basetemp", str(root / "basetemp"), str(root / "test_inner.py")],
        cwd=root,
        env={**os.environ, "TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp)},
        capture_output=True,
        text=True,
        check=False,
    )
    outcomes: dict[str, set[str]] = {}
    for line in result.stdout.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] in {"PASSED", "FAILED", "ERROR"} and "::" in words[1]:
            outcomes.setdefault(words[1].split("::")[-1], set()).add(words[0])
    assert outcomes, result.stdout + result.stderr
    return outcomes


@pytest.mark.parametrize("name", sorted(FAILING))
def test_guard_fails_the_inner_test(inner_outcomes: dict[str, set[str]], name: str) -> None:
    assert inner_outcomes[name] & {"FAILED", "ERROR"}


@pytest.mark.parametrize("name", sorted(PASSING))
def test_guard_lets_the_inner_test_pass(inner_outcomes: dict[str, set[str]], name: str) -> None:
    assert inner_outcomes[name] == {"PASSED"}


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "[::1]", b"127.0.0.2"])
def test_loopback_hosts(host: object) -> None:
    assert isolation.is_loopback(host)


@pytest.mark.parametrize("host", ["example.com", "192.0.2.1", "", None, "0.0.0.0"])
def test_non_loopback_hosts(host: object) -> None:
    assert not isolation.is_loopback(host)


def test_snapshot_sees_a_change(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f").write_bytes(b"1")
    before = isolation.snapshot(tmp_path)
    assert before["a/f"][:2] == ("file", b"1")
    (tmp_path / "a" / "f").write_bytes(b"2")
    assert isolation.snapshot(tmp_path) != before


def test_loopback_socket_is_allowed_here() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
