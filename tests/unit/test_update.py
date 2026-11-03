"""`rack update` with a fake runner: no git, no uv, no signal is ever really sent."""

from __future__ import annotations

import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from rack_overflow import cli
from rack_overflow.ops.errors import OpsError
from rack_overflow.ops.update import UpdateTools, run_command, update

PYTHON = "/venv/bin/python"
UV = "/bin/uv"


class FakeRunner:
    """Answers each command from a table; records the calls."""

    def __init__(self, answers: dict[str, tuple[int, str]] | None = None, heads: Sequence[str] = ("a", "b")):
        self.calls: list[list[str]] = []
        self.answers = answers or {}
        self.heads = list(heads)

    def __call__(self, argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        del cwd
        self.calls.append(list(argv))
        key = " ".join(argv)
        if key == "git rev-parse HEAD":
            return subprocess.CompletedProcess(argv, 0, self.heads.pop(0) + "\n", "")
        default = {"git rev-parse --abbrev-ref HEAD": (0, "main\n")}.get(key, (0, ""))
        code, stdout = self.answers.get(key, default)
        return subprocess.CompletedProcess(argv, code, stdout, "boom\n" if code else "")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    return tmp_path


class Run:
    def __init__(self, runner: FakeRunner, supervisor: int | None = 77, uv: str | None = UV) -> None:
        self.runner = runner
        self.signals: list[tuple[int, int]] = []
        self.lines: list[str] = []
        self.tools = UpdateTools(
            run=runner,
            find_supervisor=lambda data_dir: supervisor,
            send_signal=lambda pid, signum: self.signals.append((pid, signum)),
            out=self.lines.append,
            python=PYTHON,
            uv=uv,
        )

    def __call__(self, repo: Path) -> None:
        update(repo, repo / "settings.toml", repo / "data", self.tools)


def test_full_sequence_and_restart(repo: Path) -> None:
    run = Run(FakeRunner())
    run(repo)
    config = str((repo / "settings.toml").resolve())
    assert run.runner.calls == [
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        ["git", "status", "--porcelain"],
        ["git", "rev-parse", "HEAD"],
        ["git", "pull", "--ff-only"],
        ["git", "rev-parse", "HEAD"],
        [UV, "sync", "--frozen"],
        [PYTHON, "-m", "rack_overflow", "migrate", "--config", config],
    ]
    assert run.signals == [(77, signal.SIGHUP)]
    assert run.lines[-1] == "restart requested (supervisor pid 77)"


def test_already_up_to_date_still_syncs_migrates_and_restarts(repo: Path) -> None:
    """D-052: rerunning `rack update` completes an update whose sync or migration had failed."""
    run = Run(FakeRunner(heads=("a", "a")))
    run(repo)
    config = str((repo / "settings.toml").resolve())
    assert run.runner.calls[-2:] == [
        [UV, "sync", "--frozen"],
        [PYTHON, "-m", "rack_overflow", "migrate", "--config", config],
    ]
    assert run.lines == [
        "already up to date; checking dependencies and database",
        "restart requested (supervisor pid 77)",
    ]
    assert run.signals == [(77, signal.SIGHUP)]


def test_rerun_after_a_failed_sync_completes_the_update(repo: Path) -> None:
    failing = Run(FakeRunner({f"{UV} sync --frozen": (1, "")}, heads=("a", "b")))
    with pytest.raises(OpsError):
        failing(repo)
    rerun = Run(FakeRunner(heads=("b", "b")))
    rerun(repo)
    assert [UV, "sync", "--frozen"] in rerun.runner.calls
    assert rerun.signals == [(77, signal.SIGHUP)]


def test_no_supervisor_is_a_message_not_an_error(repo: Path) -> None:
    run = Run(FakeRunner(), supervisor=None)
    run(repo)
    assert run.lines[-1] == "no rack supervise running; restart the server yourself"
    assert run.signals == []


@pytest.mark.parametrize(
    "answers",
    [
        {"git rev-parse --abbrev-ref HEAD": (0, "dev\n")},
        {"git status --porcelain": (0, " M src/x.py\n")},
    ],
)
def test_refused_off_main_or_with_local_changes(repo: Path, answers: dict[str, tuple[int, str]]) -> None:
    run = Run(FakeRunner(answers))
    with pytest.raises(OpsError, match="the deployed clone must be on main with no local changes"):
        run(repo)
    assert ["git", "pull", "--ff-only"] not in run.runner.calls
    assert run.signals == []


def test_refused_outside_a_clone(tmp_path: Path) -> None:
    run = Run(FakeRunner())
    with pytest.raises(OpsError, match="is not a clone"):
        run(tmp_path)
    assert run.runner.calls == []


def test_missing_uv_is_refused_before_pulling(repo: Path) -> None:
    run = Run(FakeRunner(), uv=None)
    with pytest.raises(OpsError, match="uv not found"):
        run(repo)
    assert ["git", "pull", "--ff-only"] not in run.runner.calls


@pytest.mark.parametrize("failing", ["git pull --ff-only", f"{UV} sync --frozen", "migrate"])
def test_a_failing_step_stops_without_restart(repo: Path, failing: str) -> None:
    config = str((repo / "settings.toml").resolve())
    key = f"{PYTHON} -m rack_overflow migrate --config {config}" if failing == "migrate" else failing
    run = Run(FakeRunner({key: (1, "partial output\n")}))
    with pytest.raises(OpsError, match=r"step failed: .* \(exit 1\)"):
        run(repo)
    assert run.runner.calls[-1] == key.split(" ")
    assert run.lines == ["partial output\nboom"]
    assert run.signals == []


def test_failing_git_query_is_an_error(repo: Path) -> None:
    run = Run(FakeRunner({"git status --porcelain": (128, "")}))
    with pytest.raises(OpsError, match="exit 128"):
        run(repo)


def test_real_runner_never_raises(tmp_path: Path) -> None:
    ok = run_command([sys.executable, "-c", "print('hi')"], tmp_path)
    assert (ok.returncode, ok.stdout) == (0, "hi\n")
    missing = run_command([str(tmp_path / "absent")], tmp_path)
    assert missing.returncode == 127


def test_cli_update_maps_errors_to_exit_1(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[Path, Path]] = []

    def fake_update(repo: Path, config: Path, data_dir: Path, tools: UpdateTools) -> None:
        seen.append((repo, data_dir))
        assert tools.python == sys.executable
        raise OpsError("the deployed clone must be on main with no local changes")

    monkeypatch.setattr(cli.update, "update", fake_update)
    assert cli.main(["update", "--config", str(settings_file)]) == 1
    assert (
        capsys.readouterr().err == "rack: error: the deployed clone must be on main with no local changes\n"
    )
    [(repo, data_dir)] = seen
    assert (repo / "src" / "rack_overflow" / "cli.py").is_file()
    assert data_dir == settings_file.parent / "data"


# --- edge cases -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answers",
    [
        {"git rev-parse --abbrev-ref HEAD": (0, "HEAD\n")},  # detached HEAD
        {"git rev-parse --abbrev-ref HEAD": (0, "main-old\n")},
        {"git status --porcelain": (0, "?? stray.txt\n")},  # untracked file
    ],
)
def test_refused_on_detached_head_similar_branch_or_untracked_file(
    repo: Path, answers: dict[str, tuple[int, str]]
) -> None:
    run = Run(FakeRunner(answers))
    with pytest.raises(OpsError, match="must be on main"):
        run(repo)
    assert run.runner.calls[-1] == ["git", "status", "--porcelain"]


def test_pyproject_missing_is_not_a_clone(repo: Path) -> None:
    (repo / "pyproject.toml").unlink()
    run = Run(FakeRunner())
    with pytest.raises(OpsError, match="is not a clone"):
        run(repo)
    assert run.runner.calls == []


def test_failing_head_query_before_the_pull_stops_everything(repo: Path) -> None:
    class Broken(FakeRunner):
        def __call__(self, argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if list(argv) == ["git", "rev-parse", "HEAD"]:
                self.calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 128, "", "fatal: bad\n")
            return super().__call__(argv, cwd)

    run = Run(Broken())
    with pytest.raises(OpsError, match=r"git rev-parse HEAD \(exit 128\): fatal: bad"):
        run(repo)
    assert ["git", "pull", "--ff-only"] not in run.runner.calls
    assert run.signals == []


def test_failing_head_query_after_the_pull_stops_before_sync(repo: Path) -> None:
    class Broken(FakeRunner):
        def __call__(self, argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if list(argv) == ["git", "rev-parse", "HEAD"] and ["git", "pull", "--ff-only"] in self.calls:
                self.calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 1, "", "")
            return super().__call__(argv, cwd)

    run = Run(Broken())
    with pytest.raises(OpsError, match="exit 1"):
        run(repo)
    assert [UV, "sync", "--frozen"] not in run.runner.calls
    assert run.signals == []


def test_successful_step_output_is_echoed_and_queries_are_not(repo: Path) -> None:
    run = Run(FakeRunner({"git pull --ff-only": (0, "Fast-forward\n"), f"{UV} sync --frozen": (0, "")}))
    run(repo)
    assert run.lines == ["Fast-forward", "restart requested (supervisor pid 77)"]


def test_cli_update_runs_the_sequence_and_reports_no_supervisor(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(cli.update, "run_command", runner)
    monkeypatch.setattr(cli.shutil, "which", lambda name: UV if name == "uv" else None)
    monkeypatch.setattr(cli.os, "kill", lambda *args: pytest.fail("signal sent"))
    assert cli.main(["update", "--config", str(settings_file)]) == 0
    assert capsys.readouterr().out == "no rack supervise running; restart the server yourself\n"
    assert runner.calls[-1] == [
        sys.executable,
        "-m",
        "rack_overflow",
        "migrate",
        "--config",
        str(settings_file.resolve()),
    ]


def test_cli_update_without_uv_exits_1_before_pulling(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(cli.update, "run_command", runner)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main(["update", "--config", str(settings_file)]) == 1
    assert capsys.readouterr().err == "rack: error: uv not found on PATH\n"
    assert ["git", "pull", "--ff-only"] not in runner.calls


def test_cli_update_signals_the_running_supervisor(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(cli.update, "run_command", FakeRunner())
    monkeypatch.setattr(cli.shutil, "which", lambda name: UV)
    monkeypatch.setattr(cli.supervise, "running_supervisor_pid", lambda data_dir: 4242)
    monkeypatch.setattr(cli.os, "kill", lambda pid, signum: sent.append((pid, signum)))
    assert cli.main(["update", "--config", str(settings_file)]) == 0
    assert sent == [(4242, signal.SIGHUP)]
    assert capsys.readouterr().out.endswith("restart requested (supervisor pid 4242)\n")


@pytest.mark.parametrize(
    "error", [PermissionError(1, "Operation not permitted"), ProcessLookupError(3, "No such process")]
)
def test_cli_update_signal_failure_is_a_clean_error(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    def refuse(pid: int, signum: int) -> None:
        raise error

    monkeypatch.setattr(cli.update, "run_command", FakeRunner())
    monkeypatch.setattr(cli.shutil, "which", lambda name: UV)
    monkeypatch.setattr(cli.supervise, "running_supervisor_pid", lambda data_dir: 4242)
    monkeypatch.setattr(cli.os, "kill", refuse)
    assert cli.main(["update", "--config", str(settings_file)]) == 1


def test_signal_failure_says_the_migration_was_applied(repo: Path) -> None:
    def refuse(pid: int, signum: int) -> None:
        raise ProcessLookupError(3, "No such process")

    run = Run(FakeRunner())
    run.tools = UpdateTools(**{**run.tools.__dict__, "send_signal": refuse})
    with pytest.raises(OpsError, match=r"migration were applied.*pid 77 failed: No such process"):
        run(repo)
