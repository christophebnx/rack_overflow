"""Variable pages through the TestClient (docs/ui-spec.md L2 — Variable screens; D-050, D-054)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from request_status import triggers_without_slot
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.domain.catalog import ValueInput
from rack_overflow.services import exercises, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1


def seat_body(**extra: object) -> dict[str, object]:
    return {
        "label": "Siège",
        "scope": "setting",
        "type": "enum",
        "values": "\n".join(map(str, range(1, 11))),
        **extra,
    }


def create_seat(client: TestClient) -> int:
    response = client.post("/variables", json=seat_body(), headers=HTMX)
    assert response.status_code == 204
    return int(response.headers["hx-redirect"].rsplit("/", 1)[1])


def test_empty_list_page(client: TestClient) -> None:
    response = client.get("/variables", headers=PAGE)
    result = assert_secure_page(response, 200)
    assert "Aucune variable." in response.text
    assert 'href="/variables" aria-current="page"' in response.text
    assert "/variables/nouvelle" in result.urls


def test_create_page_and_create(client: TestClient, migrated_engine: Engine) -> None:
    page = client.get("/variables/nouvelle", headers=PAGE)
    assert_secure_page(page, 200)
    assert "<title>Nouvelle variable · Rack Overflow</title>" in page.text
    assert triggers_without_slot(page.text) == []
    variable_id = create_seat(client)
    detail = variables.get_detail(migrated_engine, USER, variable_id)
    assert detail.draft.scope == "setting" and len(detail.draft.enum_values or ()) == 10
    listed = client.get("/variables", headers=PAGE).text
    assert (
        "Siège" in listed and "Liste de choix" in listed and TEXT("variables.linked_count", count=0) in listed
    )


def test_refused_create_rerenders_the_form_with_messages(client: TestClient) -> None:
    response = client.post("/variables", json={"label": "", "type": "enum", "values": ""}, headers=HTMX)
    assert response.status_code == 200
    assert 'id="libelle-erreur"' in response.text and "À renseigner." in response.text
    assert 'aria-invalid="true"' in response.text
    assert 'id="annonce" hx-swap-oob="innerHTML">À renseigner.' in response.text
    assert "Au moins une valeur." in response.text
    assert triggers_without_slot(response.text) == []


def test_create_from_an_exercise_goes_back_with_preselection(
    client: TestClient, migrated_engine: Engine
) -> None:
    exercise_id = exercises.create(migrated_engine, USER, ExerciseForm("Presse", "strength", "gym"))
    page = client.get(f"/variables/nouvelle?exercice={exercise_id}", headers=PAGE).text
    assert TEXT("variable.for_exercise", name="Presse") in page
    assert f'href="/exercices/{exercise_id}"' in page
    response = client.post("/variables", json=seat_body(exercice=str(exercise_id)), headers=HTMX)
    assert response.headers["hx-redirect"].startswith(f"/exercices/{exercise_id}?ajout=")
    unknown = client.get("/variables/nouvelle?exercice=999", headers=PAGE).text
    assert TEXT("variable.for_exercise", name="Presse") not in unknown


def test_edit_page_and_save(client: TestClient, migrated_engine: Engine) -> None:
    variable_id = create_seat(client)
    page = client.get(f"/variables/{variable_id}", headers=PAGE)
    assert_secure_page(page, 200)
    assert "<title>Siège · Rack Overflow</title>" in page.text
    assert triggers_without_slot(page.text) == []
    body = {
        "label": "Hauteur du siège",
        "scope": "setting",
        "type": "enum",
        "value_label": [str(n) for n in range(1, 11)],
        "value_key": [str(n) for n in range(1, 11)],
        "value_remove": "10",
        "values": "11\n12",
    }
    response = client.patch(f"/variables/{variable_id}", json=body, headers=HTMX)
    assert response.status_code == 200
    assert 'data-kind="ok"' in response.text and "Modifications enregistrées." in response.text
    assert '<span id="variable-titre" hx-swap-oob="true">Hauteur du siège</span>' in response.text
    keys = [v.key for v in variables.get_detail(migrated_engine, USER, variable_id).draft.enum_values or ()]
    assert keys == [*map(str, range(1, 10)), "11", "12"]


def test_frozen_attributes_are_text_and_used_values_have_no_remove(
    client: TestClient, migrated_engine: Engine
) -> None:
    variable_id = create_seat(client)
    exercise_id = exercises.create(migrated_engine, USER, ExerciseForm("Presse", "strength", "gym"))
    exercises.add_field(migrated_engine, USER, exercise_id, variable_id=variable_id)
    with migrated_engine.begin() as connection:
        session_id = connection.execute(
            sa.insert(s.session).values(
                user_id=USER,
                local_date="2026-11-03",
                time_zone="UTC",
                started_at="2026-11-03T18:00:00Z",
                location="gym",
                status="open",
            )
        ).inserted_primary_key[0]
        se = connection.execute(
            sa.insert(s.session_exercise).values(session_id=session_id, exercise_id=exercise_id, position=0)
        ).inserted_primary_key[0]
        connection.execute(
            sa.insert(s.exercise_setting).values(
                session_exercise_id=se, variable_id=variable_id, value_text="3"
            )
        )
    page = client.get(f"/variables/{variable_id}", headers=PAGE).text
    assert 'name="scope"' not in page and 'name="type"' not in page
    assert "Ne peut plus changer" in page
    assert 'name="value_remove" value="3"' not in page and 'name="value_remove" value="4"' in page
    assert TEXT("variable.value_in_use") in page
    assert "Supprimer…" not in page
    assert TEXT("variable.shared_hint") in page
    # the page does not send frozen attributes: the stored ones are kept
    body = {
        "label": "Siège",
        "value_label": [str(n) for n in range(1, 11)],
        "value_key": [str(n) for n in range(1, 11)],
    }
    response = client.patch(f"/variables/{variable_id}", json=body, headers=HTMX)
    assert "Modifications enregistrées." in response.text
    refused = client.request("DELETE", f"/variables/{variable_id}", json={}, headers=HTMX)
    assert refused.status_code == 200
    assert TEXT("catalog.error.variable_in_use") in refused.text
    assert 'id="variable-archiver"' in refused.text and "autofocus" in refused.text


def test_archive_restore_and_delete(client: TestClient, migrated_engine: Engine) -> None:
    variable_id = create_seat(client)
    archived = client.post(f"/variables/{variable_id}/archive", json={}, headers=HTMX)
    assert archived.status_code == 200
    assert 'id="variable-restaurer"' in archived.text and "Variable archivée." in archived.text
    assert (
        '<span id="variable-etat" hx-swap-oob="true"><span class="tag">Archivée</span></span>'
        in archived.text
    )
    assert triggers_without_slot(archived.text) == []
    assert "Siège" not in client.get("/variables", headers=PAGE).text.split("<main")[1]
    assert "Siège" in client.get("/variables?archivees=1", headers=PAGE).text
    restored = client.request("DELETE", f"/variables/{variable_id}/archive", json={}, headers=HTMX)
    assert 'id="variable-archiver"' in restored.text and "Variable restaurée." in restored.text
    confirm = client.get(f"/variables/{variable_id}/suppression", headers=HTMX)
    assert TEXT("variable.confirm_delete_title", label="Siège") in confirm.text
    assert triggers_without_slot(confirm.text) == []
    cancelled = client.get(f"/variables/{variable_id}/suppression?annuler=1", headers=HTMX)
    assert 'id="variable-supprimer"' in cancelled.text and "autofocus" in cancelled.text
    deleted = client.request("DELETE", f"/variables/{variable_id}", json={}, headers=HTMX)
    assert deleted.status_code == 204 and deleted.headers["hx-redirect"] == "/variables"
    assert client.get(f"/variables/{variable_id}", headers=PAGE).status_code == 404


def test_delete_of_a_last_measure_is_refused_in_the_archive_block(
    client: TestClient, migrated_engine: Engine
) -> None:
    exercise_id = exercises.create(migrated_engine, USER, ExerciseForm("Planche", "bodyweight", "both"))
    variable_id = variables.create(migrated_engine, USER, VariableForm("Tenue", "int", "set"))
    exercises.add_field(migrated_engine, USER, exercise_id, variable_id=variable_id)
    reps = exercises.get_detail(migrated_engine, USER, exercise_id).fields[0]
    exercises.remove_field(migrated_engine, USER, exercise_id, reps.id)
    refused = client.request("DELETE", f"/variables/{variable_id}", json={}, headers=HTMX)
    assert refused.status_code == 200
    assert TEXT("catalog.error.variable_last_measure", exercises="Planche") in refused.text
    scope = client.patch(
        f"/variables/{variable_id}", json={"label": "Tenue", "type": "int", "scope": "setting"}, headers=HTMX
    )
    assert TEXT("catalog.error.variable_last_measure", exercises="Planche") in scope.text
    assert "role-set-erreur" in scope.text


def test_unknown_and_foreign_ids_are_404(client: TestClient, migrated_engine: Engine) -> None:
    theirs = variables.create(migrated_engine, 2, VariableForm("X", "enum", "set", values=[ValueInput("a")]))
    assert client.get(f"/variables/{theirs}", headers=PAGE).status_code == 404
    response = client.patch(f"/variables/{theirs}", json={"label": "Y"}, headers=HTMX)
    assert response.status_code == 404 and response.json() == {"error": "not_found"}
    assert client.post("/variables/999/archive", json={}, headers=HTMX).status_code == 404
    assert client.request("DELETE", "/variables/999", json={}, headers=HTMX).status_code == 404


@pytest.mark.parametrize(("method", "path"), [("post", "/variables"), ("patch", "/variables/1")])
def test_form_encoded_bodies_are_refused(client: TestClient, method: str, path: str) -> None:
    response = client.request(method.upper(), path, data={"label": "x"}, headers=HTMX)
    assert response.status_code == 415


def test_unpaired_requests_are_refused(unpaired_client: TestClient) -> None:
    page = unpaired_client.get("/variables", headers=PAGE, follow_redirects=False)
    assert page.status_code == 303
    action = unpaired_client.post("/variables", json={}, headers=HTMX)
    assert action.status_code == 401 and action.headers["hx-redirect"] == "/appairage"


def test_body_that_fails_validation_is_422(client: TestClient) -> None:
    response = client.post("/variables", json={"label": "x" * 500}, headers=HTMX)
    assert response.status_code == 422 and response.json() == {"error": "invalid_request"}
