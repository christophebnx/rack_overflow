"""Session template pages (docs/ui-spec.md "L3 — Template list", "L3 — New template", "L3 —
Template detail"; D-050, D-053, D-058, D-059). Thin: JSON body → `services.templates` → page or
fragment. Refused input re-renders the fragment `200` (D-050); an unknown, foreign or removed id is
a 404. The module is not called `templates` to avoid confusion with the Jinja templates.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from rack_overflow.domain.catalog import CatalogError, sort_key
from rack_overflow.domain.templates import EXERCISE, MAX_OPTIONS, MAX_SLOTS, MENU, reps_text
from rack_overflow.domain.units import DISTANCE, DURATION
from rack_overflow.domain.vocabulary import LOCATIONS
from rack_overflow.services import templates
from rack_overflow.services.templates import SlotForm, SlotView, TemplateDetail, TemplateForm
from rack_overflow.web.auth import device_user
from rack_overflow.web.display import Display
from rack_overflow.web.forms import NO_ERRORS, FormErrors, MoveBody, form_errors, move_focus
from rack_overflow.web.rendering import render

router = APIRouter()

TEXT_MAX = 200
LIST_PATH = "/seances-types"
SAVED_KEY = "status.saved"
# problem field -> input id of the template form
TEMPLATE_IDS = {"name": "seance-nom", "location": "seance-lieu-gym"}
ADD_IDS = {
    "kind": "bloc-ajout-exercice-type",
    "label": "bloc-ajout-menu",
    "exercise_id": "bloc-ajout-exercice",
}
ADD_FOCUS = "bloc-ajout-exercice-type"


class TemplateBody(BaseModel):
    """JSON body of the template form (`json-enc`)."""

    name: str | None = Field(default=None, max_length=TEXT_MAX)
    location: str | None = Field(default=None, max_length=TEXT_MAX)

    def form(self) -> TemplateForm:
        """The service form."""
        return TemplateForm(self.name, self.location)


class AddSlotBody(BaseModel):
    """A new slot: its kind, its exercise (a menu's first one) and a menu's label."""

    kind: Literal["exercise", "menu"]
    exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)
    label: str | None = Field(default=None, max_length=TEXT_MAX)


class SlotBody(BaseModel):
    """A slot's exercise (fixed slot) or label (menu) and its target, typed in display units."""

    exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)
    label: str | None = Field(default=None, max_length=TEXT_MAX)
    sets: str | None = Field(default=None, max_length=TEXT_MAX)
    reps: str | None = Field(default=None, max_length=TEXT_MAX)
    duration: str | None = Field(default=None, max_length=TEXT_MAX)
    distance: str | None = Field(default=None, max_length=TEXT_MAX)
    note: str | None = Field(default=None, max_length=TEXT_MAX)


class OptionBody(BaseModel):
    """The exercise added to a menu."""

    exercise_id: str | None = Field(default=None, max_length=TEXT_MAX)


def _engine(request: Request) -> Any:
    return request.app.state.engine


def _text(request: Request, key: str, **params: object) -> str:
    return str(request.app.state.catalog.text(key, **params))


def _id(raw: str | None) -> int | None:
    """An id sent as a select value: empty → None (refused by the service), not an integer → 422."""
    if raw is None or not raw.strip():
        return None
    if not raw.strip().isdigit():
        raise HTTPException(status_code=422)
    return int(raw)


def _errors(request: Request, error: CatalogError, ids: dict[str, str], fallback: str) -> FormErrors:
    return form_errors(request.app.state.catalog, error, ids, fallback)


# --- list


def _list_context(request: Request, show_archived: bool) -> dict[str, Any]:
    found = templates.list_templates(_engine(request), device_user(request), include_archived=show_archived)
    archived = sorted((t for t in found if t.archived), key=lambda t: (sort_key(t.draft.name), t.id))
    return {
        "active": [t for t in found if not t.archived],
        "archived": archived,
        "show_archived": show_archived,
    }


@router.get(LIST_PATH, response_class=HTMLResponse)
def list_templates(request: Request, archivees: str | None = None) -> HTMLResponse:
    """The templates in the order the session start offers them; archived ones apart on demand."""
    context = _list_context(request, archivees == "1")
    context.update({"title_key": "templates.title", "section": "templates", "focus": None, "announce": None})
    return render(request, "session_templates.html", context)


@router.post(LIST_PATH + "/{template_id}/deplacement", response_class=HTMLResponse)
def move_template(request: Request, template_id: int, body: MoveBody) -> HTMLResponse:
    """Move a template up or down; focus stays on the same button (or the other one at an end)."""
    index = templates.move(_engine(request), device_user(request), template_id, body.direction)
    context = _list_context(request, False)
    active = context["active"]
    announce = _text(
        request,
        "template.announce_moved",
        name=active[index].draft.name,
        position=index + 1,
        total=len(active),
    )
    focus = move_focus(f"seance-type-{template_id}", body.direction, index, len(active))
    return render(request, "session_templates_list.html", {**context, "focus": focus, "announce": announce})


# --- create and edit


def _form_values(detail: TemplateDetail | None = None, body: TemplateBody | None = None) -> dict[str, Any]:
    if body is not None:
        return body.model_dump()
    if detail is None:
        return {"name": "", "location": None}
    return {"name": detail.draft.name, "location": detail.draft.location}


def _form_context(
    detail: TemplateDetail | None,
    values: dict[str, Any],
    errors: FormErrors = NO_ERRORS,
    announce: str | None = None,
) -> dict[str, Any]:
    return {
        "detail": detail,
        "form": values,
        "errors": errors,
        "saved": False,
        "locations": LOCATIONS,
        "announce": errors.first_message or announce,
    }


@router.get(LIST_PATH + "/nouvelle", response_class=HTMLResponse)
def new_template(request: Request) -> HTMLResponse:
    """The create form."""
    context = _form_context(None, _form_values())
    context.update({"title_key": "template.new_title", "section": "templates"})
    return render(request, "session_template_new.html", context)


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_template(request: Request, body: TemplateBody) -> Response:
    """Create an empty template → its page."""
    try:
        template_id = templates.create(_engine(request), device_user(request), body.form())
    except CatalogError as error:
        errors = _errors(request, error, TEMPLATE_IDS, "seance-nom")
        return render(
            request, "session_template_form.html", _form_context(None, _form_values(body=body), errors)
        )
    return Response(status_code=204, headers={"HX-Redirect": f"{LIST_PATH}/{template_id}"})


def _detail(request: Request, template_id: int) -> TemplateDetail:
    return templates.get_detail(_engine(request), device_user(request), template_id)


@router.get(LIST_PATH + "/{template_id}", response_class=HTMLResponse)
def show_template(request: Request, template_id: int) -> HTMLResponse:
    """The template page: slots, informations, archive block."""
    detail = _detail(request, template_id)
    context = _form_context(detail, _form_values(detail))
    context.update(_slots_context(request, detail))
    context.update({"page_title": detail.draft.name, "section": "templates", "announce": None})
    context.update({"archive_focus": None, "oob_state": False})
    return render(request, "session_template.html", context)


@router.patch(LIST_PATH + "/{template_id}", response_class=HTMLResponse)
def update_template(request: Request, template_id: int, body: TemplateBody) -> HTMLResponse:
    """Save the name and location; the form comes back saved or with its refusals."""
    detail = _detail(request, template_id)
    try:
        templates.update(_engine(request), device_user(request), template_id, body.form())
    except CatalogError as error:
        errors = _errors(request, error, TEMPLATE_IDS, "seance-nom")
        return render(
            request, "session_template_form.html", _form_context(detail, _form_values(body=body), errors)
        )
    saved = _detail(request, template_id)
    context = _form_context(saved, _form_values(saved), announce=_text(request, SAVED_KEY))
    return render(request, "session_template_form.html", {**context, "saved": True, "retitle": True})


def _archive_response(request: Request, template_id: int, focus: str, key: str) -> HTMLResponse:
    context = {"detail": _detail(request, template_id), "archive_focus": focus, "oob_state": True}
    return render(request, "session_template_archive.html", {**context, "announce": _text(request, key)})


@router.post(LIST_PATH + "/{template_id}/archive", response_class=HTMLResponse)
def archive_template(request: Request, template_id: int) -> HTMLResponse:
    """Archive the template (still viewable and editable)."""
    templates.set_archived(_engine(request), device_user(request), template_id, request.app.state.clock())
    return _archive_response(request, template_id, "restore", "template.announce_archived")


@router.delete(LIST_PATH + "/{template_id}/archive", response_class=HTMLResponse)
def restore_template(request: Request, template_id: int) -> HTMLResponse:
    """Restore the template, last in the order."""
    templates.set_archived(_engine(request), device_user(request), template_id, None)
    return _archive_response(request, template_id, "archive", "template.announce_restored")


# --- slots


def _slot_values(request: Request, slot: SlotView) -> dict[str, str]:
    """The inputs of a slot form prefilled in display units."""
    show = Display(request.app.state.catalog)
    target = slot.target
    return {
        "exercise_id": str(slot.exercise.id) if slot.exercise is not None else "",
        "label": slot.label or "",
        "sets": str(target.sets) if target.sets is not None else "",
        "reps": reps_text(target.reps_min, target.reps_max),
        "duration": show.input_text(DURATION, target.duration_s),
        "distance": show.input_text(DISTANCE, target.distance_m),
        "note": target.note or "",
    }


def _slots_context(request: Request, detail: TemplateDetail, **options: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "open_id": None,
        "focus": None,
        "slot_errors": NO_ERRORS,
        "typed": None,
        "add_errors": NO_ERRORS,
        "add_typed": None,
        "option_errors": NO_ERRORS,
        "announce": None,
        **options,
    }
    return {
        **context,
        "detail": detail,
        "values": {slot.id: _slot_values(request, slot) for slot in detail.slots},
        "max_slots": MAX_SLOTS,
        "max_options": MAX_OPTIONS,
        "no_errors": NO_ERRORS,
    }


def _slots_response(request: Request, template_id: int, **options: Any) -> HTMLResponse:
    detail = _detail(request, template_id)
    return render(request, "session_template_slots.html", _slots_context(request, detail, **options))


@router.post(LIST_PATH + "/{template_id}/blocs", response_class=HTMLResponse)
def add_slot(request: Request, template_id: int, body: AddSlotBody) -> HTMLResponse:
    """Add an exercise or a menu (with its first exercise); its « Modifier » opens on the next step."""
    exercise_id = _id(body.exercise_id)
    label = body.label if body.kind == MENU else None
    try:
        slot_id = templates.add_slot(
            _engine(request),
            device_user(request),
            template_id,
            kind=body.kind,
            exercise_id=exercise_id,
            label=label,
        )
    except CatalogError as error:
        errors = _errors(request, error, ADD_IDS, "bloc-ajout-exercice")
        return _slots_response(
            request,
            template_id,
            add_errors=errors,
            add_typed=body.model_dump(),
            announce=errors.first_message,
        )
    detail = _detail(request, template_id)
    slot = detail.slot(slot_id)
    focus = f"bloc-{slot_id}-series" if slot.kind == EXERCISE else f"bloc-{slot_id}-option-ajout"
    announce = _text(request, "template.announce_slot_added", name=slot.name)
    return render(
        request,
        "session_template_slots.html",
        _slots_context(request, detail, open_id=slot_id, focus=focus, announce=announce),
    )


def _slot_ids(slot_id: int) -> dict[str, str]:
    prefix = f"bloc-{slot_id}"
    return {
        "exercise_id": f"{prefix}-exercice",
        "label": f"{prefix}-menu",
        "sets": f"{prefix}-series",
        "reps": f"{prefix}-reps",
        "duration": f"{prefix}-duree",
        "distance": f"{prefix}-distance",
        "note": f"{prefix}-note",
    }


@router.patch(LIST_PATH + "/{template_id}/blocs/{slot_id}", response_class=HTMLResponse)
def update_slot(request: Request, template_id: int, slot_id: int, body: SlotBody) -> HTMLResponse:
    """Save a slot's exercise or label and its target; refused → the row stays open with its messages."""
    form = SlotForm(
        exercise_id=_id(body.exercise_id),
        label=body.label,
        sets=body.sets,
        reps=body.reps,
        duration=body.duration,
        distance=body.distance,
        note=body.note,
    )
    try:
        templates.update_slot(_engine(request), device_user(request), template_id, slot_id, form)
    except CatalogError as error:
        errors = _errors(request, error, _slot_ids(slot_id), f"bloc-{slot_id}-series")
        typed = {key: value or "" for key, value in body.model_dump().items()}
        return _slots_response(
            request,
            template_id,
            open_id=slot_id,
            slot_errors=errors,
            typed=typed,
            announce=errors.first_message,
        )
    focus = f"bloc-{slot_id}-modifier"
    return _slots_response(request, template_id, focus=focus, announce=_text(request, SAVED_KEY))


@router.post(LIST_PATH + "/{template_id}/blocs/{slot_id}/deplacement", response_class=HTMLResponse)
def move_slot(request: Request, template_id: int, slot_id: int, body: MoveBody) -> HTMLResponse:
    """Move a slot up or down; focus stays on the same button (or the other one at an end)."""
    index = templates.move_slot(_engine(request), device_user(request), template_id, slot_id, body.direction)
    detail = _detail(request, template_id)
    total = len(detail.slots)
    announce = _text(
        request, "template.announce_moved", name=detail.slots[index].name, position=index + 1, total=total
    )
    focus = move_focus(f"bloc-{slot_id}", body.direction, index, total)
    return render(
        request,
        "session_template_slots.html",
        _slots_context(request, detail, focus=focus, announce=announce),
    )


@router.delete(LIST_PATH + "/{template_id}/blocs/{slot_id}", response_class=HTMLResponse)
def remove_slot(request: Request, template_id: int, slot_id: int) -> HTMLResponse:
    """Remove a slot (soft delete); focus on the next row, else the previous one, else the add form."""
    before = _detail(request, template_id)
    removed = before.slot(slot_id)
    index = before.slots.index(removed)
    templates.remove_slot(
        _engine(request), device_user(request), template_id, slot_id, request.app.state.clock()
    )
    detail = _detail(request, template_id)
    remaining = detail.slots
    neighbour = remaining[min(index, len(remaining) - 1)] if remaining else None
    focus = f"bloc-{neighbour.id}-modifier" if neighbour is not None else ADD_FOCUS
    announce = _text(request, "template.announce_slot_removed", name=removed.name)
    return render(
        request,
        "session_template_slots.html",
        _slots_context(request, detail, focus=focus, announce=announce),
    )


# --- menu options


def _option_add_id(slot_id: int) -> str:
    return f"bloc-{slot_id}-option-ajout"


@router.post(LIST_PATH + "/{template_id}/blocs/{slot_id}/options", response_class=HTMLResponse)
def add_option(request: Request, template_id: int, slot_id: int, body: OptionBody) -> HTMLResponse:
    """Offer one more exercise in a menu; the menu stays open on its add-option select."""
    try:
        option_id = templates.add_option(
            _engine(request), device_user(request), template_id, slot_id, _id(body.exercise_id)
        )
    except CatalogError as error:
        errors = _errors(request, error, {}, _option_add_id(slot_id))
        return _slots_response(
            request, template_id, open_id=slot_id, option_errors=errors, announce=errors.first_message
        )
    detail = _detail(request, template_id)
    added = next(option for option in detail.slot(slot_id).options if option.id == option_id)
    announce = _text(request, "template.announce_option_added", name=added.exercise.name)
    context = _slots_context(
        request, detail, open_id=slot_id, focus=_option_add_id(slot_id), announce=announce
    )
    return render(request, "session_template_slots.html", context)


@router.post(
    LIST_PATH + "/{template_id}/blocs/{slot_id}/options/{option_id}/deplacement", response_class=HTMLResponse
)
def move_option(
    request: Request, template_id: int, slot_id: int, option_id: int, body: MoveBody
) -> HTMLResponse:
    """Move a menu option; the menu stays open, focus on the same button (or the other one)."""
    index = templates.move_option(
        _engine(request), device_user(request), template_id, slot_id, option_id, body.direction
    )
    detail = _detail(request, template_id)
    options = detail.slot(slot_id).options
    announce = _text(
        request,
        "template.announce_moved",
        name=options[index].exercise.name,
        position=index + 1,
        total=len(options),
    )
    focus = move_focus(f"option-{option_id}", body.direction, index, len(options))
    context = _slots_context(request, detail, open_id=slot_id, focus=focus, announce=announce)
    return render(request, "session_template_slots.html", context)


@router.delete(LIST_PATH + "/{template_id}/blocs/{slot_id}/options/{option_id}", response_class=HTMLResponse)
def remove_option(request: Request, template_id: int, slot_id: int, option_id: int) -> HTMLResponse:
    """Remove a menu option; focus on the next « Retirer », else the previous one, else the select."""
    before = _detail(request, template_id).slot(slot_id).options
    index = next((i for i, option in enumerate(before) if option.id == option_id), None)
    try:
        templates.remove_option(_engine(request), device_user(request), template_id, slot_id, option_id)
    except CatalogError as error:
        errors = _errors(request, error, {}, f"bloc-{slot_id}-options")
        return _slots_response(
            request, template_id, open_id=slot_id, option_errors=errors, announce=errors.first_message
        )
    assert index is not None  # the service found it
    detail = _detail(request, template_id)
    remaining = detail.slot(slot_id).options
    neighbour = remaining[min(index, len(remaining) - 1)]
    focus = f"option-{neighbour.id}-retirer" if len(remaining) > 1 else _option_add_id(slot_id)
    announce = _text(request, "template.announce_option_removed", name=before[index].exercise.name)
    context = _slots_context(request, detail, open_id=slot_id, focus=focus, announce=announce)
    return render(request, "session_template_slots.html", context)
