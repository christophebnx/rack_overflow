"""Session logging pages (docs/ui-spec.md "L4 — Home", "L4 — Session page", "L4 — Session
summary", "L5 — Session detail and corrections"; D-050, D-053, D-061 to D-067). Thin: JSON body
or query → `services.sessions` → page or fragment. Refused input re-renders the fragment `200` with
messages per input (D-050); a set or setting correction of a closed session answers the detail's
exercise section (D-067), any other write on a closed session `HX-Redirect` to its summary with
`?terminee=1`; unknown, foreign or deleted ids are 404.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.sessions import Item, SessionError
from rack_overflow.domain.text import is_digits
from rack_overflow.services import sessions
from rack_overflow.services.sessions import FieldInfo, SessionView, SetRef, SummaryRow, SummaryView
from rack_overflow.web.auth import device_user
from rack_overflow.web.display import Display
from rack_overflow.web.forms import NO_ERRORS, FormErrors, RowId, form_errors, in_id_range, select_id
from rack_overflow.web.rendering import render

router = APIRouter()

SESSIONS = "/seances"
TEXT_MAX = 200
START_ERROR_ID = "demarrer-modele"
PLAN_ID = "seance-plan"
"""Id of the plan `<ol>` (`session_plan.html`): the start redirect scrolls to it (the current item
is the first one after a start), so the first ✓ is above the fold of a 640 px phone."""
FORM_KEYS = frozenset({"type", "session_exercise_id", "pas"})


class StartBody(BaseModel):
    """The start form: the submitter's `template_id` (empty: free session) and the location."""

    template_id: str | None = Field(default=None, max_length=TEXT_MAX)
    location: str | None = Field(default=None, max_length=TEXT_MAX)


class PickBody(BaseModel):
    """A menu pick (`slot_id`) or an added exercise (no slot)."""

    slot_id: str | None = Field(default=None, max_length=TEXT_MAX)
    exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)


class ChangeBody(BaseModel):
    """The new exercise of a row without facts."""

    exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)


class ValuesBody(BaseModel):
    """A set, set edit or settings form: the set type, the row and one text per field (`reps`,
    `weight`, `duration`, `distance`, `var_<id>`), each at most 200 characters."""

    model_config = ConfigDict(extra="allow")

    type: str | None = Field(default=None, max_length=TEXT_MAX)
    session_exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)

    def values(self) -> dict[str, str | None]:
        """The field texts (anything that is not a single string is read as empty)."""
        return _texts(self.model_extra or {})


def _texts(raw: Mapping[str, Any]) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for name, value in raw.items():
        if name in FORM_KEYS:
            continue
        if isinstance(value, str) and len(value) > TEXT_MAX:
            raise HTTPException(status_code=422)
        found[name] = value if isinstance(value, str) else None
    return found


# --- helpers


def _engine(request: Request) -> Any:
    return request.app.state.engine


def _now(request: Request) -> Any:
    return request.app.state.clock()


def _text(request: Request, key: str, **params: object) -> str:
    return str(request.app.state.catalog.text(key, **params))


def _errors(request: Request, error: CatalogError, ids: Mapping[str, str], fallback: str) -> FormErrors:
    return form_errors(request.app.state.catalog, error, ids, fallback)


def _closed(session_id: int) -> Response:
    """The answer to any write on a closed session: its summary, with the notice."""
    return Response(status_code=204, headers={"HX-Redirect": f"{SESSIONS}/{session_id}?terminee=1"})


def _query_id(raw: str | None) -> int | None:
    """An id from the query string; anything else is ignored (default current item)."""
    if raw is None or not is_digits(raw):
        return None
    value = int(raw)
    return value if in_id_range(value) else None


def _title(request: Request, title: str | None) -> str:
    return title or _text(request, "session.free_title")


def _context(view: SessionView, **extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "view": view,
        "session_id": view.session.id,
        "errors": NO_ERRORS,
        "no_errors": NO_ERRORS,
        "edit": None,
        "settings_errors": NO_ERRORS,
        "settings_saved": False,
        "settings_texts": None,
        "settings_oob": False,
        "change_errors": NO_ERRORS,
        "menu_errors": NO_ERRORS,
        "plan_oob": False,
        "focus": None,
        "announce": None,
    }
    context.update(extra)
    return context


def _field_ids(fields: tuple[FieldInfo, ...], prefix: str) -> dict[str, str]:
    """Problem field → input id of a set form (`<prefix>-<field>`, the type chips, the form)."""
    ids = {item.name: f"{prefix}-{item.name}" for item in fields}
    ids.update({"type": f"{prefix}-type", "set": f"{prefix}-serie"})
    return ids


def _block_fields(view: SessionView) -> tuple[FieldInfo, ...]:
    assert view.block is not None
    return view.block.fields


def detail_context(summary: SummaryView, **extra: Any) -> dict[str, Any]:
    """The context of a closed session's detail page or of one of its exercise sections."""
    context: dict[str, Any] = {
        "summary": summary,
        "session_id": summary.session.id,
        "no_errors": NO_ERRORS,
        "edit": None,
        "settings_errors": NO_ERRORS,
        "settings_saved": False,
        "settings_texts": None,
        "settings_oob": False,
        "totals_oob": False,
        "focus": None,
        "announce": None,
    }
    context.update(extra)
    return context


def _detail_row(summary: SummaryView, row_id: int) -> SummaryRow:
    found = summary.row(row_id)
    if found is None:
        raise HTTPException(status_code=404)
    return found


def _render_detail(request: Request, summary: SummaryView, row_id: int, **extra: Any) -> HTMLResponse:
    """The exercise section of a closed session's detail, totals out of band (D-067)."""
    context = detail_context(summary, r=_detail_row(summary, row_id), totals_oob=True, **extra)
    return render(request, "session_detail_exercise.html", context)


# --- start


@router.post(SESSIONS, response_class=HTMLResponse)
def start_session(request: Request, body: StartBody) -> Response:
    """Start a session (also answers with the open one: double tap, other device) → its page."""
    user = device_user(request)
    try:
        session_id = sessions.start(
            _engine(request),
            user,
            select_id(body.template_id),
            body.location,
            _now(request),
            request.app.state.settings.calendar.tz,
        )
    except CatalogError as error:
        page = sessions.start_page(_engine(request), user)
        location = body.location if body.location in ("gym", "home") else page.location
        errors = _errors(request, error, {}, START_ERROR_ID)
        return render(request, "home_start_form.html", {"page": page, "location": location, "errors": errors})
    return Response(status_code=204, headers={"HX-Redirect": f"{SESSIONS}/{session_id}#{PLAN_ID}"})


# --- session page


@router.get(SESSIONS + "/{session_id}", response_class=HTMLResponse)
def show_session(
    request: Request,
    session_id: RowId,
    exercice: str | None = None,
    menu: str | None = None,
    terminee: str | None = None,
) -> HTMLResponse:
    """The open session with its current item, or the summary of a closed one."""
    row, slot = _query_id(exercice), _query_id(menu)
    requested = Item(row_id=row) if row is not None else Item(menu_slot_id=slot) if slot is not None else None
    found = sessions.show(_engine(request), device_user(request), session_id, requested)
    if isinstance(found, SummaryView):
        context = detail_context(
            found,
            closed_notice=terminee == "1",
            page_title=_title(request, found.session.title),
            section="history",
        )
        return render(request, "session_summary.html", context)
    results = sessions.search_exercises(_engine(request), device_user(request), session_id, "")
    context = _context(found, page_title=_title(request, found.session.title), results=results)
    return render(request, "session.html", context)


@router.post(SESSIONS + "/{session_id}/exercices", response_class=HTMLResponse)
def add_session_exercise(request: Request, session_id: RowId, body: PickBody) -> Response:
    """Pick a menu's exercise, or add one outside the template → the plan, the new row current."""
    user = device_user(request)
    slot_id, exercise_id = select_id(body.slot_id), select_id(body.exercise_id)
    try:
        view = sessions.pick(_engine(request), user, session_id, slot_id, exercise_id)
    except SessionError:
        return _closed(session_id)
    except CatalogError as error:
        requested = Item(menu_slot_id=slot_id) if slot_id is not None else None
        current = sessions.show(_engine(request), user, session_id, requested)
        assert isinstance(current, SessionView)
        errors = _errors(request, error, {}, f"menu-{slot_id}")
        context = _context(current, menu_errors=errors, announce=errors.first_message)
        return render(request, "session_plan.html", context)
    assert view.block is not None
    key = "session.announce_picked" if slot_id is not None else "session.announce_added"
    context = _context(
        view,
        focus=f"exercice-{view.block.id}-valider",
        announce=_text(request, key, name=view.block.exercise.name),
        plan_oob=slot_id is None,
        results=sessions.search_exercises(_engine(request), user, session_id, ""),
    )
    return render(request, "session_plan.html", context)


@router.patch(SESSIONS + "/{session_id}/exercices/{row_id}", response_class=HTMLResponse)
def change_session_exercise(request: Request, session_id: RowId, row_id: RowId, body: ChangeBody) -> Response:
    """Change the exercise of a row holding no fact → the plan, the row current."""
    user = device_user(request)
    try:
        view = sessions.change_exercise(
            _engine(request), user, session_id, row_id, select_id(body.exercise_id)
        )
    except SessionError:
        return _closed(session_id)
    except CatalogError as error:
        current = sessions.show(_engine(request), user, session_id, Item(row_id=row_id))
        assert isinstance(current, SessionView)
        errors = _errors(request, error, {}, f"exercice-{row_id}-changer")
        context = _context(current, change_errors=errors, announce=errors.first_message)
        return render(request, "session_plan.html", context)
    assert view.block is not None
    context = _context(
        view,
        focus=f"exercice-{row_id}-valider",
        announce=_text(request, "session.announce_picked", name=view.block.exercise.name),
    )
    return render(request, "session_plan.html", context)


@router.get(SESSIONS + "/{session_id}/recherche", response_class=HTMLResponse)
def search_session_exercises(
    request: Request, session_id: RowId, q: str = "", ligne: str | None = None
) -> Response:
    """Results of « Ajouter un exercice » (`?ligne=` changes that added row instead); a browser
    navigation is sent to the session page."""
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(f"{SESSIONS}/{session_id}", status_code=303)
    results = sessions.search_exercises(_engine(request), device_user(request), session_id, q[:TEXT_MAX])
    context = {"results": results, "session_id": session_id, "change_row": _query_id(ligne)}
    return render(request, "session_search_results.html", context)


# --- sets


@router.get(SESSIONS + "/{session_id}/exercices/{row_id}/serie", response_class=HTMLResponse)
def set_form(request: Request, session_id: RowId, row_id: RowId) -> Response:
    """The set form after one stepper tap (`?pas=<field>:<up|down>` with the form's values): no write."""
    query = request.query_params
    try:
        view = sessions.set_form(
            _engine(request),
            device_user(request),
            session_id,
            row_id,
            query.get("type"),
            _texts(dict(query)),
            query.get("pas"),
        )
    except SessionError:
        return _closed(session_id)
    return render(request, "session_set_form.html", _context(view))


@router.post(SESSIONS + "/{session_id}/series", response_class=HTMLResponse)
def confirm_set(request: Request, session_id: RowId, body: ValuesBody) -> Response:
    """Confirm the next set of a row → its block: the set (⭐ when a record), the next form."""
    user = device_user(request)
    row_id = select_id(body.session_exercise_id)
    if row_id is None:
        raise HTTPException(status_code=422)
    values = body.values()
    try:
        confirmed = sessions.confirm_set(
            _engine(request), user, session_id, row_id, body.type, values, _now(request)
        )
    except SessionError:
        return _closed(session_id)
    except CatalogError as error:
        try:
            view = sessions.set_form(_engine(request), user, session_id, row_id, body.type, values)
        except SessionError:
            return _closed(session_id)
        errors = _errors(
            request, error, _field_ids(_block_fields(view), f"exercice-{row_id}"), f"exercice-{row_id}-serie"
        )
        return render(
            request, "session_exercise.html", _context(view, errors=errors, announce=errors.first_message)
        )
    view, done = confirmed.view, confirmed.set
    assert view.block is not None
    text = Display(request.app.state.catalog).set_text(done.facts, view.block.fields)
    key = "session.announce_set_record" if done.record else "session.announce_set_saved"
    context = _context(
        view, focus=f"exercice-{row_id}-valider", announce=_text(request, key, n=done.number, text=text)
    )
    return render(request, "session_exercise.html", context)


def _update_closed_set(request: Request, where: SetRef, set_id: int, body: ValuesBody) -> Response:
    """Correct a set of a closed session (D-067) → its exercise section of the detail."""
    user, values = device_user(request), body.values()
    try:
        answer = sessions.update_set(_engine(request), user, set_id, body.type, values, require_open=False)
    except CatalogError as error:
        summary = sessions.detail(_engine(request), user, where.session_id, where.row_id)
        prefix = f"serie-{set_id}"
        fields = _detail_row(summary, where.row_id).fields
        errors = _errors(request, error, _field_ids(fields, prefix), f"{prefix}-serie")
        edit = {"set_id": set_id, "texts": values, "type": body.type, "errors": errors}
        return _render_detail(request, summary, where.row_id, edit=edit, announce=errors.first_message)
    assert isinstance(answer, SummaryView)
    updated = _detail_row(answer, where.row_id).set(set_id)
    number = updated.number if updated is not None else 0
    announce = _text(request, "session.announce_set_updated", n=number)
    return _render_detail(request, answer, where.row_id, focus=f"serie-{set_id}-modifier", announce=announce)


@router.patch("/series/{set_id}", response_class=HTMLResponse)
def update_set(request: Request, set_id: RowId, body: ValuesBody) -> Response:
    """Correct a set → its row's block (open session) or its exercise section (closed, D-067)."""
    user = device_user(request)
    where = sessions.locate_set(_engine(request), user, set_id)
    if where.closed:
        return _update_closed_set(request, where, set_id, body)
    values = body.values()
    try:
        view = sessions.update_set(_engine(request), user, set_id, body.type, values)
    except SessionError:
        return _closed(where.session_id)
    except CatalogError as error:
        view = sessions.block(_engine(request), user, where.session_id, where.row_id)
        prefix = f"serie-{set_id}"
        errors = _errors(request, error, _field_ids(_block_fields(view), prefix), f"{prefix}-serie")
        edit = {"set_id": set_id, "texts": values, "type": body.type, "errors": errors}
        return render(
            request, "session_exercise.html", _context(view, edit=edit, announce=errors.first_message)
        )
    assert isinstance(view, SessionView) and view.block is not None
    updated = view.block.set(set_id)
    number = updated.number if updated is not None else 0
    context = _context(
        view,
        focus=f"serie-{set_id}-modifier",
        announce=_text(request, "session.announce_set_updated", n=number),
    )
    return render(request, "session_exercise.html", context)


def _delete_closed_set(request: Request, where: SetRef, set_id: int) -> Response:
    """Soft delete a set of a closed session (D-067) → its exercise section; focus on the next
    row's « Modifier », else the previous one, else « Voir la progression »."""
    user = device_user(request)
    before = _detail_row(
        sessions.detail(_engine(request), user, where.session_id, where.row_id), where.row_id
    )
    answer = sessions.delete_set(_engine(request), user, set_id, _now(request), require_open=False)
    assert isinstance(answer, SummaryView)
    deleted = before.set(set_id)
    number = deleted.number if deleted is not None else 0
    remaining = _detail_row(answer, where.row_id).sets
    if number and number <= len(remaining):
        focus = f"serie-{remaining[number - 1].id}-modifier"
    elif remaining:
        focus = f"serie-{remaining[-1].id}-modifier"
    else:
        focus = f"exercice-{where.row_id}-progression"
    announce = _text(request, "session.announce_set_deleted", n=number)
    return _render_detail(request, answer, where.row_id, focus=focus, announce=announce)


@router.delete("/series/{set_id}", response_class=HTMLResponse)
def delete_set(request: Request, set_id: RowId) -> Response:
    """Soft delete a set → its row's block, rows renumbered (open session), or its exercise
    section (closed, D-067)."""
    user = device_user(request)
    where = sessions.locate_set(_engine(request), user, set_id)
    if where.closed:
        return _delete_closed_set(request, where, set_id)
    try:
        before = sessions.block(_engine(request), user, where.session_id, where.row_id)
        view = sessions.delete_set(_engine(request), user, set_id, _now(request))
    except SessionError:
        return _closed(where.session_id)
    assert before.block is not None and isinstance(view, SessionView) and view.block is not None
    deleted = before.block.set(set_id)
    number = deleted.number if deleted is not None else 0
    remaining = view.block.sets
    if number and number <= len(remaining):
        focus = f"serie-{remaining[number - 1].id}-modifier"
    elif remaining:
        focus = f"serie-{remaining[-1].id}-modifier"
    else:
        focus = f"exercice-{where.row_id}-valider"
    announce = _text(request, "session.announce_set_deleted", n=number)
    return render(request, "session_exercise.html", _context(view, focus=focus, announce=announce))


def _save_closed_settings(
    request: Request, session_id: int, row_id: int, values: dict[str, str | None]
) -> Response:
    """Correct the settings of a closed session's row (D-067) → the same settings form."""
    user = device_user(request)
    try:
        answer = sessions.save_settings(
            _engine(request), user, session_id, row_id, values, require_open=False
        )
    except CatalogError as error:
        summary = sessions.detail(_engine(request), user, session_id, row_id)
        row = _detail_row(summary, row_id)
        prefix = f"exercice-{row_id}-reglages"
        errors = _errors(
            request, error, {item.name: f"{prefix}-{item.name}" for item in row.setting_fields}, prefix
        )
        context = detail_context(
            summary,
            settings_row=row,
            settings_errors=errors,
            settings_texts=values,
            announce=errors.first_message,
        )
        return render(request, "session_settings.html", {**context, "settings_oob": True})
    assert isinstance(answer, SummaryView)
    saved = _text(request, "session.settings_saved")
    context = detail_context(
        answer,
        settings_row=_detail_row(answer, row_id),
        settings_saved=True,
        settings_oob=True,
        announce=saved,
    )
    return render(request, "session_settings.html", context)


@router.patch(SESSIONS + "/{session_id}/exercices/{row_id}/reglages", response_class=HTMLResponse)
def save_settings(request: Request, session_id: RowId, row_id: RowId, body: ValuesBody) -> Response:
    """Save the row's settings (sent on each change) → the settings form, its summary out of band;
    on a closed session, the correction of the detail (D-067)."""
    user = device_user(request)
    values = body.values()
    try:
        view = sessions.save_settings(_engine(request), user, session_id, row_id, values)
    except SessionError:
        return _save_closed_settings(request, session_id, row_id, values)
    except CatalogError as error:
        view = sessions.block(_engine(request), user, session_id, row_id)
        prefix = f"exercice-{row_id}-reglages"
        assert view.block is not None
        ids = {item.name: f"{prefix}-{item.name}" for item in view.block.setting_fields}
        errors = _errors(request, error, ids, prefix)
        context = _context(view, settings_errors=errors, settings_texts=values, announce=errors.first_message)
        return render(request, "session_settings.html", {**context, "settings_oob": True})
    assert isinstance(view, SessionView)
    saved = _text(request, "session.settings_saved")
    context = _context(view, settings_saved=True, settings_oob=True, announce=saved)
    return render(request, "session_settings.html", context)


# --- close


@router.get(SESSIONS + "/{session_id}/cloture", response_class=HTMLResponse)
def close_confirm(request: Request, session_id: RowId, annuler: str | None = None) -> Response:
    """The in-place close confirmation (`?annuler=1` puts « Terminer la séance » back)."""
    try:
        unlogged = sessions.unlogged_count(_engine(request), device_user(request), session_id)
    except SessionError:
        return _closed(session_id)
    if annuler == "1":
        return render(request, "session_close.html", {"session_id": session_id, "focus": "terminer"})
    return render(request, "session_close_confirm.html", {"session_id": session_id, "unlogged": unlogged})


@router.post(SESSIONS + "/{session_id}/cloture", response_class=HTMLResponse)
def close_session(request: Request, session_id: RowId) -> Response:
    """Close the session → its summary (a closed session stays as it is)."""
    sessions.close(_engine(request), device_user(request), session_id, _now(request))
    return Response(status_code=204, headers={"HX-Redirect": f"{SESSIONS}/{session_id}"})
