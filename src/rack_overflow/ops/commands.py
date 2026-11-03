"""The `rack` self-invocation: a sub-command run by a given Python in a new process."""

from __future__ import annotations

from pathlib import Path


def self_command(python: str, command: str, config_path: Path) -> list[str]:
    """`<python> -m rack_overflow <command> --config <absolute config path>`.

    Used to start `rack serve` under the supervisor, re-execute `rack supervise` after an update and
    run the pulled code's `rack migrate`; `python` is the clone's `.venv` interpreter.
    """
    return [python, "-m", "rack_overflow", command, "--config", str(config_path.resolve())]
