"""Stop a migration at an older revision (tests of revisions and of restoring older snapshots)."""

from __future__ import annotations

from typing import Any

from alembic.config import Config

from rack_overflow.storage import migrate

REAL_UPGRADE = migrate.command.upgrade


def upgrade_to(target: str) -> Any:
    """A replacement of `command.upgrade` that stops at `target` instead of the head."""

    def upgrade(config: Config, revision: str, **kwargs: Any) -> None:
        del revision
        REAL_UPGRADE(config, target, **kwargs)

    return upgrade
