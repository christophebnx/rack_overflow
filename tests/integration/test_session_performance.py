"""Set confirmation time on one year of simulated history (roadmap L4 "Done when", D-066): the
full request through the TestClient (paired device, every middleware), median < 100 ms.

It runs in the default parallel invocation: the median of 30 confirmations ignores the odd request
slowed by a disk flush or a busy worker (measured about 15-20 ms under `-n auto`), so no
per-request maximum is asserted (L4 fix loop 2). To time it alone:
`uv run pytest -q tests/integration/test_session_performance.py`. The year of history is built by
`tests/support/history.py` (shared with the L5 progress test, D-071)."""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from support.history import USER, build

from rack_overflow.services import sessions
from rack_overflow.services.sessions import SessionView
from rack_overflow.storage import schema as s

CONFIRMATIONS = 30
MEDIAN_LIMIT_S = 0.100


@pytest.mark.real_fsync(reason="the target is measured with the production synchronous mode")
def test_set_confirmation_median_below_100_ms(client: TestClient, migrated_engine: Engine) -> None:
    engine = migrated_engine
    history = build(engine)
    exercise_ids = history.exercise_ids
    assert history.sets >= 5000
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
