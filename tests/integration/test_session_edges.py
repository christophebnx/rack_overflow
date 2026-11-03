"""Edge cases of session logging (L4) through `services.sessions` on a migrated database: one open
session (concurrent starts), prefill order with deleted sessions and soft-deleted sets, settings per
variable, records (ties, warm-ups, RM tests, cardio, intervals, deleted history), volume, edits
and deletions, archived exercises and variables, menus changed mid-session, time zone at day
boundaries and daylight-saving changes, unit round trips (D-061 to D-066)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError, ValueInput
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.sessions import Item
from rack_overflow.services import exercises, sessions, templates, variables
from rack_overflow.services.exercises import ExerciseForm, FieldForm
from rack_overflow.services.sessions import Confirmed, SessionView, SummaryView
from rack_overflow.services.templates import SlotForm, TemplateForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import schema as s
from rack_overflow.storage import sessions as queries

USER = 1
OTHER = 2
TZ = ZoneInfo("Europe/Brussels")
T0 = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)
DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)


# --- helpers


def make(engine: Engine, name: str, category: str = "strength", user: int = USER) -> int:
    return exercises.create(engine, user, ExerciseForm(name, category, "gym"))


def free(engine: Engine, now: datetime = T0, user: int = USER) -> int:
    return sessions.start(engine, user, None, "gym", now, TZ)


def add(engine: Engine, session_id: int, exercise_id: int) -> int:
    block = sessions.pick(engine, USER, session_id, None, exercise_id).block
    assert block is not None
    return block.id


def log(
    engine: Engine, session_id: int, row: int, values: dict[str, str], now: datetime, kind: str = "work"
) -> Confirmed:
    return sessions.confirm_set(engine, USER, session_id, row, kind, values, now)


def lift(reps: int, kg: str) -> dict[str, str]:
    return {"reps": str(reps), "weight": kg}


def block(engine: Engine, session_id: int, row: int) -> SessionView:
    found = sessions.show(engine, USER, session_id, Item(row_id=row))
    assert isinstance(found, SessionView) and found.block is not None
    return found


def form_of(engine: Engine, session_id: int, row: int) -> tuple[str, dict[str, str]]:
    found = block(engine, session_id, row).block
    assert found is not None
    return found.form.type, found.form.texts


def stars(engine: Engine, session_id: int, row: int) -> list[bool]:
    found = block(engine, session_id, row).block
    assert found is not None
    return [item.record for item in found.sets]


def past(engine: Engine, exercise_id: int, plan: list[tuple[str, dict[str, str]]], start: datetime) -> int:
    """A closed free session at `start` with the sets of `plan` on one row of `exercise_id`."""
    session_id = free(engine, start)
    row = add(engine, session_id, exercise_id)
    for index, (kind, values) in enumerate(plan):
        log(engine, session_id, row, values, start + index * MINUTE, kind)
    sessions.close(engine, USER, session_id, start + timedelta(hours=1))
    return session_id


def delete_session(engine: Engine, session_id: int) -> None:
    """The L5 soft delete of a session, done in SQL (no L4 service deletes a session)."""
    with engine.begin() as connection:
        connection.execute(
            sa.update(s.session).where(s.session.c.id == session_id).values(deleted_at="2026-12-01T00:00:00Z")
        )


def count(engine: Engine, table: sa.Table) -> int:
    with engine.begin() as connection:
        return connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()


def setting_var(engine: Engine, label: str, var_type: str = "int", **extra: object) -> int:
    return variables.create(
        engine, USER, VariableForm(label=label, var_type=var_type, scope="setting", **extra)
    )


def measure_var(engine: Engine, label: str, var_type: str = "int", **extra: object) -> int:
    return variables.create(engine, USER, VariableForm(label=label, var_type=var_type, scope="set", **extra))


def field_id(
    engine: Engine, exercise_id: int, *, quantity: str | None = None, variable: int | None = None
) -> int:
    for item in exercises.get_detail(engine, USER, exercise_id).fields:
        if quantity is not None and item.core_quantity == quantity:
            return item.id
        if variable is not None and item.variable is not None and item.variable.id == variable:
            return item.id
    raise AssertionError("no such field")


# --- one open session


def test_concurrent_starts_open_a_single_session(migrated_engine: Engine) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: free(migrated_engine), range(16)))
    assert len(set(ids)) == 1
    assert count(migrated_engine, s.session) == 1


def test_a_closed_session_lets_a_new_one_start_and_users_are_apart(migrated_engine: Engine) -> None:
    first = free(migrated_engine)
    other_user = free(migrated_engine, user=OTHER)  # another user's open session does not block
    assert other_user != first
    sessions.close(migrated_engine, USER, first, T0 + MINUTE)
    second = free(migrated_engine, T0 + DAY)
    assert second not in (first, other_user)
    page = sessions.start_page(migrated_engine, USER)
    assert page.open is not None and page.open.session.id == second


def test_a_deleted_open_session_does_not_block_a_start(migrated_engine: Engine) -> None:
    first = free(migrated_engine)
    delete_session(migrated_engine, first)
    assert sessions.start_page(migrated_engine, USER).open is None
    assert free(migrated_engine, T0 + MINUTE) != first


# --- prefill order (D-062)


def test_prefill_skips_deleted_sessions_and_soft_deleted_sets(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    past(migrated_engine, squat, [("work", lift(5, "100")), ("work", lift(5, "100"))], T0)
    # the latest session holding live sets: set 2 soft-deleted, so set N=1 is the old third set
    middle = past(
        migrated_engine,
        squat,
        [("warmup", lift(10, "60")), ("work", lift(3, "120")), ("work", lift(4, "115"))],
        T0 + 2 * DAY,
    )
    middle_sets = sessions.show(migrated_engine, USER, middle)
    assert isinstance(middle_sets, SummaryView)
    sessions.update_set(
        migrated_engine, USER, middle_sets.rows[0].sets[1].id, "work", lift(3, "120"), require_open=False
    )
    sessions.delete_set(
        migrated_engine, USER, middle_sets.rows[0].sets[1].id, T0 + 3 * DAY, require_open=False
    )
    # a newer session whose only set was soft-deleted: it holds no live set, it is skipped
    empty = free(migrated_engine, T0 + 4 * DAY)
    row = add(migrated_engine, empty, squat)
    gone = log(migrated_engine, empty, row, lift(1, "200"), T0 + 4 * DAY)
    sessions.delete_set(migrated_engine, USER, gone.set.id, T0 + 4 * DAY + MINUTE)
    sessions.close(migrated_engine, USER, empty, T0 + 4 * DAY + timedelta(hours=1))
    # a newer deleted session is ignored
    deleted = past(migrated_engine, squat, [("work", lift(1, "250"))], T0 + 5 * DAY)
    delete_session(migrated_engine, deleted)

    today = free(migrated_engine, T0 + 6 * DAY)
    row = add(migrated_engine, today, squat)
    assert form_of(migrated_engine, today, row) == ("warmup", {"reps": "10", "weight": "60"})
    log(migrated_engine, today, row, lift(10, "60"), T0 + 6 * DAY, "warmup")
    # set N=1 of the last performance (the soft-deleted 3 x 120 left out)
    assert form_of(migrated_engine, today, row) == ("work", {"reps": "4", "weight": "115"})
    log(migrated_engine, today, row, lift(4, "117,5"), T0 + 6 * DAY + MINUTE)
    # beyond the last performance: today's previous set carries forward
    assert form_of(migrated_engine, today, row) == ("work", {"reps": "4", "weight": "117,5"})


def test_today_same_type_beats_the_last_performance(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    past(
        migrated_engine,
        squat,
        [("work", lift(8, "60")), ("work", lift(8, "60")), ("work", lift(8, "60"))],
        T0,
    )
    today = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, today, squat)
    log(migrated_engine, today, row, lift(8, "65"), T0 + DAY)
    assert form_of(migrated_engine, today, row) == ("work", {"reps": "8", "weight": "65"})
    # deleting today's set brings the last performance back for set 1
    found = block(migrated_engine, today, row).block
    assert found is not None
    sessions.delete_set(migrated_engine, USER, found.sets[0].id, T0 + DAY + MINUTE)
    assert form_of(migrated_engine, today, row) == ("work", {"reps": "8", "weight": "60"})


def test_first_use_takes_the_target_low_end_then_field_defaults(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    weight = field_id(migrated_engine, squat, quantity="weight")
    exercises.update_field(
        migrated_engine, USER, squat, weight, FieldForm(required=True, increment="2,5", default="40")
    )
    salle = templates.create(migrated_engine, USER, TemplateForm("Salle", "gym"))
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=squat)
    templates.update_slot(
        migrated_engine, USER, salle, slot, SlotForm(exercise_id=squat, sets="4", reps="6-8")
    )
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView) and found.block is not None
    assert (found.block.form.type, found.block.form.texts) == ("work", {"reps": "6", "weight": "40"})
    # an added row of the same exercise has no target: the defaults alone
    added = add(migrated_engine, session_id, squat)
    assert form_of(migrated_engine, session_id, added) == ("work", {"weight": "40"})


def test_target_duration_and_distance_parts_for_cardio(migrated_engine: Engine) -> None:
    bike = make(migrated_engine, "Vélo", "cardio")
    salle = templates.create(migrated_engine, USER, TemplateForm("Cardio", "gym"))
    slot = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=bike)
    templates.update_slot(
        migrated_engine,
        USER,
        salle,
        slot,
        SlotForm(exercise_id=bike, reps="10", duration="30:00", distance="5"),
    )
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView) and found.block is not None
    # reps has no field on a cardio exercise: dropped
    assert found.block.form.texts == {"duration": "30:00", "distance": "5"}


# --- settings (D-062)


def test_settings_prefill_per_variable_from_different_sessions(migrated_engine: Engine) -> None:
    press = make(migrated_engine, "Presse")
    seat = setting_var(migrated_engine, "Siège")
    back = setting_var(migrated_engine, "Dossier")
    exercises.add_field(migrated_engine, USER, press, variable_id=seat)
    first = free(migrated_engine, T0)
    row = add(migrated_engine, first, press)
    sessions.save_settings(migrated_engine, USER, first, row, {f"var_{seat}": "4", f"var_{back}": "9"})
    sessions.close(migrated_engine, USER, first, T0 + MINUTE)
    exercises.add_field(migrated_engine, USER, press, variable_id=back)
    second = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, second, press)
    sessions.save_settings(migrated_engine, USER, second, row, {f"var_{seat}": "6", f"var_{back}": "2"})
    sessions.close(migrated_engine, USER, second, T0 + DAY + MINUTE)
    third = free(migrated_engine, T0 + 2 * DAY)
    row = add(migrated_engine, third, press)
    sessions.save_settings(migrated_engine, USER, third, row, {f"var_{seat}": "7", f"var_{back}": ""})
    sessions.close(migrated_engine, USER, third, T0 + 2 * DAY + MINUTE)
    deleted = free(migrated_engine, T0 + 3 * DAY)
    row = add(migrated_engine, deleted, press)
    sessions.save_settings(migrated_engine, USER, deleted, row, {f"var_{seat}": "1", f"var_{back}": "1"})
    sessions.close(migrated_engine, USER, deleted, T0 + 3 * DAY + MINUTE)
    delete_session(migrated_engine, deleted)

    today = free(migrated_engine, T0 + 4 * DAY)
    row = add(migrated_engine, today, press)
    found = block(migrated_engine, today, row).block
    assert found is not None
    # each variable from its own latest session; the deleted session ignored
    assert found.settings == {seat: 7, back: 2}
    # saved on change, then the ✓ keeps the saved value and writes the missing one
    sessions.save_settings(migrated_engine, USER, today, row, {f"var_{seat}": "8", f"var_{back}": ""})
    log(migrated_engine, today, row, lift(10, "100"), T0 + 4 * DAY)
    with migrated_engine.begin() as connection:
        assert queries.settings_of(connection, row) == {seat: 8, back: 2}
    log(migrated_engine, today, row, lift(10, "100"), T0 + 4 * DAY + MINUTE)
    sessions.save_settings(migrated_engine, USER, today, row, {f"var_{seat}": "9", f"var_{back}": "2"})
    with migrated_engine.begin() as connection:
        assert queries.settings_of(connection, row) == {seat: 9, back: 2}
        rows = connection.execute(
            sa.select(sa.func.count())
            .select_from(s.exercise_setting)
            .where(s.exercise_setting.c.session_exercise_id == row)
        ).scalar_one()
    assert rows == 2  # one fact per row and variable


def test_enum_bool_and_decimal_settings_round_trip(migrated_engine: Engine) -> None:
    press = make(migrated_engine, "Presse")
    grip = setting_var(
        migrated_engine, "Prise", "enum", values=[ValueInput("Pronation"), ValueInput("Neutre")]
    )
    straps = setting_var(migrated_engine, "Sangles", "bool")
    height = setting_var(migrated_engine, "Hauteur", "decimal", scale="1")
    for variable in (grip, straps, height):
        exercises.add_field(migrated_engine, USER, press, variable_id=variable)
    keys = [v.key for v in variables.get_detail(migrated_engine, USER, grip).draft.enum_values or ()]
    first = free(migrated_engine)
    row = add(migrated_engine, first, press)
    raw = {f"var_{grip}": keys[1], f"var_{straps}": "1", f"var_{height}": "12,5"}
    saved = sessions.save_settings(migrated_engine, USER, first, row, raw)
    assert saved.block is not None
    assert saved.block.settings == {grip: keys[1], straps: 1, height: 125}
    assert saved.block.settings_texts == raw
    with pytest.raises(CatalogError) as error:
        sessions.save_settings(migrated_engine, USER, first, row, {**raw, f"var_{grip}": "Neutre"})
    assert error.value.problems[0].code == "invalid_choice"  # the label is not the stored key
    with migrated_engine.begin() as connection:
        stored = connection.execute(
            sa.select(
                s.exercise_setting.c.variable_id,
                s.exercise_setting.c.value_int,
                s.exercise_setting.c.value_text,
            )
            .where(s.exercise_setting.c.session_exercise_id == row)
            .order_by(s.exercise_setting.c.variable_id)
        ).all()
    assert [tuple(item) for item in stored] == [(grip, None, keys[1]), (straps, 1, None), (height, 125, None)]


# --- measure variables, archived and unlinked fields


def test_optional_measure_variables_of_every_kind(migrated_engine: Engine) -> None:
    bike = make(migrated_engine, "Vélo", "cardio")
    level = measure_var(migrated_engine, "Niveau", "enum", values=[ValueInput("Facile"), ValueInput("Dur")])
    fan = measure_var(migrated_engine, "Ventilateur", "bool")
    cadence = measure_var(migrated_engine, "Cadence", "decimal", scale="1")
    note = measure_var(migrated_engine, "Note", "text")
    for variable in (level, fan, cadence, note):
        exercises.add_field(migrated_engine, USER, bike, variable_id=variable)
    hard = [v.key for v in variables.get_detail(migrated_engine, USER, level).draft.enum_values or ()][1]
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, bike)
    found = block(migrated_engine, session_id, row).block
    assert found is not None
    assert {f.name for f in found.more_fields} == {f"var_{v}" for v in (level, fan, cadence, note)}
    # optional variables left empty
    plain = log(migrated_engine, session_id, row, {"duration": "20:00"}, T0)
    assert plain.set.facts.values == {"duration": 1200}
    full = log(
        migrated_engine,
        session_id,
        row,
        {
            "duration": "1:02:03",
            "distance": "5,25",
            f"var_{level}": hard,
            f"var_{fan}": "0",
            f"var_{cadence}": "85,5",
            f"var_{note}": "  vent de face  ",
        },
        T0 + MINUTE,
    )
    assert full.set.facts.values == {
        "duration": 3723,
        "distance": 5250,
        f"var_{level}": hard,
        f"var_{fan}": 0,
        f"var_{cadence}": 855,
        f"var_{note}": "vent de face",
    }
    # the next form shows the same texts (today, same type): display ↔ canonical round trip
    assert form_of(migrated_engine, session_id, row)[1] == {
        "duration": "1:02:03",
        "distance": "5,25",
        f"var_{level}": hard,
        f"var_{fan}": "0",
        f"var_{cadence}": "85,5",
        f"var_{note}": "vent de face",
    }


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"distance": "800 m", "duration": "45"}, {"distance": 800, "duration": 45}),
        ({"distance": "0,8", "duration": "0:45"}, {"distance": 800, "duration": 45}),
        ({"distance": "12.345", "duration": "10:00:00"}, {"distance": 12345, "duration": 36000}),
    ],
)
def test_units_round_trip_through_the_next_form(
    migrated_engine: Engine, values: dict[str, str], expected: dict[str, int]
) -> None:
    bike = make(migrated_engine, "Vélo", "cardio")
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, bike)
    done = log(migrated_engine, session_id, row, values, T0)
    assert done.set.facts.values == expected
    _, texts = form_of(migrated_engine, session_id, row)
    again = log(migrated_engine, session_id, row, texts, T0 + MINUTE)
    assert again.set.facts.values == expected


def test_weight_grams_round_trip(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, squat)
    done = log(migrated_engine, session_id, row, lift(5, "102.125"), T0)
    assert done.set.facts.values == {"reps": 5, "weight": 102125}
    assert form_of(migrated_engine, session_id, row)[1] == {"reps": "5", "weight": "102,125"}
    with pytest.raises(CatalogError) as error:
        log(migrated_engine, session_id, row, lift(5, "1,0005"), T0)
    assert error.value.problems[0].code == "too_many_decimals"
    with pytest.raises(CatalogError) as error:
        log(migrated_engine, session_id, row, lift(5, "-5"), T0)
    assert error.value.problems[0].code == "negative"


def test_a_row_of_an_archived_exercise_keeps_logging(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, squat)
    exercises.set_archived(migrated_engine, USER, squat, T0)
    found = block(migrated_engine, session_id, row).block
    assert found is not None and found.exercise.archived
    assert log(migrated_engine, session_id, row, lift(5, "100"), T0).set.number == 1
    assert squat not in {
        e.id for e in sessions.search_exercises(migrated_engine, USER, session_id, "").recent
    }
    with pytest.raises(CatalogError):
        sessions.pick(migrated_engine, USER, session_id, None, squat)


def test_values_of_an_archived_variable_are_never_written(migrated_engine: Engine) -> None:
    bike = make(migrated_engine, "Vélo", "cardio")
    level = measure_var(migrated_engine, "Niveau")
    seat = setting_var(migrated_engine, "Selle")
    for variable in (level, seat):
        exercises.add_field(migrated_engine, USER, bike, variable_id=variable)
    variables.set_archived(migrated_engine, USER, level, T0)
    variables.set_archived(migrated_engine, USER, seat, T0)
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, bike)
    done = log(
        migrated_engine, session_id, row, {"duration": "10:00", f"var_{level}": "5", f"var_{seat}": "3"}, T0
    )
    assert done.set.facts.values == {"duration": 600}
    sessions.save_settings(migrated_engine, USER, session_id, row, {f"var_{seat}": "3"})
    assert count(migrated_engine, s.set_value) == 0
    assert count(migrated_engine, s.exercise_setting) == 0


@pytest.mark.xfail(
    strict=True,
    reason="product bug: services/sessions.update_set → storage.replace_set_values deletes every "
    "set_value of the set, so editing a set physically erases the stored value of a variable "
    "archived (or unlinked) since (invariant 8, L2 'stored values kept')",
)
def test_editing_a_set_keeps_the_values_of_archived_variables(migrated_engine: Engine) -> None:
    bike = make(migrated_engine, "Vélo", "cardio")
    level = measure_var(migrated_engine, "Niveau")
    exercises.add_field(migrated_engine, USER, bike, variable_id=level)
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, bike)
    done = log(migrated_engine, session_id, row, {"duration": "10:00", f"var_{level}": "5"}, T0)
    variables.set_archived(migrated_engine, USER, level, T0 + MINUTE)
    sessions.update_set(migrated_engine, USER, done.set.id, "work", {"duration": "11:00"})
    with migrated_engine.begin() as connection:
        assert queries.values_of(connection, [done.set.id]) == {done.set.id: {level: 5}}


# --- records (D-064)


def test_records_ties_warm_ups_and_rm_tests(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    past(migrated_engine, squat, [("warmup", lift(5, "200")), ("work", lift(5, "100"))], T0)
    today = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, today, squat)
    plan = [
        ("work", lift(5, "100")),  # tie: no
        ("work", lift(5, "105")),  # heavier at the same reps: yes (the heavy warm-up does not count)
        ("warmup", lift(5, "300")),  # warm-up: never
        ("rm_test", lift(1, "140")),  # heavier at fewer reps: yes
        ("work", lift(4, "105")),  # dominated by today's set 2: no
        ("work", lift(6, "105")),  # more reps at the load: yes
    ]
    results = [
        log(migrated_engine, today, row, values, T0 + DAY + i * MINUTE, kind).set.record
        for i, (kind, values) in enumerate(plan)
    ]
    assert results == [False, True, False, True, False, True]
    assert stars(migrated_engine, today, row) == results  # a reload shows the same stars


def test_changing_a_set_type_moves_the_stars(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    past(migrated_engine, squat, [("work", lift(5, "100"))], T0)
    today = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, today, squat)
    first = log(migrated_engine, today, row, lift(5, "110"), T0 + DAY)
    log(migrated_engine, today, row, lift(5, "110"), T0 + DAY + MINUTE)
    assert stars(migrated_engine, today, row) == [True, False]
    sessions.update_set(migrated_engine, USER, first.set.id, "warmup", lift(5, "110"))
    assert stars(migrated_engine, today, row) == [False, True]
    sessions.delete_set(migrated_engine, USER, first.set.id, T0 + DAY + 2 * MINUTE)
    assert stars(migrated_engine, today, row) == [True]


def test_a_deleted_session_leaves_the_record_history(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    old = past(migrated_engine, squat, [("work", lift(5, "100"))], T0)
    middle = past(migrated_engine, squat, [("work", lift(5, "120"))], T0 + DAY)
    today = free(migrated_engine, T0 + 2 * DAY)
    row = add(migrated_engine, today, squat)
    log(migrated_engine, today, row, lift(5, "110"), T0 + 2 * DAY)
    assert stars(migrated_engine, today, row) == [False]  # 5 x 120 dominates
    delete_session(migrated_engine, middle)
    assert stars(migrated_engine, today, row) == [True]
    delete_session(migrated_engine, old)
    assert stars(migrated_engine, today, row) == [False]  # now the first counted set ever


def test_records_are_per_exercise_and_per_user(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    bench = make(migrated_engine, "Bench")
    theirs = make(migrated_engine, "Squat", user=OTHER)
    past(migrated_engine, bench, [("work", lift(5, "100"))], T0)
    stranger = sessions.start(migrated_engine, OTHER, None, "gym", T0, TZ)
    other_row = sessions.pick(migrated_engine, OTHER, stranger, None, theirs).block
    assert other_row is not None
    sessions.confirm_set(migrated_engine, OTHER, stranger, other_row.id, "work", lift(5, "50"), T0)
    sessions.close(migrated_engine, OTHER, stranger, T0 + MINUTE)
    today = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, today, squat)
    assert not log(migrated_engine, today, row, lift(5, "110"), T0 + DAY).set.record


@pytest.mark.xfail(
    strict=True,
    reason="doc/impl conflict: D-064 and the L4 note say 'no star on the first session'; the "
    "implemented rule stars a heavier work set later in the very first session of an exercise",
)
def test_no_star_in_the_first_session_of_an_exercise(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, squat)
    log(migrated_engine, session_id, row, lift(5, "60"), T0)
    assert not log(migrated_engine, session_id, row, lift(5, "80"), T0 + MINUTE).set.record


def test_cardio_records_by_distance_and_speed(migrated_engine: Engine) -> None:
    run = make(migrated_engine, "Course", "cardio")
    past(migrated_engine, run, [("work", {"duration": "30:00", "distance": "5"})], T0)
    today = free(migrated_engine, T0 + DAY)
    row = add(migrated_engine, today, run)
    plan = [
        {"duration": "30:00", "distance": "5"},  # tie
        {"duration": "29:00", "distance": "5"},  # faster
        {"duration": "40:00", "distance": "6"},  # farther, slower
        {"duration": "35:00", "distance": "4"},  # dominated
    ]
    found = [
        log(migrated_engine, today, row, values, T0 + DAY + i * MINUTE).set.record
        for i, values in enumerate(plan)
    ]
    assert found == [False, True, True, False]


def test_intervals_record_is_the_round_beating_every_earlier_session(migrated_engine: Engine) -> None:
    tabata = make(migrated_engine, "Tabata", "intervals")
    past(migrated_engine, tabata, [("work", {"duration": "0:20"})] * 3, T0)
    past(
        migrated_engine,
        tabata,
        [("warmup", {"duration": "0:20"})] + [("work", {"duration": "0:20"})] * 2,
        T0 + DAY,
    )
    today = free(migrated_engine, T0 + 2 * DAY)
    row = add(migrated_engine, today, tabata)
    log(migrated_engine, today, row, {"duration": "0:20"}, T0 + 2 * DAY, "warmup")
    found = [
        log(migrated_engine, today, row, {"duration": "0:20"}, T0 + 2 * DAY + (i + 1) * MINUTE).set.record
        for i in range(5)
    ]
    assert found == [False, False, False, True, False]  # the 4th counted round only
    summary_row = sessions.show(migrated_engine, USER, today)
    assert isinstance(summary_row, SessionView) and summary_row.cards[row].record_count == 1


# --- volume and summary


def test_summary_volume_by_category_and_rows_without_live_sets(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    dips = make(migrated_engine, "Dips", "bodyweight")
    weight_field = exercises.add_field(migrated_engine, USER, dips, core_quantity="weight")
    del weight_field
    bike = make(migrated_engine, "Vélo", "cardio")
    curl = make(migrated_engine, "Curl")
    session_id = free(migrated_engine)
    rows = {
        name: add(migrated_engine, session_id, ex)
        for name, ex in (("squat", squat), ("dips", dips), ("bike", bike), ("curl", curl))
    }
    log(migrated_engine, session_id, rows["squat"], lift(10, "40"), T0, "warmup")
    log(migrated_engine, session_id, rows["squat"], lift(5, "100"), T0 + MINUTE)
    log(migrated_engine, session_id, rows["squat"], lift(1, "120"), T0 + 2 * MINUTE, "rm_test")
    log(migrated_engine, session_id, rows["dips"], {"reps": "10"}, T0 + 3 * MINUTE)
    log(migrated_engine, session_id, rows["dips"], {"reps": "8", "weight": "10"}, T0 + 4 * MINUTE)
    log(migrated_engine, session_id, rows["bike"], {"duration": "30:00", "distance": "10"}, T0 + 5 * MINUTE)
    gone = log(migrated_engine, session_id, rows["curl"], lift(10, "30"), T0 + 6 * MINUTE)
    sessions.delete_set(migrated_engine, USER, gone.set.id, T0 + 7 * MINUTE)
    # the curl row holds only a deleted set: it counts as an exercise without set
    assert sessions.unlogged_count(migrated_engine, USER, session_id) == 1
    sessions.close(migrated_engine, USER, session_id, T0 + timedelta(hours=1))
    summary = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(summary, SummaryView)
    assert [r.exercise.name for r in summary.rows] == ["Squat", "Dips", "Vélo"]
    squat_row, dips_row, bike_row = summary.rows
    assert (squat_row.volume.load_g, squat_row.volume.sets, squat_row.warmups) == (620_000, 2, 1)
    assert (dips_row.volume.reps, dips_row.volume.load_g) == (18, 80_000)
    assert (bike_row.volume.distance_m, bike_row.volume.duration_s) == (10_000, 1800)
    assert (summary.total_sets, summary.total_load_g) == (5, 700_000)


# --- menus, added rows, plan changes


def menu_template(engine: Engine) -> tuple[int, int, dict[str, int]]:
    names = {name: make(engine, name) for name in ("Rowing", "Tirage", "Poulie")}
    salle = templates.create(engine, USER, TemplateForm("Salle", "gym"))
    menu = templates.add_slot(engine, USER, salle, kind="menu", exercise_id=names["Rowing"], label="Dos")
    templates.add_option(engine, USER, salle, menu, names["Tirage"])
    templates.add_option(engine, USER, salle, menu, names["Poulie"])
    return salle, menu, names


def test_menu_option_archived_mid_session_is_refused(migrated_engine: Engine) -> None:
    salle, menu, names = menu_template(migrated_engine)
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    exercises.set_archived(migrated_engine, USER, names["Tirage"], T0 + MINUTE)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView)
    assert [o.name for o in found.menus[menu].options] == ["Rowing", "Poulie"]
    with pytest.raises(CatalogError) as error:
        sessions.pick(migrated_engine, USER, session_id, menu, names["Tirage"])
    assert error.value.problems[0].code == "exercise_unavailable"
    with pytest.raises(CatalogError) as error:
        sessions.pick(migrated_engine, USER, session_id, menu, None)
    assert error.value.problems[0].code == "required"
    assert count(migrated_engine, s.session_exercise) == 0


def test_every_option_archived_hides_the_pending_menu(migrated_engine: Engine) -> None:
    salle, menu, names = menu_template(migrated_engine)
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    for exercise_id in names.values():
        exercises.set_archived(migrated_engine, USER, exercise_id, T0 + MINUTE)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView) and found.items == () and found.block is None
    assert sessions.unlogged_count(migrated_engine, USER, session_id) == 0
    del menu


def test_a_row_whose_slot_was_removed_stays_after_the_plan(migrated_engine: Engine) -> None:
    salle, menu, names = menu_template(migrated_engine)
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    picked = sessions.pick(migrated_engine, USER, session_id, menu, names["Rowing"]).block
    assert picked is not None
    log(migrated_engine, session_id, picked.id, lift(10, "50"), T0)
    templates.remove_slot(migrated_engine, USER, salle, menu, T0 + MINUTE)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView)
    assert found.items == (Item(row_id=picked.id),)
    assert log(migrated_engine, session_id, picked.id, lift(10, "50"), T0 + 2 * MINUTE).set.number == 2


def test_a_menu_pick_cannot_be_changed_once_a_set_was_deleted(migrated_engine: Engine) -> None:
    salle, menu, names = menu_template(migrated_engine)
    session_id = sessions.start(migrated_engine, USER, salle, "gym", T0, TZ)
    row = sessions.pick(migrated_engine, USER, session_id, menu, names["Rowing"]).block
    assert row is not None
    done = log(migrated_engine, session_id, row.id, lift(10, "50"), T0)
    sessions.delete_set(migrated_engine, USER, done.set.id, T0 + MINUTE)
    with pytest.raises(CatalogError) as error:  # the row holds a (deleted) fact
        sessions.change_exercise(migrated_engine, USER, session_id, row.id, names["Poulie"])
    assert error.value.problems[0].code == "exercise_has_sets"


def test_a_pick_of_another_template_or_a_fixed_slot_is_not_found(migrated_engine: Engine) -> None:
    salle, menu, names = menu_template(migrated_engine)
    fixed = templates.add_slot(migrated_engine, USER, salle, kind="exercise", exercise_id=names["Poulie"])
    session_id = free(migrated_engine)  # a free session has no slot at all
    with pytest.raises(NotFoundError):
        sessions.pick(migrated_engine, USER, session_id, menu, names["Rowing"])
    sessions.close(migrated_engine, USER, session_id, T0)
    from_template = sessions.start(migrated_engine, USER, salle, "gym", T0 + DAY, TZ)
    with pytest.raises(NotFoundError):
        sessions.pick(migrated_engine, USER, from_template, fixed, names["Poulie"])


def test_a_row_of_another_session_cannot_take_a_set(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    old = free(migrated_engine)
    old_row = add(migrated_engine, old, squat)
    sessions.close(migrated_engine, USER, old, T0 + MINUTE)
    today = free(migrated_engine, T0 + DAY)
    with pytest.raises(NotFoundError):
        log(migrated_engine, today, old_row, lift(5, "100"), T0 + DAY)
    with pytest.raises(NotFoundError):
        sessions.save_settings(migrated_engine, USER, today, old_row, {})
    with pytest.raises(NotFoundError):
        sessions.set_form(migrated_engine, USER, today, old_row, "work", {}, "reps:up")
    assert count(migrated_engine, s.set_entry) == 0


def test_the_added_row_changes_to_any_available_exercise(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    bench = make(migrated_engine, "Bench")
    archived = make(migrated_engine, "Old")
    exercises.set_archived(migrated_engine, USER, archived, T0)
    theirs = make(migrated_engine, "Foreign", user=OTHER)
    session_id = free(migrated_engine)
    row = add(migrated_engine, session_id, squat)
    for refused in (archived, theirs, 999_999):
        with pytest.raises(CatalogError):
            sessions.change_exercise(migrated_engine, USER, session_id, row, refused)
    changed = sessions.change_exercise(migrated_engine, USER, session_id, row, bench)
    assert changed.block is not None and changed.block.exercise.name == "Bench"
    assert changed.current == Item(row_id=row)


# --- search: recent first


def test_recent_list_is_capped_and_ignores_deleted_sessions(migrated_engine: Engine) -> None:
    ids = [make(migrated_engine, f"Ex {i:02d}") for i in range(25)]
    for i, exercise_id in enumerate(ids):
        past(migrated_engine, exercise_id, [("work", lift(5, "10"))], T0 + i * DAY)
    hidden = past(
        migrated_engine, make(migrated_engine, "Zz hidden"), [("work", lift(5, "10"))], T0 + 30 * DAY
    )
    delete_session(migrated_engine, hidden)
    today = free(migrated_engine, T0 + 40 * DAY)
    results = sessions.search_exercises(migrated_engine, USER, today, "  ")
    assert [e.name for e in results.recent] == [f"Ex {i:02d}" for i in range(24, 4, -1)]
    assert [e.name for e in results.others] == [f"Ex {i:02d}" for i in range(5)] + ["Zz hidden"]
    ranked = sessions.search_exercises(migrated_engine, USER, today, "ex")
    assert ranked.ranked[0].name == "Ex 24"  # recent first among equal matches


# --- time zone (D-065)


@pytest.mark.parametrize(
    ("moment", "local_date"),
    [
        (datetime(2026, 11, 3, 22, 59, tzinfo=UTC), "2026-11-03"),  # 23:59 in Brussels (CET)
        (datetime(2026, 11, 3, 23, 1, tzinfo=UTC), "2026-11-04"),  # 00:01 in Brussels
        (datetime(2026, 7, 1, 21, 59, tzinfo=UTC), "2026-07-01"),  # 23:59 CEST
        (datetime(2026, 7, 1, 22, 1, tzinfo=UTC), "2026-07-02"),  # 00:01 CEST
    ],
)
def test_local_date_at_the_day_boundary(migrated_engine: Engine, moment: datetime, local_date: str) -> None:
    session_id = free(migrated_engine, moment)
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView)
    assert (found.session.local_date, found.session.time_zone) == (local_date, "Europe/Brussels")


def test_a_session_over_midnight_keeps_its_start_date(migrated_engine: Engine) -> None:
    squat = make(migrated_engine, "Squat")
    start = datetime(2026, 11, 3, 22, 59, tzinfo=UTC)  # 23:59 local
    session_id = free(migrated_engine, start)
    row = add(migrated_engine, session_id, squat)
    log(migrated_engine, session_id, row, lift(5, "100"), start + 2 * MINUTE)  # 00:01 local, next day
    sessions.close(migrated_engine, USER, session_id, start + 10 * MINUTE)
    summary = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(summary, SummaryView)
    assert summary.session.local_date == "2026-11-03" and len(summary.rows[0].sets) == 1


def test_another_zone_is_stored_with_the_session(migrated_engine: Engine) -> None:
    moment = datetime(2026, 11, 3, 23, 30, tzinfo=UTC)
    session_id = sessions.start(migrated_engine, USER, None, "gym", moment, ZoneInfo("America/New_York"))
    found = sessions.show(migrated_engine, USER, session_id)
    assert isinstance(found, SessionView)
    assert (found.session.local_date, found.session.time_zone) == ("2026-11-03", "America/New_York")
