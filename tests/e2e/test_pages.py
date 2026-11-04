"""L1a pages in real browsers: 360 / 1280 px, light / dark, same-origin only, CSP clean."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, ConsoleMessage, Page, Request, Route

pytestmark = pytest.mark.browser

WIDTHS = (360, 1280)
SCHEMES = ("light", "dark")
BACKGROUNDS = {"light": "rgb(255, 255, 255)", "dark": "rgb(19, 21, 24)"}
PATHS = {"/": 200, "/introuvable": 404}


class Watched:
    """A page plus what it tried to load outside the origin and the console errors it logged."""

    def __init__(self, page: Page, origin: str, scheme: str) -> None:
        self.page = page
        self.scheme = scheme
        self.foreign: list[str] = []
        self.console: list[str] = []
        page.on("console", self._console)
        page.route("**/*", self._route)
        self._origin = origin

    def _console(self, message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"}:
            self.console.append(message.text)

    def _route(self, route: Route, request: Request) -> None:
        if request.url.startswith(self._origin) or request.url.startswith("data:"):
            route.continue_()
        else:
            self.foreign.append(request.url)
            route.abort()


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


@pytest.mark.parametrize("path", sorted(PATHS))
def test_page_loads_clean(watched: Watched, live_server: str, path: str, tmp_path: Path) -> None:
    page = watched.page
    response = page.goto(live_server + path)
    assert response is not None and response.status == PATHS[path]
    page.wait_for_load_state("load")
    assert watched.foreign == []
    assert not [text for text in watched.console if "Content Security Policy" in text or "Refused" in text]
    inline = page.evaluate(
        """() => ({
            styles: document.querySelectorAll('style').length,
            inlineScripts: [...document.scripts].filter(s => !s.src).length,
            styleAttributes: document.querySelectorAll('[style]').length,
        })"""
    )
    assert inline == {"styles": 0, "inlineScripts": 0, "styleAttributes": 0}
    # after the audit: the screenshot leaves `style=""` on inputs (Playwright hides their caret)
    page.screenshot(path=str(tmp_path / "page.png"), full_page=True)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0
    background = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert background == BACKGROUNDS[watched.scheme]


def test_htmx_is_loaded_and_sends_json(watched: Watched, live_server: str) -> None:
    page = watched.page
    page.goto(live_server + "/")
    page.wait_for_function("() => typeof window.htmx !== 'undefined'")
    with page.expect_request(lambda request: request.method == "POST") as captured:
        page.evaluate("() => htmx.ajax('POST', '/', {source: document.body, values: {reps: 5}})")
    request = captured.value
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.post_data or "{}") == {"reps": "5"}  # form values travel as strings
