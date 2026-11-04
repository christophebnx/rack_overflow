"""Refuse a restore while a server runs on the data folder (D-075): the supervisor lock is held for
the whole restore (no `rack supervise` runs or starts meanwhile), and nothing may answer on the
server's address (a plain `rack serve`, e.g. under systemd on Jelastic)."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from rack_overflow.ops import supervise
from rack_overflow.ops.errors import OpsError, SupervisorRunningError

PROBE_TIMEOUT_S = 1.0
WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::"})
LOCAL_PROBE_HOST = "127.0.0.1"

Connect = Callable[[tuple[str, int], float], socket.socket]


def _connect(address: tuple[str, int], timeout: float) -> socket.socket:
    return socket.create_connection(address, timeout=timeout)


def probe_host(host: str) -> str:
    """The address to probe for a server bound to `host` (a wildcard is reached on loopback)."""
    return LOCAL_PROBE_HOST if host.strip("[]") in WILDCARD_HOSTS else host


def _answers(host: str, port: int, connect: Connect) -> bool:
    try:
        connection = connect((host, port), PROBE_TIMEOUT_S)
    except OSError:
        return False
    connection.close()
    return True


@contextmanager
def server_stopped(data_dir: Path, host: str, port: int, *, connect: Connect | None = None) -> Iterator[None]:
    """Hold the supervisor lock of `data_dir` while the block runs, after checking that no server
    answers on `host:port` (`connect` defaults to a TCP connect with a 1 s timeout); either
    refusal raises `OpsError` and changes nothing."""
    try:
        lock = supervise.acquire_lock(data_dir)
    except SupervisorRunningError:
        raise OpsError("rack supervise is running on this data folder; stop it first") from None
    try:
        address = probe_host(host)
        if _answers(address, port, connect or _connect):
            raise OpsError(f"a server answers on {address}:{port}; stop it first")
        yield
    finally:
        os.close(lock)
