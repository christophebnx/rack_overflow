import os
from pathlib import Path

import pytest

from rack_overflow.config import DEFAULT_RETENTION_DAYS, ConfigError, load_settings

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
