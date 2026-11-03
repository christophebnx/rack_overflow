"""L2 variable pages in real browsers: clean render, the « Siège » flow, in-place delete
confirmation, conditional type fields, and a failed save (D-053)."""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, expect
from test_pages import SCHEMES, WIDTHS, Watched

from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
_COUNTER = itertools.count()


def unique(label: str) -> str:
    return f"{label} {next(_COUNTER)}"


@pytest.fixture(params=[(w, s) for w in WIDTHS for s in SCHEMES], ids=lambda p: f"{p[0]}px-{p[1]}")
def watched(
    request: pytest.FixtureRequest,
    browser: Browser,
    live_server: str,
    device_cookies: list[dict[str, object]],
) -> Iterator[Watched]:
    width, scheme = request.param
    context = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme)
    context.add_cookies(device_cookies)  # type: ignore[arg-type]
    yield Watched(context.new_page(), live_server, scheme)
    context.close()


@pytest.fixture
def page(watched: Watched) -> Page:
    return watched.page


WIDER_THAN_VIEWPORT = """() => {
  const width = document.documentElement.clientWidth;
  return [...document.querySelectorAll("body *")]
    .filter((el) => el.getBoundingClientRect().right > width + 0.5)
    .slice(0, 5)
    .map((el) => `${el.tagName}.${el.className}#${el.id} ${Math.round(el.getBoundingClientRect().right)}`);
}"""
"""Diagnostics of a failed no-horizontal-scroll check: the elements past the right edge."""


def assert_clean(watched: Watched) -> None:
    assert watched.foreign == []
    assert not [text for text in watched.console if "Content Security Policy" in text or "Refused" in text]
    overflow = watched.page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, (watched.page.url, watched.page.evaluate(WIDER_THAN_VIEWPORT))


def create_variable(page: Page, live_server: str, label: str, values: str = "1\n2\n3") -> None:
    page.goto(live_server + "/variables/nouvelle")
    page.locator("#libelle").fill(label)
    page.get_by_label(TEXT("variable.scope.setting"), exact=True).check()
    page.locator("#type").select_option("enum")
    page.locator("#valeurs").fill(values)
    page.get_by_role("button", name=TEXT("variable.create")).click()
    expect(page.locator("#variable-titre")).to_have_text(label)
    page.wait_for_load_state()  # htmx has processed the new page before the next click


def test_variable_pages_render_clean(watched: Watched, live_server: str) -> None:
    page = watched.page
    label = unique("Siège")
    create_variable(page, live_server, label, "\n".join(str(n) for n in range(1, 11)))
    assert_clean(watched)
    expect(page.locator(".enum-value")).to_have_count(10)
    page.goto(live_server + "/variables")
    expect(page.get_by_role("link", name=TEXT("nav.variables"), exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    # exact title: « Siège 1 » must not match « Siège 11 » created by another test
    expect(page.get_by_role("link", name=re.compile(rf"^{re.escape(label)} "))).to_be_visible()
    assert_clean(watched)
    brand = page.locator(".brand").bounding_box()
    title = page.locator("h1").bounding_box()
    assert brand is not None and title is not None and brand["x"] == pytest.approx(title["x"], abs=1)
    for link in ("nav.exercises", "nav.variables"):
        box = page.get_by_role("link", name=TEXT(link), exact=True).bounding_box()
        assert box is not None and box["height"] >= 48


def test_type_select_shows_only_its_fields(page: Page, live_server: str) -> None:
    page.goto(live_server + "/variables/nouvelle")
    expect(page.locator("#libelle")).to_be_focused()
    for hidden in ("#unite", "#decimales", "#valeurs"):
        expect(page.locator(hidden)).to_be_hidden()
    page.locator("#type").select_option("decimal")
    expect(page.locator("#unite")).to_be_visible()
    expect(page.locator("#decimales")).to_be_visible()
    expect(page.locator("#valeurs")).to_be_hidden()
    page.locator("#type").select_option("enum")
    expect(page.locator("#valeurs")).to_be_visible()
    expect(page.locator("#unite")).to_be_hidden()


def test_refused_create_marks_the_field(page: Page, live_server: str) -> None:
    page.goto(live_server + "/variables/nouvelle")
    page.locator("#libelle").fill("   ")
    page.get_by_label(TEXT("variable.scope.set"), exact=True).check()
    page.locator("#type").select_option("int")
    page.get_by_role("button", name=TEXT("variable.create")).click()
    expect(page.locator("#libelle-erreur")).to_have_text(TEXT("catalog.error.required"))
    expect(page.locator("#libelle")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#libelle")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(TEXT("catalog.error.required"))


def test_delete_confirmation_in_place(page: Page, live_server: str) -> None:
    create_variable(page, live_server, unique("Prise"))
    page.get_by_role("button", name=TEXT("variable.delete")).click()
    cancel = page.get_by_role("button", name=TEXT("action.cancel"))
    expect(cancel).to_be_focused()
    cancel.click()
    expect(page.get_by_role("button", name=TEXT("variable.delete"))).to_be_focused()
    page.get_by_role("button", name=TEXT("variable.delete")).click()
    page.get_by_role("button", name=TEXT("variable.confirm_delete")).click()
    page.wait_for_url(live_server + "/variables")


def test_archive_then_restore(page: Page, live_server: str) -> None:
    create_variable(page, live_server, unique("Inclinaison"))
    page.get_by_role("button", name=TEXT("action.archive")).click()
    expect(page.get_by_role("button", name=TEXT("action.restore"))).to_be_focused()
    expect(page.locator("#variable-etat .tag")).to_have_text(TEXT("tag.archived_f"))
    expect(page.locator("#annonce")).to_have_text(TEXT("variable.announce_archived"))
    page.get_by_role("button", name=TEXT("action.restore")).click()
    expect(page.get_by_role("button", name=TEXT("action.archive"))).to_be_focused()
    expect(page.locator("#variable-etat .tag")).to_have_count(0)


def test_failed_save_keeps_values_and_says_not_saved(page: Page, live_server: str) -> None:
    label = unique("Barre")
    create_variable(page, live_server, label)
    page.route(
        "**/variables/*",
        lambda route: route.abort() if route.request.method == "PATCH" else route.continue_(),
    )
    page.locator("#libelle").fill(label + " modifiée")
    page.get_by_role("button", name=TEXT("action.save")).click()
    slot = page.locator("#variable-formulaire [data-request-status]")
    expect(slot).to_have_text(TEXT("error.not_saved"))
    expect(slot).to_have_attribute("data-kind", "error")
    expect(page.locator("#libelle")).to_have_value(label + " modifiée")
    expect(page.locator("#libelle")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(TEXT("error.not_saved"))
    page.unroute("**/variables/*")
    page.get_by_role("button", name=TEXT("action.save")).click()
    expect(slot).to_have_text(TEXT("status.saved"))
    expect(page.locator("#variable-titre")).to_have_text(label + " modifiée")
