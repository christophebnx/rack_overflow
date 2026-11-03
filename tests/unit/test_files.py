import os
from pathlib import Path

import pytest

from template_python.storage.files import atomic_write


def test_atomic_write_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write(target, b"one")
    atomic_write(target, b"two")
    assert target.read_bytes() == b"two"
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_failed_replace_keeps_the_original_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"original")

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(target, b"new")
    assert target.read_bytes() == b"original"
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_missing_folder_raises_and_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        atomic_write(tmp_path / "missing" / "state.json", b"data")
    assert not (tmp_path / "missing").exists()
