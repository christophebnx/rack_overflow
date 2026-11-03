"""L4 in real browsers (roadmap L4 "Done when", docs/ui-spec.md "L4 — Tap counts"): a full « Salle
A » session logged at 360 x 640 with every tap counted and no keyboard in the nominal path, the
failure display of a ✓, and the L4 pages at 360 / 1280 px in light and dark (WebKit and Chromium;
an engine not installed is skipped)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import LiveApp, pairing_code
from playwright.sync_api import Browser, ConsoleMessage, Locator, Page, Request, Route, expect

from rack_overflow.domain.users import SINGLE_USER_ID as USER
from rack_overflow.services import devices, exercises, sessions, templates, variables
from rack_overflow.services.exercises import FieldForm
from rack_overflow.services.sessions import SessionView
from rack_overflow.services.variables import VariableForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.auth import COOKIE_NAME
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser

TEXT = load_catalog(CATALOG).text
PHONE = {"width": 360, "height": 640}
TARGET_MIN = 48
EARLIER = datetime.now(UTC) - timedelta(days=3)
BRUSSELS = ZoneInfo("Europe/Brussels")


class KeyboardUsedError(AssertionError):
    """The nominal path used the keyboard."""


class Taps:
    """Counts every tap of a scenario; typing fails unless the step is a correction."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.count = 0
        self._keyboard = False

    def tap(self, locator: Locator) -> None:
        """One tap on `locator`."""
        locator.click()
        self.count += 1

    def fill(self, locator: Locator, text: str) -> None:
        """Typing: allowed only inside `keyboard()` (a correction, not the nominal path)."""
        if not self._keyboard:
            raise KeyboardUsedError(f"keyboard in the nominal path: {text!r}")
        locator.fill(text)

    @contextlib.contextmanager
    def keyboard(self) -> Iterator[None]:
        """A correction step where the keyboard is accepted (edit a set)."""
        self._keyboard = True
        try:
            yield
        finally:
            self._keyboard = False

    @contextlib.contextmanager
    def counted(self, limit: int) -> Iterator[None]:
        """Assert the taps of one action stay within `limit`."""
        before = self.count
        yield
        used = self.count - before
        assert used <= limit, f"{used} taps, at most {limit}"


def _name(engine: object, name: str) -> int:
    return next(e.id for e in exercises.list_exercises(engine, USER) if e.draft.name == name)  # type: ignore[arg-type]


def _history(engine: object) -> int:
    """One earlier « Salle A » session at the gym: sets on every slot, settings on the leg press."""
    press = _name(engine, "Presse à cuisses")
    seat = variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting"))  # type: ignore[arg-type]
    field_id = exercises.add_field(engine, USER, press, variable_id=seat)  # type: ignore[arg-type]
    exercises.update_field(engine, USER, press, field_id, FieldForm(discrete_values="1 2 3 4 5 6 7 8 9 10"))  # type: ignore[arg-type]
    salle_a = next(t.id for t in templates.list_templates(engine, USER) if t.draft.name.startswith("Salle A"))  # type: ignore[arg-type]
    session_id = sessions.start(engine, USER, salle_a, "gym", EARLIER, BRUSSELS)  # type: ignore[arg-type]
    plan = sessions.show(engine, USER, session_id)  # type: ignore[arg-type]
    assert isinstance(plan, SessionView)
    picks = {
        "Tirage horizontal": "Rowing barre au rack",
        "Jambes unilatéral": "Presse à cuisses",
        "Gainage": "Planche",
    }
    for slot_id, menu in plan.menus.items():
        option = next(o.id for o in menu.options if o.name == picks[menu.label])
        sessions.pick(engine, USER, session_id, slot_id, option)  # type: ignore[arg-type]
    plan = sessions.show(engine, USER, session_id)  # type: ignore[arg-type]
    assert isinstance(plan, SessionView)
    values = {
        "Squat au rack (barre)": [("warmup", {"reps": "10", "weight": "40"})]
        + [("work", {"reps": "8", "weight": "60"})] * 3,
        "Développé couché (barre)": [("work", {"reps": "8", "weight": "50"})] * 3,
        "Rowing barre au rack": [("work", {"reps": "10", "weight": "45"})] * 3,
        "Presse à cuisses": [("work", {"reps": "10", "weight": "100"})] * 3,
        "Curl barre EZ": [("work", {"reps": "12", "weight": "25"})] * 3,
        "Planche": [("work", {"duration": "0:45"})] * 3,
    }
    moment = EARLIER
    for row_id, card in plan.cards.items():
        for kind, raw in values[card.exercise.name]:
            moment += timedelta(minutes=2)
            sessions.confirm_set(engine, USER, session_id, row_id, kind, raw, moment)  # type: ignore[arg-type]
        if card.exercise.id == press:
            sessions.save_settings(engine, USER, session_id, row_id, {f"var_{seat}": "4"})  # type: ignore[arg-type]
    sessions.close(engine, USER, session_id, moment + timedelta(minutes=5))  # type: ignore[arg-type]
    return session_id


EARLIER_SESSION: dict[str, int] = {}


@pytest.fixture(scope="module")
def history(seeded_live_app: LiveApp) -> LiveApp:
    """The seeded app with the earlier session (once per module)."""
    EARLIER_SESSION["id"] = _history(seeded_live_app.engine)
    return seeded_live_app


class Watched:
    """A phone page: CSP violations and foreign requests are recorded; `origin` is the app's
    base URL."""

    def __init__(self, page: Page, origin: str) -> None:
        self.page = page
        self.console: list[str] = []
        self.foreign: list[str] = []
        self.origin = origin
        page.on("console", self._console)
        page.route("**/*", self._route)

    def _console(self, message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"}:
            self.console.append(message.text)

    def _route(self, route: Route, request: Request) -> None:
        if request.url.startswith(self.origin) or request.url.startswith("data:"):
            route.fallback()
        else:
            self.foreign.append(request.url)
            route.abort()

    def check_clean(self) -> None:
        assert self.foreign == []
        assert not [text for text in self.console if "Content Security Policy" in text or "Refused" in text]
        overflow = self.page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0


@pytest.fixture
def phone(browser: Browser, history: LiveApp) -> Iterator[Watched]:
    """A paired 360 x 640 page on the seeded app."""
    token = devices.pair(
        history.engine,
        pairing_code(history, f"phone-{id(browser)}-{datetime.now(UTC).timestamp()}"),
        datetime.now(UTC),
    ).token
    found = sessions.start_page(history.engine, USER).open
    if found is not None:  # a flow left its session open (it failed): start from home again
        sessions.close(history.engine, USER, found.session.id, datetime.now(UTC))
    context = browser.new_context(viewport=PHONE, color_scheme="light")
    context.add_cookies(
        [
            {
                "name": COOKIE_NAME,
                "value": token or "",
                "url": history.url + "/",
                "httpOnly": True,
                "sameSite": "Strict",
            }
        ]
    )
    yield Watched(context.new_page(), history.url)
    context.close()


def confirm_button(page: Page) -> Locator:
    return page.locator("button.button--confirm")


def assert_confirm_in_thumb_zone(page: Page) -> None:
    """After a ✓ the next ✓ sits in the lower half of the 640 px viewport (the swap's `show:`
    scrolls the block's action bar to the bottom)."""
    expect(confirm_button(page)).to_be_enabled()
    page.wait_for_function(
        """(height) => {
            const box = document.querySelector('button.button--confirm').getBoundingClientRect();
            return box.top >= height / 2 - 1 && box.bottom <= height + 1;
        }""",
        arg=PHONE["height"],
        timeout=2000,
    )


def assert_targets(page: Page) -> None:
    """Every visible control of the page is at least 48 x 48 px."""
    page.wait_for_load_state("load")  # stylesheets applied
    small = page.evaluate(
        """(minimum) => {
            const controls = 'main button, main .button, main .chip, main summary, main a.row, '
                + 'main input:not([type=radio]):not([type=hidden])';
            return [...document.querySelectorAll(controls)]
                .filter(e => e.getClientRects().length && !e.closest('details:not([open]) > :not(summary)'))
                .map(e => {
                    const box = e.getBoundingClientRect();
                    const name = e.id || e.textContent.trim().slice(0, 30);
                    return [name, Math.round(box.width), Math.round(box.height)];
                })
                .filter(([, w, h]) => w < minimum || h < minimum);
        }""",
        TARGET_MIN,
    )
    assert small == []


def wait_settled(page: Page) -> None:
    page.wait_for_load_state("networkidle")


def current_block(page: Page) -> Locator:
    return page.locator('li[aria-current="step"] > .session-block')


def test_full_salle_a_session_in_counted_taps(phone: Watched) -> None:
    page, taps = phone.page, Taps(phone.page)
    page.goto(phone.origin + "/")
    assert_targets(page)
    phone.check_clean()

    # start « Salle A », the place preselected: 1 tap (≤ 3)
    with taps.counted(1):
        taps.tap(page.get_by_role("button", name="Salle A"))
    page.wait_for_url("**/seances/*")
    session_url = page.url
    expect(current_block(page).locator("h2")).to_have_text("Squat au rack (barre)")
    assert_targets(page)
    phone.check_clean()

    # Squat: prefilled from the last performance (warm-up 10 x 40 kg), each unchanged set in 1 tap
    expect(page.locator('input[name="type"][value="warmup"]')).to_be_checked()
    for _ in range(2):
        with taps.counted(1):
            taps.tap(confirm_button(page))
        assert_confirm_in_thumb_zone(page)
    # a modified set: « + » on the load, then ✓ (2 taps): heavier than every earlier set → ⭐
    with taps.counted(2):
        taps.tap(page.locator('[id$="-weight-plus"]'))
        expect(page.locator('form.set-form input[name="weight"]')).to_have_value("62,5")
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)
    expect(current_block(page).locator(".set-row").last).to_contain_text(TEXT("session.record"))
    # two steps then ✓: 3 taps
    with taps.counted(3):
        taps.tap(page.locator('[id$="-reps-plus"]'))
        expect(page.locator('form.set-form input[name="reps"]')).to_have_value("9")
        taps.tap(page.locator('[id$="-reps-plus"]'))
        expect(page.locator('form.set-form input[name="reps"]')).to_have_value("10")
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)
    expect(current_block(page).locator(".set-row")).to_have_count(4)

    # next exercise: 1 tap; a warm-up set: type then ✓ (2 taps)
    with taps.counted(1):
        taps.tap(page.get_by_role("link", name=TEXT("session.next_item", name="Développé couché (barre)")))
    expect(current_block(page).locator("h2")).to_have_text("Développé couché (barre)")
    with taps.counted(2):
        taps.tap(page.locator("label.chip", has_text=TEXT("session.set_type.warmup")))
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)
    expect(current_block(page).locator(".set-row").first).to_contain_text(TEXT("session.set_type.warmup"))
    with taps.counted(1):
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)

    # a pending menu: « Suivant », then the option (2 taps), then ✓
    with taps.counted(2):
        taps.tap(page.get_by_role("link", name=TEXT("session.next_item", name="Tirage horizontal")))
        taps.tap(page.get_by_role("button", name="Rowing barre au rack"))
    expect(current_block(page).locator("h2")).to_have_text("Rowing barre au rack")
    expect(page.locator("#annonce")).to_have_text(
        TEXT("session.announce_picked", name="Rowing barre au rack")
    )
    with taps.counted(1):
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)

    # « Jambes unilatéral »: pick the leg press; its settings are prefilled from the last session
    with taps.counted(2):
        taps.tap(page.get_by_role("link", name=TEXT("session.next_item", name="Jambes unilatéral")))
        taps.tap(page.get_by_role("button", name="Presse à cuisses"))
    settings = current_block(page).locator(".session-settings__summary").first
    expect(settings).to_contain_text("Siège\u00a04")
    # change a setting chip: summary, chip (2 taps), saved at once
    with taps.counted(2):
        taps.tap(settings)
        taps.tap(current_block(page).locator(".settings-form label.chip", has_text="5").first)
    expect(current_block(page).locator(".settings-form .form-status")).to_have_text(
        TEXT("session.settings_saved")
    )
    expect(settings).to_contain_text("Siège\u00a05")
    with taps.counted(1):
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)

    # reload mid-session: the same state, current = the row of the latest set
    page.reload()
    expect(current_block(page).locator("h2")).to_have_text("Presse à cuisses")
    expect(current_block(page).locator(".set-row")).to_have_count(1)

    # edit a set (keyboard accepted: a correction), then delete one (2 taps)
    with taps.keyboard():
        taps.tap(current_block(page).locator(".set-row__edit > summary").first)
        taps.fill(current_block(page).locator(".set-edit input[name='reps']").first, "12")
        taps.tap(current_block(page).get_by_role("button", name=TEXT("action.save")))
    expect(current_block(page).locator(".set-row").first).to_contain_text("12\u00a0\u00d7")
    expect(page.locator("#annonce")).to_have_text(TEXT("session.announce_set_updated", n=1))
    with taps.counted(1):
        taps.tap(confirm_button(page))
    expect(current_block(page).locator(".set-row")).to_have_count(2)
    assert_confirm_in_thumb_zone(page)
    with taps.counted(2):
        taps.tap(current_block(page).locator(".set-row__edit > summary").last)
        taps.tap(current_block(page).get_by_role("button", name=TEXT("session.delete_set")).last)
    expect(current_block(page).locator(".set-row")).to_have_count(1)
    expect(page.locator("#annonce")).to_have_text(TEXT("session.announce_set_deleted", n=2))

    # curl, then the « Gainage » menu with the plank (duration from the last performance)
    with taps.counted(1):
        taps.tap(page.get_by_role("link", name=TEXT("session.next_item", name="Curl barre EZ")))
    with taps.counted(1):
        taps.tap(confirm_button(page))
    with taps.counted(2):
        taps.tap(page.get_by_role("link", name=TEXT("session.next_item", name="Gainage")))
        taps.tap(page.get_by_role("button", name="Planche"))
    expect(page.locator('form.set-form input[name="duration"]')).to_have_value("0:45")
    with taps.counted(1):
        taps.tap(confirm_button(page))
    assert_targets(page)
    phone.check_clean()

    # a failed ✓: values kept, « Non enregistré, réessayer », the ✓ disabled during the request
    page.route("**/seances/*/series", lambda route: route.abort())
    taps.tap(page.locator('[id$="-duration-plus"]'))
    expect(page.locator('form.set-form input[name="duration"]')).to_have_value("1:00")
    page.evaluate(
        """() => {
            const button = document.querySelector('button.button--confirm');
            window.confirmDisabled = false;
            new MutationObserver((records) => {
                if (records.some((record) => record.oldValue === null)) window.confirmDisabled = true;
            }).observe(button, {attributes: true, attributeFilter: ['disabled'], attributeOldValue: true});
        }"""
    )
    taps.tap(confirm_button(page))
    status = current_block(page).locator(".set-form .form-status")
    expect(status).to_have_text(TEXT("error.not_saved"))
    expect(confirm_button(page)).to_be_enabled()
    expect(page.locator('form.set-form input[name="duration"]')).to_have_value("1:00")
    assert page.evaluate("() => window.confirmDisabled") is True
    page.unroute("**/seances/*/series")
    expect(current_block(page).locator(".set-row")).to_have_count(1)

    # close from the last exercise: « Terminer la séance », « Terminer » (2 taps)
    with taps.counted(2):
        taps.tap(current_block(page).get_by_role("button", name=TEXT("session.close")))
        taps.tap(page.get_by_role("button", name=TEXT("session.close_confirm"), exact=True))
    page.wait_for_url(session_url)
    expect(page.locator("h1")).to_have_text("Salle A — Squat & poussée horizontale")
    expect(page.locator(".summary-totals")).to_contain_text(TEXT("session.total_volume"))
    expect(page.locator("main")).to_contain_text(TEXT("session.summary.records", count=1))
    assert_targets(page)
    phone.check_clean()


def test_other_place_discrete_load_recent_exercise_and_resume(phone: Watched) -> None:
    page, taps = phone.page, Taps(phone.page)
    page.goto(phone.origin + "/")
    with taps.counted(2):  # the other place, then its template (≤ 3)
        taps.tap(page.locator("label.chip", has_text=TEXT("exercise.location.home")))
        taps.tap(page.get_by_role("button", name="Maison"))
    page.wait_for_url("**/seances/*")
    expect(current_block(page).locator("h2")).to_have_text("Kettlebell swing")
    # a discrete load: chip, then ✓ (2 taps; reps from the target, no keyboard)
    with taps.counted(2):
        taps.tap(current_block(page).locator("form.set-form label.chip", has_text="16"))
        taps.tap(confirm_button(page))
    assert_confirm_in_thumb_zone(page)
    expect(current_block(page).locator(".set-row")).to_have_count(1)
    # add a recent exercise: « Ajouter un exercice », then the result (2 taps)
    with taps.counted(2):
        taps.tap(page.locator("#ajout > summary"))
        taps.tap(page.locator("#ajout-resultats button", has_text="Squat au rack (barre)").first)
    expect(current_block(page).locator("h2")).to_have_text("Squat au rack (barre)")
    added = TEXT("session.announce_added", name="Squat au rack (barre)")
    expect(page.locator("#annonce")).to_have_text(added)
    expect(page.locator("#ajout")).not_to_have_attribute("open", "")
    # resume from home: 1 tap, current = the row of the latest set
    page.goto(phone.origin + "/")
    with taps.counted(1):
        taps.tap(page.get_by_role("link", name=TEXT("home.resume")))
    expect(current_block(page).locator("h2")).to_have_text("Kettlebell swing")
    taps.tap(page.locator("#terminer"))
    taps.tap(page.get_by_role("button", name=TEXT("session.close_confirm"), exact=True))
    expect(page.locator(".summary-totals")).to_be_visible()
    assert_targets(page)
    phone.check_clean()


@pytest.mark.parametrize("width", [360, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_l4_pages_are_clean(browser: Browser, history: LiveApp, width: int, scheme: str) -> None:
    token = devices.pair(
        history.engine, pairing_code(history, f"pages-{width}-{scheme}-{id(browser)}"), datetime.now(UTC)
    ).token
    context = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme)
    context.add_cookies(
        [
            {
                "name": COOKIE_NAME,
                "value": token or "",
                "url": history.url + "/",
                "httpOnly": True,
                "sameSite": "Strict",
            }
        ]
    )
    watched = Watched(context.new_page(), history.url)
    try:
        page = watched.page
        page.goto(history.url + "/")
        watched.check_clean()
        page.goto(f"{history.url}/seances/{EARLIER_SESSION['id']}")
        expect(page.locator(".summary-totals")).to_be_visible()
        watched.check_clean()
        assert page.evaluate("() => document.querySelectorAll('[style], style').length") == 0
    finally:
        context.close()
