import logging
from pathlib import Path

import pytest

from rack_overflow.web.locale import Catalog, LocaleError, load_catalog


def test_placeholders_are_filled() -> None:
    assert Catalog({"a": "Code {status}"}).text("a", status=404) == "Code 404"


def test_missing_key_renders_the_key_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    catalog = Catalog({})
    with caplog.at_level(logging.WARNING):
        assert catalog.text("nope") == "nope"
        assert catalog.text("nope") == "nope"
    assert len([r for r in caplog.records if "nope" in r.getMessage()]) == 1


def test_missing_parameter_is_an_error() -> None:
    with pytest.raises(LocaleError):
        Catalog({"a": "Code {status}"}).text("a")


@pytest.mark.parametrize(
    "content",
    ["[]", '{"a": 1}', '{"a": "{0}"}', '{"a": "{x!r}"}', '{"a": "{x:>3}"}', '{"a": "{"}', "not json"],
)
def test_malformed_catalog(tmp_path: Path, content: str) -> None:
    path = tmp_path / "fr.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(LocaleError):
        load_catalog(path)


def test_bom_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "fr.json"
    path.write_text('{"a": "é"}', encoding="utf-8-sig")
    assert load_catalog(path).text("a") == "é"
