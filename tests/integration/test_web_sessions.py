"""Session logging pages through the TestClient (docs/ui-spec.md "L4 — …"; D-050 refusals, D-053
slots, D-061 to D-066): home in both states, start, plan, picks, steppers, sets, records, settings,
close and summary, closed-session redirects, 404s, JSON only."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from request_status import triggers_without_slot, write_triggers
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.services import exercises, seed, sessions, templates, variables
from rack_overflow.services.sessions import SessionView
from rack_overflow.services.variables import VariableForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
NBSP = "\u00a0"
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock


@pytest.fixture
def seeded(migrated_engine: Engine) -> Engine:
    seed.seed_catalog(migrated_engine, USER)
    return migrated_engine


def template_id(engine: Engine, prefix: str) -> int:
    return next(t.id for t in templates.list_templates(engine, USER) if t.draft.name.startswith(prefix))


def exercise_id(engine: Engine, name: str) -> int:
    return next(e.id for e in exercises.list_exercises(engine, USER) if e.draft.name == name)


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html, re.S)
    assert match is not None, html
    return match.group(1)


def autofocused(html: str) -> list[str]:
    return re.findall(r'id="([^"]+)"[^>]*\sautofocus', html)


def start(client: TestClient, template: int | str = "", location: str = "gym") -> int:
    response = client.post(
        "/seances", json={"template_id": str(template), "location": location}, headers=HTMX
    )
    assert response.status_code == 204, response.text
    return int(response.headers["HX-Redirect"].rsplit("/", 1)[1])


def view(engine: Engine, session_id: int) -> SessionView:
    found = sessions.show(engine, USER, session_id)
    assert isinstance(found, SessionView)
    return found


def row_of(engine: Engine, session_id: int, name: str) -> int:
    return next(i for i, card in view(engine, session_id).cards.items() if card.exercise.name == name)


def confirm(client: TestClient, session_id: int, row: int, **values: str) -> object:
    body = {"session_exercise_id": str(row), "type": values.pop("type", "work"), **values}
    return client.post(f"/seances/{session_id}/series", json=body, headers=HTMX)


# --- home


def test_home_offers_the_templates_and_the_free_session(client: TestClient, seeded: Engine) -> None:
    response = client.get("/", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert TEXT("home.start_title") in html and TEXT("home.free_session") in html
    assert 'name="location" value="gym" id="lieu-gym" checked' in html
    assert html.count('class="button start__template"') == 4
    assert 'data-location="home"' in html and 'data-location="both"' in html  # Cardio
    assert TEXT("home.last_used") not in html
    assert triggers_without_slot(html) == []
    assert TEXT("home.no_template_gym") not in html


def test_home_without_templates_shows_the_empty_lines(client: TestClient) -> None:
    html = client.get("/", headers=PAGE).text
    assert TEXT("home.no_template_gym") in html and TEXT("home.no_template_home") in html
    assert 'href="/seances-types/nouvelle"' in html


def test_start_redirects_and_home_then_resumes(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    assert start(client, "", "home") == session_id  # double tap or second device
    html = client.get("/", headers=PAGE).text
    assert TEXT("home.open_title") in html and TEXT("home.resume") in html
    assert f'href="/seances/{session_id}"' in html
    assert f"Salle{NBSP}· commencée à 19:04".replace(NBSP, " ") in html  # 18:04 UTC in Brussels
    assert TEXT("home.open_counts", exercises=0, sets=0) in html
    assert "hx-post" not in html


def test_start_refusals_re_render_the_form(client: TestClient, seeded: Engine) -> None:
    salle_a = template_id(seeded, "Salle A")
    templates.set_archived(seeded, USER, salle_a, NOW)
    response = client.post("/seances", json={"template_id": str(salle_a), "location": "home"}, headers=HTMX)
    assert response.status_code == 200
    assert TEXT("catalog.error.template_unavailable") in response.text
    assert announced(response.text) == TEXT("catalog.error.template_unavailable")
    assert 'value="home" id="lieu-home" checked' in response.text
    assert (
        client.post("/seances", json={"template_id": "x", "location": "gym"}, headers=HTMX).status_code == 422
    )
    form = client.post(
        "/seances",
        content=b"template_id=&location=gym",
        headers={**HTMX, "content-type": "application/x-www-form-urlencoded"},
    )
    assert form.status_code == 415


# --- session page


def test_session_page_from_salle_a(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    response = client.get(f"/seances/{session_id}", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert "<title>Salle A — Squat &amp; poussée horizontale · Rack Overflow</title>" in html
    assert html.count('<li aria-current="step">') == 1
    squat = row_of(seeded, session_id, "Squat au rack (barre)")
    assert f'id="exercice-{squat}-valider"' in html
    assert TEXT("session.confirm_set", n=1) in html
    assert f'id="exercice-{squat}-reps" name="reps" type="text" inputmode="numeric" value="6"' in html
    assert TEXT("session.first_value_hint") in html  # no weight yet: keyboard once
    assert TEXT("session.menu_pending") in html and TEXT("template.tag_menu") in html
    assert TEXT("session.next_item", name="Développé couché (barre)") in html
    assert f'hx-swap="outerHTML show:#exercice-{squat}-actions:bottom"' in html
    assert TEXT("session.recent_heading") in html  # the session's own exercises
    assert TEXT("session.all_heading") in html
    assert triggers_without_slot(html) == []
    assert write_triggers(html) > 40
    # every button of a form is disabled during its request (htmx `find` would take the first only)
    assert f'hx-disabled-elt="#exercice-{squat}-serie button"' in html
    assert 'hx-disabled-elt="find button"' not in html


def test_requested_items_and_unknown_ones(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    found = view(seeded, session_id)
    pull = next(i for i, m in found.menus.items() if m.label == "Tirage horizontal")
    html = client.get(f"/seances/{session_id}?menu={pull}", headers=PAGE).text
    assert f'<section class="session-block" id="menu-{pull}"' in html
    assert TEXT("session.menu_intro") in html
    for query in ("exercice=abc", "exercice=99999999999999999999", "menu=0", "exercice=999"):
        assert client.get(f"/seances/{session_id}?{query}", headers=PAGE).status_code == 200


def test_free_session_opens_the_add_block(client: TestClient, seeded: Engine) -> None:
    session_id = start(client)
    html = client.get(f"/seances/{session_id}", headers=PAGE).text
    assert "<title>Séance libre · Rack Overflow</title>" in html
    assert TEXT("session.empty_title") in html
    assert '<details class="session-add" id="ajout" open>' in html


def test_pick_add_and_change(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    found = view(seeded, session_id)
    pull = next(i for i, m in found.menus.items() if m.label == "Tirage horizontal")
    options = {o.name: o.id for o in found.menus[pull].options}
    response = client.post(
        f"/seances/{session_id}/exercices",
        json={"slot_id": str(pull), "exercise_id": str(options["Rowing barre au rack"])},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert response.text.startswith('<ol class="session-plan" id="seance-plan">')
    assert announced(response.text) == TEXT("session.announce_picked", name="Rowing barre au rack")
    row = row_of(seeded, session_id, "Rowing barre au rack")
    assert autofocused(response.text) == [f"exercice-{row}-valider"]
    assert TEXT("session.change_exercise") in response.text
    again = client.post(
        f"/seances/{session_id}/exercices",
        json={"slot_id": str(pull), "exercise_id": str(options["Rowing assis machine"])},
        headers=HTMX,
    )
    assert announced(again.text) == TEXT("catalog.error.slot_already_picked")
    changed = client.patch(
        f"/seances/{session_id}/exercices/{row}",
        json={"exercise_id": str(options["Tirage horizontal poulie"])},
        headers=HTMX,
    )
    assert announced(changed.text) == TEXT("session.announce_picked", name="Tirage horizontal poulie")
    curl = exercise_id(seeded, "Curl barre EZ")
    added = client.post(f"/seances/{session_id}/exercices", json={"exercise_id": str(curl)}, headers=HTMX)
    assert announced(added.text) == TEXT("session.announce_added", name="Curl barre EZ")
    assert '<details class="session-add" id="ajout" hx-swap-oob="true">' in added.text
    refused = client.patch(
        f"/seances/{session_id}/exercices/{row}", json={"exercise_id": str(curl)}, headers=HTMX
    )
    assert announced(refused.text) == TEXT("catalog.error.exercise_unavailable")
    assert f"exercice-{row}-changer-erreur" in refused.text


def test_search_groups_and_change_mode(client: TestClient, seeded: Engine) -> None:
    session_id = start(client)
    curl = exercise_id(seeded, "Curl barre EZ")
    client.post(f"/seances/{session_id}/exercices", json={"exercise_id": str(curl)}, headers=HTMX)
    results = client.get(f"/seances/{session_id}/recherche?q=", headers=HTMX).text
    assert results.index(TEXT("session.recent_heading")) < results.index(TEXT("session.all_heading"))
    assert f'id="ajout-{curl}"' in results and triggers_without_slot(f"<div>{results}</div>") == []
    ranked = client.get(f"/seances/{session_id}/recherche?q=dc", headers=HTMX).text
    assert "Développé couché" in ranked and announced(ranked).startswith("Résultats")
    none = client.get(f"/seances/{session_id}/recherche?q=zzzzzz", headers=HTMX).text
    assert TEXT("exercises.no_match", query="zzzzzz") in none
    row = row_of(seeded, session_id, "Curl barre EZ")
    change = client.get(f"/seances/{session_id}/recherche?q=&ligne={row}", headers=HTMX).text
    assert f'hx-patch="/seances/{session_id}/exercices/{row}"' in change
    navigation = client.get(f"/seances/{session_id}/recherche?q=x", headers=PAGE, follow_redirects=False)
    assert navigation.status_code == 303


def test_stepper_answers_the_form_without_writing(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    squat = row_of(seeded, session_id, "Squat au rack (barre)")
    url = f"/seances/{session_id}/exercices/{squat}/serie"
    response = client.get(
        url, params={"type": "work", "reps": "8", "weight": "60", "pas": "weight:up"}, headers=HTMX
    )
    assert response.status_code == 200
    assert response.text.startswith(f'<form class="set-form" id="exercice-{squat}-serie"')
    assert (
        f'id="exercice-{squat}-weight" name="weight" type="text" inputmode="decimal" value="62,5"'
        in response.text
    )
    assert f'aria-label="Augmenter Charge de 2,5{NBSP}kg"' in response.text
    down = client.get(url, params={"type": "warmup", "reps": "1", "pas": "reps:down"}, headers=HTMX).text
    assert f'id="exercice-{squat}-reps-moins"' in down and 'value="0"' in down
    assert re.search(rf'id="exercice-{squat}-reps-moins"[^>]*disabled', down)
    assert 'value="warmup" id="exercice-' in down and f'id="exercice-{squat}-type-warmup" checked' in down
    assert view(seeded, session_id).cards[squat].set_count == 0


def test_confirm_sets_records_and_announcements(client: TestClient, seeded: Engine) -> None:
    first = start(client, template_id(seeded, "Salle A"))
    squat = row_of(seeded, first, "Squat au rack (barre)")
    assert confirm(client, first, squat, reps="8", weight="60").status_code == 200
    client.post(f"/seances/{first}/cloture", json={}, headers=HTMX)
    second = start(client, template_id(seeded, "Salle A"))
    squat2 = row_of(seeded, second, "Squat au rack (barre)")
    page = client.get(f"/seances/{second}", headers=PAGE).text
    assert f'id="exercice-{squat2}-weight" name="weight" type="text" inputmode="decimal" value="60"' in page
    response = confirm(client, second, squat2, reps="8", weight="62,5")
    html = response.text
    assert html.startswith(f'<section class="session-block" id="exercice-{squat2}"')
    record = TEXT("session.announce_set_record", n=1, text=f"8{NBSP}\u00d7{NBSP}62,5{NBSP}kg")
    assert announced(html) == record
    assert '<span class="tag tag--record">Record</span>' in html
    assert autofocused(html) == [f"exercice-{squat2}-valider"]
    assert TEXT("session.confirm_set", n=2) in html
    assert triggers_without_slot(html) == []
    plain = confirm(client, second, squat2, reps="8", weight="62,5")
    assert announced(plain.text) == TEXT(
        "session.announce_set_saved", n=2, text=f"8{NBSP}\u00d7{NBSP}62,5{NBSP}kg"
    )


def test_refused_set_keeps_the_values(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    squat = row_of(seeded, session_id, "Squat au rack (barre)")
    html = confirm(client, session_id, squat, reps="huit", weight="").text
    assert f'id="exercice-{squat}-reps" name="reps" type="text" inputmode="numeric" value="huit"' in html
    assert 'aria-invalid="true"' in html
    assert announced(html) == f"{TEXT('catalog.error.not_a_number')}"
    assert autofocused(html)[0] == f"exercice-{squat}-reps"
    empty = client.post(
        f"/seances/{session_id}/series",
        json={"session_exercise_id": str(squat), "type": "work", "reps": "", "weight": ""},
        headers=HTMX,
    ).text
    assert TEXT("catalog.error.required") in empty
    planche = exercise_id(seeded, "Planche")
    added = sessions.pick(seeded, USER, session_id, None, planche).block
    assert added is not None
    optional = exercises.get_detail(seeded, USER, planche).fields[0]
    exercises.update_field(
        seeded, USER, planche, optional.id, exercises.FieldForm(required=False, increment="15")
    )
    nothing = confirm(client, session_id, added.id, duration="")
    assert TEXT("catalog.error.empty_set") in nothing.text
    assert f'id="exercice-{added.id}-serie-erreur"' in nothing.text
    assert confirm(client, session_id, 999999, reps="1").status_code == 404
    bad = client.post(f"/seances/{session_id}/series", json={"type": "work"}, headers=HTMX)
    assert bad.status_code == 422
    too_long = confirm(client, session_id, squat, reps="1" * 201)
    assert too_long.status_code == 422


def test_edit_and_delete_a_set(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    squat = row_of(seeded, session_id, "Squat au rack (barre)")
    confirm(client, session_id, squat, reps="8", weight="60")
    confirm(client, session_id, squat, reps="8", weight="60")
    sets = view(seeded, session_id).block.sets  # type: ignore[union-attr]
    edited = client.patch(
        f"/series/{sets[0].id}", json={"type": "warmup", "reps": "10", "weight": "40"}, headers=HTMX
    )
    assert announced(edited.text) == TEXT("session.announce_set_updated", n=1)
    assert autofocused(edited.text) == [f"serie-{sets[0].id}-modifier"]
    assert TEXT("session.set_type.warmup") in edited.text
    refused = client.patch(
        f"/series/{sets[0].id}", json={"type": "work", "reps": "x", "weight": "40"}, headers=HTMX
    )
    assert '<details class="set-row__edit" open>' in refused.text
    assert f'id="serie-{sets[0].id}-reps"' in refused.text and 'value="x"' in refused.text
    deleted = client.request("DELETE", f"/series/{sets[0].id}", json={}, headers=HTMX)
    assert announced(deleted.text) == TEXT("session.announce_set_deleted", n=1)
    assert autofocused(deleted.text) == [f"serie-{sets[1].id}-modifier"]
    last = client.request("DELETE", f"/series/{sets[1].id}", json={}, headers=HTMX)
    assert autofocused(last.text) == [f"exercice-{squat}-valider"]
    assert client.request("DELETE", f"/series/{sets[1].id}", json={}, headers=HTMX).status_code == 404
    assert client.patch("/series/99999999999999999999", json={}, headers=HTMX).status_code == 404


def test_settings_saved_on_change(client: TestClient, seeded: Engine) -> None:
    press = exercise_id(seeded, "Presse à cuisses")
    seat = variables.create(seeded, USER, VariableForm(label="Siège", var_type="int", scope="setting"))
    exercises.add_field(seeded, USER, press, variable_id=seat)
    session_id = start(client)
    row = sessions.pick(seeded, USER, session_id, None, press).block
    assert row is not None
    page = client.get(f"/seances/{session_id}", headers=PAGE).text
    assert TEXT("session.settings_summary", values=f"Siège{NBSP}—") in page
    assert f'hx-patch="/seances/{session_id}/exercices/{row.id}/reglages" hx-trigger="change"' in page
    saved = client.patch(
        f"/seances/{session_id}/exercices/{row.id}/reglages", json={f"var_{seat}": "4"}, headers=HTMX
    )
    assert saved.text.startswith(f'<form class="settings-form" id="exercice-{row.id}-reglages"')
    assert 'data-kind="ok">' + TEXT("session.settings_saved") in saved.text
    assert f'<span id="exercice-{row.id}-reglages-resume" hx-swap-oob="innerHTML">' in saved.text
    assert TEXT("session.settings_summary", values=f"Siège{NBSP}4") in saved.text
    refused = client.patch(
        f"/seances/{session_id}/exercices/{row.id}/reglages", json={f"var_{seat}": "x"}, headers=HTMX
    )
    assert 'aria-invalid="true"' in refused.text and 'value="x"' in refused.text


def test_close_flow_summary_and_closed_redirects(client: TestClient, seeded: Engine) -> None:
    session_id = start(client, template_id(seeded, "Salle A"))
    squat = row_of(seeded, session_id, "Squat au rack (barre)")
    confirm(client, session_id, squat, type="warmup", reps="10", weight="40")
    confirm(client, session_id, squat, reps="8", weight="60")
    ask = client.get(f"/seances/{session_id}/cloture", headers=HTMX).text
    assert TEXT("session.close_confirm_title") in ask and TEXT("session.close_unlogged", count=5) in ask
    assert triggers_without_slot(ask) == []
    back = client.get(f"/seances/{session_id}/cloture?annuler=1", headers=HTMX).text
    assert autofocused(back) == ["terminer"]
    closed = client.post(f"/seances/{session_id}/cloture", json={}, headers=HTMX)
    assert closed.headers["HX-Redirect"] == f"/seances/{session_id}"
    summary = client.get(f"/seances/{session_id}", headers=PAGE)
    assert_secure_page(summary, 200)
    html = summary.text
    assert TEXT("session.summary_meta", location="Salle") in html
    assert "03/11/2026 · 19:04\u201319:04 · 0" in html.replace(NBSP, " ")
    assert TEXT("session.summary.volume", value=f"480{NBSP}kg") in html
    assert TEXT("session.summary.warmups", count=1) in html
    assert TEXT("session.closed_notice") not in html
    notice = client.get(f"/seances/{session_id}?terminee=1", headers=PAGE).text
    assert TEXT("session.closed_notice") in notice and 'role="alert"' in notice
    redirect = f"/seances/{session_id}?terminee=1"
    for response in (
        confirm(client, session_id, squat, reps="8", weight="60"),
        client.post(f"/seances/{session_id}/exercices", json={"exercise_id": "1"}, headers=HTMX),
        client.get(f"/seances/{session_id}/exercices/{squat}/serie?pas=reps:up", headers=HTMX),
        client.get(f"/seances/{session_id}/cloture", headers=HTMX),
        client.patch(f"/seances/{session_id}/exercices/{squat}/reglages", json={}, headers=HTMX),
        client.patch(f"/seances/{session_id}/exercices/{squat}", json={"exercise_id": "1"}, headers=HTMX),
    ):
        assert response.status_code == 204 and response.headers["HX-Redirect"] == redirect
    set_id = sessions.show(seeded, USER, session_id).rows[0].sets[0].id  # type: ignore[union-attr]
    assert (
        client.patch(f"/series/{set_id}", json={"type": "work", "reps": "1"}, headers=HTMX).headers[
            "HX-Redirect"
        ]
        == redirect
    )
    assert (
        client.request("DELETE", f"/series/{set_id}", json={}, headers=HTMX).headers["HX-Redirect"]
        == redirect
    )
    assert client.post(f"/seances/{session_id}/cloture", json={}, headers=HTMX).status_code == 204


def test_foreign_and_unknown_sessions_are_404(client: TestClient, seeded: Engine) -> None:
    other = sessions.start(seeded, OTHER, None, "gym", NOW, UTC)
    for path in (f"/seances/{other}", "/seances/999", "/seances/0", "/seances/99999999999999999999"):
        assert client.get(path, headers=PAGE).status_code == 404
    assert client.post(f"/seances/{other}/cloture", json={}, headers=HTMX).status_code == 404
    assert client.get(f"/seances/{other}/recherche?q=", headers=HTMX).status_code == 404
    assert (
        client.post(f"/seances/{other}/series", json={"session_exercise_id": "1"}, headers=HTMX).status_code
        == 404
    )


def test_summary_of_an_empty_session(client: TestClient, seeded: Engine) -> None:
    session_id = start(client)
    client.post(f"/seances/{session_id}/cloture", json={}, headers=HTMX)
    html = client.get(f"/seances/{session_id}", headers=PAGE).text
    assert TEXT("session.summary_empty") in html and "summary-totals" not in html
