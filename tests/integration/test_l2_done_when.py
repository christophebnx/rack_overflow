"""The L2 "Done when" of docs/roadmap.md, each as one scenario through the HTTP routes (paired
TestClient, migrated unseeded database unless the seed is asked for). History rows do not exist in
the UI yet: they are inserted directly."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.services import exercises, seed, variables
from rack_overflow.storage import migrate
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1


def created_id(response: object) -> int:
    assert response.status_code == 204, response.text  # type: ignore[attr-defined]
    target = response.headers["hx-redirect"]  # type: ignore[attr-defined]
    return int(target.split("?", 1)[0].rsplit("/", 1)[1])


def create_exercise(client: TestClient, name: str, category: str, location: str = "gym") -> int:
    body = {"name": name, "category": category, "location": location}
    return created_id(client.post("/exercices", json=body, headers=HTMX))


def add_source(client: TestClient, exercise_id: int, source: str) -> str:
    response = client.post(f"/exercices/{exercise_id}/champs", json={"source": source}, headers=HTMX)
    assert response.status_code == 200
    return response.text


def field_of(engine: Engine, exercise_id: int, *, quantity: str | None = None, label: str | None = None):
    for field in exercises.get_detail(engine, USER, exercise_id).fields:
        if quantity is not None and field.core_quantity == quantity:
            return field
        if label is not None and field.variable is not None and field.variable.draft.label == label:
            return field
    raise AssertionError(f"no field {quantity or label}")


def counts(engine: Engine) -> dict[str, int]:
    with engine.begin() as connection:
        return {
            table.name: connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in s.metadata.sorted_tables
        }


def store_history(
    engine: Engine, exercise_id: int, variable_id: int | None = None, *, deleted: bool = False
) -> None:
    """A session with the exercise, one set (soft-deleted on demand) and its variable value."""
    with engine.begin() as connection:
        session_id = connection.execute(
            sa.insert(s.session).values(
                user_id=USER,
                local_date="2026-11-03",
                time_zone="Europe/Paris",
                started_at="2026-11-03T18:00:00Z",
                location="gym",
                status="closed",
                ended_at="2026-11-03T19:00:00Z",
            )
        ).inserted_primary_key[0]
        session_exercise_id = connection.execute(
            sa.insert(s.session_exercise).values(session_id=session_id, exercise_id=exercise_id, position=0)
        ).inserted_primary_key[0]
        set_id = connection.execute(
            sa.insert(s.set_entry).values(
                session_exercise_id=session_exercise_id,
                position=0,
                reps=10,
                weight_g=60000,
                deleted_at="2026-11-03T18:30:00Z" if deleted else None,
            )
        ).inserted_primary_key[0]
        if variable_id is not None:
            connection.execute(
                sa.insert(s.set_value).values(set_entry_id=set_id, variable_id=variable_id, value_int=7)
            )


def test_seat_enum_linked_to_two_exercises_without_migration(
    client: TestClient, migrated_engine: Engine
) -> None:
    revision = migrate.current_revision(migrated_engine)
    press = create_exercise(client, "Presse à cuisses", "strength")
    bench = create_exercise(client, "Développé couché machine", "strength")
    body = {
        "label": "Siège",
        "scope": "setting",
        "type": "enum",
        "values": "\n".join(map(str, range(1, 11))),
        "exercice": str(press),
    }
    response = client.post("/variables", json=body, headers=HTMX)
    seat = created_id(response)
    assert response.headers["hx-redirect"] == f"/exercices/{press}?ajout={seat}"
    add_source(client, press, f"variable:{seat}")
    add_source(client, bench, f"variable:{seat}")
    draft = variables.get_detail(migrated_engine, USER, seat).draft
    assert [(v.key, v.label) for v in draft.enum_values or ()] == [(str(n), str(n)) for n in range(1, 11)]
    assert {e.name for e in variables.get_detail(migrated_engine, USER, seat).linked} == {
        "Presse à cuisses",
        "Développé couché machine",
    }
    assert migrate.current_revision(migrated_engine) == revision
    # one shared row: a rename shows on both exercise pages, keys untouched
    rename = {
        "label": "Réglage siège",
        "scope": "setting",
        "type": "enum",
        "value_label": [str(n) for n in range(1, 11)],
        "value_key": [str(n) for n in range(1, 11)],
    }
    assert client.patch(f"/variables/{seat}", json=rename, headers=HTMX).status_code == 200
    for exercise_id in (press, bench):
        assert "Réglage siège" in client.get(f"/exercices/{exercise_id}", headers=PAGE).text
    renamed = variables.get_detail(migrated_engine, USER, seat).draft
    assert [v.key for v in renamed.enum_values or ()] == [str(n) for n in range(1, 11)]


def test_kettlebell_swing_with_discrete_loads(client: TestClient, migrated_engine: Engine) -> None:
    swing = create_exercise(client, "Kettlebell swing", "kettlebell", "home")
    weight = field_of(migrated_engine, swing, quantity="weight")
    body = {
        "required": "on",
        "mode": "values",
        "increment": "2,5",
        "discrete_values": "16 20 24",
        "default": "16",
    }
    response = client.patch(f"/exercices/{swing}/champs/{weight.id}", json=body, headers=HTMX)
    assert response.status_code == 200 and TEXT("status.saved") in response.text
    saved = field_of(migrated_engine, swing, quantity="weight").params
    assert saved.discrete_values == (16000, 20000, 24000)
    assert saved.increment is None and saved.default_int == 16000 and saved.required
    assert "16 · 20 · 24\u00a0kg" in client.get(f"/exercices/{swing}", headers=PAGE).text


def test_bike_with_duration_distance_and_a_resistance_created_in_the_ui(
    client: TestClient, migrated_engine: Engine
) -> None:
    bike = create_exercise(client, "Vélo", "cardio")
    page = client.get(f"/variables/nouvelle?exercice={bike}", headers=PAGE)
    assert page.status_code == 200
    body = {"label": "Résistance", "scope": "set", "type": "int", "exercice": str(bike)}
    response = client.post("/variables", json=body, headers=HTMX)
    resistance = created_id(response)
    assert response.headers["hx-redirect"] == f"/exercices/{bike}?ajout={resistance}"
    preselected = client.get(f"/exercices/{bike}?ajout={resistance}", headers=PAGE).text
    assert f'value="variable:{resistance}" selected' in preselected
    add_source(client, bike, f"variable:{resistance}")
    fields = exercises.get_detail(migrated_engine, USER, bike).fields
    assert [(f.core_quantity, f.variable.draft.label if f.variable else None) for f in fields] == [
        ("duration", None),
        ("distance", None),
        (None, "Résistance"),
    ]
    assert fields[2].variable is not None and fields[2].variable.draft.scope == "set"
    # durations and distances are typed in display units and stored canonical
    duration, distance = fields[0], fields[1]
    client.patch(
        f"/exercices/{bike}/champs/{duration.id}",
        json={"increment": "1:00", "default": "45:00"},
        headers=HTMX,
    )
    client.patch(
        f"/exercices/{bike}/champs/{distance.id}",
        json={"increment": "100 m", "default": "15,5"},
        headers=HTMX,
    )
    assert field_of(migrated_engine, bike, quantity="duration").params.default_int == 2700
    assert field_of(migrated_engine, bike, quantity="distance").params.increment == 100
    assert field_of(migrated_engine, bike, quantity="distance").params.default_int == 15500


def test_unused_variable_can_be_archived(client: TestClient, migrated_engine: Engine) -> None:
    bench = create_exercise(client, "Banc", "strength")
    body = {"label": "Inclinaison", "scope": "setting", "type": "int", "unit": "°"}
    incline = created_id(client.post("/variables", json=body, headers=HTMX))
    assert client.post(f"/variables/{incline}/archive", json={}, headers=HTMX).status_code == 200
    assert variables.get_detail(migrated_engine, USER, incline).archived
    assert "Inclinaison" not in client.get("/variables", headers=PAGE).text.split("<main", 1)[1]
    assert "Inclinaison" in client.get("/variables?archivees=1", headers=PAGE).text
    # an archived variable is no longer offered when adding a field, and cannot be linked
    assert f"variable:{incline}" not in client.get(f"/exercices/{bench}", headers=PAGE).text
    refused = add_source(client, bench, f"variable:{incline}")
    assert TEXT("catalog.error.invalid_choice") in refused
    assert all(f.variable is None for f in exercises.get_detail(migrated_engine, USER, bench).fields)


def test_variable_linked_to_exercises_with_history_cannot_be_deleted(
    client: TestClient, migrated_engine: Engine
) -> None:
    bike = create_exercise(client, "Vélo", "cardio")
    resistance = created_id(
        client.post("/variables", json={"label": "Résistance", "scope": "set", "type": "int"}, headers=HTMX)
    )
    add_source(client, bike, f"variable:{resistance}")
    # history kept even when the set was soft-deleted (invariant 8)
    store_history(migrated_engine, bike, resistance, deleted=True)
    before = counts(migrated_engine)
    page = client.get(f"/variables/{resistance}", headers=PAGE).text
    assert 'id="variable-supprimer"' not in page
    assert client.get(f"/variables/{resistance}/suppression", headers=HTMX).status_code == 200
    refused = client.request("DELETE", f"/variables/{resistance}", json={}, headers=HTMX)
    assert refused.status_code == 200
    assert TEXT("catalog.error.variable_in_use") in refused.text
    assert counts(migrated_engine) == before
    # archiving stays possible and keeps the link and values
    assert client.post(f"/variables/{resistance}/archive", json={}, headers=HTMX).status_code == 200
    assert counts(migrated_engine) == before


def test_archiving_an_exercise_with_history_deletes_no_data(
    client: TestClient, migrated_engine: Engine
) -> None:
    squat = create_exercise(client, "Squat", "strength")
    tempo = created_id(
        client.post("/variables", json={"label": "Tempo", "scope": "set", "type": "int"}, headers=HTMX)
    )
    add_source(client, squat, f"variable:{tempo}")
    client.post(f"/exercices/{squat}/alias", json={"alias": "Back squat"}, headers=HTMX)
    store_history(migrated_engine, squat, tempo)
    before = counts(migrated_engine)
    archived = client.post(f"/exercices/{squat}/archive", json={}, headers=HTMX)
    assert archived.status_code == 200
    assert counts(migrated_engine) == before
    assert exercises.get_detail(migrated_engine, USER, squat).archived
    assert exercises.get_detail(migrated_engine, USER, squat).has_history
    # out of the list and the search, back on demand, page still reachable
    assert "Squat" not in client.get("/exercices", headers=PAGE).text.split("<main", 1)[1]
    assert "Squat" in client.get("/exercices?archives=1", headers=PAGE).text
    hidden = client.get("/exercices/recherche?q=back", headers=HTMX).text
    assert "Squat" not in hidden
    assert "Squat" in client.get("/exercices/recherche?q=back&archives=1", headers=HTMX).text
    assert client.get(f"/exercices/{squat}", headers=PAGE).status_code == 200
    # restoring brings it back unchanged
    client.request("DELETE", f"/exercices/{squat}/archive", json={}, headers=HTMX)
    assert counts(migrated_engine) == before


def test_bench_press_found_by_dc_bench_and_developpe(client: TestClient, migrated_engine: Engine) -> None:
    assert seed.seed_catalog(migrated_engine, USER).exercises == 41
    for query in ("DC", "bench", "developpe", "dc", "Bench", "DÉVELOPPÉ"):
        response = client.get(f"/exercices/recherche?q={query}", headers=HTMX)
        assert response.status_code == 200
        main = response.text
        first = main.find("Développé couché (barre)")
        assert first != -1, query
        # it is the first result listed
        for other in ("Développé couché haltères", "Développé haltères au sol"):
            position = main.find(other)
            assert position == -1 or first < position, (query, other)
