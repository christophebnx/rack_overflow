"""History pages (docs/ui-spec.md "L5 — History", "L5 — Session detail and corrections"; D-067,
D-070): the list with consistency and keyset pages, and the session delete with its in-place
confirmation. Thin: query → `services.history` / `services.sessions` → page or fragment."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from rack_overflow.domain.sessions import local_start
from rack_overflow.services import history, sessions
from rack_overflow.web.auth import device_user
from rack_overflow.web.forms import RowId, select_id
from rack_overflow.web.rendering import render

router = APIRouter()

HISTORY = "/historique"
SECTION = "history"


def _engine(request: Request) -> Any:
    return request.app.state.engine


def local_today(request: Request) -> str:
    """Today's local date (`YYYY-MM-DD`) from the injected clock in the configured zone (D-065)."""
    return local_start(request.app.state.clock(), request.app.state.settings.calendar.tz)[0]


@router.get(HISTORY, response_class=HTMLResponse)
def show_history(request: Request, avant: str | None = None, supprimee: str | None = None) -> Response:
    """The history page (`?avant={id}`: the page after that session); with `HX-Request` and
    `?avant`, the next items fragment of « Plus anciennes »."""
    user = device_user(request)
    before = select_id(avant)
    page = history.history_page(_engine(request), user, before)
    if before is not None and request.headers.get("HX-Request") == "true":
        return render(request, "history_page.html", {"page": page, "fragment": True})
    consistency = (
        history.consistency(_engine(request), user, local_today(request)) if before is None else None
    )
    context = {
        "page": page,
        "consistency": consistency,
        "deleted": supprimee == "1",
        "title_key": "history.title",
        "section": SECTION,
    }
    return render(request, "history.html", context)


@router.get("/seances/{session_id}/suppression", response_class=HTMLResponse)
def delete_session_confirm(request: Request, session_id: RowId, annuler: str | None = None) -> Response:
    """The in-place confirmation of a session delete (`?annuler=1` puts the button back)."""
    sessions.info(_engine(request), device_user(request), session_id)
    if annuler == "1":
        return render(request, "session_delete.html", {"session_id": session_id, "focus": "seance-supprimer"})
    return render(request, "session_delete_confirm.html", {"session_id": session_id})


@router.delete("/seances/{session_id}", response_class=HTMLResponse)
def delete_session(request: Request, session_id: RowId) -> Response:
    """Soft delete a session, open or closed (D-067) → the history with its notice."""
    sessions.delete_session(_engine(request), device_user(request), session_id, request.app.state.clock())
    return Response(status_code=204, headers={"HX-Redirect": f"{HISTORY}?supprimee=1"})
