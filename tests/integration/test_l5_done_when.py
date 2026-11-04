"""The L5 "Done when" criteria of docs/roadmap.md as scenarios through the web entry points (the
paired TestClient on a migrated temporary database): formula change, measured RM vs estimate and
the flag, estimation exclusions, corrections and session delete reaching every indicator. The
chart timing criterion is `test_progress_performance.py` (and the browser check in `tests/e2e`)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from rack_overflow.services import exercises, sessions
from rack_overflow.services.exercises import ExerciseForm
from rack_overflow.services.sessions import SessionView, SummaryView
from rack_overflow.storage import schema as s
from rack_overflow.web.app import CATALOG
from rack_overflow.web.locale import load_catalog

TEXT = load_catalog(CATALOG).text
PAGE = {"accept": "text/html"}
HTMX = {"hx-request": "true"}
USER = 1
NBSP = "\u00a0"
TIMES = "\u00d7"
NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)  # the TestClient clock


def make(engine: Engine, name: str = "Squat", category: str = "strength") -> int:
    return exercises.create(engine, USER, ExerciseForm(name, category, "gym"))


def logged(engine: Engine, when: datetime, exercise_id: int, items: list[tuple[str, int, str]]) -> int:
    """A closed free session at `when` with sets `(type, reps, kg)` of one exercise."""
    session_id = sessions.start(engine, USER, None, "gym", when, UTC)
    block = sessions.pick(engine, USER, session_id, None, exercise_id).block
    assert block is not None
    for number, (kind, reps, kg) in enumerate(items, start=1):
        values = {"reps": str(reps), "weight": kg}
        sessions.confirm_set(
            engine, USER, session_id, block.id, kind, values, when + timedelta(minutes=number)
        )
    sessions.close(engine, USER, session_id, when + timedelta(hours=1))
    return session_id


def set_ids(engine: Engine, session_id: int) -> list[int]:
    found = sessions.show(engine, USER, session_id)
    assert isinstance(found, SummaryView)
    return [item.id for item in found.rows[0].sets]


def chart(client: TestClient, exercise_id: int) -> dict[str, object]:
    response = client.get(f"/api/progression/{exercise_id}")
    assert response.status_code == 200
    data: dict[str, object] = response.json()
    return data


def series(client: TestClient, exercise_id: int) -> dict[str, list[float | None]]:
    data = chart(client, exercise_id)
    found = data["series"]
    assert isinstance(found, list)
    return {item["label"]: item["values"] for item in found}


def pair(reps: int, load: str) -> str:
    return f"{reps}{NBSP}{TIMES}{NBSP}{load}{NBSP}kg"


def kg(value: str) -> str:
    return f"{value}{NBSP}kg"


def stored(engine: Engine) -> tuple[object, ...]:
    """Every stored fact the formula must never rewrite."""
    with engine.begin() as connection:
        return tuple(
            tuple(tuple(row) for row in connection.execute(sa.select(table).order_by(table.c.id)))
            for table in (s.rm_measured, s.set_entry)
        )


# --- changing the formula recomputes estimates without touching measured RMs


def test_changing_the_formula_recomputes_estimates_only(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=20), squat, [("rm_test", 3, "110")])
    logged(migrated_engine, NOW - timedelta(days=10), squat, [("work", 10, "80")])
    saved = client.post(f"/rm/{squat}", json={"n": "1", "weight": "120", "date": "2026-10-01"}, headers=HTMX)
    assert saved.status_code == 200
    before_facts = stored(migrated_engine)
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    assert TEXT("rm.estimate_beside", formula="Epley", value=kg("106,7")) in page
    assert TEXT("rm.origin.manual", date="01/10/2026") in page
    estimates = {
        "epley": "106,7",
        "brzycki": "106,7",
        "lombardi": "100,7",
        "oconner": "100",
        "wathan": "107,8",
    }
    for formula, value in estimates.items():
        answer = client.patch("/reglages", json={"rm_formula": formula}, headers=HTMX)
        assert answer.status_code == 200 and 'data-kind="ok"' in answer.text
        name = TEXT(f"rm.formula.{formula}")
        page = client.get(f"/progression/{squat}", headers=PAGE).text
        assert TEXT("rm.estimate_beside", formula=name, value=kg(value)) in page
        # the measured 1RM and the 3RM test stay what was measured
        assert TEXT("rm.origin.manual", date="01/10/2026") in page and kg("120") in page
        assert TEXT("rm.origin.rm_test", date="14/10/2026") in page and kg("110") in page
        labels = series(client, squat)
        assert labels[TEXT("progress.series.e1rm", formula=name)] == [None, float(value.replace(",", "."))]
        assert labels[TEXT("progress.series.measured_1rm")] == [120.0, None]
    assert stored(migrated_engine) == before_facts


def test_a_refused_formula_changes_nothing(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=1), squat, [("work", 5, "100")])
    client.patch("/reglages", json={"rm_formula": "wathan"}, headers=HTMX)
    refused = client.patch("/reglages", json={"rm_formula": "Epley"}, headers=HTMX)
    assert refused.status_code == 200 and 'aria-describedby="reglages-formule-erreur"' in refused.text
    assert TEXT("catalog.error.invalid_choice") in refused.text
    assert client.patch("/reglages", json={}, headers=HTMX).status_code == 200
    page = client.get("/reglages", headers=PAGE).text
    assert re.findall(r'value="(\w+)" id="formule-\w+" checked', page) == ["wathan"]
    assert TEXT("rm.formula.wathan") in client.get(f"/progression/{squat}", headers=PAGE).text


# --- a measured RM wins over an estimate; an estimate above an older test is flagged


def test_measured_wins_and_only_an_older_test_is_flagged(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=30), squat, [("rm_test", 1, "110")])  # 04/10
    logged(migrated_engine, NOW - timedelta(days=5), squat, [("work", 5, "100")])  # e1RM 116,7 on 29/10
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    rm = page[page.index('id="rm"') :]
    assert TEXT("rm.origin.rm_test", date="04/10/2026") in rm
    assert rm.index(kg("110")) < rm.index(TEXT("rm.estimate_beside", formula="Epley", value=kg("116,7")))
    assert TEXT("rm.flag", date="04/10/2026") in rm
    # a newer manual test, below the estimate: it wins and nothing is flagged
    client.post(f"/rm/{squat}", json={"n": "1", "weight": "112,5", "date": "2026-11-02"}, headers=HTMX)
    rm = client.get(f"/rm/{squat}", headers=HTMX).text
    assert TEXT("rm.origin.manual", date="02/11/2026") in rm and kg("112,5") in rm
    assert TEXT("rm.flag", date="02/11/2026") not in rm and TEXT("rm.flag", date="04/10/2026") not in rm
    # deleting that measure brings the older, overtaken test back with its flag
    measure = client.get(f"/progression/{squat}", headers=PAGE).text
    assert "/rm/mesures/" in measure
    measured_id = measure.split('hx-delete="/rm/mesures/')[1].split('"')[0]
    deleted = client.request("DELETE", f"/rm/mesures/{measured_id}", json={}, headers=HTMX)
    assert deleted.status_code == 200 and TEXT("rm.flag", date="04/10/2026") in deleted.text
    with migrated_engine.begin() as connection:
        row = connection.execute(sa.select(s.rm_measured.c.deleted_at)).scalar_one()
    assert row is not None  # soft delete


def test_one_write_per_fact_for_tests_and_manual_entries(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    session_id = logged(migrated_engine, NOW - timedelta(days=3), squat, [("rm_test", 1, "120")])
    client.post(f"/rm/{squat}", json={"n": "3", "weight": "105", "date": "2026-11-01"}, headers=HTMX)
    with migrated_engine.begin() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(s.rm_measured)).scalar_one() == 1
        assert connection.execute(sa.select(sa.func.count()).select_from(s.set_entry)).scalar_one() == 1
    rm = client.get(f"/rm/{squat}", headers=HTMX).text
    assert (
        TEXT("rm.origin.rm_test", date="31/10/2026") in rm
        and TEXT("rm.origin.manual", date="01/11/2026") in rm
    )
    # correcting the RM-test set in its session corrects the measured 1RM (no copy elsewhere)
    test_set = set_ids(migrated_engine, session_id)[0]
    client.patch(f"/series/{test_set}", json={"type": "rm_test", "reps": "1", "weight": "125"}, headers=HTMX)
    rm = client.get(f"/rm/{squat}", headers=HTMX).text
    assert kg("125") in rm and kg("120") not in rm
    assert series(client, squat)[TEXT("progress.series.measured_1rm")] == [125.0]


# --- warm-ups and sets above 12 reps are excluded from estimation


def test_warm_ups_and_long_sets_are_not_estimated(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    logged(migrated_engine, NOW - timedelta(days=4), squat, [("warmup", 1, "200"), ("work", 15, "100")])
    only_excluded = client.get(f"/progression/{squat}", headers=PAGE).text
    assert TEXT("rm.no_data") in only_excluded
    assert chart(client, squat)["series"] == []
    logged(
        migrated_engine,
        NOW - timedelta(days=2),
        squat,
        [("warmup", 2, "180"), ("work", 12, "60"), ("work", 13, "90")],
    )
    labels = series(client, squat)
    assert labels == {TEXT("progress.series.e1rm", formula="Epley"): [84.0]}  # 12 x 60 kg only
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    assert TEXT("rm.origin.estimated", formula="Epley", set=pair(12, "60"), date="01/11/2026") in page
    # the records still keep the long set (13 et plus), never the warm-up
    assert TEXT("progress.reps_13_plus") in page and kg("200") not in page


# --- a corrected set changes the indicators


def test_a_corrected_closed_set_changes_every_indicator(client: TestClient, migrated_engine: Engine) -> None:
    squat = make(migrated_engine)
    first = logged(migrated_engine, NOW - timedelta(days=9), squat, [("work", 5, "100")])
    second = logged(migrated_engine, NOW - timedelta(days=2), squat, [("work", 5, "90"), ("work", 15, "60")])
    assert series(client, squat)[TEXT("progress.series.e1rm", formula="Epley")] == [116.7, 105.0]
    short, long = set_ids(migrated_engine, second)
    # an excluded set corrected into the estimable range starts feeding the estimate
    answer = client.patch(
        f"/series/{long}", json={"type": "work", "reps": "8", "weight": "110"}, headers=HTMX
    )
    assert answer.status_code == 200 and "HX-Redirect" not in answer.headers
    assert TEXT("session.record") in answer.text
    assert series(client, squat)[TEXT("progress.series.e1rm", formula="Epley")] == [116.7, 139.3]
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    assert TEXT("rm.origin.estimated", formula="Epley", set=pair(8, "110"), date="01/11/2026") in page
    # turned into a warm-up, it leaves the estimate, the records and the volume
    client.patch(f"/series/{long}", json={"type": "warmup", "reps": "8", "weight": "110"}, headers=HTMX)
    assert series(client, squat)[TEXT("progress.series.e1rm", formula="Epley")] == [116.7, 105.0]
    found = sessions.show(migrated_engine, USER, second)
    assert isinstance(found, SummaryView) and found.rows[0].volume.load_g == 450000
    # the corrected set also changes the next session's prefill (last performance)
    client.patch(f"/series/{short}", json={"type": "work", "reps": "6", "weight": "92,5"}, headers=HTMX)
    upcoming = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    block = sessions.pick(migrated_engine, USER, upcoming, None, squat).block
    assert block is not None and block.form.texts["weight"] == "92,5" and block.form.texts["reps"] == "6"
    assert first != second


# --- a deleted session disappears from history and indicators but stays in the database


def test_a_deleted_session_leaves_every_reader_and_stays_stored(
    client: TestClient, migrated_engine: Engine
) -> None:
    squat = make(migrated_engine)
    kept = logged(migrated_engine, NOW - timedelta(days=9), squat, [("work", 5, "100")])
    best = logged(
        migrated_engine, NOW - timedelta(days=5), squat, [("work", 5, "130"), ("rm_test", 1, "150")]
    )
    later = logged(migrated_engine, NOW - timedelta(days=1), squat, [("work", 5, "110")])
    found = sessions.show(migrated_engine, USER, later)
    assert isinstance(found, SummaryView) and not found.rows[0].sets[0].record  # below the 130 kg
    assert client.request("DELETE", f"/seances/{best}", json={}, headers=HTMX).status_code == 204
    history = client.get("/historique", headers=PAGE).text
    assert f'href="/seances/{best}"' not in history and f'href="/seances/{kept}"' in history
    assert TEXT("history.this_week", count=1) in history  # only `later` (02/11) is in this week
    data = chart(client, squat)
    assert data["labels"] == ["25/10", "02/11"]
    assert series(client, squat) == {TEXT("progress.series.e1rm", formula="Epley"): [116.7, 128.3]}
    page = client.get(f"/progression/{squat}", headers=PAGE).text
    assert (
        kg("150") not in page
        and kg("130") not in page
        and TEXT("rm.origin.rm_test", date="29/10/2026") not in page
    )
    # the star is recomputed: `later` is now a record against `kept` alone
    found = sessions.show(migrated_engine, USER, later)
    assert isinstance(found, SummaryView) and found.rows[0].sets[0].record
    assert client.get(f"/seances/{best}", headers=PAGE).status_code == 404
    with migrated_engine.begin() as connection:
        session_row = connection.execute(sa.select(s.session).where(s.session.c.id == best)).one()
        sets = (
            connection.execute(
                sa.select(s.set_entry.c.deleted_at)
                .join(s.session_exercise, s.session_exercise.c.id == s.set_entry.c.session_exercise_id)
                .where(s.session_exercise.c.session_id == best)
            )
            .scalars()
            .all()
        )
    assert session_row.deleted_at is not None and session_row.status == "closed"
    assert sets == [None, None]  # the sets are untouched: one fact, the session's flag


def test_a_deleted_session_leaves_the_prefill_and_the_progress_index(
    client: TestClient, migrated_engine: Engine
) -> None:
    squat, bench = make(migrated_engine), make(migrated_engine, "Bench")
    logged(migrated_engine, NOW - timedelta(days=9), squat, [("work", 5, "100")])
    only_bench = logged(migrated_engine, NOW - timedelta(days=3), bench, [("work", 5, "80")])
    newest = logged(migrated_engine, NOW - timedelta(days=2), squat, [("work", 3, "120")])
    client.request("DELETE", f"/seances/{newest}", json={}, headers=HTMX)
    client.request("DELETE", f"/seances/{only_bench}", json={}, headers=HTMX)
    index = client.get("/progression", headers=PAGE).text
    assert f'href="/progression/{squat}"' in index and f'href="/progression/{bench}"' not in index
    upcoming = sessions.start(migrated_engine, USER, None, "gym", NOW, UTC)
    block = sessions.pick(migrated_engine, USER, upcoming, None, squat).block
    assert block is not None and block.form.texts["weight"] == "100" and block.form.texts["reps"] == "5"
    shown = sessions.show(migrated_engine, USER, upcoming)
    assert isinstance(shown, SessionView)
    # the deleted session's corrections are refused: its sets are gone for every writer
    deleted_set = None
    with migrated_engine.begin() as connection:
        deleted_set = connection.execute(
            sa.select(s.set_entry.c.id)
            .join(s.session_exercise, s.session_exercise.c.id == s.set_entry.c.session_exercise_id)
            .where(s.session_exercise.c.session_id == newest)
        ).scalar_one()
    body = {"type": "work", "reps": "3", "weight": "125"}
    assert client.patch(f"/series/{deleted_set}", json=body, headers=HTMX).status_code == 404
    assert client.request("DELETE", f"/series/{deleted_set}", json={}, headers=HTMX).status_code == 404
