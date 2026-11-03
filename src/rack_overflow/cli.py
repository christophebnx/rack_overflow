"""Command-line entry point and composition root (D-004, D-044).

Exit codes: 0 success, 1 error, 2 usage (no command, unknown command, bad option).
Errors print `rack: error: <message>` on stderr. Tests call `main([...])` in-process.
Every command except `--version` reads the settings file given by `--config`. A handler receives
the settings and the parsed arguments; `device` has sub-commands (`add`, `list`, `revoke`).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from sqlalchemy.engine import Engine

import rack_overflow
from rack_overflow import __version__
from rack_overflow.config import ConfigError, Settings, load_settings
from rack_overflow.domain import devices as device_rules
from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.timestamps import to_text
from rack_overflow.ops import supervise, update
from rack_overflow.ops.errors import OpsError
from rack_overflow.ops.logs import utc_formatter
from rack_overflow.services import backups, devices
from rack_overflow.storage import db, migrate
from rack_overflow.storage.errors import MigrationError, StorageError
from rack_overflow.web.app import create_app
from rack_overflow.web.auth import PAIRING_PATH

PROG = "rack"
DEFAULT_CONFIG = Path("config.toml")
NEVER = "-"

Handler = Callable[[Settings, argparse.Namespace], None]
DeviceHandler = Callable[[Engine, Settings, argparse.Namespace], None]


def _now() -> datetime:
    return datetime.now(UTC)


def _backup_now(settings: Settings) -> Path:
    return backups.backup_now(
        settings.database_path, settings.backups_dir, _now(), settings.backup.retention_days
    )


def run_migrate(settings: Settings, args: argparse.Namespace) -> None:
    """Create the data folder if needed, snapshot an existing database with pending revisions, upgrade."""
    del args
    data_dir = settings.storage.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MigrationError(f"cannot create data folder {data_dir}: {error.strerror}") from error
    existed = settings.database_path.is_file()
    engine = db.create_engine(settings.database_path)
    try:
        if existed and not migrate.is_up_to_date(engine):
            print(f"backup {_backup_now(settings)}")
        revision = migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
    print(f"database {settings.database_path} at revision {revision}")


def run_backup(settings: Settings, args: argparse.Namespace) -> None:
    """Snapshot the database now and prune expired snapshots."""
    del args
    print(_backup_now(settings))


def configure_logging() -> None:
    """Server logs on stderr, UTC timestamps, INFO; uvicorn's loggers propagate here."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(utc_formatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def _open_current_database(settings: Settings) -> Engine:
    """An engine on the database, refused unless the file exists and is at the head revision."""
    engine = db.create_engine(settings.database_path)
    try:
        current = settings.database_path.is_file() and migrate.is_up_to_date(engine)
    except MigrationError:
        engine.dispose()
        raise
    if not current:
        engine.dispose()
        raise MigrationError("database is not up to date; run rack migrate")
    return engine


def run_serve(settings: Settings, args: argparse.Namespace) -> None:
    """Serve the web app on the configured host and port (one worker), once the database is current."""
    del args
    engine = _open_current_database(settings)
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


def _self_command(command: str, config_path: Path) -> list[str]:
    """`rack <command> --config <absolute path>` run by this Python (the clone's `.venv`)."""
    return [sys.executable, "-m", "rack_overflow", command, "--config", str(config_path.resolve())]


def run_supervise(settings: Settings, args: argparse.Namespace) -> None:
    """Run `rack serve` under a supervisor: restarts, rotating logs, one instance per data folder.

    SIGTERM / SIGINT stop the server and exit; SIGHUP (sent by `rack update`) stops the server and
    re-executes the supervisor, so both run the updated code.
    """
    data_dir = settings.storage.data_dir
    log_file = supervise.log_path(data_dir)
    lock = supervise.acquire_lock(data_dir)
    stop = threading.Event()
    reexec = threading.Event()

    def on_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop.set()

    def on_hangup(signum: int, frame: object) -> None:
        reexec.set()
        on_stop(signum, frame)

    try:
        supervise.write_pid(data_dir, os.getpid())
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, on_stop)
        signal.signal(signal.SIGHUP, on_hangup)
        supervise.Supervisor(_self_command("serve", args.config), log_file).run(stop)
    finally:
        supervise.remove_pid(data_dir)
        os.close(lock)
    if reexec.is_set():
        command = _self_command("supervise", args.config)
        os.execv(command[0], command)


def run_update(settings: Settings, args: argparse.Namespace) -> None:
    """Update this deployed clone (pull, sync, migrate) and restart the supervised server."""
    tools = update.UpdateTools(
        run=update.run_command,
        find_supervisor=supervise.running_supervisor_pid,
        send_signal=os.kill,
        out=print,
        python=sys.executable,
        uv=shutil.which("uv"),
    )
    repo = Path(rack_overflow.__file__).resolve().parents[2]
    update.update(repo, args.config, settings.storage.data_dir, tools)


def _pairing_url(settings: Settings) -> str:
    scheme = "https" if settings.server.https else "http"
    return f"{scheme}://{settings.server.public_host}:{settings.server.port}{PAIRING_PATH}"


def _device_add(engine: Engine, settings: Settings, args: argparse.Namespace) -> None:
    new = devices.add_device(engine, args.name, _now())
    minutes = int(device_rules.CODE_TTL.total_seconds() // 60)
    print(
        f'device "{new.name}" added; pairing code {device_rules.format_code(new.code)}, '
        f"valid until {to_text(new.expires_at)} ({minutes} minutes)"
    )
    print(f"open {_pairing_url(settings)} on the device and type the code")


def _device_list(engine: Engine, settings: Settings, args: argparse.Namespace) -> None:
    del settings, args
    rows = [("NAME", "STATE", "CREATED", "LAST SEEN")]
    for info in devices.list_devices(engine):
        last_seen = to_text(info.last_seen_at) if info.last_seen_at else NEVER
        rows.append((info.name, info.state.value, to_text(info.created_at), last_seen))
    if len(rows) == 1:
        print("no devices")
        return
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]) - 1)]
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row[:-1], widths, strict=True)]
        print("  ".join([*cells, row[-1]]))


def _device_revoke(engine: Engine, settings: Settings, args: argparse.Namespace) -> None:
    del settings
    devices.revoke_device(engine, args.name, _now())
    print(f'device "{args.name.strip()}" revoked')


DEVICE_ACTIONS: dict[str, tuple[str, DeviceHandler]] = {
    "add": ("add a device and print its one-time pairing code", _device_add),
    "list": ("list devices with their state and last use", _device_list),
    "revoke": ("revoke a device: its browser must pair again", _device_revoke),
}


def run_device(settings: Settings, args: argparse.Namespace) -> None:
    """Run a `rack device` action on the current database (safe while the server runs: WAL)."""
    engine = _open_current_database(settings)
    try:
        DEVICE_ACTIONS[args.action][1](engine, settings, args)
    finally:
        engine.dispose()


def _config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"settings file (default: {DEFAULT_CONFIG} in the current folder)",
    )


def _device_arguments(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", metavar="<action>", required=True)
    for name, (help_text, _) in DEVICE_ACTIONS.items():
        action = actions.add_parser(name, help=help_text)
        if name != "list":
            action.add_argument("name", help="device name (e.g. iPhone)")
        _config_argument(action)


@dataclass(frozen=True)
class Command:
    """A `rack` sub-command: help text, handler, and its extra arguments if any."""

    help: str
    run: Handler
    arguments: Callable[[argparse.ArgumentParser], None] | None = None


COMMANDS: dict[str, Command] = {
    "migrate": Command("create or upgrade the database to the latest schema", run_migrate),
    "backup": Command("snapshot the database now and prune expired snapshots", run_backup),
    "serve": Command("serve the web app (host and port from the settings file)", run_serve),
    "supervise": Command("run the server, restart it after a crash, write logs", run_supervise),
    "update": Command("pull main, sync, migrate, then restart rack supervise", run_update),
    "device": Command(
        "add, list or revoke the devices allowed to use the app", run_device, _device_arguments
    ),
}


def build_parser() -> argparse.ArgumentParser:
    """The `rack` argument parser with one sub-command per operation."""
    parser = argparse.ArgumentParser(prog=PROG, description="Rack Overflow: personal training tracker.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    for name, command in COMMANDS.items():
        sub = commands.add_parser(name, help=command.help)
        if command.arguments is None:
            _config_argument(sub)
        else:  # nested actions carry `--config` (a parent default would override the child's value)
            command.arguments(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run `rack` with `argv` and return the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    try:
        COMMANDS[args.command].run(load_settings(args.config), args)
    except (DomainError, ConfigError, StorageError, OpsError) as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 1
    return 0
