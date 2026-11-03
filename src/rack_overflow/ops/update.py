"""`rack update` (D-051): update a deployed clone of `main` and restart the supervised server.

Sequence: preconditions (clone on `main`, no local changes, `uv` found), `git pull --ff-only`
(HEAD unchanged: stop), `uv sync --frozen`, `rack migrate` in a new process (the pulled code's
migrations, with its own pre-migration backup), then SIGHUP to the running supervisor. A failing
step stops the sequence with its output and requests no restart. Commands run through an injected
`run`, so tests never run git or uv.
"""

from __future__ import annotations

import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rack_overflow.ops.errors import OpsError

DEPLOYED_BRANCH = "main"
NOT_CLEAN = f"the deployed clone must be on {DEPLOYED_BRANCH} with no local changes"

Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class UpdateTools:
    """What `update` runs and signals (injected: tests pass fakes)."""

    run: Runner
    find_supervisor: Callable[[Path], int | None]
    send_signal: Callable[[int, int], None]
    out: Callable[[str], None]
    python: str
    uv: str | None


def run_command(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """The real runner: no shell, output captured, exit code returned (never raises on failure)."""
    try:
        return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as error:
        return subprocess.CompletedProcess(list(argv), 127, "", f"{error.strerror}\n")


def _step(tools: UpdateTools, argv: Sequence[str], repo: Path) -> str:
    """Run one step; echo its output; a non-zero exit stops the update."""
    result = tools.run(argv, repo)
    output = (result.stdout or "") + (result.stderr or "")
    if output.strip():
        tools.out(output.rstrip("\n"))
    if result.returncode != 0:
        raise OpsError(f"step failed: {' '.join(argv)} (exit {result.returncode})")
    return result.stdout.strip()


def _check_clone(tools: UpdateTools, repo: Path) -> None:
    if not (repo / ".git").exists() or not (repo / "pyproject.toml").is_file():
        raise OpsError(f"{repo} is not a clone of rack_overflow; {NOT_CLEAN}")
    branch = _quiet(tools, ["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    changes = _quiet(tools, ["git", "status", "--porcelain"], repo)
    if branch != DEPLOYED_BRANCH or changes:
        raise OpsError(NOT_CLEAN)
    if tools.uv is None:
        raise OpsError("uv not found on PATH")


def _quiet(tools: UpdateTools, argv: Sequence[str], repo: Path) -> str:
    """A read-only git query: output returned, not echoed."""
    result = tools.run(argv, repo)
    if result.returncode != 0:
        raise OpsError(f"step failed: {' '.join(argv)} (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def update(repo: Path, config_path: Path, data_dir: Path, tools: UpdateTools) -> None:
    """Pull, sync, migrate and restart; see the module docstring."""
    _check_clone(tools, repo)
    before = _quiet(tools, ["git", "rev-parse", "HEAD"], repo)
    _step(tools, ["git", "pull", "--ff-only"], repo)
    if _quiet(tools, ["git", "rev-parse", "HEAD"], repo) == before:
        tools.out("already up to date")
        return
    _step(tools, [str(tools.uv), "sync", "--frozen"], repo)
    migrate = [tools.python, "-m", "rack_overflow", "migrate", "--config", str(config_path.resolve())]
    _step(tools, migrate, repo)
    pid = tools.find_supervisor(data_dir)
    if pid is None:
        tools.out("no rack supervise running; restart the server yourself")
        return
    tools.send_signal(pid, signal.SIGHUP)
    tools.out(f"restart requested (supervisor pid {pid})")
