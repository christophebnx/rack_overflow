"""HTTP request checks and security headers (D-034, D-047), as one pure ASGI middleware.

Outermost application middleware, applied to every request (static files and errors included):
1. `Host` hostname must be the public host or a loopback name (else 400 `invalid_host`);
2. on non-GET/HEAD requests and on `/api/`, `Origin` and `Sec-Fetch-Site` must be same-origin
   (else 403 `forbidden_origin`);
3. non-GET/HEAD requests must be `application/json` (else 415 `unsupported_media_type`);
4. bodies above `MAX_BODY_BYTES` are refused (413 `payload_too_large`), from `Content-Length`
   before reading, or while counting a streamed body.
Every response gets the CSP, `Referrer-Policy`, `nosniff`, `Cache-Control: no-store` outside
`/static/`, and HSTS only when HTTPS is configured. Never a CORS header.
"""

from __future__ import annotations

import json

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 65536
SAFE_METHODS = frozenset({"GET", "HEAD"})
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})
ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})
JSON_MEDIA_TYPE = "application/json"
STATIC_PREFIX = "/static/"
API_PREFIX = "/api/"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'self'"
)
COMMON_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
NO_STORE = "no-store"
HSTS = "max-age=31536000"


class _RejectedError(Exception):
    """A request refused with an HTTP status and a stable error code."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class SecurityMiddleware:
    """Pure ASGI middleware: checks requests, then adds the security headers to every response."""

    def __init__(self, app: ASGIApp, *, public_host: str, https: bool) -> None:
        self.app = app
        self.allowed_hosts = LOOPBACK_HOSTS | {public_host.lower()}
        self.https = https

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        send_with_headers = self._with_headers(scope, send)
        try:
            self._check_headers(scope)
            if scope["method"] not in SAFE_METHODS:
                receive = await _bounded_body(receive)
        except _RejectedError as rejection:
            await _reject(rejection, send_with_headers)
            return
        await self.app(scope, receive, send_with_headers)

    def _check_headers(self, scope: Scope) -> None:
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        if hostname(host) not in self.allowed_hosts:
            raise _RejectedError(400, "invalid_host")
        method = scope["method"]
        if method not in SAFE_METHODS or scope["path"].startswith(API_PREFIX):
            self._check_origin(headers, host)
        if method not in SAFE_METHODS:
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != JSON_MEDIA_TYPE:
                raise _RejectedError(415, "unsupported_media_type")
            length = headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                raise _RejectedError(413, "payload_too_large")

    def _check_origin(self, headers: Headers, host: str) -> None:
        origin = headers.get("origin")
        scheme = "https" if self.https else "http"
        if origin is not None and origin.lower() != f"{scheme}://{host.lower()}":
            raise _RejectedError(403, "forbidden_origin")
        site = headers.get("sec-fetch-site")
        if site is not None and site.lower() not in ALLOWED_FETCH_SITES:
            raise _RejectedError(403, "forbidden_origin")

    def _with_headers(self, scope: Scope, send: Send) -> Send:
        static = scope["path"].startswith(STATIC_PREFIX)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in COMMON_HEADERS.items():
                    headers[name] = value
                if not static:
                    headers["Cache-Control"] = NO_STORE
                if self.https:
                    headers["Strict-Transport-Security"] = HSTS
            await send(message)

        return send_with_headers


def hostname(host: str) -> str:
    """The lowercase host name of a `Host` header value, port removed (`[::1]` keeps its brackets)."""
    host = host.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0] + "]" if "]" in host else host
    return host.rsplit(":", 1)[0] if ":" in host else host


async def _bounded_body(receive: Receive) -> Receive:
    """Read the whole body, refusing it as soon as it exceeds the limit; return a replaying `receive`."""
    chunks: list[bytes] = []
    size = 0
    more = True
    while more:
        message = await receive()
        if message["type"] == "http.disconnect":
            return _replay(message, receive)
        body = message.get("body", b"")
        size += len(body)
        if size > MAX_BODY_BYTES:
            raise _RejectedError(413, "payload_too_large")
        chunks.append(body)
        more = message.get("more_body", False)
    return _replay({"type": "http.request", "body": b"".join(chunks), "more_body": False}, receive)


def _replay(first: Message, receive: Receive) -> Receive:
    """`receive` that returns `first` once, then hands over to the real channel (disconnects)."""
    pending = [first]

    async def replaying() -> Message:
        if pending:
            return pending.pop()
        return await receive()

    return replaying


async def _reject(rejection: _RejectedError, send: Send) -> None:
    body = json.dumps({"error": rejection.code}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": rejection.status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
