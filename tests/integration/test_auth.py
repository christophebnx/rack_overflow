"""Device authentication and the pairing page through the TestClient (D-049, D-050)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from starlette.routing import Mount

from rack_overflow.config import Settings
from rack_overflow.domain import devices as rules
from rack_overflow.services import devices
from rack_overflow.storage import schema
from rack_overflow.web.app import CATALOG, create_app
from rack_overflow.web.auth import COOKIE_NAME, PUBLIC_PATHS, cleared_cookie, device_cookie
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.security import CONTENT_SECURITY_POLICY

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
PAGE = {"accept": "text/html,application/xhtml+xml"}
JSON = {"content-type": "application/json"}
HTMX = {**JSON, "HX-Request": "true", "accept": "text/html"}
MAX_AGE = 400 * 24 * 3600
TEXT = load_catalog(CATALOG).text


class Clock:
    """A settable clock injected into the app."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def _client(settings: Settings, engine: Engine, clock: Clock) -> TestClient:
    app = create_app(settings, engine, clock=clock, run_scheduler=False)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def web(settings: Settings, migrated_engine: Engine, clock: Clock) -> Iterator[TestClient]:
    """An unpaired client that does not follow redirects, on a settable clock."""
    with _client(settings, migrated_engine, clock) as client:
        yield client


def _code(engine: Engine, name: str = "iPhone") -> str:
    return devices.add_device(engine, name, NOW).code


def _pair(web: TestClient, engine: Engine) -> str:
    response = web.post("/appairage", headers=HTMX, json={"code": _code(engine)})
    assert response.status_code == 200
    return web.cookies[COOKIE_NAME]


def _set_cookies(response: object) -> list[str]:
    return response.headers.get_list("set-cookie")  # type: ignore[attr-defined]


def _assert_security_headers(response: object) -> None:
    headers = response.headers  # type: ignore[attr-defined]
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert headers["cache-control"] == "no-store"


# --- unpaired requests ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/nulle-part", "/appairage/x"])
def test_unpaired_navigation_is_sent_to_pairing(web: TestClient, path: str) -> None:
    response = web.get(path, headers=PAGE)
    assert response.status_code == 303
    assert response.headers["location"] == "/appairage"
    assert "set-cookie" not in response.headers
    _assert_security_headers(response)


def test_unpaired_htmx_request_gets_401_and_hx_redirect(web: TestClient) -> None:
    response = web.get("/", headers={**PAGE, "HX-Request": "true"})
    assert response.status_code == 401
    assert response.json() == {"error": "not_paired"}
    assert response.headers["hx-redirect"] == "/appairage"
    _assert_security_headers(response)


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_unpaired_json_request_gets_401_without_hx_redirect(web: TestClient, method: str) -> None:
    response = web.request(method, "/", headers=JSON, content=b"{}")
    assert response.status_code == 401
    assert response.json() == {"error": "not_paired"}
    assert "hx-redirect" not in response.headers


def test_unpaired_post_from_a_page_gets_the_error_page(web: TestClient) -> None:
    response = web.post("/", headers={**PAGE, **JSON}, content=b"{}")
    assert response.status_code == 401
    assert TEXT("error.not_paired") in response.text


def test_unpaired_form_post_is_refused_by_security_first(web: TestClient) -> None:
    response = web.post("/", data={"code": "1"})
    assert response.status_code == 415


def test_public_paths(web: TestClient) -> None:
    assert web.get("/appairage", headers=PAGE).status_code == 200
    assert web.get("/static/css/tokens.css").status_code == 200
    assert web.get("/static/absent.css").status_code == 404
    assert web.put("/appairage", headers=JSON, content=b"{}").status_code == 405


def test_static_requests_skip_the_database(web: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(devices, "authenticate", lambda *args: pytest.fail("authenticated"))
    web.cookies.set(COOKIE_NAME, "A" * rules.TOKEN_LENGTH)
    assert web.get("/static/css/tokens.css").status_code == 200


def _routes(routes: list[object]) -> Iterator[object]:
    """Every route, included routers flattened (none of them has a prefix)."""
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _routes(included.routes)
        else:
            yield route


def test_every_route_but_the_public_ones_is_protected(web: TestClient) -> None:
    routes = list(_routes(web.app.routes))  # type: ignore[attr-defined]
    assert {route.path for route in routes if isinstance(route, APIRoute)} >= {"/", "/appairage"}
    for route in routes:
        if isinstance(route, Mount):
            assert route.path == "/static"
            continue
        assert isinstance(route, APIRoute)
        if route.path in PUBLIC_PATHS:
            continue
        path = re.sub(r"\{[^}]+\}", "x", route.path)
        for method in route.methods:
            response = web.request(method, path, headers={**PAGE, **JSON}, content=b"{}")
            assert response.status_code in {303, 401}, (method, path)


def test_routes_added_later_are_protected(web: TestClient) -> None:
    router = APIRouter()

    @router.get("/plus-tard")
    def later() -> dict[str, str]:
        return {"ok": "yes"}

    web.app.include_router(router)  # type: ignore[attr-defined]
    assert web.get("/plus-tard", headers=JSON).status_code == 401


def test_database_failure_during_the_check_is_the_500_page(
    web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise sa.exc.OperationalError("SELECT", {}, Exception("disk"))

    monkeypatch.setattr(devices, "authenticate", broken)
    web.cookies.set(COOKIE_NAME, "A" * rules.TOKEN_LENGTH)
    response = web.get("/", headers=PAGE)
    assert response.status_code == 500
    assert "Erreur du serveur" in response.text
    _assert_security_headers(response)


# --- pairing ---------------------------------------------------------------------------------------


def test_pairing_page_renders_the_form(web: TestClient) -> None:
    response = web.get("/appairage", headers=PAGE)
    html = response.text
    assert f"<title>{TEXT('pairing.title')} · Rack Overflow</title>" in html
    assert 'hx-post="/appairage"' in html
    assert 'autocomplete="one-time-code"' in html
    assert 'aria-describedby="code-aide"' in html
    assert "aria-invalid" not in html
    assert "/static/css/pages/pairing.css" in html
    _assert_security_headers(response)


def test_pairing_sets_the_cookie_and_redirects_htmx_home(web: TestClient, migrated_engine: Engine) -> None:
    response = web.post("/appairage", headers=HTMX, json={"code": rules.format_code(_code(migrated_engine))})
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/"
    assert TEXT("pairing.paired") in response.text
    [cookie] = _set_cookies(response)
    token = web.cookies[COOKIE_NAME]
    assert cookie == f"rack_device={token}; Path=/; Max-Age={MAX_AGE}; HttpOnly; SameSite=Strict"
    assert "Secure" not in cookie and "Domain" not in cookie
    assert web.get("/", headers=PAGE).status_code == 200


def test_secure_cookie_with_https(settings: Settings, migrated_engine: Engine, clock: Clock) -> None:
    https = replace(settings, server=replace(settings.server, https=True))
    app = create_app(https, migrated_engine, clock=clock, run_scheduler=False)
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/appairage", headers=HTMX, json={"code": _code(migrated_engine)})
    [cookie] = _set_cookies(response)
    assert cookie.endswith("; HttpOnly; SameSite=Strict; Secure")


def test_cookie_values() -> None:
    assert (
        device_cookie("t", True)
        == f"rack_device=t; Path=/; Max-Age={MAX_AGE}; HttpOnly; SameSite=Strict; Secure"
    )
    assert cleared_cookie(False) == "rack_device=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


def _refusal(response: object, message: str) -> None:
    html = response.text  # type: ignore[attr-defined]
    assert response.status_code == 200  # type: ignore[attr-defined]
    assert _set_cookies(response) == []
    assert "hx-redirect" not in response.headers  # type: ignore[attr-defined]
    assert html.lstrip().startswith('<form class="pairing-form"')
    assert f'<p id="code-erreur" class="field__error">{message}</p>' in html
    assert 'aria-describedby="code-erreur code-aide" aria-invalid="true"' in html
    assert f'<div id="annonce" hx-swap-oob="innerHTML">{message}</div>' in html
    assert "value=" not in html


def test_wrong_code_shows_remaining_attempts(web: TestClient, migrated_engine: Engine) -> None:
    code = _code(migrated_engine)
    wrong = f"{(int(code) + 1) % 10**8:08d}"
    response = web.post("/appairage", headers=HTMX, json={"code": wrong})
    _refusal(response, TEXT("pairing.wrong_code_remaining", remaining=4))


def test_malformed_code_shows_the_generic_message(web: TestClient, migrated_engine: Engine) -> None:
    _code(migrated_engine)
    response = web.post("/appairage", headers=HTMX, json={"code": "12"})
    _refusal(response, TEXT("pairing.wrong_code"))


def test_used_code_is_expired(web: TestClient, migrated_engine: Engine) -> None:
    code = _code(migrated_engine)
    web.post("/appairage", headers=HTMX, json={"code": code})
    web.cookies.clear()
    response = web.post("/appairage", headers=HTMX, json={"code": code})
    _refusal(response, TEXT("pairing.code_expired"))


def test_fifth_wrong_code_blocks(web: TestClient, migrated_engine: Engine) -> None:
    code = _code(migrated_engine)
    wrong = f"{(int(code) + 1) % 10**8:08d}"
    for _ in range(rules.MAX_ATTEMPTS - 1):
        web.post("/appairage", headers=HTMX, json={"code": wrong})
    response = web.post("/appairage", headers=HTMX, json={"code": wrong})
    _refusal(response, TEXT("pairing.too_many_attempts"))


@pytest.mark.parametrize("body", [{}, {"code": "1" * 33}, {"code": 12345678}])
def test_invalid_body_is_the_generic_422(web: TestClient, body: dict[str, object]) -> None:
    response = web.post("/appairage", headers=JSON, json=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}


def test_pairing_logs_without_secrets(
    web: TestClient, migrated_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    code = _code(migrated_engine)
    with caplog.at_level("INFO"):
        web.post("/appairage", headers=HTMX, json={"code": "00000000" if code != "00000000" else "11111111"})
        web.post("/appairage", headers=HTMX, json={"code": code})
    assert "pairing refused: wrong_code" in caplog.text
    assert 'device "iPhone" paired' in caplog.text
    assert code not in caplog.text
    assert web.cookies[COOKIE_NAME] not in caplog.text


def test_paired_device_sees_the_already_paired_state(web: TestClient, migrated_engine: Engine) -> None:
    _pair(web, migrated_engine)
    html = web.get("/appairage", headers=PAGE).text
    assert TEXT("pairing.already_paired") in html
    assert "<form" not in html
    assert 'class="main--message"' in html


# --- cookie lifecycle -----------------------------------------------------------------------------


def test_revoked_device_is_sent_back_with_the_cookie_cleared(
    web: TestClient, migrated_engine: Engine
) -> None:
    _pair(web, migrated_engine)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    response = web.get("/", headers=PAGE)
    assert response.status_code == 303
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_unknown_cookie_on_the_pairing_page_is_cleared(web: TestClient) -> None:
    web.cookies.set(COOKIE_NAME, "not-a-token")
    response = web.get("/appairage", headers=PAGE)
    assert response.status_code == 200
    assert "<form" in response.text
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_renewal_resends_the_cookie_after_an_hour(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    token = _pair(web, migrated_engine)
    clock.now = NOW + rules.RENEW_AFTER - timedelta(seconds=1)
    assert _set_cookies(web.get("/", headers=PAGE)) == []
    clock.now = NOW + rules.RENEW_AFTER
    response = web.get("/", headers=PAGE)
    assert response.status_code == 200
    assert _set_cookies(response) == [device_cookie(token, False)]
    assert _set_cookies(web.get("/", headers=PAGE)) == []


def test_token_unused_for_400_days_is_refused(web: TestClient, migrated_engine: Engine, clock: Clock) -> None:
    _pair(web, migrated_engine)
    clock.now = NOW + rules.TOKEN_LIFETIME
    assert web.get("/", headers=PAGE).status_code == 303


def test_route_set_cookie_is_kept_next_to_the_renewal(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    router = APIRouter()

    @router.get("/biscuit")
    def biscuit() -> JSONResponse:
        response = JSONResponse({})
        response.set_cookie("autre", "1")
        return response

    web.app.include_router(router)  # type: ignore[attr-defined]
    _pair(web, migrated_engine)
    clock.now = NOW + rules.RENEW_AFTER
    cookies = _set_cookies(web.get("/biscuit"))
    assert len(cookies) == 2
    assert any(cookie.startswith("autre=1") for cookie in cookies)


def test_request_state_device_is_the_authenticated_device(web: TestClient, migrated_engine: Engine) -> None:
    router = APIRouter()
    seen: list[object] = []

    @router.get("/moi")
    def me(request: Request) -> dict[str, object]:
        seen.append(request.state.device)
        return {}

    web.app.include_router(router)  # type: ignore[attr-defined]
    _pair(web, migrated_engine)
    web.get("/moi")
    [device] = seen
    assert isinstance(device, devices.Device)
    assert (device.user_id, device.name) == (1, "iPhone")


def test_device_row_after_pairing(web: TestClient, migrated_engine: Engine) -> None:
    token = _pair(web, migrated_engine)
    with migrated_engine.connect() as connection:
        row = connection.execute(sa.select(schema.device)).one()
    assert row.token_hash == rules.hash_secret(token)
    assert row.last_seen_at == "2026-11-03T18:04:05Z"
