"""Progress pages (docs/ui-spec.md "L5 — Progress index", "L5 — Progress of an exercise", "L5 —
Settings"; D-068 to D-070): the progression index, an exercise's progress page and the JSON of
its chart, the measured RM entries and the 1RM formula setting. Thin: request →
`services.progress` → page, fragment or JSON. Refused input re-renders the section `200` (D-050);
unknown or foreign ids are 404."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from rack_overflow.domain import units
from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.indicators import DEFAULT_FORMULA, RM_FORMULAS, Series
from rack_overflow.services import progress
from rack_overflow.services.progress import ChartData, RmView
from rack_overflow.web.auth import device_user
from rack_overflow.web.display import Display
from rack_overflow.web.forms import NO_ERRORS, FormErrors, RowId, form_errors
from rack_overflow.web.rendering import render
from rack_overflow.web.routes.history import local_today

router = APIRouter()

SECTION = "progress"
TEXT_MAX = 200
RM_FORM_IDS = {"n": "rm-n", "weight": "rm-weight", "date": "rm-date"}
FORMULA_ID = "reglages-formule"
# main series key → (axis key, unit key or None); a duration axis and tooltip read m:ss (D-029)
AXES = {
    "e1rm": ("progress.axis.weight", "unit.kg"),
    "measured_1rm": ("progress.axis.weight", "unit.kg"),
    "load": ("progress.axis.reps", None),
    "max_reps": ("progress.axis.reps", None),
    "max_duration": ("progress.axis.duration", None),
    "duration": ("progress.axis.duration", None),
    "distance": ("progress.axis.distance", "unit.km"),
    "rounds": ("progress.axis.rounds", None),
}


class RmBody(BaseModel):
    """The RM form: the rep count chip, the load typed in kg, the ISO date of the test."""

    n: str | None = Field(default=None, max_length=TEXT_MAX)
    weight: str | None = Field(default=None, max_length=TEXT_MAX)
    date: str | None = Field(default=None, max_length=TEXT_MAX)


class FormulaBody(BaseModel):
    """The formula radio of the settings page."""

    rm_formula: str | None = Field(default=None, max_length=TEXT_MAX)


def _engine(request: Request) -> Any:
    return request.app.state.engine


def _show(request: Request) -> Display:
    return Display(request.app.state.catalog)


def _text(request: Request, key: str, **params: object) -> str:
    return str(request.app.state.catalog.text(key, **params))


# --- pages


@router.get("/progression", response_class=HTMLResponse)
def progress_index(request: Request) -> HTMLResponse:
    """Exercises with history, most recent first."""
    items = progress.progress_index(_engine(request), device_user(request))
    context = {"items": items, "title_key": "progress.title", "section": SECTION}
    return render(request, "progress_index.html", context)


def _rm_context(request: Request, rm_section_view: RmView, **extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "rm": rm_section_view,
        "today": local_today(request),
        "rm_errors": NO_ERRORS,
        "rm_texts": {},
        "focus": None,
        "announce": None,
    }
    context.update(extra)
    return context


@router.get("/progression/{exercise_id}", response_class=HTMLResponse)
def exercise_progress(request: Request, exercise_id: RowId) -> HTMLResponse:
    """The progress page of an exercise (any of the user's, archived included)."""
    view = progress.exercise_progress(_engine(request), device_user(request), exercise_id)
    dates = _aligned(view.series)[0]
    chart = {"days": len(dates), "first": dates[0] if dates else "", "last": dates[-1] if dates else ""}
    context = _rm_context(
        request, view.rm, view=view, chart=chart, page_title=view.exercise.name, section=SECTION
    )
    return render(request, "progress.html", context)


# --- chart JSON


def _aligned(series: tuple[Series, ...]) -> tuple[list[str], list[list[float | None]]]:
    """The dates of every series (ascending) and each series' chart numbers on them."""
    dates = sorted({point.local_date for item in series for point in item.points})
    values = []
    for item in series:
        by_date = {point.local_date: units.chart_number(item.unit_kind, point.value) for point in item.points}
        values.append([by_date.get(day) for day in dates])
    return dates, values


SCALES = {units.WEIGHT: "decimal", units.DISTANCE: "decimal", units.DURATION: "duration"}
"""Value kind of the main series → how the chart writes the axis and tooltip numbers: decimals
with the `fr` locale, whole counts (`count`), or durations m:ss / h:mm:ss (`duration`)."""


def _duration_step(series: tuple[Series, ...]) -> int | None:
    """The tick step of a duration axis in seconds, else None."""
    if series[0].unit_kind != units.DURATION:
        return None
    found = [point.value for item in series for point in item.points]
    return units.chart_duration_step(min(found), max(found))


def _titles(show: Display, dates: list[str]) -> list[str]:
    """Tooltip titles: the short date, the full date when the chart spans two years or more."""
    if dates[0][:4] == dates[-1][:4]:
        return [show.short_date(day) for day in dates]
    return [show.local_date(day) for day in dates]


def chart_json(show: Display, catalog: Any, data: ChartData) -> dict[str, Any]:
    """The chart's JSON (D-068): labels « 03/11 », values in display units (durations in
    seconds, written m:ss by the script), the axis scale and step, French texts."""
    if not data.series:
        return {
            "unit": "",
            "axis": "",
            "tooltip": "",
            "scale": "",
            "step": None,
            "titles": [],
            "labels": [],
            "series": [],
        }
    axis_key, unit_key = AXES[data.series[0].key]
    unit = catalog.text(unit_key) if unit_key else ""
    tooltip = catalog.text("progress.chart_tooltip", label="{label}", value="{value}", unit=unit).rstrip()
    dates, values = _aligned(data.series)
    return {
        "unit": unit,
        "axis": catalog.text(axis_key),
        "tooltip": tooltip,
        "scale": SCALES.get(data.series[0].unit_kind, "count"),
        "step": _duration_step(data.series),
        "titles": _titles(show, dates),
        "labels": [show.short_date(day) for day in dates],
        "series": [
            {"label": show.series_label(item, data.formula), "kind": item.kind, "values": item_values}
            for item, item_values in zip(data.series, values, strict=True)
        ],
    }


@router.get("/api/progression/{exercise_id}")
def progress_data(request: Request, exercise_id: RowId) -> JSONResponse:
    """The JSON of the exercise's chart (`no-store`, same origin only: D-047)."""
    data = progress.chart_data(_engine(request), device_user(request), exercise_id)
    return JSONResponse(chart_json(_show(request), request.app.state.catalog, data))


# --- RM


@router.get("/rm/{exercise_id}", response_class=HTMLResponse)
def rm_section(request: Request, exercise_id: RowId) -> Response:
    """The RM section (htmx); a navigation goes to the progress page's RM section."""
    view = progress.rm_view(_engine(request), device_user(request), exercise_id)
    if not view.available:
        raise HTTPException(status_code=404)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(f"/progression/{exercise_id}#rm", status_code=303)
    return render(request, "progress_rm.html", _rm_context(request, view))


def _rm_errors(request: Request, error: CatalogError) -> FormErrors:
    return form_errors(request.app.state.catalog, error, RM_FORM_IDS, "rm-form")


@router.post("/rm/{exercise_id}", response_class=HTMLResponse)
def add_measured_rm(request: Request, exercise_id: RowId, body: RmBody) -> HTMLResponse:
    """Store a measured RM → the RM section (saved, or refused with messages, `200`)."""
    user = device_user(request)
    try:
        saved = progress.add_measured_rm(
            _engine(request),
            user,
            exercise_id,
            body.n,
            body.weight,
            body.date,
            now=request.app.state.clock(),
            today=local_today(request),
        )
    except CatalogError as error:
        view = progress.rm_view(_engine(request), user, exercise_id)
        errors = _rm_errors(request, error)
        texts = {"n": body.n or "", "weight": body.weight or "", "date": body.date or ""}
        context = _rm_context(request, view, rm_errors=errors, rm_texts=texts, announce=errors.first_message)
        return render(request, "progress_rm.html", context)
    value = _show(request).value(units.WEIGHT, saved.draft.weight_g)
    announce = _text(request, "rm.saved", n=saved.draft.n, value=value)
    context = _rm_context(request, saved.view, focus="rm-saisir", announce=announce, saved=announce)
    return render(request, "progress_rm.html", context)


@router.delete("/rm/mesures/{measured_id}", response_class=HTMLResponse)
def delete_measured_rm(request: Request, measured_id: RowId) -> HTMLResponse:
    """Soft delete a manual RM entry → the RM section; focus on the next entry's « Supprimer »."""
    user = device_user(request)
    deleted = progress.delete_measured_rm(_engine(request), user, measured_id, request.app.state.clock())
    focus = f"rm-mesure-{deleted.next_id}-supprimer" if deleted.next_id is not None else "rm-saisir"
    announce = _text(request, "rm.deleted")
    return render(
        request, "progress_rm.html", _rm_context(request, deleted.view, focus=focus, announce=announce)
    )


# --- settings


def _settings_context(chosen: str, **extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "formulas": RM_FORMULAS,
        "default_formula": DEFAULT_FORMULA,
        "chosen": chosen,
        "formula_errors": NO_ERRORS,
        "saved": None,
        "announce": None,
        "focus": None,
    }
    context.update(extra)
    return context


@router.get("/reglages", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    """The settings page: the 1RM formula."""
    chosen = progress.formula(_engine(request), device_user(request))
    return render(request, "settings.html", _settings_context(chosen, title_key="settings.title"))


@router.patch("/reglages", response_class=HTMLResponse)
def save_settings_page(request: Request, body: FormulaBody) -> HTMLResponse:
    """Save the formula (sent on change) → the formula form with its saved state."""
    user = device_user(request)
    try:
        chosen = progress.set_formula(_engine(request), user, body.rm_formula)
    except CatalogError as error:
        errors = form_errors(request.app.state.catalog, error, {}, FORMULA_ID)
        current = progress.formula(_engine(request), user)
        context = _settings_context(current, formula_errors=errors, announce=errors.first_message)
        return render(request, "settings_formula.html", context)
    saved = _text(request, "settings.formula_saved", formula=_show(request).formula(chosen))
    context = _settings_context(chosen, saved=saved, announce=saved, focus=f"formule-{chosen}")
    return render(request, "settings_formula.html", context)
