"""Apply and inspect Alembic migrations, configured in code (no `alembic.ini`; D-046)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from rack_overflow.storage.errors import MigrationError

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
HEAD = "head"
OLDER = "older"
UNKNOWN = "unknown"
RevisionOrder = Literal["head", "older", "unknown"]


def _config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@contextmanager
def _as_migration_error() -> Iterator[None]:
    """Turn a database failure (e.g. not a database) or an unknown revision into `MigrationError`."""
    try:
        yield
    except DBAPIError as error:
        raise MigrationError(f"database cannot be read or migrated: {error.orig}") from error
    except CommandError as error:
        raise MigrationError(f"migration failed: {error}") from error


def head_revision() -> str:
    """The newest revision shipped with the package."""
    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:
        raise MigrationError("no migration found")
    return head


def known_revisions() -> list[str]:
    """Every revision shipped with the package, oldest first."""
    script = ScriptDirectory.from_config(_config())
    return [revision.revision for revision in reversed(list(script.walk_revisions()))]


def revision_order(revision: str) -> RevisionOrder:
    """`head`, `older` (a shipped revision before the head) or `unknown` (newer than this code,
    or foreign)."""
    known = known_revisions()
    if revision not in known:
        return UNKNOWN
    return HEAD if revision == known[-1] else OLDER


def revision_of_file(path: Path) -> str | None:
    """The revision recorded in the database file at `path`, None when it has no
    `alembic_version` table. Read through a bare read-only connection: the file is never written
    nor switched to WAL. An unreadable file raises `MigrationError`."""
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise MigrationError(f"database cannot be read: {error}") from error
    try:
        found = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
        ).fetchone()
        if found is None:
            return None
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error as error:
        raise MigrationError(f"database cannot be read: {error}") from error
    finally:
        connection.close()
    return None if row is None else str(row[0])


def current_revision(engine: Engine) -> str | None:
    """The revision the database is at, or None for an empty database."""
    with _as_migration_error(), engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def is_up_to_date(engine: Engine) -> bool:
    """True when the database is at the head revision."""
    return current_revision(engine) == head_revision()


def upgrade_to_head(engine: Engine) -> str:
    """Apply the pending revisions in one transaction and return the new revision.

    Foreign keys are off during the upgrade (batch mode rebuilds tables) and must pass
    `PRAGMA foreign_key_check` before the commit; otherwise everything is rolled back.
    A database that cannot be read or is at an unknown revision raises `MigrationError`.
    """
    with _as_migration_error(), engine.connect() as connection:
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
