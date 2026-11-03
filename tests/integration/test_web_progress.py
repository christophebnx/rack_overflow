"""Progress pages, chart JSON, RM entries and the formula setting through the TestClient
(docs/ui-spec.md "L5 — Progress index", "L5 — Progress of an exercise", "L5 — Settings"; D-047,
D-050, D-053, D-068 to D-070)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from request_status import triggers_without_slot
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.services import exercises, progress, sessions
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
NBSP = "\u00a0"
TIMES = f"{NBSP}\u00d7{NBSP}"
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock


def make(engine: Engine, name: str = "Squat", category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def logged(engine: Engine, when: datetime, exercise_id: int, items: list[dict[str, str]]) -> int:
    session_id = sessions.start(engine, USER, None, "gym", when, UTC)
    block = sessions.pick(engine, USER, session_id, None, exercise_id).block
    assert block is not None
    for number, values in enumerate(items, start=1):
        kind = values.pop("type", "work")
        sessions.confirm_set(
            engine, USER, session_id, block.id, kind, values, when + timedelta(minutes=number)
        )
    sessions.close(engine, USER, session_id, when + timedelta(hours=1))
    return session_id


def lift(reps: int, kg: str, kind: str = "work") -> dict[str, str]:
    return {"reps": str(reps), "weight": kg, "type": kind}


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html, re.S)
    assert match is not None, html
    return match.group(1)


def autofocused(html: str) -> list[str]:
    return re.findall(r'id="([^"]+)"[^>]*\sautofocus', html)


@pytest.fixture
def squat(migrated_engine: Engine) -> int:
    exercise = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=20), exercise, [lift(8, "40", "warmup"), lift(5, "100")])
    logged(migrated_engine, NOW - timedelta(days=10), exercise, [lift(5, "105"), lift(1, "120", "rm_test")])
    return exercise


# --- index


def test_progress_index(client: TestClient, migrated_engine: Engine, squat: int) -> None:
    make(migrated_engine, "Bench")
    response = client.get("/progression", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert '<a class="site-nav__link" href="/progression" aria-current="page">' in html
    assert 'href="/reglages"' in html and f'href="/progression/{squat}"' in html
    assert TEXT("progress.item_sessions", count=2) in html and "24/10/2026" in html
    assert "Bench" not in html


def test_progress_index_empty(client: TestClient) -> None:
    html = client.get("/progression", headers=PAGE).text
    assert TEXT("progress.empty_title") in html and TEXT("progress.empty_text") in html


# --- progress page


def test_strength_progress_page(client: TestClient, squat: int) -> None:
    response = client.get(f"/progression/{squat}", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert '<a class="site-nav__link" href="/progression" aria-current="page">' in html
    assert f'href="/exercices/{squat}"' in html and TEXT("progress.sheet_link") in html
    assert TEXT("progress.last_heading") in html and TEXT("session.set_type.rm_test") in html
    # RM: the RM test of 24/10 is the measured 1RM; the estimate (5 x 105) is older, no flag
    assert 'id="rm"' in html and TEXT("rm.origin.rm_test", date="24/10/2026") in html
    assert TEXT("rm.estimate_beside", formula="Epley", value=f"122,5{NBSP}kg") in html
    assert TEXT("rm.flag", date="24/10/2026") not in html
    # chart: two days, the measured series too, so a legend; scripts loaded
    assert 'data-chart-src="/api/progression/' in html and 'class="chart" hidden' in html
    assert "chart-legend__item--2" in html
    assert '<script src="/static/vendor/chart.umd.min.js" defer></script>' in html
    assert '<script src="/static/js/progress-chart.js" defer></script>' in html
    assert TEXT("progress.chart_span", count=2, first="14/10/2026", last="24/10/2026") in html
    assert TEXT("progress.col.measured") in html and TEXT("progress.data_caption") in html
    # records
    assert TEXT("progress.record.max_load_by_reps") in html and TEXT("progress.record.session_volume") in html
    assert triggers_without_slot(html) == []


def test_one_day_and_no_history(client: TestClient, migrated_engine: Engine) -> None:
    once = make(migrated_engine, "Once")
    logged(migrated_engine, NOW - timedelta(days=1), once, [lift(5, "60")])
    html = client.get(f"/progression/{once}", headers=PAGE).text
    assert TEXT("progress.chart_one_point") in html and "data-chart-src" not in html
    assert (
        "chart.umd.min.js" not in html
        and TEXT("rm.origin.estimated", formula="Epley", set=f"5{TIMES}60{NBSP}kg", date="02/11/2026") in html
    )
    empty = client.get(f"/progression/{make(migrated_engine, 'Empty')}", headers=PAGE).text
    assert TEXT("progress.last_empty") in empty and TEXT("progress.chart_empty") in empty
    assert TEXT("progress.records_empty") in empty and TEXT("rm.no_data") in empty and TEXT("rm.add") in empty


def test_cardio_progress_page(client: TestClient, migrated_engine: Engine) -> None:
    run = make(migrated_engine, "Run", "cardio")
    logged(migrated_engine, NOW - timedelta(days=3), run, [{"duration": "26:40", "distance": "5"}])
    logged(migrated_engine, NOW - timedelta(days=1), run, [{"duration": "25:00", "distance": "5"}])
    html = client.get(f"/progression/{run}", headers=PAGE).text
    assert 'id="rm"' not in html
    assert TEXT("progress.record.best_pace") in html and TEXT("unit.pace", value="5:00") in html
    assert TEXT("unit.speed", value="12,0") in html
    assert TEXT("progress.chart_intro.distance") in html and "chart-legend" not in html
    assert TEXT("progress.chart_latest", value=f"5{NBSP}km", best=f"5{NBSP}km") in html


def test_progress_page_404(client: TestClient, migrated_engine: Engine) -> None:
    foreign = make(migrated_engine, "Theirs", user=OTHER)
    for path in (f"/progression/{foreign}", "/progression/999", "/api/progression/999", f"/rm/{foreign}"):
        assert client.get(path, headers=PAGE).status_code == 404


def test_exercise_sheet_links_to_its_progress(client: TestClient, migrated_engine: Engine) -> None:
    exercise = make(migrated_engine)
    html = client.get(f"/exercices/{exercise}", headers=PAGE).text
    assert f'<a class="button" href="/progression/{exercise}">{TEXT("progress.link")}</a>' in html


# --- chart JSON


def test_chart_json(client: TestClient, squat: int) -> None:
    response = client.get(f"/api/progression/{squat}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["labels"] == ["14/10", "24/10"]
    assert data["axis"] == TEXT("progress.axis.weight") and data["unit"] == "kg"
    assert data["tooltip"] == f"{{label}}{NBSP}: {{value}}{NBSP}kg"
    assert data["series"] == [
        {"label": "1RM estimé (Epley)", "kind": "line", "values": [116.7, 122.5]},
        {"label": "1RM mesuré", "kind": "points", "values": [None, 120.0]},
    ]
    foreign = client.get(f"/api/progression/{squat}", headers={"origin": "http://evil.example"})
    assert foreign.status_code == 403
    assert (
        client.get(f"/api/progression/{squat}", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    )


def test_chart_json_empty_and_kettlebell(client: TestClient, migrated_engine: Engine) -> None:
    assert client.get(f"/api/progression/{make(migrated_engine)}").json()["series"] == []
    swing = make(migrated_engine, "Swing", "kettlebell")
    logged(migrated_engine, NOW - timedelta(days=2), swing, [lift(15, "16"), lift(10, "24")])
    data = client.get(f"/api/progression/{swing}").json()
    assert [item["label"] for item in data["series"]] == [f"16{NBSP}kg", f"24{NBSP}kg"]
    assert data["axis"] == TEXT("progress.axis.reps") and data["tooltip"] == f"{{label}}{NBSP}: {{value}}"


# --- RM


def test_rm_section_routes(client: TestClient, migrated_engine: Engine, squat: int) -> None:
    fragment = client.get(f"/rm/{squat}", headers=HTMX)
    assert fragment.status_code == 200 and fragment.text.startswith('<section class="section rm" id="rm"')
    navigation = client.get(f"/rm/{squat}", headers=PAGE, follow_redirects=False)
    assert navigation.status_code == 303 and navigation.headers["location"] == f"/progression/{squat}#rm"
    run = make(migrated_engine, "Run", "cardio")
    assert client.get(f"/rm/{run}", headers=HTMX).status_code == 404


def test_measured_rm_saved_refused_and_deleted(
    client: TestClient, migrated_engine: Engine, squat: int
) -> None:
    saved = client.post(f"/rm/{squat}", json={"n": "1", "weight": "130", "date": "2026-11-01"}, headers=HTMX)
    assert saved.status_code == 200
    assert announced(saved.text) == TEXT("rm.saved", n=1, value=f"130{NBSP}kg")
    assert (
        autofocused(saved.text) == ["rm-saisir"] and '<details class="rm-add" id="rm-saisie">' in saved.text
    )
    assert TEXT("rm.origin.manual", date="01/11/2026") in saved.text
    second = client.post(f"/rm/{squat}", json={"n": "5", "weight": "110", "date": "2026-11-02"}, headers=HTMX)
    assert TEXT("rm.measures_heading") in second.text
    refused = client.post(f"/rm/{squat}", json={"n": "13", "weight": "0", "date": "2026-11-04"}, headers=HTMX)
    assert refused.status_code == 200 and 'aria-invalid="true"' in refused.text
    assert '<details class="rm-add" id="rm-saisie" open>' in refused.text
    assert (
        TEXT("catalog.error.rm_reps_range") in refused.text
        and TEXT("catalog.error.must_be_positive") in refused.text
    )
    assert TEXT("catalog.error.date_in_future") in refused.text
    measures = progress.rm_view(migrated_engine, USER, squat).measures
    newest, older = measures[0].measured_id, measures[1].measured_id
    deleted = client.request("DELETE", f"/rm/mesures/{newest}", json={}, headers=HTMX)
    assert deleted.status_code == 200 and announced(deleted.text) == TEXT("rm.deleted")
    assert autofocused(deleted.text) == [f"rm-mesure-{older}-supprimer"]
    last = client.request("DELETE", f"/rm/mesures/{older}", json={}, headers=HTMX)
    assert autofocused(last.text) == ["rm-saisir"]
    assert client.request("DELETE", f"/rm/mesures/{older}", json={}, headers=HTMX).status_code == 404
    assert triggers_without_slot(saved.text) == []


def test_rm_refused_outside_strength_and_non_json(
    client: TestClient, migrated_engine: Engine, squat: int
) -> None:
    run = make(migrated_engine, "Run", "cardio")
    refused = client.post(f"/rm/{run}", json={"n": "1", "weight": "100", "date": "2026-11-01"}, headers=HTMX)
    assert refused.status_code == 200 and TEXT("catalog.error.rm_not_strength") in refused.text
    form = client.post(f"/rm/{squat}", data={"n": "1"}, headers=HTMX)
    assert form.status_code == 415


# --- settings


def test_settings_page_and_formula_change(client: TestClient, migrated_engine: Engine, squat: int) -> None:
    response = client.get("/reglages", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    assert html.count('name="rm_formula"') == 5 and 'id="formule-epley" checked' in html
    assert TEXT("rm.formula_text.brzycki") in html and TEXT("settings.default_tag") in html
    assert "aria-current" not in html.split("</nav>")[0].split("<nav")[1]
    assert triggers_without_slot(html) == []
    saved = client.patch("/reglages", json={"rm_formula": "brzycki"}, headers=HTMX)
    assert saved.status_code == 200 and 'id="formule-brzycki" checked autofocus' in saved.text
    assert announced(saved.text) == TEXT("settings.formula_saved", formula="Brzycki")
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    assert TEXT("rm.formula_line", formula="Brzycki") in page
    refused = client.patch("/reglages", json={"rm_formula": "magic"}, headers=HTMX)
    assert refused.status_code == 200 and TEXT("catalog.error.invalid_choice") in refused.text
    assert 'id="formule-brzycki" checked' in refused.text
