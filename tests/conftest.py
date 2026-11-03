"""Shared fixtures. The isolation guard (`isolation.py`) wraps every test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import isolation
import pytest
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings, load_settings
from rack_overflow.storage import db, migrate

SETTINGS_TEMPLATE = """\
[server]
host = "127.0.0.1"
port = 8765
public_host = "testserver"

[storage]
data_dir = "data"
"""


def pytest_configure(config: pytest.Config) -> None:
    """Record the real home before any redirection and install the audit hook (once per process)."""
    del config
    isolation.install(Path.home())


@pytest.fixture(autouse=True)
def _isolation_guard(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    yield from isolation.guard(request, tmp_path_factory, monkeypatch)


@pytest.fixture
def strict_network() -> Iterator[None]:
    """Refuse every name lookup during the test, loopback included."""
    isolation.set_strict_network(True)
    yield
    isolation.set_strict_network(False)


@pytest.fixture
def snapshot() -> isolation.Snapshot:
    """`snapshot(folder)` maps a folder tree to (kind, bytes, mtime) to assert nothing changed."""
    return isolation.snapshot


@pytest.fixture(autouse=True)
def _skip_sqlite_flush(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """New connections use `synchronous = OFF` unless the test is marked `real_fsync`."""
    if request.node.get_closest_marker("real_fsync") is None:
        monkeypatch.setattr(db, "SYNCHRONOUS", "OFF")


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    """A valid settings file in `tmp_path` (data folder `tmp_path/data`, host `testserver`)."""
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
    return path


@pytest.fixture
def settings(settings_file: Path) -> Settings:
    """The settings loaded from `settings_file`, data folder created."""
    loaded = load_settings(settings_file)
    loaded.storage.data_dir.mkdir()
    return loaded


@pytest.fixture
def migrated_engine(settings: Settings) -> Iterator[Engine]:
    """An engine on a database at the head revision, disposed after the test."""
    engine = db.create_engine(settings.database_path)
    migrate.upgrade_to_head(engine)
    yield engine
    engine.dispose()
