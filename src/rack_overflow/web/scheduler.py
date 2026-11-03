"""The daily backup inside the server (D-037, D-045): checked at start-up, then every hour."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from rack_overflow.config import Settings
from rack_overflow.services import backups

logger = logging.getLogger(__name__)
CHECK_INTERVAL_S = 3600.0


async def backup_once(settings: Settings, clock: Callable[[], datetime]) -> None:
    """Take a snapshot if one is due; log a failure and return (the server keeps serving)."""
    try:
        snapshot = await asyncio.to_thread(
            backups.backup_if_due,
            settings.database_path,
            settings.backups_dir,
            clock(),
            settings.backup.retention_days,
        )
    except Exception:
        logger.exception("daily backup failed")
        return
    if snapshot is not None:
        logger.info("backup written to %s", snapshot)


async def run_daily_backup(
    settings: Settings, clock: Callable[[], datetime], interval_s: float = CHECK_INTERVAL_S
) -> None:
    """Loop forever: `backup_once`, then sleep `interval_s`. Cancelled by the app lifespan."""
    while True:
        await backup_once(settings, clock)
        await asyncio.sleep(interval_s)
