"""The web app through the TestClient: pages, errors and the security middleware."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from rack_overflow.config import Settings
from rack_overflow.web.security import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES

PAGE = {"accept": "text/html,application/xhtml+xml"}
JSON = {"content-type": "application/json"}


def assert_security_headers(response: object, *, no_store: bool = True) -> None:
    headers = response.headers  # type: ignore[attr-defined]
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"
    assert ("cache-control" in headers and headers["cache-control"] == "no-store") is no_store
    assert "strict-transport-security" not in headers
    assert not any(name.startswith("access-control-") for name in headers)


def test_home_page(client: TestClient) -> None:
    response = client.get("/", headers=PAGE)
    assert response.status_code == 200
    assert '<html lang="fr">' in response.text
    assert "<title>Accueil · Rack Overflow</title>" in response.text
    assert 'aria-current="page"' in response.text
    assert 'id="annonce"' in response.text
    assert "<nav" not in response.text
    assert_security_headers(response)


def test_static_file_has_headers_but_may_be_cached(client: TestClient) -> None:
    response = client.get("/static/css/tokens.css")
    assert response.status_code == 200
    assert_security_headers(response, no_store=False)


def test_not_found_page_for_a_browser(client: TestClient) -> None:
    response = client.get("/nulle-part", headers=PAGE)
    assert response.status_code == 404
    assert "Page introuvable" in response.text
    assert "Code 404" in response.text
    assert "nulle-part" not in response.text
    assert_security_headers(response)


def test_not_found_code_for_htmx(client: TestClient) -> None:
    response = client.get("/nulle-part", headers={**PAGE, "HX-Request": "true"})
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


def test_method_not_allowed(client: TestClient) -> None:
    response = client.post("/", headers=JSON, content=b"{}")
    assert response.status_code == 405
    assert response.json() == {"error": "method_not_allowed"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"content-type": "application/x-www-form-urlencoded"}, {"content-type": "text/plain"}],
)
def test_non_json_post_gets_415(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/", headers=headers, content=b"a=1")
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    assert_security_headers(response)


def test_json_with_charset_passes(client: TestClient) -> None:
    response = client.post("/", headers={"content-type": "application/json; charset=utf-8"}, content=b"{}")
    assert response.status_code == 405  # reached the routing


@pytest.mark.parametrize(
    "headers",
    [{"origin": "http://evil.example"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}],
)
def test_foreign_origin_gets_403(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/", headers={**JSON, **headers}, content=b"{}")
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}


def test_same_origin_post_passes(client: TestClient) -> None:
    headers = {**JSON, "origin": "http://testserver", "sec-fetch-site": "same-origin"}
    assert client.post("/", headers=headers, content=b"{}").status_code == 405


@pytest.mark.parametrize("host", ["evil.example", "testserver.evil.example", ""])
def test_wrong_host_gets_400(client: TestClient, host: str) -> None:
    response = client.get("/", headers={"host": host})
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_host"}
    assert_security_headers(response)


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1", "[::1]:80", "TESTSERVER:1234"])
def test_loopback_and_public_hosts_pass(client: TestClient, host: str) -> None:
    assert client.get("/", headers={"host": host}).status_code == 200


def test_oversized_content_length_gets_413(client: TestClient) -> None:
    response = client.post("/", headers=JSON, content=b"x" * (MAX_BODY_BYTES + 1))
    assert response.status_code == 413
    assert response.json() == {"error": "payload_too_large"}


def test_oversized_streamed_body_gets_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(5):
            yield b"x" * (MAX_BODY_BYTES // 4)

    response = client.post("/", headers=JSON, content=chunks())
    assert response.status_code == 413


def test_unhandled_error_gives_the_500_page_with_headers(client: TestClient) -> None:
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client.app.include_router(router)  # type: ignore[attr-defined]
    response = client.get("/boom?x=1", headers=PAGE)
    assert response.status_code == 500
    assert "Erreur du serveur" in response.text
    assert 'href="/boom"' in response.text
    assert_security_headers(response)
    assert client.get("/boom").json() == {"error": "internal"}


def test_hsts_only_with_https(settings: Settings, migrated_engine: object) -> None:
    from dataclasses import replace

    from rack_overflow.web.app import create_app

    https = replace(settings, server=replace(settings.server, https=True))
    app = create_app(https, migrated_engine, clock=lambda: None, run_scheduler=False)  # type: ignore[arg-type]
    with TestClient(app, base_url="https://testserver") as https_client:
        response = https_client.get("/")
    assert response.headers["strict-transport-security"].startswith("max-age=")
