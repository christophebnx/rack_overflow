"""Ids beyond the database's integer range (`web.forms.RowId`, `row_id`): every route with an id in
its path, and every id sent in a body, answers 404, never a 500 from the driver."""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.services import exercises, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.web.forms import MAX_ID, in_id_range, row_id
from rack_overflow.web.routes import exercises as exercise_routes
from rack_overflow.web.routes import session_templates as template_routes
from rack_overflow.web.routes import variables as variable_routes

HTMX = {"hx-request": "true"}
PAGE = {"accept": "text/html"}
USER = 1
HUGE = str(MAX_ID + 1)
PARAM = re.compile(r"\{\w+\}")


def _id_routes() -> list[tuple[str, str, str]]:
    """(method, path template, parameter) of every route with an id in its path."""
    found = []
    for router in (exercise_routes.router, template_routes.router, variable_routes.router):
        for route in router.routes:
            assert isinstance(route, APIRoute)
            for name in PARAM.findall(route.path):
                found.extend((method, route.path, name) for method in sorted(route.methods))
    return found


ID_ROUTES = _id_routes()


def test_the_id_routes_are_found() -> None:
    assert len(ID_ROUTES) >= 40  # one entry per id in each route path


def test_the_id_range_is_the_database_integer() -> None:
    assert in_id_range(1) and in_id_range(MAX_ID)
    assert not in_id_range(0) and not in_id_range(MAX_ID + 1)
    assert row_id(MAX_ID) == MAX_ID


@pytest.mark.parametrize(("method", "path", "param"), ID_ROUTES)
def test_a_path_id_beyond_the_range_is_404(client: TestClient, method: str, path: str, param: str) -> None:
    url = PARAM.sub("1", path.replace(param, HUGE))
    body = None if method == "GET" else {}
    response = client.request(method, url, json=body, headers=HTMX)
    assert response.status_code == 404


def test_a_page_id_beyond_the_range_is_a_404_page(client: TestClient) -> None:
    for path in ("/exercices/", "/variables/", "/seances-types/"):
        response = client.get(path + HUGE, headers=PAGE)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")


def _template_with_menu(engine: Engine) -> tuple[int, int, int]:
    squat = exercises.create(engine, USER, ExerciseForm("Squat", "strength", "gym"))
    salle = templates.create(engine, USER, TemplateForm("Salle", "gym"))
    menu = templates.add_slot(engine, USER, salle, kind="menu", exercise_id=squat, label="Jambes")
    return squat, salle, menu


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("POST", "/blocs", {"kind": "exercise", "exercise_id": HUGE}),
        ("PATCH", "/blocs/{menu}", {"exercise_id": HUGE}),
        ("POST", "/blocs/{menu}/options", {"exercise_id": HUGE}),
    ],
)
def test_a_body_id_beyond_the_range_is_404(
    client: TestClient, migrated_engine: Engine, method: str, suffix: str, body: dict[str, str]
) -> None:
    _, salle, menu = _template_with_menu(migrated_engine)
    url = f"/seances-types/{salle}" + suffix.format(menu=menu)
    assert client.request(method, url, json=body, headers=HTMX).status_code == 404


def test_a_field_source_beyond_the_range_is_404(client: TestClient, migrated_engine: Engine) -> None:
    squat, _, _ = _template_with_menu(migrated_engine)
    response = client.post(f"/exercices/{squat}/champs", json={"source": f"variable:{HUGE}"}, headers=HTMX)
    assert response.status_code == 404


def test_a_new_variable_for_an_exercise_beyond_the_range_ignores_it(client: TestClient) -> None:
    response = client.get(f"/variables/nouvelle?exercice={HUGE}", headers=PAGE)
    assert response.status_code == 200
