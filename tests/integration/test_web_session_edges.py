"""Every L4 route against the security rules (JSON only, same origin, paired device, ids beyond
the integer range, unknown ids), and edge states of the session pages: steppers at their bounds
and with discrete values, buttons disabled during their request, resume from another device,
local times at midnight and across a daylight-saving change (D-034, D-049, D-053, D-061 to D-065)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx
import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.services import devices, exercises, seed, sessions, templates
from rack_overflow.services.exercises import ExerciseForm, FieldForm
from rack_overflow.services.sessions import SessionView
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG, create_app
from rack_overflow.web.auth import COOKIE_NAME
from rack_overflow.web.display import Display
from rack_overflow.web.forms import MAX_ID
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.routes import home as home_routes
from rack_overflow.web.routes import sessions as session_routes

CATALOG_TEXTS = load_catalog(CATALOG)
TEXT = CATALOG_TEXTS.text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
HUGE = str(MAX_ID + 1)
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
FOREIGN = [{"origin": "http://evil.example"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}]

# every non-GET route of L4, ids filled in by `ids_of`
ACTIONS = [
    ("POST", "/seances"),
    ("POST", "/seances/{s}/exercices"),
    ("PATCH", "/seances/{s}/exercices/{r}"),
    ("PATCH", "/seances/{s}/exercices/{r}/reglages"),
    ("POST", "/seances/{s}/series"),
    ("PATCH", "/series/{t}"),
    ("DELETE", "/series/{t}"),
    ("POST", "/seances/{s}/cloture"),
]
PAGES = ["/", "/seances/{s}"]
FRAGMENTS = [
    "/seances/{s}/recherche?q=",
    "/seances/{s}/exercices/{r}/serie?pas=reps:up",
    "/seances/{s}/cloture",
]


def pair_device(engine: Engine, name: str = "test") -> str:
    """A device paired through the service; its token (the cookie value)."""
    token = devices.pair(engine, devices.add_device(engine, name, NOW).code, NOW).token
    assert token is not None
    return token


@pytest.fixture
def seeded(migrated_engine: Engine) -> Engine:
    seed.seed_catalog(migrated_engine, USER)
    return migrated_engine


def open_session(engine: Engine) -> dict[str, int]:
    """An open free session with one squat row and one confirmed set."""
    squat = exercises.create(engine, USER, ExerciseForm("Squat", "strength", "gym"))
    session_id = sessions.start(engine, USER, None, "gym", NOW, UTC)
    found = sessions.pick(engine, USER, session_id, None, squat).block
    assert found is not None
    done = sessions.confirm_set(
        engine, USER, session_id, found.id, "work", {"reps": "5", "weight": "100"}, NOW
    )
    return {"s": session_id, "r": found.id, "t": done.set.id, "e": squat}


def facts(engine: Engine) -> tuple[object, ...]:
    """Everything a session write could change."""
    with engine.begin() as connection:
        return tuple(
            tuple(tuple(row) for row in connection.execute(sa.select(table).order_by(table.c.id)))
            for table in (s.session, s.session_exercise, s.set_entry, s.set_value, s.exercise_setting)
        )


def fill(path: str, ids: dict[str, int]) -> str:
    return path.format(**ids)


def body_for(path: str, ids: dict[str, int]) -> dict[str, str]:
    if path == "/seances/{s}/series":
        return {"session_exercise_id": str(ids["r"]), "type": "work", "reps": "5", "weight": "100"}
    if path == "/series/{t}":
        return {"type": "work", "reps": "6", "weight": "100"}
    if path.startswith("/seances/{s}/exercices"):
        return {"exercise_id": str(ids["e"])}
    if path == "/seances":
        return {"template_id": "", "location": "gym"}
    return {}


# --- security on every route


def test_the_list_covers_every_session_action() -> None:
    found = {
        (method, route.path)
        for router in (session_routes.router, home_routes.router)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "GET"
    }
    listed = {
        (method, path.replace("{s}", "{session_id}").replace("{r}", "{row_id}").replace("{t}", "{set_id}"))
        for method, path in ACTIONS
    }
    assert found == listed


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_form_encoded_body_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = open_session(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, fill(path, ids), data=body_for(path, ids), headers=HTMX)
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
@pytest.mark.parametrize("foreign", FOREIGN)
def test_cross_origin_action_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str, foreign: dict[str, str]
) -> None:
    ids = open_session(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, fill(path, ids), json=body_for(path, ids), headers={**HTMX, **foreign})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_unpaired_action_is_sent_to_pairing_and_changes_nothing(
    unpaired_client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = open_session(migrated_engine)
    before = facts(migrated_engine)
    response = unpaired_client.request(method, fill(path, ids), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/appairage"
    assert facts(migrated_engine) == before


@pytest.mark.parametrize("path", PAGES)
def test_unpaired_navigation_goes_to_pairing(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = open_session(migrated_engine)
    response = unpaired_client.get(fill(path, ids), headers=PAGE, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/appairage"


@pytest.mark.parametrize("path", FRAGMENTS)
def test_unpaired_fragment_is_refused(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = open_session(migrated_engine)
    response = unpaired_client.get(fill(path, ids), headers=HTMX, follow_redirects=False)
    assert response.status_code == 401 and response.headers["hx-redirect"] == "/appairage"


def _id_routes() -> list[tuple[str, str, str]]:
    """(method, path, id name) for each id of each session route path."""
    found = []
    for route in session_routes.router.routes:
        assert isinstance(route, APIRoute)
        for which in ("session_id", "row_id", "set_id"):
            if "{" + which + "}" in route.path:
                found.extend((method, route.path, which) for method in sorted(route.methods))
    return found


ID_ROUTES = _id_routes()


def test_the_id_routes_are_found() -> None:
    assert len(ID_ROUTES) == 14  # 11 routes with an id, 3 of them with two


@pytest.mark.parametrize(("method", "path", "which"), ID_ROUTES)
def test_a_path_id_beyond_the_range_is_404(
    client: TestClient, migrated_engine: Engine, method: str, path: str, which: str
) -> None:
    ids = open_session(migrated_engine)
    real = {"session_id": ids["s"], "row_id": ids["r"], "set_id": ids["t"]}
    url = path.format(**{**real, which: HUGE})
    before = facts(migrated_engine)
    response = client.request(method, url, json=None if method == "GET" else {}, headers=HTMX)
    assert response.status_code == 404
    assert facts(migrated_engine) == before


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/seances", {"template_id": HUGE, "location": "gym"}),
        ("/seances/{s}/exercices", {"exercise_id": HUGE}),
        ("/seances/{s}/exercices", {"slot_id": HUGE, "exercise_id": "1"}),
        ("/seances/{s}/series", {"session_exercise_id": HUGE, "type": "work", "reps": "5"}),
    ],
)
def test_a_body_id_beyond_the_range_is_404(
    client: TestClient, migrated_engine: Engine, path: str, body: dict[str, str]
) -> None:
    ids = open_session(migrated_engine)
    if path == "/seances":
        sessions.close(migrated_engine, USER, ids["s"], NOW)
    before = facts(migrated_engine)
    response = client.post(fill(path, ids), json=body, headers=HTMX)
    assert response.status_code == 404
    assert facts(migrated_engine) == before


def test_change_with_a_body_id_beyond_the_range_is_404(client: TestClient, migrated_engine: Engine) -> None:
    ids = open_session(migrated_engine)
    response = client.patch(fill("/seances/{s}/exercices/{r}", ids), json={"exercise_id": HUGE}, headers=HTMX)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PATCH", "/seances/{s}/exercices/999", {"exercise_id": "1"}),
        ("PATCH", "/seances/{s}/exercices/999/reglages", {}),
        ("GET", "/seances/{s}/exercices/999/serie?pas=reps:up", None),
        ("POST", "/seances/{s}/series", {"session_exercise_id": "999", "type": "work", "reps": "1"}),
        ("PATCH", "/series/999", {"type": "work", "reps": "1"}),
        ("DELETE", "/series/999", {}),
        ("POST", "/seances/999/exercices", {"exercise_id": "1"}),
        ("POST", "/seances/999/cloture", {}),
        ("GET", "/seances/999/cloture", None),
        ("GET", "/seances/999/recherche?q=", None),
    ],
)
def test_unknown_ids_are_a_json_404_for_htmx(
    client: TestClient, migrated_engine: Engine, method: str, path: str, body: dict[str, str] | None
) -> None:
    ids = open_session(migrated_engine)
    before = facts(migrated_engine)
    response = client.request(method, fill(path, ids), json=body, headers=HTMX)
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert facts(migrated_engine) == before


def test_another_users_set_and_rows_are_404(client: TestClient, migrated_engine: Engine) -> None:
    theirs = exercises.create(migrated_engine, OTHER, ExerciseForm("Squat", "strength", "gym"))
    session_id = sessions.start(migrated_engine, OTHER, None, "gym", NOW, UTC)
    row = sessions.pick(migrated_engine, OTHER, session_id, None, theirs).block
    assert row is not None
    done = sessions.confirm_set(
        migrated_engine, OTHER, session_id, row.id, "work", {"reps": "5", "weight": "1"}, NOW
    )
    before = facts(migrated_engine)
    assert (
        client.patch(f"/series/{done.set.id}", json={"type": "work", "reps": "1"}, headers=HTMX).status_code
        == 404
    )
    assert client.request("DELETE", f"/series/{done.set.id}", json={}, headers=HTMX).status_code == 404
    assert client.get(f"/seances/{session_id}/exercices/{row.id}/serie", headers=HTMX).status_code == 404
    mine = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    stolen = {"session_exercise_id": str(row.id), "type": "work", "reps": "5"}
    assert client.post(f"/seances/{mine}/series", json=stolen, headers=HTMX).status_code == 404
    taken = client.post(f"/seances/{mine}/exercices", json={"exercise_id": str(theirs)}, headers=HTMX)
    assert taken.status_code == 200 and TEXT("catalog.error.exercise_unavailable") in taken.text
    after = facts(migrated_engine)
    assert after[2:] == before[2:]  # no set, value or setting written


@pytest.mark.parametrize("value", [8, ["8"], {"x": "8"}, None, True])
def test_a_non_text_field_value_is_read_as_empty(
    client: TestClient, migrated_engine: Engine, value: object
) -> None:
    ids = open_session(migrated_engine)
    body = {"session_exercise_id": str(ids["r"]), "type": "work", "reps": value, "weight": "100"}
    response = client.post(fill("/seances/{s}/series", ids), json=body, headers=HTMX)
    assert response.status_code == 200
    assert TEXT("catalog.error.required") in response.text


@pytest.mark.parametrize("kind", [None, "", "rm", "warmup "])
def test_an_unknown_set_type_is_refused_in_place(
    client: TestClient, migrated_engine: Engine, kind: str | None
) -> None:
    ids = open_session(migrated_engine)
    before = facts(migrated_engine)
    body = {"session_exercise_id": str(ids["r"]), "type": kind, "reps": "5", "weight": "100"}
    response = client.post(fill("/seances/{s}/series", ids), json=body, headers=HTMX)
    assert (
        response.status_code == 200 and 'aria-invalid="true"' in response.text
    ) or "erreur" in response.text
    assert facts(migrated_engine) == before


def test_rm_test_is_refused_for_a_kettlebell(client: TestClient, migrated_engine: Engine) -> None:
    bell = exercises.create(migrated_engine, USER, ExerciseForm("Swing", "kettlebell", "gym"))
    session_id = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    row = sessions.pick(migrated_engine, USER, session_id, None, bell).block
    assert row is not None
    page = client.get(f"/seances/{session_id}", headers=PAGE).text
    assert 'value="rm_test"' not in page
    body = {"session_exercise_id": str(row.id), "type": "rm_test", "reps": "10", "weight": "16"}
    response = client.post(f"/seances/{session_id}/series", json=body, headers=HTMX)
    assert response.status_code == 200 and TEXT("catalog.error.invalid_choice") in response.text


# --- steppers (D-063)


def step(client: TestClient, ids: dict[str, int], **params: str) -> str:
    response = client.get(fill("/seances/{s}/exercices/{r}/serie", ids), params=params, headers=HTMX)
    assert response.status_code == 200
    return response.text


def value_of(html: str, row: int, name: str) -> str:
    match = re.search(rf'id="exercice-{row}-{name}" name="{name}"[^>]*value="([^"]*)"', html)
    assert match is not None, html
    return match.group(1)


def test_steppers_at_their_bounds(client: TestClient, migrated_engine: Engine) -> None:
    ids = open_session(migrated_engine)
    row = ids["r"]
    before = facts(migrated_engine)
    assert (
        value_of(step(client, ids, type="work", reps="", weight="", pas="weight:up"), row, "weight") == "2,5"
    )
    assert (
        value_of(step(client, ids, type="work", reps="", weight="", pas="weight:down"), row, "weight") == ""
    )
    zero = step(client, ids, type="work", reps="0", weight="0", pas="reps:down")
    assert value_of(zero, row, "reps") == "0"
    assert re.search(rf'id="exercice-{row}-reps-moins"[^>]*disabled', zero)
    assert re.search(rf'id="exercice-{row}-weight-moins"[^>]*disabled', zero)
    assert (
        value_of(step(client, ids, type="work", reps="1", weight="61", pas="weight:up"), row, "weight")
        == "62,5"
    )
    assert (
        value_of(step(client, ids, type="work", reps="1", weight="61", pas="weight:down"), row, "weight")
        == "60"
    )
    assert (
        value_of(step(client, ids, type="work", reps="1", weight="1", pas="weight:down"), row, "weight")
        == "0"
    )
    # unreadable value, unknown field or direction: the texts stay as typed
    for pas in ("weight:sideways", "nope:up", "weight", "", "type:up", "session_exercise_id:up"):
        html = step(client, ids, type="work", reps="1", weight="abc", pas=pas)
        assert value_of(html, row, "weight") == "abc"
    assert (
        value_of(step(client, ids, type="work", reps="7", weight="abc", pas="weight:up"), row, "weight")
        == "abc"
    )
    assert facts(migrated_engine) == before


def test_discrete_values_are_chips_without_stepper(client: TestClient, migrated_engine: Engine) -> None:
    bell = exercises.create(migrated_engine, USER, ExerciseForm("Swing", "kettlebell", "gym"))
    weight = next(
        f.id for f in exercises.get_detail(migrated_engine, USER, bell).fields if f.core_quantity == "weight"
    )
    exercises.update_field(
        migrated_engine, USER, bell, weight, FieldForm(required=True, discrete_values="16 20 24")
    )
    session_id = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    row = sessions.pick(migrated_engine, USER, session_id, None, bell).block
    assert row is not None
    ids = {"s": session_id, "r": row.id}
    html = step(client, ids, type="work", reps="10", weight="18", pas="weight:up")
    assert f'id="exercice-{row.id}-weight-plus"' not in html
    chips = re.findall(r'name="weight" value="([^"]*)"[^>]*?( checked)?>', html)
    assert chips == [("16", ""), ("20", ""), ("24", ""), ("18", " checked")]  # off the list: kept, checked
    response = client.post(
        f"/seances/{session_id}/series",
        json={"session_exercise_id": str(row.id), "type": "work", "reps": "10", "weight": "20"},
        headers=HTMX,
    )
    assert response.status_code == 200
    assert re.search(r'name="weight" value="20"[^>]*checked', response.text)  # next set prefilled


# --- every button disabled during its request (D-053)


class _Triggers(HTMLParser):
    """Each htmx write trigger (or close GET) with the `hx-disabled-elt` of itself or an ancestor
    and the ids of its ancestors."""

    VOID = frozenset({"input", "br", "img", "meta", "link", "hr", "source", "area", "base", "col", "wbr"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict[str, str | None]] = []
        self.found: list[tuple[str, str | None, list[dict[str, str | None]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        attributes["<tag>"] = tag
        chain = [*self.stack, attributes]
        for verb in ("hx-post", "hx-patch", "hx-delete", "hx-get"):
            url = attributes.get(verb)
            if url is None:
                continue
            disabled = next(
                (a.get("hx-disabled-elt") for a in reversed(chain) if a.get("hx-disabled-elt")), None
            )
            self.found.append((f"{verb} {url}", disabled, chain))
        if tag not in self.VOID:
            self.stack.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            if self.stack.pop()["<tag>"] == tag:
                break


def triggers(html: str) -> list[tuple[str, str | None, list[dict[str, str | None]]]]:
    parser = _Triggers()
    parser.feed(html)
    parser.close()
    return parser.found


def busy_page(client: TestClient, seeded: Engine) -> tuple[int, list[str]]:
    """A Salle A session with sets, a pending menu, the change block and the close confirmation."""
    salle = next(t.id for t in templates.list_templates(seeded, USER) if t.draft.name.startswith("Salle A"))
    started = client.post("/seances", json={"template_id": str(salle), "location": "gym"}, headers=HTMX)
    session_id = int(started.headers["HX-Redirect"].rsplit("/", 1)[1])
    found = sessions.show(seeded, USER, session_id)
    assert isinstance(found, SessionView) and found.block is not None
    row = found.block.id
    for _ in range(2):
        client.post(
            f"/seances/{session_id}/series",
            json={"session_exercise_id": str(row), "type": "work", "reps": "8", "weight": "60"},
            headers=HTMX,
        )
    menu = next(iter(found.menus))
    pages = [
        client.get(f"/seances/{session_id}", headers=PAGE).text,
        client.get(f"/seances/{session_id}?menu={menu}", headers=PAGE).text,
        client.get(f"/seances/{session_id}/cloture", headers=HTMX).text,
        client.get(f"/seances/{session_id}/recherche?q=squat", headers=HTMX).text,
    ]
    curl = next(e.id for e in exercises.list_exercises(seeded, USER) if e.draft.name == "Curl barre EZ")
    added = client.post(f"/seances/{session_id}/exercices", json={"exercise_id": str(curl)}, headers=HTMX)
    pages.append(added.text)
    picked = sessions.show(seeded, USER, session_id)
    assert isinstance(picked, SessionView) and picked.block is not None
    pages.append(client.get(f"/seances/{session_id}/recherche?q=&ligne={picked.block.id}", headers=HTMX).text)
    return session_id, pages


def test_every_write_disables_its_buttons_during_the_request(client: TestClient, seeded: Engine) -> None:
    _, pages = busy_page(client, seeded)
    home = client.get("/", headers=PAGE).text
    checked = 0
    for html in pages:
        for label, disabled, chain in triggers(html):
            verb = label.split(" ", 1)[0]
            if verb == "hx-get":
                continue  # navigation-like reads: steppers checked below, close checked apart
            if "reglages" in label:
                assert disabled is None  # settings: saved on change, nothing disabled (ui-spec)
                continue
            checked += 1
            assert disabled is not None, label
            if disabled.endswith(" button"):
                target = disabled.split(" ", 1)[0].lstrip("#")
                assert any(a.get("id") == target for a in chain), (label, disabled)
            else:
                assert disabled == "this", (label, disabled)
            assert "find " not in disabled, label  # htmx `find` takes the first match only
    assert checked > 20
    steppers = [t for html in pages for t in triggers(html) if "/serie" in t[0] and t[0].startswith("hx-get")]
    assert steppers and all(d is not None and d.endswith("-valider") for _, d, _ in steppers)
    assert [d for _, d, _ in triggers(home) if d] == []  # the open session: resume link only


def test_the_start_form_disables_every_start_button(client: TestClient, seeded: Engine) -> None:
    del seeded
    home = client.get("/", headers=PAGE).text
    found = triggers(home)
    assert found and all(disabled == "#demarrer button" for _, disabled, _ in found)
    assert home.count('name="template_id"') == 5  # four templates and « Séance libre »


def test_the_close_buttons_are_disabled_during_their_request(client: TestClient, seeded: Engine) -> None:
    _, pages = busy_page(client, seeded)
    close = [t for html in pages for t in triggers(html) if "/cloture" in t[0]]
    assert close and all(disabled is not None for _, disabled, _ in close), close


# --- resume, requested items


def test_resume_from_another_device_rebuilds_the_page(
    client: TestClient, unpaired_client: TestClient, seeded: Engine
) -> None:
    session_id, _ = busy_page(client, seeded)
    first = client.get(f"/seances/{session_id}", headers=PAGE).text
    # a new browser (the old one closed): another paired device, nothing kept client-side
    unpaired_client.cookies.clear()
    unpaired_client.cookies.set(COOKIE_NAME, pair_device(seeded, "phone"))
    home = unpaired_client.get("/", headers=PAGE).text
    assert TEXT("home.resume") in home and f'href="/seances/{session_id}"' in home
    again = unpaired_client.get(f"/seances/{session_id}", headers=PAGE).text
    assert again == first


def test_an_item_of_another_session_is_ignored(client: TestClient, migrated_engine: Engine) -> None:
    ids = open_session(migrated_engine)
    sessions.close(migrated_engine, USER, ids["s"], NOW)
    squat = ids["e"]
    session_id = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    row = sessions.pick(migrated_engine, USER, session_id, None, squat).block
    assert row is not None
    for query in (
        f"exercice={ids['r']}",
        f"menu={ids['r']}",
        f"exercice={HUGE}",
        "exercice=-1",
        "exercice=1e3",
    ):
        html = client.get(f"/seances/{session_id}?{query}", headers=PAGE).text
        assert f'id="exercice-{row.id}-valider"' in html, query
    change = client.get(f"/seances/{session_id}/recherche?q=&ligne={HUGE}", headers=HTMX)
    assert change.status_code == 200 and "hx-patch" not in change.text


# --- local times (D-065)


@pytest.fixture
def clocked(settings: Settings, migrated_engine: Engine) -> Iterator[tuple[TestClient, list[datetime]]]:
    """A paired client whose clock the test moves."""
    now = [NOW]
    app = create_app(settings, migrated_engine, clock=lambda: now[0], run_scheduler=False)
    with TestClient(app) as web:
        web.cookies.set(COOKIE_NAME, pair_device(migrated_engine))
        yield web, now


def summary_of(
    web: TestClient, now: list[datetime], start: datetime, minutes: list[int], end: datetime
) -> str:
    now[0] = start
    response = web.post("/seances", json={"template_id": "", "location": "gym"}, headers=HTMX)
    session_id = int(response.headers["HX-Redirect"].rsplit("/", 1)[1])
    squat = web.app.state.engine  # type: ignore[attr-defined]
    exercise_id = exercises.create(squat, USER, ExerciseForm(f"Squat {start:%H%M%d}", "strength", "gym"))
    web.post(f"/seances/{session_id}/exercices", json={"exercise_id": str(exercise_id)}, headers=HTMX)
    found = sessions.show(squat, USER, session_id)
    assert isinstance(found, SessionView) and found.block is not None
    for minute in minutes:
        now[0] = start + timedelta(minutes=minute)
        web.post(
            f"/seances/{session_id}/series",
            json={"session_exercise_id": str(found.block.id), "type": "work", "reps": "5", "weight": "100"},
            headers=HTMX,
        )
    now[0] = end
    web.post(f"/seances/{session_id}/cloture", json={}, headers=HTMX)
    return web.get(f"/seances/{session_id}", headers=PAGE).text.replace("\u00a0", " ")


def test_summary_of_a_session_over_midnight(clocked: tuple[TestClient, list[datetime]]) -> None:
    web, now = clocked
    start = datetime(2026, 11, 3, 22, 59, tzinfo=UTC)  # 23:59 in Brussels
    html = summary_of(web, now, start, [2], start + timedelta(minutes=10))
    duration = Display(CATALOG_TEXTS).duration_compact(600).replace("\u00a0", " ")
    assert f"03/11/2026 · 23:59\u201300:09 · {duration}" in html


def test_summary_across_the_autumn_clock_change(clocked: tuple[TestClient, list[datetime]]) -> None:
    web, now = clocked
    start = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST, clocks go back at 01:00 UTC
    html = summary_of(web, now, start, [5], datetime(2026, 10, 25, 1, 45, tzinfo=UTC))  # 02:45 CET
    duration = Display(CATALOG_TEXTS).duration_compact(4500).replace("\u00a0", " ")
    assert f"25/10/2026 · 02:30\u201302:45 · {duration}" in html


def test_home_shows_the_local_start_in_summer_time(clocked: tuple[TestClient, list[datetime]]) -> None:
    web, now = clocked
    now[0] = datetime(2026, 7, 1, 22, 1, tzinfo=UTC)  # 00:01 CEST, the next local day
    web.post("/seances", json={"template_id": "", "location": "home"}, headers=HTMX)
    home = web.get("/", headers=PAGE).text.replace("\u00a0", " ")
    assert "commencée à 00:01" in home


# --- the session closed between two service calls of one request (another device)


def closing_first(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, session_id: int, name: str, *, after: bool = False
) -> None:
    """Wrap the service `name` so the session is closed just before it runs (or just after)."""
    real = getattr(sessions, name)

    def wrapped(*args: object, **kwargs: object) -> object:
        if not after:
            sessions.close(engine, USER, session_id, NOW)
        try:
            return real(*args, **kwargs)
        finally:
            if after:
                sessions.close(engine, USER, session_id, NOW)

    monkeypatch.setattr(sessions, name, wrapped)


def assert_closed(response: httpx.Response, session_id: int) -> None:
    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == f"/seances/{session_id}?terminee=1"


def test_a_refused_set_on_a_session_closed_meanwhile_redirects(
    client: TestClient, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = open_session(migrated_engine)
    closing_first(monkeypatch, migrated_engine, ids["s"], "confirm_set", after=True)
    body = {"session_exercise_id": str(ids["r"]), "type": "work", "reps": "x", "weight": "100"}
    before = facts(migrated_engine)
    response = client.post(fill("/seances/{s}/series", ids), json=body, headers=HTMX)
    assert_closed(response, ids["s"])
    assert facts(migrated_engine)[2:] == before[2:]  # no set written, only the close


@pytest.mark.parametrize(("method", "name"), [("PATCH", "update_set"), ("DELETE", "delete_set")])
def test_a_set_change_on_a_session_closed_meanwhile_redirects(
    client: TestClient, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, method: str, name: str
) -> None:
    ids = open_session(migrated_engine)
    closing_first(monkeypatch, migrated_engine, ids["s"], name)
    before = facts(migrated_engine)
    body = body_for("/series/{t}", ids) if method == "PATCH" else {}
    response = client.request(method, fill("/series/{t}", ids), json=body, headers=HTMX)
    assert_closed(response, ids["s"])
    assert facts(migrated_engine)[1:] == before[1:]  # the set untouched, only the close
