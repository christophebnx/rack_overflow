"""Open the database with the project pragmas (D-016, D-046): the one place an engine is created."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import Engine

SYNCHRONOUS = "FULL"
"""`PRAGMA synchronous` of every new connection; the test suite sets it to OFF (no disk flush)."""
BUSY_TIMEOUT_MS = 5000
READ_ONLY = "rack_read_only"
"""Execution option of a connection whose transactions only read (`read_transaction`)."""


def create_engine(database_path: Path) -> Engine:
    """Engine on the SQLite file `database_path`: WAL, foreign keys, `BEGIN IMMEDIATE` transactions."""
    engine = sa.create_engine(f"sqlite:///{database_path.resolve()}")
    event.listen(engine, "connect", _on_connect)
    event.listen(engine, "begin", _on_begin)
    return engine


def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
    """Set the pragmas and hand transaction control to SQLAlchemy (pysqlite recipe)."""
    del connection_record
    dbapi_connection.isolation_level = None  # no implicit BEGIN from the driver
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA synchronous = {_synchronous()}")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _synchronous() -> str:
    if SYNCHRONOUS not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        raise ValueError(f"invalid synchronous mode {SYNCHRONOUS!r}")
    return SYNCHRONOUS


def _on_begin(connection: sa.Connection) -> None:
    """Take the write lock up front: no read-to-write upgrade failing with SQLITE_BUSY under WAL.
    A `read_transaction` begins deferred instead: a WAL reader never waits for a writer."""
    if connection.get_execution_options().get(READ_ONLY):
        connection.exec_driver_sql("BEGIN DEFERRED")
    else:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


@contextmanager
def read_transaction(engine: Engine) -> Iterator[sa.Connection]:
    """A transaction that only reads: one consistent WAL snapshot from its first read to its end,
    without taking the write lock, so writers are neither blocked nor waited for. Never write
    through it."""
    with engine.connect() as connection:
        connection.execution_options(**{READ_ONLY: True})
        with connection.begin():
            yield connection


def guarded_write[T](connection: sa.Connection, write: Callable[[], T], refusal: Exception) -> T:
    """Run `write` in a savepoint; a unique-constraint violation rolls the savepoint back and
    raises `refusal`, leaving the caller's transaction usable. Other integrity errors propagate."""
    savepoint = connection.begin_nested()
    try:
        result = write()
    except sa.exc.IntegrityError as error:
        savepoint.rollback()
        if "UNIQUE" not in str(error.orig).upper():
            raise
        raise refusal from None
    savepoint.commit()
    return result
