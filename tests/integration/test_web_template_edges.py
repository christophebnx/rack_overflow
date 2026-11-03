"""Every L3 route against the security rules (JSON only, same origin, paired device), unknown,
foreign and soft-deleted ids, moves at the ends, D-050 refusals and D-053 focus on the new forms
and row actions (docs/ui-spec.md "L3 — Template detail"; D-034, D-049, D-058, D-059)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from request_status import triggers_without_slot
from sqlalchemy.engine import Engine

from rack_overflow.services import exercises, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.routes import session_templates as template_routes

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
NOW = datetime(2026, 11, 3, tzinfo=UTC)

# every non-GET route of L3, ids filled in by `template_ids`
ACTIONS = [
    ("POST", "/seances-types"),
    ("POST", "/seances-types/{t}/deplacement"),
    ("PATCH", "/seances-types/{t}"),
    ("POST", "/seances-types/{t}/archive"),
    ("DELETE", "/seances-types/{t}/archive"),
    ("POST", "/seances-types/{t}/blocs"),
    ("PATCH", "/seances-types/{t}/blocs/{s}"),
    ("POST", "/seances-types/{t}/blocs/{s}/deplacement"),
    ("DELETE", "/seances-types/{t}/blocs/{s}"),
    ("POST", "/seances-types/{t}/blocs/{s}/options"),
    ("POST", "/seances-types/{t}/blocs/{s}/options/{o}/deplacement"),
    ("DELETE", "/seances-types/{t}/blocs/{s}/options/{o}"),
]
GETS = ["/seances-types", "/seances-types?archivees=1", "/seances-types/nouvelle", "/seances-types/{t}"]
VALID_BODIES = {
    "/seances-types": {"name": "Neuve", "location": "gym"},
    "/seances-types/{t}": {"name": "Salle 1", "location": "home"},
    "/seances-types/{t}/deplacement": {"direction": "down"},
    "/seances-types/{t}/blocs": {"kind": "exercise", "exercise_id": "{e}"},
    "/seances-types/{t}/blocs/{s}": {"label": "Tirage", "sets": "3"},
    "/seances-types/{t}/blocs/{s}/deplacement": {"direction": "down"},
    "/seances-types/{t}/blocs/{s}/options": {"exercise_id": "{e}"},
    "/seances-types/{t}/blocs/{s}/options/{o}/deplacement": {"direction": "down"},
}


def exercise(engine: Engine, name: str, user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, "strength", "gym"))


def template_ids(engine: Engine) -> dict[str, int]:
    """« Salle 1 » with a menu « Tirage » of two options, a second template, a spare exercise."""
    a, b, spare = (exercise(engine, name) for name in ("Rowing", "Tirage poulie", "Squat"))
    salle = templates.create(engine, USER, TemplateForm("Salle 1", "gym"))
    templates.create(engine, USER, TemplateForm("Maison", "home"))
    menu = templates.add_slot(engine, USER, salle, kind="menu", exercise_id=a, label="Tirage")
    option = templates.get_detail(engine, USER, salle).slot(menu).options[0].id
    templates.add_option(engine, USER, salle, menu, b)
    return {"t": salle, "s": menu, "o": option, "e": spare}


def fill(path: str, ids: dict[str, int]) -> str:
    return path.format(**ids)


def body_for(path: str, ids: dict[str, int]) -> dict[str, str]:
    return {key: value.format(**ids) for key, value in VALID_BODIES.get(path, {}).items()}


def rows(engine: Engine) -> tuple[list[tuple], ...]:
    with engine.begin() as connection:
        return tuple(
            [tuple(row) for row in connection.execute(sa.select(table).order_by(table.c.id))]
            for table in (s.template, s.template_slot, s.template_slot_option)
        )


def autofocused(html: str) -> list[str]:
    return re.findall(r'id="([^"]+)"[^>]*\sautofocus', html)


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html)
    assert match is not None, html
    return match.group(1)


# --- security, every route


def test_the_list_covers_every_template_action() -> None:
    app_routes = {
        (method, route.path)
        for route in template_routes.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "GET"
    }
    names = {"{t}": "{template_id}", "{s}": "{slot_id}", "{o}": "{option_id}"}
    listed = set()
    for method, path in ACTIONS:
        for short, long in names.items():
            path = path.replace(short, long)
        listed.add((method, path))
    assert app_routes == listed


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_form_encoded_body_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    response = client.request(method, fill(path, ids), data=body_for(path, ids) or {"x": "y"}, headers=HTMX)
    assert response.status_code == 415
    assert response.json() == {"error": "unsupported_media_type"}
    assert rows(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
@pytest.mark.parametrize(
    "foreign", [{"origin": "http://evil.example"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}]
)
def test_cross_origin_action_is_refused_and_changes_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str, foreign: dict[str, str]
) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    response = client.request(method, fill(path, ids), json=body_for(path, ids), headers={**HTMX, **foreign})
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden_origin"}
    assert rows(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), ACTIONS)
def test_unpaired_action_is_sent_to_pairing_and_changes_nothing(
    unpaired_client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    response = unpaired_client.request(method, fill(path, ids), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/appairage"
    assert rows(migrated_engine) == before


@pytest.mark.parametrize("path", GETS)
def test_unpaired_navigation_goes_to_pairing(
    unpaired_client: TestClient, migrated_engine: Engine, path: str
) -> None:
    ids = template_ids(migrated_engine)
    response = unpaired_client.get(fill(path, ids), headers=PAGE, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/appairage"


@pytest.mark.parametrize(("method", "path"), [a for a in ACTIONS if a[1] != "/seances-types"])
def test_valid_bodies_are_accepted(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    """The 404 tests below send these bodies: they must not be refused for another reason."""
    ids = template_ids(migrated_engine)
    response = client.request(method, fill(path, ids), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 200, response.text


# --- unknown, foreign, soft-deleted ids


def _missing_cases() -> list[tuple[str, str, str]]:
    return [(m, p, k) for m, p in ACTIONS for k in "tso" if "{" + k + "}" in p]


@pytest.mark.parametrize(("method", "path", "missing"), _missing_cases())
@pytest.mark.parametrize("kind", ["unknown", "foreign"])
def test_unknown_and_foreign_ids_are_404_and_change_nothing(
    client: TestClient, migrated_engine: Engine, method: str, path: str, missing: str, kind: str
) -> None:
    ids = template_ids(migrated_engine)
    if kind == "unknown":
        ids[missing] = 9999
    else:  # the same kind of row, owned by another user
        theirs_a, theirs_b = exercise(migrated_engine, "A", OTHER), exercise(migrated_engine, "B", OTHER)
        theirs = templates.create(migrated_engine, OTHER, TemplateForm("Autre", "gym"))
        menu = templates.add_slot(
            migrated_engine, OTHER, theirs, kind="menu", exercise_id=theirs_a, label="M"
        )
        templates.add_option(migrated_engine, OTHER, theirs, menu, theirs_b)
        option = templates.get_detail(migrated_engine, OTHER, theirs).slot(menu).options[0].id
        ids[missing] = {"t": theirs, "s": menu, "o": option}[missing]
    before = rows(migrated_engine)
    response = client.request(method, fill(path, ids), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert rows(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), [a for a in ACTIONS if "{s}" in a[1]])
def test_a_slot_of_another_template_is_404(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = template_ids(migrated_engine)
    other = templates.list_templates(migrated_engine, USER)[1].id
    before = rows(migrated_engine)
    response = client.request(method, fill(path, {**ids, "t": other}), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 404
    assert rows(migrated_engine) == before


@pytest.mark.parametrize(("method", "path"), [a for a in ACTIONS if "{s}" in a[1]])
def test_a_soft_deleted_slot_is_404_but_its_rows_stay(
    client: TestClient, migrated_engine: Engine, method: str, path: str
) -> None:
    ids = template_ids(migrated_engine)
    templates.remove_slot(migrated_engine, USER, ids["t"], ids["s"], NOW)
    before = rows(migrated_engine)
    assert len(before[1]) == 1 and len(before[2]) == 2  # slot and its options kept
    response = client.request(method, fill(path, ids), json=body_for(path, ids), headers=HTMX)
    assert response.status_code == 404
    assert rows(migrated_engine) == before


def test_an_option_of_another_menu_is_404(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    other_menu = templates.add_slot(
        migrated_engine, USER, ids["t"], kind="menu", exercise_id=ids["e"], label="X"
    )
    base = f"/seances-types/{ids['t']}/blocs/{other_menu}/options/{ids['o']}"
    assert client.request("DELETE", base, json={}, headers=HTMX).status_code == 404
    moved = client.post(base + "/deplacement", json={"direction": "down"}, headers=HTMX)
    assert moved.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/seances-types/0",
        "/seances-types/-1",
        "/seances-types/9223372036854775808",
    ],
)
def test_odd_template_ids_on_pages_are_404_pages(client: TestClient, path: str) -> None:
    response = client.get(path, headers=PAGE)
    assert response.status_code in (404, 422)
    assert response.headers["content-type"].startswith("text/html")


def test_a_soft_deleted_slot_leaves_the_page_and_the_count(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = template_ids(migrated_engine)
    kept = templates.add_slot(migrated_engine, USER, ids["t"], kind="exercise", exercise_id=ids["e"])
    templates.remove_slot(migrated_engine, USER, ids["t"], ids["s"], NOW)
    page = client.get(f"/seances-types/{ids['t']}", headers=PAGE).text
    assert f'id="bloc-{ids["s"]}"' not in page and f'id="bloc-{kept}"' in page
    listed = client.get("/seances-types", headers=PAGE).text
    assert TEXT("templates.slot_count", count=1) in listed
    with migrated_engine.begin() as connection:
        position = connection.execute(
            sa.select(s.template_slot.c.position).where(s.template_slot.c.id == kept)
        ).scalar_one()
    assert position == 0  # live slots renumbered


# --- moves at the ends


def _focus_on(html: str, element_id: str) -> bool:
    return autofocused(html) == [element_id]


def test_template_moves_at_the_ends(client: TestClient, migrated_engine: Engine) -> None:
    template_ids(migrated_engine)
    first, last = (t.id for t in templates.list_templates(migrated_engine, USER))
    before = rows(migrated_engine)
    up = client.post(f"/seances-types/{first}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert up.status_code == 200 and _focus_on(up.text, f"seance-type-{first}-descendre")
    assert announced(up.text) == TEXT("template.announce_moved", name="Salle 1", position=1, total=2)
    down = client.post(f"/seances-types/{last}/deplacement", json={"direction": "down"}, headers=HTMX)
    assert _focus_on(down.text, f"seance-type-{last}-monter")
    assert rows(migrated_engine) == before
    swapped = client.post(f"/seances-types/{last}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert _focus_on(swapped.text, f"seance-type-{last}-descendre")
    assert [t.id for t in templates.list_templates(migrated_engine, USER)] == [last, first]


def test_moving_a_lone_row_keeps_focus_on_a_live_control(client: TestClient, migrated_engine: Engine) -> None:
    salle = templates.create(migrated_engine, USER, TemplateForm("Solo", "gym"))
    only = exercise(migrated_engine, "Unique")
    menu = templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=only, label="M")
    option = templates.get_detail(migrated_engine, USER, salle).slot(menu).options[0].id
    base = f"/seances-types/{salle}"
    for direction in ("up", "down"):
        body = {"direction": direction}
        listed = client.post(f"{base}/deplacement", json=body, headers=HTMX)
        assert _focus_on(listed.text, f"seance-type-{salle}-lien")
        slot = client.post(f"{base}/blocs/{menu}/deplacement", json=body, headers=HTMX)
        assert _focus_on(slot.text, f"bloc-{menu}-modifier")
        moved = client.post(f"{base}/blocs/{menu}/options/{option}/deplacement", json=body, headers=HTMX)
        assert _focus_on(moved.text, f"bloc-{menu}-option-ajout")  # a lone option has no « Retirer »


def test_an_archived_template_cannot_move_and_restore_puts_it_last(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = template_ids(migrated_engine)
    third = templates.create(migrated_engine, USER, TemplateForm("Cardio", "both"))
    client.post(f"/seances-types/{ids['t']}/archive", json={}, headers=HTMX)
    moved = client.post(f"/seances-types/{ids['t']}/deplacement", json={"direction": "down"}, headers=HTMX)
    assert moved.status_code == 404
    listed = client.get("/seances-types", headers=PAGE).text
    assert f'id="seance-type-{ids["t"]}"' not in listed
    restored = client.request("DELETE", f"/seances-types/{ids['t']}/archive", json={}, headers=HTMX)
    assert restored.status_code == 200
    assert [t.id for t in templates.list_templates(migrated_engine, USER)][-1] == ids["t"]
    assert third in [t.id for t in templates.list_templates(migrated_engine, USER)]


def test_slot_moves_at_the_ends(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    fixed = templates.add_slot(migrated_engine, USER, ids["t"], kind="exercise", exercise_id=ids["e"])
    base = f"/seances-types/{ids['t']}/blocs"
    up = client.post(f"{base}/{ids['s']}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert _focus_on(up.text, f"bloc-{ids['s']}-descendre")
    down = client.post(f"{base}/{fixed}/deplacement", json={"direction": "down"}, headers=HTMX)
    assert _focus_on(down.text, f"bloc-{fixed}-monter")
    assert [x.id for x in templates.get_detail(migrated_engine, USER, ids["t"]).slots] == [ids["s"], fixed]
    swap = client.post(f"{base}/{fixed}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert _focus_on(swap.text, f"bloc-{fixed}-descendre")
    assert announced(swap.text) == TEXT("template.announce_moved", name="Squat", position=1, total=2)
    assert [x.position for x in templates.get_detail(migrated_engine, USER, ids["t"]).slots] == [0, 1]


def test_option_moves_at_the_ends_keep_the_menu_open(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    first, last = (o.id for o in templates.get_detail(migrated_engine, USER, ids["t"]).slot(ids["s"]).options)
    base = f"/seances-types/{ids['t']}/blocs/{ids['s']}/options"
    up = client.post(f"{base}/{first}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert _focus_on(up.text, f"option-{first}-descendre")
    assert '<details class="slot__edit" open>' in up.text
    down = client.post(f"{base}/{last}/deplacement", json={"direction": "down"}, headers=HTMX)
    assert _focus_on(down.text, f"option-{last}-monter")
    swap = client.post(f"{base}/{last}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert announced(swap.text) == TEXT("template.announce_moved", name="Tirage poulie", position=1, total=2)
    options = templates.get_detail(migrated_engine, USER, ids["t"]).slot(ids["s"]).options
    assert [o.id for o in options] == [last, first]
    assert "Tirage poulie · Rowing" in swap.text  # the summary line follows the new order


@pytest.mark.parametrize("direction", ["left", "", "UP", None])
def test_bad_directions_are_422_on_every_move(
    client: TestClient, migrated_engine: Engine, direction: str | None
) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    for path in [p for _, p in ACTIONS if p.endswith("deplacement")]:
        response = client.post(fill(path, ids), json={"direction": direction}, headers=HTMX)
        assert response.status_code == 422, path
    assert rows(migrated_engine) == before


# --- menus: zero, one, many options; duplicates


def test_a_menu_is_never_created_empty(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    for exercise_id in ("", "   ", None):
        body = {"kind": "menu", "label": "Bras", "exercise_id": exercise_id}
        refused = client.post(f"/seances-types/{ids['t']}/blocs", json=body, headers=HTMX)
        assert refused.status_code == 200
        assert (
            'id="bloc-ajout-exercice-erreur" class="field__error">' + TEXT("catalog.error.required")
            in refused.text
        )
        assert autofocused(refused.text) == ["bloc-ajout-exercice"]
        assert 'value="Bras"' in refused.text
    assert rows(migrated_engine) == before


def test_a_menu_with_one_option_has_no_remove_button(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    menu = templates.add_slot(
        migrated_engine, USER, ids["t"], kind="menu", exercise_id=ids["e"], label="Seul"
    )
    html = client.get(f"/seances-types/{ids['t']}", headers=PAGE).text
    only = templates.get_detail(migrated_engine, USER, ids["t"]).slot(menu).options[0].id
    assert f'id="option-{only}-retirer"' not in html
    assert f'id="option-{ids["o"]}-retirer"' in html  # the two-option menu keeps its buttons
    refused = client.request(
        "DELETE", f"/seances-types/{ids['t']}/blocs/{menu}/options/{only}", json={}, headers=HTMX
    )
    assert refused.status_code == 200
    assert (
        f'id="bloc-{menu}-options-erreur" class="field__error">{TEXT("catalog.error.last_option")}'
        in refused.text
    )
    assert announced(refused.text) == TEXT("catalog.error.last_option")
    assert len(templates.get_detail(migrated_engine, USER, ids["t"]).slot(menu).options) == 1


def test_a_duplicate_option_is_refused_with_focus_on_the_select(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = template_ids(migrated_engine)
    rowing = templates.get_detail(migrated_engine, USER, ids["t"]).slot(ids["s"]).options[0].exercise.id
    before = rows(migrated_engine)
    refused = client.post(
        f"/seances-types/{ids['t']}/blocs/{ids['s']}/options", json={"exercise_id": str(rowing)}, headers=HTMX
    )
    assert refused.status_code == 200
    assert TEXT("catalog.error.option_taken") in refused.text
    assert autofocused(refused.text) == [f"bloc-{ids['s']}-option-ajout"]
    assert 'aria-invalid="true"' in refused.text
    assert announced(refused.text) == TEXT("catalog.error.option_taken")
    assert rows(migrated_engine) == before


def test_the_same_exercise_may_sit_in_several_slots_and_menus(
    client: TestClient, migrated_engine: Engine
) -> None:
    ids = template_ids(migrated_engine)
    base = f"/seances-types/{ids['t']}/blocs"
    for body in (
        {"kind": "exercise", "exercise_id": str(ids["e"])},
        {"kind": "exercise", "exercise_id": str(ids["e"])},
        {"kind": "menu", "exercise_id": str(ids["e"]), "label": "Tirage"},  # same label as the first menu
    ):
        assert TEXT(
            "template.announce_slot_added", name="Squat" if body["kind"] == "exercise" else "Tirage"
        ) in (client.post(base, json=body, headers=HTMX).text)
    added = client.post(f"{base}/{ids['s']}/options", json={"exercise_id": str(ids["e"])}, headers=HTMX)
    assert announced(added.text) == TEXT("template.announce_option_added", name="Squat")
    assert len(templates.get_detail(migrated_engine, USER, ids["t"]).slots) == 4


def test_twelve_options_then_the_add_form_is_replaced(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    more = [exercise(migrated_engine, f"Option {n:02d}") for n in range(10)]
    base = f"/seances-types/{ids['t']}/blocs/{ids['s']}/options"
    for exercise_id in more[:9]:
        templates.add_option(migrated_engine, USER, ids["t"], ids["s"], exercise_id)
    twelfth = client.post(base, json={"exercise_id": str(more[9])}, headers=HTMX)
    assert announced(twelfth.text) == TEXT("template.announce_option_added", name="Option 09")
    assert TEXT("template.options_full") in twelfth.text
    assert autofocused(twelfth.text) == [f"bloc-{ids['s']}-option-ajout"]  # the muted line takes the focus
    before = rows(migrated_engine)
    refused = client.post(base, json={"exercise_id": str(ids["e"])}, headers=HTMX)
    assert refused.status_code == 200
    assert TEXT("catalog.error.too_many_options", max=12) in refused.text
    assert rows(migrated_engine) == before


@pytest.mark.xfail(
    strict=True,
    reason="session_template_slot_form.html: a refused add-option whose form became a muted line "
    "(none left / 12 options) autofocuses nothing, so the focus is lost after the swap (D-053)",
)
def test_a_refused_option_keeps_a_focus_target_when_nothing_is_left(
    client: TestClient, migrated_engine: Engine
) -> None:
    salle = templates.create(migrated_engine, USER, TemplateForm("Solo", "gym"))
    only = exercise(migrated_engine, "Unique")
    menu = templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=only, label="M")
    refused = client.post(
        f"/seances-types/{salle}/blocs/{menu}/options", json={"exercise_id": str(only)}, headers=HTMX
    )
    assert TEXT("catalog.error.option_taken") in refused.text
    assert autofocused(refused.text) == [f"bloc-{menu}-option-ajout"]


# --- archived exercises in slots and menus


def test_archived_exercise_choices(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    fixed = templates.add_slot(migrated_engine, USER, ids["t"], kind="exercise", exercise_id=ids["e"])
    exercises.set_archived(migrated_engine, USER, ids["e"], NOW)
    base = f"/seances-types/{ids['t']}/blocs"
    page = client.get(f"/seances-types/{ids['t']}", headers=PAGE).text
    add_form = page.split('class="add-slot"', 1)[1]
    assert ">Squat<" not in add_form  # never offered when adding
    refused = client.post(base, json={"kind": "exercise", "exercise_id": str(ids["e"])}, headers=HTMX)
    assert TEXT("catalog.error.exercise_unavailable") in refused.text
    option = client.post(f"{base}/{ids['s']}/options", json={"exercise_id": str(ids["e"])}, headers=HTMX)
    assert TEXT("catalog.error.exercise_unavailable") in option.text
    other = exercise(migrated_engine, "Fentes")
    switched = client.patch(f"{base}/{fixed}", json={"exercise_id": str(other)}, headers=HTMX)
    assert announced(switched.text) == TEXT("status.saved")
    back = client.patch(f"{base}/{fixed}", json={"exercise_id": str(ids["e"])}, headers=HTMX)
    assert f'id="bloc-{fixed}-exercice-erreur" class="field__error">' in back.text
    assert TEXT("catalog.error.exercise_unavailable") in back.text
    assert autofocused(back.text) == [f"bloc-{fixed}-exercice"]
    assert templates.get_detail(migrated_engine, USER, ids["t"]).slot(fixed).exercise.id == other  # type: ignore[union-attr]
    exercises.set_archived(migrated_engine, USER, ids["e"], None)
    assert (
        ">Squat<"
        in client.get(f"/seances-types/{ids['t']}", headers=PAGE).text.split('class="add-slot"', 1)[1]
    )


def test_a_foreign_exercise_is_unavailable_everywhere(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    theirs = exercise(migrated_engine, "Secret", OTHER)
    base = f"/seances-types/{ids['t']}/blocs"
    before = rows(migrated_engine)
    for response in (
        client.post(base, json={"kind": "exercise", "exercise_id": str(theirs)}, headers=HTMX),
        client.post(base, json={"kind": "menu", "label": "M", "exercise_id": str(theirs)}, headers=HTMX),
        client.post(f"{base}/{ids['s']}/options", json={"exercise_id": str(theirs)}, headers=HTMX),
    ):
        assert response.status_code == 200
        assert TEXT("catalog.error.exercise_unavailable") in response.text
        assert "Secret" not in response.text
    assert rows(migrated_engine) == before


def test_removing_the_last_slot_with_no_exercise_left_focuses_the_muted_line(
    client: TestClient, migrated_engine: Engine
) -> None:
    salle = templates.create(migrated_engine, USER, TemplateForm("Vide", "gym"))
    only = exercise(migrated_engine, "Unique")
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=only)
    exercises.set_archived(migrated_engine, USER, only, NOW)
    gone = client.request("DELETE", f"/seances-types/{salle}/blocs/{slot}", json={}, headers=HTMX)
    assert TEXT("template.no_exercise") in gone.text
    assert autofocused(gone.text) == ["bloc-ajout-exercice-type"]
    assert TEXT("template.no_slot_title") in gone.text


# --- targets through the page


@pytest.mark.parametrize(
    ("body", "stored"),
    [
        ({"sets": "4", "reps": "6\u20138"}, (4, 6, 8, None, None, None)),
        ({"sets": "3", "reps": "12", "duration": "0:30"}, (3, 12, 12, 30, None, None)),
        ({"sets": "1", "duration": "30:00"}, (1, None, None, 1800, None, None)),
        ({"sets": "4"}, (4, None, None, None, None, None)),
        ({"reps": " 8 à 10 ", "note": " par côté "}, (None, 8, 10, None, None, "par côté")),
        ({"distance": "0,4"}, (None, None, None, None, 400, None)),
        ({"sets": "", "reps": "", "duration": "", "distance": "", "note": ""}, (None,) * 6),
    ],
)
def test_targets_round_trip_through_the_page(
    client: TestClient, migrated_engine: Engine, body: dict[str, str], stored: tuple
) -> None:
    ids = template_ids(migrated_engine)
    path = f"/seances-types/{ids['t']}/blocs/{ids['s']}"
    client.patch(path, json={"label": "Tirage", "sets": "9", "reps": "9", "note": "x"}, headers=HTMX)
    saved = client.patch(path, json={"label": "Tirage", **body}, headers=HTMX)
    assert announced(saved.text) == TEXT("status.saved")
    assert autofocused(saved.text) == [f"bloc-{ids['s']}-modifier"]
    target = templates.get_detail(migrated_engine, USER, ids["t"]).slot(ids["s"]).target
    assert (
        target.sets,
        target.reps_min,
        target.reps_max,
        target.duration_s,
        target.distance_m,
        target.note,
    ) == stored
    if all(part is None for part in stored):
        assert 'class="slot__target"' not in saved.text


@pytest.mark.parametrize(
    ("body", "field", "code", "params"),
    [
        ({"sets": "21"}, "series", "target_sets_range", {}),
        ({"sets": "abc"}, "series", None, {}),
        ({"reps": "0"}, "reps", "target_reps_range", {}),
        ({"reps": "101"}, "reps", "target_reps_range", {}),
        ({"reps": "8-"}, "reps", "target_reps_format", {}),
        ({"reps": "10-8"}, "reps", "target_reps_order", {}),
        ({"duration": "0"}, "duree", "must_be_positive", {}),
        ({"duration": "24:00:01"}, "duree", None, {}),
        ({"distance": "0"}, "distance", "must_be_positive", {}),
        ({"note": "x" * 41}, "note", "too_long", {"max": 40}),
    ],
)
def test_target_refusals_mark_their_input(
    client: TestClient,
    migrated_engine: Engine,
    body: dict[str, str],
    field: str,
    code: str | None,
    params: dict[str, int],
) -> None:
    ids = template_ids(migrated_engine)
    before = rows(migrated_engine)
    refused = client.patch(
        f"/seances-types/{ids['t']}/blocs/{ids['s']}", json={"label": "Tirage", **body}, headers=HTMX
    )
    assert refused.status_code == 200
    input_id = f"bloc-{ids['s']}-{field}"
    assert f'id="{input_id}-erreur" class="field__error">' in refused.text
    if code is not None:
        assert TEXT(f"catalog.error.{code}", **params) in refused.text
    assert autofocused(refused.text) == [input_id]
    assert '<details class="slot__edit" open>' in refused.text
    assert announced(refused.text)
    assert rows(migrated_engine) == before


def test_a_menu_label_over_its_limit_is_refused_in_place(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    path = f"/seances-types/{ids['t']}/blocs/{ids['s']}"
    assert announced(client.patch(path, json={"label": "é" * 40}, headers=HTMX).text) == TEXT("status.saved")
    refused = client.patch(path, json={"label": "x" * 41}, headers=HTMX)
    assert TEXT("catalog.error.too_long", max=40) in refused.text
    assert autofocused(refused.text) == [f"bloc-{ids['s']}-menu"]
    empty = client.patch(path, json={"label": "  "}, headers=HTMX)
    assert TEXT("catalog.error.required") in empty.text
    assert templates.get_detail(migrated_engine, USER, ids["t"]).slot(ids["s"]).label == "é" * 40


# --- template names


@pytest.mark.parametrize("name", ["SALLE 1", " salle 1 ", "Sallé 1"])
def test_template_name_taken_on_create(client: TestClient, migrated_engine: Engine, name: str) -> None:
    template_ids(migrated_engine)
    before = rows(migrated_engine)
    refused = client.post("/seances-types", json={"name": name, "location": "home"}, headers=HTMX)
    assert refused.status_code == 200
    message = TEXT("catalog.error.template_name_taken")
    assert f'id="seance-nom-erreur" class="field__error">{message}' in refused.text
    assert TEXT("catalog.error.name_taken") not in refused.text
    assert autofocused(refused.text) == ["seance-nom"]
    assert announced(refused.text) == message
    assert rows(migrated_engine) == before


def test_template_name_taken_by_an_archived_one_on_edit(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    maison = templates.list_templates(migrated_engine, USER)[1].id
    templates.set_archived(migrated_engine, USER, maison, NOW)
    refused = client.patch(
        f"/seances-types/{ids['t']}", json={"name": "MAISON", "location": "gym"}, headers=HTMX
    )
    assert TEXT("catalog.error.template_name_taken") in refused.text
    assert autofocused(refused.text) == ["seance-nom"]
    own = client.patch(
        f"/seances-types/{ids['t']}", json={"name": "SALLE 1", "location": "gym"}, headers=HTMX
    )
    assert TEXT("status.saved") in own.text  # its own name, new case
    assert templates.get_detail(migrated_engine, USER, ids["t"]).draft.name == "SALLE 1"


def test_template_names_at_their_limit(client: TestClient, migrated_engine: Engine) -> None:
    assert (
        client.post("/seances-types", json={"name": "é" * 60, "location": "both"}, headers=HTMX).status_code
        == 204
    )
    refused = client.post("/seances-types", json={"name": "x" * 61, "location": "both"}, headers=HTMX)
    assert refused.status_code == 200 and TEXT("catalog.error.too_long", max=60) in refused.text
    none = client.post("/seances-types", json={"name": "Sans lieu"}, headers=HTMX)
    assert none.status_code == 200
    assert 'id="seance-lieu-gym"' in none.text and 'aria-invalid="true"' in none.text
    assert [t.draft.name for t in templates.list_templates(migrated_engine, USER)] == ["é" * 60]


def test_every_write_trigger_of_a_full_page_has_a_slot(client: TestClient, migrated_engine: Engine) -> None:
    ids = template_ids(migrated_engine)
    exercises.set_archived(migrated_engine, USER, ids["e"], NOW)
    for path in (f"/seances-types/{ids['t']}", "/seances-types", "/seances-types/nouvelle"):
        html = client.get(path, headers=PAGE).text
        html = html.replace('<details class="slot__edit">', '<details class="slot__edit" open>')
        assert triggers_without_slot(html) == [], path
