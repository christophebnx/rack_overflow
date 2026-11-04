import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rack_overflow.config import (
    DEFAULT_RETENTION_DAYS,
    DEFAULT_TIME_ZONE,
    SECRETS_FILE_NAME,
    ConfigError,
    load_settings,
)

VALID = """
[server]
host = "0.0.0.0"
port = 8765
public_host = "rack.example.net"

[storage]
data_dir = "data"
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_file_with_defaults(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID))
    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 8765
    assert settings.server.public_host == "rack.example.net"
    assert settings.server.https is False
    assert settings.storage.data_dir == (tmp_path / "data").resolve()
    assert settings.database_path == settings.storage.data_dir / "rack.sqlite"
    assert settings.backups_dir == settings.storage.data_dir / "backups"
    assert settings.backup.retention_days == DEFAULT_RETENTION_DAYS
    assert dict(settings.secrets) == {}


def test_absolute_data_dir_and_optional_keys(tmp_path: Path) -> None:
    text = VALID.replace('"data"', f'"{(tmp_path / "abs").as_posix()}"')
    text += "\n[backup]\nretention_days = 7\n"
    settings = load_settings(write(tmp_path, text.replace("[storage]", "https = true\n\n[storage]")))
    assert settings.storage.data_dir == tmp_path / "abs"
    assert settings.backup.retention_days == 7
    assert settings.server.https is True


def test_secrets_file_beside_is_read_without_touching_the_environment(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("RACK_TEST_SECRET=value\n", encoding="utf-8")
    settings = load_settings(write(tmp_path, VALID))
    assert settings.secrets["RACK_TEST_SECRET"] == "value"
    assert "RACK_TEST_SECRET" not in os.environ


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (("port = 8765", "port = 0"), "server.port must be between"),
        (("port = 8765", "port = 70000"), "server.port must be between"),
        (("port = 8765", 'port = "8765"'), "server.port must be of type int"),
        (("port = 8765", "port = true"), "server.port must be of type int"),
        (('public_host = "rack.example.net"', 'public_host = " "'), "server.public_host must not be empty"),
        (('public_host = "rack.example.net"', ""), "missing key server.public_host"),
        (("[storage]", "[storage]\nextra = 1"), "unknown key storage.extra"),
        (("[storage]", "[other]\n[storage]"), "unknown section [other]"),
        (('[storage]\ndata_dir = "data"', ""), "missing section [storage]"),
        (("[server]", "[server\n"), "malformed TOML"),
        (("[storage]", "[backup]\nretention_days = 0\n[storage]"), "retention_days must be at least 1"),
    ],
)
def test_invalid_files(tmp_path: Path, change: tuple[str, str], fragment: str) -> None:
    with pytest.raises(ConfigError) as error:
        load_settings(write(tmp_path, VALID.replace(*change)))
    assert fragment in str(error.value)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="settings file not found"):
        load_settings(tmp_path / "absent.toml")


def test_example_file_is_valid(tmp_path: Path) -> None:
    # copied: loading it in place would read the developer's secrets file beside it
    example = Path(__file__).resolve().parents[2] / "config.example.toml"
    settings = load_settings(write(tmp_path, example.read_text(encoding="utf-8")))
    assert settings.storage.data_dir == tmp_path / ".local" / "dev-data"
    assert (settings.server.host, settings.server.port) == ("127.0.0.1", 8765)


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (("[storage]", "https = 1\n[storage]"), "server.https must be of type bool"),
        (('host = "0.0.0.0"', 'host = ""'), "server.host must not be empty"),
        (('data_dir = "data"', 'data_dir = "  "'), "storage.data_dir must not be empty"),
        (('data_dir = "data"', "data_dir = 1"), "storage.data_dir must be of type str"),
        (("port = 8765", "port = 8765.0"), "server.port must be of type int"),
        (
            ("[storage]", "[backup]\nretention_days = true\n[storage]"),
            "backup.retention_days must be of type int",
        ),
        (("[storage]", "[backup]\nretention_days = -3\n[storage]"), "retention_days must be at least 1"),
        (("[storage]", "[backup]\nkeep = 3\n[storage]"), "unknown key backup.keep"),
        (("[storage]", "[server.extra]\nx = 1\n[storage]"), "unknown key server.extra"),
    ],
)
def test_more_invalid_files(tmp_path: Path, change: tuple[str, str], fragment: str) -> None:
    text = VALID.replace(*change)
    assert text != VALID
    with pytest.raises(ConfigError) as error:
        load_settings(write(tmp_path, text))
    assert fragment in str(error.value)


def test_section_that_is_not_a_table(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[storage\] must be a table"):
        load_settings(write(tmp_path, 'storage = "data"\n' + VALID.split("[storage]", 1)[0]))


def test_missing_server_section(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"missing section \[server\]"):
        load_settings(write(tmp_path, "[storage]" + VALID.split("[storage]", 1)[1]))


def test_unreadable_settings_path(tmp_path: Path) -> None:
    folder = tmp_path / "folder.toml"
    folder.mkdir()
    with pytest.raises(ConfigError, match="cannot read settings file"):
        load_settings(folder)


def test_not_utf8_settings_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_bytes(VALID.replace("rack.example.net", "rack\xe9").encode("latin-1"))
    with pytest.raises(ConfigError, match="not UTF-8 text"):
        load_settings(path)


def test_not_utf8_secrets_file(tmp_path: Path) -> None:
    (tmp_path / SECRETS_FILE_NAME).write_bytes("RACK_A=caf\xe9\n".encode("latin-1"))
    with pytest.raises(ConfigError, match="not UTF-8 text"):
        load_settings(write(tmp_path, VALID))


def test_port_bounds_are_inclusive(tmp_path: Path) -> None:
    for port in (1, 65535):
        settings = load_settings(write(tmp_path, VALID.replace("port = 8765", f"port = {port}")))
        assert settings.server.port == port


def test_home_relative_data_dir_uses_the_home(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID.replace('"data"', '"~/rack-data"')))
    assert settings.storage.data_dir == Path.home() / "rack-data"
    assert settings.storage.data_dir.is_absolute()


def test_relative_data_dir_is_relative_to_the_settings_file_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "conf").mkdir()
    path = tmp_path / "conf" / "settings.toml"
    path.write_text(VALID.replace('"data"', '"../data"'), encoding="utf-8")
    monkeypatch.chdir(tmp_path / "conf")
    settings = load_settings(Path("settings.toml"))
    assert settings.storage.data_dir == (tmp_path / "data").resolve()


def test_secrets_are_read_only_and_empty_values_are_strings(tmp_path: Path) -> None:
    (tmp_path / SECRETS_FILE_NAME).write_text("RACK_A=\nRACK_B\nRACK_C='quoted value'\n", encoding="utf-8")
    settings = load_settings(write(tmp_path, VALID))
    assert dict(settings.secrets) == {"RACK_A": "", "RACK_B": "", "RACK_C": "quoted value"}
    with pytest.raises(TypeError):
        settings.secrets["RACK_D"] = "x"  # type: ignore[index]
    assert not any(name in os.environ for name in ("RACK_A", "RACK_B", "RACK_C"))


def test_settings_are_immutable(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID))
    with pytest.raises(AttributeError):
        settings.server.port = 1  # type: ignore[misc]


def test_loading_creates_nothing(tmp_path: Path) -> None:
    load_settings(write(tmp_path, VALID))
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.toml"]


def test_calendar_defaults_to_brussels(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID))
    assert settings.calendar.time_zone == DEFAULT_TIME_ZONE == "Europe/Brussels"
    assert settings.calendar.tz.key == "Europe/Brussels"  # type: ignore[attr-defined]


def test_calendar_time_zone_is_read(tmp_path: Path) -> None:
    settings = load_settings(write(tmp_path, VALID + '\n[calendar]\ntime_zone = "America/Montreal"\n'))
    assert settings.calendar.time_zone == "America/Montreal"
    assert settings.calendar.tz.utcoffset(datetime(2026, 1, 15)) == timedelta(hours=-5)


def test_example_file_sets_the_calendar(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "config.example.toml"
    settings = load_settings(write(tmp_path, example.read_text(encoding="utf-8")))
    assert settings.calendar.time_zone == "Europe/Brussels"


@pytest.mark.parametrize(
    ("calendar", "fragment"),
    [
        ('time_zone = "Mars/Olympus"', "calendar.time_zone: unknown time zone 'Mars/Olympus'"),
        ('time_zone = ""', "calendar.time_zone: unknown time zone ''"),
        ('time_zone = "../etc/passwd"', "calendar.time_zone: unknown time zone"),
        ("time_zone = 1", "calendar.time_zone must be of type str"),
        ('zone = "Europe/Paris"', "unknown key calendar.zone"),
    ],
)
def test_invalid_calendar(tmp_path: Path, calendar: str, fragment: str) -> None:
    with pytest.raises(ConfigError) as error:
        load_settings(write(tmp_path, VALID + f"\n[calendar]\n{calendar}\n"))
    assert fragment in str(error.value)
