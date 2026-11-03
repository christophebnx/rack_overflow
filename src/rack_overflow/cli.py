"""Command-line entry point and composition root (D-004, D-044).

Exit codes: 0 success, 1 error, 2 usage (no command, unknown command, bad option).
Errors print `rack: error: <message>` on stderr. Tests call `main([...])` in-process.
Every command except `--version` reads the settings file given by `--config`.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from rack_overflow import __version__
from rack_overflow.config import ConfigError, Settings, load_settings
from rack_overflow.domain.errors import DomainError
from rack_overflow.services import backups
from rack_overflow.storage import db, migrate
from rack_overflow.storage.errors import MigrationError, StorageError
from rack_overflow.web.app import create_app

PROG = "rack"
DEFAULT_CONFIG = Path("config.toml")


def _now() -> datetime:
    return datetime.now(UTC)


def _backup_now(settings: Settings) -> Path:
    return backups.backup_now(
        settings.database_path, settings.backups_dir, _now(), settings.backup.retention_days
    )


def run_migrate(settings: Settings) -> None:
    """Create the data folder if needed, snapshot an existing database with pending revisions, upgrade."""
    settings.storage.data_dir.mkdir(parents=True, exist_ok=True)
    existed = settings.database_path.is_file()
    engine = db.create_engine(settings.database_path)
    try:
        if existed and not migrate.is_up_to_date(engine):
            print(f"backup {_backup_now(settings)}")
        revision = migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
    print(f"database {settings.database_path} at revision {revision}")


def run_backup(settings: Settings) -> None:
    """Snapshot the database now and prune expired snapshots."""
    print(_backup_now(settings))


def configure_logging() -> None:
    """Server logs on stderr, UTC timestamps, INFO; uvicorn's loggers propagate here."""
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def run_serve(settings: Settings) -> None:
    """Serve the web app on the configured host and port (one worker), once the database is current."""
    engine = db.create_engine(settings.database_path)
    if not settings.database_path.is_file() or not migrate.is_up_to_date(engine):
        engine.dispose()
        raise MigrationError("database is not up to date; run rack migrate")
    configure_logging()
    app = create_app(settings, engine, clock=_now)
    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
        server_header=False,
        proxy_headers=False,
        log_config=None,
    )


COMMANDS: dict[str, tuple[str, Callable[[Settings], None]]] = {
    "migrate": ("create or upgrade the database to the latest schema", run_migrate),
    "backup": ("snapshot the database now and prune expired snapshots", run_backup),
    "serve": ("serve the web app (host and port from the settings file)", run_serve),
}


def build_parser() -> argparse.ArgumentParser:
    """The `rack` argument parser with one sub-command per operation."""
    parser = argparse.ArgumentParser(prog=PROG, description="Rack Overflow: personal training tracker.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    for name, (help_text, _) in COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        command.add_argument(
            "--config",
            type=Path,
            default=DEFAULT_CONFIG,
            help=f"settings file (default: {DEFAULT_CONFIG} in the current folder)",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run `rack` with `argv` and return the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    _, run = COMMANDS[args.command]
    try:
        run(load_settings(args.config))
    except (DomainError, ConfigError, StorageError) as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 1
    return 0
