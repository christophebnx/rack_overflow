"""Home page (`GET /`, docs/ui-spec.md "L4 — Home: start or resume"): the open session to resume,
or the start form (location, templates, « Séance libre »; D-061)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from rack_overflow.services import sessions
from rack_overflow.web.auth import device_user
from rack_overflow.web.forms import NO_ERRORS
from rack_overflow.web.rendering import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """Home: resume the open session, or start one."""
    page = sessions.start_page(request.app.state.engine, device_user(request))
    context = {"page": page, "location": page.location, "errors": NO_ERRORS}
    return render(request, "home.html", {**context, "title_key": "home.title", "current": "home"})
