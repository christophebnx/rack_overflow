"""Edge cases of device authentication and pairing through the TestClient (D-034, D-040, D-049).

Complements `test_auth.py`: expiry boundaries, several live codes, revocation on htmx and JSON
requests, cookie flags under HTTPS, malformed cookies, security checks before authentication.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.domain import devices as rules
from rack_overflow.services import devices
from rack_overflow.storage import devices as queries
from rack_overflow.storage import schema
from rack_overflow.web.app import CATALOG, create_app
from rack_overflow.web.auth import COOKIE_NAME, cleared_cookie, device_cookie
from rack_overflow.web.locale import load_catalog

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
PAGE = {"accept": "text/html,application/xhtml+xml"}
JSON = {"content-type": "application/json"}
HTMX = {**JSON, "HX-Request": "true", "accept": "text/html"}
TEXT = load_catalog(CATALOG).text


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def web(settings: Settings, migrated_engine: Engine, clock: Clock) -> Iterator[TestClient]:
    app = create_app(settings, migrated_engine, clock=clock, run_scheduler=False)
    with TestClient(app, follow_redirects=False) as client:
        yield client


@pytest.fixture
def secure_web(settings: Settings, migrated_engine: Engine, clock: Clock) -> Iterator[TestClient]:
    https = replace(settings, server=replace(settings.server, https=True))
    app = create_app(https, migrated_engine, clock=clock, run_scheduler=False)
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        yield client


def _wrong(*codes: str) -> str:
    return next(code for code in (f"{n:08d}" for n in range(100)) if code not in codes)


def _attempts(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        query = sa.select(schema.pairing_code.c.attempts).order_by(schema.pairing_code.c.id)
        return list(connection.execute(query).scalars())


def _last_seen(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(sa.select(schema.device.c.last_seen_at)).scalar_one()


def _post_code(client: TestClient, code: str) -> object:
    return client.post("/appairage", headers=HTMX, json={"code": code})


def _pair(client: TestClient, engine: Engine, name: str = "iPhone") -> str:
    response = _post_code(client, devices.add_device(engine, name, NOW).code)
    assert response.headers["hx-redirect"] == "/"  # type: ignore[attr-defined]
    return client.cookies[COOKIE_NAME]


def _set_cookies(response: object) -> list[str]:
    return response.headers.get_list("set-cookie")  # type: ignore[attr-defined]


# --- code expiry and attempts through the page ------------------------------------------------------


def test_code_one_second_before_expiry_pairs(web: TestClient, migrated_engine: Engine, clock: Clock) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    clock.now = NOW + rules.CODE_TTL - timedelta(seconds=1)
    response = _post_code(web, code)
    assert response.headers["hx-redirect"] == "/"  # type: ignore[attr-defined]
    assert web.get("/", headers=PAGE).status_code == 200


def test_code_at_exactly_ten_minutes_is_expired(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    clock.now = NOW + rules.CODE_TTL
    response = _post_code(web, code)
    assert TEXT("pairing.code_expired") in response.text  # type: ignore[attr-defined]
    assert _set_cookies(response) == []
    assert COOKIE_NAME not in web.cookies
    assert _attempts(migrated_engine) == [0]  # a match on a dead code charges nothing


def test_wrong_code_with_no_live_code_shows_the_message_without_a_count(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    clock.now = NOW + rules.CODE_TTL
    response = _post_code(web, _wrong(code))
    assert f">{TEXT('pairing.wrong_code')}</p>" in response.text  # type: ignore[attr-defined]


def test_wrong_code_is_charged_to_every_live_code(web: TestClient, migrated_engine: Engine) -> None:
    first = devices.add_device(migrated_engine, "iPhone", NOW).code
    second = devices.add_device(migrated_engine, "Mac", NOW).code
    wrong = _wrong(first, second)
    for remaining in range(rules.MAX_ATTEMPTS - 1, 0, -1):
        response = _post_code(web, wrong)
        expected = TEXT("pairing.wrong_code_remaining", remaining=remaining)
        assert expected in response.text  # type: ignore[attr-defined]
    response = _post_code(web, wrong)
    assert TEXT("pairing.too_many_attempts") in response.text  # type: ignore[attr-defined]
    assert _attempts(migrated_engine) == [rules.MAX_ATTEMPTS, rules.MAX_ATTEMPTS]
    for code in (first, second):
        assert TEXT("pairing.too_many_attempts") in _post_code(web, code).text  # type: ignore[attr-defined]
    assert COOKIE_NAME not in web.cookies


def test_fifth_wrong_attempt_then_a_new_code_pairs(web: TestClient, migrated_engine: Engine) -> None:
    blocked = devices.add_device(migrated_engine, "iPhone", NOW).code
    for _ in range(rules.MAX_ATTEMPTS):
        _post_code(web, _wrong(blocked))
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    fresh = devices.add_device(migrated_engine, "iPhone", NOW).code
    assert _post_code(web, fresh).headers["hx-redirect"] == "/"  # type: ignore[attr-defined]


def test_reused_code_from_a_second_browser_is_refused(
    web: TestClient, settings: Settings, migrated_engine: Engine, clock: Clock
) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    assert _post_code(web, code).headers["hx-redirect"] == "/"  # type: ignore[attr-defined]
    other = create_app(settings, migrated_engine, clock=clock, run_scheduler=False)
    with TestClient(other, follow_redirects=False) as second:
        response = _post_code(second, code)
        assert TEXT("pairing.code_expired") in response.text  # type: ignore[attr-defined]
        assert COOKIE_NAME not in second.cookies


def test_code_typed_with_hyphen_and_spaces_pairs(web: TestClient, migrated_engine: Engine) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    response = _post_code(web, f" {code[:4]}-{code[4:]} ")
    assert response.headers["hx-redirect"] == "/"  # type: ignore[attr-defined]


# --- revocation and token lifetime ---------------------------------------------------------------


def test_revoked_device_htmx_request_gets_401_hx_redirect_and_cleared_cookie(
    web: TestClient, migrated_engine: Engine
) -> None:
    _pair(web, migrated_engine)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    response = web.get("/", headers={**PAGE, "HX-Request": "true"})
    assert response.status_code == 401
    assert response.json() == {"error": "not_paired"}
    assert response.headers["hx-redirect"] == "/appairage"
    assert _set_cookies(response) == [cleared_cookie(False)]
    assert COOKIE_NAME not in web.cookies


def test_revoked_device_json_post_gets_401_and_cleared_cookie(
    web: TestClient, migrated_engine: Engine
) -> None:
    _pair(web, migrated_engine)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    response = web.post("/", headers=JSON, content=b"{}")
    assert response.status_code == 401
    assert "hx-redirect" not in response.headers
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_revocation_takes_effect_on_the_very_next_request(web: TestClient, migrated_engine: Engine) -> None:
    _pair(web, migrated_engine)
    assert web.get("/", headers=PAGE).status_code == 200
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    assert web.get("/", headers=PAGE).status_code == 303


def test_revoking_one_device_keeps_the_other(
    web: TestClient, settings: Settings, migrated_engine: Engine, clock: Clock
) -> None:
    _pair(web, migrated_engine, "iPhone")
    other = create_app(settings, migrated_engine, clock=clock, run_scheduler=False)
    with TestClient(other, follow_redirects=False) as mac:
        _pair(mac, migrated_engine, "Mac")
        devices.revoke_device(migrated_engine, "iPhone", NOW)
        assert mac.get("/", headers=PAGE).status_code == 200
    assert web.get("/", headers=PAGE).status_code == 303


def test_token_one_second_before_its_lifetime_still_works_and_renews(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    token = _pair(web, migrated_engine)
    clock.now = NOW + rules.TOKEN_LIFETIME - timedelta(seconds=1)
    response = web.get("/", headers=PAGE)
    assert response.status_code == 200
    assert _set_cookies(response) == [device_cookie(token, False)]
    clock.now += rules.TOKEN_LIFETIME - timedelta(seconds=1)  # a used token never expires
    assert web.get("/", headers=PAGE).status_code == 200


def test_expired_token_cookie_is_cleared(web: TestClient, migrated_engine: Engine, clock: Clock) -> None:
    _pair(web, migrated_engine)
    clock.now = NOW + rules.TOKEN_LIFETIME
    response = web.get("/", headers=PAGE)
    assert response.status_code == 303
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_last_seen_is_written_at_most_once_an_hour(
    web: TestClient, migrated_engine: Engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pair(web, migrated_engine)
    touches: list[str] = []
    real_touch = queries.touch

    def counting(connection: sa.Connection, device_id: int, now: str) -> None:
        touches.append(now)
        real_touch(connection, device_id, now)

    monkeypatch.setattr(queries, "touch", counting)
    for minutes in (0, 1, 30, 59):
        clock.now = NOW + timedelta(minutes=minutes)
        assert web.get("/", headers=PAGE).status_code == 200
    assert touches == []
    assert _last_seen(migrated_engine) == "2026-11-03T18:04:05Z"
    clock.now = NOW + timedelta(minutes=61)
    web.get("/", headers=PAGE)
    web.get("/", headers=PAGE)
    clock.now = NOW + timedelta(minutes=120)
    web.get("/", headers=PAGE)
    assert touches == ["2026-11-03T19:05:05Z"]
    assert _last_seen(migrated_engine) == "2026-11-03T19:05:05Z"


# --- malformed cookies ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["", "short", "A" * (rules.TOKEN_LENGTH + 1), "A" * (rules.TOKEN_LENGTH - 1) + "!"]
)
def test_malformed_cookie_is_refused_without_a_query_and_cleared(
    web: TestClient, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queries, "device_by_token_hash", lambda *args: pytest.fail("database queried"))
    web.cookies.set(COOKIE_NAME, value)
    response = web.get("/", headers=PAGE)
    assert response.status_code == 303
    assert response.headers["location"] == "/appairage"
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_well_shaped_unknown_token_gets_401_on_json(web: TestClient) -> None:
    web.cookies.set(COOKIE_NAME, "A" * rules.TOKEN_LENGTH)
    response = web.get("/", headers=JSON)
    assert response.status_code == 401
    assert _set_cookies(response) == [cleared_cookie(False)]


def test_database_failure_during_the_check_is_json_internal_for_htmx(
    web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise sa.exc.OperationalError("SELECT", {}, Exception("disk"))

    monkeypatch.setattr(devices, "authenticate", broken)
    web.cookies.set(COOKIE_NAME, "A" * rules.TOKEN_LENGTH)
    response = web.post("/", headers=HTMX, content=b"{}")
    assert response.status_code == 500
    assert response.json() == {"error": "internal"}


# --- cookie flags with HTTPS --------------------------------------------------------------------------


def test_https_cookies_are_secure_when_cleared_and_renewed(
    secure_web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    token = _pair(secure_web, migrated_engine)
    clock.now = NOW + rules.RENEW_AFTER
    renewed = secure_web.get("/", headers=PAGE)
    assert renewed.status_code == 200
    assert _set_cookies(renewed) == [device_cookie(token, True)]
    assert renewed.headers["strict-transport-security"]
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    response = secure_web.get("/", headers=PAGE)
    assert response.status_code == 303
    [cleared] = _set_cookies(response)
    assert cleared == cleared_cookie(True)
    assert cleared.endswith("; HttpOnly; SameSite=Strict; Secure")


def test_http_cookie_never_carries_secure(web: TestClient, migrated_engine: Engine, clock: Clock) -> None:
    _pair(web, migrated_engine)
    clock.now = NOW + rules.RENEW_AFTER
    cookies = _set_cookies(web.get("/", headers=PAGE))
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    cookies += _set_cookies(web.get("/", headers=PAGE))
    assert len(cookies) == 2
    assert all("Secure" not in cookie and "HttpOnly" in cookie for cookie in cookies)


# --- request types, public paths, error pages -------------------------------------------------------


def test_unpaired_head_navigation_is_sent_to_pairing(web: TestClient) -> None:
    response = web.head("/", headers=PAGE)
    assert response.status_code == 303
    assert response.headers["location"] == "/appairage"


def test_unpaired_request_without_html_accept_gets_401(web: TestClient) -> None:
    response = web.get("/", headers={"accept": "*/*"})
    assert response.status_code == 401
    assert response.json() == {"error": "not_paired"}


def test_unpaired_wrong_method_on_a_protected_path_does_not_reveal_405(web: TestClient) -> None:
    response = web.put("/", headers=JSON, content=b"{}")
    assert response.status_code == 401


def test_paired_unknown_path_is_the_404_page(web: TestClient, migrated_engine: Engine) -> None:
    _pair(web, migrated_engine)
    response = web.get("/nulle-part", headers=PAGE)
    assert response.status_code == 404
    assert TEXT("error.title.not_found") in response.text


def test_unpaired_static_not_found_is_json_or_page_without_redirect(web: TestClient) -> None:
    response = web.get("/static/absent.css", headers=PAGE)
    assert response.status_code == 404
    assert "location" not in response.headers


def test_pairing_page_is_public_for_htmx_and_json(web: TestClient) -> None:
    assert web.get("/appairage", headers={**PAGE, "HX-Request": "true"}).status_code == 200
    assert web.get("/appairage", headers=JSON).status_code == 200


# --- security checks run before authentication ---------------------------------------------------------


def test_wrong_host_is_refused_before_authentication(
    web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devices, "authenticate", lambda *args: pytest.fail("authenticated"))
    web.cookies.set(COOKIE_NAME, "A" * rules.TOKEN_LENGTH)
    response = web.get("/", headers={**PAGE, "host": "evil.example"})
    assert response.status_code == 400
    assert "location" not in response.headers


def test_cross_origin_pairing_post_is_refused_and_charges_nothing(
    web: TestClient, migrated_engine: Engine
) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    response = web.post(
        "/appairage", headers={**HTMX, "origin": "http://evil.example"}, json={"code": _wrong(code)}
    )
    assert response.status_code == 403
    response = web.post("/appairage", headers={**HTMX, "sec-fetch-site": "cross-site"}, json={"code": code})
    assert response.status_code == 403
    assert _attempts(migrated_engine) == [0]
    assert COOKIE_NAME not in web.cookies


def test_form_encoded_pairing_post_is_refused_and_charges_nothing(
    web: TestClient, migrated_engine: Engine
) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    response = web.post("/appairage", data={"code": code})
    assert response.status_code == 415
    assert _attempts(migrated_engine) == [0]
    assert COOKIE_NAME not in web.cookies


def test_oversized_pairing_body_is_413(web: TestClient) -> None:
    response = web.post("/appairage", headers=JSON, content=b'{"code": "' + b"1" * 70000 + b'"}')
    assert response.status_code == 413


# --- pairing with a stale cookie still in the browser --------------------------------------------------


def test_pairing_with_a_stale_cookie_keeps_the_new_token(web: TestClient, migrated_engine: Engine) -> None:
    _pair(web, migrated_engine, "iPhone")
    devices.revoke_device(migrated_engine, "iPhone", NOW)  # e.g. page restored from the back-forward cache
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    response = _post_code(web, code)
    assert response.headers["hx-redirect"] == "/"  # type: ignore[attr-defined]
    # RFC 6265 user agents process Set-Cookie headers in order: the last one for the name wins
    last = [cookie for cookie in _set_cookies(response) if cookie.startswith(f"{COOKIE_NAME}=")][-1]
    assert last != cleared_cookie(False)
    assert devices.authenticate(migrated_engine, last.split(";")[0].split("=", 1)[1], NOW) is not None


def test_pairing_with_a_renewable_cookie_keeps_only_the_new_token(
    web: TestClient, migrated_engine: Engine, clock: Clock
) -> None:
    old = _pair(web, migrated_engine, "iPhone")
    clock.now = NOW + rules.RENEW_AFTER + timedelta(minutes=1)  # the old cookie is due for renewal
    code = devices.add_device(migrated_engine, "iPad", clock.now).code
    response = _post_code(web, code)
    device_cookies = [cookie for cookie in _set_cookies(response) if cookie.startswith(f"{COOKIE_NAME}=")]
    assert len(device_cookies) == 1
    assert device_cookies[0] != device_cookie(old, False)
    new = device_cookies[0].split(";")[0].split("=", 1)[1]
    assert devices.authenticate(migrated_engine, new, clock.now).name == "iPad"  # type: ignore[union-attr]
