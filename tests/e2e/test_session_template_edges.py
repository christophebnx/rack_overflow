"""L3 edge states in real browsers: refusals (D-050) and failed requests (D-053) on the new
template forms and row actions, the two-row header at 360 px, and the archived states."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from conftest import LiveApp
from playwright.sync_api import Browser, Route, expect
from test_pages import SCHEMES, WIDTHS, Watched
from test_variables import assert_clean

from rack_overflow.services import exercises, seed, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser
TEXT = load_catalog(CATALOG).text
USER = 1
_COUNTER = itertools.count()


@pytest.fixture(scope="module", autouse=True)
def seeded(live_app: LiveApp) -> None:
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


def fail(route: Route) -> None:
    route.fulfill(status=500, content_type="application/json", body='{"error": "internal"}')


def fresh_template(live_app: LiveApp) -> tuple[int, int, int]:
    """A template with one fixed slot and a two-option menu; (template, fixed slot, menu)."""
    name = f"Bords {next(_COUNTER)}"
    created = templates.create(live_app.engine, USER, TemplateForm(name, "gym"))
    ids = [e.id for e in exercises.list_exercises(live_app.engine, USER)]
    fixed = templates.add_slot(live_app.engine, USER, created, kind="exercise", exercise_id=ids[0])
    menu = templates.add_slot(live_app.engine, USER, created, kind="menu", exercise_id=ids[1], label="Tirage")
    templates.add_option(live_app.engine, USER, created, menu, ids[2])
    return created, fixed, menu


def test_header_takes_two_rows_on_the_phone_without_overflow(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    created, _, _ = fresh_template(live_app)
    for path in ("/seances-types", "/seances-types/nouvelle", f"/seances-types/{created}", "/exercices"):
        page.goto(live_app.url + path)
        brand = page.locator(".brand").bounding_box()
        nav = page.locator(".site-nav").bounding_box()
        assert brand is not None and nav is not None
        width = page.viewport_size["width"] if page.viewport_size else 0
        if width < 640:
            assert nav["y"] >= brand["y"] + brand["height"] - 1, path
            assert nav["x"] + nav["width"] <= width, path
        else:
            assert abs(nav["y"] - brand["y"]) < brand["height"], path  # one row
        links = page.locator(".site-nav__list a")
        tops = {round(links.nth(i).bounding_box()["y"]) for i in range(links.count())}  # type: ignore[index]
        assert len(tops) == 1, path  # the three links share one line
        assert_clean(watched)


def test_refused_create_marks_the_name_and_focuses_it(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    page.goto(live_app.url + "/seances-types/nouvelle")
    page.locator("#seance-nom").fill("salle a — squat & poussée horizontale")
    page.locator("#seance-lieu-gym").check()
    page.get_by_role("button", name=TEXT("template.create")).click()
    expect(page.locator("#seance-nom-erreur")).to_have_text(TEXT("catalog.error.template_name_taken"))
    expect(page.locator("#seance-nom")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#seance-nom")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(TEXT("catalog.error.template_name_taken"))
    assert_clean(watched)


def test_failed_create_keeps_the_form(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    page.goto(live_app.url + "/seances-types/nouvelle")
    page.route("**/seances-types", fail)
    page.locator("#seance-nom").fill("Jamais créée")
    page.locator("#seance-lieu-home").check()
    page.get_by_role("button", name=TEXT("template.create")).click()
    expect(page.locator("form [data-request-status]").first).to_have_text(TEXT("error.not_saved"))
    expect(page.locator("#seance-nom")).to_have_value("Jamais créée")
    expect(page.locator("#seance-nom")).to_be_focused()
    assert page.url.endswith("/seances-types/nouvelle")
    assert all(t.draft.name != "Jamais créée" for t in templates.list_templates(live_app.engine, USER))


def test_failed_slot_save_keeps_the_typed_target(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    created, fixed, _ = fresh_template(live_app)
    page.goto(f"{live_app.url}/seances-types/{created}")
    page.locator(f"#bloc-{fixed}-modifier").click()
    page.route(f"**/blocs/{fixed}", fail)
    page.locator(f"#bloc-{fixed}-series").fill("5")
    page.locator(f"#bloc-{fixed}-reps").fill("5")
    page.locator(f"#bloc-{fixed}-formulaire").get_by_role("button", name=TEXT("action.save")).click()
    status = page.locator(f"#bloc-{fixed}-formulaire > [data-request-status]")
    expect(status).to_have_text(TEXT("error.not_saved"))
    expect(page.locator(f"#bloc-{fixed}-series")).to_have_value("5")
    expect(page.locator(f"#bloc-{fixed}-exercice")).to_be_focused()  # first visible field
    page.unroute(f"**/blocs/{fixed}")
    page.locator(f"#bloc-{fixed}-reps").fill("10-8")
    page.locator(f"#bloc-{fixed}-formulaire").get_by_role("button", name=TEXT("action.save")).click()
    expect(page.locator(f"#bloc-{fixed}-reps-erreur")).to_have_text(TEXT("catalog.error.target_reps_order"))
    expect(page.locator(f"#bloc-{fixed}-reps")).to_be_focused()
    expect(page.locator(f"#bloc-{fixed}-formulaire > [data-request-status]")).to_have_text("")
    assert_clean(watched)


def test_failed_option_actions_keep_focus_on_their_trigger(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    created, _, menu = fresh_template(live_app)
    page.goto(f"{live_app.url}/seances-types/{created}")
    page.locator(f"#bloc-{menu}-modifier").click()
    options = templates.get_detail(live_app.engine, USER, created).slot(menu).options
    page.route("**/options/**", fail)
    remove = page.locator(f"#option-{options[0].id}-retirer")
    remove.click()
    scope = page.locator(f"#bloc-{menu} .menu-options > [data-request-status]")
    expect(scope).to_have_text(TEXT("error.not_saved"))
    expect(remove).to_be_focused()
    down = page.locator(f"#option-{options[0].id}-descendre")
    down.click()
    expect(down).to_be_focused()
    assert len(templates.get_detail(live_app.engine, USER, created).slot(menu).options) == 2
    page.unroute("**/options/**")
    remove.click()
    expect(page.locator(".option")).to_have_count(1)
    expect(page.locator(f"#bloc-{menu}-option-ajout")).to_be_focused()
    expect(page.locator("#annonce")).to_have_text(
        TEXT("template.announce_option_removed", name=options[0].exercise.name)
    )
    assert_clean(watched)


def test_archived_template_and_exercise_states(watched: Watched, live_app: LiveApp) -> None:
    page = watched.page
    created, fixed, _ = fresh_template(live_app)
    name = f"Archivable {next(_COUNTER)}"
    gone = exercises.create(live_app.engine, USER, ExerciseForm(name, "strength", "gym"))
    templates.update_slot(
        live_app.engine,
        USER,
        created,
        fixed,
        templates.SlotForm(exercise_id=gone),
    )
    exercises.set_archived(live_app.engine, USER, gone, datetime(2026, 11, 3, tzinfo=UTC))
    page.goto(f"{live_app.url}/seances-types/{created}")
    row = page.locator(f"#bloc-{fixed}")
    expect(row.locator(".tag")).to_have_text(TEXT("tag.archived_m"))
    expect(row.locator(".slot__skipped")).to_have_text(TEXT("template.slot_skipped_exercise"))
    page.get_by_role("button", name=TEXT("action.archive")).click()
    expect(page.locator("#seance-type-etat .tag")).to_have_text(TEXT("tag.archived_f"))
    row.locator("summary").click()
    page.locator(f"#bloc-{fixed}-series").fill("3")
    row.get_by_role("button", name=TEXT("action.save")).click()
    expect(page.locator("#annonce")).to_have_text(TEXT("status.saved"))  # archived stays editable
    expect(page.locator(f"#bloc-{fixed}-modifier")).to_be_focused()
    assert_clean(watched)
