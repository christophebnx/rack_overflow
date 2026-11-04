"""Static checks of the web assets: vendored hashes, string keys, no inline script or style."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from rack_overflow.web.app import CATALOG, STATIC
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.rendering import TEMPLATES

VENDOR = STATIC / "vendor"
MANIFEST = json.loads((VENDOR / "manifest.json").read_text(encoding="utf-8"))
TEMPLATE_FILES = sorted(TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
def test_vendored_file_matches_the_manifest(name: str) -> None:
    entry = MANIFEST["files"][name]
    assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == entry["sha256"]
    assert (
        entry["source"]
        == f"https://unpkg.com/{entry['package']}@{entry['version']}/"
        + entry["source"].split(f"@{entry['version']}/", 1)[1]
    )


def test_every_vendored_file_is_in_the_manifest() -> None:
    files = {path.name for path in VENDOR.iterdir() if path.name != "manifest.json"}
    assert files == set(MANIFEST["files"])


def test_every_template_key_exists() -> None:
    keys = load_catalog(CATALOG).keys()
    used = {
        key
        for path in TEMPLATE_FILES
        for key in re.findall(r"""\bt\(\s*["']([\w.]+)["']""", path.read_text(encoding="utf-8"))
    }
    assert used
    assert used <= keys


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda path: path.name)
def test_templates_have_no_inline_script_or_style(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "<style" not in text
    assert " style=" not in text
    assert not re.search(r"\son[a-z]+\s*=", text)
    assert all("src=" in tag for tag in re.findall(r"<script[^>]*>", text))
    assert not re.search(r"""(?:src|href)=["'](?:https?:)?//""", text)


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda path: path.name)
def test_forms_disable_every_button_by_their_own_id(path: Path) -> None:
    """htmx's `find button` disables only the first button (docs/ui-spec.md "L6 — Forms disable
    every button"): a form names its buttons through its own id, `#<form id> button`."""
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"""hx-disabled-elt=["']\s*find\b""", text)
    for tag in re.findall(r"<form\b[^>]*>", text):
        disabled = re.search(r'hx-disabled-elt="([^"]*)"', tag)
        if disabled is None:
            continue
        form_id = re.search(r'\bid="([^"]+)"', tag)
        assert form_id is not None, tag
        assert disabled.group(1) == f"#{form_id.group(1)} button", tag
