"""Machine settings and secrets, loaded once by the CLI and passed down explicitly (D-044).

The settings file is TOML (`--config`, default `config.toml` in the current folder); secrets come
from the `.env` file in the same folder, read without touching `os.environ`. No other module
reads the environment or these files.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

SECRETS_FILE_NAME = ".env"
DATABASE_FILE_NAME = "rack.sqlite"
BACKUPS_FOLDER_NAME = "backups"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_TIME_ZONE = "Europe/Brussels"
PORT_RANGE = (1, 65535)

_SECTIONS: dict[str, dict[str, tuple[type, bool]]] = {
    # section -> key -> (type, required)
    "server": {"host": (str, True), "port": (int, True), "public_host": (str, True), "https": (bool, False)},
    "storage": {"data_dir": (str, True)},
    "backup": {"retention_days": (int, False)},
    "calendar": {"time_zone": (str, False)},
}
_REQUIRED_SECTIONS = frozenset({"server", "storage"})


class ConfigError(Exception):
    """The settings file is missing, malformed or holds an invalid value."""


@dataclass(frozen=True)
class ServerSettings:
    """`[server]`: where `rack serve` listens and which host name it answers to."""

    host: str
    port: int
    public_host: str
    https: bool = False


@dataclass(frozen=True)
class StorageSettings:
    """`[storage]`: the data folder (absolute)."""

    data_dir: Path


@dataclass(frozen=True)
class BackupSettings:
    """`[backup]`: snapshot retention (D-045)."""

    retention_days: int = DEFAULT_RETENTION_DAYS


@dataclass(frozen=True)
class CalendarSettings:
    """`[calendar]`: the IANA time zone giving a session its local date and times (D-065)."""

    time_zone: str = DEFAULT_TIME_ZONE

    @property
    def tz(self) -> tzinfo:
        """The zone as a `tzinfo`; the name was checked when the settings were loaded."""
        return ZoneInfo(self.time_zone)


@dataclass(frozen=True)
class Settings:
    """Everything the application needs from the machine, immutable once loaded."""

    server: ServerSettings
    storage: StorageSettings
    backup: BackupSettings
    secrets: Mapping[str, str]
    calendar: CalendarSettings = field(default_factory=CalendarSettings)

    @property
    def database_path(self) -> Path:
        """The SQLite database file inside the data folder."""
        return self.storage.data_dir / DATABASE_FILE_NAME

    @property
    def backups_dir(self) -> Path:
        """The folder of database snapshots inside the data folder."""
        return self.storage.data_dir / BACKUPS_FOLDER_NAME


def load_settings(config_path: Path) -> Settings:
    """Read and validate the settings file, then the secrets file beside it."""
    raw = _read_toml(config_path)
    _check_shape(raw, config_path)
    base = config_path.resolve().parent
    server = raw["server"]
    return Settings(
        server=ServerSettings(
            host=_non_empty(server["host"], "server.host", config_path),
            port=_in_range(server["port"], PORT_RANGE, "server.port", config_path),
            public_host=_non_empty(server["public_host"], "server.public_host", config_path),
            https=server.get("https", False),
        ),
        storage=StorageSettings(data_dir=_data_dir(raw["storage"]["data_dir"], base, config_path)),
        backup=BackupSettings(retention_days=_retention(raw.get("backup", {}), config_path)),
        secrets=_read_secrets(base / SECRETS_FILE_NAME),
        calendar=CalendarSettings(time_zone=_time_zone(raw.get("calendar", {}), config_path)),
    )


def _read_toml(config_path: Path) -> dict[str, Any]:
    try:
        with open(config_path, "rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"settings file not found: {config_path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{config_path}: malformed TOML: {error}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"{config_path}: not UTF-8 text") from None
    except OSError as error:
        raise ConfigError(f"cannot read settings file {config_path}: {error.strerror}") from None


def _check_shape(raw: dict[str, Any], config_path: Path) -> None:
    """Refuse unknown sections or keys, missing required ones and wrong types."""
    for section in raw:
        if section not in _SECTIONS:
            raise ConfigError(f"{config_path}: unknown section [{section}]")
        if not isinstance(raw[section], dict):
            raise ConfigError(f"{config_path}: [{section}] must be a table")
    for section in sorted(_REQUIRED_SECTIONS - raw.keys()):
        raise ConfigError(f"{config_path}: missing section [{section}]")
    for section, values in raw.items():
        _check_section(section, values, config_path)


def _check_section(section: str, values: dict[str, Any], config_path: Path) -> None:
    keys = _SECTIONS[section]
    for key, value in values.items():
        if key not in keys:
            raise ConfigError(f"{config_path}: unknown key {section}.{key}")
        expected = keys[key][0]
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError(f"{config_path}: {section}.{key} must be of type {expected.__name__}")
    for key, (_, required) in keys.items():
        if required and key not in values:
            raise ConfigError(f"{config_path}: missing key {section}.{key}")


def _non_empty(value: str, name: str, config_path: Path) -> str:
    if not value.strip():
        raise ConfigError(f"{config_path}: {name} must not be empty")
    return value


def _in_range(value: int, bounds: tuple[int, int], name: str, config_path: Path) -> int:
    low, high = bounds
    if not low <= value <= high:
        raise ConfigError(f"{config_path}: {name} must be between {low} and {high}")
    return value


def _data_dir(value: str, base: Path, config_path: Path) -> Path:
    path = Path(_non_empty(value, "storage.data_dir", config_path)).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _retention(backup: dict[str, Any], config_path: Path) -> int:
    days = backup.get("retention_days", DEFAULT_RETENTION_DAYS)
    if days < 1:
        raise ConfigError(f"{config_path}: backup.retention_days must be at least 1")
    return days


def _time_zone(calendar: dict[str, Any], config_path: Path) -> str:
    """The configured IANA zone name, refused when `zoneinfo` does not know it."""
    name = calendar.get("time_zone", DEFAULT_TIME_ZONE)
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"{config_path}: calendar.time_zone: unknown time zone {name!r}") from None
    return name


def _read_secrets(path: Path) -> Mapping[str, str]:
    """The secrets file as a read-only mapping; a missing file is an empty mapping."""
    if not path.is_file():
        return MappingProxyType({})
    try:
        values = dotenv_values(path)
    except UnicodeDecodeError:
        raise ConfigError(f"{path}: not UTF-8 text") from None
    except OSError as error:
        raise ConfigError(f"cannot read secrets file {path}: {error.strerror}") from None
    return MappingProxyType({key: value or "" for key, value in values.items()})
