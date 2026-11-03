"""L1b pairing page in real browsers: clean render, pairing by code, refusal shown in place."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import LiveApp, pairing_code
from playwright.sync_api import Browser, expect
from test_pages import SCHEMES, WIDTHS, Watched

from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text


@pytest.fixture(params=[(w, s) for w in WIDTHS for s in SCHEMES], ids=lambda p: f"{p[0]}px-{p[1]}")
def unpaired(request: pytest.FixtureRequest, browser: Browser, live_server: str) -> Iterator[Watched]:
    """A fresh browser context without the device cookie."""
    width, scheme = request.param
    context = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme)
    yield Watched(context.new_page(), live_server, scheme)
    context.close()


def test_unpaired_home_lands_on_a_clean_pairing_page(unpaired: Watched, live_server: str) -> None:
    page = unpaired.page
    response = page.goto(live_server + "/")
    assert response is not None and response.status == 200
    assert page.url == live_server + "/appairage"
    expect(page.locator("h1")).to_have_text(TEXT("pairing.title"))
    expect(page.locator("#code")).to_be_focused()
    assert unpaired.foreign == []
    assert not [text for text in unpaired.console if "Content Security Policy" in text or "Refused" in text]
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0
    box = page.locator("#code").bounding_box()
    assert box is not None and box["height"] >= 48


def test_right_code_pairs_and_opens_home(unpaired: Watched, live_app: LiveApp) -> None:
    page = unpaired.page
    page.goto(live_app.url + "/appairage")
    code = pairing_code(live_app, f"e2e-{unpaired.scheme}-{page.viewport_size['width']}")  # type: ignore[index]
    page.locator("#code").fill(f"{code[:4]} {code[4:]}")
    page.get_by_role("button", name=TEXT("pairing.submit")).click()
    page.wait_for_url(live_app.url + "/")
    expect(page.locator("h1")).to_have_text(TEXT("home.title"))
    assert page.goto(live_app.url + "/") is not None
    assert page.url == live_app.url + "/"


def test_wrong_code_shows_the_message_in_place(unpaired: Watched, live_server: str) -> None:
    page = unpaired.page
    page.goto(live_server + "/appairage")
    page.locator("#code").fill("12")
    page.get_by_role("button", name=TEXT("pairing.submit")).click()
    message = TEXT("pairing.wrong_code")
    expect(page.locator("#code-erreur")).to_have_text(message)
    expect(page.locator("#annonce")).to_have_text(message)
    expect(page.locator("#code")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#code")).to_have_value("")
    assert page.url == live_server + "/appairage"
