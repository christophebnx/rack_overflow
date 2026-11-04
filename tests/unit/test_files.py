import errno
import os
from pathlib import Path

import pytest

from rack_overflow.storage.files import atomic_produce, atomic_write


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


def test_atomic_produce_failure_keeps_the_original_and_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"original")

    def broken(temp: Path) -> None:
        temp.write_bytes(b"half")
        raise RuntimeError("producer failed")

    with pytest.raises(RuntimeError, match="producer failed"):
        atomic_produce(target, broken)
    assert target.read_bytes() == b"original"
    assert [path.name for path in tmp_path.iterdir()] == ["state.bin"]


def test_atomic_produce_creates_the_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_produce(target, lambda temp: temp.write_bytes(b"made"))
    assert target.read_bytes() == b"made"


def test_no_overwrite_creates_a_new_file_without_temp(tmp_path: Path) -> None:
    target = tmp_path / "export.json"
    atomic_write(target, b"data", overwrite=False)
    assert target.read_bytes() == b"data"
    assert [path.name for path in tmp_path.iterdir()] == ["export.json"]


def test_no_overwrite_keeps_a_file_created_while_producing(tmp_path: Path) -> None:
    target = tmp_path / "export.json"

    def racing(temp: Path) -> None:
        temp.write_bytes(b"ours")
        target.write_bytes(b"theirs")  # appears after any check made before the write

    with pytest.raises(FileExistsError):
        atomic_produce(target, racing, overwrite=False)
    assert target.read_bytes() == b"theirs"
    assert [path.name for path in tmp_path.iterdir()] == ["export.json"]


@pytest.mark.parametrize("taken", [False, True])
def test_no_overwrite_without_hard_links_checks_then_renames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, taken: bool
) -> None:
    target = tmp_path / "export.json"
    if taken:
        target.write_bytes(b"theirs")

    def no_links(src: object, dst: object) -> None:
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    if taken:
        with pytest.raises(FileExistsError):
            atomic_write(target, b"ours", overwrite=False)
    else:
        atomic_write(target, b"ours", overwrite=False)
    assert target.read_bytes() == (b"theirs" if taken else b"ours")
    assert [path.name for path in tmp_path.iterdir()] == ["export.json"]


def test_no_overwrite_propagates_other_link_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(src: object, dst: object) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "link", broken)
    with pytest.raises(OSError, match="Input/output error"):
        atomic_write(tmp_path / "export.json", b"ours", overwrite=False)
    assert list(tmp_path.iterdir()) == []
