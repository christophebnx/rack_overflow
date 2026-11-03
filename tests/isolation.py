"""Test isolation guard (D-043, brief appendix A.3).

One process-wide audit hook (`sys.addaudithook`) is installed by `pytest_configure` (each xdist
worker installs its own). It does nothing until `guard` (an autouse fixture body) activates it
around a test. While active it refuses:

- writes under the real home (outside the allowed roots) or under `<repo>/.local/`;
- any open, read included, under `<repo>/.local/`, of `<repo>/.env` or `<repo>/config.toml`;
- name lookups, TCP connects and binds that are not loopback (`AF_UNIX` allowed).

A refusal raises `IsolationError` (an `AssertionError`, never swallowed as an `OSError`) and is
recorded, so the test fails at teardown even if the refusal was caught or raised in a thread.
Subprocesses are not hooked; they inherit the temporary home only.
"""

from __future__ import annotations

import functools
import ipaddress
import os
import socket
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SECRET_NAMES = (".env", "config.toml")
OPT_OUT_MARKERS = ("real_home", "external_network", "real_fsync")
HOME_VARIABLES = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
XDG_VARIABLES = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
WRITE_EVENTS = frozenset(
    {
        "os.remove",
        "os.rmdir",
        "os.mkdir",
        "os.chmod",
        "os.truncate",
        "os.rename",
        "os.link",
        "os.symlink",
        "shutil.rmtree",
        "shutil.move",
    }
)
LOOKUP_EVENTS = frozenset({"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"})


class IsolationError(AssertionError):
    """A test touched something the isolation guard forbids."""


@dataclass
class _State:
    """Process-wide guard state; one instance per process."""

    installed: bool = False
    active: bool = False
    real_home: Path = Path()
    repo: Path = REPO
    allowed_roots: tuple[str, ...] = ()
    protect_home: bool = True
    allow_network: bool = False
    strict_network: bool = False
    refusals: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_STATE = _State()
_INSIDE = threading.local()


def install(real_home: Path, repo: Path = REPO) -> None:
    """Record the real home and the repository, and add the audit hook once per process."""
    _STATE.real_home = Path(os.path.realpath(real_home))
    _STATE.repo = Path(os.path.realpath(repo))
    if not _STATE.installed:
        sys.addaudithook(_audit)
        _STATE.installed = True


def activate(base_temp: Path, *, protect_home: bool = True, allow_network: bool = False) -> None:
    """Start refusing; `base_temp` is pytest's base temporary folder (an allowed root)."""
    prefixes = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}
    roots = {str(_STATE.repo), tempfile.gettempdir(), str(base_temp), *prefixes}
    _STATE.allowed_roots = tuple(_normal(os.path.realpath(root)) for root in roots)
    _STATE.protect_home = protect_home
    _STATE.allow_network = allow_network
    _STATE.strict_network = False
    _STATE.refusals = []
    _STATE.active = True


def set_strict_network(strict: bool) -> None:
    """Refuse every name lookup, loopback included (the `strict_network` fixture)."""
    _STATE.strict_network = strict


def deactivate() -> list[str]:
    """Stop refusing and return the refusals recorded since `activate`."""
    _STATE.active = False
    with _STATE.lock:
        refusals, _STATE.refusals = _STATE.refusals, []
    return refusals


def _normal(path: str) -> str:
    return os.path.normcase(path)


@functools.lru_cache(maxsize=4096)
def _real_parent(parent: str) -> str:
    return os.path.realpath(parent)


def _resolve(raw: object) -> str | None:
    """Absolute, normalised path of `raw`; the parent is resolved, the last component is not."""
    if isinstance(raw, int) or raw is None:
        return None
    try:
        text = os.fsdecode(os.fspath(raw))  # type: ignore[arg-type]
    except TypeError:
        return None
    absolute = os.path.abspath(text)
    parent, name = os.path.split(absolute)
    return _normal(os.path.join(_real_parent(parent), name))


def _is_inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _is_secret(path: str) -> bool:
    repo = _normal(str(_STATE.repo))
    if _is_inside(path, _normal(os.path.join(repo, ".local"))):
        return True
    return any(path == _normal(os.path.join(repo, name)) for name in SECRET_NAMES)


def _write_forbidden(path: str) -> bool:
    if _is_inside(path, _normal(os.path.join(str(_STATE.repo), ".local"))):
        return True
    if not _STATE.protect_home or f"{os.sep}__pycache__" in path:
        return False
    if not _is_inside(path, _normal(str(_STATE.real_home))):
        return False
    return not any(_is_inside(path, root) for root in _STATE.allowed_roots)


def _refuse(message: str) -> None:
    with _STATE.lock:
        _STATE.refusals.append(message)
    raise IsolationError(f"isolation guard: {message}")


def _check_open(args: tuple[object, ...]) -> None:
    raw, mode, flags = args
    path = _resolve(raw)
    if path is None:
        return
    if _is_secret(path):
        _refuse(f"open of a protected file {path}")
    writing = any(char in mode for char in "wax+") if isinstance(mode, str) else bool(flags & WRITE_FLAGS)
    if writing and _write_forbidden(path):
        _refuse(f"write under a protected folder {path}")


def _check_write(event: str, args: tuple[object, ...]) -> None:
    targets = args[:2] if event in {"os.rename", "os.link", "os.symlink", "shutil.move"} else args[:1]
    for raw in targets:
        path = _resolve(raw)
        if path is not None and _write_forbidden(path):
            _refuse(f"{event} under a protected folder {path}")


def _check_sqlite(args: tuple[object, ...]) -> None:
    raw = args[0]
    if isinstance(raw, str) and (raw == ":memory:" or raw == ""):
        return
    if isinstance(raw, str) and raw.startswith("file:"):
        raw = raw.removeprefix("file:").split("?", 1)[0]
    path = _resolve(raw)
    if path is not None and (_is_secret(path) or _write_forbidden(path)):
        _refuse(f"sqlite3.connect under a protected folder {path}")


def is_loopback(host: object) -> bool:
    """True for a loopback name or address (`localhost`, `127.0.0.0/8`, `::1`)."""
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str) or not host:
        return False
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]").split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _check_lookup(event: str, args: tuple[object, ...]) -> None:
    host = args[0]
    if _STATE.strict_network:
        _refuse(f"{event} of {host!r} (strict network)")
    if host is not None and not is_loopback(host):
        _refuse(f"{event} of a non-loopback host {host!r}")


def _check_socket(event: str, args: tuple[object, ...]) -> None:
    sock, address = args[0], args[1]
    if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", object()):
        return
    if getattr(sock, "type", socket.SOCK_STREAM) != socket.SOCK_STREAM and event == "socket.connect":
        return  # UDP is not watched
    host = address[0] if isinstance(address, tuple) and address else address
    if not is_loopback(host):
        _refuse(f"{event} to a non-loopback address {address!r}")


def _dispatch(event: str, args: tuple[object, ...]) -> None:
    if event == "open":
        _check_open(args)
    elif event in WRITE_EVENTS:
        _check_write(event, args)
    elif event == "sqlite3.connect":
        _check_sqlite(args)
    elif _STATE.allow_network:
        return
    elif event in LOOKUP_EVENTS:
        _check_lookup(event, args)
    elif event in {"socket.connect", "socket.bind"}:
        _check_socket(event, args)


def _audit(event: str, args: tuple[object, ...]) -> None:
    """The audit hook: cheap when inactive, never re-entered from its own checks."""
    if not _STATE.active or getattr(_INSIDE, "busy", False):
        return
    _INSIDE.busy = True
    try:
        _dispatch(event, args)
    finally:
        _INSIDE.busy = False


def _marker_reason(request: pytest.FixtureRequest, name: str) -> bool:
    """True when the test carries the opt-out marker `name`; its `reason` is required."""
    marker = request.node.get_closest_marker(name)
    if marker is None:
        return False
    if not marker.kwargs.get("reason"):
        pytest.fail(f"@pytest.mark.{name} needs reason=...", pytrace=False)
    return True


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    for name in HOME_VARIABLES:
        monkeypatch.setenv(name, str(home))
    for name in XDG_VARIABLES:
        folder = home / name.lower()
        folder.mkdir()
        monkeypatch.setenv(name, str(folder))


def guard(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Body of the autouse fixture: redirect the home, skip fsync, activate, check at teardown."""
    real_home = _marker_reason(request, "real_home")
    external_network = _marker_reason(request, "external_network")
    if not _marker_reason(request, "real_fsync"):
        monkeypatch.setattr(os, "fsync", _no_fsync)
    if not real_home:
        _redirect_home(monkeypatch, tmp_path_factory.mktemp("home"))
    activate(tmp_path_factory.getbasetemp(), protect_home=not real_home, allow_network=external_network)
    try:
        yield
    finally:
        refusals = deactivate()
    if refusals:
        pytest.fail("isolation guard refused:\n" + "\n".join(refusals), pytrace=False)


def _no_fsync(descriptor: int) -> None:
    """Tests skip disk flushes (`@pytest.mark.real_fsync(reason=...)` keeps them)."""
    del descriptor


def snapshot(folder: Path) -> dict[str, tuple[str, bytes | None, int]]:
    """Map a folder tree to {relative path: (kind, bytes, mtime_ns)} to assert nothing changed."""
    tree: dict[str, tuple[str, bytes | None, int]] = {}
    if not folder.exists():
        return tree
    for path in sorted(folder.rglob("*")):
        status = path.lstat()
        key = path.relative_to(folder).as_posix()
        if path.is_symlink():
            tree[key] = ("link", os.fsencode(os.readlink(path)), status.st_mtime_ns)
        elif path.is_dir():
            tree[key] = ("dir", None, status.st_mtime_ns)
        else:
            tree[key] = ("file", path.read_bytes(), status.st_mtime_ns)
    return tree


Snapshot = Callable[[Path], dict[str, tuple[str, bytes | None, int]]]
