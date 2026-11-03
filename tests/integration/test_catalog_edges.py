"""Catalog edge cases on a migrated, unseeded database: enum key stability, measures kept, field
order at the ends, duplicates, units through the services, concurrent creation (D-032, D-054,
D-055). Known product bugs are strict xfails."""

from __future__ import annotations

import contextlib
import threading

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError, ValueInput
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.services import exercises, variables
from rack_overflow.services.exercises import ExerciseForm, FieldForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import db
from rack_overflow.storage import schema as s

USER = 1
OTHER = 2


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[str]:
    return [problem.code for problem in error.value.problems]


def new_exercise(engine: Engine, name: str, category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def enum_form(label: str, values: list[ValueInput]) -> VariableForm:
    return VariableForm(label, "enum", "setting", values=values)


def keys_labels(engine: Engine, variable_id: int) -> list[tuple[str, str]]:
    draft = variables.get_detail(engine, USER, variable_id).draft
    return [(value.key, value.label) for value in draft.enum_values or ()]


def store_setting(engine: Engine, exercise_id: int, variable_id: int, key: str) -> None:
    with engine.begin() as connection:
        session_id = connection.execute(
            sa.insert(s.session).values(
                user_id=USER,
                local_date="2026-11-03",
                time_zone="UTC",
                started_at="2026-11-03T18:00:00Z",
                location="gym",
                status="open",
            )
        ).inserted_primary_key[0]
        session_exercise_id = connection.execute(
            sa.insert(s.session_exercise).values(session_id=session_id, exercise_id=exercise_id, position=0)
        ).inserted_primary_key[0]
        connection.execute(
            sa.insert(s.exercise_setting).values(
                session_exercise_id=session_exercise_id, variable_id=variable_id, value_text=key
            )
        )


def only_variable_measure(engine: Engine, label: str) -> tuple[int, int]:
    """An exercise whose one measure is a `set`-scope variable (its reps field removed)."""
    exercise_id = new_exercise(engine, f"Gainage {label}", "bodyweight")
    variable_id = variables.create(engine, USER, VariableForm(label, "int", "set"))
    exercises.add_field(engine, USER, exercise_id, variable_id=variable_id)
    reps = exercises.get_detail(engine, USER, exercise_id).fields[0]
    assert reps.core_quantity == "reps"
    exercises.remove_field(engine, USER, exercise_id, reps.id)
    return exercise_id, variable_id


def measures(engine: Engine, exercise_id: int) -> list[str]:
    found = []
    for field in exercises.get_detail(engine, USER, exercise_id).fields:
        if field.core_quantity is not None:
            found.append(field.core_quantity)
        elif field.variable is not None and field.variable.draft.scope == "set":
            found.append(field.variable.draft.label)
    return found


# --- enum keys (D-032)


def test_relabel_and_reorder_keep_keys_and_history_resolves(migrated_engine: Engine) -> None:
    seat = variables.create(
        migrated_engine, USER, enum_form("Siège", [ValueInput("Bas"), ValueInput("Haut")])
    )
    press = new_exercise(migrated_engine, "Presse")
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    store_setting(migrated_engine, press, seat, "bas")
    form = enum_form("Siège", [ValueInput("Très bas", key="bas"), ValueInput("Très haut", key="haut")])
    variables.update(migrated_engine, USER, seat, form)
    assert keys_labels(migrated_engine, seat) == [("bas", "Très bas"), ("haut", "Très haut")]
    with migrated_engine.begin() as connection:
        stored = connection.execute(sa.select(s.exercise_setting.c.value_text)).scalar_one()
    assert stored == "bas"
    # a new value whose label slugs to a used key gets a suffix, never the used key
    form = enum_form(
        "Siège",
        [ValueInput("Très bas", key="bas"), ValueInput("Très haut", key="haut"), ValueInput("Bas")],
    )
    variables.update(migrated_engine, USER, seat, form)
    assert keys_labels(migrated_engine, seat)[-1] == ("bas_2", "Bas")


def test_relabel_keeps_an_enum_default_on_its_links(migrated_engine: Engine) -> None:
    seat = variables.create(migrated_engine, USER, enum_form("Siège", [ValueInput("1"), ValueInput("2")]))
    press = new_exercise(migrated_engine, "Presse")
    field_id = exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    exercises.update_field(migrated_engine, USER, press, field_id, FieldForm(default="2"))
    variables.update(
        migrated_engine,
        USER,
        seat,
        enum_form("Siège", [ValueInput("Un", key="1"), ValueInput("Deux", key="2")]),
    )
    field = exercises.get_detail(migrated_engine, USER, press).fields[-1]
    assert field.params.default_text == "2"


def test_removing_the_default_value_clears_the_default_of_its_links(migrated_engine: Engine) -> None:
    seat = variables.create(migrated_engine, USER, enum_form("Siège", [ValueInput("1"), ValueInput("2")]))
    press = new_exercise(migrated_engine, "Presse")
    field_id = exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    exercises.update_field(migrated_engine, USER, press, field_id, FieldForm(required=True, default="2"))
    variables.update(
        migrated_engine,
        USER,
        seat,
        enum_form("Siège", [ValueInput("1", key="1"), ValueInput("2", key="2", remove=True)]),
    )
    params = exercises.get_detail(migrated_engine, USER, press).fields[-1].params
    assert params.default_text is None and params.required


@pytest.mark.xfail(
    strict=True,
    reason="product bug: a removed enum key is handed out again to a new value (D-032 / design note §1: "
    "'A key is never reused'); enum_values only knows the keys still stored",
)
def test_a_removed_enum_key_is_never_reused(migrated_engine: Engine) -> None:
    seat = variables.create(migrated_engine, USER, enum_form("Siège", [ValueInput("1"), ValueInput("2")]))
    variables.update(
        migrated_engine,
        USER,
        seat,
        enum_form("Siège", [ValueInput("1", key="1"), ValueInput("2", key="2", remove=True)]),
    )
    variables.update(
        migrated_engine, USER, seat, enum_form("Siège", [ValueInput("1", key="1"), ValueInput("2")])
    )
    assert keys_labels(migrated_engine, seat)[-1][0] != "2"


def test_a_used_key_cannot_be_removed_even_when_soft_hidden(migrated_engine: Engine) -> None:
    seat = variables.create(migrated_engine, USER, enum_form("Siège", [ValueInput("1"), ValueInput("2")]))
    press = new_exercise(migrated_engine, "Presse")
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    store_setting(migrated_engine, press, seat, "2")
    with pytest.raises(CatalogError) as refused:
        variables.update(migrated_engine, USER, seat, enum_form("Siège", [ValueInput("1", key="1")]))
    assert "enum_value_in_use" in codes(refused)
    assert keys_labels(migrated_engine, seat) == [("1", "1"), ("2", "2")]


# --- at least one measure (D-054)


@pytest.mark.xfail(
    strict=True,
    reason="product bug: deleting a variable without values removes its links even when it is an "
    "exercise's last measure (services/variables.py delete; check_measures not applied)",
)
def test_deleting_a_variable_keeps_a_measure_on_every_exercise(migrated_engine: Engine) -> None:
    exercise_id, variable_id = only_variable_measure(migrated_engine, "Tenue")
    with contextlib.suppress(CatalogError):
        variables.delete(migrated_engine, USER, variable_id)
    assert measures(migrated_engine, exercise_id) != []


@pytest.mark.xfail(
    strict=True,
    reason="product bug: changing a variable's scope from set to setting (no values yet) leaves an "
    "exercise whose last measure it was without any measure (services/variables.py update)",
)
def test_scope_change_keeps_a_measure_on_every_exercise(migrated_engine: Engine) -> None:
    exercise_id, variable_id = only_variable_measure(migrated_engine, "Tenue")
    with contextlib.suppress(CatalogError):
        variables.update(migrated_engine, USER, variable_id, VariableForm("Tenue", "int", "setting"))
    assert measures(migrated_engine, exercise_id) != []


def test_removing_the_last_measure_is_refused_and_nothing_changes(migrated_engine: Engine) -> None:
    exercise_id, _ = only_variable_measure(migrated_engine, "Tenue")
    seat = variables.create(migrated_engine, USER, enum_form("Siège", [ValueInput("1")]))
    exercises.add_field(migrated_engine, USER, exercise_id, variable_id=seat)
    measure = exercises.get_detail(migrated_engine, USER, exercise_id).fields[0]
    with pytest.raises(CatalogError) as refused:
        exercises.remove_field(migrated_engine, USER, exercise_id, measure.id)
    assert codes(refused) == ["last_measure"]
    assert len(exercises.get_detail(migrated_engine, USER, exercise_id).fields) == 2


# --- field order


def positions(engine: Engine, exercise_id: int) -> list[tuple[int, str]]:
    return [
        (field.position, field.core_quantity or "")
        for field in exercises.get_detail(engine, USER, exercise_id).fields
    ]


def test_moves_at_the_ends_change_nothing(migrated_engine: Engine) -> None:
    run = new_exercise(migrated_engine, "Course", "cardio")
    exercises.add_field(migrated_engine, USER, run, core_quantity="reps")
    before = positions(migrated_engine, run)
    assert before == [(0, "duration"), (1, "distance"), (2, "reps")]
    fields = exercises.get_detail(migrated_engine, USER, run).fields
    assert exercises.move_field(migrated_engine, USER, run, fields[0].id, "up") == 0
    assert exercises.move_field(migrated_engine, USER, run, fields[-1].id, "down") == 2
    assert positions(migrated_engine, run) == before
    assert exercises.move_field(migrated_engine, USER, run, fields[-1].id, "up") == 1
    assert exercises.move_field(migrated_engine, USER, run, fields[-1].id, "up") == 0
    assert positions(migrated_engine, run) == [(0, "reps"), (1, "duration"), (2, "distance")]


def test_positions_stay_contiguous_after_removal_and_append(migrated_engine: Engine) -> None:
    run = new_exercise(migrated_engine, "Course", "cardio")
    exercises.add_field(migrated_engine, USER, run, core_quantity="reps")
    middle = exercises.get_detail(migrated_engine, USER, run).fields[1]
    exercises.remove_field(migrated_engine, USER, run, middle.id)
    exercises.add_field(migrated_engine, USER, run, core_quantity="weight")
    assert positions(migrated_engine, run) == [(0, "duration"), (1, "reps"), (2, "weight")]


def test_moving_a_single_field_is_a_no_op(migrated_engine: Engine) -> None:
    plank = new_exercise(migrated_engine, "Planche", "bodyweight")
    only = exercises.get_detail(migrated_engine, USER, plank).fields[0]
    assert exercises.move_field(migrated_engine, USER, plank, only.id, "up") == 0
    assert exercises.move_field(migrated_engine, USER, plank, only.id, "down") == 0


def test_bad_direction_and_foreign_field(migrated_engine: Engine) -> None:
    mine = new_exercise(migrated_engine, "Squat")
    theirs = new_exercise(migrated_engine, "Squat", user=OTHER)
    their_field = exercises.get_detail(migrated_engine, OTHER, theirs).fields[0]
    with pytest.raises(CatalogError):
        exercises.move_field(migrated_engine, USER, mine, their_field.id, "sideways")
    with pytest.raises(NotFoundError):
        exercises.move_field(migrated_engine, USER, mine, their_field.id, "up")
    with pytest.raises(NotFoundError):
        exercises.remove_field(migrated_engine, USER, mine, their_field.id)


def test_a_source_is_linked_once(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    with pytest.raises(CatalogError) as twice:
        exercises.add_field(migrated_engine, USER, squat, core_quantity="reps")
    assert codes(twice) == ["already_linked"]
    tempo = variables.create(migrated_engine, USER, VariableForm("Tempo", "int", "set"))
    exercises.add_field(migrated_engine, USER, squat, variable_id=tempo)
    with pytest.raises(CatalogError) as again:
        exercises.add_field(migrated_engine, USER, squat, variable_id=tempo)
    assert codes(again) == ["already_linked"]
    with pytest.raises(CatalogError):
        exercises.add_field(migrated_engine, USER, squat, core_quantity="calories")


def test_a_foreign_variable_cannot_be_linked(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    theirs = variables.create(migrated_engine, OTHER, VariableForm("Tempo", "int", "set"))
    with pytest.raises(CatalogError) as refused:
        exercises.add_field(migrated_engine, USER, squat, variable_id=theirs)
    assert codes(refused) == ["invalid_choice"]


# --- duplicates


def test_rename_to_own_case_variant_is_allowed_but_not_to_another(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "squat")
    new_exercise(migrated_engine, "Développé couché")
    exercises.update(migrated_engine, USER, squat, ExerciseForm("Squat", "strength", "gym"))
    assert exercises.get_detail(migrated_engine, USER, squat).draft.name == "Squat"
    for taken in ("developpe couche", "  DÉVELOPPÉ-COUCHÉ ", "Developpe   couche"):
        with pytest.raises(CatalogError) as refused:
            exercises.update(migrated_engine, USER, squat, ExerciseForm(taken, "strength", "gym"))
        assert codes(refused) == ["name_taken"]
    # another user's names do not count
    assert new_exercise(migrated_engine, "Squat", user=OTHER)


def test_alias_duplicates_and_shared_aliases(migrated_engine: Engine) -> None:
    bench = new_exercise(migrated_engine, "Développé couché (barre)")
    dumbbell = new_exercise(migrated_engine, "Développé couché haltères")
    exercises.add_alias(migrated_engine, USER, bench, "Bench press")
    for twin in ("bench press", "BENCH-PRESS", " Bénch  préss "):
        with pytest.raises(CatalogError) as refused:
            exercises.add_alias(migrated_engine, USER, bench, twin)
        assert codes(refused) == ["alias_taken"]
    with pytest.raises(CatalogError) as named:
        exercises.add_alias(migrated_engine, USER, bench, "developpe couche barre")
    assert codes(named) == ["alias_is_name"]
    with pytest.raises(CatalogError) as empty:
        exercises.add_alias(migrated_engine, USER, bench, " -- ")
    assert codes(empty) == ["required"]
    # the same alias on two exercises: search returns both
    exercises.add_alias(migrated_engine, USER, dumbbell, "Bench press")
    found = {e.id for e in exercises.search_exercises(migrated_engine, USER, "bench press")}
    assert found == {bench, dumbbell}


def test_removed_alias_can_be_added_again(migrated_engine: Engine) -> None:
    bench = new_exercise(migrated_engine, "Développé couché")
    exercises.add_alias(migrated_engine, USER, bench, "DC")
    alias_id = exercises.get_detail(migrated_engine, USER, bench).aliases[0].id
    assert exercises.remove_alias(migrated_engine, USER, bench, alias_id) == "DC"
    with pytest.raises(NotFoundError):
        exercises.remove_alias(migrated_engine, USER, bench, alias_id)
    exercises.add_alias(migrated_engine, USER, bench, "dc")
    assert [a.alias for a in exercises.get_detail(migrated_engine, USER, bench).aliases] == ["dc"]


def test_alias_of_another_exercise_cannot_be_removed_through_this_one(migrated_engine: Engine) -> None:
    bench = new_exercise(migrated_engine, "Développé couché")
    squat = new_exercise(migrated_engine, "Squat")
    exercises.add_alias(migrated_engine, USER, bench, "DC")
    alias_id = exercises.get_detail(migrated_engine, USER, bench).aliases[0].id
    with pytest.raises(NotFoundError):
        exercises.remove_alias(migrated_engine, USER, squat, alias_id)
    assert len(exercises.get_detail(migrated_engine, USER, bench).aliases) == 1


def test_concurrent_creation_of_the_same_name_keeps_one(migrated_engine: Engine, settings) -> None:
    engines = [db.create_engine(settings.database_path) for _ in range(4)]
    barrier = threading.Barrier(len(engines))
    outcomes: list[object] = []

    def create(engine: Engine, name: str) -> None:
        barrier.wait()
        try:
            outcomes.append(exercises.create(engine, USER, ExerciseForm(name, "strength", "gym")))
        except CatalogError as error:
            outcomes.append([p.code for p in error.problems])

    names = ["Squat", "squat", "SQUAT", "Squât"]
    threads = [threading.Thread(target=create, args=pair) for pair in zip(engines, names, strict=True)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for engine in engines:
        engine.dispose()
    assert sum(isinstance(outcome, int) for outcome in outcomes) == 1
    assert [o for o in outcomes if not isinstance(o, int)] == [["name_taken"]] * 3
    assert len(exercises.list_exercises(migrated_engine, USER)) == 1


# --- units through the services (D-055)


@pytest.mark.parametrize(
    ("quantity", "category", "typed", "stored", "shown_again"),
    [
        ("weight", "strength", "2,5", 2500, "2,5"),
        ("weight", "strength", "1.25", 1250, "1,25"),
        ("weight", "strength", "100,000", 100000, "100"),
        ("distance", "cardio", "5,2", 5200, "5,2"),
        ("distance", "cardio", "5,2 km", 5200, "5,2"),
        ("distance", "cardio", "400 m", 400, "400 m"),
        ("distance", "cardio", "0,999", 999, "999 m"),
        ("distance", "cardio", "1000m", 1000, "1"),
        ("duration", "cardio", "90", 90, "1:30"),
        ("duration", "cardio", "59:59", 3599, "59:59"),
        ("duration", "cardio", "60:00", 3600, "1:00:00"),
        ("duration", "cardio", "1:00:00", 3600, "1:00:00"),
    ],
)
def test_field_values_round_trip_through_display_units(
    migrated_engine: Engine, quantity: str, category: str, typed: str, stored: int, shown_again: str
) -> None:
    from rack_overflow.domain import units

    exercise_id = new_exercise(migrated_engine, "Test", category)
    field = next(
        f
        for f in exercises.get_detail(migrated_engine, USER, exercise_id).fields
        if f.core_quantity == quantity
    )
    exercises.update_field(migrated_engine, USER, exercise_id, field.id, FieldForm(increment=typed))
    saved = exercises.get_detail(migrated_engine, USER, exercise_id).fields[field.position]
    assert saved.params.increment == stored
    text = units.input_text(saved.kind.kind, stored)
    assert text == shown_again
    exercises.update_field(migrated_engine, USER, exercise_id, field.id, FieldForm(increment=text))
    assert (
        exercises.get_detail(migrated_engine, USER, exercise_id).fields[field.position].params.increment
        == stored
    )


@pytest.mark.parametrize(
    ("scale", "typed", "outcome"),
    [
        (1, "2,5", 25),
        (1, "2,55", "too_many_decimals"),
        (2, "2,5", 250),
        (3, "0,001", 1),
        (3, "-1", "negative"),
    ],
)
def test_decimal_variable_scale(migrated_engine: Engine, scale: int, typed: str, outcome: int | str) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    rpe = variables.create(migrated_engine, USER, VariableForm("RPE", "decimal", "set", scale=str(scale)))
    field_id = exercises.add_field(migrated_engine, USER, squat, variable_id=rpe)
    if isinstance(outcome, int):
        exercises.update_field(migrated_engine, USER, squat, field_id, FieldForm(default=typed))
        assert exercises.get_detail(migrated_engine, USER, squat).fields[-1].params.default_int == outcome
    else:
        with pytest.raises(CatalogError) as refused:
            exercises.update_field(migrated_engine, USER, squat, field_id, FieldForm(default=typed))
        assert codes(refused) == [outcome]


def test_refused_field_update_leaves_the_stored_parameters(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    weight = exercises.get_detail(migrated_engine, USER, squat).fields[1]
    before = weight.params
    for form in (
        FieldForm(increment="abc"),
        FieldForm(increment="0"),
        FieldForm(discrete_values="20 20"),
        FieldForm(discrete_values="16 20", default="18"),
        FieldForm(increment="2,5", discrete_values="16 20"),
        FieldForm(increment="1,2345"),
    ):
        with pytest.raises(CatalogError):
            exercises.update_field(migrated_engine, USER, squat, weight.id, form)
        assert exercises.get_detail(migrated_engine, USER, squat).fields[1].params == before


def test_decimal_scale_frozen_once_values_exist(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    rpe = variables.create(migrated_engine, USER, VariableForm("RPE", "decimal", "set", scale="1"))
    exercises.add_field(migrated_engine, USER, squat, variable_id=rpe)
    store_setting(migrated_engine, squat, rpe, "x")
    with pytest.raises(CatalogError) as refused:
        variables.update(migrated_engine, USER, rpe, VariableForm("RPE", "decimal", "set", scale="2"))
    assert codes(refused) == ["frozen_after_use"]
    variables.update(
        migrated_engine, USER, rpe, VariableForm("Effort perçu", "decimal", "set", scale="1", unit="/10")
    )
    assert variables.get_detail(migrated_engine, USER, rpe).draft.label == "Effort perçu"


def test_archived_variable_stays_listed_on_its_exercises(migrated_engine: Engine) -> None:
    squat = new_exercise(migrated_engine, "Squat")
    tempo = variables.create(migrated_engine, USER, VariableForm("Tempo", "int", "set"))
    exercises.add_field(migrated_engine, USER, squat, variable_id=tempo)
    variables.set_archived(migrated_engine, USER, tempo, exercises_now())
    detail = exercises.get_detail(migrated_engine, USER, squat)
    linked = [f.variable for f in detail.fields if f.variable is not None]
    assert len(linked) == 1 and linked[0].archived
    assert tempo not in {ref.id for ref in detail.addable_variables}
    assert variables.list_variables(migrated_engine, USER) == []
    assert [v.id for v in variables.list_variables(migrated_engine, USER, include_archived=True)] == [tempo]
    variables.set_archived(migrated_engine, USER, tempo, None)
    assert [v.id for v in variables.list_variables(migrated_engine, USER)] == [tempo]


def exercises_now():
    from datetime import UTC, datetime

    return datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def test_search_edges(migrated_engine: Engine) -> None:
    ids = [new_exercise(migrated_engine, name) for name in ("Squat", "Écarté", "abdos")]
    listed = [e.id for e in exercises.search_exercises(migrated_engine, USER, "")]
    assert listed == [ids[2], ids[1], ids[0]]  # by folded name
    assert [e.id for e in exercises.search_exercises(migrated_engine, USER, "   ")] == listed
    assert exercises.search_exercises(migrated_engine, USER, "zzzz") == []
    assert [e.id for e in exercises.search_exercises(migrated_engine, USER, "ECARTE")] == [ids[1]]
    exercises.set_archived(migrated_engine, USER, ids[0], exercises_now())
    assert exercises.search_exercises(migrated_engine, USER, "squat") == []
    archived = exercises.search_exercises(migrated_engine, USER, "squat", include_archived=True)
    assert [(e.id, e.archived) for e in archived] == [(ids[0], True)]
    assert exercises.search_exercises(migrated_engine, OTHER, "") == []
