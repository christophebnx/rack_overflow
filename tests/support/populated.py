"""A small database holding a row in every table (L6 export and restore tests): the seeded
catalog, variables of each kind (enum with a retired key, decimal, setting, text), an archived
exercise, variable and template, a removed slot, closed, open and soft-deleted sessions with
settings, set values and a soft-deleted set, live and deleted measured RMs, app settings, a paired
device, a revoked one and their pairing codes, and text that CSV must quote (`;`, quotes, a
newline). Written through the services and the storage queries, like the app writes them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import ValueInput
from rack_overflow.domain.timestamps import to_text
from rack_overflow.services import devices, exercises, progress, seed, templates, variables
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.templates import TemplateForm
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import rm, schema
from rack_overflow.storage import sessions as queries

USER = 1
NOW = datetime(2026, 11, 3, 18, 42, tzinfo=UTC)
QUOTED_NOTE = 'Prise « large »; "serrée"\nsuite'


def _variables(engine: Engine) -> dict[str, int]:
    grip = variables.create(
        engine,
        USER,
        VariableForm(
            label="Prise",
            var_type="enum",
            scope="set",
            values=(ValueInput("Large"), ValueInput("Serrée"), ValueInput("Neutre")),
        ),
    )
    keys = sorted(variables.get_detail(engine, USER, grip).draft.enum_values, key=lambda value: value.label)
    neutral = next(value.key for value in keys if value.label == "Neutre")
    variables.update(
        engine,
        USER,
        grip,
        VariableForm(
            label="Prise",
            var_type="enum",
            scope="set",
            values=tuple(ValueInput(value.label, value.key, value.key == neutral) for value in keys),
        ),
    )
    return {
        "grip": grip,
        "tempo": variables.create(
            engine, USER, VariableForm(label="Tempo", var_type="decimal", scope="set", unit="s", scale="1")
        ),
        "seat": variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting")),
        "remark": variables.create(
            engine, USER, VariableForm(label="Remarque", var_type="text", scope="set")
        ),
        "old": variables.create(engine, USER, VariableForm(label="Ancienne", var_type="bool", scope="set")),
    }


def _catalog(engine: Engine, ids: dict[str, int]) -> int:
    """The custom exercise (fields of every variable) and the archived catalog rows."""
    press = exercises.create(
        engine, USER, ExerciseForm(name="Presse « test »; maison", category="strength", location="both")
    )
    for key in ("grip", "tempo", "seat", "remark"):
        exercises.add_field(engine, USER, press, variable_id=ids[key])
    exercises.add_alias(engine, USER, press, 'presse "maison"')
    variables.set_archived(engine, USER, ids["old"], NOW)
    archived = exercises.create(engine, USER, ExerciseForm(name="Ancien", category="cardio", location="gym"))
    exercises.set_archived(engine, USER, archived, NOW)
    template = templates.create(engine, USER, TemplateForm(name="Essai", location="gym"))
    templates.add_slot(engine, USER, template, kind="exercise", exercise_id=press)
    removed = templates.add_slot(engine, USER, template, kind="menu", exercise_id=press, label="Tirage")
    templates.remove_slot(engine, USER, template, removed, NOW)
    templates.set_archived(engine, USER, template, NOW)
    return press


def _session(connection: sa.Connection, day: int, *, location: str = "gym") -> int:
    started = NOW - timedelta(days=day)
    return queries.insert_session(
        connection,
        USER,
        local_date=started.date().isoformat(),
        time_zone="Europe/Brussels",
        started_at=to_text(started),
        location=location,
        template_id=None,
    )


def _history(engine: Engine, press: int, ids: dict[str, int]) -> None:
    grip_key = variables.get_detail(engine, USER, ids["grip"]).draft.enum_values[0].key
    with engine.begin() as connection:
        closed = _session(connection, 3)
        row = queries.insert_session_exercise(connection, closed, press, None)
        queries.upsert_settings(connection, row, {ids["seat"]: 4})
        for number in range(3):
            core = {"reps": 8 + number, "weight": 62500 + number * 2500}
            set_id = queries.insert_set(
                connection, row, set_type="work", core=core, completed_at=to_text(NOW - timedelta(days=3))
            )
            queries.insert_set_values(
                connection, set_id, {ids["grip"]: grip_key, ids["tempo"]: 25, ids["remark"]: QUOTED_NOTE}
            )
        queries.soft_delete_set(connection, set_id, to_text(NOW - timedelta(days=2)))
        queries.close_session(connection, closed, to_text(NOW - timedelta(days=3, hours=-1)))
        connection.execute(
            sa.update(schema.session).where(schema.session.c.id == closed).values(notes=QUOTED_NOTE)
        )
        deleted = _session(connection, 2, location="home")
        queries.insert_session_exercise(connection, deleted, press, None)
        queries.close_session(connection, deleted, to_text(NOW - timedelta(days=2)))
        queries.soft_delete_session(connection, deleted, to_text(NOW - timedelta(days=1)))
        _session(connection, 0)
        live = rm.insert_measured(
            connection, USER, press, n=1, weight_g=100000, measured_on="2026-10-01", created_at=to_text(NOW)
        )
        gone = rm.insert_measured(
            connection, USER, press, n=3, weight_g=90000, measured_on="2026-10-02", created_at=to_text(NOW)
        )
        rm.soft_delete_measured(connection, gone, to_text(NOW))
        del live


def _devices(engine: Engine) -> None:
    code = devices.add_device(engine, "iPhone", NOW).code
    devices.pair(engine, code, NOW)
    devices.add_device(engine, "Ancien", NOW)
    devices.revoke_device(engine, "Ancien", NOW)


def populate(engine: Engine) -> None:
    """Write the rows described in the module docstring into a migrated, empty database."""
    seed.seed_catalog(engine, USER)
    ids = _variables(engine)
    press = _catalog(engine, ids)
    _history(engine, press, ids)
    progress.set_formula(engine, USER, "brzycki")
    _devices(engine)
