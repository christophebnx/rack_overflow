"""Template services on a migrated, unseeded database: the L3 roadmap scenario and the rules of
D-058 / D-059 (names, order, archive, slots, menus, options, targets)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.templates import Target
from rack_overflow.services import exercises, templates
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import SlotForm, TemplateForm
from rack_overflow.storage import schema as s
from rack_overflow.storage.errors import NameTakenError

USER = 1
OTHER = 2
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[tuple[str, str]]:
    return [(problem.field, problem.code) for problem in error.value.problems]


def exercise(engine: Engine, name: str, pattern: str | None = None, user: int = USER) -> int:
    form = ExerciseForm(name=name, category="strength", location="gym", movement_pattern=pattern)
    return exercises.create(engine, user, form)


def template(engine: Engine, name: str = "Salle 1", location: str = "gym", user: int = USER) -> int:
    return templates.create(engine, user, TemplateForm(name, location))


def menu(engine: Engine, template_id: int, label: str, first: int) -> int:
    return templates.add_slot(engine, USER, template_id, kind="menu", exercise_id=first, label=label)


def fixed(engine: Engine, template_id: int, exercise_id: int) -> int:
    return templates.add_slot(engine, USER, template_id, kind="exercise", exercise_id=exercise_id)


def option_names(engine: Engine, template_id: int, slot_id: int) -> list[str]:
    slot = templates.get_detail(engine, USER, template_id).slot(slot_id)
    return [option.exercise.name for option in slot.options]


def test_roadmap_scenario(migrated_engine: Engine) -> None:
    rowing = exercise(migrated_engine, "Rowing barre", "Tirage horizontal")
    seated = exercise(migrated_engine, "Rowing assis", "Tirage horizontal")
    cable = exercise(migrated_engine, "Tirage poulie", "Tirage horizontal")
    squat = exercise(migrated_engine, "Squat", "Squat")
    salle = template(migrated_engine)
    pull = menu(migrated_engine, salle, "Tirage", rowing)
    templates.add_option(migrated_engine, USER, salle, pull, seated)
    templates.add_option(migrated_engine, USER, salle, pull, cable)
    legs = fixed(migrated_engine, salle, squat)
    assert option_names(migrated_engine, salle, pull) == ["Rowing barre", "Rowing assis", "Tirage poulie"]

    assert templates.move_slot(migrated_engine, USER, salle, legs, "up") == 0
    detail = templates.get_detail(migrated_engine, USER, salle)
    assert [(slot.name, slot.position, slot.kind) for slot in detail.slots] == [
        ("Squat", 0, "exercise"),
        ("Tirage", 1, "menu"),
    ]
    third = detail.slot(pull).options[2].id
    assert templates.move_option(migrated_engine, USER, salle, pull, third, "up") == 1
    assert option_names(migrated_engine, salle, pull) == ["Rowing barre", "Tirage poulie", "Rowing assis"]

    other = template(migrated_engine, "Maison", "home")
    templates.set_archived(migrated_engine, USER, salle, NOW)
    listed = templates.list_templates(migrated_engine, USER)
    assert [t.draft.name for t in listed] == ["Maison"]
    archived = templates.list_templates(migrated_engine, USER, include_archived=True)
    assert [(t.draft.name, t.archived, t.slot_count) for t in archived] == [
        ("Salle 1", True, 2),
        ("Maison", False, 0),
    ]
    assert templates.get_detail(migrated_engine, USER, salle).archived
    templates.set_archived(migrated_engine, USER, salle, None)
    assert [t.id for t in templates.list_templates(migrated_engine, USER)] == [other, salle]
    assert len(templates.get_detail(migrated_engine, USER, salle).slots) == 2


def test_names_are_unique_after_folding_archived_included(migrated_engine: Engine) -> None:
    first = template(migrated_engine, "Salle A")
    templates.set_archived(migrated_engine, USER, first, NOW)
    for name in ("salle a", "SALLE  A", "Sallé-A"):
        with pytest.raises(CatalogError) as refused:
            template(migrated_engine, name)
        assert codes(refused) == [("name", "template_name_taken")]
    second = template(migrated_engine, "Salle B")
    with pytest.raises(CatalogError):
        templates.update(migrated_engine, USER, second, TemplateForm("SALLE A", "gym"))
    assert templates.update(migrated_engine, USER, second, TemplateForm("salle b", "both")).name == "salle b"
    assert template(migrated_engine, "Salle A", user=OTHER) > 0


def test_create_refusals_report_every_problem(migrated_engine: Engine) -> None:
    with pytest.raises(CatalogError) as refused:
        templates.create(migrated_engine, USER, TemplateForm("", "office"))
    assert codes(refused) == [("name", "required"), ("location", "invalid_choice")]


def _taken(*args: Any, **kwargs: Any) -> Any:
    raise NameTakenError("race")


def test_name_race_is_template_name_taken(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    salle = template(migrated_engine)
    monkeypatch.setattr(templates.queries, "insert", _taken)
    with pytest.raises(CatalogError) as refused:
        template(migrated_engine, "Autre")
    assert codes(refused) == [("name", "template_name_taken")]
    monkeypatch.setattr(templates.queries, "update", _taken)
    with pytest.raises(CatalogError) as refused:
        templates.update(migrated_engine, USER, salle, TemplateForm("Autre", "gym"))
    assert codes(refused) == [("name", "template_name_taken")]


def test_option_race_is_option_taken(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    salle = template(migrated_engine)
    pull = menu(migrated_engine, salle, "Tirage", exercise(migrated_engine, "A"))
    monkeypatch.setattr(templates.queries, "insert_option", _taken)
    with pytest.raises(CatalogError) as refused:
        templates.add_option(migrated_engine, USER, salle, pull, exercise(migrated_engine, "B"))
    assert codes(refused) == [("exercise_id", "option_taken")]


def test_the_unique_index_backs_the_name_rule(migrated_engine: Engine) -> None:
    template(migrated_engine, "Salle A")
    from rack_overflow.domain.templates import TemplateDraft
    from rack_overflow.storage import templates as queries

    with migrated_engine.begin() as connection, pytest.raises(NameTakenError):
        queries.insert(connection, USER, TemplateDraft("Salle A", "gym"), 5)


def test_move_among_non_archived_templates(migrated_engine: Engine) -> None:
    a, b, c = (template(migrated_engine, name) for name in "ABC")
    templates.set_archived(migrated_engine, USER, b, NOW)
    assert templates.move(migrated_engine, USER, c, "up") == 0
    assert [t.id for t in templates.list_templates(migrated_engine, USER)] == [c, a]
    assert templates.move(migrated_engine, USER, c, "up") == 0
    assert templates.move(migrated_engine, USER, a, "down") == 1
    with pytest.raises(NotFoundError):
        templates.move(migrated_engine, USER, b, "up")
    with pytest.raises(CatalogError):
        templates.move(migrated_engine, USER, a, "sideways")
    templates.set_archived(migrated_engine, USER, b, None)
    assert [t.id for t in templates.list_templates(migrated_engine, USER)] == [c, a, b]


def test_restoring_an_active_template_changes_nothing(migrated_engine: Engine) -> None:
    a, b = template(migrated_engine, "A"), template(migrated_engine, "B")
    templates.set_archived(migrated_engine, USER, a, None)
    assert [t.id for t in templates.list_templates(migrated_engine, USER)] == [a, b]


def test_add_slot_refusals(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    archived = exercise(migrated_engine, "Vieux")
    exercises.set_archived(migrated_engine, USER, archived, NOW)
    foreign = exercise(migrated_engine, "Autre", user=OTHER)
    for exercise_id in (archived, foreign, 999):
        with pytest.raises(CatalogError) as refused:
            fixed(migrated_engine, salle, exercise_id)
        assert codes(refused) == [("exercise_id", "exercise_unavailable")]
    with pytest.raises(CatalogError) as refused:
        templates.add_slot(migrated_engine, USER, salle, kind="menu", exercise_id=None, label=" ")
    assert codes(refused) == [("label", "required"), ("exercise_id", "required")]
    with pytest.raises(CatalogError) as refused:
        templates.add_slot(migrated_engine, USER, salle, kind="superset", exercise_id=None)
    assert codes(refused) == [("kind", "invalid_choice")]
    assert templates.get_detail(migrated_engine, USER, salle).slots == ()


def test_at_most_thirty_slots(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    squat = exercise(migrated_engine, "Squat")
    for _ in range(30):
        fixed(migrated_engine, salle, squat)
    with pytest.raises(CatalogError) as refused:
        fixed(migrated_engine, salle, squat)
    assert codes(refused) == [("kind", "too_many_slots")]
    first = templates.get_detail(migrated_engine, USER, salle).slots[0].id
    templates.remove_slot(migrated_engine, USER, salle, first, NOW)
    fixed(migrated_engine, salle, squat)


def test_options_rules(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    ids = [exercise(migrated_engine, f"E{n}") for n in range(13)]
    pull = menu(migrated_engine, salle, "Tirage", ids[0])
    with pytest.raises(CatalogError) as refused:
        templates.add_option(migrated_engine, USER, salle, pull, ids[0])
    assert codes(refused) == [("exercise_id", "option_taken")]
    only = templates.get_detail(migrated_engine, USER, salle).slot(pull).options[0].id
    with pytest.raises(CatalogError) as refused:
        templates.remove_option(migrated_engine, USER, salle, pull, only)
    assert codes(refused) == [("option", "last_option")]
    for exercise_id in ids[1:12]:
        templates.add_option(migrated_engine, USER, salle, pull, exercise_id)
    with pytest.raises(CatalogError) as refused:
        templates.add_option(migrated_engine, USER, salle, pull, ids[12])
    assert codes(refused) == [("exercise_id", "too_many_options")]
    options = templates.get_detail(migrated_engine, USER, salle).slot(pull).options
    templates.remove_option(migrated_engine, USER, salle, pull, options[0].id)
    with migrated_engine.begin() as connection:
        rows = connection.execute(
            sa.select(s.template_slot_option.c.id, s.template_slot_option.c.position).order_by(
                s.template_slot_option.c.position
            )
        ).all()
    assert [row.id for row in rows] == [option.id for option in options[1:]]
    assert [row.position for row in rows] == list(range(11))


def test_option_on_a_fixed_slot_or_unknown_option_is_not_found(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    squat = exercise(migrated_engine, "Squat")
    slot = fixed(migrated_engine, salle, squat)
    with pytest.raises(NotFoundError):
        templates.add_option(migrated_engine, USER, salle, slot, exercise(migrated_engine, "B"))
    pull = menu(migrated_engine, salle, "Tirage", squat)
    with pytest.raises(NotFoundError):
        templates.move_option(migrated_engine, USER, salle, pull, 999, "up")
    with pytest.raises(NotFoundError):
        templates.remove_option(migrated_engine, USER, salle, pull, 999)


def test_archived_exercise_is_kept_and_flagged(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    plank = exercise(migrated_engine, "Planche", "Gainage")
    crunch = exercise(migrated_engine, "Crunch", "Gainage")
    slot = fixed(migrated_engine, salle, plank)
    core = menu(migrated_engine, salle, "Gainage", plank)
    templates.add_option(migrated_engine, USER, salle, core, crunch)
    exercises.set_archived(migrated_engine, USER, plank, NOW)
    detail = templates.get_detail(migrated_engine, USER, salle)
    assert detail.slot(slot).exercise is not None and detail.slot(slot).exercise.archived
    assert detail.slot(slot).skipped and not detail.slot(core).skipped
    assert [o.exercise.archived for o in detail.slot(core).options] == [True, False]
    assert [ref.name for ref in detail.available] == ["Crunch"]
    exercises.set_archived(migrated_engine, USER, crunch, NOW)
    assert templates.get_detail(migrated_engine, USER, salle).slot(core).skipped

    # the current archived exercise is kept when saving a target; a newly chosen archived one is not
    saved = templates.update_slot(migrated_engine, USER, salle, slot, SlotForm(exercise_id=plank, sets="3"))
    assert saved.target == Target(sets=3) and saved.exercise is not None and saved.exercise.id == plank
    other_slot = fixed(migrated_engine, salle, exercise(migrated_engine, "Squat"))
    with pytest.raises(CatalogError) as refused:
        templates.update_slot(migrated_engine, USER, salle, other_slot, SlotForm(exercise_id=plank))
    assert codes(refused) == [("exercise_id", "exercise_unavailable")]


def test_update_slot_exercise_label_and_target(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    squat, press = exercise(migrated_engine, "Squat"), exercise(migrated_engine, "Presse")
    slot = fixed(migrated_engine, salle, squat)
    pull = menu(migrated_engine, salle, "Tirage", squat)
    form = SlotForm(exercise_id=press, sets="4", reps="6-8", label="ignored")
    saved = templates.update_slot(migrated_engine, USER, salle, slot, form)
    assert saved.name == "Presse" and saved.target == Target(sets=4, reps_min=6, reps_max=8)
    form = SlotForm(label=" Tirage horizontal ", duration="0:30", reps="12", sets="3", note="par côté")
    saved = templates.update_slot(migrated_engine, USER, salle, pull, form)
    assert saved.label == "Tirage horizontal"
    assert saved.target == Target(3, 12, 12, 30, None, "par côté")
    cleared = templates.update_slot(migrated_engine, USER, salle, pull, SlotForm(label="Tirage"))
    assert cleared.target.is_empty
    with pytest.raises(CatalogError) as refused:
        templates.update_slot(
            migrated_engine, USER, salle, pull, SlotForm(label="", sets="0", reps="9-3", note="x" * 41)
        )
    assert codes(refused) == [
        ("label", "required"),
        ("sets", "target_sets_range"),
        ("reps", "target_reps_order"),
        ("note", "too_long"),
    ]
    assert templates.get_detail(migrated_engine, USER, salle).slot(pull).label == "Tirage"


def test_remove_slot_is_a_soft_delete(migrated_engine: Engine) -> None:
    salle = template(migrated_engine)
    squat = exercise(migrated_engine, "Squat")
    first = fixed(migrated_engine, salle, squat)
    pull = menu(migrated_engine, salle, "Tirage", squat)
    last = fixed(migrated_engine, salle, squat)
    templates.remove_slot(migrated_engine, USER, salle, pull, NOW)
    detail = templates.get_detail(migrated_engine, USER, salle)
    assert [(slot.id, slot.position) for slot in detail.slots] == [(first, 0), (last, 1)]
    with migrated_engine.begin() as connection:
        removed = connection.execute(sa.select(s.template_slot).where(s.template_slot.c.id == pull)).one()
        assert removed.deleted_at == "2026-11-03T18:04:05Z"
        options = connection.execute(sa.select(sa.func.count()).select_from(s.template_slot_option))
        assert options.scalar_one() == 1
        session_id = connection.execute(
            sa.insert(s.session).values(
                user_id=USER,
                local_date="2026-11-03",
                time_zone="Europe/Paris",
                started_at="2026-11-03T18:00:00Z",
                location="gym",
                status="open",
                template_id=salle,
            )
        ).inserted_primary_key[0]
        connection.execute(
            sa.insert(s.session_exercise).values(
                session_id=session_id, exercise_id=squat, template_slot_id=pull, position=0
            )
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    for action in (
        lambda: templates.remove_slot(migrated_engine, USER, salle, pull, NOW),
        lambda: templates.move_slot(migrated_engine, USER, salle, pull, "up"),
        lambda: templates.update_slot(migrated_engine, USER, salle, pull, SlotForm(label="X")),
        lambda: templates.add_option(migrated_engine, USER, salle, pull, squat),
        lambda: templates.get_detail(migrated_engine, USER, salle).slot(pull),
    ):
        with pytest.raises(NotFoundError):
            action()


def test_foreign_and_unknown_ids_are_not_found(migrated_engine: Engine) -> None:
    mine = template(migrated_engine)
    theirs = template(migrated_engine, user=OTHER)
    their_exercise = exercise(migrated_engine, "Squat", user=OTHER)
    their_slot = templates.add_slot(
        migrated_engine, OTHER, theirs, kind="exercise", exercise_id=their_exercise
    )
    for action in (
        lambda: templates.get_detail(migrated_engine, USER, theirs),
        lambda: templates.update(migrated_engine, USER, theirs, TemplateForm("X", "gym")),
        lambda: templates.set_archived(migrated_engine, USER, theirs, NOW),
        lambda: templates.move(migrated_engine, USER, 999, "up"),
        lambda: templates.add_slot(migrated_engine, USER, theirs, kind="exercise", exercise_id=1),
        lambda: templates.move_slot(migrated_engine, USER, mine, their_slot, "up"),
        lambda: templates.remove_slot(migrated_engine, USER, mine, their_slot, NOW),
        lambda: templates.update_slot(migrated_engine, USER, mine, their_slot, SlotForm()),
    ):
        with pytest.raises(NotFoundError):
            action()


def test_groups_by_movement_pattern(migrated_engine: Engine) -> None:
    exercise(migrated_engine, "Squat", "Squat")
    exercise(migrated_engine, "Rowing barre", "Tirage horizontal")
    exercise(migrated_engine, "Gainage libre")
    exercise(migrated_engine, "Rowing assis", "tirage  HORIZONTAL")
    exercise(migrated_engine, "Fentes", "Jambes")
    salle = template(migrated_engine)
    detail = templates.get_detail(migrated_engine, USER, salle)
    groups = [(g.movement_pattern, [e.name for e in g.exercises]) for g in detail.groups()]
    assert groups == [
        ("Jambes", ["Fentes"]),
        ("Squat", ["Squat"]),
        ("Tirage horizontal", ["Rowing assis", "Rowing barre"]),
        (None, ["Gainage libre"]),
    ]
    pull = menu(migrated_engine, salle, "Tirage horizontal", detail.available[1].id)
    slot = templates.get_detail(migrated_engine, USER, salle).slot(pull)
    option_groups = templates.get_detail(migrated_engine, USER, salle).option_groups(slot)
    assert [(g.movement_pattern, [e.name for e in g.exercises]) for g in option_groups] == [
        ("Tirage horizontal", ["Rowing assis"]),
        ("Jambes", ["Fentes"]),
        ("Squat", ["Squat"]),
        (None, ["Gainage libre"]),
    ]
    assert detail.patterns == ("Squat", "Tirage horizontal", "Jambes")
