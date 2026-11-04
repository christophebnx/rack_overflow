"""Every htmx write trigger has a status slot (D-053); the layout carries the nav (L2)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from request_status import triggers_without_slot, write_triggers

PAGE = {"accept": "text/html"}


def test_the_audit_finds_a_trigger_without_slot() -> None:
    assert triggers_without_slot('<div><button hx-post="/x">x</button></div>') == ["<button hx-post=/x>"]
    assert (
        triggers_without_slot(
            '<form hx-post="/x"><p data-request-status hidden></p><button>x</button></form>'
        )
        == []
    )
    assert (
        triggers_without_slot(
            '<section><p data-request-status></p><div><button hx-delete="/y"></button></div></section>'
        )
        == []
    )


def test_pairing_form_has_its_slot_first(unpaired_client: TestClient) -> None:
    html = unpaired_client.get("/appairage", headers=PAGE).text
    assert write_triggers(html) == 1
    assert triggers_without_slot(html) == []
    form = html[html.index('<form class="pairing-form"') :]
    assert form.index("data-request-status") < form.index('<div class="field">')


def test_pairing_refusal_keeps_the_slot(unpaired_client: TestClient) -> None:
    response = unpaired_client.post("/appairage", json={"code": "1"}, headers={"hx-request": "true"})
    assert triggers_without_slot(response.text) == []
    assert '<p class="form-status" data-request-status hidden></p>' in response.text


def test_layout_carries_the_not_saved_text_and_the_header_wrapper(client: TestClient) -> None:
    html = client.get("/", headers=PAGE).text
    assert 'data-not-saved="Non enregistré, réessayer"' in html
    assert '<div class="site-header__inner">' in html
    assert '<script src="/static/js/request-errors.js" defer></script>' in html
