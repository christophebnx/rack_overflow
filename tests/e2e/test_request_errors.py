"""D-053 in real browsers: a failed htmx request keeps the form, shows « Non enregistré, réessayer »
in its slot and the live region, clears old refusals, focuses the form; a retry starts clean.
Also the L2 header: brand and content share their left edge."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route, expect

from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
NOT_SAVED = TEXT("error.not_saved")


@pytest.fixture(params=[360, 1280], ids=lambda width: f"{width}px")
def page(request: pytest.FixtureRequest, browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": request.param, "height": 800})
    yield context.new_page()
    context.close()


def _submit_wrong_code(page: Page) -> None:
    page.locator("#code").fill("12")
    page.get_by_role("button", name=TEXT("pairing.submit")).click()
    expect(page.locator("#code-erreur")).to_be_visible()


@pytest.mark.parametrize("failure", ["abort", "500"])
def test_failed_pairing_post_shows_not_saved(page: Page, live_server: str, failure: str) -> None:
    page.goto(live_server + "/appairage")
    _submit_wrong_code(page)

    def fail(route: Route) -> None:
        if failure == "abort":
            route.abort()
        else:
            route.fulfill(status=500, content_type="application/json", body='{"error": "internal"}')

    page.route(
        "**/appairage", lambda route: fail(route) if route.request.method == "POST" else route.continue_()
    )
    page.locator("#code").fill("1234 5678")
    page.get_by_role("button", name=TEXT("pairing.submit")).click()
    slot = page.locator(".pairing-form [data-request-status]")
    expect(slot).to_have_text(NOT_SAVED)
    expect(slot).to_be_visible()
    expect(slot).to_have_attribute("data-kind", "error")
    expect(page.locator("#annonce")).to_have_text(NOT_SAVED)
    expect(page.locator("#code")).to_have_value("1234 5678")
    expect(page.locator("#code")).to_be_focused()
    expect(page.locator("#code-erreur")).to_be_hidden()
    expect(page.locator("#code")).not_to_have_attribute("aria-invalid", "true")
    assert "code-erreur" not in (page.locator("#code").get_attribute("aria-describedby") or "")
    expect(page.get_by_role("button", name=TEXT("pairing.submit"))).to_be_enabled()

    page.unroute("**/appairage")
    page.locator("#code").fill("12")
    page.get_by_role("button", name=TEXT("pairing.submit")).click()
    expect(page.locator("#code-erreur")).to_have_text(TEXT("pairing.wrong_code"))
    expect(page.locator(".pairing-form [data-request-status]")).to_be_hidden()


def test_brand_and_content_share_the_left_edge(page: Page, live_server: str) -> None:
    page.goto(live_server + "/appairage")
    brand = page.locator(".brand").bounding_box()
    title = page.locator("h1").bounding_box()
    assert brand is not None and title is not None
    assert brand["x"] == pytest.approx(title["x"], abs=1)
