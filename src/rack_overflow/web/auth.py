"""Device authentication (D-040, D-049): a pure ASGI middleware, deny by default.

Public: `PAIRING_PATH` and everything under `/static/` (static requests skip the check entirely).
Every other path, existing or not, needs the `rack_device` cookie of an active paired device:
- a browser navigation (GET / HEAD) without one gets `303` to the pairing page;
- any other request gets `401 {"error": "not_paired"}`, plus `HX-Redirect` for htmx.
A cookie that did not authenticate is cleared on the response; a renewed device gets its cookie
re-sent with a fresh `Max-Age` (same token); neither when the route sets the device cookie
itself. The device, or None, is in `request.state.device`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.engine import Engine
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rack_overflow.domain.devices import TOKEN_LIFETIME
from rack_overflow.services import devices
from rack_overflow.web.errors import error_response, wants_page
from rack_overflow.web.security import SAFE_METHODS, STATIC_PREFIX

COOKIE_NAME = "rack_device"
PAIRING_PATH = "/appairage"
PUBLIC_PATHS = frozenset({PAIRING_PATH})
COOKIE_MAX_AGE = int(TOKEN_LIFETIME.total_seconds())


def _cookie(value: str, max_age: int, https: bool) -> str:
    secure = "; Secure" if https else ""
    return f"{COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}"


def device_cookie(token: str, https: bool) -> str:
    """`Set-Cookie` value carrying the device token (host-only, `Secure` only over HTTPS)."""
    return _cookie(token, COOKIE_MAX_AGE, https)


def cleared_cookie(https: bool) -> str:
    """`Set-Cookie` value that removes the device cookie."""
    return _cookie("", 0, https)


def is_public(path: str) -> bool:
    """True for the paths an unpaired browser may reach."""
    return path in PUBLIC_PATHS or path.startswith(STATIC_PREFIX)


def unpaired_response(request: Request) -> Response:
    """`303` to the pairing page for a navigation, else `401 not_paired` (`HX-Redirect` for htmx)."""
    if request.method in SAFE_METHODS and wants_page(request):
        return RedirectResponse(PAIRING_PATH, status_code=303)
    response = error_response(request, 401)
    if "hx-request" in request.headers:
        response.headers["HX-Redirect"] = PAIRING_PATH
    return response


class DeviceAuthMiddleware:
    """Authenticate the device cookie and refuse unpaired requests outside the public paths."""

    def __init__(self, app: ASGIApp, *, engine: Engine, clock: Callable[[], datetime], https: bool) -> None:
        self.app = app
        self.engine = engine
        self.clock = clock
        self.https = https

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(STATIC_PREFIX):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        token = request.cookies.get(COOKIE_NAME)
        device = None
        if token is not None:
            device = await run_in_threadpool(devices.authenticate, self.engine, token, self.clock())
        scope.setdefault("state", {})["device"] = device
        cookie = self._cookie_update(token, device)
        if device is None and not is_public(scope["path"]):
            response = unpaired_response(request)
            if cookie is not None:
                response.headers.append("set-cookie", cookie)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, _with_cookie(send, cookie))

    def _cookie_update(self, token: str | None, device: devices.Device | None) -> str | None:
        if token is None:
            return None
        if device is None:
            return cleared_cookie(self.https)
        return device_cookie(token, self.https) if device.renewed else None


def _sets_device_cookie(headers: MutableHeaders) -> bool:
    return any(value.startswith(f"{COOKIE_NAME}=") for value in headers.getlist("set-cookie"))


def _with_cookie(send: Send, cookie: str | None) -> Send:
    """`send` appending `cookie` to the response headers, unless the route already set the device
    cookie (pairing with a stale cookie: browsers apply `Set-Cookie` in order, so a clear or renewal
    of the old token appended after the new one would undo the pairing)."""
    if cookie is None:
        return send

    async def sending(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = MutableHeaders(scope=message)
            if not _sets_device_cookie(headers):
                headers.append("set-cookie", cookie)
        await send(message)

    return sending
