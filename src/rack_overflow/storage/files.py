"""The single atomic file writer (CLAUDE.md invariant 3)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` so that readers see either the old file or the new one, never a mix.

    Writes a `.tmp-<name>-<random>` file in the same folder, fsyncs it, renames it over `path`,
    then fsyncs the folder (POSIX only). On failure the temp file is removed and the original
    file is left as it was.
    """
    temp = path.with_name(f".tmp-{path.name}-{secrets.token_hex(4)}")
    with open(temp, "xb") as handle:  # "x": never reuse a leftover temp file
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_folder(path.parent)


def _fsync_folder(folder: Path) -> None:
    if os.name == "nt":  # Windows cannot open a folder for fsync
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
