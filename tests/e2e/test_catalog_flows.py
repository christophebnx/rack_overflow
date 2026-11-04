"""L2 flows not covered elsewhere, in real browsers: « Vélo » with a « Résistance » measure created
from the exercise page, D-053 on a timeout and on a 5xx of the exercise form (old refusal cleared,
message gone on retry), navigation state and header alignment on catalog pages."""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, Route, expect
from test_exercises import row_link
from test_pages import SCHEMES, WIDTHS, Watched
from test_variables import assert_clean

from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
NOT_SAVED = TEXT("error.not_saved")
_COUNTER = itertools.count()


def unique(name: str) -> str:
    return f"{name} {next(_COUNTER)}"


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


@pytest.fixture(params=WIDTHS, ids=lambda width: f"{width}px")
def page(
    request: pytest.FixtureRequest, browser: Browser, device_cookies: list[dict[str, object]]
) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": request.param, "height": 800})
    context.add_cookies(device_cookies)  # type: ignore[arg-type]
    yield context.new_page()
    context.close()


def create_exercise(page: Page, live_server: str, name: str, category: str) -> None:
    page.goto(live_server + "/exercices/nouveau")
    page.locator("#nom").fill(name)
    page.locator(f"#categorie-{category}").check()
    page.get_by_role("button", name=TEXT("exercise.create")).click()
    expect(page.locator("#exercice-titre")).to_have_text(name)
    page.wait_for_load_state()  # htmx has processed the new page before the next click


def test_bike_with_a_resistance_measure_created_in_the_ui(watched: Watched, live_server: str) -> None:
    page = watched.page
    bike = unique("Vélo")
    create_exercise(page, live_server, bike, "cardio")
    expect(page.locator(".field-row", has_text=TEXT("quantity.duration"))).to_be_visible()
    expect(page.locator(".field-row", has_text=TEXT("quantity.distance"))).to_be_visible()
    page.get_by_role("link", name=TEXT("field.new_variable")).click()
    label = unique("Résistance")
    page.locator("#libelle").fill(label)
    page.get_by_label(TEXT("variable.scope.set"), exact=True).check()
    page.locator("#type").select_option("int")
    page.get_by_role("button", name=TEXT("variable.create")).click()
    page.wait_for_url("**/exercices/*?ajout=*")
    expect(page.locator("#champ-ajout")).to_be_focused()
    page.locator(".add-field button[type=submit]").click()
    rows = page.locator(".field-row")
    expect(rows).to_have_count(3)
    expect(rows.nth(2)).to_contain_text(label)
    assert_clean(watched)


def test_timeout_says_not_saved_and_keeps_the_form(page: Page, live_server: str) -> None:
    name = unique("Tirage")
    create_exercise(page, live_server, name, "strength")
    page.evaluate("() => { htmx.config.timeout = 300; }")
    held: list[Route] = []
    page.route(
        "**/exercices/*",
        lambda route: held.append(route) if route.request.method == "PATCH" else route.continue_(),
    )
    page.locator("#nom").fill(name + " modifié")
    page.get_by_role("button", name=TEXT("action.save")).first.click()
    form = page.locator("form", has=page.locator("#nom"))
    slot = form.locator("[data-request-status]")
    expect(slot).to_have_text(NOT_SAVED)
    expect(slot).to_be_visible()
    expect(page.locator("#annonce")).to_have_text(NOT_SAVED)
    expect(page.locator("#nom")).to_have_value(name + " modifié")
    expect(page.locator("#nom")).to_be_focused()
    expect(page.get_by_role("button", name=TEXT("action.save")).first).to_be_enabled()
    for route in held:
        route.abort()


def test_server_error_clears_the_old_refusal_and_retry_clears_the_message(
    page: Page, live_server: str
) -> None:
    taken = unique("Curl taken")
    create_exercise(page, live_server, taken, "strength")
    page.goto(live_server + "/exercices/nouveau")
    page.locator("#nom").fill(taken)
    page.locator("#categorie-strength").check()
    page.get_by_role("button", name=TEXT("exercise.create")).click()
    expect(page.locator("#nom")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#nom-erreur")).to_have_text(TEXT("catalog.error.name_taken"))
    page.route(
        "**/exercices",
        lambda route: (
            route.fulfill(status=500, content_type="application/json", body='{"error": "internal"}')
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    name = unique("Curl")
    page.locator("#nom").fill(name)
    page.locator("#categorie-strength").check()
    page.get_by_role("button", name=TEXT("exercise.create")).click()
    slot = page.locator("form [data-request-status]").first
    expect(slot).to_have_text(NOT_SAVED)
    expect(page.locator("#nom")).not_to_have_attribute("aria-invalid", "true")
    expect(page.locator("#nom-erreur")).to_be_hidden()
    expect(page.locator("#nom")).to_have_value(name)
    expect(page.locator("#nom")).to_be_focused()
    page.unroute("**/exercices")
    page.get_by_role("button", name=TEXT("exercise.create")).click()
    expect(page.locator("#exercice-titre")).to_have_text(name)


def test_nav_marks_the_section_on_detail_pages(page: Page, live_server: str) -> None:
    create_exercise(page, live_server, unique("Squat"), "strength")
    exercises_link = page.get_by_role("link", name=TEXT("nav.exercises"), exact=True)
    variables_link = page.get_by_role("link", name=TEXT("nav.variables"), exact=True)
    expect(exercises_link).to_have_attribute("aria-current", "page")
    expect(variables_link).not_to_have_attribute("aria-current", "page")
    page.goto(live_server + "/variables/nouvelle")
    expect(variables_link).to_have_attribute("aria-current", "page")
    expect(exercises_link).not_to_have_attribute("aria-current", "page")


@pytest.mark.parametrize("path", ["/exercices", "/variables", "/exercices/nouveau", "/variables/nouvelle"])
def test_brand_and_title_share_the_left_edge_on_catalog_pages(
    page: Page, live_server: str, path: str
) -> None:
    page.goto(live_server + path)
    brand = page.locator(".brand").bounding_box()
    title = page.locator("main h1").first.bounding_box()
    assert brand is not None and title is not None
    assert brand["x"] == pytest.approx(title["x"], abs=1)


def test_archived_exercise_hidden_then_shown_on_demand(page: Page, live_server: str) -> None:
    name = unique("Hip thrust")
    create_exercise(page, live_server, name, "strength")
    page.get_by_role("button", name=TEXT("action.archive")).click()
    expect(page.get_by_role("button", name=TEXT("action.restore"))).to_be_focused()
    page.goto(live_server + "/exercices")
    page.locator("#q").fill(name)
    expect(page.locator("#resultats")).not_to_contain_text(name)
    page.locator("input[name=archives]").check()
    row = row_link(page.locator("#resultats"), name)
    expect(row).to_be_visible()
    expect(row.locator(".tag")).to_have_text(TEXT("tag.archived_m"))
