"""Progress and history timing on one year of simulated history (roadmap L5 "Done when", D-071):
the full requests through the TestClient (paired device, every middleware). The progress page
plus its chart JSON, for the busiest strength exercise and the run, and the history pages: median
of 10 rounds below 1 s each (measured in tens of milliseconds). Like the L4 test it runs in the
default parallel invocation, so only the median is asserted."""

from __future__ import annotations

import re
import statistics
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from support.history import build

ROUNDS = 10
MEDIAN_LIMIT_S = 1.0
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}


def median_of(request: Callable[[], None]) -> float:
    request()  # untimed: templates compiled, caches warm
    timings = []
    for _ in range(ROUNDS):
        started = time.perf_counter()
        request()
        timings.append(time.perf_counter() - started)
    return statistics.median(timings)


@pytest.mark.real_fsync(reason="the target is measured with the production synchronous mode")
def test_progress_and_history_medians_below_one_second(client: TestClient, migrated_engine: Engine) -> None:
    history = build(migrated_engine, tracking=True)
    assert history.sets >= 5000

    def pair(exercise_id: int) -> Callable[[], None]:
        def run() -> None:
            page = client.get(f"/progression/{exercise_id}", headers=PAGE)
            data = client.get(f"/api/progression/{exercise_id}")
            assert page.status_code == 200 and data.status_code == 200
            assert len(data.json()["labels"]) > 100

        return run

    for exercise_id in (history.exercise_ids[0], history.cardio_id):
        median = median_of(pair(exercise_id))
        assert median < MEDIAN_LIMIT_S, f"progress {exercise_id}: median {median * 1000:.1f} ms"

    first = client.get("/historique", headers=PAGE).text
    match = re.search(r'href="/historique\?avant=(\d+)"', first)
    assert match is not None
    for path, headers in (("/historique", PAGE), (f"/historique?avant={match.group(1)}", HTMX)):
        median = median_of(
            lambda path=path, headers=headers: client.get(path, headers=headers).raise_for_status()
        )
        assert median < MEDIAN_LIMIT_S, f"{path}: median {median * 1000:.1f} ms"
