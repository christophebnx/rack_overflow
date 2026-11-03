"""Edge cases of `rack supervise` (D-038, D-051): delay cap, log lines, signal handling of the
command (handlers recorded, no real signal sent), PID file and lock lifecycle."""

from __future__ import annotations

import os
import re
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import pytest

from rack_overflow import cli
from rack_overflow.domain.supervision import RestartPolicy
from rack_overflow.ops import supervise
from rack_overflow.ops.supervise import Supervisor

OWN_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z (INFO|WARNING) rack_overflow\.supervise: .+$")


def _child(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _recording_wait(delays: list[float], count: int) -> Callable[[threading.Event, float], None]:
    def wait(stop: threading.Event, delay: float) -> None:
        delays.append(delay)
        if len(delays) >= count:
            stop.set()

    return wait


def _short_runs() -> Callable[[], float]:
    """Every run lasts 1 s on the fake monotonic clock."""
    ticks = iter(range(0, 10_000))
    return lambda: float(next(ticks))


def test_delay_doubles_up_to_the_cap(tmp_path: Path) -> None:
    delays: list[float] = []
    policy = RestartPolicy(initial_s=1, factor=2, max_s=5, stable_after_s=60)
    supervisor = Supervisor(
        _child("raise SystemExit(1)"),
        tmp_path / "rack.log",
        policy,
        monotonic=_short_runs(),
        wait=_recording_wait(delays, 6),
    )
    supervisor.run(threading.Event())
    assert delays == [1, 2, 4, 5, 5, 5]


def test_stop_set_while_waiting_starts_no_new_child(tmp_path: Path) -> None:
    record = tmp_path / "starts"
    code = f"open({str(record)!r}, 'a').write('x'); raise SystemExit(4)"
    delays: list[float] = []
    supervisor = Supervisor(
        _child(code), tmp_path / "rack.log", monotonic=_short_runs(), wait=_recording_wait(delays, 1)
    )
    assert supervisor.run(threading.Event()) == 0
    assert record.read_text(encoding="utf-8") == "x"
    assert delays == [1]


def test_stop_already_set_starts_nothing(tmp_path: Path) -> None:
    record = tmp_path / "starts"
    stop = threading.Event()
    stop.set()
    supervisor = Supervisor(_child(f"open({str(record)!r}, 'a').write('x')"), tmp_path / "rack.log")
    assert supervisor.run(stop) == 0
    assert not record.exists()
    assert "supervisor stopped" in (tmp_path / "rack.log").read_text(encoding="utf-8")


def test_log_lines_child_raw_own_utc_and_bad_bytes_replaced(tmp_path: Path) -> None:
    log = tmp_path / "rack.log"
    code = (
        "import sys; sys.stdout.buffer.write(b'caf\\xe9 line\\nsecond\\n'); "
        "sys.stdout.flush(); raise SystemExit(2)"
    )
    supervisor = Supervisor(_child(code), log, monotonic=_short_runs(), wait=_recording_wait([], 1))
    supervisor.run(threading.Event())
    lines = log.read_text(encoding="utf-8").splitlines()
    assert "caf� line" in lines
    assert "second" in lines
    own = [line for line in lines if line not in {"caf� line", "second"}]
    assert len(own) == 3
    assert all(OWN_LINE.match(line) for line in own), own
    assert own[1].endswith("WARNING rack_overflow.supervise: server exited with code 2; restarting in 1 s")


def test_child_killed_by_a_signal_is_restarted(tmp_path: Path) -> None:
    log = tmp_path / "rack.log"
    code = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"
    delays: list[float] = []
    supervisor = Supervisor(_child(code), log, monotonic=_short_runs(), wait=_recording_wait(delays, 2))
    supervisor.run(threading.Event())
    assert delays == [1, 2]
    assert f"server exited with code -{int(signal.SIGKILL)}; restarting in 1 s" in log.read_text(
        encoding="utf-8"
    )


def test_supervisor_lines_do_not_reach_the_root_logger(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        Supervisor(_child("pass"), tmp_path / "rack.log", wait=_recording_wait([], 1)).run(threading.Event())
    assert "rack_overflow.supervise" not in caplog.text


# --- running_supervisor_pid ---------------------------------------------------------------------------


def test_running_pid_is_none_when_the_pid_file_is_missing_or_garbage(tmp_path: Path) -> None:
    held = supervise.acquire_lock(tmp_path)
    try:
        assert supervise.running_supervisor_pid(tmp_path) is None
        (tmp_path / supervise.PID_FILE_NAME).write_text("not a pid\n", encoding="ascii")
        assert supervise.running_supervisor_pid(tmp_path) is None
    finally:
        os.close(held)


def test_stale_pid_file_without_a_lock_holder_is_ignored(tmp_path: Path) -> None:
    supervise.write_pid(tmp_path, 4242)
    assert supervise.running_supervisor_pid(tmp_path) is None  # no lock file at all
    os.close(supervise.acquire_lock(tmp_path))
    assert supervise.running_supervisor_pid(tmp_path) is None  # lock free: PID left by a reboot


# --- the command: signal handlers, PID file, lock ------------------------------------------------------


class FakeSupervisor:
    """Stands in for `Supervisor` in `run_supervise`; `action` runs inside `run(stop)`."""

    action: Callable[[threading.Event], None] = staticmethod(lambda stop: None)
    seen: ClassVar[list[tuple[list[str], Path]]] = []

    def __init__(self, command: list[str], log_path: Path) -> None:
        FakeSupervisor.seen.append((command, log_path))

    def run(self, stop: threading.Event) -> int:
        FakeSupervisor.action(stop)
        return 0


@pytest.fixture
def handlers(monkeypatch: pytest.MonkeyPatch) -> dict[int, Callable[[int, object], None]]:
    """Signal handlers installed by the command, recorded instead of installed."""
    installed: dict[int, Callable[[int, object], None]] = {}
    monkeypatch.setattr(cli.signal, "signal", lambda signum, handler: installed.__setitem__(signum, handler))
    FakeSupervisor.seen = []
    monkeypatch.setattr(cli.supervise, "Supervisor", FakeSupervisor)
    return installed


@pytest.fixture
def execs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.os, "execv", lambda path, argv: calls.append([path, *argv]))
    return calls


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_sigterm_and_sigint_stop_cleanly(
    settings_file: Path,
    handlers: dict[int, Callable[[int, object], None]],
    execs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    signum: int,
) -> None:
    data = settings_file.parent / "data"
    during: list[object] = []

    def action(stop: threading.Event) -> None:
        during.append((data / supervise.PID_FILE_NAME).read_text(encoding="ascii"))
        during.append(supervise.running_supervisor_pid(data))
        handlers[signum](signum, None)
        during.append(stop.is_set())

    monkeypatch.setattr(FakeSupervisor, "action", staticmethod(action))
    assert cli.main(["supervise", "--config", str(settings_file)]) == 0
    assert during == [f"{os.getpid()}\n", os.getpid(), True]
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
    [(command, log)] = FakeSupervisor.seen
    assert command == [
        sys.executable,
        "-m",
        "rack_overflow",
        "serve",
        "--config",
        str(settings_file.resolve()),
    ]
    assert log == data / "logs" / "rack.log"
    assert execs == []
    assert not (data / supervise.PID_FILE_NAME).exists()
    assert supervise.running_supervisor_pid(data) is None


def test_sighup_reexecutes_the_supervisor_after_releasing_the_lock(
    settings_file: Path,
    handlers: dict[int, Callable[[int, object], None]],
    execs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = settings_file.parent / "data"
    monkeypatch.setattr(FakeSupervisor, "action", staticmethod(lambda stop: handlers[signal.SIGHUP](1, None)))
    lock_free_at_exec: list[bool] = []
    monkeypatch.setattr(
        cli.os,
        "execv",
        lambda path, argv: (
            lock_free_at_exec.append(supervise.running_supervisor_pid(data) is None),
            execs.append([path, *argv]),
        ),
    )
    assert cli.main(["supervise", "--config", str(settings_file)]) == 0
    config = str(settings_file.resolve())
    assert execs == [[sys.executable, sys.executable, "-m", "rack_overflow", "supervise", "--config", config]]
    assert lock_free_at_exec == [True]
    assert not (data / supervise.PID_FILE_NAME).exists()


def test_crash_of_the_supervisor_still_removes_the_pid_and_frees_the_lock(
    settings_file: Path, handlers: dict[int, Callable[[int, object], None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del handlers
    data = settings_file.parent / "data"

    def explode(stop: threading.Event) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeSupervisor, "action", staticmethod(explode))
    with pytest.raises(RuntimeError):
        cli.main(["supervise", "--config", str(settings_file)])
    assert not (data / supervise.PID_FILE_NAME).exists()
    os.close(supervise.acquire_lock(data))


def test_second_instance_leaves_the_first_pid_file_alone(
    settings_file: Path,
    handlers: dict[int, Callable[[int, object], None]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    del handlers
    data = settings_file.parent / "data"
    data.mkdir()
    held = supervise.acquire_lock(data)
    try:
        supervise.write_pid(data, 4242)
        assert cli.main(["supervise", "--config", str(settings_file)]) == 1
        assert capsys.readouterr().err == "rack: error: another rack supervise is running\n"
        assert (data / supervise.PID_FILE_NAME).read_text(encoding="ascii") == "4242\n"
        assert FakeSupervisor.seen == []
    finally:
        os.close(held)
