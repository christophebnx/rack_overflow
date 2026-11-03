"""CHECK, UNIQUE and foreign key constraints of the migrated schema on a real temporary database.

`compare_metadata` ignores CHECK constraints, so the first test checks that the frozen migration
carries every CHECK of `schema.metadata`; the others insert rows to see each rule enforced.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import vocabulary
from rack_overflow.storage import schema

NOW = "2026-11-03T18:04:05Z"


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).replace("( ", "(").replace(" )", ")").strip()


@pytest.fixture
def connection(migrated_engine: Engine) -> Iterator[sa.Connection]:
    """A connection whose transaction is rolled back after the test."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _insert(connection: sa.Connection, table: sa.Table, **values: object) -> int:
    return connection.execute(sa.insert(table).values(values)).inserted_primary_key[0]


def _refused(connection: sa.Connection, table: sa.Table, **values: object) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.insert(table).values(values))
    savepoint.rollback()


def _exercise(connection: sa.Connection, name: str = "Squat") -> int:
    return _insert(connection, schema.exercise, user_id=1, name=name, category="strength", location="gym")


def _variable(connection: sa.Connection, code: str = "seat", **values: object) -> int:
    row = {"user_id": 1, "code": code, "label": "Siège", "type": "int", "scope": "setting", **values}
    return _insert(connection, schema.variable, **row)


def _session(connection: sa.Connection, **values: object) -> int:
    row = {
        "user_id": 1,
        "local_date": "2026-11-03",
        "time_zone": "Europe/Paris",
        "started_at": NOW,
        "location": "gym",
        "status": "closed",
        "ended_at": NOW,
        **values,
    }
    return _insert(connection, schema.session, **row)


def _session_exercise(connection: sa.Connection) -> int:
    return _insert(
        connection,
        schema.session_exercise,
        session_id=_session(connection),
        exercise_id=_exercise(connection),
        position=1,
    )


def _template(connection: sa.Connection) -> int:
    return _insert(connection, schema.template, user_id=1, name="Salle A", location="gym", position=1)


def test_migration_carries_every_check_of_the_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        created = dict(
            connection.exec_driver_sql("SELECT name, sql FROM sqlite_master WHERE type = 'table'").fetchall()
        )
    for table in schema.metadata.sorted_tables:
        sql = _normalise(created[table.name])
        declared = re.findall(r"CONSTRAINT (\w+) CHECK", sql)
        expected = [c for c in table.constraints if isinstance(c, sa.CheckConstraint)]
        assert sorted(declared) == sorted(str(c.name) for c in expected), table.name
        for check in expected:
            if not isinstance(check.sqltext, sa.TextClause):  # Boolean(create_constraint=True)
                continue
            text = _normalise(str(check.sqltext.compile(dialect=migrated_engine.dialect)))
            assert text in sql, f"{check.name}: {text}"


def test_migration_carries_every_index_of_the_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
        ).fetchall()
    created = {name: _normalise(sql) for name, sql in rows}
    for table in schema.metadata.sorted_tables:
        for index in table.indexes:
            assert index.name in created, index.name
            assert (" UNIQUE " in f" {created[index.name]} ") is bool(index.unique), index.name


ENUM_COLUMNS = [
    ("exercise.category", vocabulary.EXERCISE_CATEGORIES),
    ("exercise.location", vocabulary.LOCATIONS),
    ("template.location", vocabulary.LOCATIONS),
    ("session.location", vocabulary.SESSION_LOCATIONS),
    ("variable.scope", vocabulary.VARIABLE_SCOPES),
    ("set_entry.type", vocabulary.SET_TYPES),
    ("exercise_field.core_quantity", vocabulary.CORE_QUANTITIES),
]


def _row_with(connection: sa.Connection, column: str, value: str) -> tuple[sa.Table, dict[str, object]]:
    """A valid row of the column's table with `column` set to `value`."""
    table_name, name = column.split(".")
    rows: dict[str, dict[str, object]] = {
        "exercise": {"user_id": 1, "name": f"E {value}", "category": "strength", "location": "gym"},
        "template": {"user_id": 1, "name": "T", "location": "gym", "position": 1},
        "session": {
            "user_id": 1,
            "local_date": "2026-11-03",
            "time_zone": "UTC",
            "started_at": NOW,
            "location": "gym",
            "status": "closed",
            "ended_at": NOW,
        },
        "variable": {"user_id": 1, "code": f"v-{value}", "label": "V", "type": "int", "scope": "set"},
    }
    if table_name == "set_entry":
        rows["set_entry"] = {"session_exercise_id": _session_exercise(connection), "position": 1}
    if table_name == "exercise_field":
        rows["exercise_field"] = {"exercise_id": _exercise(connection, "Field host"), "position": 1}
    return schema.metadata.tables[table_name], {**rows[table_name], name: value}


@pytest.mark.parametrize(
    ("column", "value"),
    [(column, value) for column, values in ENUM_COLUMNS for value in values],
)
def test_each_vocabulary_value_is_accepted(connection: sa.Connection, column: str, value: str) -> None:
    table, row = _row_with(connection, column, value)
    _insert(connection, table, **row)


@pytest.mark.parametrize("column", [column for column, _ in ENUM_COLUMNS])
@pytest.mark.parametrize("value", ["unknown", "", "Gym", " gym"])
def test_unknown_or_label_like_values_are_refused(connection: sa.Connection, column: str, value: str) -> None:
    table, row = _row_with(connection, column, value)
    _refused(connection, table, **row)


@pytest.mark.parametrize("variable_type", vocabulary.VARIABLE_TYPES)
def test_each_variable_type_with_its_companion_columns(connection: sa.Connection, variable_type: str) -> None:
    extra: dict[str, object] = {}
    if variable_type == "enum":
        extra["enum_values"] = [{"key": "low", "label": "Bas"}]
    if variable_type == "decimal":
        extra["decimal_scale"] = 1
    _variable(connection, code=variable_type, type=variable_type, **extra)


def test_unknown_variable_type_is_refused(connection: sa.Connection) -> None:
    _refused(connection, schema.variable, user_id=1, code="x", label="X", type="float", scope="set")


@pytest.mark.parametrize(
    "values",
    [
        {"type": "enum"},  # enum without values
        {"type": "int", "enum_values": ["a"]},  # values on a non-enum
        pytest.param(
            {"type": "decimal"},
            marks=pytest.mark.xfail(
                strict=True,
                reason="product bug: ck_variable_decimal_scale is NULL (passes) when decimal_scale is NULL",
            ),
            id="decimal-without-scale",
        ),
        {"type": "decimal", "decimal_scale": 0},
        {"type": "decimal", "decimal_scale": 7},
        {"type": "int", "decimal_scale": 2},  # scale on a non-decimal
    ],
)
def test_variable_companion_column_rules(connection: sa.Connection, values: dict[str, object]) -> None:
    _refused(connection, schema.variable, user_id=1, code="x", label="X", scope="set", **values)


@pytest.mark.parametrize("scale", [1, 6])
def test_decimal_scale_bounds_are_inclusive(connection: sa.Connection, scale: int) -> None:
    _variable(connection, code=f"d{scale}", type="decimal", decimal_scale=scale)


def test_variable_code_is_unique_per_user(connection: sa.Connection) -> None:
    _variable(connection)
    _variable(connection, user_id=2)
    _refused(connection, schema.variable, user_id=1, code="seat", label="Autre", type="int", scope="set")


def test_exercise_name_is_unique_per_user(connection: sa.Connection) -> None:
    _exercise(connection)
    _insert(connection, schema.exercise, user_id=2, name="Squat", category="strength", location="gym")
    _refused(connection, schema.exercise, user_id=1, name="Squat", category="cardio", location="home")


@pytest.mark.parametrize("required", [2, -1])
def test_exercise_field_required_is_a_boolean(connection: sa.Connection, required: int) -> None:
    exercise_id = _exercise(connection)
    _refused(
        connection,
        schema.exercise_field,
        exercise_id=exercise_id,
        core_quantity="reps",
        position=1,
        required=sa.literal(required, sa.Integer),
    )


def test_exercise_field_rules(connection: sa.Connection) -> None:
    exercise_id = _exercise(connection)
    variable_id = _variable(connection)
    field = schema.exercise_field
    base = {"exercise_id": exercise_id, "position": 1}
    _refused(connection, field, **base, core_quantity="reps", variable_id=variable_id)  # both sources
    _refused(connection, field, **base, core_quantity="reps", increment=0)
    _refused(connection, field, **base, core_quantity="reps", default_int=1, default_text="a")
    _insert(connection, field, **base, core_quantity="weight", increment=2500, discrete_values=[16000, 20000])
    _insert(connection, field, **base, variable_id=variable_id, default_int=5)
    _refused(connection, field, **base, core_quantity="weight")  # same quantity twice
    _refused(connection, field, **base, variable_id=variable_id)  # same variable twice
    _refused(connection, field, exercise_id=999, position=1, core_quantity="reps")  # FK


def test_alias_is_unique_per_exercise_after_normalisation(connection: sa.Connection) -> None:
    exercise_id = _exercise(connection)
    alias = schema.exercise_alias
    _insert(connection, alias, exercise_id=exercise_id, alias="DC", alias_normalised="dc")
    _refused(connection, alias, exercise_id=exercise_id, alias="dc", alias_normalised="dc")
    _insert(connection, alias, exercise_id=_exercise(connection, "Autre"), alias="DC", alias_normalised="dc")


def test_template_slot_needs_exactly_one_source(connection: sa.Connection) -> None:
    template_id = _template(connection)
    exercise_id = _exercise(connection)
    slot = schema.template_slot
    _insert(connection, slot, template_id=template_id, position=1, exercise_id=exercise_id)
    _insert(connection, slot, template_id=template_id, position=2, movement_pattern="pull")
    _refused(connection, slot, template_id=template_id, position=3)
    _refused(
        connection,
        slot,
        template_id=template_id,
        position=3,
        exercise_id=exercise_id,
        movement_pattern="pull",
    )


@pytest.mark.parametrize(
    "targets",
    [
        {"target_sets": 0},
        {"target_reps_min": -1},
        {"target_reps_max": -1},
        {"target_reps_min": 10, "target_reps_max": 8},
        {"target_duration_s": 0},
        {"target_distance_m": 0},
    ],
)
def test_template_slot_targets_are_checked(connection: sa.Connection, targets: dict[str, int]) -> None:
    template_id = _template(connection)
    _refused(
        connection,
        schema.template_slot,
        template_id=template_id,
        position=1,
        movement_pattern="push",
        **targets,
    )


def test_template_slot_targets_at_their_bounds(connection: sa.Connection) -> None:
    targets = {"target_sets": 1, "target_reps_min": 0, "target_reps_max": 0, "target_duration_s": 1}
    _insert(
        connection,
        schema.template_slot,
        template_id=_template(connection),
        position=1,
        movement_pattern="push",
        target_distance_m=1,
        **targets,
    )


def test_slot_option_is_unique_per_slot(connection: sa.Connection) -> None:
    slot_id = _insert(
        connection,
        schema.template_slot,
        template_id=_template(connection),
        position=1,
        movement_pattern="pull",
    )
    exercise_id = _exercise(connection)
    option = schema.template_slot_option
    _insert(connection, option, template_slot_id=slot_id, exercise_id=exercise_id, position=1)
    _refused(connection, option, template_slot_id=slot_id, exercise_id=exercise_id, position=2)


@pytest.mark.parametrize(
    ("status", "ended_at"),
    [("open", NOW), ("closed", None)],
)
def test_session_status_matches_its_end(connection: sa.Connection, status: str, ended_at: str | None) -> None:
    row = {
        "user_id": 1,
        "local_date": "2026-11-03",
        "time_zone": "UTC",
        "started_at": NOW,
        "location": "gym",
        "status": status,
        "ended_at": ended_at,
    }
    _refused(connection, schema.session, **row)


def test_session_status_vocabulary(connection: sa.Connection) -> None:
    _session(connection, status="open", ended_at=None)
    _session(connection)
    _refused(
        connection,
        schema.session,
        user_id=1,
        local_date="2026-11-03",
        time_zone="UTC",
        started_at=NOW,
        location="gym",
        status="paused",
    )


def test_session_location_both_is_refused(connection: sa.Connection) -> None:
    table, row = _row_with(connection, "session.location", "both")
    _refused(connection, table, **row)


def test_soft_deleted_open_session_frees_the_slot_and_users_are_independent(
    connection: sa.Connection,
) -> None:
    _session(connection, status="open", ended_at=None, deleted_at=NOW)
    _session(connection, status="open", ended_at=None)
    _session(connection, status="open", ended_at=None, user_id=2)
    _session(connection)  # closed sessions are unlimited


@pytest.mark.parametrize("column", ["reps", "weight_g", "duration_s", "distance_m"])
def test_set_quantities_are_non_negative_integers(connection: sa.Connection, column: str) -> None:
    session_exercise_id = _session_exercise(connection)
    _insert(connection, schema.set_entry, session_exercise_id=session_exercise_id, position=1, **{column: 0})
    _refused(
        connection, schema.set_entry, session_exercise_id=session_exercise_id, position=2, **{column: -1}
    )


def test_set_type_defaults_to_work(connection: sa.Connection) -> None:
    set_id = _insert(
        connection, schema.set_entry, session_exercise_id=_session_exercise(connection), position=1
    )
    kind = connection.execute(sa.select(schema.set_entry.c.type).where(schema.set_entry.c.id == set_id))
    assert kind.scalar_one() == "work"


@pytest.mark.parametrize("table", [schema.exercise_setting, schema.set_value])
def test_value_tables_need_exactly_one_value(connection: sa.Connection, table: sa.Table) -> None:
    session_exercise_id = _session_exercise(connection)
    owner = (
        {"session_exercise_id": session_exercise_id}
        if table is schema.exercise_setting
        else {
            "set_entry_id": _insert(
                connection, schema.set_entry, session_exercise_id=session_exercise_id, position=1
            )
        }
    )
    first, second = _variable(connection, "a"), _variable(connection, "b")
    _refused(connection, table, **owner, variable_id=first)
    _refused(connection, table, **owner, variable_id=first, value_int=1, value_text="low")
    _insert(connection, table, **owner, variable_id=first, value_int=3)
    _insert(connection, table, **owner, variable_id=second, value_text="low")
    _refused(connection, table, **owner, variable_id=first, value_int=4)  # one value per variable
    _refused(connection, table, **{**owner, **dict.fromkeys(owner, 999)}, variable_id=first, value_int=1)
    _refused(connection, table, **owner, variable_id=999, value_int=1)


@pytest.mark.parametrize(("n", "weight_g"), [(0, 100000), (1, 0), (1, -5)])
def test_measured_rm_rules(connection: sa.Connection, n: int, weight_g: int) -> None:
    row = {"user_id": 1, "exercise_id": _exercise(connection), "measured_on": "2026-11-03", "created_at": NOW}
    _insert(connection, schema.rm_measured, **row, n=1, weight_g=1)
    _refused(connection, schema.rm_measured, **row, n=n, weight_g=weight_g)


def test_device_names_and_tokens(connection: sa.Connection) -> None:
    device = schema.device
    first = _insert(connection, device, user_id=1, name="iPhone", token_hash="h1", created_at=NOW)
    _refused(connection, device, user_id=1, name="iPhone", token_hash="h2", created_at=NOW)
    _refused(connection, device, user_id=1, name="Mac", token_hash="h1", created_at=NOW)
    connection.execute(sa.update(device).where(device.c.id == first).values(revoked_at=NOW))
    _insert(connection, device, user_id=1, name="iPhone", token_hash="h3", created_at=NOW)
    _insert(connection, device, user_id=1, name="Mac", created_at=NOW)
    _insert(connection, device, user_id=1, name="iPad", created_at=NOW)  # several devices without token


def test_pairing_code_rules(connection: sa.Connection) -> None:
    device_id = _insert(connection, schema.device, user_id=1, name="iPhone", created_at=NOW)
    row = {"device_id": device_id, "code_hash": "c", "expires_at": NOW}
    code_id = _insert(connection, schema.pairing_code, **row)
    attempts = connection.execute(
        sa.select(schema.pairing_code.c.attempts).where(schema.pairing_code.c.id == code_id)
    ).scalar_one()
    assert attempts == 0
    _refused(connection, schema.pairing_code, **row, attempts=-1)
    _refused(connection, schema.pairing_code, **{**row, "device_id": 999})


def test_app_setting_key_is_unique_per_user(connection: sa.Connection) -> None:
    _insert(connection, schema.app_setting, user_id=1, key="time_zone", value="Europe/Paris")
    _insert(connection, schema.app_setting, user_id=2, key="time_zone", value="UTC")
    _refused(connection, schema.app_setting, user_id=1, key="time_zone", value="UTC")


@pytest.mark.parametrize(
    "table",
    [table for table in schema.metadata.sorted_tables if any(c.name == "user_id" for c in table.columns)],
    ids=lambda table: table.name,
)
def test_root_tables_require_a_user(connection: sa.Connection, table: sa.Table) -> None:
    del connection
    assert table.c.user_id.nullable is False


def test_archived_and_deleted_markers_are_nullable_text() -> None:
    for table in schema.metadata.sorted_tables:
        for column in table.columns:
            if column.name in {"archived_at", "deleted_at", "revoked_at"}:
                assert column.nullable, f"{table.name}.{column.name}"
                assert isinstance(column.type, sa.Text)
