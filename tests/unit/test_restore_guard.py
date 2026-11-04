"""`ops.restore.server_stopped`: the supervisor lock is held during a restore and a server
answering on its address is refused (D-075). Probes are injected, except one loopback listener."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from rack_overflow.ops import restore, supervise
from rack_overflow.ops.errors import OpsError


class Probe:
    """An injected connect: records the addresses, answers or refuses."""

    def __init__(self, *, answers: bool) -> None:
        self.answers = answers
        self.addresses: list[tuple[str, int]] = []

    def __call__(self, address: tuple[str, int], timeout: float) -> socket.socket:
        assert timeout == restore.PROBE_TIMEOUT_S
        self.addresses.append(address)
        if not self.answers:
            raise ConnectionRefusedError
        left, right = socket.socketpair()
        right.close()
        return left


def _lock_is_free(data_dir: Path) -> bool:
    try:
        descriptor = supervise.acquire_lock(data_dir)
    except OpsError:
        return False
    os.close(descriptor)
    return True


def test_free_server_yields_and_holds_the_lock_until_the_end(tmp_path: Path) -> None:
    probe = Probe(answers=False)
    with restore.server_stopped(tmp_path, "127.0.0.1", 8765, connect=probe):
        assert not _lock_is_free(tmp_path)
    assert _lock_is_free(tmp_path)
    assert probe.addresses == [("127.0.0.1", 8765)]


def test_running_supervisor_is_refused(tmp_path: Path) -> None:
    held = supervise.acquire_lock(tmp_path)
    probe = Probe(answers=False)
    try:
        with (
            pytest.raises(OpsError, match=r"^rack supervise is running on this data folder; stop it first$"),
            restore.server_stopped(tmp_path, "127.0.0.1", 8765, connect=probe),
        ):
            pytest.fail("the block must not run")
    finally:
        os.close(held)
    assert probe.addresses == []


def test_answering_server_is_refused_and_the_lock_released(tmp_path: Path) -> None:
    with (
        pytest.raises(OpsError, match=r"^a server answers on 127\.0\.0\.1:8765; stop it first$"),
        restore.server_stopped(tmp_path, "0.0.0.0", 8765, connect=Probe(answers=True)),
    ):
        pytest.fail("the block must not run")
    assert _lock_is_free(tmp_path)


def test_lock_released_when_the_block_fails(tmp_path: Path) -> None:
    with (
        pytest.raises(RuntimeError),
        restore.server_stopped(tmp_path, "127.0.0.1", 8765, connect=Probe(answers=False)),
    ):
        raise RuntimeError("restore failed")
    assert _lock_is_free(tmp_path)


@pytest.mark.parametrize(
    ("host", "probed"),
    [("0.0.0.0", "127.0.0.1"), ("::", "127.0.0.1"), ("[::]", "127.0.0.1"), ("", "127.0.0.1")],
)
def test_wildcard_hosts_are_probed_on_loopback(host: str, probed: str) -> None:
    assert restore.probe_host(host) == probed


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "192.168.1.20", "rack.example"])
def test_other_hosts_are_probed_as_configured(host: str) -> None:
    assert restore.probe_host(host) == host


def test_a_real_loopback_listener_is_detected(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with (
            pytest.raises(OpsError, match="a server answers"),
            restore.server_stopped(tmp_path, "127.0.0.1", port),
        ):
            pytest.fail("the block must not run")
    with restore.server_stopped(tmp_path, "127.0.0.1", port):  # closed: nothing answers any more
        pass
