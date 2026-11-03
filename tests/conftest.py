"""Shared fixtures. The isolation guard (`isolation.py`) wraps every test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import isolation
import pytest


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
