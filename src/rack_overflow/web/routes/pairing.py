"""Pairing page (`GET` / `POST /appairage`, docs/ui-spec.md "L1b — Pairing", D-049, D-050).

Public: reachable without a paired device. A refusal is answered `200` with the form re-rendered
in place (D-050); a success sets the device cookie and sends htmx to the home page.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from rack_overflow.domain.devices import PairingOutcome
from rack_overflow.services import devices
from rack_overflow.web.auth import PAIRING_PATH, device_cookie
from rack_overflow.web.rendering import render

logger = logging.getLogger(__name__)
router = APIRouter()

CODE_MAX_LENGTH = 32
HOME_PATH = "/"
# refusal outcome -> message key (explicit: no dynamic key lookup)
REFUSAL_KEYS: dict[PairingOutcome, str] = {
    PairingOutcome.WRONG_CODE: "pairing.wrong_code",
    PairingOutcome.CODE_EXPIRED: "pairing.code_expired",
    PairingOutcome.TOO_MANY_ATTEMPTS: "pairing.too_many_attempts",
}
WRONG_CODE_REMAINING_KEY = "pairing.wrong_code_remaining"


class PairingRequest(BaseModel):
    """JSON body of the pairing form (`json-enc`)."""

    code: str = Field(max_length=CODE_MAX_LENGTH)


def _form_context(message_key: str | None = None, **params: Any) -> dict[str, Any]:
    return {
        "pairing_path": PAIRING_PATH,
        "paired": False,
        "message_key": message_key,
        "message_params": params,
    }


@router.get(PAIRING_PATH, response_class=HTMLResponse)
def pairing_page(request: Request) -> HTMLResponse:
    """The code form, or the "already paired" state for a paired device."""
    context = {"title_key": "pairing.title", "already_paired": request.state.device is not None}
    return render(request, "pairing.html", {**context, **_form_context()})


@router.post(PAIRING_PATH, response_class=HTMLResponse)
def pair(request: Request, body: PairingRequest) -> HTMLResponse:
    """Check the typed code: pair this browser, or re-render the form with the refusal."""
    state = request.app.state
    result = devices.pair(state.engine, body.code, state.clock())
    if result.outcome is PairingOutcome.PAIRED and result.token is not None:
        logger.info('device "%s" paired', result.device_name)
        response = render(request, "pairing_form.html", {**_form_context(), "paired": True})
        response.headers.append("set-cookie", device_cookie(result.token, state.settings.server.https))
        response.headers["HX-Redirect"] = HOME_PATH
        return response
    logger.warning("pairing refused: %s", result.outcome.value)
    if result.outcome is PairingOutcome.WRONG_CODE and result.remaining_attempts is not None:
        context = _form_context(WRONG_CODE_REMAINING_KEY, remaining=result.remaining_attempts)
    else:
        context = _form_context(REFUSAL_KEYS[result.outcome])
    return render(request, "pairing_form.html", {**context, "announce": True})
