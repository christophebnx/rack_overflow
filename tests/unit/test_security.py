"""The security middleware driven directly as ASGI, with a recording fake app (D-034, D-047)."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from rack_overflow.web.security import (
    COMMON_HEADERS,
    HSTS,
    MAX_BODY_BYTES,
    SecurityMiddleware,
    hostname,
)

JSON_TYPE = (b"content-type", b"application/json")


class FakeApp:
    """Records what reaches it, answers 200 with an empty body."""

    def __init__(self) -> None:
        self.calls: list[tuple[Scope, list[Message]]] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        received: list[Message] = []
        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD"}:
            received.append(await receive())
        self.calls.append((scope, received))
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})


def _scope(
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    host: bytes = b"rack",
) -> Scope:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"host", host), *(headers or [])],
    }


def _call(
    scope: Scope, chunks: list[Message] | None = None, *, https: bool = False
) -> tuple[FakeApp, list[Message]]:
    app = FakeApp()
    middleware = SecurityMiddleware(app, public_host="Rack", https=https)
    incoming = list(chunks or [{"type": "http.request", "body": b"", "more_body": False}])
    sent: list[Message] = []

    async def receive() -> Message:
        return incoming.pop(0) if incoming else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    # own thread: a running loop on the worker (Playwright's sync API) forbids asyncio.run here
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, middleware(scope, receive, send)).result()
    return app, sent


def _status(sent: list[Message]) -> int:
    return sent[0]["status"]


def _headers(sent: list[Message]) -> dict[str, str]:
    return {name.decode(): value.decode() for name, value in sent[0]["headers"]}


def _error(sent: list[Message]) -> Any:
    return json.loads(sent[1]["body"])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("rack", "rack"),
        ("RACK:8765", "rack"),
        (" rack ", "rack"),
        ("[::1]", "[::1]"),
        ("[::1]:8765", "[::1]"),
        ("[::1", "[::1"),
        ("", ""),
        ("127.0.0.1:80", "127.0.0.1"),
    ],
)
def test_hostname(value: str, expected: str) -> None:
    assert hostname(value) == expected


def test_public_host_is_compared_case_insensitively() -> None:
    app, sent = _call(_scope(host=b"RACK:8765"))
    assert _status(sent) == 200
    assert len(app.calls) == 1


@pytest.mark.parametrize("host", [b"[::1", b"rack.", b"evil", b"127.0.0.1.evil", b"rack@evil"])
def test_unknown_hosts_are_refused_before_the_app(host: bytes) -> None:
    app, sent = _call(_scope(host=host))
    assert (_status(sent), _error(sent)) == (400, {"error": "invalid_host"})
    assert app.calls == []


def test_missing_host_header_is_refused() -> None:
    app, sent = _call({"type": "http", "method": "GET", "path": "/", "headers": []})
    assert _status(sent) == 400
    assert app.calls == []


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_every_unsafe_method_needs_json(method: str) -> None:
    app, sent = _call(_scope(method, headers=[(b"content-type", b"multipart/form-data; boundary=x")]))
    assert (_status(sent), _error(sent)) == (415, {"error": "unsupported_media_type"})
    assert app.calls == []


@pytest.mark.parametrize("media_type", [b"APPLICATION/JSON", b" application/json ; charset=utf-8"])
def test_json_media_type_is_parsed_loosely(media_type: bytes) -> None:
    _, sent = _call(_scope("POST", headers=[(b"content-type", media_type)]))
    assert _status(sent) == 200


@pytest.mark.parametrize("media_type", [b"application/json-patch+json", b"application/jsonx", b"text/json"])
def test_look_alike_media_types_are_refused(media_type: bytes) -> None:
    _, sent = _call(_scope("POST", headers=[(b"content-type", media_type)]))
    assert _status(sent) == 415


def test_head_needs_no_content_type() -> None:
    app, sent = _call(_scope("HEAD"))
    assert _status(sent) == 200
    assert len(app.calls) == 1


@pytest.mark.parametrize("length", [b"abc", b"-1", b"1e3", str(MAX_BODY_BYTES + 1).encode()])
def test_bad_or_oversized_content_length_is_refused(length: str) -> None:
    app, sent = _call(_scope("POST", headers=[JSON_TYPE, (b"content-length", length)]))
    assert (_status(sent), _error(sent)) == (413, {"error": "payload_too_large"})
    assert app.calls == []


def test_body_at_the_limit_is_replayed_whole_to_the_app() -> None:
    half = MAX_BODY_BYTES // 2
    chunks: list[Message] = [
        {"type": "http.request", "body": b"a" * half, "more_body": True},
        {"type": "http.request", "body": b"b" * (MAX_BODY_BYTES - half), "more_body": False},
    ]
    app, sent = _call(_scope("POST", headers=[JSON_TYPE]), chunks)
    assert _status(sent) == 200
    [(_, received)] = app.calls
    assert received == [
        {"type": "http.request", "body": b"a" * half + b"b" * (MAX_BODY_BYTES - half), "more_body": False}
    ]


def test_streamed_body_one_byte_over_the_limit_is_refused() -> None:
    chunks: list[Message] = [
        {"type": "http.request", "body": b"a" * MAX_BODY_BYTES, "more_body": True},
        {"type": "http.request", "body": b"b", "more_body": False},
    ]
    app, sent = _call(_scope("POST", headers=[JSON_TYPE]), chunks)
    assert _status(sent) == 413
    assert app.calls == []


def test_client_disconnect_while_reading_is_passed_on() -> None:
    chunks: list[Message] = [{"type": "http.disconnect"}]
    app, _ = _call(_scope("POST", headers=[JSON_TYPE]), chunks)
    [(_, received)] = app.calls
    assert received == [{"type": "http.disconnect"}]


@pytest.mark.parametrize(
    "headers",
    [
        [(b"origin", b"http://evil")],
        [(b"origin", b"https://rack")],  # scheme differs from the configured one
        [(b"origin", b"http://rack:9999")],
        [(b"sec-fetch-site", b"same-site")],
        [(b"sec-fetch-site", b"cross-site")],
    ],
)
def test_foreign_origin_is_refused_on_unsafe_methods(headers: list[tuple[bytes, bytes]]) -> None:
    app, sent = _call(_scope("POST", headers=[JSON_TYPE, *headers]))
    assert (_status(sent), _error(sent)) == (403, {"error": "forbidden_origin"})
    assert app.calls == []


@pytest.mark.parametrize("site", [b"same-origin", b"none", b"SAME-ORIGIN"])
def test_same_origin_fetch_sites_pass(site: bytes) -> None:
    _, sent = _call(
        _scope("POST", headers=[JSON_TYPE, (b"sec-fetch-site", site), (b"origin", b"HTTP://RACK")])
    )
    assert _status(sent) == 200


def test_origin_check_follows_https() -> None:
    _, sent = _call(_scope("POST", headers=[JSON_TYPE, (b"origin", b"https://rack")]), https=True)
    assert _status(sent) == 200
    _, sent = _call(_scope("POST", headers=[JSON_TYPE, (b"origin", b"http://rack")]), https=True)
    assert _status(sent) == 403


def test_api_reads_are_origin_checked_but_page_reads_are_not() -> None:
    foreign = [(b"origin", b"http://evil"), (b"sec-fetch-site", b"cross-site")]
    _, sent = _call(_scope("GET", "/api/things", headers=foreign))
    assert _status(sent) == 403
    _, sent = _call(_scope("GET", "/", headers=foreign))  # a link followed from another site
    assert _status(sent) == 200


def test_headers_on_passed_and_refused_responses() -> None:
    for scope in (_scope(), _scope(host=b"evil"), _scope("POST")):
        _, sent = _call(scope)
        headers = _headers(sent)
        for name, value in COMMON_HEADERS.items():
            assert headers[name.lower()] == value
        assert headers["cache-control"] == "no-store"
        assert "strict-transport-security" not in headers
        assert not any(name.startswith("access-control-") for name in headers)


def test_static_responses_may_be_cached_and_hsts_follows_https() -> None:
    _, sent = _call(_scope(path="/static/css/tokens.css"), https=True)
    headers = _headers(sent)
    assert "cache-control" not in headers
    assert headers["strict-transport-security"] == HSTS


def test_rejection_has_a_matching_content_length() -> None:
    _, sent = _call(_scope(host=b"evil"))
    headers = _headers(sent)
    assert headers["content-type"] == "application/json"
    assert int(headers["content-length"]) == len(sent[1]["body"])


def test_non_http_scopes_pass_through_untouched() -> None:
    app, sent = _call({"type": "lifespan"})
    assert [scope["type"] for scope, _ in app.calls] == ["lifespan"]
    assert sent == []
