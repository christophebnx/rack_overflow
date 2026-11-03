"""`rack supervise` (D-038, D-051): run `rack serve` as a child, copy its output to a rotating log,
restart it after a crash with a doubling delay, and keep one supervisor per data folder.

POSIX only (`fcntl`, signals). The clock and the wait between restarts are injected, so tests
run a fake server without real delays.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO

from rack_overflow.domain.supervision import RestartPolicy, next_delay
from rack_overflow.ops.errors import OpsError
from rack_overflow.ops.logs import utc_formatter
from rack_overflow.storage.files import atomic_write

LOGS_FOLDER_NAME = "logs"
LOG_FILE_NAME = "rack.log"
LOCK_FILE_NAME = "supervise.lock"
PID_FILE_NAME = "supervise.pid"
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 5
KILL_AFTER_S = 10.0
POLL_S = 0.1

Wait = Callable[[threading.Event, float], object]


def _stop_wait(stop: threading.Event, delay_s: float) -> object:
    return stop.wait(delay_s)


class _LineFormatter(logging.Formatter):
    """Child lines are written as they come (the server timestamps them); own lines get the UTC format."""

    def __init__(self) -> None:
        super().__init__()
        self._own = utc_formatter()

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "child", False):
            return record.getMessage()
        return self._own.format(record)


class Supervisor:
    """Run `command` until `stop` is set, restarting it after each exit."""

    def __init__(
        self,
        command: Sequence[str],
        log_path: Path,
        policy: RestartPolicy | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Wait = _stop_wait,
        max_bytes: int = LOG_MAX_BYTES,
        backup_count: int = LOG_BACKUP_COUNT,
        kill_after_s: float = KILL_AFTER_S,
    ) -> None:
        self.command = list(command)
        self.policy = policy or RestartPolicy()
        self.monotonic = monotonic
        self.wait = wait
        self.kill_after_s = kill_after_s
        self.handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        self.handler.setFormatter(_LineFormatter())
        self.logger = logging.Logger("rack_overflow.supervise")  # standalone: never reaches the root
        self.logger.addHandler(self.handler)

    def run(self, stop: threading.Event) -> int:
        """Start, watch and restart the child until `stop` is set; then stop the child and return 0."""
        self.logger.info("supervisor started (pid %d): %s", os.getpid(), " ".join(self.command))
        delay: float | None = None
        try:
            while not stop.is_set():
                started = self.monotonic()
                code = self._run_once(stop)
                if stop.is_set():
                    break
                delay = next_delay(self.policy, delay, self.monotonic() - started)
                self.logger.warning("server exited with code %d; restarting in %g s", code, delay)
                self.wait(stop, delay)
            self.logger.info("supervisor stopped")
        finally:
            self.handler.close()
        return 0

    def _run_once(self, stop: threading.Event) -> int:
        child = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )
        assert child.stdout is not None
        reader = threading.Thread(target=self._copy, args=(child.stdout,), daemon=True)
        reader.start()
        while True:
            try:
                code = child.wait(timeout=POLL_S)
                break
            except subprocess.TimeoutExpired:
                if stop.is_set():
                    code = self._terminate(child)
                    break
        reader.join()
        return code

    def _copy(self, stream: IO[bytes]) -> None:
        with stream:
            for raw in stream:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                self.logger.info("%s", line, extra={"child": True})

    def _terminate(self, child: subprocess.Popen[bytes]) -> int:
        child.terminate()
        try:
            return child.wait(timeout=self.kill_after_s)
        except subprocess.TimeoutExpired:
            self.logger.warning("server ignored SIGTERM for %g s; killing it", self.kill_after_s)
            child.kill()
            return child.wait()


def log_path(data_dir: Path) -> Path:
    """`<data_dir>/logs/rack.log`, its folder created."""
    folder = data_dir / LOGS_FOLDER_NAME
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OpsError(f"cannot create log folder {folder}: {error.strerror}") from error
    return folder / LOG_FILE_NAME


def acquire_lock(data_dir: Path) -> int:
    """Take the supervisor lock of `data_dir` (held until the descriptor is closed or the process dies)."""
    path = data_dir / LOCK_FILE_NAME
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as error:
        raise OpsError(f"cannot open lock file {path}: {error.strerror}") from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        raise OpsError("another rack supervise is running") from None
    return descriptor


def write_pid(data_dir: Path, pid: int) -> None:
    """Record the supervisor's PID (atomic write)."""
    atomic_write(data_dir / PID_FILE_NAME, f"{pid}\n".encode())


def remove_pid(data_dir: Path) -> None:
    """Remove the PID file on a clean exit."""
    with contextlib.suppress(FileNotFoundError):
        (data_dir / PID_FILE_NAME).unlink()


def running_supervisor_pid(data_dir: Path) -> int | None:
    """The PID of the supervisor running on `data_dir`, or None when the lock is free."""
    if not (data_dir / LOCK_FILE_NAME).exists():
        return None
    try:
        descriptor = acquire_lock(data_dir)
    except OpsError:
        try:
            return int((data_dir / PID_FILE_NAME).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
    os.close(descriptor)
    return None
