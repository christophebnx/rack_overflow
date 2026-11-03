"""Variable pages (docs/ui-spec.md "L2 — Variable list", "L2 — Variable create and edit"; D-050,
D-054). Thin: JSON body → `services.variables` → page or fragment. Refused input re-renders the
form `200` with messages per field (D-050); an unknown or foreign id is a 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from rack_overflow.domain.catalog import CatalogError, ValueInput
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.vocabulary import VARIABLE_TYPES
from rack_overflow.services import exercises, variables
from rack_overflow.services.variables import VariableDetail, VariableForm
from rack_overflow.web.auth import device_user
from rack_overflow.web.forms import NO_ERRORS, FormErrors, RowId, as_list, form_errors, in_id_range
from rack_overflow.web.rendering import render

router = APIRouter()

TEXT_MAX = 200
VALUES_MAX = 4000
LIST_PATH = "/variables"
SAVED_KEY = "status.saved"
# problem field -> input id (refusals tied to their input, D-050)
INPUT_IDS = {
    "label": "libelle",
    "scope": "role-set",
    "type": "type",
    "unit": "unite",
    "decimal_scale": "decimales",
    "values": "valeurs",
}
FORM_LEVEL_ID = "libelle"
ARCHIVE_IDS = {"delete": "variable-archiver"}
Many = str | list[str] | None


class VariableBody(BaseModel):
    """JSON body of the variable form (`json-enc`): every typed value is a string."""

    label: str | None = Field(default=None, max_length=TEXT_MAX)
    scope: str | None = Field(default=None, max_length=TEXT_MAX)
    type: str | None = Field(default=None, max_length=TEXT_MAX)
    unit: str | None = Field(default=None, max_length=TEXT_MAX)
    decimal_scale: str | None = Field(default=None, max_length=TEXT_MAX)
    values: str | None = Field(default=None, max_length=VALUES_MAX)
    value_label: Many = None
    value_key: Many = None
    value_remove: Many = None
    exercice: str | None = Field(default=None, max_length=TEXT_MAX)


def _value_inputs(body: VariableBody) -> list[ValueInput]:
    """Existing values (label + hidden key, maybe removed), then the new lines of the textarea."""
    removed = set(as_list(body.value_remove))
    rows = [
        ValueInput(label, key=key, remove=key in removed)
        for label, key in zip(as_list(body.value_label), as_list(body.value_key), strict=False)
    ]
    rows.extend(ValueInput(line) for line in (body.values or "").splitlines() if line.strip())
    return rows


def _form(body: VariableBody, frozen: VariableDetail | None = None) -> VariableForm:
    """The service form; frozen attributes (not sent by the page) come from the stored variable."""
    var_type, scope, scale = body.type, body.scope, body.decimal_scale
    if frozen is not None and frozen.has_values:
        draft = frozen.draft
        var_type, scope = draft.type, draft.scope
        scale = str(draft.decimal_scale) if draft.decimal_scale is not None else None
    return VariableForm(body.label, var_type, scope, body.unit, scale, _value_inputs(body))


def _exercise_name(request: Request, raw: str | None) -> tuple[int, str] | None:
    """The exercise a variable is created for (`?exercice=`), when it is the user's."""
    if raw is None or not raw.isdigit() or not in_id_range(int(raw)):
        return None
    try:
        detail = exercises.get_detail(request.app.state.engine, device_user(request), int(raw))
    except NotFoundError:
        return None
    return detail.id, detail.draft.name


def _form_context(
    request: Request,
    *,
    detail: VariableDetail | None,
    values: dict[str, Any],
    errors: FormErrors = NO_ERRORS,
    saved: bool = False,
    for_exercise: tuple[int, str] | None = None,
) -> dict[str, Any]:
    return {
        "section": "variables",
        "detail": detail,
        "form": values,
        "errors": errors,
        "saved": saved,
        "for_exercise": for_exercise,
        "types": VARIABLE_TYPES,
        "announce": errors.first_message or (request.app.state.catalog.text(SAVED_KEY) if saved else None),
    }


def _values_of(detail: VariableDetail) -> dict[str, Any]:
    draft = detail.draft
    return {
        "label": draft.label,
        "scope": draft.scope,
        "type": draft.type,
        "unit": draft.unit or "",
        "decimal_scale": str(draft.decimal_scale or 1),
        "values": "",
        "rows": [{"key": v.key, "label": v.label, "remove": False} for v in draft.enum_values or ()],
    }


def _values_of_body(body: VariableBody, detail: VariableDetail | None) -> dict[str, Any]:
    """The typed values, to re-render a refused form as the user left it."""
    removed = set(as_list(body.value_remove))
    rows = [
        {"key": key, "label": label, "remove": key in removed}
        for label, key in zip(as_list(body.value_label), as_list(body.value_key), strict=False)
    ]
    frozen = detail.draft if detail is not None and detail.has_values else None
    return {
        "label": body.label or "",
        "scope": frozen.scope if frozen else body.scope,
        "type": frozen.type if frozen else body.type,
        "unit": body.unit or "",
        "decimal_scale": str(frozen.decimal_scale or 1) if frozen else (body.decimal_scale or "1"),
        "values": body.values or "",
        "rows": rows,
    }


@router.get(LIST_PATH, response_class=HTMLResponse)
def list_variables(request: Request, archivees: str | None = None) -> HTMLResponse:
    """The variable list, grouped by role; archived ones with `?archivees=1`."""
    show_archived = archivees == "1"
    found = variables.list_variables(
        request.app.state.engine, device_user(request), include_archived=show_archived
    )
    context = {
        "title_key": "variables.title",
        "section": "variables",
        "groups": [(scope, [v for v in found if v.draft.scope == scope]) for scope in ("set", "setting")],
        "show_archived": show_archived,
        "empty": not found,
    }
    return render(request, "variables.html", context)


@router.get(LIST_PATH + "/nouvelle", response_class=HTMLResponse)
def new_variable(request: Request, exercice: str | None = None) -> HTMLResponse:
    """The create form, optionally for an exercise (« Annuler » and success go back to it)."""
    values = {
        "label": "",
        "scope": None,
        "type": None,
        "unit": "",
        "decimal_scale": "1",
        "values": "",
        "rows": [],
    }
    context = _form_context(
        request, detail=None, values=values, for_exercise=_exercise_name(request, exercice)
    )
    return render(request, "variable.html", {**context, "title_key": "variable.new_title", "announce": None})


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_variable(request: Request, body: VariableBody) -> Response:
    """Create the variable; success → its page, or back to the exercise with it preselected."""
    for_exercise = _exercise_name(request, body.exercice)
    try:
        variable_id = variables.create(request.app.state.engine, device_user(request), _form(body))
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, INPUT_IDS, FORM_LEVEL_ID)
        context = _form_context(
            request, detail=None, values=_values_of_body(body, None), errors=errors, for_exercise=for_exercise
        )
        return render(request, "variable_form.html", context)
    target = f"{LIST_PATH}/{variable_id}"
    if for_exercise is not None:
        target = f"/exercices/{for_exercise[0]}?ajout={variable_id}"
    return Response(status_code=204, headers={"HX-Redirect": target})


def _detail(request: Request, variable_id: int) -> VariableDetail:
    return variables.get_detail(request.app.state.engine, device_user(request), variable_id)


@router.get(LIST_PATH + "/{variable_id}", response_class=HTMLResponse)
def show_variable(request: Request, variable_id: RowId) -> HTMLResponse:
    """The edit page: form, linked exercises, archive and delete."""
    detail = _detail(request, variable_id)
    context = _form_context(request, detail=detail, values=_values_of(detail))
    return render(request, "variable.html", {**context, "page_title": detail.draft.label, "announce": None})


@router.patch(LIST_PATH + "/{variable_id}", response_class=HTMLResponse)
def update_variable(request: Request, variable_id: RowId, body: VariableBody) -> HTMLResponse:
    """Save the shared variable; the form comes back with the saved state or the refusals."""
    detail = _detail(request, variable_id)
    try:
        variables.update(request.app.state.engine, device_user(request), variable_id, _form(body, detail))
    except CatalogError as error:
        ids = {**INPUT_IDS, "values": "valeurs-ajout"}
        errors = form_errors(request.app.state.catalog, error, ids, FORM_LEVEL_ID)
        context = _form_context(request, detail=detail, values=_values_of_body(body, detail), errors=errors)
        return render(request, "variable_form.html", context)
    saved = _detail(request, variable_id)
    context = _form_context(request, detail=saved, values=_values_of(saved), saved=True)
    return render(request, "variable_form.html", {**context, "retitle": True})


def _archive_block(
    request: Request, detail: VariableDetail, *, focus: str | None, announce: str | None = None, **extra: Any
) -> HTMLResponse:
    context = {
        "detail": detail,
        "focus": focus,
        "announce": announce,
        "oob_state": True,
        "refusal": None,
        **extra,
    }
    return render(request, "variable_archive.html", context)


@router.post(LIST_PATH + "/{variable_id}/archive", response_class=HTMLResponse)
def archive_variable(request: Request, variable_id: RowId) -> HTMLResponse:
    """Archive the variable (always allowed); the block shows « Restaurer »."""
    state = request.app.state
    variables.set_archived(state.engine, device_user(request), variable_id, state.clock())
    text = state.catalog.text("variable.announce_archived")
    return _archive_block(request, _detail(request, variable_id), focus="restore", announce=text)


@router.delete(LIST_PATH + "/{variable_id}/archive", response_class=HTMLResponse)
def restore_variable(request: Request, variable_id: RowId) -> HTMLResponse:
    """Restore the variable; the block shows « Archiver »."""
    state = request.app.state
    variables.set_archived(state.engine, device_user(request), variable_id, None)
    text = state.catalog.text("variable.announce_restored")
    return _archive_block(request, _detail(request, variable_id), focus="archive", announce=text)


@router.get(LIST_PATH + "/{variable_id}/suppression", response_class=HTMLResponse)
def confirm_delete_variable(request: Request, variable_id: RowId, annuler: str | None = None) -> HTMLResponse:
    """The in-place delete confirmation, or (`?annuler=1`) the block back with focus on « Supprimer… »."""
    detail = _detail(request, variable_id)
    if annuler == "1":
        return _archive_block(request, detail, focus="delete", oob_state=False)
    return render(request, "confirm_delete.html", {"detail": detail})


@router.delete(LIST_PATH + "/{variable_id}", response_class=HTMLResponse)
def delete_variable(request: Request, variable_id: RowId) -> Response:
    """Delete a variable without values (→ the list); with values, the block explains the refusal."""
    state = request.app.state
    try:
        variables.delete(state.engine, device_user(request), variable_id)
    except CatalogError as error:
        errors = form_errors(state.catalog, error, ARCHIVE_IDS, ARCHIVE_IDS["delete"])
        detail = _detail(request, variable_id)
        return _archive_block(request, detail, focus="archive", announce=errors.first_message, refusal=errors)
    return Response(status_code=204, headers={"HX-Redirect": LIST_PATH})
