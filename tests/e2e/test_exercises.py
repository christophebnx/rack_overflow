"""L2 exercise pages in real browsers: clean render, the « Kettlebell swing » and « Siège » flows,
search by « DC », a failed field save (D-053) and a revoked device's action."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from conftest import LiveApp, pairing_code
from playwright.sync_api import Browser, Page, expect
from test_pages import SCHEMES, WIDTHS, Watched
from test_variables import assert_clean

from rack_overflow.services import devices
from rack_overflow.web.app import CATALOG
from rack_overflow.web.auth import COOKIE_NAME
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
_COUNTER = itertools.count()


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


def create_exercise(page: Page, live_server: str, name: str, category: str) -> None:
    page.goto(live_server + "/exercices/nouveau")
    expect(page.locator("#nom")).to_be_focused()
    page.locator("#nom").fill(name)
    page.locator(f"#categorie-{category}").check()
    page.get_by_role("button", name=TEXT("exercise.create")).click()
    expect(page.locator("#exercice-titre")).to_have_text(name)


def weight_row(page: Page) -> str:
    row = page.locator(".field-row", has_text=TEXT("quantity.weight"))
    return str(row.get_attribute("id"))


def test_exercise_pages_render_clean(watched: Watched, live_server: str) -> None:
    page = watched.page
    name = f"Kettlebell swing {next(_COUNTER)}"
    create_exercise(page, live_server, name, "kettlebell")
    assert_clean(watched)
    expect(page.get_by_role("link", name=TEXT("nav.exercises"), exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    page.goto(live_server + "/exercices")
    expect(page.locator(".row", has_text=name)).to_be_visible()
    assert_clean(watched)


def test_kettlebell_swing_loads(page: Page, live_server: str) -> None:
    create_exercise(page, live_server, f"Swing {next(_COUNTER)}", "kettlebell")
    row = "#" + weight_row(page)
    page.locator(f"{row} summary").click()
    page.locator(f"{row} input[name=mode][value=values]").check()
    expect(page.locator(f"{row}-pas")).to_be_hidden()
    page.locator(f"{row}-valeurs").fill("16 20 24")
    page.locator(f"{row}-defaut").fill("20")
    page.locator(f"{row} button[type=submit]").click()
    expect(page.locator(f"{row} .field-row__summary")).to_contain_text("16 · 20 · 24\u00a0kg")
    expect(page.locator(f"{row}-modifier")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(TEXT("status.saved"))


def test_seat_from_the_exercise_page(page: Page, live_server: str) -> None:
    create_exercise(page, live_server, f"Presse {next(_COUNTER)}", "strength")
    page.get_by_role("link", name=TEXT("field.new_variable")).click()
    label = f"Siège {next(_COUNTER)}"
    page.locator("#libelle").fill(label)
    page.get_by_label(TEXT("variable.scope.setting"), exact=True).check()
    page.locator("#type").select_option("enum")
    page.locator("#valeurs").fill("\n".join(str(n) for n in range(1, 11)))
    page.get_by_role("button", name=TEXT("variable.create")).click()
    page.wait_for_url("**/exercices/*?ajout=*")
    expect(page.locator("#champ-ajout")).to_be_focused()
    page.locator(".add-field button[type=submit]").click()
    row = page.locator(".field-row", has_text=label)
    expect(row).to_be_visible()
    expect(row.locator("input[name=required]")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(TEXT("exercise.announce_field_added", field=label))


def test_search_by_alias(page: Page, live_server: str) -> None:
    name = f"Développé couché (barre) {next(_COUNTER)}"
    create_exercise(page, live_server, name, "strength")
    page.locator("#alias-nouveau").fill("DC")
    page.get_by_role("button", name=TEXT("action.add"), exact=True).last.click()
    expect(page.locator(".alias__text", has_text="DC")).to_be_visible()
    expect(page.locator("#alias-nouveau")).to_be_focused()
    page.goto(live_server + "/exercices")
    page.locator("#q").fill("DC")
    expect(page.locator("#resultats .row", has_text=name)).to_be_visible()
    page.wait_for_url("**/exercices?q=DC")


def test_failed_field_save_says_not_saved(page: Page, live_server: str) -> None:
    create_exercise(page, live_server, f"Rowing {next(_COUNTER)}", "strength")
    row = "#" + weight_row(page)
    page.locator(f"{row} summary").click()
    page.route(
        "**/champs/*", lambda route: route.abort() if route.request.method == "PATCH" else route.continue_()
    )
    page.locator(f"{row}-pas").fill("5")
    page.locator(f"{row} button[type=submit]").click()
    slot = page.locator(f"{row}-formulaire [data-request-status]")
    expect(slot).to_have_text(TEXT("error.not_saved"))
    expect(page.locator(f"{row}-pas")).to_have_value("5")
    expect(page.locator(f"{row}-obligatoire")).to_be_focused()
    page.unroute("**/champs/*")
    page.locator(f"{row} button[type=submit]").click()
    expect(page.locator(f"{row} .field-row__summary")).to_contain_text("5\u00a0kg")


def test_failed_search_says_search_failed(page: Page, live_server: str) -> None:
    page.goto(live_server + "/exercices")
    page.route("**/exercices/recherche*", lambda route: route.fulfill(status=500, body="{}"))
    page.locator("#q").fill("squat")
    slot = page.locator(".search [data-request-status]")
    expect(slot).to_have_text(TEXT("error.search_failed"))
    expect(page.locator("#q")).to_be_focused()


def test_revoked_device_action_lands_on_pairing(browser: Browser, live_app: LiveApp) -> None:
    name = f"e2e-revoked-{next(_COUNTER)}"
    token = devices.pair(live_app.engine, pairing_code(live_app, name), datetime.now(UTC)).token
    assert token is not None
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.add_cookies([{"name": COOKIE_NAME, "value": token, "url": live_app.url + "/"}])
    page = context.new_page()
    create_exercise(page, live_app.url, f"Dips {next(_COUNTER)}", "bodyweight")
    devices.revoke_device(live_app.engine, name, datetime.now(UTC))
    page.get_by_role("button", name=TEXT("action.archive")).click()
    page.wait_for_url(live_app.url + "/appairage")
    context.close()
