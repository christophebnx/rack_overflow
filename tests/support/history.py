"""One year of simulated history (D-066, D-071), shared by the L4 set-confirmation and the L5
progress performance tests: 208 closed sessions of six seeded strength exercises, five sets each
(a warm-up, four work sets), one setting variable and one set variable, about 5 000 sets, written
through `storage` in one transaction. `tracking=True` adds what the progress pages read: an
outdoor run in every other session, a 1RM test on the squat every eighth session and a few
manual RMs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.timestamps import to_text
from rack_overflow.services import exercises, seed, variables
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import rm
from rack_overflow.storage import sessions as queries

USER = 1
WEEKS = 52
SESSIONS_PER_WEEK = 4
SETS_PER_EXERCISE = 4
EXERCISES = (
    "Squat au rack (barre)",
    "Développé couché (barre)",
    "Rowing barre au rack",
    "Presse à cuisses",
    "Curl barre EZ",
    "Développé militaire haltères",
)
CARDIO = "Course extérieure"
START = datetime(2025, 11, 3, 17, 0, tzinfo=UTC)


@dataclass(frozen=True)
class YearHistory:
    """What the builder wrote: the six strength exercise ids (squat first), the run's id, the
    setting and set variables, and the number of sets."""

    exercise_ids: list[int]
    cardio_id: int
    seat: int
    resistance: int
    sets: int


def _ids(engine: Engine) -> dict[str, int]:
    return {e.draft.name: e.id for e in exercises.list_exercises(engine, USER)}


def _strength_sets(
    connection: sa.Connection, history: YearHistory, session_id: int, index: int, started: datetime
) -> int:
    count = 0
    for exercise_id in history.exercise_ids:
        row = queries.insert_session_exercise(connection, session_id, exercise_id, None)
        if exercise_id == history.exercise_ids[3]:
            queries.upsert_settings(connection, row, {history.seat: 4 + index % 3})
        for number in range(SETS_PER_EXERCISE + 1):
            kind = "warmup" if number == 0 else "work"
            weight = 40000 + (index % 20) * 2500 + number * 1000
            set_id = queries.insert_set(
                connection,
                row,
                set_type=kind,
                core={"reps": 8, "weight": weight},
                completed_at=to_text(started + timedelta(minutes=number)),
            )
            if exercise_id == history.exercise_ids[0]:
                queries.insert_set_values(connection, set_id, {history.resistance: number})
            count += 1
    return count


def _tracking_sets(
    connection: sa.Connection, history: YearHistory, session_id: int, index: int, started: datetime
) -> int:
    count = 0
    later = to_text(started + timedelta(minutes=30))
    if index % 2 == 0:
        row = queries.insert_session_exercise(connection, session_id, history.cardio_id, None)
        core = {"duration": 1500 + index * 3, "distance": 5000 + (index % 10) * 100}
        queries.insert_set(connection, row, set_type="work", core=core, completed_at=later)
        count += 1
    if index % 8 == 0:
        squat_row = queries.session_exercises(connection, session_id)[0].id
        core = {"reps": 1, "weight": 100000 + index * 100}
        queries.insert_set(connection, squat_row, set_type="rm_test", core=core, completed_at=later)
        count += 1
    return count


def build(engine: Engine, *, tracking: bool = False) -> YearHistory:
    """Seed the catalog, add the variables and write the year (see the module docstring)."""
    seed.seed_catalog(engine, USER)
    by_name = _ids(engine)
    exercise_ids = [by_name[name] for name in EXERCISES]
    seat = variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting"))
    resistance = variables.create(engine, USER, VariableForm(label="Prise", var_type="int", scope="set"))
    exercises.add_field(engine, USER, exercise_ids[3], variable_id=seat)
    exercises.add_field(engine, USER, exercise_ids[0], variable_id=resistance)
    history = YearHistory(exercise_ids, by_name[CARDIO], seat, resistance, 0)
    count = 0
    with engine.begin() as connection:
        for index in range(WEEKS * SESSIONS_PER_WEEK):
            started = START + timedelta(days=index * 7 // SESSIONS_PER_WEEK, minutes=index)
            session_id = queries.insert_session(
                connection,
                USER,
                local_date=started.date().isoformat(),
                time_zone="Europe/Brussels",
                started_at=to_text(started),
                location="gym",
                template_id=None,
            )
            count += _strength_sets(connection, history, session_id, index, started)
            if tracking:
                count += _tracking_sets(connection, history, session_id, index, started)
            queries.close_session(connection, session_id, to_text(started + timedelta(hours=1)))
        if tracking:
            for month in range(1, 12, 3):
                day = (START + timedelta(days=30 * month)).date().isoformat()
                for n, weight in ((1, 110000 + month * 500), (5, 92500)):
                    rm.insert_measured(
                        connection,
                        USER,
                        exercise_ids[0],
                        n=n,
                        weight_g=weight,
                        measured_on=day,
                        created_at=day,
                    )
    return YearHistory(exercise_ids, history.cardio_id, seat, resistance, count)
