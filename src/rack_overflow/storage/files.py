"""The single atomic file writer (CLAUDE.md invariant 3)."""

from __future__ import annotations

import errno
import os
import secrets
from collections.abc import Callable
from pathlib import Path

_NO_HARD_LINKS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EMLINK}
"""`os.link` errors of a file system without hard links (FAT, some network shares)."""


def atomic_produce(path: Path, produce: Callable[[Path], None], *, overwrite: bool = True) -> None:
    """Let `produce(temp)` create the new file, then switch `path` to it atomically.

    `temp` is an unused `.tmp-<name>-<random>` path in the same folder that `produce` must create.
    The temp file is fsynced, renamed over `path`, then the folder is fsynced (POSIX only). On any
    failure, of `produce` included, the temp file is removed and the original file is left as it was.
    With `overwrite=False` an existing `path` is never replaced, even one created while `produce`
    ran: the temp file is hard-linked as `path` (`FileExistsError` when taken), then removed.
    """
    temp = _unused_temp(path)
    try:
        produce(temp)
        _fsync_file(temp)
        if overwrite:
            os.replace(temp, path)
        else:
            _publish_new(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_folder(path.parent)


def atomic_write(path: Path, data: bytes, *, overwrite: bool = True) -> None:
    """Write `data` to `path` so that readers see either the old file or the new one, never a mix.
    With `overwrite=False` an existing `path` raises `FileExistsError` and is left as it is."""

    def write(temp: Path) -> None:
        with open(temp, "xb") as handle:  # "x": never reuse a leftover temp file
            handle.write(data)

    atomic_produce(path, write, overwrite=overwrite)


def _publish_new(temp: Path, path: Path) -> None:
    """Give the complete `temp` the name `path` only if `path` is free: a hard link fails on an
    existing name atomically. Where hard links are not supported, check then rename (a narrow
    window, the best that file system allows)."""
    try:
        os.link(temp, path)
    except FileExistsError:
        raise
    except OSError as error:
        if error.errno not in _NO_HARD_LINKS:
            raise
        if path.exists() or path.is_symlink():
            raise FileExistsError(errno.EEXIST, "File exists", str(path)) from error
        os.replace(temp, path)
        return
    temp.unlink()


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
