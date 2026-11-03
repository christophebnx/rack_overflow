"""Session template pages through the TestClient (docs/ui-spec.md L3; D-050 refusals, D-053 slots,
D-058, D-059): pages, fragments, refusals, 404s, JSON only, focus and announcements."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from request_status import triggers_without_slot
from sqlalchemy.engine import Engine
from test_web_pages import assert_secure_page

from rack_overflow.domain.templates import Target
from rack_overflow.services import exercises, seed, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.web.app import CATALOG
from rack_overflow.web.display import Display
from rack_overflow.web.locale import load_catalog

CATALOG_TEXTS = load_catalog(CATALOG)
TEXT = CATALOG_TEXTS.text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
OTHER = 2
ARCHIVED_AT = datetime(2026, 11, 3, tzinfo=UTC)
NBSP = "\u00a0"
X = f"{NBSP}\u00d7{NBSP}"  # the multiplication sign between sets and parts


def exercise(engine: Engine, name: str, pattern: str | None = None, user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, "strength", "gym", movement_pattern=pattern))


def template(engine: Engine, name: str = "Salle 1", user: int = USER) -> int:
    return templates.create(engine, user, TemplateForm(name, "gym"))


def delete(client: TestClient, path: str) -> object:
    return client.request("DELETE", path, json={}, headers=HTMX)


def announced(html: str) -> str:
    match = re.search(r'<div id="annonce" hx-swap-oob="innerHTML">(.*?)</div>', html)
    assert match is not None, html
    return match.group(1)


def autofocused(html: str) -> list[str]:
    return re.findall(r'id="([^"]+)"[^>]*\sautofocus', html)


# --- list


def test_empty_list_and_nav(client: TestClient) -> None:
    response = client.get("/seances-types", headers=PAGE)
    assert_secure_page(response, 200)
    assert TEXT("templates.empty_title") in response.text
    assert 'href="/seances-types" aria-current="page"' in response.text
    assert 'href="/seances-types/nouvelle"' in response.text
    home = client.get("/", headers=PAGE).text
    assert 'href="/seances-types"' in home and 'href="/seances-types" aria-current' not in home


def test_seeded_list_in_order_with_moves(client: TestClient, migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    response = client.get("/seances-types", headers=PAGE)
    assert_secure_page(response, 200)
    html = response.text
    names = [t.draft.name for t in templates.list_templates(migrated_engine, USER)]
    positions = [html.index(name.replace("&", "&amp;")) for name in names]
    assert positions == sorted(positions)
    assert TEXT("templates.slot_count", count=6) in html
    assert triggers_without_slot(html) == []
    first, second = (t.id for t in templates.list_templates(migrated_engine, USER)[:2])
    assert re.search(rf'id="seance-type-{first}-monter"[^>]*disabled', html)
    moved = client.post(f"/seances-types/{first}/deplacement", json={"direction": "down"}, headers=HTMX)
    assert moved.status_code == 200
    assert autofocused(moved.text) == [f"seance-type-{first}-descendre"]
    assert announced(moved.text) == TEXT(
        "template.announce_moved", name=names[0], position=2, total=4
    ).replace("&", "&amp;")
    assert [t.id for t in templates.list_templates(migrated_engine, USER)[:2]] == [second, first]
    assert triggers_without_slot(moved.text) == []


def test_one_template_has_no_move_buttons_and_archived_are_apart(
    client: TestClient, migrated_engine: Engine
) -> None:
    active = template(migrated_engine, "Active")
    old = template(migrated_engine, "Ancienne")
    client.post(f"/seances-types/{old}/archive", json={}, headers=HTMX)
    html = client.get("/seances-types", headers=PAGE).text
    assert "deplacement" not in html and "Ancienne" not in html
    shown = client.get("/seances-types?archivees=1", headers=PAGE).text
    assert TEXT("templates.archived_heading") in shown and "Ancienne" in shown
    assert TEXT("templates.hide_archived") in shown
    assert f'/seances-types/{active}"' in shown


def test_move_refusals(client: TestClient, migrated_engine: Engine) -> None:
    a = template(migrated_engine, "A")
    template(migrated_engine, "B")
    assert (
        client.post(f"/seances-types/{a}/deplacement", json={"direction": "left"}, headers=HTMX).status_code
        == 422
    )
    assert (
        client.post("/seances-types/999/deplacement", json={"direction": "up"}, headers=HTMX).status_code
        == 404
    )
    form = client.post(
        f"/seances-types/{a}/deplacement",
        data={"direction": "up"},
        headers={**HTMX, "content-type": "application/x-www-form-urlencoded"},
    )
    assert form.status_code == 415


# --- create and edit


def test_new_page_and_create(client: TestClient, migrated_engine: Engine) -> None:
    page = client.get("/seances-types/nouvelle", headers=PAGE)
    assert_secure_page(page, 200)
    assert 'id="seance-nom"' in page.text and "checked" not in page.text
    assert triggers_without_slot(page.text) == []
    created = client.post("/seances-types", json={"name": "Salle 1", "location": "gym"}, headers=HTMX)
    assert created.status_code == 204
    template_id = templates.list_templates(migrated_engine, USER)[0].id
    assert created.headers["hx-redirect"] == f"/seances-types/{template_id}"
    detail = client.get(f"/seances-types/{template_id}", headers=PAGE)
    assert_secure_page(detail, 200)
    assert TEXT("template.no_slot_title") in detail.text
    assert triggers_without_slot(detail.text) == []


@pytest.mark.parametrize(
    ("body", "input_id", "message"),
    [
        ({"name": "", "location": "gym"}, "seance-nom", TEXT("catalog.error.required")),
        ({"name": "x" * 61, "location": "gym"}, "seance-nom", TEXT("catalog.error.too_long", max=60)),
        ({"name": "salle 1", "location": "gym"}, "seance-nom", TEXT("catalog.error.template_name_taken")),
        ({"name": "B", "location": "office"}, "seance-lieu-gym", TEXT("catalog.error.invalid_choice")),
        ({"name": "B"}, "seance-lieu-gym", TEXT("catalog.error.required")),
    ],
)
def test_create_refusals(
    client: TestClient, migrated_engine: Engine, body: dict[str, str], input_id: str, message: str
) -> None:
    template(migrated_engine, "Salle 1")
    response = client.post("/seances-types", json=body, headers=HTMX)
    assert response.status_code == 200
    assert f'id="{input_id}-erreur" class="field__error">{message}' in response.text
    assert autofocused(response.text) == [input_id]
    assert announced(response.text) == message
    assert 'aria-invalid="true"' in response.text
    assert len(templates.list_templates(migrated_engine, USER)) == 1


def test_edit_saves_and_retitles(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    template(migrated_engine, "Maison")
    saved = client.patch(
        f"/seances-types/{salle}", json={"name": "Salle A", "location": "both"}, headers=HTMX
    )
    assert saved.status_code == 200
    assert 'data-kind="ok"' in saved.text and announced(saved.text) == TEXT("status.saved")
    assert '<span id="seance-type-titre" hx-swap-oob="true">Salle A</span>' in saved.text
    assert TEXT("exercise.location.both") in saved.text.split('id="seance-type-lieu"', 1)[1]
    refused = client.patch(
        f"/seances-types/{salle}", json={"name": "MAISON", "location": "gym"}, headers=HTMX
    )
    assert TEXT("catalog.error.template_name_taken") in refused.text
    assert templates.get_detail(migrated_engine, USER, salle).draft.name == "Salle A"


def test_archive_and_restore(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    archived = client.post(f"/seances-types/{salle}/archive", json={}, headers=HTMX)
    assert announced(archived.text) == TEXT("template.announce_archived")
    assert autofocused(archived.text) == ["seance-type-restaurer"]
    assert (
        f'<span id="seance-type-etat" hx-swap-oob="true"><span class="tag">{TEXT("tag.archived_f")}'
        in archived.text
    )
    page = client.get(f"/seances-types/{salle}", headers=PAGE).text
    assert TEXT("template.archived_text") in page and 'hx-patch="/seances-types/' in page
    restored = delete(client, f"/seances-types/{salle}/archive")
    assert announced(restored.text) == TEXT("template.announce_restored")  # type: ignore[attr-defined]


@pytest.mark.parametrize("path", ["/seances-types/999", "/seances-types/abc"])
def test_unknown_template_pages(client: TestClient, path: str) -> None:
    response = client.get(path, headers=PAGE)
    assert response.status_code in (404, 422)


def test_foreign_template_is_not_found(client: TestClient, migrated_engine: Engine) -> None:
    theirs = template(migrated_engine, user=OTHER)
    assert client.get(f"/seances-types/{theirs}", headers=PAGE).status_code == 404
    assert client.patch(
        f"/seances-types/{theirs}", json={"name": "X", "location": "gym"}, headers=HTMX
    ).json() == {"error": "not_found"}
    assert client.post(f"/seances-types/{theirs}/archive", json={}, headers=HTMX).status_code == 404
    assert (
        client.post(
            f"/seances-types/{theirs}/blocs", json={"kind": "exercise", "exercise_id": "1"}, headers=HTMX
        ).status_code
        == 404
    )


# --- slots and options


def test_roadmap_scenario_through_the_routes(client: TestClient, migrated_engine: Engine) -> None:
    ids = [
        exercise(migrated_engine, name, "Tirage horizontal")
        for name in ("Rowing barre", "Rowing assis", "Poulie")
    ]
    squat = exercise(migrated_engine, "Squat", "Squat")
    client.post("/seances-types", json={"name": "Salle 1", "location": "gym"}, headers=HTMX)
    salle = templates.list_templates(migrated_engine, USER)[0].id
    base = f"/seances-types/{salle}/blocs"

    added = client.post(
        base, json={"kind": "menu", "exercise_id": str(ids[0]), "label": "Tirage"}, headers=HTMX
    )
    assert added.status_code == 200 and triggers_without_slot(added.text) == []
    pull = templates.get_detail(migrated_engine, USER, salle).slots[0].id
    assert autofocused(added.text) == [f"bloc-{pull}-option-ajout"]
    assert announced(added.text) == TEXT("template.announce_slot_added", name="Tirage")
    assert '<details class="slot__edit" open>' in added.text
    for exercise_id in ids[1:]:
        option = client.post(f"{base}/{pull}/options", json={"exercise_id": str(exercise_id)}, headers=HTMX)
        assert autofocused(option.text) == [f"bloc-{pull}-option-ajout"]
    assert announced(option.text) == TEXT("template.announce_option_added", name="Poulie")
    assert TEXT("template.options_none_left") not in option.text  # « Squat » can still be added

    fixed = client.post(
        base, json={"kind": "exercise", "exercise_id": str(squat), "label": "ignored"}, headers=HTMX
    )
    leg = templates.get_detail(migrated_engine, USER, salle).slots[1]
    assert leg.label is None and leg.name == "Squat"
    assert autofocused(fixed.text) == [f"bloc-{leg.id}-series"]

    moved = client.post(f"{base}/{leg.id}/deplacement", json={"direction": "up"}, headers=HTMX)
    assert autofocused(moved.text) == [f"bloc-{leg.id}-descendre"]
    assert announced(moved.text) == TEXT("template.announce_moved", name="Squat", position=1, total=2)
    options = templates.get_detail(migrated_engine, USER, salle).slot(pull).options
    moved_option = client.post(
        f"{base}/{pull}/options/{options[2].id}/deplacement", json={"direction": "up"}, headers=HTMX
    )
    assert autofocused(moved_option.text) == [f"option-{options[2].id}-monter"]
    names = [o.exercise.name for o in templates.get_detail(migrated_engine, USER, salle).slot(pull).options]
    assert names == ["Rowing barre", "Poulie", "Rowing assis"]

    archived = client.post(f"/seances-types/{salle}/archive", json={}, headers=HTMX)
    assert archived.status_code == 200
    assert templates.list_templates(migrated_engine, USER) == []


def test_save_slot_target_and_its_display(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    plank = exercise(migrated_engine, "Planche", "Gainage")
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=plank)
    body = {"exercise_id": str(plank), "sets": "3", "reps": "12", "duration": "0:30", "note": "par côté"}
    saved = client.patch(f"/seances-types/{salle}/blocs/{slot}", json=body, headers=HTMX)
    assert saved.status_code == 200
    assert f"3{X}30{NBSP}s / 12 · par côté" in saved.text
    assert autofocused(saved.text) == [f"bloc-{slot}-modifier"]
    assert announced(saved.text) == TEXT("status.saved")
    assert 'value="0:30"' in saved.text and 'value="12"' in saved.text
    assert templates.get_detail(migrated_engine, USER, salle).slot(slot).target == Target(
        3, 12, 12, 30, None, "par côté"
    )


def test_slot_refusals_keep_the_row_open(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    squat = exercise(migrated_engine, "Squat")
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=squat)
    body = {"exercise_id": str(squat), "sets": "0", "reps": "10-8", "duration": "1:75", "note": "x" * 41}
    refused = client.patch(f"/seances-types/{salle}/blocs/{slot}", json=body, headers=HTMX)
    assert refused.status_code == 200
    assert '<details class="slot__edit" open>' in refused.text
    assert autofocused(refused.text) == [f"bloc-{slot}-series"]
    for input_id, key in (
        ("series", "catalog.error.target_sets_range"),
        ("reps", "catalog.error.target_reps_order"),
        ("duree", "catalog.error.bad_duration"),
    ):
        assert f'id="bloc-{slot}-{input_id}-erreur" class="field__error">{TEXT(key)}' in refused.text
    assert TEXT("catalog.error.too_long", max=40) in refused.text
    assert 'value="10-8"' in refused.text
    assert announced(refused.text) == TEXT("catalog.error.target_sets_range")
    bad = client.patch(f"/seances-types/{salle}/blocs/{slot}", json={"exercise_id": "abc"}, headers=HTMX)
    assert bad.status_code == 422


def test_add_slot_refusals(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    old = exercise(migrated_engine, "Vieux")
    exercise(migrated_engine, "Neuf")
    exercises.set_archived(migrated_engine, USER, old, ARCHIVED_AT)
    base = f"/seances-types/{salle}/blocs"
    refused = client.post(base, json={"kind": "menu", "exercise_id": "", "label": " "}, headers=HTMX)
    assert (
        f'id="bloc-ajout-menu-erreur" class="field__error">{TEXT("catalog.error.required")}' in refused.text
    )
    assert autofocused(refused.text) == ["bloc-ajout-menu"]
    assert 'value="menu" checked' in refused.text
    unavailable = client.post(base, json={"kind": "exercise", "exercise_id": "999"}, headers=HTMX)
    assert TEXT("catalog.error.exercise_unavailable") in unavailable.text
    assert client.post(base, json={"kind": "superset", "exercise_id": "1"}, headers=HTMX).status_code == 422
    assert client.post(base, json={"kind": "exercise", "exercise_id": "x"}, headers=HTMX).status_code == 422


def test_archived_exercises_are_flagged(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    plank = exercise(migrated_engine, "Planche", "Gainage")
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=plank)
    templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=plank, label="Gainage")
    exercises.set_archived(migrated_engine, USER, plank, ARCHIVED_AT)
    html = client.get(f"/seances-types/{salle}", headers=PAGE).text
    assert TEXT("template.slot_skipped_exercise") in html and TEXT("template.slot_skipped_menu") in html
    assert TEXT("template.option_archived", name="Planche") in html
    assert f'<option value="{plank}" selected>{TEXT("template.option_archived", name="Planche")}' in html
    assert TEXT("template.no_exercise") in html
    saved = client.patch(
        f"/seances-types/{salle}/blocs/{slot}", json={"exercise_id": str(plank), "sets": "2"}, headers=HTMX
    )
    assert announced(saved.text) == TEXT("status.saved")
    assert (
        TEXT("template.last_option_hint") in html
        and '-retirer" hx-delete="/seances-types/1/blocs/2/options' not in html
    )


def test_remove_slot_and_options_focus(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    a, b, c = (exercise(migrated_engine, name) for name in "ABC")
    first = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=a)
    menu = templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=a, label="M")
    templates.add_option(migrated_engine, USER, salle, menu, b)
    templates.add_option(migrated_engine, USER, salle, menu, c)
    base = f"/seances-types/{salle}/blocs"
    options = templates.get_detail(migrated_engine, USER, salle).slot(menu).options
    removed = delete(client, f"{base}/{menu}/options/{options[1].id}")
    assert autofocused(removed.text) == [f"option-{options[2].id}-retirer"]  # type: ignore[attr-defined]
    assert announced(removed.text) == TEXT("template.announce_option_removed", name="B")  # type: ignore[attr-defined]
    removed = delete(client, f"{base}/{menu}/options/{options[2].id}")
    assert autofocused(removed.text) == [f"bloc-{menu}-option-ajout"]  # type: ignore[attr-defined]
    last = delete(client, f"{base}/{menu}/options/{options[0].id}")
    assert TEXT("catalog.error.last_option") in last.text  # type: ignore[attr-defined]
    assert delete(client, f"{base}/{menu}/options/999").status_code == 404  # type: ignore[attr-defined]

    gone = delete(client, f"{base}/{menu}")
    assert autofocused(gone.text) == [f"bloc-{first}-modifier"]  # type: ignore[attr-defined]
    assert announced(gone.text) == TEXT("template.announce_slot_removed", name="M")  # type: ignore[attr-defined]
    assert delete(client, f"{base}/{menu}").status_code == 404  # type: ignore[attr-defined]
    assert client.patch(f"{base}/{menu}", json={}, headers=HTMX).status_code == 404
    gone = delete(client, f"{base}/{first}")
    assert autofocused(gone.text) == ["bloc-ajout-exercice-type"]  # type: ignore[attr-defined]


def test_option_refusals(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    a = exercise(migrated_engine, "A")
    menu = templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=a, label="M")
    taken = client.post(
        f"/seances-types/{salle}/blocs/{menu}/options", json={"exercise_id": str(a)}, headers=HTMX
    )
    error = f'id="bloc-{menu}-option-ajout-erreur" class="field__error">{TEXT("catalog.error.option_taken")}'
    assert error in taken.text
    assert '<details class="slot__edit" open>' in taken.text
    assert TEXT("template.options_none_left") in taken.text
    fixed = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=a)
    assert (
        client.post(
            f"/seances-types/{salle}/blocs/{fixed}/options", json={"exercise_id": str(a)}, headers=HTMX
        ).status_code
        == 404
    )


def test_full_template_replaces_the_add_form(client: TestClient, migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    a = exercise(migrated_engine, "A")
    for _ in range(30):
        templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=a)
    html = client.get(f"/seances-types/{salle}", headers=PAGE).text
    assert TEXT("template.slots_full") in html and 'name="kind"' not in html


# --- target text


@pytest.mark.parametrize(
    ("target", "text"),
    [
        (Target(sets=4, reps_min=6, reps_max=8), f"4{X}6\u20138"),
        (Target(sets=3, reps_min=10, reps_max=10), f"3{X}10"),
        (Target(sets=3, reps_min=12, reps_max=12, duration_s=30), f"3{X}30{NBSP}s / 12"),
        (Target(sets=1, duration_s=1800), f"1{X}30{NBSP}min"),
        (Target(sets=3, reps_min=10, reps_max=10, note="par côté"), f"3{X}10 · par côté"),
        (
            Target(sets=3, reps_min=3, reps_max=3, duration_s=30, note="par côté"),
            f"3{X}30{NBSP}s / 3 · par côté",
        ),
        (Target(sets=5, distance_m=400), f"5{X}400{NBSP}m"),
        (Target(reps_min=8, reps_max=10), "8\u201310"),
        (Target(sets=4), f"Séries{NBSP}: 4"),
        (Target(note="par côté"), "par côté"),
        (Target(), ""),
        (Target(duration_s=4530), "1:15:30"),
        (Target(duration_s=4500, distance_m=5000), f"1{NBSP}h{NBSP}15 / 5{NBSP}km"),
    ],
)
def test_target_text(target: Target, text: str) -> None:
    assert Display(CATALOG_TEXTS).target(target) == text


def test_every_seed_target_has_a_text(migrated_engine: Engine) -> None:
    seed.seed_catalog(migrated_engine, USER)
    show = Display(CATALOG_TEXTS)
    texts = {
        show.target(slot.target)
        for summary in templates.list_templates(migrated_engine, USER)
        for slot in templates.get_detail(migrated_engine, USER, summary.id).slots
    }
    assert f"3{X}30{NBSP}s / 12" in texts and f"1{X}30{NBSP}min" in texts
    assert f"3{X}10 · par côté" in texts and all(texts)
