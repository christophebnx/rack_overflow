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


def test_already_up_to_date_stops_before_sync(repo: Path) -> None:
    run = Run(FakeRunner(heads=("a", "a")))
    run(repo)
    assert [call[0] for call in run.runner.calls] == ["git"] * 5
    assert run.lines == ["already up to date"]
    assert run.signals == []


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
