"""Every L5 route against the security rules (JSON only, same origin, paired device, ids beyond
the integer range, foreign and unknown ids), and edge states of the history and progress pages:
keyset page boundaries, a deleted anchor, local dates at day boundaries, chart JSON shapes per
category, the closed-session write rules of D-067 and the chart assets (D-034, D-047, D-049,
D-053, D-067 to D-070)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.services import exercises, history, progress, sessions
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.sessions import SummaryView
from rack_overflow.storage import schema as s
from rack_overflow.web import app as web_app
from rack_overflow.web.app import CATALOG
from rack_overflow.web.forms import MAX_ID
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.routes import history as history_routes
from rack_overflow.web.routes import progress as progress_routes

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
HUGE = str(MAX_ID + 1)
NBSP = "\u00a0"
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock (a Tuesday)
PARIS = ZoneInfo("Europe/Paris")
FOREIGN = [{"origin": "http://evil.example"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}]
STATIC = Path(web_app.__file__).parent / "static"

# every non-GET route of L5, ids filled in by `ids_of`
ACTIONS = [
    ("POST", "/rm/{e}"),
    ("DELETE", "/rm/mesures/{m}"),
    ("PATCH", "/reglages"),
    ("DELETE", "/seances/{s}"),
]
PAGES = ["/historique", "/progression", "/progression/{e}", "/reglages"]
FRAGMENTS = ["/rm/{e}", "/seances/{s}/suppression", "/historique?avant={s}"]
ID_ROUTES = [
    ("GET", "/progression/{}"),
    ("GET", "/api/progression/{}"),
    ("GET", "/rm/{}"),
    ("POST", "/rm/{}"),
    ("DELETE", "/rm/mesures/{}"),
    ("GET", "/seances/{}/suppression"),
    ("DELETE", "/seances/{}"),
]


def make(engine: Engine, name: str = "Squat", category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def logged(
    engine: Engine,
    when: datetime,
    exercise_id: int | None,
    items: list[dict[str, str]],
    *,
    tz: ZoneInfo | None = None,
    close: bool = True,
    user: int = USER,
) -> int:
    session_id = sessions.start(engine, user, None, "gym", when, tz or UTC)
    if exercise_id is not None:
        block = sessions.pick(engine, user, session_id, None, exercise_id).block
        assert block is not None
        for number, values in enumerate(items, start=1):
            values = dict(values)
            kind = values.pop("type", "work")
            sessions.confirm_set(
                engine, user, session_id, block.id, kind, values, when + timedelta(minutes=number)
            )
    if close:
        sessions.close(engine, user, session_id, when + timedelta(hours=1))
    return session_id


def lift(reps: int, kg: str, kind: str = "work") -> dict[str, str]:
    return {"reps": str(reps), "weight": kg, "type": kind}


def ids_of(engine: Engine) -> dict[str, int]:
    """A strength exercise with a closed session and a manual RM entry."""
    squat = make(engine)
    session_id = logged(engine, NOW - timedelta(days=1), squat, [lift(5, "100")])
    saved = progress.add_measured_rm(
        engine, USER, squat, "1", "120", "2026-11-01", now=NOW, today="2026-11-03"
    )
    return {"e": squat, "s": session_id, "m": saved.view.measures[0].measured_id}


def body_for(path: str) -> dict[str, str]:
    if path == "/rm/{e}":
        return {"n": "1", "weight": "130", "date": "2026-11-02"}
    if path == "/reglages":
        return {"rm_formula": "brzycki"}
    return {}


def facts(engine: Engine) -> tuple[object, ...]:
    """Everything an L5 write could change."""
    with engine.begin() as connection:
        return tuple(
            tuple(tuple(row) for row in connection.execute(sa.select(table)))
            for table in (s.session, s.set_entry, s.rm_measured, s.app_setting)
        )


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html, re.S)
    assert match is not None, html
    return match.group(1)


# --- security on every route


def test_the_lists_cover_every_l5_route() -> None:
    found = {
        (method, route.path)
        for router in (history_routes.router, progress_routes.router)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    names = {"{e}": "{exercise_id}", "{m}": "{measured_id}", "{s}": "{session_id}"}

    def real(path: str) -> str:
        for short, long in names.items():
            path = path.replace(short, long)
        return path.split("?")[0]

    listed = {(method, real(path)) for method, path in ACTIONS}
    listed |= {("GET", real(path)) for path in PAGES + FRAGMENTS}
    listed |= {("GET", "/api/progression/{exercise_id}")}
    assert found == listed


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_form_encoded_body_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = ids_of(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, path.format(**ids), data=body_for(path), headers=HTMX)
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
@pytest.mark.parametrize("foreign", FOREIGN)
def test_cross_origin_action_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str, foreign: dict[str, str]
) -> None:
    ids = ids_of(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, path.format(**ids), json=body_for(path), headers={**HTMX, **foreign})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_unpaired_action_is_sent_to_pairing_and_changes_nothing(
    unpaired_client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = ids_of(migrated_engine)
    before = facts(migrated_engine)
    response = unpaired_client.request(method, path.format(**ids), json=body_for(path), headers=HTMX)
    assert response.status_code == 401 and response.headers["hx-redirect"] == "/appairage"
    assert facts(migrated_engine) == before


@pytest.mark.parametrize("path", PAGES)
def test_unpaired_navigation_goes_to_pairing(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = ids_of(migrated_engine)
    response = unpaired_client.get(path.format(**ids), headers=PAGE, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/appairage"


@pytest.mark.parametrize("path", FRAGMENTS)
def test_unpaired_fragment_is_refused(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = ids_of(migrated_engine)
    response = unpaired_client.get(path.format(**ids), headers=HTMX, follow_redirects=False)
    assert response.status_code == 401 and response.headers["hx-redirect"] == "/appairage"


def test_unpaired_chart_json_leaks_nothing(unpaired_client: TestClient, migrated_engine: Engine) -> None:
    ids = ids_of(migrated_engine)
    response = unpaired_client.get(f"/api/progression/{ids['e']}", follow_redirects=False)
    assert response.status_code in (303, 401)
    assert "series" not in response.text and "labels" not in response.text


@pytest.mark.parametrize("foreign", FOREIGN)
def test_chart_json_refuses_a_foreign_origin(
    client: TestClient, migrated_engine: Engine, foreign: dict[str, str]
) -> None:
    ids = ids_of(migrated_engine)
    response = client.get(f"/api/progression/{ids['e']}", headers=foreign)
    assert response.status_code == 403 and "series" not in response.text


@pytest.mark.parametrize(("method", "path"), ID_ROUTES)
def test_a_path_id_beyond_the_range_is_404(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids_of(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, path.format(HUGE), json=None if method == "GET" else {}, headers=HTMX)
    assert response.status_code == 404
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ID_ROUTES)
def test_a_non_integer_path_id_is_422(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path.format("abc"), json=None if method == "GET" else {}, headers=HTMX)
    assert response.status_code == 422


@pytest.mark.parametrize(("method", "path"), ID_ROUTES)
def test_another_users_ids_are_404_and_change_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    theirs = make(migrated_engine, "Theirs", user=OTHER)
    session_id = logged(migrated_engine, NOW - timedelta(days=1), theirs, [lift(5, "100")], user=OTHER)
    saved = progress.add_measured_rm(
        migrated_engine, OTHER, theirs, "1", "120", "2026-11-01", now=NOW, today="2026-11-03"
    )
    target = {"/rm/mesures/{}": saved.view.measures[0].measured_id}.get(path)
    if target is None:
        target = session_id if "seances" in path else theirs
    before = facts(migrated_engine)
    body = None if method == "GET" else body_for("/rm/{e}" if method == "POST" else "")
    response = client.request(method, path.format(target), json=body, headers=HTMX)
    assert response.status_code == 404
    assert facts(migrated_engine) == before


def test_history_with_a_huge_or_foreign_anchor(client: TestClient, migrated_engine: Engine) -> None:
    ids_of(migrated_engine)
    assert client.get(f"/historique?avant={HUGE}", headers=HTMX).status_code == 404
    theirs = logged(migrated_engine, NOW - timedelta(days=2), None, [], user=OTHER)
    fragment = client.get(f"/historique?avant={theirs}", headers=HTMX)
    assert fragment.status_code == 200 and "/seances/" not in fragment.text  # no page after a foreign anchor
    unknown = client.get("/historique?avant=987654", headers=HTMX)
    assert unknown.status_code == 200 and "/seances/" not in unknown.text


def test_history_anchor_with_a_superscript_digit_is_422(client: TestClient) -> None:
    assert client.get("/historique?avant=²", headers=HTMX).status_code == 422


def test_rm_entry_with_a_superscript_digit_is_refused(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    response = client.post(
        f"/rm/{squat}", json={"n": "²", "weight": "100", "date": "2026-11-01"}, headers=HTMX
    )
    assert response.status_code == 200 and TEXT("catalog.error.rm_reps_range") in response.text


@pytest.mark.parametrize(
    "path", ["/variables/nouvelle?exercice=²", "/exercices/{e}?ajout=²", "/seances/{s}?exercice=²"]
)
def test_superscript_digit_query_ids_are_ignored(
    client: TestClient, migrated_engine: Engine, path: str
) -> None:
    squat = make(migrated_engine)
    session_id = logged(migrated_engine, NOW - timedelta(hours=1), squat, [], close=False)
    assert client.get(path.format(e=squat, s=session_id), headers=PAGE).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"n": "1" * 201, "weight": "100", "date": "2026-11-01"},
        {"n": ["1"], "weight": "100", "date": "2026-11-01"},
        {"rm_formula": {"key": "epley"}},
    ],
)
def test_malformed_json_bodies_are_422_and_change_nothing(
    client: TestClient, migrated_engine: Engine, body: dict[str, object]
) -> None:
    squat = make(migrated_engine)
    before = facts(migrated_engine)
    path = "/reglages" if "rm_formula" in body else f"/rm/{squat}"
    method = "PATCH" if "rm_formula" in body else "POST"
    assert client.request(method, path, json=body, headers=HTMX).status_code == 422
    assert facts(migrated_engine) == before


# --- history: pages, anchors, day boundaries


def test_exactly_twenty_sessions_have_no_older_page(client: TestClient, migrated_engine: Engine) -> None:
    for day in range(20):
        logged(migrated_engine, NOW - timedelta(days=day + 1), None, [])
    html = client.get("/historique", headers=PAGE).text
    assert html.count('href="/seances/') == 20 and TEXT("history.more") not in html
    logged(migrated_engine, NOW - timedelta(days=30), None, [])
    html = client.get("/historique", headers=PAGE).text
    assert html.count('href="/seances/') == 20 and TEXT("history.more") in html


def test_a_page_starting_a_new_month_repeats_no_heading_only_when_it_continues(
    client: TestClient, migrated_engine: Engine
) -> None:
    # 20 sessions in November (1 to 3 Nov, several a day), then 2 in October
    starts = [datetime(2026, 11, 1, 6, tzinfo=UTC) + timedelta(hours=3 * i) for i in range(20)]
    for when in starts:
        logged(migrated_engine, when, None, [])
    october = [logged(migrated_engine, datetime(2026, 10, day, 9, tzinfo=UTC), None, []) for day in (20, 10)]
    first = history.history_page(migrated_engine, USER)
    assert [g.key for g in first.months] == ["2026-11"] and first.next_before is not None
    second = history.history_page(migrated_engine, USER, first.next_before)
    assert not second.continues_month and [g.key for g in second.months] == ["2026-10"]
    fragment = client.get(f"/historique?avant={first.next_before}", headers=HTMX).text
    assert ">octobre 2026</h2>" in fragment
    assert [int(found) for found in re.findall(r'href="/seances/(\d+)"', fragment)] == october
    assert announced(fragment) == TEXT("history.loaded", count=2)


def test_a_deleted_anchor_keeps_the_next_page_stable(client: TestClient, migrated_engine: Engine) -> None:
    ids = [logged(migrated_engine, NOW - timedelta(days=30 - i), None, []) for i in range(23)]
    first = history.history_page(migrated_engine, USER)
    assert first.next_before == ids[3]
    client.request("DELETE", f"/seances/{ids[3]}", json={}, headers=HTMX)
    client.request("DELETE", f"/seances/{ids[22]}", json={}, headers=HTMX)  # one already seen
    second = history.history_page(migrated_engine, USER, first.next_before)
    assert [item.id for g in second.months for item in g.items] == [ids[2], ids[1], ids[0]]
    fragment = client.get(f"/historique?avant={ids[3]}", headers=HTMX).text
    assert [int(x) for x in re.findall(r'href="/seances/(\d+)"', fragment)] == [ids[2], ids[1], ids[0]]


def test_sessions_with_the_same_start_page_by_id(migrated_engine: Engine) -> None:
    when = NOW - timedelta(days=3)
    ids = []
    for _ in range(22):
        session_id = logged(migrated_engine, when, None, [])
        ids.append(session_id)
    first = history.history_page(migrated_engine, USER)
    second = history.history_page(migrated_engine, USER, first.next_before)
    seen = [item.id for page in (first, second) for g in page.months for item in g.items]
    assert seen == sorted(ids, reverse=True)


def test_local_date_at_day_and_month_boundaries(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    # 31 Oct 23:30 UTC is 1 Nov 00:30 in Paris: November, in the week of 26 Oct
    late = logged(
        migrated_engine, datetime(2026, 10, 31, 23, 30, tzinfo=UTC), squat, [lift(5, "100")], tz=PARIS
    )
    # Sunday 1 Nov 23:30 UTC is Monday 2 Nov 00:30 in Paris: the current week
    monday = logged(
        migrated_engine, datetime(2026, 11, 1, 23, 30, tzinfo=UTC), squat, [lift(5, "105")], tz=PARIS
    )
    with migrated_engine.begin() as connection:
        dates = dict(
            connection.execute(
                sa.select(s.session.c.id, s.session.c.local_date).where(s.session.c.id.in_([late, monday]))
            ).all()
        )
    assert dates == {late: "2026-11-01", monday: "2026-11-02"}
    page = history.history_page(migrated_engine, USER)
    assert [g.key for g in page.months] == ["2026-11"] and page.count == 2
    found = history.consistency(migrated_engine, USER, "2026-11-03")
    assert found.weeks[-1].count == 1 and found.weeks[-2].count == 1
    html = client.get("/historique", headers=PAGE).text
    assert ">octobre 2026</h2>" not in html and ">novembre 2026</h2>" in html
    assert TEXT("history.item_when", weekday="dim.", date="01/11", time="00:30") in html
    assert client.get(f"/api/progression/{squat}").json()["labels"] == ["01/11", "02/11"]


def test_consistency_across_the_new_year(migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    for when in (datetime(2026, 12, 29, 9, tzinfo=UTC), datetime(2027, 1, 2, 9, tzinfo=UTC)):
        logged(migrated_engine, when, squat, [lift(5, "100")])
    logged(migrated_engine, datetime(2026, 12, 31, 9, tzinfo=UTC), None, [])  # no live set: not counted
    found = history.consistency(migrated_engine, USER, "2027-01-03")
    assert found.weeks[-1].start == "2026-12-28" and found.weeks[-1].count == 2
    page = history.history_page(migrated_engine, USER)
    assert [g.key for g in page.months] == ["2027-01", "2026-12"]


def test_seven_and_more_sessions_a_week_use_the_last_bar(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    for hour in range(9):
        logged(migrated_engine, datetime(2026, 11, 2, 6 + hour, tzinfo=UTC), squat, [lift(5, "100")])
    html = client.get("/historique", headers=PAGE).text
    assert (
        "week-chart__bar--7" in html and "week-chart__bar--8" not in html and "week-chart__bar--9" not in html
    )
    assert TEXT("history.this_week", count=9) in html


# --- closed-session writes (D-067)


@pytest.fixture
def closed(migrated_engine: Engine) -> dict[str, int]:
    squat, bench = make(migrated_engine), make(migrated_engine, "Bench")
    session_id = logged(migrated_engine, NOW - timedelta(days=1), squat, [lift(5, "100")])
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SummaryView)
    return {"s": session_id, "r": found.rows[0].id, "t": found.rows[0].sets[0].id, "e": squat, "b": bench}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/seances/{s}/exercices", {"exercise_id": "{b}"}),
        ("PATCH", "/seances/{s}/exercices/{r}", {"exercise_id": "{b}"}),
        (
            "POST",
            "/seances/{s}/series",
            {"session_exercise_id": "{r}", "type": "work", "reps": "5", "weight": "1"},
        ),
    ],
)
def test_other_writes_on_a_closed_session_redirect_and_change_nothing(
    client: TestClient,
    migrated_engine: Engine,
    closed: dict[str, int],
    method: str,
    path: str,
    body: dict[str, str],
) -> None:
    before = facts(migrated_engine)
    filled = {key: value.format(**closed) for key, value in body.items()}
    response = client.request(method, path.format(**closed), json=filled, headers=HTMX)
    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == f"/seances/{closed['s']}?terminee=1"
    assert facts(migrated_engine) == before


def test_closing_a_closed_session_again_changes_nothing(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    before = facts(migrated_engine)
    response = client.post(f"/seances/{closed['s']}/cloture", json={}, headers=HTMX)
    assert response.status_code == 204 and response.headers["HX-Redirect"] == f"/seances/{closed['s']}"
    assert facts(migrated_engine) == before


def test_corrections_of_a_deleted_closed_session_are_404(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    sessions.delete_session(migrated_engine, USER, closed["s"], NOW)
    before = facts(migrated_engine)
    body = {"type": "work", "reps": "5", "weight": "120"}
    assert client.patch(f"/series/{closed['t']}", json=body, headers=HTMX).status_code == 404
    assert client.request("DELETE", f"/series/{closed['t']}", json={}, headers=HTMX).status_code == 404
    path = f"/seances/{closed['s']}/exercices/{closed['r']}/reglages"
    assert client.patch(path, json={}, headers=HTMX).status_code == 404
    assert facts(migrated_engine) == before


def test_a_correction_cannot_empty_a_set_or_change_its_exercise(
    client: TestClient, migrated_engine: Engine, closed: dict[str, int]
) -> None:
    before = facts(migrated_engine)
    refused = client.patch(
        f"/series/{closed['t']}", json={"type": "work", "reps": "", "weight": ""}, headers=HTMX
    )
    assert refused.status_code == 200 and 'aria-invalid="true"' in refused.text
    assert (
        client.patch(
            f"/series/{closed['t']}", json={"type": "dropset", "reps": "5", "weight": "100"}, headers=HTMX
        ).status_code
        == 200
    )
    assert facts(migrated_engine) == before


# --- chart JSON per category


def chart(client: TestClient, exercise_id: int) -> dict[str, object]:
    response = client.get(f"/api/progression/{exercise_id}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    data: dict[str, object] = response.json()
    assert set(data) == {"unit", "axis", "tooltip", "labels", "series"}
    labels = data["labels"]
    assert isinstance(labels, list)
    for item in data["series"]:  # type: ignore[attr-defined]
        assert set(item) == {"label", "kind", "values"} and item["kind"] in ("line", "points")
        assert len(item["values"]) == len(labels)
    return data


def test_chart_json_empty_shapes(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=1), squat, [lift(5, "60", "warmup")])
    assert chart(client, squat) == {"unit": "", "axis": "", "tooltip": "", "labels": [], "series": []}
    run = make(migrated_engine, "Run", "cardio")
    assert chart(client, run)["series"] == []


def test_chart_json_one_day(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=1), squat, [lift(3, "100"), lift(5, "100")])
    logged(migrated_engine, NOW - timedelta(hours=20), squat, [lift(1, "120")])  # same local day
    data = chart(client, squat)
    assert data["labels"] == ["02/11"]
    assert data["series"] == [{"label": "1RM estimé (Epley)", "kind": "line", "values": [120.0]}]


def test_chart_json_cardio_without_distance_is_minutes(client: TestClient, migrated_engine: Engine) -> None:
    run = make(migrated_engine, "Run", "cardio")
    logged(migrated_engine, NOW - timedelta(days=3), run, [{"duration": "30:00"}])
    logged(migrated_engine, NOW - timedelta(days=1), run, [{"duration": "20:00"}, {"duration": "25:30"}])
    data = chart(client, run)
    assert data["axis"] == TEXT("progress.axis.minutes") and data["labels"] == ["31/10", "02/11"]
    assert data["series"] == [
        {"label": TEXT("progress.series.duration"), "kind": "line", "values": [30.0, 45.5]}
    ]
    page = client.get(f"/progression/{run}", headers=PAGE).text
    assert TEXT("progress.record.best_pace") not in page and TEXT("progress.record.best_speed") not in page


def test_chart_json_cardio_distance_on_some_days(client: TestClient, migrated_engine: Engine) -> None:
    run = make(migrated_engine, "Run", "cardio")
    logged(migrated_engine, NOW - timedelta(days=3), run, [{"duration": "30:00"}])
    logged(migrated_engine, NOW - timedelta(days=1), run, [{"duration": "25:00", "distance": "5,5"}])
    data = chart(client, run)
    assert data["axis"] == TEXT("progress.axis.distance") and data["unit"] == "km"
    assert data["labels"] == ["02/11"] and data["series"][0]["values"] == [5.5]  # type: ignore[index]


def test_chart_json_intervals_rounds(client: TestClient, migrated_engine: Engine) -> None:
    tabata = make(migrated_engine, "Tabata", "intervals")
    logged(
        migrated_engine,
        NOW - timedelta(days=2),
        tabata,
        [{"duration": "0:20", "type": "warmup"}] + [{"duration": "0:20"}] * 8,
    )
    logged(migrated_engine, NOW - timedelta(days=1), tabata, [{"duration": "0:20"}] * 6)
    data = chart(client, tabata)
    assert data["axis"] == TEXT("progress.axis.rounds")
    assert data["series"] == [{"label": TEXT("progress.series.rounds"), "kind": "line", "values": [8.0, 6.0]}]
    page = client.get(f"/progression/{tabata}", headers=PAGE).text
    assert TEXT("progress.record.session_rounds") in page and TEXT("progress.record.session_work") in page
    assert 'id="rm"' not in page


def test_chart_json_bodyweight_with_added_load(client: TestClient, migrated_engine: Engine) -> None:
    dips = make(migrated_engine, "Dips", "bodyweight")
    exercises.add_field(migrated_engine, USER, dips, core_quantity="weight")
    logged(migrated_engine, NOW - timedelta(days=2), dips, [{"reps": "12"}])
    logged(migrated_engine, NOW - timedelta(days=1), dips, [{"reps": "6", "weight": "10"}])
    data = chart(client, dips)
    assert data["series"] == [
        {"label": TEXT("progress.series.max_reps"), "kind": "line", "values": [12.0, 6.0]}
    ]
    page = client.get(f"/progression/{dips}", headers=PAGE).text
    assert TEXT("progress.record.max_added_load") in page and f"10{NBSP}kg" in page


def test_chart_json_kettlebell_aligns_loads_with_nulls(client: TestClient, migrated_engine: Engine) -> None:
    swing = make(migrated_engine, "Swing", "kettlebell")
    logged(migrated_engine, NOW - timedelta(days=3), swing, [lift(15, "16")])
    logged(migrated_engine, NOW - timedelta(days=2), swing, [lift(10, "24")])
    logged(migrated_engine, NOW - timedelta(days=1), swing, [lift(20, "16"), lift(12, "24")])
    data = chart(client, swing)
    assert data["series"] == [
        {"label": f"16{NBSP}kg", "kind": "line", "values": [15.0, None, 20.0]},
        {"label": f"24{NBSP}kg", "kind": "line", "values": [None, 10.0, 12.0]},
    ]


def test_archived_exercise_keeps_its_progress(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=2), squat, [lift(5, "100")])
    logged(migrated_engine, NOW - timedelta(days=1), squat, [lift(5, "105")])
    exercises.set_archived(migrated_engine, USER, squat, NOW)
    assert_secure_page(client.get(f"/progression/{squat}", headers=PAGE), 200)
    assert len(chart(client, squat)["labels"]) == 2  # type: ignore[arg-type]
    assert f'href="/progression/{squat}"' in client.get("/progression", headers=PAGE).text


def test_data_table_fallback_holds_every_day(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    for day in (3, 2, 1):
        logged(migrated_engine, NOW - timedelta(days=day), squat, [lift(5, str(90 + day))])
    html = client.get(f"/progression/{squat}", headers=PAGE).text
    table = html[html.index(TEXT("progress.data_toggle")) :]
    table = table[: table.index("</table>")]
    assert "<details" in html[: html.index(TEXT("progress.data_toggle"))]
    rows = re.findall(r"<tr>", table)
    assert len(rows) == 1 + 3  # header and one row per day, newest first
    assert table.index("02/11/2026") < table.index("31/10/2026")
    assert TEXT("progress.chart_error") in html  # the fallback text is server-rendered (hidden)


# --- RM entry edges


def test_rm_entry_on_an_exercise_without_history_and_today(
    client: TestClient, migrated_engine: Engine
) -> None:
    squat = make(migrated_engine)
    saved = client.post(f"/rm/{squat}", json={"n": "12", "weight": "60", "date": "2026-11-03"}, headers=HTMX)
    assert saved.status_code == 200 and announced(saved.text) == TEXT("rm.saved", n=12, value=f"60{NBSP}kg")
    assert TEXT("rm.origin.manual", date="03/11/2026") in saved.text
    assert chart(client, squat)["series"] == []  # a 12RM is not a 1RM point
    future = client.post(f"/rm/{squat}", json={"n": "1", "weight": "60", "date": "2026-11-04"}, headers=HTMX)
    assert TEXT("catalog.error.date_in_future") in future.text


def test_rm_entry_today_follows_the_configured_zone(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    html = client.get(f"/rm/{squat}", headers=HTMX).text
    assert 'value="2026-11-03"' in html and 'max="2026-11-03"' in html


def test_deleting_a_measured_rm_twice_or_after_its_exercise_is_archived(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = ids_of(migrated_engine)
    exercises.set_archived(migrated_engine, USER, ids["e"], NOW)
    deleted = client.request("DELETE", f"/rm/mesures/{ids['m']}", json={}, headers=HTMX)
    assert deleted.status_code == 200 and announced(deleted.text) == TEXT("rm.deleted")
    assert client.request("DELETE", f"/rm/mesures/{ids['m']}", json={}, headers=HTMX).status_code == 404
    with migrated_engine.begin() as connection:
        assert connection.execute(sa.select(s.rm_measured.c.deleted_at)).scalar_one() is not None


# --- chart assets


def test_vendored_chart_js_injects_no_style_element() -> None:
    text = (STATIC / "vendor" / "chart.umd.min.js").read_text(encoding="utf-8")
    assert not re.search(r"createElement\(\s*[\"'`]style[\"'`]\s*\)", text)
    assert "insertRule" not in text and "adoptedStyleSheets" not in text
    assert "http://" not in text.replace("http://www.w3.org", "")  # no external resource fetched


def test_chart_script_has_no_french_no_html_injection_and_no_style_element() -> None:
    text = (STATIC / "js" / "progress-chart.js").read_text(encoding="utf-8")
    assert not re.search("[àâçéèêëîïôûùüœæ«»]", text, re.I)  # no French text
    assert "innerHTML" not in text and "createElement" not in text and "eval(" not in text
    assert "fetch(" in text and "http" not in text
    assert "animation: false" in text
