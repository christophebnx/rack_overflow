"""Apply and inspect Alembic migrations, configured in code (no `alembic.ini`; D-046)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine

from rack_overflow.storage.errors import MigrationError

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def _config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision() -> str:
    """The newest revision shipped with the package."""
    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:
        raise MigrationError("no migration found")
    return head


def current_revision(engine: Engine) -> str | None:
    """The revision the database is at, or None for an empty database."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def is_up_to_date(engine: Engine) -> bool:
    """True when the database is at the head revision."""
    return current_revision(engine) == head_revision()


def upgrade_to_head(engine: Engine) -> str:
    """Apply the pending revisions in one transaction and return the new revision.

    Foreign keys are off during the upgrade (batch mode rebuilds tables) and must pass
    `PRAGMA foreign_key_check` before the commit; otherwise everything is rolled back.
    """
    with engine.connect() as connection:
        driver = connection.connection.driver_connection
        driver.execute("PRAGMA foreign_keys = OFF")  # no effect inside a transaction: run it first
        try:
            with connection.begin():
                command.upgrade(_config(connection), "head")
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise MigrationError(f"migration breaks {len(violations)} foreign key(s); rolled back")
        finally:
            driver.execute("PRAGMA foreign_keys = ON")
    return head_revision()
