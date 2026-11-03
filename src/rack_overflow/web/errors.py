"""HTTP errors: an error page for a browser navigation, a stable JSON code otherwise (D-036, D-047).

The error page reads no data, so it renders even when the database or a service fails.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rack_overflow.web.rendering import render
from rack_overflow.web.security import PAYLOAD_TOO_LARGE, UNSUPPORTED_MEDIA_TYPE

logger = logging.getLogger(__name__)

# HTTP status -> stable English error code (JSON answers)
CODES: dict[int, str] = {
    400: "bad_request",
    401: "not_paired",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: PAYLOAD_TOO_LARGE,
    415: UNSUPPORTED_MEDIA_TYPE,
    422: "invalid_request",
    500: "internal",
}
# error code -> message key in the catalog (explicit: no dynamic key lookup)
MESSAGE_KEYS: dict[str, str] = {
    "not_found": "error.not_found",
    "not_paired": "error.not_paired",
    "internal": "error.internal",
    "method_not_allowed": "error.method_not_allowed",
    PAYLOAD_TOO_LARGE: "error.payload_too_large",
    UNSUPPORTED_MEDIA_TYPE: "error.unsupported_media_type",
}
TITLE_KEYS: dict[int, str] = {404: "error.title.not_found", 500: "error.title.internal"}
GENERIC_CODE = "error"
GENERIC_TITLE_KEY = "error.title.generic"
GENERIC_MESSAGE_KEY = "error.generic"


def wants_page(request: Request) -> bool:
    """True for a browser navigation: HTML accepted and not an htmx request."""
    return "text/html" in request.headers.get("accept", "") and "hx-request" not in request.headers


def error_response(request: Request, status: int) -> Response:
    """The answer to an HTTP error: the error page or `{"error": <code>}`."""
    code = CODES.get(status, GENERIC_CODE)
    if not wants_page(request):
        return JSONResponse({"error": code}, status_code=status)
    context = {
        "title_key": TITLE_KEYS.get(status, GENERIC_TITLE_KEY),
        "message_key": MESSAGE_KEYS.get(code, GENERIC_MESSAGE_KEY),
        "status": status,
        "retry_path": _retry_path(request) if status >= 500 else None,
    }
    return render(request, "error.html", context, status=status)


def _retry_path(request: Request) -> str:
    """The current path as sent (still percent-encoded, no query) as a same-origin link.

    The raw path keeps `%3F` encoded, so retrying goes to the same address; `//host` would leave the site.
    """
    raw = request.scope.get("raw_path")
    path = raw.decode("latin-1") if isinstance(raw, bytes) else request.url.path
    return "/" + path.lstrip("/")


async def _http_error(request: Request, error: Exception) -> Response:
    status = error.status_code if isinstance(error, HTTPException) else 400
    response = error_response(request, status)
    if isinstance(error, HTTPException) and error.headers:
        response.headers.update(error.headers)
    return response


async def _validation_error(request: Request, error: Exception) -> Response:
    del error
    return error_response(request, 422)


class UnhandledErrorMiddleware:
    """Turn an unhandled exception into the 500 answer, inside the security middleware (its headers apply)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("unhandled error on %s %s", scope["method"], scope["path"])
            if started:
                raise
            response = error_response(Request(scope), 500)
            await response(scope, receive, send)


def install(app: FastAPI) -> None:
    """Register the error handlers and the unhandled-error middleware on `app`."""
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_middleware(UnhandledErrorMiddleware)
