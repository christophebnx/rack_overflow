"""Rendered pages through the TestClient: same-origin resources only, no inline script or style,
security headers on every answer (pages, errors, static files), and JSON error codes."""

from __future__ import annotations

from collections.abc import Iterator
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from rack_overflow.web.security import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES

PAGE = {"accept": "text/html,application/xhtml+xml"}
JSON = {"content-type": "application/json"}
URL_ATTRIBUTES = {"src", "href", "action", "formaction", "poster", "data", "srcset", "hx-get", "hx-post"}


class PageAudit(HTMLParser):
    """Collects what the D-034 page rules forbid, and every URL the page refers to."""

    def __init__(self) -> None:
        super().__init__()
        self.problems: list[str] = []
        self.urls: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = {name for name, _ in attrs}
        if tag == "style":
            self.problems.append("<style> element")
        if tag == "script" and "src" not in names:
            self.problems.append("inline <script>")
        self._in_script = tag == "script"
        for name, value in attrs:
            if name == "style":
                self.problems.append(f"style attribute on <{tag}>")
            if name.startswith("on"):
                self.problems.append(f"{name} handler on <{tag}>")
            if name in URL_ATTRIBUTES and value is not None:
                self.urls.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script and data.strip():
            self.problems.append("script body")


def audit(html: str) -> PageAudit:
    parser = PageAudit()
    parser.feed(html)
    parser.close()
    return parser


def is_same_origin(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "data":
        return True
    return not parts.scheme and not parts.netloc and not url.startswith("//")


def assert_secure_page(response: object, status: int, *, no_store: bool = True) -> PageAudit:
    assert response.status_code == status  # type: ignore[attr-defined]
    headers = response.headers  # type: ignore[attr-defined]
    assert headers["content-type"].startswith("text/html")
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert (headers.get("cache-control") == "no-store") is no_store
    result = audit(response.text)  # type: ignore[attr-defined]
    assert result.problems == []
    assert result.urls
    assert [url for url in result.urls if not is_same_origin(url)] == []
    return result


class Body(BaseModel):
    """The JSON body of the test route."""

    count: int


def _add_routes(client: TestClient) -> None:
    router = APIRouter()

    @router.post("/essai")
    def accept(body: Body) -> dict[str, int]:
        return {"count": body.count}

    @router.get("/panne/{rest:path}")
    def crash(rest: str) -> None:
        raise RuntimeError(rest)

    client.app.include_router(router)  # type: ignore[attr-defined]


def test_audit_catches_what_it_must() -> None:
    page = (
        '<style>a{}</style><script>x()</script><p style="x" onclick="y">'
        '<a href="https://cdn.example/x"></a><img src="//cdn.example/i.png">'
    )
    result = audit(page)
    assert len(result.problems) == 5
    assert [url for url in result.urls if not is_same_origin(url)] == [
        "https://cdn.example/x",
        "//cdn.example/i.png",
    ]


def test_home_page_refers_only_to_served_same_origin_assets(client: TestClient) -> None:
    result = assert_secure_page(client.get("/", headers=PAGE), 200)
    assets = [url for url in result.urls if url.startswith("/static/")]
    assert len(assets) >= 4
    for url in assets:
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert response.headers["x-content-type-options"] == "nosniff"


def test_vendored_scripts_are_served_as_javascript(client: TestClient) -> None:
    for name in ("htmx.min.js", "json-enc.js"):
        response = client.get(f"/static/vendor/{name}")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize(("path", "no_store"), [("/nulle-part", True), ("/static/absent.css", False)])
def test_not_found_pages_follow_the_rules(client: TestClient, path: str, no_store: bool) -> None:
    assert_secure_page(client.get(path, headers=PAGE), 404, no_store=no_store)


def test_missing_static_file_for_a_script_is_a_json_code(client: TestClient) -> None:
    response = client.get("/static/absent.js")
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_static_path_traversal_is_refused(client: TestClient) -> None:
    response = client.get("/static/..%2f..%2fapp.py")
    assert response.status_code == 404


def test_server_error_page_follows_the_rules_and_links_back_on_site(client: TestClient) -> None:
    _add_routes(client)
    response = client.get("http://testserver/panne//evil.example/x", headers=PAGE)
    result = assert_secure_page(response, 500)
    assert "/panne//evil.example/x" in result.urls  # path kept, still same-origin
    assert all(not url.startswith("//") for url in result.urls)


def test_server_error_for_htmx_is_a_json_code(client: TestClient) -> None:
    _add_routes(client)
    response = client.get("/panne/x", headers={**PAGE, "HX-Request": "true"})
    assert response.status_code == 500
    assert response.json() == {"error": "internal"}
    assert response.headers["cache-control"] == "no-store"


def test_method_not_allowed_page_for_a_browser(client: TestClient) -> None:
    response = client.post("/", headers={**PAGE, **JSON}, content=b"{}")
    assert_secure_page(response, 405)


def test_json_body_reaches_the_route(client: TestClient) -> None:
    _add_routes(client)
    response = client.post("/essai", headers=JSON, content=b'{"count": 3}')
    assert response.status_code == 200
    assert response.json() == {"count": 3}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("body", [b'{"count": "trois"}', b"{", b""])
def test_invalid_json_body_is_a_stable_code(client: TestClient, body: bytes) -> None:
    _add_routes(client)
    response = client.post("/essai", headers=JSON, content=body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_form_post_never_reaches_a_route(client: TestClient) -> None:
    _add_routes(client)
    response = client.post("/essai", data={"count": "3"})
    assert response.status_code == 415


def test_body_at_the_limit_passes_and_one_more_byte_does_not(client: TestClient) -> None:
    _add_routes(client)
    padding = MAX_BODY_BYTES - len(b'{"count": 1, "p": ""}')
    body = b'{"count": 1, "p": "' + b"x" * padding + b'"}'
    assert len(body) == MAX_BODY_BYTES
    assert client.post("/essai", headers=JSON, content=body).status_code == 200
    response = client.post("/essai", headers=JSON, content=body + b" ")
    assert response.status_code == 413
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["cache-control"] == "no-store"


def test_foreign_origin_answer_has_the_headers_and_no_cors(client: TestClient) -> None:
    response = client.post("/", headers={**JSON, "origin": "http://evil.example"}, content=b"{}")
    assert response.status_code == 403
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["referrer-policy"] == "no-referrer"
    assert not any(name.startswith("access-control-") for name in response.headers)


def test_no_api_documentation_is_exposed(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_no_server_header_leaks_from_the_app(client: TestClient) -> None:
    assert "server" not in client.get("/").headers


def test_error_after_the_response_started_is_not_masked(client: TestClient) -> None:
    router = APIRouter()

    def chunks() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError("mid-stream")

    @router.get("/flux")
    def stream() -> StreamingResponse:
        return StreamingResponse(chunks(), media_type="text/plain")

    client.app.include_router(router)  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="mid-stream"):
        client.get("/flux")
