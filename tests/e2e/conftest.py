"""Browser test fixtures (D-042): a live server in a thread and Playwright browsers, no pytest-playwright.

Each browser engine is launched separately and skipped when its executable is missing, unless
`RACK_REQUIRE_BROWSER=1`, which turns the skip into a failure. The browsers folder is recorded
before the isolation guard redirects the home folder, which would otherwise hide it.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, BrowserType, Playwright, sync_playwright

from rack_overflow.config import load_settings
from rack_overflow.storage import db, migrate
from rack_overflow.web.app import create_app

ENGINES = ("chromium", "webkit")
REQUIRE_BROWSER = "RACK_REQUIRE_BROWSER"
BROWSERS_PATH_VARIABLE = "PLAYWRIGHT_BROWSERS_PATH"
_BROWSERS: dict[str, str] = {}

SERVER_SETTINGS = """\
[server]
host = "127.0.0.1"
port = {port}
public_host = "127.0.0.1"

[storage]
data_dir = "data"
"""


def _default_browsers_path(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "ms-playwright"


def pytest_configure(config: pytest.Config) -> None:
    """Record the browsers folder before any home redirection."""
    del config
    _BROWSERS["path"] = os.environ.get(BROWSERS_PATH_VARIABLE) or str(_default_browsers_path(Path.home()))
    _BROWSERS["require"] = os.environ.get(REQUIRE_BROWSER, "")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Base URL of the app served by uvicorn on a free loopback port, on a temp migrated database."""
    folder = tmp_path_factory.mktemp("live")
    settings_path = folder / "settings.toml"
    settings_path.write_text(SERVER_SETTINGS.format(port=_free_port()), encoding="utf-8")
    settings = load_settings(settings_path)
    settings.storage.data_dir.mkdir()
    engine = db.create_engine(settings.database_path)
    migrate.upgrade_to_head(engine)
    app = create_app(settings, engine, clock=lambda: datetime.now(UTC), run_scheduler=False)
    config = uvicorn.Config(app, host="127.0.0.1", port=settings.server.port, log_config=None, lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("live server did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{settings.server.port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def playwright() -> Iterator[Playwright]:
    """The Playwright driver, pointed at the browsers folder recorded at start-up."""
    previous = os.environ.get(BROWSERS_PATH_VARIABLE)
    os.environ[BROWSERS_PATH_VARIABLE] = _BROWSERS["path"]  # read by the driver subprocess at start
    try:
        with sync_playwright() as driver:
            yield driver
    finally:
        if previous is None:
            os.environ.pop(BROWSERS_PATH_VARIABLE, None)
        else:
            os.environ[BROWSERS_PATH_VARIABLE] = previous


def _skip_or_fail(message: str) -> None:
    if _BROWSERS.get("require") == "1":
        pytest.fail(f"{message} ({REQUIRE_BROWSER}=1)")
    pytest.skip(message)


@pytest.fixture(scope="session", params=ENGINES)
def browser(request: pytest.FixtureRequest, playwright: Playwright) -> Iterator[Browser]:
    """One browser per engine; skipped when the engine is not installed."""
    engine: BrowserType = getattr(playwright, request.param)
    if not Path(engine.executable_path).exists():
        _skip_or_fail(f"{request.param} not installed")
    try:
        launched = engine.launch()
    except Exception as error:  # missing system libraries, broken install
        _skip_or_fail(f"{request.param} cannot start: {str(error).splitlines()[0]}")
        raise
    yield launched
    launched.close()
