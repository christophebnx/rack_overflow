"""Every L2 route against the security rules (JSON-only, same origin, paired device), unknown ids,
and edge inputs through the pages (D-034, D-049, D-050, D-053, D-056)."""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import ValueInput
from rack_overflow.services import exercises, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.routes import exercises as exercise_routes
from rack_overflow.web.routes import variables as variable_routes

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1

# every non-GET route of L2, with ids filled in by `catalog_ids`
ACTIONS = [
    ("POST", "/variables"),
    ("PATCH", "/variables/{v}"),
    ("POST", "/variables/{v}/archive"),
    ("DELETE", "/variables/{v}/archive"),
    ("DELETE", "/variables/{v}"),
    ("POST", "/exercices"),
    ("PATCH", "/exercices/{e}"),
    ("POST", "/exercices/{e}/archive"),
    ("DELETE", "/exercices/{e}/archive"),
    ("POST", "/exercices/{e}/champs"),
    ("PATCH", "/exercices/{e}/champs/{f}"),
    ("POST", "/exercices/{e}/champs/{f}/deplacement"),
    ("DELETE", "/exercices/{e}/champs/{f}"),
    ("POST", "/exercices/{e}/alias"),
    ("DELETE", "/exercices/{e}/alias/{a}"),
]
GETS = [
    "/variables",
    "/variables/nouvelle",
    "/variables/{v}",
    "/variables/{v}/suppression",
    "/exercices",
    "/exercices/recherche?q=x",
    "/exercices/nouveau",
    "/exercices/{e}",
]


def catalog_ids(engine: Engine) -> dict[str, int]:
    exercise_id = exercises.create(engine, USER, ExerciseForm("Squat", "strength", "gym"))
    exercises.add_alias(engine, USER, exercise_id, "Back squat")
    detail = exercises.get_detail(engine, USER, exercise_id)
    variable_id = variables.create(
        engine, USER, VariableForm("Siège", "enum", "setting", values=[ValueInput("1")])
    )
    return {"v": variable_id, "e": exercise_id, "f": detail.fields[0].id, "a": detail.aliases[0].id}


def fill(path: str, ids: dict[str, int]) -> str:
    return path.format(**ids)


def test_the_list_covers_every_catalog_action(client: TestClient) -> None:
    del client
    app_routes = {
        (method, route.path)
        for router in (variable_routes.router, exercise_routes.router)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "GET"
    }
    listed = {
        (
            method,
            path.replace("{v}", "{variable_id}")
            .replace("{e}", "{exercise_id}")
            .replace("{f}", "{field_id}")
            .replace("{a}", "{alias_id}"),
        )
        for method, path in ACTIONS
    }
    assert app_routes == listed


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_form_encoded_body_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = catalog_ids(migrated_engine)
    before = (
        exercises.get_detail(migrated_engine, USER, ids["e"]),
        variables.get_detail(migrated_engine, USER, ids["v"]),
    )
    response = client.request(method, fill(path, ids), data={"label": "x", "name": "x"}, headers=HTMX)
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    after = (
        exercises.get_detail(migrated_engine, USER, ids["e"]),
        variables.get_detail(migrated_engine, USER, ids["v"]),
    )
    assert after == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
@pytest.mark.parametrize(
    "foreign", [{"origin": "http://evil.example"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}]
)
def test_cross_origin_action_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str, foreign: dict[str, str]
) -> None:
    ids = catalog_ids(migrated_engine)
    before = (
        exercises.get_detail(migrated_engine, USER, ids["e"]),
        variables.get_detail(migrated_engine, USER, ids["v"]),
    )
    response = client.request(method, fill(path, ids), json={}, headers={**HTMX, **foreign})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    after = (
        exercises.get_detail(migrated_engine, USER, ids["e"]),
        variables.get_detail(migrated_engine, USER, ids["v"]),
    )
    assert after == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_unpaired_action_is_sent_to_pairing(
    unpaired_client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = catalog_ids(migrated_engine)
    response = unpaired_client.request(method, fill(path, ids), json={}, headers=HTMX)
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/appairage"


@pytest.mark.parametrize("path", GETS)
def test_unpaired_navigation_goes_to_pairing(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = catalog_ids(migrated_engine)
    response = unpaired_client.get(fill(path, ids), headers=PAGE, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/appairage"


VALID_BODIES = {
    "/variables/{v}": {"label": "x", "scope": "setting", "type": "int"},
    "/exercices/{e}": {"name": "x", "category": "strength", "location": "gym"},
    "/exercices/{e}/champs": {"source": "core:distance"},
    "/exercices/{e}/champs/{f}/deplacement": {"direction": "down"},
    "/exercices/{e}/alias": {"alias": "y"},
}


@pytest.mark.parametrize(
    ("method", "path", "missing"),
    [(m, p, k) for m, p in ACTIONS for k in "vefa" if "{" + k + "}" in p],
)
def test_unknown_ids_are_404(
    client: TestClient, migrated_engine: Engine, method: str, path: str, missing: str
) -> None:
    ids = {**catalog_ids(migrated_engine), missing: 9999}
    response = client.request(method, fill(path, ids), json=VALID_BODIES.get(path, {}), headers=HTMX)
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


@pytest.mark.parametrize("path", [g for g in GETS if "{" in g])
def test_unknown_ids_on_pages_are_404_pages(client: TestClient, migrated_engine: Engine, path: str) -> None:
    ids = {**catalog_ids(migrated_engine), "v": 9999, "e": 9999}
    response = client.get(fill(path, ids), headers=PAGE)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")


def test_a_field_of_another_exercise_is_404(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    other = exercises.create(migrated_engine, USER, ExerciseForm("Rowing", "strength", "gym"))
    response = client.request("DELETE", f"/exercices/{other}/champs/{ids['f']}", json={}, headers=HTMX)
    assert response.status_code == 404
    alias = client.request("DELETE", f"/exercices/{other}/alias/{ids['a']}", json={}, headers=HTMX)
    assert alias.status_code == 404
    assert len(exercises.get_detail(migrated_engine, USER, ids["e"]).fields) == 2


def test_another_users_variable_cannot_be_linked_through_the_page(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = catalog_ids(migrated_engine)
    theirs = variables.create(migrated_engine, 2, VariableForm("Tempo", "int", "set"))
    response = client.post(
        f"/exercices/{ids['e']}/champs", json={"source": f"variable:{theirs}"}, headers=HTMX
    )
    assert response.status_code == 200
    assert TEXT("catalog.error.invalid_choice") in response.text
    assert "Tempo" not in response.text


@pytest.mark.parametrize(
    "source", ["", "core:", "core:calories", "variable:", "variable:abc", "variable:-1", "x"]
)
def test_bad_add_field_sources_are_refused_in_place(
    client: TestClient, migrated_engine: Engine, source: str
) -> None:
    ids = catalog_ids(migrated_engine)
    response = client.post(f"/exercices/{ids['e']}/champs", json={"source": source}, headers=HTMX)
    assert response.status_code == 200
    assert 'id="annonce" hx-swap-oob="innerHTML">' in response.text
    assert len(exercises.get_detail(migrated_engine, USER, ids["e"]).fields) == 2


def test_move_at_the_ends_through_the_page_keeps_focus_on_the_other_button(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = catalog_ids(migrated_engine)
    detail = exercises.get_detail(migrated_engine, USER, ids["e"])
    first, last = detail.fields[0].id, detail.fields[-1].id
    up = client.post(
        f"/exercices/{ids['e']}/champs/{first}/deplacement", json={"direction": "up"}, headers=HTMX
    )
    assert up.status_code == 200
    assert f'id="champ-{first}-descendre"' in up.text
    assert "autofocus" in up.text.split(f'id="champ-{first}-descendre"', 1)[1].split(">", 1)[0]
    down = client.post(
        f"/exercices/{ids['e']}/champs/{last}/deplacement", json={"direction": "down"}, headers=HTMX
    )
    assert "autofocus" in down.text.split(f'id="champ-{last}-monter"', 1)[1].split(">", 1)[0]
    assert [f.id for f in exercises.get_detail(migrated_engine, USER, ids["e"]).fields] == [first, last]


def test_moving_a_lone_field_keeps_focus_on_its_edit_button(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = catalog_ids(migrated_engine)
    fields = exercises.get_detail(migrated_engine, USER, ids["e"]).fields
    for extra in fields[1:]:
        exercises.remove_field(migrated_engine, USER, ids["e"], extra.id)
    lone = fields[0].id
    for direction in ("up", "down"):
        moved = client.post(
            f"/exercices/{ids['e']}/champs/{lone}/deplacement", json={"direction": direction}, headers=HTMX
        )
        assert moved.status_code == 200
        assert re.findall(r'id="([^"]+)"[^>]*\sautofocus', moved.text) == [f"champ-{lone}-modifier"]


def test_refused_field_input_keeps_typed_values_and_marks_the_input(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = catalog_ids(migrated_engine)
    weight = exercises.get_detail(migrated_engine, USER, ids["e"]).fields[1]
    body = {"mode": "values", "discrete_values": "16 20 abc", "default": "16"}
    response = client.patch(f"/exercices/{ids['e']}/champs/{weight.id}", json=body, headers=HTMX)
    assert response.status_code == 200
    assert 'value="16 20 abc"' in response.text
    assert f'id="champ-{weight.id}-valeurs-erreur"' in response.text or "aria-invalid" in response.text
    assert TEXT("catalog.error.not_a_number", value="abc") in response.text
    assert exercises.get_detail(migrated_engine, USER, ids["e"]).fields[1].params == weight.params


def test_duplicate_names_through_the_pages(client: TestClient, migrated_engine: Engine) -> None:
    catalog_ids(migrated_engine)
    response = client.post(
        "/exercices", json={"name": " SQUÂT ", "category": "strength", "location": "gym"}, headers=HTMX
    )
    assert response.status_code == 200
    assert TEXT("catalog.error.name_taken") in response.text
    assert 'value=" SQUÂT "' in response.text or "SQUÂT" in response.text
    assert len(exercises.list_exercises(migrated_engine, USER)) == 1


def test_duplicate_alias_through_the_page(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    response = client.post(f"/exercices/{ids['e']}/alias", json={"alias": "BACK-SQUAT"}, headers=HTMX)
    assert response.status_code == 200
    assert TEXT("catalog.error.alias_taken") in response.text
    assert 'aria-invalid="true"' in response.text
    assert len(exercises.get_detail(migrated_engine, USER, ids["e"]).aliases) == 1


def test_variable_labels_may_repeat_and_get_distinct_codes(
    client: TestClient, migrated_engine: Engine
) -> None:
    body = {"label": "Tempo", "scope": "set", "type": "int"}
    first = client.post("/variables", json=body, headers=HTMX)
    second = client.post("/variables", json=body, headers=HTMX)
    assert first.status_code == second.status_code == 204
    assert first.headers["hx-redirect"] != second.headers["hx-redirect"]


@pytest.mark.parametrize("label", ["x" * 40, "é" * 40])
def test_variable_label_at_its_limit_is_accepted(client: TestClient, label: str) -> None:
    response = client.post("/variables", json={"label": label, "scope": "set", "type": "int"}, headers=HTMX)
    assert response.status_code == 204


def test_variable_label_over_its_limit_is_refused_in_place(client: TestClient) -> None:
    response = client.post(
        "/variables", json={"label": "x" * 41, "scope": "set", "type": "int"}, headers=HTMX
    )
    assert response.status_code == 200
    assert TEXT("catalog.error.too_long", max=40) in response.text


def test_enum_relabel_through_the_page_keeps_keys(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    body = {
        "label": "Siège",
        "scope": "setting",
        "type": "enum",
        "value_label": "Premier cran",
        "value_key": "1",
    }
    response = client.patch(f"/variables/{ids['v']}", json=body, headers=HTMX)
    assert response.status_code == 200 and TEXT("status.saved") in response.text
    draft = variables.get_detail(migrated_engine, USER, ids["v"]).draft
    assert [(v.key, v.label) for v in draft.enum_values or ()] == [("1", "Premier cran")]


def test_enum_key_forged_by_a_client_is_refused(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    body = {
        "label": "Siège",
        "scope": "setting",
        "type": "enum",
        "value_label": ["1", "X"],
        "value_key": ["1", "forged"],
    }
    response = client.patch(f"/variables/{ids['v']}", json=body, headers=HTMX)
    assert response.status_code == 200
    assert TEXT("status.saved") not in response.text
    draft = variables.get_detail(migrated_engine, USER, ids["v"]).draft
    assert [v.key for v in draft.enum_values or ()] == ["1"]


@pytest.mark.parametrize("q", ["", "   ", "!!!", "x" * 500, "%", "_", "'; DROP TABLE exercise; --"])
def test_search_odd_queries_answer(client: TestClient, migrated_engine: Engine, q: str) -> None:
    catalog_ids(migrated_engine)
    fragment = client.get("/exercices/recherche", params={"q": q}, headers=HTMX)
    assert fragment.status_code == 200
    page = client.get("/exercices", params={"q": q}, headers=PAGE)
    assert page.status_code == 200
    assert len(exercises.list_exercises(migrated_engine, USER)) == 1


def test_search_url_is_kept_and_truncated(client: TestClient) -> None:
    fragment = client.get("/exercices/recherche", params={"q": "y" * 300, "archives": "1"}, headers=HTMX)
    replaced = fragment.headers["hx-replace-url"]
    assert replaced == "/exercices?q=" + "y" * 200 + "&archives=1"


def test_search_ranks_exact_before_prefix_before_fuzzy(client: TestClient, migrated_engine: Engine) -> None:
    for name in ("Jump squat", "Squaat sauté", "Squat bulgare", "Squat", "Fente"):
        exercises.create(migrated_engine, USER, ExerciseForm(name, "strength", "gym"))
    text = client.get("/exercices/recherche?q=squat", headers=HTMX).text
    titles = re.findall(r'<span class="row__title">([^<]*)', text)
    # exact, prefix, token prefix, fuzzy (edit distance 1); no match left out
    assert titles == ["Squat", "Squat bulgare", "Jump squat", "Squaat sauté"]


def test_archived_exercise_page_and_create_with_its_name(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    client.post(f"/exercices/{ids['e']}/archive", json={}, headers=HTMX)
    page = client.get(f"/exercices/{ids['e']}", headers=PAGE)
    assert page.status_code == 200 and TEXT("tag.archived_m") in page.text
    # an archived name stays taken
    response = client.post(
        "/exercices", json={"name": "squat", "category": "strength", "location": "gym"}, headers=HTMX
    )
    assert TEXT("catalog.error.name_taken") in response.text


def test_archive_twice_and_restore_twice_are_harmless(client: TestClient, migrated_engine: Engine) -> None:
    ids = catalog_ids(migrated_engine)
    for _ in range(2):
        assert client.post(f"/exercices/{ids['e']}/archive", json={}, headers=HTMX).status_code == 200
        assert client.post(f"/variables/{ids['v']}/archive", json={}, headers=HTMX).status_code == 200
    for _ in range(2):
        assert (
            client.request("DELETE", f"/exercices/{ids['e']}/archive", json={}, headers=HTMX).status_code
            == 200
        )
        assert (
            client.request("DELETE", f"/variables/{ids['v']}/archive", json={}, headers=HTMX).status_code
            == 200
        )
    assert not exercises.get_detail(migrated_engine, USER, ids["e"]).archived
    assert not variables.get_detail(migrated_engine, USER, ids["v"]).archived


def test_deleted_variable_is_gone_and_a_second_delete_is_404(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = catalog_ids(migrated_engine)
    exercises.add_field(migrated_engine, USER, ids["e"], variable_id=ids["v"])
    assert client.request("DELETE", f"/variables/{ids['v']}", json={}, headers=HTMX).status_code == 204
    assert all(f.variable is None for f in exercises.get_detail(migrated_engine, USER, ids["e"]).fields)
    assert client.request("DELETE", f"/variables/{ids['v']}", json={}, headers=HTMX).status_code == 404
