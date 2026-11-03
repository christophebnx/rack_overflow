"""Session logging services on a seeded database (D-061 to D-066): start, menus, added exercises,
prefill across sessions, sets, records, settings, close and summary."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain.catalog import CatalogError
from rack_overflow.domain.errors import NotFoundError
from rack_overflow.domain.sessions import Item, SessionError
from rack_overflow.domain.text import normalise
from rack_overflow.services import exercises, seed, sessions, templates, variables
from rack_overflow.services.sessions import SessionView, SummaryView
from rack_overflow.services.variables import VariableForm
from rack_overflow.storage import schema as s
from rack_overflow.storage import sessions as session_queries
from rack_overflow.storage.errors import SessionOpenError

USER = 1
OTHER = 2
TZ = ZoneInfo("Europe/Brussels")
T0 = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)


@pytest.fixture
def engine(migrated_engine: Engine) -> Iterator[Engine]:
    seed.seed_catalog(migrated_engine, USER)
    yield migrated_engine


def template_id(engine: Engine, prefix: str) -> int:
    return next(t.id for t in templates.list_templates(engine, USER) if t.draft.name.startswith(prefix))


def exercise_id(engine: Engine, name: str) -> int:
    return next(
        e.id for e in exercises.list_exercises(engine, USER, include_archived=True) if e.draft.name == name
    )


def view(engine: Engine, session_id: int, requested: Item | None = None) -> SessionView:
    found = sessions.show(engine, USER, session_id, requested)
    assert isinstance(found, SessionView)
    return found


def names(found: SessionView) -> list[str]:
    return [found.name_of(item) for item in found.items]


def start_a(engine: Engine, now: datetime = T0) -> int:
    return sessions.start(engine, USER, template_id(engine, "Salle A"), "gym", now, TZ)


def row_of(found: SessionView, name: str) -> int:
    return next(row_id for row_id, card in found.cards.items() if card.exercise.name == name)


def confirm(
    engine: Engine, session_id: int, row_id: int, values: dict[str, str], now: datetime, kind: str = "work"
):
    return sessions.confirm_set(engine, USER, session_id, row_id, kind, values, now)


def menu_slot(found: SessionView, label: str) -> int:
    return next(slot_id for slot_id, menu in found.menus.items() if menu.label == label)


def option(found: SessionView, label: str, name: str) -> int:
    return next(o.id for o in found.menus[menu_slot(found, label)].options if o.name == name)


# --- start


def test_start_from_salle_a_writes_fixed_rows_and_leaves_menus_pending(engine: Engine) -> None:
    session_id = start_a(engine)
    found = view(engine, session_id)
    assert names(found) == [
        "Squat au rack (barre)",
        "Développé couché (barre)",
        "Tirage horizontal",
        "Jambes unilatéral",
        "Curl barre EZ",
        "Gainage",
    ]
    assert found.current == found.items[0]
    assert found.block is not None and found.block.exercise.name == "Squat au rack (barre)"
    assert found.session.title == "Salle A — Squat & poussée horizontale"
    assert (found.session.local_date, found.session.time_zone) == ("2026-11-03", "Europe/Brussels")
    assert found.session.started_at == "2026-11-03T17:00:00Z"
    assert len(found.cards) == 3 and len(found.menus) == 3
    assert found.block.form.type == "work"
    assert found.block.form.texts == {"reps": "6"}  # target reps min, no weight yet


def test_local_date_follows_the_configured_zone(engine: Engine) -> None:
    session_id = sessions.start(engine, USER, None, "home", datetime(2026, 11, 3, 23, 30, tzinfo=UTC), TZ)
    assert view(engine, session_id).session.local_date == "2026-11-04"


def test_start_while_open_returns_the_open_session(engine: Engine) -> None:
    first = start_a(engine)
    assert sessions.start(engine, USER, None, "home", T0, TZ) == first
    with engine.begin() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(s.session)).scalar_one() == 1


def test_start_race_on_the_unique_index_returns_the_open_session(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = start_a(engine)
    real = session_queries.open_session
    calls = iter([None])

    def first_miss(connection: sa.Connection, user_id: int) -> sa.Row | None:
        return next(calls, None) or real(connection, user_id)

    monkeypatch.setattr(session_queries, "open_session", first_miss)
    assert sessions.start(engine, USER, None, "gym", T0, TZ) == first


def test_insert_session_refuses_a_second_open_session(engine: Engine) -> None:
    start_a(engine)
    with engine.begin() as connection, pytest.raises(SessionOpenError):
        session_queries.insert_session(
            connection,
            USER,
            local_date="x",
            time_zone="UTC",
            started_at="x",
            location="gym",
            template_id=None,
        )


def test_start_refusals(engine: Engine) -> None:
    salle_a = template_id(engine, "Salle A")
    templates.set_archived(engine, USER, salle_a, T0)
    with pytest.raises(CatalogError) as error:
        sessions.start(engine, USER, salle_a, "moon", T0, TZ)
    assert [(p.field, p.code) for p in error.value.problems] == [
        ("location", "invalid_choice"),
        ("template_id", "template_unavailable"),
    ]
    with pytest.raises(CatalogError):
        sessions.start(engine, OTHER, template_id(engine, "Salle B"), "gym", T0, TZ)


def test_start_page(engine: Engine) -> None:
    page = sessions.start_page(engine, USER)
    assert page.open is None and page.location == "gym"
    assert [t.name.split(" — ")[0] for t in page.templates] == ["Salle A", "Salle B", "Maison", "Cardio"]
    assert not any(t.last_used for t in page.templates)
    assert page.offered("home") and page.offered("gym")
    session_id = sessions.start(engine, USER, template_id(engine, "Maison"), "home", T0, TZ)
    found = view(engine, session_id)
    open_page = sessions.start_page(engine, USER)
    assert open_page.open is not None and open_page.open.session.id == session_id
    assert (open_page.open.exercises, open_page.open.sets) == (0, 0)
    assert found.block is not None
    confirm(engine, session_id, found.block.id, {"reps": "10", "weight": "16"}, T0)
    open_page = sessions.start_page(engine, USER)
    assert open_page.open is not None and (open_page.open.exercises, open_page.open.sets) == (1, 1)
    sessions.close(engine, USER, session_id, T0 + timedelta(hours=1))
    after = sessions.start_page(engine, USER)
    assert after.location == "home"
    assert [t.last_used for t in after.templates] == [False, False, True, False]


def test_templates_skip_archived_slots_and_pick_lone_menu_options(engine: Engine) -> None:
    salle_a = template_id(engine, "Salle A")
    exercises.set_archived(engine, USER, exercise_id(engine, "Curl barre EZ"), T0)
    for name in ("Fentes haltères", "Split squat bulgare"):
        exercises.set_archived(engine, USER, exercise_id(engine, name), T0)
    session_id = sessions.start(engine, USER, salle_a, "gym", T0, TZ)
    found = view(engine, session_id)
    assert names(found) == [
        "Squat au rack (barre)",
        "Développé couché (barre)",
        "Tirage horizontal",
        "Presse à cuisses",  # the one available option, picked at start
        "Gainage",
    ]


# --- menus and added exercises


def test_pick_a_menu_option_and_refusals(engine: Engine) -> None:
    session_id = start_a(engine)
    found = view(engine, session_id)
    pull = menu_slot(found, "Tirage horizontal")
    seated = option(found, "Tirage horizontal", "Rowing assis machine")
    squat = exercise_id(engine, "Squat au rack (barre)")
    with pytest.raises(CatalogError) as error:
        sessions.pick(engine, USER, session_id, pull, squat)
    assert error.value.problems[0].code == "exercise_unavailable"
    picked = sessions.pick(engine, USER, session_id, pull, seated)
    assert picked.block is not None and picked.block.exercise.name == "Rowing assis machine"
    assert picked.current == Item(row_id=picked.block.id)
    assert names(picked)[2] == "Rowing assis machine"
    assert picked.block.menu_label == "Tirage horizontal"
    with pytest.raises(CatalogError) as error:
        sessions.pick(engine, USER, session_id, pull, seated)
    assert error.value.problems[0].code == "slot_already_picked"
    with pytest.raises(NotFoundError):
        sessions.pick(engine, USER, session_id, 9999, seated)


def test_change_a_pick_while_the_row_holds_no_fact(engine: Engine) -> None:
    session_id = start_a(engine)
    found = view(engine, session_id)
    pull = menu_slot(found, "Tirage horizontal")
    rowing = option(found, "Tirage horizontal", "Rowing barre au rack")
    cable = option(found, "Tirage horizontal", "Tirage horizontal poulie")
    picked = sessions.pick(engine, USER, session_id, pull, rowing)
    assert picked.block is not None
    row_id = picked.block.id
    assert {o.name for o in picked.block.change_options} == {
        "Rowing assis machine",
        "Tirage horizontal poulie",
    }
    changed = sessions.change_exercise(engine, USER, session_id, row_id, cable)
    assert changed.block is not None and changed.block.exercise.name == "Tirage horizontal poulie"
    with pytest.raises(CatalogError) as error:
        sessions.change_exercise(engine, USER, session_id, row_id, exercise_id(engine, "Planche"))
    assert error.value.problems[0].code == "exercise_unavailable"
    confirm(engine, session_id, row_id, {"reps": "10", "weight": "40"}, T0)
    with pytest.raises(CatalogError) as error:
        sessions.change_exercise(engine, USER, session_id, row_id, rowing)
    assert error.value.problems[0].code == "exercise_has_sets"
    fixed_row = row_of(changed, "Squat au rack (barre)")
    with pytest.raises(CatalogError):  # a fixed slot's row cannot change
        sessions.change_exercise(engine, USER, session_id, fixed_row, rowing)


def test_add_by_search_with_recent_first(engine: Engine) -> None:
    earlier = start_a(engine)
    curl = exercise_id(engine, "Curl barre EZ")
    sessions.close(engine, USER, earlier, T0 + timedelta(hours=1))
    free = sessions.start(engine, USER, None, "gym", T0 + timedelta(days=2), TZ)
    found = view(engine, free)
    assert found.items == () and found.block is None
    results = sessions.search_exercises(engine, USER, free, "")
    assert {e.name for e in results.recent} >= {"Curl barre EZ", "Squat au rack (barre)"}
    assert len(results.recent) == 3
    assert results.count == 41
    assert [e.name for e in results.others] == sorted((e.name for e in results.others), key=normalise)
    ranked = sessions.search_exercises(engine, USER, free, "curl")
    assert ranked.ranked[0].name == "Curl barre EZ" and not ranked.recent
    added = sessions.pick(engine, USER, free, None, curl)
    assert added.block is not None and added.block.card.slot_id is None
    again = sessions.pick(engine, USER, free, None, curl)  # twice: allowed
    assert len(again.cards) == 2
    exercises.set_archived(engine, USER, exercise_id(engine, "Planche"), T0)
    assert "Planche" not in {e.name for e in sessions.search_exercises(engine, USER, free, "").others}
    with pytest.raises(CatalogError):
        sessions.pick(engine, USER, free, None, exercise_id(engine, "Planche"))
    other_row = again.block.id if again.block else 0
    changed = sessions.change_exercise(
        engine, USER, free, other_row, exercise_id(engine, "Squat au rack (barre)")
    )
    assert changed.block is not None and changed.block.exercise.name == "Squat au rack (barre)"


# --- sets, prefill, records


def test_prefill_across_two_sessions_and_records(engine: Engine) -> None:
    first = start_a(engine)
    row = row_of(view(engine, first), "Squat au rack (barre)")
    plan = [("warmup", "10", "40"), ("work", "8", "60"), ("work", "8", "60"), ("work", "7", "60")]
    for minute, (kind, reps, kg) in enumerate(plan):
        confirm(engine, first, row, {"reps": reps, "weight": kg}, T0 + timedelta(minutes=minute), kind)
    sessions.close(engine, USER, first, T0 + timedelta(hours=1))

    second = start_a(engine, T0 + timedelta(days=3))
    found = view(engine, second)
    block = found.block
    assert block is not None and block.exercise.name == "Squat au rack (barre)"
    assert (block.form.type, block.form.texts) == ("warmup", {"reps": "10", "weight": "40"})
    now = T0 + timedelta(days=3, minutes=1)
    after_warmup = confirm(engine, second, block.id, {"reps": "10", "weight": "40"}, now, "warmup")
    assert not after_warmup.set.record
    next_form = after_warmup.view.block.form  # type: ignore[union-attr]
    assert (next_form.type, next_form.texts) == ("work", {"reps": "8", "weight": "60"})
    heavier = confirm(engine, second, block.id, {"reps": "8", "weight": "62,5"}, now + timedelta(minutes=1))
    assert heavier.set.record and heavier.set.number == 2
    carried = heavier.view.block.form  # type: ignore[union-attr]
    assert carried.texts == {"reps": "8", "weight": "62,5"}  # today's choice carries forward
    tie = confirm(engine, second, block.id, {"reps": "8", "weight": "62,5"}, now + timedelta(minutes=2))
    assert not tie.set.record
    # editing the earlier record makes the later tie a record
    edited = sessions.update_set(engine, USER, heavier.set.id, "work", {"reps": "8", "weight": "61"})
    assert edited.block is not None
    assert [s.record for s in edited.block.sets] == [False, True, True]
    deleted = sessions.delete_set(engine, USER, tie.set.id, now + timedelta(minutes=3))
    assert deleted.block is not None and [s.number for s in deleted.block.sets] == [1, 2]
    with engine.begin() as connection:
        stored = connection.execute(sa.select(s.set_entry.c.deleted_at).where(s.set_entry.c.id == tie.set.id))
        assert stored.scalar_one() is not None  # soft delete
    card = view(engine, second).cards[block.id]
    assert (card.set_count, card.record_count) == (2, 1)


def test_set_refusals_write_nothing(engine: Engine) -> None:
    session_id = start_a(engine)
    row = row_of(view(engine, session_id), "Squat au rack (barre)")
    with pytest.raises(CatalogError) as error:
        confirm(engine, session_id, row, {"reps": "", "weight": "abc"}, T0)
    assert [(p.field, p.code) for p in error.value.problems] == [
        ("reps", "required"),
        ("weight", "not_a_number"),
    ]
    with pytest.raises(NotFoundError):
        confirm(engine, session_id, 9999, {"reps": "8"}, T0)
    with engine.begin() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(s.set_entry)).scalar_one() == 0


def test_stepper_form_has_no_write(engine: Engine) -> None:
    session_id = start_a(engine)
    row = row_of(view(engine, session_id), "Squat au rack (barre)")
    stepped = sessions.set_form(
        engine, USER, session_id, row, "work", {"reps": "8", "weight": "60"}, "weight:up"
    )
    assert stepped.block is not None and stepped.block.form.texts == {"reps": "8", "weight": "62,5"}
    with engine.begin() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(s.set_entry)).scalar_one() == 0


def setting_variable(engine: Engine, label: str = "Siège") -> int:
    return variables.create(engine, USER, VariableForm(label=label, var_type="int", scope="setting"))


def test_settings_written_with_the_first_set_and_prefilled_next_time(engine: Engine) -> None:
    press = exercise_id(engine, "Presse à cuisses")
    seat = setting_variable(engine)
    exercises.add_field(engine, USER, press, variable_id=seat)
    first = sessions.start(engine, USER, None, "gym", T0, TZ)
    row = sessions.pick(engine, USER, first, None, press).block
    assert row is not None and row.settings == {} and [f.label for f in row.setting_fields] == ["Siège"]
    saved = sessions.save_settings(engine, USER, first, row.id, {f"var_{seat}": "4"})
    assert saved.block is not None and saved.block.settings == {seat: 4}
    assert saved.block.has_facts and saved.block.change_options == ()
    confirm(engine, first, row.id, {"reps": "10", "weight": "100"}, T0)
    sessions.close(engine, USER, first, T0 + timedelta(hours=1))

    second = sessions.start(engine, USER, None, "gym", T0 + timedelta(days=2), TZ)
    row2 = sessions.pick(engine, USER, second, None, press).block
    assert row2 is not None and row2.settings == {seat: 4}  # prefilled, not stored yet
    assert row2.form.texts == {"reps": "10", "weight": "100"}
    with engine.begin() as connection:
        assert session_queries.settings_of(connection, row2.id) == {}
    confirm(
        engine, second, row2.id, {"reps": "10", "weight": "105", f"var_{seat}": "9"}, T0 + timedelta(days=2)
    )
    with engine.begin() as connection:
        assert session_queries.settings_of(connection, row2.id) == {seat: 4}  # recomputed, not from the body
    cleared = sessions.save_settings(engine, USER, second, row2.id, {f"var_{seat}": ""})
    with engine.begin() as connection:
        assert session_queries.settings_of(connection, row2.id) == {}
    assert cleared.block is not None and cleared.block.settings == {seat: 4}  # prefill shown again
    with pytest.raises(CatalogError):
        sessions.save_settings(engine, USER, second, row2.id, {f"var_{seat}": "x"})


def test_measure_variables_are_stored_and_archived_ones_hidden(engine: Engine) -> None:
    bike = exercises.create(
        engine, USER, exercises.ExerciseForm(name="Vélo test", category="cardio", location="gym")
    )
    resistance = variables.create(engine, USER, VariableForm(label="Résistance", var_type="int", scope="set"))
    exercises.add_field(engine, USER, bike, variable_id=resistance)
    session_id = sessions.start(engine, USER, None, "gym", T0, TZ)
    row = sessions.pick(engine, USER, session_id, None, bike).block
    assert row is not None and [f.name for f in row.more_fields] == [f"var_{resistance}"]
    done = confirm(
        engine, session_id, row.id, {"duration": "30:00", "distance": "12", f"var_{resistance}": "8"}, T0
    )
    assert done.set.facts.values == {"duration": 1800, "distance": 12000, f"var_{resistance}": 8}
    variables.set_archived(engine, USER, resistance, T0)
    again = sessions.block(engine, USER, session_id, row.id).block
    assert again is not None and all(f.name != f"var_{resistance}" for f in again.fields)
    assert again.form.texts == {"duration": "30:00", "distance": "12"}


# --- close, summary, closed session


def test_close_and_summary(engine: Engine) -> None:
    session_id = start_a(engine)
    found = view(engine, session_id)
    squat = row_of(found, "Squat au rack (barre)")
    confirm(engine, session_id, squat, {"reps": "10", "weight": "40"}, T0, "warmup")
    confirm(engine, session_id, squat, {"reps": "8", "weight": "60"}, T0 + timedelta(minutes=2))
    plank_slot = menu_slot(found, "Gainage")
    plank = sessions.pick(engine, USER, session_id, plank_slot, option(found, "Gainage", "Planche")).block
    assert plank is not None
    assert plank.form.texts == {"duration": "0:30"}  # target duration part
    confirm(engine, session_id, plank.id, {"duration": "0:45"}, T0 + timedelta(minutes=5))
    assert sessions.unlogged_count(engine, USER, session_id) == 4
    sessions.close(engine, USER, session_id, T0 + timedelta(minutes=69))
    sessions.close(engine, USER, session_id, T0 + timedelta(hours=5))  # no-op
    summary = sessions.show(engine, USER, session_id)
    assert isinstance(summary, SummaryView)
    assert summary.session.ended_at == "2026-11-03T18:09:00Z"
    assert [r.exercise.name for r in summary.rows] == ["Squat au rack (barre)", "Planche"]
    assert summary.rows[0].warmups == 1 and summary.rows[0].volume.load_g == 480000
    assert summary.rows[1].volume.duration_s == 45
    assert (summary.total_sets, summary.total_load_g, summary.total_records) == (2, 480000, 0)
    with pytest.raises(SessionError) as closed:
        confirm(engine, session_id, squat, {"reps": "8", "weight": "60"}, T0)
    assert closed.value.code == "session_closed"
    for action in (
        lambda: sessions.pick(engine, USER, session_id, plank_slot, 1),
        lambda: sessions.save_settings(engine, USER, session_id, squat, {}),
        lambda: sessions.set_form(engine, USER, session_id, squat, "work", {}, None),
        lambda: sessions.unlogged_count(engine, USER, session_id),
        lambda: sessions.update_set(engine, USER, summary.rows[0].sets[1].id, "work", {"reps": "1"}),
        lambda: sessions.delete_set(engine, USER, summary.rows[0].sets[1].id, T0),
    ):
        with pytest.raises(SessionError):
            action()
    # L5 history corrections reuse the same services on a closed session
    corrected = summary.rows[0].sets[1].id
    sessions.update_set(engine, USER, corrected, "work", {"reps": "8", "weight": "65"}, require_open=False)
    assert sessions.locate_set(engine, USER, corrected).closed


def test_foreign_and_deleted_ids(engine: Engine) -> None:
    session_id = start_a(engine)
    row = row_of(view(engine, session_id), "Squat au rack (barre)")
    done = confirm(engine, session_id, row, {"reps": "8", "weight": "60"}, T0)
    for action in (
        lambda: sessions.show(engine, OTHER, session_id),
        lambda: sessions.confirm_set(engine, OTHER, session_id, row, "work", {"reps": "8"}, T0),
        lambda: sessions.update_set(engine, OTHER, done.set.id, "work", {"reps": "8"}),
        lambda: sessions.locate_set(engine, OTHER, done.set.id),
        lambda: sessions.search_exercises(engine, OTHER, session_id, ""),
    ):
        with pytest.raises(NotFoundError):
            action()
    sessions.delete_set(engine, USER, done.set.id, T0)
    with pytest.raises(NotFoundError):
        sessions.delete_set(engine, USER, done.set.id, T0)
    with engine.begin() as connection:
        connection.execute(sa.update(s.session).values(deleted_at="2026-11-03T20:00:00Z"))
    with pytest.raises(NotFoundError):
        sessions.show(engine, USER, session_id)


def test_requested_item_and_resume(engine: Engine) -> None:
    session_id = start_a(engine)
    found = view(engine, session_id)
    bench = row_of(found, "Développé couché (barre)")
    pull = menu_slot(found, "Tirage horizontal")
    assert view(engine, session_id, Item(menu_slot_id=pull)).current == Item(menu_slot_id=pull)
    assert view(engine, session_id, Item(row_id=9999)).current == found.items[0]
    confirm(engine, session_id, bench, {"reps": "8", "weight": "50"}, T0)
    resumed = view(engine, session_id)
    assert resumed.current == Item(row_id=bench)  # the row of the latest set
    assert resumed.next_after(resumed.current) == Item(menu_slot_id=pull)
    assert resumed.number_of(Item(menu_slot_id=pull)) == 3
