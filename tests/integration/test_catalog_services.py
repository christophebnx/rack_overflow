"""Catalog services on a migrated, unseeded database: the L2 roadmap scenarios (D-030 to D-032, D-054)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError, EnumValue, FieldParams, ValueInput
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.services import exercises, variables
from rack_overflow.services.exercises import ExerciseForm, FieldForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import app_settings, migrate
from rack_overflow.storage import schema as s

USER = 1
OTHER = 2
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[str]:
    return [problem.code for problem in error.value.problems]


def new_exercise(
    engine: Engine, name: str, category: str = "strength", user: int = USER, **extra: str
) -> int:
    return exercises.create(engine, user, ExerciseForm(name=name, category=category, location="gym", **extra))


def seat_form(label: str = "Siège") -> VariableForm:
    return VariableForm(label, "enum", "setting", values=[ValueInput(str(n)) for n in range(1, 11)])


def store_session_exercise(engine: Engine, exercise_id: int) -> int:
    with engine.begin() as connection:
        session_id = connection.execute(
            sa.insert(s.session).values(
                user_id=USER,
                local_date="2026-11-03",
                time_zone="Europe/Paris",
                started_at="2026-11-03T18:00:00Z",
                location="gym",
                status="open",
            )
        ).inserted_primary_key[0]
        return connection.execute(
            sa.insert(s.session_exercise).values(session_id=session_id, exercise_id=exercise_id, position=0)
        ).inserted_primary_key[0]


def store_setting(engine: Engine, exercise_id: int, variable_id: int, key: str) -> None:
    session_exercise_id = store_session_exercise(engine, exercise_id)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(s.exercise_setting).values(
                session_exercise_id=session_exercise_id, variable_id=variable_id, value_text=key
            )
        )


def row_counts(engine: Engine) -> dict[str, int]:
    with engine.begin() as connection:
        return {
            table.name: connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in s.metadata.sorted_tables
        }


def test_seat_setting_shared_by_two_exercises_without_migration(migrated_engine: Engine) -> None:
    revision = migrate.current_revision(migrated_engine)
    press = new_exercise(migrated_engine, "Presse à cuisses")
    bench = new_exercise(migrated_engine, "Développé couché machine")
    seat = variables.create(migrated_engine, USER, seat_form())
    for exercise_id in (press, bench):
        exercises.add_field(migrated_engine, USER, exercise_id, variable_id=seat)
    variables.update(
        migrated_engine,
        USER,
        seat,
        VariableForm(
            "Hauteur du siège",
            "enum",
            "setting",
            values=[ValueInput(str(n), key=str(n)) for n in range(1, 11)],
        ),
    )
    for exercise_id in (press, bench):
        detail = exercises.get_detail(migrated_engine, USER, exercise_id)
        labels = [f.variable.draft.label for f in detail.fields if f.variable is not None]
        assert labels == ["Hauteur du siège"]
    linked = variables.get_detail(migrated_engine, USER, seat).linked
    assert [link.name for link in linked] == ["Développé couché machine", "Presse à cuisses"]
    assert migrate.current_revision(migrated_engine) == revision


def test_kettlebell_swing_with_discrete_loads(migrated_engine: Engine) -> None:
    swing = new_exercise(migrated_engine, "Kettlebell swing", "kettlebell")
    detail = exercises.get_detail(migrated_engine, USER, swing)
    weight = next(f for f in detail.fields if f.core_quantity == "weight")
    params = exercises.update_field(
        migrated_engine,
        USER,
        swing,
        weight.id,
        FieldForm(required=True, discrete_values="16 20 24", default="20"),
    )
    assert params == FieldParams(True, None, (16000, 20000, 24000), 20000, None)
    stored = exercises.get_detail(migrated_engine, USER, swing).fields
    assert [(f.core_quantity, f.params.discrete_values) for f in stored] == [
        ("reps", None),
        ("weight", (16000, 20000, 24000)),
    ]


def test_bike_with_duration_distance_and_a_resistance_measure(migrated_engine: Engine) -> None:
    bike = new_exercise(migrated_engine, "Vélo", "cardio")
    resistance = variables.create(
        migrated_engine, USER, VariableForm("Résistance", "int", "set", unit="niveau")
    )
    exercises.add_field(migrated_engine, USER, bike, variable_id=resistance)
    fields = exercises.get_detail(migrated_engine, USER, bike).fields
    assert [(f.core_quantity, f.variable.draft.label if f.variable else None) for f in fields] == [
        ("duration", None),
        ("distance", None),
        (None, "Résistance"),
    ]
    assert [f.params.required for f in fields] == [True, False, False]
    assert [f.position for f in fields] == [0, 1, 2]


def test_create_keeps_first_seen_spelling_and_lists_suggestions(migrated_engine: Engine) -> None:
    new_exercise(migrated_engine, "Rowing", movement_pattern="Tirage horizontal", equipment="Barre")
    second = new_exercise(
        migrated_engine, "Tirage poulie", movement_pattern="tirage  HORIZONTAL", equipment="poulie"
    )
    detail = exercises.get_detail(migrated_engine, USER, second)
    assert detail.draft.movement_pattern == "Tirage horizontal"
    suggestions = exercises.suggestions(migrated_engine, USER)
    assert suggestions.movement_patterns == ("Tirage horizontal",)
    assert suggestions.equipments == ("Barre", "poulie")


def test_names_are_unique_ignoring_case_and_accents(migrated_engine: Engine) -> None:
    first = new_exercise(migrated_engine, "Développé couché")
    with pytest.raises(CatalogError) as caught:
        new_exercise(migrated_engine, "DEVELOPPE couche")
    assert codes(caught) == ["name_taken"]
    other = new_exercise(migrated_engine, "Squat")
    with pytest.raises(CatalogError):
        exercises.update(migrated_engine, USER, other, ExerciseForm("développé couché", "strength", "gym"))
    exercises.update(migrated_engine, USER, first, ExerciseForm("Développé Couché", "strength", "both"))
    assert exercises.get_detail(migrated_engine, USER, first).draft.location == "both"
    new_exercise(migrated_engine, "Développé couché", user=OTHER)  # per user


def test_archived_names_stay_taken_and_archive_changes_nothing_else(migrated_engine: Engine) -> None:
    swing = new_exercise(migrated_engine, "Kettlebell swing", "kettlebell")
    exercises.add_alias(migrated_engine, USER, swing, "KB swing")
    store_session_exercise(migrated_engine, swing)
    before = row_counts(migrated_engine)
    exercises.set_archived(migrated_engine, USER, swing, NOW)
    assert row_counts(migrated_engine) == before
    detail = exercises.get_detail(migrated_engine, USER, swing)
    assert detail.archived and detail.has_history
    assert exercises.list_exercises(migrated_engine, USER) == []
    assert [e.id for e in exercises.list_exercises(migrated_engine, USER, include_archived=True)] == [swing]
    assert exercises.search_exercises(migrated_engine, USER, "swing") == []
    assert [e.id for e in exercises.search_exercises(migrated_engine, USER, "kb", include_archived=True)] == [
        swing
    ]
    with pytest.raises(CatalogError):
        new_exercise(migrated_engine, "kettlebell swing")
    exercises.set_archived(migrated_engine, USER, swing, None)
    assert not exercises.get_detail(migrated_engine, USER, swing).archived


def test_search_by_alias_initials_and_name(migrated_engine: Engine) -> None:
    bench = new_exercise(migrated_engine, "Développé couché (barre)")
    new_exercise(migrated_engine, "Squat au rack (barre)")
    exercises.add_alias(migrated_engine, USER, bench, "Bench press")
    for query in ("DC", "bench", "developpe"):
        assert exercises.search_exercises(migrated_engine, USER, query)[0].id == bench
    assert [e.draft.name for e in exercises.search_exercises(migrated_engine, USER, "")] == [
        "Développé couché (barre)",
        "Squat au rack (barre)",
    ]


def test_list_sorted_by_folded_name(migrated_engine: Engine) -> None:
    for name in ("Rameur", "élévations", "Abdos"):
        new_exercise(migrated_engine, name)
    assert [e.draft.name for e in exercises.list_exercises(migrated_engine, USER)] == [
        "Abdos",
        "élévations",
        "Rameur",
    ]


def test_variable_archive_and_delete_before_values(migrated_engine: Engine) -> None:
    press = new_exercise(migrated_engine, "Presse")
    seat = variables.create(migrated_engine, USER, seat_form())
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    variables.set_archived(migrated_engine, USER, seat, NOW)
    assert variables.list_variables(migrated_engine, USER) == []
    summary = variables.list_variables(migrated_engine, USER, include_archived=True)[0]
    assert summary.archived and summary.linked_count == 1
    detail = exercises.get_detail(migrated_engine, USER, press)
    assert detail.fields[-1].variable is not None and detail.fields[-1].variable.archived
    assert detail.addable_variables == ()
    with pytest.raises(CatalogError) as caught:
        exercises.add_field(migrated_engine, USER, new_exercise(migrated_engine, "Autre"), variable_id=seat)
    assert codes(caught) == ["invalid_choice"]
    variables.set_archived(migrated_engine, USER, seat, None)
    variables.delete(migrated_engine, USER, seat)
    assert [f.core_quantity for f in exercises.get_detail(migrated_engine, USER, press).fields] == [
        "reps",
        "weight",
    ]
    with pytest.raises(NotFoundError):
        variables.get_detail(migrated_engine, USER, seat)


def test_variable_with_values_cannot_be_deleted_and_freezes(migrated_engine: Engine) -> None:
    press = new_exercise(migrated_engine, "Presse")
    seat = variables.create(migrated_engine, USER, seat_form())
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    store_setting(migrated_engine, press, seat, "3")
    detail = variables.get_detail(migrated_engine, USER, seat)
    assert detail.has_values and detail.used_enum_keys == {"3"}
    with pytest.raises(CatalogError) as caught:
        variables.delete(migrated_engine, USER, seat)
    assert codes(caught) == ["variable_in_use"]
    with pytest.raises(CatalogError) as caught:
        variables.update(migrated_engine, USER, seat, VariableForm("Siège", "int", "setting"))
    assert codes(caught) == ["frozen_after_use"]
    rows = [ValueInput(str(n), key=str(n), remove=n == 3) for n in range(1, 11)]
    with pytest.raises(CatalogError) as caught:
        variables.update(migrated_engine, USER, seat, VariableForm("Siège", "enum", "setting", values=rows))
    assert codes(caught) == ["enum_value_in_use"]
    rows = [ValueInput(str(n), key=str(n), remove=n == 10) for n in range(1, 11)] + [ValueInput("11")]
    draft = variables.update(
        migrated_engine, USER, seat, VariableForm("Siège", "enum", "setting", values=rows)
    )
    assert draft.enum_values is not None and draft.enum_values[-1] == EnumValue("11", "11")
    assert len(draft.enum_values) == 10


def test_type_change_clears_incompatible_field_parameters(migrated_engine: Engine) -> None:
    press = new_exercise(migrated_engine, "Presse")
    load = variables.create(migrated_engine, USER, VariableForm("Lest", "weight", "set"))
    field_id = exercises.add_field(migrated_engine, USER, press, variable_id=load)
    exercises.update_field(
        migrated_engine, USER, press, field_id, FieldForm(True, increment="2,5", default="10")
    )
    variables.update(
        migrated_engine, USER, load, VariableForm("Lest", "enum", "set", values=[ValueInput("A")])
    )
    field = next(f for f in exercises.get_detail(migrated_engine, USER, press).fields if f.id == field_id)
    assert field.params == FieldParams(required=True)
    assert field.kind.kind == "enum"


def test_variable_codes_are_derived_and_never_shown_twice(migrated_engine: Engine) -> None:
    first = variables.create(migrated_engine, USER, VariableForm("Siège", "int", "setting"))
    second = variables.create(migrated_engine, USER, VariableForm("siege", "int", "setting"))
    with migrated_engine.begin() as connection:
        found = dict(connection.execute(sa.select(s.variable.c.id, s.variable.c.code)).all())
    assert found == {first: "siege", second: "siege_2"}


def test_remove_field_keeps_values_and_the_last_measure(migrated_engine: Engine) -> None:
    press = new_exercise(migrated_engine, "Presse", "bodyweight")
    seat = variables.create(migrated_engine, USER, seat_form())
    seat_field = exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    store_setting(migrated_engine, press, seat, "2")
    reps = exercises.get_detail(migrated_engine, USER, press).fields[0]
    with pytest.raises(CatalogError) as caught:
        exercises.remove_field(migrated_engine, USER, press, reps.id)
    assert codes(caught) == ["last_measure"]
    exercises.remove_field(migrated_engine, USER, press, seat_field)
    assert [f.id for f in exercises.get_detail(migrated_engine, USER, press).fields] == [reps.id]
    assert row_counts(migrated_engine)["exercise_setting"] == 1
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    with pytest.raises(CatalogError) as caught:
        exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    assert codes(caught) == ["already_linked"]
    with pytest.raises(CatalogError) as caught:
        exercises.add_field(migrated_engine, USER, press, core_quantity="reps")
    assert codes(caught) == ["already_linked"]


def test_move_field_swaps_and_renumbers(migrated_engine: Engine) -> None:
    bike = new_exercise(migrated_engine, "Vélo", "cardio")
    exercises.add_field(migrated_engine, USER, bike, core_quantity="reps")
    duration, distance, reps = (f.id for f in exercises.get_detail(migrated_engine, USER, bike).fields)
    assert exercises.move_field(migrated_engine, USER, bike, reps, "up") == 1
    assert exercises.move_field(migrated_engine, USER, bike, duration, "up") == 0
    assert exercises.move_field(migrated_engine, USER, bike, distance, "down") == 2
    fields = exercises.get_detail(migrated_engine, USER, bike).fields
    assert [(f.id, f.position) for f in fields] == [(duration, 0), (reps, 1), (distance, 2)]
    with pytest.raises(CatalogError):
        exercises.move_field(migrated_engine, USER, bike, reps, "left")


def test_aliases(migrated_engine: Engine) -> None:
    bench = new_exercise(migrated_engine, "Développé couché (barre)")
    other = new_exercise(migrated_engine, "Développé couché haltères")
    assert exercises.add_alias(migrated_engine, USER, bench, " DC ") == "DC"
    exercises.add_alias(migrated_engine, USER, other, "DC")  # same alias on two exercises
    with pytest.raises(CatalogError) as caught:
        exercises.add_alias(migrated_engine, USER, bench, " dc")
    assert codes(caught) == ["alias_taken"]
    alias = exercises.get_detail(migrated_engine, USER, bench).aliases[0]
    assert exercises.remove_alias(migrated_engine, USER, bench, alias.id) == "DC"
    with pytest.raises(NotFoundError):
        exercises.remove_alias(migrated_engine, USER, bench, alias.id)


def test_foreign_rows_are_not_found(migrated_engine: Engine) -> None:
    mine = new_exercise(migrated_engine, "Squat")
    theirs = new_exercise(migrated_engine, "Squat", user=OTHER)
    their_var = variables.create(migrated_engine, OTHER, seat_form())
    with pytest.raises(NotFoundError):
        exercises.get_detail(migrated_engine, USER, theirs)
    with pytest.raises(NotFoundError):
        variables.set_archived(migrated_engine, USER, their_var, NOW)
    with pytest.raises(CatalogError):
        exercises.add_field(migrated_engine, USER, mine, variable_id=their_var)
    their_field = exercises.get_detail(migrated_engine, OTHER, theirs).fields[0].id
    with pytest.raises(NotFoundError):
        exercises.remove_field(migrated_engine, USER, mine, their_field)
    with pytest.raises(NotFoundError):
        variables.delete(migrated_engine, USER, 999)
    assert exercises.search_exercises(migrated_engine, USER, "squat")[0].id == mine


def test_addable_sources(migrated_engine: Engine) -> None:
    press = new_exercise(migrated_engine, "Presse")
    zeta = variables.create(migrated_engine, USER, VariableForm("Zèle", "int", "set"))
    alpha = variables.create(migrated_engine, USER, VariableForm("Angle", "int", "setting"))
    detail = exercises.get_detail(migrated_engine, USER, press)
    assert detail.addable_quantities == ("duration", "distance")
    assert [ref.id for ref in detail.addable_variables] == [alpha, zeta]
    with pytest.raises(CatalogError) as caught:
        exercises.add_field(migrated_engine, USER, press)
    assert codes(caught) == ["required"]
    with pytest.raises(CatalogError):
        exercises.add_field(migrated_engine, USER, press, core_quantity="speed")


def test_app_settings_get_and_put(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        assert app_settings.get(connection, USER, "seed.version") is None
        app_settings.put(connection, USER, "seed.version", "1")
        app_settings.put(connection, USER, "seed.version", "2")
        app_settings.put(connection, OTHER, "seed.version", "7")
        assert app_settings.get(connection, USER, "seed.version") == "2"
        assert app_settings.get(connection, OTHER, "seed.version") == "7"


def test_only_unique_violations_become_name_taken(migrated_engine: Engine) -> None:
    from rack_overflow.domain.catalog import VariableDraft
    from rack_overflow.storage import variables as variable_queries
    from rack_overflow.storage.errors import NameTakenError

    with migrated_engine.begin() as connection:
        variable_queries.insert(connection, USER, "a", VariableDraft("A", "int", "set"))
        with pytest.raises(NameTakenError):
            variable_queries.insert(connection, USER, "a", VariableDraft("A", "int", "set"))
        with pytest.raises(sa.exc.IntegrityError):
            variable_queries.insert(connection, USER, "b", VariableDraft("B", "nope", "set"))
