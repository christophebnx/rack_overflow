"""The single atomic file writer (CLAUDE.md invariant 3)."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from pathlib import Path


def atomic_produce(path: Path, produce: Callable[[Path], None]) -> None:
    """Let `produce(temp)` create the new file, then switch `path` to it atomically.

    `temp` is an unused `.tmp-<name>-<random>` path in the same folder that `produce` must create.
    The temp file is fsynced, renamed over `path`, then the folder is fsynced (POSIX only). On any
    failure, of `produce` included, the temp file is removed and the original file is left as it was.
    """
    temp = _unused_temp(path)
    try:
        produce(temp)
        _fsync_file(temp)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_folder(path.parent)


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` so that readers see either the old file or the new one, never a mix."""

    def write(temp: Path) -> None:
        with open(temp, "xb") as handle:  # "x": never reuse a leftover temp file
            handle.write(data)

    atomic_produce(path, write)


def _unused_temp(path: Path) -> Path:
    while True:
        temp = path.with_name(f".tmp-{path.name}-{secrets.token_hex(4)}")
        if not temp.exists():
            return temp


def _fsync_file(path: Path) -> None:
    with open(path, "rb") as handle:
        os.fsync(handle.fileno())


def _fsync_folder(folder: Path) -> None:
    if os.name == "nt":  # Windows cannot open a folder for fsync
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
