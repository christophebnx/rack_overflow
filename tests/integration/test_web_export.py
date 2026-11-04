"""The data export on the settings page and `GET /api/export` (docs/ui-spec.md "L6 — Settings:
export"; D-074), and the « Réessayer » link of a 5xx page keeping the query, safely."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from starlette.requests import Request
from support.populated import populate
from test_web_pages import assert_secure_page

from rack_overflow import __version__
from rack_overflow.domain import export as rules
from rack_overflow.services import export
from rack_overflow.web import errors
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.security import CONTENT_SECURITY_POLICY

FIXED_NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock
PAGE = {"accept": "text/html,application/xhtml+xml"}
HTMX = {"accept": "text/html", "HX-Request": "true"}
TEXT = load_catalog(CATALOG).text
DISPOSITION = re.compile(r'^attachment; filename="rack-overflow-\d{8}T\d{6}Z(\.json|-csv\.zip)"$')


def test_settings_page_has_the_data_section(client: TestClient) -> None:
    response = client.get("/reglages", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert '<section class="section settings" id="donnees" aria-labelledby="donnees-titre">' in html
    assert f'<h2 id="donnees-titre">{TEXT("settings.data_heading")}</h2>' in html
    for kind in ("json", "csv"):
        link = (
            f'<a class="button export__link" id="export-{kind}" href="/api/export?format={kind}" '
            f'aria-describedby="export-{kind}-aide">{TEXT(f"settings.export_{kind}")}</a>'
        )
        assert link in html
        assert f'id="export-{kind}-aide">{TEXT(f"settings.export_{kind}_hint")}</p>' in html
    assert " download" not in html
    assert TEXT("settings.export_units") in html and TEXT("settings.export_not_backup") in html
    progress_link = html.index('<a class="button" href="/progression">')
    assert html.index('id="export-json"') < html.index('id="export-csv"') < progress_link


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_export_downloads(client: TestClient, migrated_engine: Engine, kind: str) -> None:
    populate(migrated_engine)
    response = client.get(f"/api/export?format={kind}", headers=PAGE)
    assert response.status_code == 200
    expected = export.export(migrated_engine, kind, FIXED_NOW, __version__)
    assert response.content == expected.data
    assert response.headers["content-type"] == expected.media_type
    assert DISPOSITION.match(response.headers["content-disposition"])
    assert response.headers["content-disposition"].endswith(f'filename="{expected.file_name}"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_json_download_reads_back(client: TestClient) -> None:
    meta, tables = rules.read_json(client.get("/api/export?format=json").content)
    assert meta.exported_at == FIXED_NOW and meta.app_version == __version__
    assert [row["name"] for row in tables["device"]] == ["test"]
    assert "token_hash" not in tables["device"][0]


@pytest.mark.parametrize("query", ["", "?format=xml", "?format=JSON", "?format="])
def test_unknown_or_missing_format_is_422(client: TestClient, query: str) -> None:
    assert client.get(f"/api/export{query}").json() == {"error": "invalid_request"}
    page = client.get(f"/api/export{query}", headers=PAGE)
    assert_secure_page(page, 422)
    assert TEXT("error.invalid_request") in page.text


def test_foreign_origin_is_refused(client: TestClient) -> None:
    assert client.get("/api/export?format=json", headers={"origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/export?format=json", headers={"sec-fetch-site": "cross-site"}).status_code == 403


def test_unpaired_browser_is_sent_to_pairing(unpaired_client: TestClient) -> None:
    navigation = unpaired_client.get("/api/export?format=json", headers=PAGE, follow_redirects=False)
    assert navigation.status_code == 303 and navigation.headers["location"] == "/appairage"
    assert unpaired_client.get("/api/export?format=json", headers=HTMX).status_code == 401


def test_server_failure_retry_keeps_the_query(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object) -> None:
        raise RuntimeError("disk")

    monkeypatch.setattr(export, "export", broken)
    response = client.get("/api/export?format=json", headers=PAGE)
    assert_secure_page(response, 500)
    assert f'<a class="button button--primary" href="/api/export?format=json">{TEXT("action.retry")}</a>' in (
        response.text
    )


def _retry(raw_path: bytes, query: bytes) -> str:
    scope = {"type": "http", "path": raw_path.decode("latin-1"), "raw_path": raw_path, "query_string": query}
    return errors._retry_path(Request(scope))


@pytest.mark.parametrize(
    ("raw_path", "query", "link"),
    [
        (b"/api/export", b"format=json", "/api/export?format=json"),
        (b"/panne/a%3Fb", b"x=1&y=%C3%A9", "/panne/a%3Fb?x=1&y=%C3%A9"),
        (b"/p", b"", "/p"),
        (b"/p", b'a="><script>x</script>', "/p?a=%22%3E%3Cscript%3Ex%3C/script%3E"),
        (b"/p", b"a=1#frag b\\c", "/p?a=1%23frag%20b%5Cc"),
        (b"/p", "a=é\n".encode(), "/p?a=%C3%A9%0A"),
        (b"//evil.example/x", b"q=1", "/evil.example/x?q=1"),
        (b"/\\evil.example", b"", "/%5Cevil.example"),
        (b"/a b<c>", b"", "/a%20b%3Cc%3E"),
    ],
)
def test_retry_link_is_same_origin_and_encoded(raw_path: bytes, query: bytes, link: str) -> None:
    assert _retry(raw_path, query) == link
