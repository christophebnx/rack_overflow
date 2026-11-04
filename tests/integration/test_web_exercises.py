"""Exercise pages, fields, aliases and search through the TestClient (docs/ui-spec.md L2; D-050,
D-053 slots, D-054, D-056)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from request_status import triggers_without_slot
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.domain.catalog import ValueInput
from rack_overflow.services import exercises, seed, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
BENCH = "Développé couché (barre)"


def new(engine: Engine, name: str = "Kettlebell swing", category: str = "kettlebell") -> int:
    return exercises.create(engine, USER, ExerciseForm(name, category, "home"))


def fields(engine: Engine, exercise_id: int) -> list[exercises.FieldView]:
    return list(exercises.get_detail(engine, USER, exercise_id).fields)


def delete(client: TestClient, path: str) -> object:
    return client.request("DELETE", path, json={}, headers=HTMX)


def test_empty_list(client: TestClient) -> None:
    response = client.get("/exercices", headers=PAGE)
    assert_secure_page(response, 200)
    assert TEXT("exercises.empty_title") in response.text
    assert 'href="/exercices" aria-current="page"' in response.text
    assert 'data-message="Recherche impossible, réessayer"' in response.text


def test_seeded_list_grouped_and_search(client: TestClient, migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    page = client.get("/exercices", headers=PAGE).text
    assert page.index(TEXT("exercise.category.strength")) < page.index(TEXT("exercise.category.cardio"))
    for query in ("DC", "bench", "developpe"):
        response = client.get(f"/exercices/recherche?q={query}", headers=HTMX)
        assert response.status_code == 200
        first = response.text.index('class="row__title"')
        assert response.text[first:].split(">", 1)[1].startswith(BENCH)
        assert response.headers["hx-replace-url"] == f"/exercices?q={query}"
        assert (
            'id="annonce" hx-swap-oob="innerHTML">' + TEXT("exercises.results", count=0)[:9] in response.text
        )
    ranked = client.get("/exercices?q=dc", headers=PAGE)
    assert_secure_page(ranked, 200)
    assert 'value="dc"' in ranked.text and BENCH in ranked.text
    none = client.get("/exercices/recherche?q=zzzz", headers=HTMX).text
    assert TEXT("exercises.no_match", query="zzzz") in none
    assert TEXT("exercises.results", count=0) in none


def test_search_navigation_goes_to_the_page(client: TestClient) -> None:
    response = client.get("/exercices/recherche?q=dc&archives=1", headers=PAGE, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/exercices?q=dc&archives=1"


def test_archived_only_on_demand(client: TestClient, migrated_engine: Engine) -> None:
    swing = new(migrated_engine)
    exercises.set_archived(migrated_engine, USER, swing, None)
    client.post(f"/exercices/{swing}/archive", json={}, headers=HTMX)
    assert "Kettlebell swing" not in client.get("/exercices", headers=PAGE).text.split("<main")[1]
    shown = client.get("/exercices?archives=1", headers=PAGE).text
    assert "Kettlebell swing" in shown and TEXT("tag.archived_m") in shown
    found = client.get("/exercices/recherche?q=swing&archives=1", headers=HTMX)
    assert found.headers["hx-replace-url"] == "/exercices?q=swing&archives=1"
    assert "Kettlebell swing" in found.text


def test_create_page_create_and_refusals(client: TestClient, migrated_engine: Engine) -> None:
    page = client.get("/exercices/nouveau", headers=PAGE)
    assert_secure_page(page, 200)
    assert triggers_without_slot(page.text) == []
    assert 'value="both" required checked' in page.text
    body = {"name": "Vélo", "category": "cardio", "location": "gym", "movement_pattern": "", "equipment": ""}
    created = client.post("/exercices", json=body, headers=HTMX)
    assert created.status_code == 204
    exercise_id = int(created.headers["hx-redirect"].rsplit("/", 1)[1])
    assert [f.core_quantity for f in fields(migrated_engine, exercise_id)] == ["duration", "distance"]
    refused = client.post("/exercices", json={**body, "name": "velo"}, headers=HTMX)
    assert refused.status_code == 200
    assert TEXT("catalog.error.name_taken") in refused.text and 'id="nom-erreur"' in refused.text
    assert 'aria-invalid="true"' in refused.text and "autofocus" in refused.text
    missing = client.post("/exercices", json={"name": "X", "location": "gym"}, headers=HTMX)
    assert 'id="categorie-strength-erreur"' in missing.text


def test_detail_page_and_save(client: TestClient, migrated_engine: Engine) -> None:
    swing = new(migrated_engine)
    page = client.get(f"/exercices/{swing}", headers=PAGE)
    assert_secure_page(page, 200)
    assert "<title>Kettlebell swing · Rack Overflow</title>" in page.text
    assert triggers_without_slot(page.text) == []
    assert "Pas\u00a0: 2,5\u00a0kg" in page.text
    body = {"name": "KB swing", "category": "kettlebell", "location": "home", "movement_pattern": "Charnière"}
    saved = client.patch(f"/exercices/{swing}", json=body, headers=HTMX)
    assert 'data-kind="ok"' in saved.text
    assert '<span id="exercice-titre" hx-swap-oob="true">KB swing</span>' in saved.text


def test_kettlebell_loads_through_the_page(client: TestClient, migrated_engine: Engine) -> None:
    swing = new(migrated_engine)
    weight = fields(migrated_engine, swing)[1]
    body = {
        "required": "1",
        "mode": "values",
        "increment": "2,5",
        "discrete_values": "16 20 24",
        "default": "20",
    }
    response = client.patch(f"/exercices/{swing}/champs/{weight.id}", json=body, headers=HTMX)
    assert response.status_code == 200
    assert "Valeurs\u00a0: 16 · 20 · 24\u00a0kg" in response.text
    assert "Par défaut\u00a0: 20\u00a0kg" in response.text
    assert f'id="champ-{weight.id}-modifier" autofocus' in response.text
    assert fields(migrated_engine, swing)[1].params.discrete_values == (16000, 20000, 24000)
    refused = client.patch(
        f"/exercices/{swing}/champs/{weight.id}", json={"mode": "step", "increment": "abc"}, headers=HTMX
    )
    assert TEXT("catalog.error.not_a_number") in refused.text
    assert f'id="champ-{weight.id}-pas-erreur"' in refused.text
    assert '<details class="field-row__edit" open>' in refused.text
    assert 'value="abc"' in refused.text


def test_add_move_and_remove_fields(client: TestClient, migrated_engine: Engine) -> None:
    bike = new(migrated_engine, "Vélo", "cardio")
    resistance = variables.create(
        migrated_engine, USER, VariableForm("Résistance", "int", "set", unit="niveau")
    )
    page = client.get(f"/exercices/{bike}?ajout={resistance}", headers=PAGE).text
    assert f'<option value="variable:{resistance}" selected>' in page
    assert 'id="champ-ajout" name="source" required autofocus' in page
    added = client.post(f"/exercices/{bike}/champs", json={"source": f"variable:{resistance}"}, headers=HTMX)
    assert TEXT("exercise.announce_field_added", field="Résistance") in added.text
    new_field = fields(migrated_engine, bike)[-1]
    assert f'id="champ-{new_field.id}-obligatoire" name="required" value="1" autofocus' in added.text
    duration = fields(migrated_engine, bike)[0]
    moved = client.post(
        f"/exercices/{bike}/champs/{new_field.id}/deplacement", json={"direction": "up"}, headers=HTMX
    )
    assert TEXT("exercise.announce_field_moved", field="Résistance", position=2, total=3) in moved.text
    assert f'id="champ-{new_field.id}-monter"' in moved.text
    top = client.post(
        f"/exercices/{bike}/champs/{new_field.id}/deplacement", json={"direction": "up"}, headers=HTMX
    )
    assert f'id="champ-{new_field.id}-descendre" hx-post' in top.text
    assert f'aria-label="{TEXT("field.move_down_named", field="Résistance")}" autofocus' in top.text
    removed = delete(client, f"/exercices/{bike}/champs/{duration.id}")
    assert TEXT("exercise.announce_field_removed", field=TEXT("quantity.duration")) in removed.text  # type: ignore[attr-defined]
    empty = client.post(f"/exercices/{bike}/champs", json={"source": ""}, headers=HTMX)
    assert 'id="champ-ajout-erreur"' in empty.text
    unknown = client.post(f"/exercices/{bike}/champs", json={"source": "variable:999"}, headers=HTMX)
    assert TEXT("catalog.error.invalid_choice") in unknown.text


def test_last_measure_is_refused_in_place(client: TestClient, migrated_engine: Engine) -> None:
    plank = new(migrated_engine, "Planche", "bodyweight")
    reps = fields(migrated_engine, plank)[0]
    refused = delete(client, f"/exercices/{plank}/champs/{reps.id}")
    assert refused.status_code == 200  # type: ignore[attr-defined]
    assert TEXT("catalog.error.last_measure") in refused.text  # type: ignore[attr-defined]
    assert f'id="champ-{reps.id}-retirer-erreur"' in refused.text  # type: ignore[attr-defined]


def test_enum_and_bool_fields_have_selects(client: TestClient, migrated_engine: Engine) -> None:
    press = new(migrated_engine, "Presse", "strength")
    seat = variables.create(
        migrated_engine,
        USER,
        VariableForm("Siège", "enum", "setting", values=[ValueInput("Bas"), ValueInput("Haut")]),
    )
    flag = variables.create(migrated_engine, USER, VariableForm("Ceinture", "bool", "setting"))
    for variable_id in (seat, flag):
        exercises.add_field(migrated_engine, USER, press, variable_id=variable_id)
    seat_field, flag_field = fields(migrated_engine, press)[2:]
    client.patch(f"/exercices/{press}/champs/{seat_field.id}", json={"default": "haut"}, headers=HTMX)
    page = client.patch(
        f"/exercices/{press}/champs/{flag_field.id}", json={"default": "1"}, headers=HTMX
    ).text
    assert "Par défaut\u00a0: Haut" in page and "Par défaut\u00a0: Oui" in page
    assert '<option value="haut" selected>Haut</option>' in page
    assert 'name="mode"' in page  # numeric rows only
    assert page.count('name="mode" value="step"') == 2


def test_aliases(client: TestClient, migrated_engine: Engine) -> None:
    bench = new(migrated_engine, BENCH, "strength")
    added = client.post(f"/exercices/{bench}/alias", json={"alias": "DC"}, headers=HTMX)
    assert TEXT("exercise.announce_alias_added", alias="DC") in added.text
    assert 'id="alias-nouveau" name="alias" type="text" value=""' in added.text
    assert triggers_without_slot(added.text) == []
    refused = client.post(f"/exercices/{bench}/alias", json={"alias": "dc"}, headers=HTMX)
    assert TEXT("catalog.error.alias_taken") in refused.text and 'value="dc"' in refused.text
    alias_id = exercises.get_detail(migrated_engine, USER, bench).aliases[0].id
    removed = delete(client, f"/exercices/{bench}/alias/{alias_id}")
    assert TEXT("exercise.announce_alias_removed", alias="DC") in removed.text  # type: ignore[attr-defined]
    assert TEXT("exercise.no_alias") in removed.text  # type: ignore[attr-defined]


def test_archive_and_restore(client: TestClient, migrated_engine: Engine) -> None:
    swing = new(migrated_engine)
    archived = client.post(f"/exercices/{swing}/archive", json={}, headers=HTMX)
    assert 'id="exercice-restaurer"' in archived.text and TEXT("exercise.announce_archived") in archived.text
    assert '<span id="exercice-etat" hx-swap-oob="true"><span class="tag">' in archived.text
    restored = delete(client, f"/exercices/{swing}/archive")
    assert 'id="exercice-archiver"' in restored.text  # type: ignore[attr-defined]


def test_unknown_and_foreign_ids_are_404(client: TestClient, migrated_engine: Engine) -> None:
    theirs = exercises.create(migrated_engine, 2, ExerciseForm("Squat", "strength", "gym"))
    assert client.get(f"/exercices/{theirs}", headers=PAGE).status_code == 404
    assert client.patch(f"/exercices/{theirs}", json={"name": "x"}, headers=HTMX).status_code == 404
    assert client.post(f"/exercices/{theirs}/alias", json={"alias": "x"}, headers=HTMX).status_code == 404
    mine = new(migrated_engine)
    their_field = exercises.get_detail(migrated_engine, 2, theirs).fields[0].id
    assert client.patch(f"/exercices/{mine}/champs/{their_field}", json={}, headers=HTMX).status_code == 404
    assert delete(client, f"/exercices/{mine}/alias/999").status_code == 404  # type: ignore[attr-defined]


def test_form_encoded_is_refused(client: TestClient) -> None:
    assert client.post("/exercices", data={"name": "x"}, headers=HTMX).status_code == 415


def test_unpaired_is_sent_to_pairing(unpaired_client: TestClient) -> None:
    assert unpaired_client.get("/exercices", headers=PAGE, follow_redirects=False).status_code == 303
    action = unpaired_client.post("/exercices", json={}, headers=HTMX)
    assert action.status_code == 401 and action.headers["hx-redirect"] == "/appairage"


@pytest.mark.parametrize("direction", ["left", ""])
def test_bad_move_direction_is_refused(client: TestClient, migrated_engine: Engine, direction: str) -> None:
    swing = new(migrated_engine)
    reps = fields(migrated_engine, swing)[0]
    response = client.post(
        f"/exercices/{swing}/champs/{reps.id}/deplacement", json={"direction": direction}, headers=HTMX
    )
    assert response.status_code == 422
