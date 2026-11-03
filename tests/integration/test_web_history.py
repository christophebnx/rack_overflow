"""History, closed-session detail and session delete through the TestClient (docs/ui-spec.md
"L5 — History", "L5 — Session detail and corrections"; D-050, D-053, D-067, D-070)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from request_status import triggers_without_slot, write_triggers
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.services import exercises, sessions, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.sessions import SummaryView
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
NBSP = "\u00a0"
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock (a Tuesday)


def make(engine: Engine, name: str = "Squat", category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def logged(
    engine: Engine,
    when: datetime,
    sets: dict[int, list[dict[str, str]]],
    *,
    close: bool = True,
    user: int = USER,
) -> int:
    session_id = sessions.start(engine, user, None, "gym", when, UTC)
    for exercise_id, items in sets.items():
        block = sessions.pick(engine, user, session_id, None, exercise_id).block
        assert block is not None
        for number, values in enumerate(items, start=1):
            kind = values.pop("type", "work")
            sessions.confirm_set(
                engine, user, session_id, block.id, kind, values, when + timedelta(minutes=number)
            )
    if close:
        sessions.close(engine, user, session_id, when + timedelta(hours=1))
    return session_id


def lift(reps: int, kg: str, kind: str = "work") -> dict[str, str]:
    return {"reps": str(reps), "weight": kg, "type": kind}


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html, re.S)
    assert match is not None, html
    return match.group(1)


def autofocused(html: str) -> list[str]:
    return re.findall(r'id="([^"]+)"[^>]*\sautofocus', html)


def summary(engine: Engine, session_id: int) -> SummaryView:
    found = sessions.show(engine, USER, session_id)
    assert isinstance(found, SummaryView)
    return found


# --- history list


def test_empty_history(client: TestClient) -> None:
    response = client.get("/historique", headers=PAGE)
    audit = assert_secure_page(response, 200)
    html = response.text
    assert TEXT("history.empty_title") in html and 'href="/"' in html
    assert TEXT("history.consistency_heading") not in html
    assert '<a class="site-nav__link" href="/historique" aria-current="page">' in html
    assert audit.problems == []


def test_history_lists_sessions_with_consistency(client: TestClient, migrated_engine: Engine) -> None:
    squat, bench = make(migrated_engine), make(migrated_engine, "Bench")
    logged(migrated_engine, NOW - timedelta(days=40), {squat: [lift(5, "100")]})
    logged(
        migrated_engine,
        NOW - timedelta(hours=5),
        {squat: [lift(8, "40", "warmup"), lift(5, "100")], bench: [lift(5, "80")]},
    )
    logged(migrated_engine, NOW - timedelta(hours=2), {})
    logged(migrated_engine, NOW - timedelta(hours=1), {}, close=False)
    html = client.get("/historique", headers=PAGE).text
    assert TEXT("history.this_week", count=1) in html
    assert TEXT("history.week_average", value="0,2") in html
    assert html.count('class="week-chart__item') == 12
    assert TEXT("history.week_item_current", date="02/11", count=1) in html
    assert "week-chart__bar--1" in html and "week-chart__bar--0" in html
    assert ">novembre 2026</h2>" in html and ">septembre 2026</h2>" in html
    assert TEXT("history.open_tag") in html and TEXT("history.no_sets") in html
    assert TEXT("history.item_when", weekday="mar.", date="03/11", time="13:04") in html
    assert (
        TEXT("session.summary.sets", count=2) + " · " + TEXT("session.summary.volume", value=f"900{NBSP}kg")
        in html
    )
    assert "Squat · Bench" in html
    assert TEXT("history.more") not in html


def test_history_pages_by_keyset(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    ids = [
        logged(migrated_engine, NOW - timedelta(days=30 - i), {squat: [lift(5, "100")]}) for i in range(22)
    ]
    html = client.get("/historique", headers=PAGE).text
    match = re.search(r'hx-get="/historique\?avant=(\d+)"', html)
    assert match is not None and int(match.group(1)) == ids[2]
    assert triggers_without_slot(html) == []
    fragment = client.get(f"/historique?avant={ids[2]}", headers=HTMX)
    assert fragment.status_code == 200
    assert "<h1" not in fragment.text and "<h2" not in fragment.text  # October continues
    assert f'href="/seances/{ids[1]}" autofocus' in fragment.text
    assert announced(fragment.text) == TEXT("history.loaded", count=2)
    assert TEXT("history.more") not in fragment.text
    page = client.get(f"/historique?avant={ids[2]}", headers=PAGE).text
    assert ">octobre 2026</h2>" in page and TEXT("history.consistency_heading") not in page
    assert client.get("/historique?avant=abc", headers=PAGE).status_code == 422


def test_history_after_delete_shows_the_notice(client: TestClient) -> None:
    html = client.get("/historique?supprimee=1", headers=PAGE).text
    assert TEXT("history.deleted_notice") in html and 'data-kind="ok" role="status"' in html


def test_nav_has_five_links_in_two_groups(client: TestClient) -> None:
    html = client.get("/exercices", headers=PAGE).text
    nav = html[html.index('<nav class="site-nav"') : html.index("</nav>")]
    assert nav.count("<ul") == 2 and "site-nav__list--tracking" in nav
    links = re.findall(r'href="([^"]+)"', nav)
    assert links == ["/historique", "/progression", "/exercices", "/variables", "/seances-types"]


# --- closed session detail


@pytest.fixture
def closed(migrated_engine: Engine) -> dict[str, int]:
    squat = make(migrated_engine)
    seat = variables.create(
        migrated_engine, USER, VariableForm(label="Siège", var_type="int", scope="setting")
    )
    exercises.add_field(migrated_engine, USER, squat, variable_id=seat)
    logged(migrated_engine, NOW - timedelta(days=7), {squat: [lift(5, "100")]})
    session_id = logged(
        migrated_engine,
        NOW - timedelta(days=1),
        {squat: [lift(8, "40", "warmup"), lift(5, "90"), lift(5, "95")]},
    )
    found = summary(migrated_engine, session_id)
    row = found.rows[0]
    return {
        "s": session_id,
        "r": row.id,
        "e": squat,
        "v": seat,
        **{f"t{i}": item.id for i, item in enumerate(row.sets)},
    }


def test_closed_session_page_is_the_detail(client: TestClient, closed: dict[str, int]) -> None:
    response = client.get(f"/seances/{closed['s']}", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert '<a class="site-nav__link" href="/historique" aria-current="page">' in html
    assert f'id="exercice-{closed["r"]}"' in html and 'id="seance-totaux"' in html
    assert f'href="/progression/{closed["e"]}"' in html and TEXT("progress.link") in html
    assert f'hx-patch="/series/{closed["t1"]}"' in html and f'hx-delete="/series/{closed["t1"]}"' in html
    assert f'hx-patch="/seances/{closed["s"]}/exercices/{closed["r"]}/reglages"' in html
    assert TEXT("session.settings_hint_closed") in html
    assert 'id="seance-suppression"' in html and TEXT("session.delete") in html
    assert '/series"' not in html and 'hx-post="/seances/' not in html  # no next-set form
    assert triggers_without_slot(html) == [] and write_triggers(html) >= 7


def test_correcting_a_closed_set_answers_the_section(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    response = client.patch(
        f"/series/{closed['t1']}", json={"type": "work", "reps": "5", "weight": "120"}, headers=HTMX
    )
    assert response.status_code == 200 and "HX-Redirect" not in response.headers
    html = response.text
    assert html.startswith(
        f'<section class="section session-block session-detail" id="exercice-{closed["r"]}"'
    )
    assert TEXT("session.record") in html
    assert 'id="seance-totaux" hx-swap-oob="true"' in html
    assert announced(html) == TEXT("session.announce_set_updated", n=2)
    assert autofocused(html) == [f"serie-{closed['t1']}-modifier"]
    assert summary(migrated_engine, closed["s"]).rows[0].sets[1].facts.value("weight") == 120000


def test_a_refused_closed_correction_keeps_the_values(client: TestClient, closed: dict[str, int]) -> None:
    response = client.patch(
        f"/series/{closed['t1']}", json={"type": "work", "reps": "x", "weight": "120"}, headers=HTMX
    )
    assert response.status_code == 200
    html = response.text
    assert f'id="serie-{closed["t1"]}-reps"' in html and 'aria-invalid="true"' in html
    assert 'value="x"' in html and '<details class="set-row__edit" open>' in html
    assert announced(html) == TEXT("catalog.error.not_a_number")


def test_deleting_closed_sets_moves_the_focus(client: TestClient, closed: dict[str, int]) -> None:
    first = client.request("DELETE", f"/series/{closed['t1']}", json={}, headers=HTMX)
    assert first.status_code == 200
    assert autofocused(first.text) == [f"serie-{closed['t2']}-modifier"]
    assert announced(first.text) == TEXT("session.announce_set_deleted", n=2)
    client.request("DELETE", f"/series/{closed['t2']}", json={}, headers=HTMX)
    last = client.request("DELETE", f"/series/{closed['t0']}", json={}, headers=HTMX)
    assert TEXT("session.exercise_no_sets") in last.text
    assert autofocused(last.text) == [f"exercice-{closed['r']}-progression"]
    assert client.request("DELETE", f"/series/{closed['t0']}", json={}, headers=HTMX).status_code == 404


def test_correcting_a_closed_setting(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    path = f"/seances/{closed['s']}/exercices/{closed['r']}/reglages"
    saved = client.patch(path, json={f"var_{closed['v']}": "6"}, headers=HTMX)
    assert saved.status_code == 200
    assert TEXT("session.settings_saved") in saved.text and 'data-kind="ok"' in saved.text
    assert TEXT("session.settings_summary", values=f"Siège{NBSP}6") in saved.text
    assert summary(migrated_engine, closed["s"]).rows[0].settings == {closed["v"]: 6}
    refused = client.patch(path, json={f"var_{closed['v']}": "abc"}, headers=HTMX)
    assert refused.status_code == 200 and 'aria-invalid="true"' in refused.text
    assert announced(refused.text) == TEXT("catalog.error.not_a_number")


def test_other_writes_on_a_closed_session_still_redirect(client: TestClient, closed: dict[str, int]) -> None:
    body = {"session_exercise_id": str(closed["r"]), "type": "work", "reps": "5", "weight": "100"}
    response = client.post(f"/seances/{closed['s']}/series", json=body, headers=HTMX)
    assert (
        response.status_code == 204
        and response.headers["HX-Redirect"] == f"/seances/{closed['s']}?terminee=1"
    )


# --- session delete


def test_delete_confirmation_and_delete(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    sid = closed["s"]
    confirm = client.get(f"/seances/{sid}/suppression", headers=HTMX)
    assert confirm.status_code == 200
    assert (
        TEXT("session.delete_confirm_title") in confirm.text
        and TEXT("session.delete_confirm_text") in confirm.text
    )
    assert autofocused(confirm.text) == ["seance-suppression-annuler"]
    assert triggers_without_slot(confirm.text) == []
    back = client.get(f"/seances/{sid}/suppression?annuler=1", headers=HTMX)
    assert autofocused(back.text) == ["seance-supprimer"]
    assert client.delete(f"/seances/{sid}", headers=HTMX).status_code == 415  # JSON only
    deleted = client.request("DELETE", f"/seances/{sid}", json={}, headers=HTMX)
    assert deleted.status_code == 204 and deleted.headers["HX-Redirect"] == "/historique?supprimee=1"
    assert client.get(f"/seances/{sid}", headers=PAGE).status_code == 404
    assert client.request("DELETE", f"/seances/{sid}", json={}, headers=HTMX).status_code == 404
    assert client.get(f"/seances/{sid}/suppression", headers=HTMX).status_code == 404
    html = client.get("/historique", headers=PAGE).text
    assert f'href="/seances/{sid}"' not in html
    with migrated_engine.begin() as connection:
        row = connection.execute(sa.select(s.session.c.deleted_at).where(s.session.c.id == sid)).scalar_one()
    assert row is not None


def test_open_session_has_the_delete_block_and_can_be_deleted(
    client: TestClient, migrated_engine: Engine
) -> None:
    squat = make(migrated_engine)
    sid = logged(migrated_engine, NOW, {squat: [lift(5, "100")]}, close=False)
    html = client.get(f"/seances/{sid}", headers=PAGE).text
    assert html.index('id="fin-de-seance"') < html.index('id="seance-suppression"')
    assert '<a class="site-nav__link" href="/historique" aria-current="page">' not in html
    assert client.request("DELETE", f"/seances/{sid}", json={}, headers=HTMX).status_code == 204
    assert sessions.start_page(migrated_engine, USER).open is None


def test_foreign_sessions_cannot_be_deleted(client: TestClient, migrated_engine: Engine) -> None:
    other = sessions.start(migrated_engine, OTHER, None, "gym", NOW, UTC)
    assert client.request("DELETE", f"/seances/{other}", json={}, headers=HTMX).status_code == 404
    assert client.get(f"/seances/{other}/suppression", headers=HTMX).status_code == 404
    assert client.request("DELETE", "/seances/99999999999999999999", json={}, headers=HTMX).status_code == 404
    foreign = client.request(
        "DELETE", f"/seances/{other}", json={}, headers={**HTMX, "origin": "http://evil.example"}
    )
    assert foreign.status_code == 403
