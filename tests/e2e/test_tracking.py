"""L5 in real browsers (roadmap L5 "Done when", D-071, docs/ui-spec.md "L5 — …"): the chart is
ready in under 1 s on one year of simulated history with no CSP violation, no `<style>` element
and no external request; the chart's fallback when its JSON fails; the L5 pages at 360 / 1280 px
in light and dark; and the flows: correct a set of a closed session and see the record change,
delete a session and see it leave the history, enter a measured 1RM and change the formula
(WebKit and Chromium; an engine not installed is skipped)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from conftest import LiveApp, _served, pairing_code
from playwright.sync_api import Browser, ConsoleMessage, Page, Request, Route, expect
from support.history import build

from rack_overflow.domain.users import SINGLE_USER_ID as USER
from rack_overflow.services import devices, exercises, history, seed, sessions
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.auth import COOKIE_NAME
from rack_overflow.web.locale import load_catalog

pytestmark = pytest.mark.browser

TEXT = load_catalog(CATALOG).text
NBSP = "\u00a0"
PHONE = {"width": 360, "height": 640}
DESKTOP = {"width": 1280, "height": 900}
TARGET_MIN = 48
CHART_LIMIT_MS = 1000
VIOLATIONS = """
window.__violations = [];
document.addEventListener('securitypolicyviolation', (e) => {
  window.__violations.push(e.violatedDirective + ' ' + e.blockedURI);
});
"""


class Watched:
    """A paired page: CSP violations, console errors and foreign requests are recorded."""

    def __init__(self, page: Page, origin: str) -> None:
        self.page = page
        self.origin = origin
        self.console: list[str] = []
        self.foreign: list[str] = []
        page.add_init_script(VIOLATIONS)
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

    def goto(self, path: str) -> None:
        self.page.goto(self.origin + path, wait_until="load")

    def check_clean(self) -> None:
        assert self.foreign == []
        assert self.page.evaluate("window.__violations") == []
        assert not [text for text in self.console if "Content Security Policy" in text or "Refused" in text]
        assert self.page.evaluate("document.querySelectorAll('style').length") == 0
        overflow = self.page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 0


def watched_page(
    browser: Browser, app: LiveApp, viewport: dict[str, int], scheme: str = "light"
) -> Iterator[Watched]:
    token = devices.pair(
        app.engine, pairing_code(app, f"l5-{id(browser)}-{datetime.now(UTC).timestamp()}"), datetime.now(UTC)
    ).token
    context = browser.new_context(viewport=viewport, color_scheme=scheme)  # type: ignore[arg-type]
    context.add_cookies(
        [
            {
                "name": COOKIE_NAME,
                "value": token or "",
                "url": app.url + "/",
                "httpOnly": True,
                "sameSite": "Strict",
            }
        ]
    )
    yield Watched(context.new_page(), app.url)
    context.close()


# --- one year of history


YEAR: dict[str, int] = {}


@pytest.fixture(scope="module")
def year_app(browser: Browser, tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveApp]:
    """A live app holding the shared one-year history (D-071), one per engine."""
    del browser

    def prepare(engine: object) -> None:
        built = build(engine, tracking=True)  # type: ignore[arg-type]
        YEAR.update(squat=built.exercise_ids[0], run=built.cardio_id)

    yield from _served(tmp_path_factory.mktemp("year"), prepare)


@pytest.fixture
def year_phone(browser: Browser, year_app: LiveApp) -> Iterator[Watched]:
    yield from watched_page(browser, year_app, PHONE)


def test_chart_ready_under_one_second_on_a_year(year_phone: Watched) -> None:
    for key in ("squat", "run"):
        year_phone.goto(f"/progression/{YEAR[key]}")
        canvas = year_phone.page.locator("canvas[data-chart-src]")
        expect(canvas).to_have_attribute("data-chart-state", "ready", timeout=5000)
        elapsed = float(canvas.get_attribute("data-chart-ms") or "inf")
        assert elapsed < CHART_LIMIT_MS, f"{key}: chart ready after {elapsed} ms"
        expect(year_phone.page.locator(".chart")).to_be_visible()
        expect(year_phone.page.locator("[data-chart-error]")).to_be_hidden()
        box = canvas.bounding_box()
        assert box is not None and box["height"] > 200 and box["width"] > 300
        year_phone.check_clean()


def test_chart_falls_back_when_its_json_fails(year_phone: Watched) -> None:
    page = year_phone.page
    page.route("**/api/progression/**", lambda route: route.abort())
    year_phone.goto(f"/progression/{YEAR['squat']}")
    canvas = page.locator("canvas[data-chart-src]")
    expect(canvas).to_have_attribute("data-chart-state", "error")
    expect(page.locator("[data-chart-error]")).to_have_text(TEXT("progress.chart_error"))
    expect(page.locator(".chart")).to_be_hidden()
    page.get_by_text(TEXT("progress.data_toggle")).click()
    expect(page.locator(".chart-data .data-table tbody tr").first).to_be_visible()


CHART_COLOUR = """() => {
    const chart = Chart.getChart(document.querySelector('canvas[data-chart-src]'));
    const token = getComputedStyle(document.documentElement).getPropertyValue('--chart-1').trim();
    return [chart.data.datasets[0].borderColor, token];
}"""


def test_chart_colours_follow_the_colour_scheme(year_phone: Watched) -> None:
    page = year_phone.page
    year_phone.goto(f"/progression/{YEAR['squat']}")
    expect(page.locator("canvas[data-chart-src]")).to_have_attribute("data-chart-state", "ready")
    light, light_token = page.evaluate(CHART_COLOUR)
    assert light == light_token
    page.emulate_media(color_scheme="dark")
    page.wait_for_function(
        "(before) => Chart.getChart(document.querySelector('canvas[data-chart-src]'))"
        ".data.datasets[0].borderColor !== before",
        arg=light,
    )
    dark, dark_token = page.evaluate(CHART_COLOUR)
    assert dark == dark_token and dark != light
    year_phone.check_clean()


def test_chart_data_tables_fit_the_phone(year_phone: Watched) -> None:
    page = year_phone.page
    for key in ("squat", "run"):
        year_phone.goto(f"/progression/{YEAR[key]}")
        page.get_by_text(TEXT("progress.data_toggle")).click()
        scroll = page.locator(".chart-data .data-table__scroll")
        widths = scroll.evaluate("(e) => [e.scrollWidth, e.clientWidth]")
        assert widths[0] <= widths[1], f"{key}: the data table scrolls ({widths})"


def _hold(engine: object) -> int:
    """A duration-only bodyweight exercise (« Planche ») held 1:09 then 1:36, a year apart."""
    plank = exercises.create(engine, USER, ExerciseForm("Planche latérale test", "bodyweight", "home"))  # type: ignore[arg-type]
    exercises.add_field(engine, USER, plank, core_quantity="duration")  # type: ignore[arg-type]
    detail = exercises.get_detail(engine, USER, plank)  # type: ignore[arg-type]
    reps = next(item.id for item in detail.fields if item.core_quantity == "reps")
    exercises.remove_field(engine, USER, plank, reps)  # type: ignore[arg-type]
    for days, held in ((400, "1:09"), (1, "1:36")):
        when = datetime.now(UTC) - timedelta(days=days)
        session_id = sessions.start(engine, USER, None, "home", when, UTC)  # type: ignore[arg-type]
        block = sessions.pick(engine, USER, session_id, None, plank).block  # type: ignore[arg-type]
        assert block is not None
        values = {"duration": held}
        sessions.confirm_set(engine, USER, session_id, block.id, "work", values, when)  # type: ignore[arg-type]
        sessions.close(engine, USER, session_id, when + timedelta(minutes=5))  # type: ignore[arg-type]
    return plank


def test_a_duration_chart_reads_clock_time(flow_phone: Watched, flow_app: LiveApp) -> None:
    plank = _hold(flow_app.engine)
    page = flow_phone.page
    flow_phone.goto(f"/progression/{plank}")
    expect(page.locator("canvas[data-chart-src]")).to_have_attribute("data-chart-state", "ready")
    chart = "Chart.getChart(document.querySelector('canvas[data-chart-src]'))"
    ticks = page.evaluate(f"() => {chart}.scales.y.ticks.map((tick) => tick.label)")
    assert ticks and all(re.fullmatch(r"\d+:\d\d", label) for label in ticks), ticks
    assert len(set(ticks)) == len(ticks)
    tooltip = page.evaluate(
        f"""() => {{
            const callbacks = {chart}.options.plugins.tooltip.callbacks;
            const item = {{dataset: {{label: 'x'}}, parsed: {{y: 96}}, formattedValue: '96', dataIndex: 0}};
            return [callbacks.label(item), callbacks.title([item])];
        }}"""
    )
    assert tooltip[0] == f"x{NBSP}: 1:36"
    assert re.fullmatch(r"\d\d/\d\d/\d{4}", tooltip[1])  # the year: the chart spans two years
    flow_phone.check_clean()


@pytest.mark.parametrize("viewport", [PHONE, DESKTOP], ids=["360px", "1280px"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_l5_pages_fit_and_load_clean(
    browser: Browser, year_app: LiveApp, viewport: dict[str, int], scheme: str
) -> None:
    page = history.history_page(year_app.engine, USER)
    closed = page.months[0].items[0].id  # the latest session of the year, closed
    for watched in watched_page(browser, year_app, viewport, scheme):
        for path in (
            "/historique",
            f"/seances/{closed}",
            "/progression",
            f"/progression/{YEAR['squat']}",
            "/reglages",
        ):
            watched.goto(path)
            if "progression/" in path:
                expect(watched.page.locator("canvas[data-chart-src]")).to_have_attribute(
                    "data-chart-state", "ready"
                )
            watched.check_clean()
            if viewport is PHONE:
                assert_targets(watched.page)
        if viewport is PHONE:
            header = watched.page.locator(".site-header").bounding_box()
            assert header is not None and header["height"] <= 3 * TARGET_MIN + 8


def assert_targets(page: Page) -> None:
    """Every visible control of the page is at least 48 x 48 px."""
    small = page.evaluate(
        """(minimum) => {
            const controls = 'main button, main .button, main .chip, main summary, main a';
            return [...document.querySelectorAll(controls)]
                .filter(e => e.getClientRects().length && !e.closest('details:not([open]) > :not(summary)'))
                .filter(e => !e.closest('.visually-hidden'))
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


# --- flows on a small history


FLOW: dict[str, int] = {}


def _flows(engine: object) -> None:
    seed.seed_catalog(engine, USER)  # type: ignore[arg-type]
    squat = next(
        e.id for e in exercises.list_exercises(engine, USER) if e.draft.name == "Squat au rack (barre)"
    )  # type: ignore[arg-type]
    start = datetime.now(UTC) - timedelta(days=10)
    ids = []
    for day, weight in ((0, "100"), (3, "102,5"), (6, "105")):
        when = start + timedelta(days=day)
        session_id = sessions.start(engine, USER, None, "gym", when, UTC)  # type: ignore[arg-type]
        block = sessions.pick(engine, USER, session_id, None, squat).block  # type: ignore[arg-type]
        assert block is not None
        for number in range(2):
            values = {"reps": "5", "weight": weight}
            sessions.confirm_set(
                engine, USER, session_id, block.id, "work", values, when + timedelta(minutes=number + 1)
            )  # type: ignore[arg-type]
        sessions.close(engine, USER, session_id, when + timedelta(hours=1))  # type: ignore[arg-type]
        ids.append(session_id)
    FLOW.update(squat=squat, first=ids[0], last=ids[-1])


@pytest.fixture(scope="module")
def flow_app(browser: Browser, tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveApp]:
    del browser
    yield from _served(tmp_path_factory.mktemp("flows"), _flows)


@pytest.fixture
def flow_phone(browser: Browser, flow_app: LiveApp) -> Iterator[Watched]:
    yield from watched_page(browser, flow_app, PHONE)


def test_correcting_a_closed_set_changes_the_record(flow_phone: Watched) -> None:
    page = flow_phone.page
    flow_phone.goto(f"/seances/{FLOW['last']}")
    first_set = page.locator(".set-row").first
    first_set.locator("summary").click()
    first_set.locator("input[name=weight]").fill("140")
    first_set.get_by_role("button", name=TEXT("action.save")).click()
    expect(page.locator("#annonce")).to_have_text(TEXT("session.announce_set_updated", n=1))
    expect(page.locator(".set-row").first).to_contain_text(f"140{NBSP}kg")
    expect(page.locator(".set-row").first.locator("summary")).to_be_focused()
    expect(page.locator("#seance-totaux")).to_contain_text(f"1225{NBSP}kg")
    flow_phone.goto(f"/progression/{FLOW['squat']}")
    records = page.locator("#records-reps").locator("xpath=..")
    expect(records).to_contain_text(f"140{NBSP}kg")
    flow_phone.check_clean()


def test_deleting_a_session_removes_it_from_the_history(flow_phone: Watched) -> None:
    page = flow_phone.page
    flow_phone.goto(f"/seances/{FLOW['first']}")
    page.get_by_role("button", name=TEXT("session.delete")).click()
    expect(page.locator("#seance-suppression-annuler")).to_be_focused()
    with page.expect_navigation(wait_until="load"):
        page.locator("#seance-supprimer-confirmer").click()
    assert page.url.endswith("/historique?supprimee=1")
    expect(page.get_by_text(TEXT("history.deleted_notice"))).to_be_visible()
    expect(page.locator(f'a[href="/seances/{FLOW["first"]}"]')).to_have_count(0)
    flow_phone.check_clean()


def test_measured_rm_wins_and_the_formula_changes_only_the_estimate(flow_phone: Watched) -> None:
    page = flow_phone.page
    flow_phone.goto(f"/progression/{FLOW['squat']}")
    page.locator("#rm-saisir").click()
    page.locator("label.chip", has_text="1").first.click()
    page.locator("#rm-weight").fill("150")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    page.locator("#rm-date").fill(yesterday)
    page.get_by_role("button", name=TEXT("rm.submit")).click()
    expect(page.locator("#annonce")).to_have_text(TEXT("rm.saved", n=1, value=f"150{NBSP}kg"))
    first_row = page.locator(".rm-row").first
    expect(first_row.locator(".rm-row__value")).to_have_text(f"150{NBSP}kg")
    expect(first_row).to_contain_text(TEXT("rm.estimate_beside", formula="Epley", value=""))
    estimate_before = first_row.locator(".rm-row__line").nth(1).inner_text()
    page.get_by_role("link", name=TEXT("rm.formula_change")).click()
    page.wait_for_load_state("load")
    page.locator('label[for="formule-brzycki"]').click()
    expect(page.locator("#annonce")).to_have_text(TEXT("settings.formula_saved", formula="Brzycki"))
    flow_phone.goto(f"/progression/{FLOW['squat']}")
    first_row = page.locator(".rm-row").first
    expect(first_row.locator(".rm-row__value")).to_have_text(f"150{NBSP}kg")
    estimate_after = first_row.locator(".rm-row__line").nth(1).inner_text()
    assert "Brzycki" in estimate_after and estimate_after != estimate_before
    flow_phone.check_clean()
