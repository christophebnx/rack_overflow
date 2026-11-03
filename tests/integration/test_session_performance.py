"""Set confirmation time on one year of simulated history (roadmap L4 "Done when", D-066): the
full request through the TestClient (paired device, every middleware), median < 100 ms.

It runs in the default parallel invocation: the median of 30 confirmations ignores the odd request
slowed by a disk flush or a busy worker (measured about 15-20 ms under `-n auto`), so no
per-request maximum is asserted (L4 fix loop 2). To time it alone:
`uv run pytest -q tests/integration/test_session_performance.py`."""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.domain.timestamps import to_text
from rack_overflow.services import exercises, seed, sessions, variables
from rack_overflow.services.sessions import SessionView
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import schema as s
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
CONFIRMATIONS = 30
MEDIAN_LIMIT_S = 0.100
START = datetime(2025, 11, 3, 17, 0, tzinfo=UTC)


def _ids(engine: Engine) -> list[int]:
    by_name = {e.draft.name: e.id for e in exercises.list_exercises(engine, USER)}
    return [by_name[name] for name in EXERCISES]


def _history(engine: Engine, exercise_ids: list[int], seat: int, resistance: int) -> int:
    """One year of closed sessions written through `storage` in one transaction; the set count."""
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
            for exercise_id in exercise_ids:
                row = queries.insert_session_exercise(connection, session_id, exercise_id, None)
                if exercise_id == exercise_ids[3]:
                    queries.upsert_settings(connection, row, {seat: 4 + index % 3})
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
                    if exercise_id == exercise_ids[0]:
                        queries.insert_set_values(connection, set_id, {resistance: number})
                    count += 1
            queries.close_session(connection, session_id, to_text(started + timedelta(hours=1)))
    return count


@pytest.mark.real_fsync(reason="the target is measured with the production synchronous mode")
def test_set_confirmation_median_below_100_ms(client: TestClient, migrated_engine: Engine) -> None:
    engine = migrated_engine
    seed.seed_catalog(engine, USER)
    exercise_ids = _ids(engine)
    seat = variables.create(engine, USER, VariableForm(label="Siège", var_type="int", scope="setting"))
    resistance = variables.create(engine, USER, VariableForm(label="Prise", var_type="int", scope="set"))
    exercises.add_field(engine, USER, exercise_ids[3], variable_id=seat)
    exercises.add_field(engine, USER, exercise_ids[0], variable_id=resistance)
    assert _history(engine, exercise_ids, seat, resistance) >= 5000
    session_id = sessions.start(engine, USER, None, "gym", datetime(2026, 11, 3, 17, tzinfo=UTC), UTC)
    rows = []
    for exercise_id in exercise_ids:
        picked = sessions.pick(engine, USER, session_id, None, exercise_id)
        assert isinstance(picked, SessionView) and picked.block is not None
        rows.append(picked.block.id)
    warm_up = {"session_exercise_id": str(rows[-1]), "type": "work", "reps": "8", "weight": "60"}
    headers = {"hx-request": "true"}
    assert client.post(f"/seances/{session_id}/series", json=warm_up, headers=headers).is_success
    timings: list[float] = []  # after one untimed request: templates compiled, caches warm
    for index in range(CONFIRMATIONS):
        row = rows[index % len(rows)]
        body = {"session_exercise_id": str(row), "type": "work", "reps": "8", "weight": "62,5"}
        started = time.perf_counter()
        response = client.post(f"/seances/{session_id}/series", json=body, headers={"hx-request": "true"})
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    with engine.begin() as connection:
        total = connection.execute(sa.select(sa.func.count()).select_from(s.set_entry)).scalar_one()
    assert total >= 5000 + CONFIRMATIONS + 1
    median = statistics.median(timings)
    assert median < MEDIAN_LIMIT_S, f"median {median * 1000:.1f} ms"
