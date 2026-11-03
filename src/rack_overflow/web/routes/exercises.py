"""Exercise pages (docs/ui-spec.md "L2 — Exercise list and search", "L2 — New exercise",
"L2 — Exercise detail"; D-050, D-054, D-056). Thin: JSON body → `services.exercises` → page or
fragment. Refused input re-renders the fragment `200` (D-050); an unknown or foreign id is a 404.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from rack_overflow.domain.catalog import CatalogError, Problem
from rack_overflow.domain.vocabulary import EXERCISE_CATEGORIES, LOCATIONS
from rack_overflow.services import exercises
from rack_overflow.services.exercises import ExerciseDetail, ExerciseForm, FieldForm, FieldView
from rack_overflow.web.forms import NO_ERRORS, FormErrors, checked, form_errors
from rack_overflow.web.rendering import render

router = APIRouter()

TEXT_MAX = 200
VALUES_MAX = 2000
LIST_PATH = "/exercices"
SEARCH_PATH = LIST_PATH + "/recherche"
SAVED_KEY = "status.saved"
DEFAULT_LOCATION = "both"
CORE_PREFIX = "core:"
VARIABLE_PREFIX = "variable:"
STEP_MODE = "step"
VALUES_MODE = "values"
# problem field -> input id of the exercise form
EXERCISE_IDS = {
    "name": "nom",
    "category": "categorie-strength",
    "location": "lieu-gym",
    "movement_pattern": "mouvement",
    "equipment": "equipement",
}
ADD_ID = "champ-ajout"
ALIAS_ID = "alias-nouveau"
QUANTITY_KEYS = {
    "reps": "quantity.reps",
    "weight": "quantity.weight",
    "duration": "quantity.duration",
    "distance": "quantity.distance",
}
Many = str | list[str] | None


class ExerciseBody(BaseModel):
    """JSON body of the exercise form (`json-enc`)."""

    name: str | None = Field(default=None, max_length=TEXT_MAX)
    category: str | None = Field(default=None, max_length=TEXT_MAX)
    location: str | None = Field(default=None, max_length=TEXT_MAX)
    movement_pattern: str | None = Field(default=None, max_length=TEXT_MAX)
    equipment: str | None = Field(default=None, max_length=TEXT_MAX)

    def form(self) -> ExerciseForm:
        """The service form."""
        return ExerciseForm(self.name, self.category, self.location, self.movement_pattern, self.equipment)


class AddFieldBody(BaseModel):
    """`source`: `core:<quantity>` or `variable:<id>`."""

    source: str | None = Field(default=None, max_length=TEXT_MAX)


class FieldBody(BaseModel):
    """A field's parameters as typed (display units); only the input of the chosen mode counts."""

    required: Many = None
    mode: str | None = Field(default=None, max_length=TEXT_MAX)
    increment: str | None = Field(default=None, max_length=TEXT_MAX)
    discrete_values: str | None = Field(default=None, max_length=VALUES_MAX)
    default: str | None = Field(default=None, max_length=TEXT_MAX)


class MoveBody(BaseModel):
    """`direction`: `up` or `down`."""

    direction: Literal["up", "down"]


class AliasBody(BaseModel):
    """A new alias."""

    alias: str | None = Field(default=None, max_length=TEXT_MAX)


def _user(request: Request) -> int:
    return int(request.state.device.user_id)


def _engine(request: Request) -> Any:
    return request.app.state.engine


def _text(request: Request, key: str, **params: object) -> str:
    return str(request.app.state.catalog.text(key, **params))


def field_name(request: Request, field: FieldView) -> str:
    """The displayed name of a field: the core quantity's word or the variable's label."""
    if field.variable is not None:
        return field.variable.draft.label
    return _text(request, QUANTITY_KEYS[field.core_quantity or ""])


# --- list and search


def _results_context(request: Request, q: str, show_archived: bool) -> dict[str, Any]:
    user, engine = _user(request), _engine(request)
    if q.strip():
        found = exercises.search_exercises(engine, user, q, include_archived=show_archived)
        groups: list[tuple[str | None, list[exercises.ExerciseSummary]]] = [(None, found)]
    else:
        found = exercises.list_exercises(engine, user, include_archived=show_archived)
        groups = [(c, [e for e in found if e.draft.category == c]) for c in EXERCISE_CATEGORIES]
    return {"q": q, "show_archived": show_archived, "groups": groups, "count": len(found)}


@router.get(LIST_PATH, response_class=HTMLResponse)
def list_exercises(request: Request, q: str = "", archives: str | None = None) -> HTMLResponse:
    """The exercise list with its search box (grouped by category when the search is empty)."""
    context = _results_context(request, q[:TEXT_MAX], archives == "1")
    return render(
        request, "exercises.html", {**context, "title_key": "exercises.title", "section": "exercises"}
    )


@router.get(SEARCH_PATH, response_class=HTMLResponse)
def search_exercises(request: Request, q: str = "", archives: str | None = None) -> Response:
    """The results fragment for htmx (URL kept in the history); a navigation gets the page."""
    query = {"q": q[:TEXT_MAX], **({"archives": "1"} if archives == "1" else {})}
    page_url = f"{LIST_PATH}?{urlencode(query)}"
    if "hx-request" not in request.headers:
        return RedirectResponse(page_url, status_code=303)
    context = _results_context(request, q[:TEXT_MAX], archives == "1")
    response = render(request, "exercise_results.html", {**context, "announce_count": True})
    response.headers["HX-Replace-Url"] = page_url
    return response


# --- create and edit


def _form_values(draft: Any = None, body: ExerciseBody | None = None) -> dict[str, Any]:
    if body is not None:
        return body.model_dump()
    if draft is None:
        return {
            "name": "",
            "category": None,
            "location": DEFAULT_LOCATION,
            "movement_pattern": "",
            "equipment": "",
        }
    return {
        "name": draft.name,
        "category": draft.category,
        "location": draft.location,
        "movement_pattern": draft.movement_pattern or "",
        "equipment": draft.equipment or "",
    }


def _exercise_form_context(
    request: Request,
    *,
    detail: ExerciseDetail | None,
    values: dict[str, Any],
    errors: FormErrors = NO_ERRORS,
    saved: bool = False,
) -> dict[str, Any]:
    suggestions = exercises.suggestions(_engine(request), _user(request))
    announce = errors.first_message or (_text(request, SAVED_KEY) if saved else None)
    return {
        "detail": detail,
        "form": values,
        "errors": errors,
        "saved": saved,
        "suggestions": suggestions,
        "categories": EXERCISE_CATEGORIES,
        "locations": LOCATIONS,
        "announce": announce,
    }


@router.get(LIST_PATH + "/nouveau", response_class=HTMLResponse)
def new_exercise(request: Request) -> HTMLResponse:
    """The create form."""
    context = _exercise_form_context(request, detail=None, values=_form_values())
    context.update({"title_key": "exercise.new_title", "section": "exercises", "announce": None})
    return render(request, "exercise_new.html", context)


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_exercise(request: Request, body: ExerciseBody) -> Response:
    """Create the exercise with its default fields → its page."""
    try:
        exercise_id = exercises.create(_engine(request), _user(request), body.form())
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, EXERCISE_IDS, "nom")
        context = _exercise_form_context(request, detail=None, values=_form_values(body=body), errors=errors)
        return render(request, "exercise_form.html", context)
    return Response(status_code=204, headers={"HX-Redirect": f"{LIST_PATH}/{exercise_id}"})


def _detail(request: Request, exercise_id: int) -> ExerciseDetail:
    return exercises.get_detail(_engine(request), _user(request), exercise_id)


@router.get(LIST_PATH + "/{exercise_id}", response_class=HTMLResponse)
def show_exercise(request: Request, exercise_id: int, ajout: str | None = None) -> HTMLResponse:
    """The exercise page; `?ajout={variable_id}` preselects that variable in « Ajouter un champ »."""
    detail = _detail(request, exercise_id)
    selected = f"{VARIABLE_PREFIX}{ajout}" if ajout and ajout.isdigit() else None
    context = _exercise_form_context(request, detail=detail, values=_form_values(detail.draft))
    context.update(_fields_context(request, detail, selected=selected, focus=ADD_ID if selected else None))
    context.update(
        {"page_title": detail.draft.name, "section": "exercises", "announce": None, "alias_errors": NO_ERRORS}
    )
    context.update({"alias_value": "", "alias_focus": False, "archive_focus": None})
    return render(request, "exercise.html", context)


@router.patch(LIST_PATH + "/{exercise_id}", response_class=HTMLResponse)
def update_exercise(request: Request, exercise_id: int, body: ExerciseBody) -> HTMLResponse:
    """Save the exercise's attributes; the form comes back saved or with its refusals."""
    detail = _detail(request, exercise_id)
    try:
        exercises.update(_engine(request), _user(request), exercise_id, body.form())
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, EXERCISE_IDS, "nom")
        context = _exercise_form_context(
            request, detail=detail, values=_form_values(body=body), errors=errors
        )
        return render(request, "exercise_form.html", context)
    saved = _detail(request, exercise_id)
    context = _exercise_form_context(request, detail=saved, values=_form_values(saved.draft), saved=True)
    return render(request, "exercise_form.html", {**context, "retitle": True})


def _archive_response(request: Request, exercise_id: int, focus: str, key: str) -> HTMLResponse:
    context = {"detail": _detail(request, exercise_id), "archive_focus": focus, "oob_state": True}
    return render(request, "exercise_archive.html", {**context, "announce": _text(request, key)})


@router.post(LIST_PATH + "/{exercise_id}/archive", response_class=HTMLResponse)
def archive_exercise(request: Request, exercise_id: int) -> HTMLResponse:
    """Archive the exercise (history untouched)."""
    exercises.set_archived(_engine(request), _user(request), exercise_id, request.app.state.clock())
    return _archive_response(request, exercise_id, "restore", "exercise.announce_archived")


@router.delete(LIST_PATH + "/{exercise_id}/archive", response_class=HTMLResponse)
def restore_exercise(request: Request, exercise_id: int) -> HTMLResponse:
    """Restore the exercise."""
    exercises.set_archived(_engine(request), _user(request), exercise_id, None)
    return _archive_response(request, exercise_id, "archive", "exercise.announce_restored")


# --- fields


def _fields_context(
    request: Request,
    detail: ExerciseDetail,
    *,
    open_id: int | None = None,
    focus: str | None = None,
    errors: FormErrors = NO_ERRORS,
    typed: dict[str, Any] | None = None,
    selected: str | None = None,
    add_errors: FormErrors = NO_ERRORS,
    announce: str | None = None,
) -> dict[str, Any]:
    return {
        "detail": detail,
        "open_id": open_id,
        "focus": focus,
        "field_errors": errors,
        "no_errors": NO_ERRORS,
        "typed": typed,
        "selected": selected,
        "add_errors": add_errors,
        "names": {field.id: field_name(request, field) for field in detail.fields},
        "announce": announce,
    }


def _fields_response(request: Request, exercise_id: int, **options: Any) -> HTMLResponse:
    detail = _detail(request, exercise_id)
    return render(request, "exercise_fields.html", _fields_context(request, detail, **options))


def _source(raw: str | None) -> dict[str, Any]:
    """The service arguments of an add-field `source` value."""
    if not raw:
        raise CatalogError([Problem("source", "required")])
    if raw.startswith(CORE_PREFIX):
        return {"core_quantity": raw.removeprefix(CORE_PREFIX)}
    number = raw.removeprefix(VARIABLE_PREFIX)
    if raw.startswith(VARIABLE_PREFIX) and number.isdigit():
        return {"variable_id": int(number)}
    raise CatalogError([Problem("source", "invalid_choice")])


@router.post(LIST_PATH + "/{exercise_id}/champs", response_class=HTMLResponse)
def add_field(request: Request, exercise_id: int, body: AddFieldBody) -> HTMLResponse:
    """Link a core quantity or a variable; the new row opens on « Obligatoire »."""
    _detail(request, exercise_id)
    try:
        field_id = exercises.add_field(_engine(request), _user(request), exercise_id, **_source(body.source))
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, {}, ADD_ID)
        return _fields_response(
            request, exercise_id, add_errors=errors, selected=body.source, announce=errors.first_message
        )
    detail = _detail(request, exercise_id)
    added = next(field for field in detail.fields if field.id == field_id)
    announce = _text(request, "exercise.announce_field_added", field=field_name(request, added))
    context = _fields_context(
        request, detail, open_id=field_id, focus=f"champ-{field_id}-obligatoire", announce=announce
    )
    return render(request, "exercise_fields.html", context)


def _field_ids(field_id: int) -> dict[str, str]:
    prefix = f"champ-{field_id}"
    return {
        "increment": f"{prefix}-pas",
        "discrete_values": f"{prefix}-valeurs",
        "default": f"{prefix}-defaut",
        "field": f"{prefix}-retirer",
    }


@router.patch(LIST_PATH + "/{exercise_id}/champs/{field_id}", response_class=HTMLResponse)
def update_field(request: Request, exercise_id: int, field_id: int, body: FieldBody) -> HTMLResponse:
    """Save a field's parameters; refused → the row stays open with its messages."""
    form = FieldForm(
        required=checked(body.required),
        increment=body.increment if body.mode != VALUES_MODE else None,
        discrete_values=body.discrete_values if body.mode == VALUES_MODE else None,
        default=body.default,
    )
    try:
        exercises.update_field(_engine(request), _user(request), exercise_id, field_id, form)
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, _field_ids(field_id), f"champ-{field_id}-pas")
        typed = {**body.model_dump(), "required": checked(body.required)}
        return _fields_response(
            request, exercise_id, open_id=field_id, errors=errors, typed=typed, announce=errors.first_message
        )
    focus = f"champ-{field_id}-modifier"
    return _fields_response(request, exercise_id, focus=focus, announce=_text(request, SAVED_KEY))


@router.post(LIST_PATH + "/{exercise_id}/champs/{field_id}/deplacement", response_class=HTMLResponse)
def move_field(request: Request, exercise_id: int, field_id: int, body: MoveBody) -> HTMLResponse:
    """Move a field up or down; focus stays on the same button (or the other one at an end)."""
    index = exercises.move_field(_engine(request), _user(request), exercise_id, field_id, body.direction)
    detail = _detail(request, exercise_id)
    last = len(detail.fields) - 1
    button = "monter" if body.direction == exercises.UP else "descendre"
    if (button == "monter" and index == 0) or (button == "descendre" and index == last):
        button = "descendre" if button == "monter" else "monter"
    moved = detail.fields[index]
    announce = _text(
        request,
        "exercise.announce_field_moved",
        field=field_name(request, moved),
        position=index + 1,
        total=last + 1,
    )
    context = _fields_context(request, detail, focus=f"champ-{field_id}-{button}", announce=announce)
    return render(request, "exercise_fields.html", context)


@router.delete(LIST_PATH + "/{exercise_id}/champs/{field_id}", response_class=HTMLResponse)
def remove_field(request: Request, exercise_id: int, field_id: int) -> HTMLResponse:
    """Remove a field (stored values stay); the last measure is refused in place."""
    before = _detail(request, exercise_id)
    index = next((i for i, field in enumerate(before.fields) if field.id == field_id), None)
    try:
        exercises.remove_field(_engine(request), _user(request), exercise_id, field_id)
    except CatalogError as error:
        errors = form_errors(
            request.app.state.catalog, error, _field_ids(field_id), f"champ-{field_id}-retirer"
        )
        return _fields_response(
            request, exercise_id, open_id=field_id, errors=errors, announce=errors.first_message
        )
    assert index is not None  # the service found it
    removed = field_name(request, before.fields[index])
    detail = _detail(request, exercise_id)
    focus = f"champ-{detail.fields[index].id}-modifier" if index < len(detail.fields) else ADD_ID
    announce = _text(request, "exercise.announce_field_removed", field=removed)
    return render(
        request, "exercise_fields.html", _fields_context(request, detail, focus=focus, announce=announce)
    )


# --- aliases


def _aliases_response(
    request: Request,
    exercise_id: int,
    *,
    errors: FormErrors = NO_ERRORS,
    value: str = "",
    announce: str | None = None,
) -> HTMLResponse:
    context = {
        "detail": _detail(request, exercise_id),
        "alias_errors": errors,
        "alias_value": value,
        "alias_focus": True,
        "announce": announce,
    }
    return render(request, "exercise_aliases.html", context)


@router.post(LIST_PATH + "/{exercise_id}/alias", response_class=HTMLResponse)
def add_alias(request: Request, exercise_id: int, body: AliasBody) -> HTMLResponse:
    """Add an alias; the input comes back empty and focused (aliases often come in twos)."""
    try:
        alias = exercises.add_alias(_engine(request), _user(request), exercise_id, body.alias)
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, {}, ALIAS_ID)
        return _aliases_response(
            request, exercise_id, errors=errors, value=body.alias or "", announce=errors.first_message
        )
    return _aliases_response(
        request, exercise_id, announce=_text(request, "exercise.announce_alias_added", alias=alias)
    )


@router.delete(LIST_PATH + "/{exercise_id}/alias/{alias_id}", response_class=HTMLResponse)
def remove_alias(request: Request, exercise_id: int, alias_id: int) -> HTMLResponse:
    """Remove an alias."""
    alias = exercises.remove_alias(_engine(request), _user(request), exercise_id, alias_id)
    return _aliases_response(
        request, exercise_id, announce=_text(request, "exercise.announce_alias_removed", alias=alias)
    )
