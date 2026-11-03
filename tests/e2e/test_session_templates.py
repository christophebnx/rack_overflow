"""L3 session template pages in real browsers (docs/ui-spec.md L3): clean render of the seeded
list and detail at 360 / 1280 px in both schemes, the « Salle 1 » flow, focus after a move and
after a failed move (D-053), and the three-link navigation on the phone."""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest
from conftest import LiveApp
from playwright.sync_api import Browser, Page, expect
from test_pages import SCHEMES, WIDTHS, Watched
from test_variables import assert_clean

from rack_overflow.services import exercises, seed, templates
from rack_overflow.services.templates import TemplateForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
_COUNTER = itertools.count()
USER = 1
LONGEST = "Salle B — Charnière & poussée verticale"
SQUAT_TARGET = "4\u00a0\u00d7\u00a06\u20138"  # sets, multiplication sign, reps range


@pytest.fixture(scope="module", autouse=True)
def seeded(live_app: LiveApp) -> None:
    """The seed of brief 6.1 in the live database (idempotent: the version is stored)."""
    seed.seed_catalog(live_app.engine, USER)


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


def template_id(live_app: LiveApp, name: str) -> int:
    found = [
        t
        for t in templates.list_templates(live_app.engine, USER, include_archived=True)
        if t.draft.name == name
    ]
    assert len(found) == 1
    return found[0].id


def big_menu(live_app: LiveApp) -> int:
    """A template whose menu offers 12 exercises, with a long name."""
    name = f"Menu de douze exercices au choix pour tester {next(_COUNTER)}"
    created = templates.create(live_app.engine, USER, TemplateForm(name, "both"))
    ids = [e.id for e in exercises.list_exercises(live_app.engine, USER)][:12]
    slot = templates.add_slot(
        live_app.engine, USER, created, kind="menu", exercise_id=ids[0], label="Ischios / fessiers et dos"
    )
    for exercise_id in ids[1:]:
        templates.add_option(live_app.engine, USER, created, slot, exercise_id)
    return created


def test_template_pages_render_clean(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    page.goto(live_app.url + "/seances-types")
    expect(page.get_by_role("link", name=TEXT("nav.templates"), exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    expect(page.locator(".template-row").first).to_be_visible()
    assert_clean(watched)
    page.goto(f"{live_app.url}/seances-types/{template_id(live_app, LONGEST)}")
    expect(page.locator("#seance-type-titre")).to_have_text(LONGEST)
    expect(page.locator(".slot")).to_have_count(6)
    assert_clean(watched)
    page.locator(".slot").nth(2).locator("summary").click()  # a menu's « Modifier » open
    expect(page.locator(".slot").nth(2).locator(".option")).to_have_count(3)
    assert_clean(watched)
    page.goto(f"{live_app.url}/seances-types/{big_menu(live_app)}")
    page.locator(".slot summary").first.click()
    expect(page.locator(".option")).to_have_count(12)
    expect(page.locator(".add-option p.muted")).to_have_text(TEXT("template.options_full"))
    assert_clean(watched)
    page.goto(live_app.url + "/seances-types/nouvelle")
    expect(page.locator("#seance-nom")).to_be_focused()
    assert_clean(watched)


def test_nav_has_three_links_that_fit_on_the_phone(watched: Watched, live_server: str) -> None:
    page = watched.page
    page.goto(live_server + "/seances-types")
    brand = page.locator(".brand").bounding_box()
    assert brand is not None
    for key in ("nav.exercises", "nav.variables", "nav.templates"):
        box = page.get_by_role("link", name=TEXT(key), exact=True).bounding_box()
        assert box is not None and box["height"] >= 48
        if page.viewport_size and page.viewport_size["width"] < 640:
            assert box["y"] >= brand["y"] + brand["height"] - 1  # the nav has its own row under the brand
    assert_clean(watched)


def test_salle_1_flow(page: Page, live_app: LiveApp) -> None:
    name = f"Salle 1 {next(_COUNTER)}"
    page.goto(live_app.url + "/seances-types/nouvelle")
    page.locator("#seance-nom").fill(name)
    page.locator("#seance-lieu-gym").check()
    page.get_by_role("button", name=TEXT("template.create")).click()
    expect(page.locator("#seance-type-titre")).to_have_text(name)
    page.wait_for_load_state()
    expect(page.locator(".template-slots .empty")).to_be_visible()

    page.locator("#bloc-ajout-menu-type").check()
    expect(page.locator("#bloc-ajout-menu")).to_be_visible()
    page.locator("#bloc-ajout-menu").fill("Tirage")
    page.locator("#bloc-ajout-exercice").select_option(label="Rowing barre au rack")
    page.get_by_role("button", name=TEXT("template.add_slot")).click()
    menu = page.locator(".slot").first
    expect(menu.locator(".slot__name")).to_have_text("Tirage")
    select = menu.locator("select[id$=-option-ajout]")
    expect(select).to_be_focused()
    for option in ("Rowing assis machine", "Tirage horizontal poulie"):
        select.select_option(label=option)
        menu.get_by_role("button", name=TEXT("action.add"), exact=True).click()
        expect(menu.locator(".option", has_text=option)).to_be_visible()
        expect(select).to_be_focused()
    expect(menu.locator(".option")).to_have_count(3)

    expect(page.locator("#bloc-ajout-menu")).to_be_hidden()
    page.locator("#bloc-ajout-exercice").select_option(label="Squat au rack (barre)")
    page.get_by_role("button", name=TEXT("template.add_slot")).click()
    squat = page.locator(".slot").nth(1)
    expect(squat.locator(".slot__name")).to_have_text("Squat au rack (barre)")
    expect(squat.locator("input[name=sets]")).to_be_focused()
    squat.locator("input[name=sets]").fill("4")
    squat.locator("input[name=reps]").fill("6-8")
    squat.get_by_role("button", name=TEXT("action.save")).click()
    expect(page.locator(".slot").nth(1).locator(".slot__target")).to_have_text(SQUAT_TARGET)
    expect(page.locator(".slot").nth(1).locator("summary")).to_be_focused()

    up = page.locator(".slot").nth(1).locator("[id$=-monter]")
    up_id = up.get_attribute("id")
    up.click()
    expect(page.locator(".slot").first.locator(".slot__name")).to_have_text("Squat au rack (barre)")
    expect(page.locator(f"#{up_id[: -len('monter')]}descendre")).to_be_focused()  # type: ignore[index]

    page.get_by_role("button", name=TEXT("action.archive")).click()
    expect(page.locator("#seance-type-etat .tag")).to_have_text(TEXT("tag.archived_f"))
    expect(page.get_by_role("button", name=TEXT("action.restore"))).to_be_focused()
    page.goto(live_app.url + "/seances-types")
    expect(page.get_by_role("link", name=name)).to_have_count(0)


def test_failed_move_keeps_focus_on_its_button(page: Page, live_app: LiveApp) -> None:
    page.goto(f"{live_app.url}/seances-types/{template_id(live_app, LONGEST)}")
    page.route("**/deplacement", lambda route: route.abort())
    button = page.locator(".slot").first.locator("[id$=-descendre]")
    button.click()
    expect(page.locator("#blocs > [data-request-status]")).to_have_text(TEXT("error.not_saved"))
    expect(button).to_be_focused()
    page.unroute("**/deplacement")
    page.goto(live_app.url + "/seances-types")
    page.route("**/deplacement", lambda route: route.abort())
    row_button = page.locator(".template-row").first.locator("[id$=-descendre]")
    row_button.click()
    expect(page.locator("#seances-types-liste > [data-request-status]")).to_have_text(TEXT("error.not_saved"))
    expect(row_button).to_be_focused()
