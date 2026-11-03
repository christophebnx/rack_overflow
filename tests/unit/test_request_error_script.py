"""The request-error display (D-053): one first-party script, loaded after htmx, no French text."""

from __future__ import annotations

import json
import re

from rack_overflow.web.app import STATIC
from rack_overflow.web.rendering import TEMPLATES

SCRIPT = STATIC / "js" / "request-errors.js"
BASE = (TEMPLATES / "base.html").read_text(encoding="utf-8")


def test_script_is_ascii_and_has_no_eval() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.isascii()  # no user-facing (French) text can hide in it
    assert "eval(" not in text and "new Function" not in text and "innerHTML" not in text
    assert "htmx:afterRequest" in text and "htmx:beforeRequest" in text


def test_script_is_loaded_deferred_after_htmx() -> None:
    scripts = re.findall(r'<script src="([^"]+)" defer></script>', BASE)
    assert scripts == [
        "/static/vendor/htmx.min.js",
        "/static/vendor/json-enc.js",
        "/static/js/request-errors.js",
    ]


def test_body_carries_the_not_saved_text_and_htmx_times_out() -> None:
    assert "data-not-saved=\"{{ t('error.not_saved') }}\"" in BASE
    config = json.loads(re.search(r"name=\"htmx-config\" content='([^']+)'", BASE).group(1))  # type: ignore[union-attr]
    assert config["timeout"] == 10000
    assert config["allowEval"] is False
