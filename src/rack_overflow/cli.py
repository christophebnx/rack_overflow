"""Command-line entry point and composition root (D-004, D-044).

Exit codes: 0 success, 1 error, 2 usage (no command, unknown command, bad option).
Errors print `rack: error: <message>` on stderr. Tests call `main([...])` in-process.
Every command except `--version` reads the settings file given by `--config`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from rack_overflow import __version__
from rack_overflow.config import ConfigError, Settings, load_settings
from rack_overflow.domain.errors import DomainError
from rack_overflow.storage import db, migrate
from rack_overflow.storage.errors import StorageError

PROG = "rack"
DEFAULT_CONFIG = Path("config.toml")


def run_migrate(settings: Settings) -> None:
    """Create the data folder if needed and bring the database to the head revision."""
    settings.storage.data_dir.mkdir(parents=True, exist_ok=True)
    engine = db.create_engine(settings.database_path)
    try:
        revision = migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
    print(f"database {settings.database_path} at revision {revision}")


COMMANDS: dict[str, tuple[str, Callable[[Settings], None]]] = {
    "migrate": ("create or upgrade the database to the latest schema", run_migrate),
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
