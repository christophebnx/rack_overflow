"""Home page (`GET /`). L1a: empty state only (docs/ui-spec.md, L1a — Home)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from rack_overflow.web.rendering import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """The home page."""
    return render(request, "home.html", {"title_key": "home.title", "current": "home"})
