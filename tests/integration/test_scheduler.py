"""The daily backup run by the server (injected clock)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.storage import backup
from rack_overflow.web import scheduler
from rack_overflow.web.app import create_app

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def test_one_snapshot_at_start_up_none_on_a_second_start_the_same_day(
    settings: Settings, migrated_engine: Engine
) -> None:
    asyncio.run(scheduler.backup_once(settings, lambda: NOW))
    asyncio.run(scheduler.backup_once(settings, lambda: NOW + timedelta(hours=5)))
    assert len(backup.list_snapshots(settings.backups_dir)) == 1


def test_failure_is_logged_and_swallowed(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        asyncio.run(scheduler.backup_once(settings, lambda: NOW))  # no database yet
    assert "daily backup failed" in caplog.text


def test_lifespan_starts_the_scheduler(settings: Settings, migrated_engine: Engine) -> None:
    app = create_app(settings, migrated_engine, clock=lambda: NOW)
    with TestClient(app):
        for _ in range(200):
            if backup.list_snapshots(settings.backups_dir):
                break
            asyncio.run(asyncio.sleep(0.01))
    assert len(backup.list_snapshots(settings.backups_dir)) == 1
