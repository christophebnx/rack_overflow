"""`rack supervise` with a fake server (`tests/fixtures/fake_server.py`): restarts, delays, log
rotation, stop, single instance; then one run of the real command on a real `rack serve`."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from rack_overflow.ops import supervise
from rack_overflow.ops.errors import OpsError
from rack_overflow.ops.supervise import Supervisor

FAKE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_server.py"
DEADLINE_S = 30


def fake(record: Path, *options: str) -> list[str]:
    return [sys.executable, str(FAKE_SERVER), str(record), *options]


def starts(record: Path) -> int:
    return len(list(record.glob("start-*")))


class FakeClock:
    """`monotonic` returning, for run n, a start at 1000 n and an end `uptimes[n]` later."""

    def __init__(self, uptimes: list[float]) -> None:
        self.values: Iterator[float] = iter(
            value for index, up in enumerate(uptimes) for value in (1000.0 * index, 1000.0 * index + up)
        )

    def __call__(self) -> float:
        return next(self.values)


def stop_after(count: int, delays: list[float]) -> Callable[[threading.Event, float], None]:
    """A fake wait recording each delay and setting `stop` after `count` of them."""

    def wait(stop: threading.Event, delay: float) -> None:
        delays.append(delay)
        if len(delays) >= count:
            stop.set()

    return wait


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + DEADLINE_S
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.02)


def test_restarts_after_crashes_with_doubling_delays(tmp_path: Path) -> None:
    delays: list[float] = []
    log = tmp_path / "rack.log"
    supervisor = Supervisor(
        fake(tmp_path, "--exit", "3"), log, monotonic=FakeClock([1, 1, 1, 1]), wait=stop_after(4, delays)
    )
    assert supervisor.run(threading.Event()) == 0
    assert delays == [1, 2, 4, 8]
    assert starts(tmp_path) == 4
    text = log.read_text(encoding="utf-8")
    assert "server exited with code 3; restarting in 4 s" in text
    assert "fake line 2.0\n" in text  # child lines copied as they come
    assert " INFO rack_overflow.supervise: supervisor started (pid " in text


def test_delay_resets_after_a_long_run(tmp_path: Path) -> None:
    delays: list[float] = []
    supervisor = Supervisor(
        fake(tmp_path), tmp_path / "rack.log", monotonic=FakeClock([1, 1, 120, 1]), wait=stop_after(4, delays)
    )
    supervisor.run(threading.Event())
    assert delays == [1, 2, 1, 2]


def test_logs_rotate(tmp_path: Path) -> None:
    record = tmp_path / "record"
    record.mkdir()
    log = tmp_path / "rack.log"
    supervisor = Supervisor(
        fake(record, "--lines", "40", "--line-bytes", "50"),
        log,
        monotonic=FakeClock([1, 1, 1]),
        wait=stop_after(3, []),
        max_bytes=500,
        backup_count=2,
    )
    supervisor.run(threading.Event())
    assert sorted(path.name for path in tmp_path.glob("rack.log*")) == [
        "rack.log",
        "rack.log.1",
        "rack.log.2",
    ]
    assert all(path.stat().st_size <= 600 for path in tmp_path.glob("rack.log*"))


def _run_in_thread(supervisor: Supervisor, stop: threading.Event) -> threading.Thread:
    thread = threading.Thread(target=supervisor.run, args=(stop,))
    thread.start()
    return thread


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


@pytest.mark.parametrize("options", [(), ("--ignore-term",)])
def test_stop_terminates_the_child(tmp_path: Path, options: tuple[str, ...]) -> None:
    stop = threading.Event()
    supervisor = Supervisor(
        fake(tmp_path, "--run-s", "60", *options), tmp_path / "rack.log", kill_after_s=0.3
    )
    thread = _run_in_thread(supervisor, stop)
    wait_for(lambda: starts(tmp_path) == 1)
    pid = int((tmp_path / "start-1").read_text(encoding="ascii"))
    stop.set()
    thread.join(timeout=DEADLINE_S)
    assert not thread.is_alive()
    assert _gone(pid)
    assert starts(tmp_path) == 1
    log = (tmp_path / "rack.log").read_text(encoding="utf-8")
    assert ("killing it" in log) is bool(options)
    assert log.rstrip().endswith("supervisor stopped")


def test_single_instance_lock(tmp_path: Path) -> None:
    assert supervise.running_supervisor_pid(tmp_path) is None
    held = supervise.acquire_lock(tmp_path)
    try:
        supervise.write_pid(tmp_path, 4242)
        with pytest.raises(OpsError, match="another rack supervise is running"):
            supervise.acquire_lock(tmp_path)
        assert supervise.running_supervisor_pid(tmp_path) == 4242
    finally:
        os.close(held)
    assert supervise.running_supervisor_pid(tmp_path) is None
    os.close(supervise.acquire_lock(tmp_path))
    supervise.remove_pid(tmp_path)
    supervise.remove_pid(tmp_path)  # already gone: no error
    assert not (tmp_path / "supervise.pid").exists()


def test_lock_is_free_after_the_holder_process_dies(tmp_path: Path) -> None:
    script = (
        "import sys, time; from pathlib import Path; from rack_overflow.ops import supervise; "
        "supervise.acquire_lock(Path(sys.argv[1])); print('held', flush=True); time.sleep(60)"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline() == "held\n"
        with pytest.raises(OpsError):
            supervise.acquire_lock(tmp_path)
    finally:
        holder.kill()
        holder.communicate(timeout=DEADLINE_S)
    os.close(supervise.acquire_lock(tmp_path))


def test_log_folder_that_cannot_be_created(tmp_path: Path) -> None:
    (tmp_path / "logs").write_bytes(b"a file")
    with pytest.raises(OpsError, match="cannot create log folder"):
        supervise.log_path(tmp_path)


# --- the real command --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _count(log: Path, text: str) -> int:
    return log.read_text(encoding="utf-8").count(text) if log.exists() else 0


def _listening(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def test_rack_supervise_runs_serve_reexecs_on_sighup_and_stops_on_sigterm(settings_file: Path) -> None:
    port = _free_port()
    text = settings_file.read_text(encoding="utf-8").replace("port = 8765", f"port = {port}")
    settings_file.write_text(text, encoding="utf-8")
    rack = [sys.executable, "-m", "rack_overflow"]
    assert subprocess.run([*rack, "migrate", "--config", str(settings_file)], check=False).returncode == 0
    data = settings_file.parent / "data"
    log = data / "logs" / "rack.log"
    process = subprocess.Popen([*rack, "supervise", "--config", str(settings_file)])
    try:
        wait_for(lambda: _count(log, "Application startup complete") == 1)
        assert (data / "supervise.pid").read_text(encoding="ascii") == f"{process.pid}\n"
        second = subprocess.run(
            [*rack, "supervise", "--config", str(settings_file)], capture_output=True, text=True, check=False
        )
        assert second.returncode == 1
        assert second.stderr == "rack: error: another rack supervise is running\n"
        process.send_signal(signal.SIGHUP)
        wait_for(lambda: _count(log, "supervisor started") == 2)
        wait_for(lambda: _count(log, "Application startup complete") == 2)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=DEADLINE_S) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert not _listening(port)  # no orphan server
    assert not (data / "supervise.pid").exists()
    assert supervise.running_supervisor_pid(data) is None


def test_supervise_with_invalid_settings_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from rack_overflow.cli import main

    path = tmp_path / "settings.toml"
    path.write_text("[server\n", encoding="utf-8")
    assert main(["supervise", "--config", str(path)]) == 1
    assert capsys.readouterr().err.startswith("rack: error: ")
