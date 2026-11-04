"""Edge cases of milestone L6 (tester): export of unusual values and of the CSV zip layout,
`rack export` refusals and atomicity, `GET /api/export` headers, `rack restore` refusals and
recoveries beyond the developer's tests, and a rendered audit of the forms that disable every
button (docs/ui-spec.md "L6 — Forms disable every button"). In-process CLI and TestClient,
temporary folders, the server probe replaced (no port is opened)."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest
import sqlalchemy as sa
import test_restore as restoring
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from support.export_loader import read_csv_zip
from support.migrations import upgrade_to
from support.populated import populate
from test_restore import ASIDE, NOW, assert_untouched, dump, restore, sha
from test_web_pages import assert_secure_page

from rack_overflow import __version__, cli
from rack_overflow.cli import main
from rack_overflow.config import Settings, load_settings
from rack_overflow.domain import export as rules
from rack_overflow.services import export
from rack_overflow.storage import backup, db, migrate
from rack_overflow.storage import export as contents

# The restore fixtures, shared with tests/integration/test_restore.py (`_quiet` is autouse).
_quiet = restoring._quiet
source = restoring.source
snapshot = restoring.snapshot
target = restoring.target
current = restoring.current

PAGE = {"accept": "text/html,application/xhtml+xml"}
UNICODE_NAME = "L\u2019haltère « été » 🏋️ Ωμέγα"
HUGE = 2**62
AWKWARD_NOTE = '  début\r\nfin; "x" \u2019  '


def _dump(engine: Engine) -> dict[str, list[dict[str, object]]]:
    with engine.begin() as connection:
        return contents.dump(connection)


@pytest.fixture
def awkward(migrated_engine: Engine) -> Engine:
    """The populated database, plus unicode names, huge integers, an empty text and a note with
    CR LF, `;`, quotes and surrounding spaces."""
    populate(migrated_engine)
    with migrated_engine.begin() as connection:
        connection.exec_driver_sql("UPDATE exercise SET name = ? WHERE name = 'Ancien'", (UNICODE_NAME,))
        connection.exec_driver_sql(
            "UPDATE set_entry SET weight_g = ?, duration_s = ?, distance_m = ? "
            "WHERE id = (SELECT min(id) FROM set_entry)",
            (HUGE, 10**9, 4 * 10**7),
        )
        connection.exec_driver_sql(
            "UPDATE session SET notes = '' WHERE id = (SELECT max(id) FROM session WHERE notes IS NULL)"
        )
        connection.exec_driver_sql(
            "UPDATE session SET notes = ? WHERE deleted_at IS NOT NULL", (AWKWARD_NOTE,)
        )
    return migrated_engine


# --- export contents


def test_unicode_huge_and_awkward_values_survive_the_json_export(awkward: Engine) -> None:
    data = export.export(awkward, "json", NOW, __version__).data
    assert UNICODE_NAME.encode() in data  # raw UTF-8, never \u escapes
    assert not data.startswith(b"\xef\xbb\xbf")  # the JSON has no BOM
    tables = rules.read_json(data)[1]
    assert tables == _dump(awkward)
    assert any(row["weight_g"] == HUGE for row in tables["set_entry"])
    notes = [row["notes"] for row in tables["session"]]
    assert "" in notes and AWKWARD_NOTE in notes
    assert None in [row["ended_at"] for row in tables["session"]]  # JSON tells "" from null


def test_unicode_huge_and_awkward_values_survive_the_csv_export(awkward: Engine) -> None:
    header, tables = read_csv_zip(export.export(awkward, "csv", NOW, __version__).data)
    expected = {
        name: [{key: None if value == "" else value for key, value in row.items()} for row in rows]
        for name, rows in _dump(awkward).items()
    }  # the documented CSV limit: an empty text reads back as no value
    assert tables == expected
    assert header["units"] == {"weight": "g", "duration": "s", "distance": "m"}


def test_csv_zip_layout(awkward: Engine) -> None:
    file = export.export(awkward, "csv", NOW, __version__)
    zipped = zipfile.ZipFile(io.BytesIO(file.data))
    assert zipped.testzip() is None
    columns = contents.exported_columns()
    assert zipped.namelist() == [rules.HEADER_ENTRY, *(f"{name}.csv" for name in columns)]
    assert not any(info.is_dir() for info in zipped.infolist())
    document = json.loads(export.export(awkward, "json", NOW, __version__).data)
    del document["tables"]
    assert json.loads(zipped.read(rules.HEADER_ENTRY)) == document
    for name, names in columns.items():
        raw = zipped.read(f"{name}.csv")
        assert raw.startswith(b"\xef\xbb\xbf" + ";".join(names).encode() + b"\r\n"), name
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
        assert all(len(row) == len(names) for row in rows), name
    exercises = zipped.read("exercise.csv").decode("utf-8-sig")
    assert UNICODE_NAME in exercises


def test_csv_export_holds_no_secret(awkward: Engine) -> None:
    with awkward.connect() as connection:
        hashes = [
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT token_hash FROM device WHERE token_hash IS NOT NULL "
                "UNION SELECT code_hash FROM pairing_code"
            )
        ]
    assert hashes
    zipped = zipfile.ZipFile(io.BytesIO(export.export(awkward, "csv", NOW, __version__).data))
    for entry in zipped.namelist():
        text = zipped.read(entry).decode("utf-8-sig")
        assert "token_hash" not in text and "code_hash" not in text, entry
        assert not any(value in text for value in hashes), entry


def test_empty_database_csv_has_every_table_header_only(migrated_engine: Engine) -> None:
    file = export.export(migrated_engine, "csv", NOW, __version__)
    assert file.rows == 0
    zipped = zipfile.ZipFile(io.BytesIO(file.data))
    for name, names in contents.exported_columns().items():
        assert zipped.read(f"{name}.csv") == b"\xef\xbb\xbf" + ";".join(names).encode() + b"\r\n"
    header = json.loads(zipped.read(rules.HEADER_ENTRY))
    assert header["format"] == rules.FORMAT and header["format_version"] == rules.FORMAT_VERSION
    assert header["schema_revision"] == migrate.head_revision()
    assert header["app_version"] == __version__


def test_export_of_an_older_database_names_its_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = db.create_engine(tmp_path / "old.sqlite")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to("0003"))
            migrate.upgrade_to_head(engine)
        meta = rules.read_json(export.export(engine, "json", NOW, __version__).data)[0]
    finally:
        engine.dispose()
    assert meta.schema_revision == "0003"


# --- rack export


@pytest.fixture
def config(settings_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert main(["migrate", "--config", str(settings_file)]) == 0
    capsys.readouterr()
    return str(settings_file)


def _temps(folder: Path) -> list[str]:
    return [path.name for path in folder.iterdir() if path.name.startswith(".tmp-")]


def test_export_write_failure_leaves_no_file(
    config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()

    def disk_full(source: object, target: object) -> None:
        del source, target
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", disk_full)
    assert main(["export", str(out / "x.json"), "--config", config]) == 1
    assert "cannot write" in capsys.readouterr().err
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "dangling symlink", "symlink to a file"])
def test_export_never_replaces_an_existing_name(
    config: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    target = tmp_path / "taken.json"
    precious = tmp_path / "precious.txt"
    precious.write_text("keep me", encoding="utf-8")
    if kind == "directory":
        target.mkdir()
    elif kind == "dangling symlink":
        target.symlink_to(tmp_path / "nowhere")
    else:
        target.symlink_to(precious)
    assert main(["export", str(target), "--config", config]) == 1
    assert "already exists" in capsys.readouterr().err
    assert precious.read_text(encoding="utf-8") == "keep me"
    assert target.is_symlink() or target.is_dir()
    assert _temps(tmp_path) == []


def test_export_without_a_database_writes_nothing(
    settings_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "x.json"
    assert main(["export", str(target), "--config", str(settings_file)]) == 1
    assert "run rack migrate" in capsys.readouterr().err
    assert not target.exists() and _temps(tmp_path) == []


def test_cli_and_web_exports_are_the_same_bytes(config: str, tmp_path: Path) -> None:
    target = tmp_path / "x.zip"
    assert main(["export", str(target), "--format", "csv", "--config", config]) == 0
    engine = db.create_engine(load_settings(Path(config)).database_path)
    try:
        assert target.read_bytes() == export.export(engine, "csv", NOW, __version__).data
    finally:
        engine.dispose()


# --- GET /api/export


def test_csv_download_is_a_valid_zip_with_the_security_headers(client: TestClient) -> None:
    response = client.get("/api/export?format=csv", headers=PAGE)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].endswith('-csv.zip"')
    assert response.headers["content-disposition"].isascii()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    zipped = zipfile.ZipFile(io.BytesIO(response.content))
    assert zipped.testzip() is None
    assert "device.csv" in zipped.namelist()


def test_json_download_content_type_is_utf8(client: TestClient) -> None:
    response = client.get("/api/export?format=json", headers=PAGE)
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.headers["content-disposition"].endswith('.json"')


def test_unknown_format_page_offers_no_retry(client: TestClient) -> None:
    page = client.get("/api/export?format=xml", headers=PAGE)
    assert_secure_page(page, 422)
    assert "/api/export?format=xml" not in page.text  # 4xx: no « Réessayer » (L1a)


def test_export_route_refuses_a_write_method(client: TestClient) -> None:
    response = client.post("/api/export?format=json", json={}, headers={"origin": "http://testserver"})
    assert response.status_code == 405
    assert b"rack-overflow-export" not in response.content


def test_several_formats_use_the_last_one_or_refuse(client: TestClient) -> None:
    response = client.get("/api/export?format=xml&format=json")
    assert response.status_code in {200, 422}
    if response.status_code == 200:
        assert rules.read_json(response.content)


# --- rack restore


def _config(settings: Settings) -> Path:
    return settings.storage.data_dir.parent / "settings.toml"


def _wal_set(dest: Path, scratch: Path) -> None:
    """A Rack Overflow database at `dest` in WAL mode whose last committed row (`app_setting`
    `latest`) is only in `dest-wal`, as a power cut or a restore's aside set leaves it."""
    scratch.mkdir()
    live = scratch / "live.sqlite"
    engine = db.create_engine(live)
    try:
        migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()  # schema checkpointed into the main file
    engine = db.create_engine(live)
    connection = engine.raw_connection()
    try:
        connection.driver_connection.execute("PRAGMA wal_autocheckpoint = 0")
        connection.driver_connection.execute(
            "INSERT INTO app_setting (user_id, key, value) VALUES (1, 'latest', 'in the wal')"
        )
        connection.driver_connection.commit()
        for suffix in ("", "-wal", "-shm"):
            shutil.copyfile(f"{live}{suffix}", f"{dest}{suffix}")
    finally:
        connection.close()
        engine.dispose()
    assert Path(f"{dest}-wal").stat().st_size > 0


def _latest(path: Path) -> object:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT value FROM app_setting WHERE key = 'latest'").fetchone()
    finally:
        connection.close()


def test_a_directory_snapshot_is_refused(
    current: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "folder.sqlite"
    folder.mkdir()
    statements, digest = dump(current), sha(current)
    assert restore(current.parent.parent / "settings.toml", folder) == 1
    assert "snapshot not found" in capsys.readouterr().err
    assert_untouched(current, statements, digest)


@pytest.mark.parametrize("kind", ["empty file", "empty alembic_version"])
def test_a_snapshot_without_revision_is_refused(
    current: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    bad = tmp_path / "bad.sqlite"
    if kind == "empty file":
        bad.write_bytes(b"")
    else:
        shutil.copyfile(current, bad)
        connection = sqlite3.connect(bad)
        connection.execute("PRAGMA journal_mode = DELETE")  # like a snapshot: no -wal involved
        connection.execute("DELETE FROM alembic_version")
        connection.commit()
        connection.close()
    statements, digest = dump(current), sha(current)
    assert restore(current.parent.parent / "settings.toml", bad) == 1
    assert "not a Rack Overflow database" in capsys.readouterr().err
    assert_untouched(current, statements, digest)


def test_a_symlink_to_the_database_is_refused(
    current: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link = tmp_path / "link.sqlite"
    link.symlink_to(current)
    statements, digest = dump(current), sha(current)
    assert restore(current.parent.parent / "settings.toml", link) == 1
    assert "the snapshot is the database itself" in capsys.readouterr().err
    assert_untouched(current, statements, digest)


def test_a_corrupt_current_database_is_kept_aside_intact(
    source: Settings, snapshot: Path, target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = load_settings(target).database_path
    database.parent.mkdir()
    garbage = os.urandom(4096)
    database.write_bytes(garbage)
    assert restore(target, snapshot) == 0
    assert (database.parent / ASIDE).read_bytes() == garbage  # D-045: never deleted nor rewritten
    assert dump(database) == dump(source.database_path)
    assert f"kept {database.parent / ASIDE}" in capsys.readouterr().out


def test_two_restores_in_the_same_second_keep_both_databases(
    snapshot: Path, current: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = current.parent.parent / "settings.toml"
    fresh = dump(current)
    assert restore(config, snapshot) == 0
    restored = dump(current)
    assert restore(config, snapshot) == 0
    assert dump(current.parent / ASIDE) == fresh
    assert dump(current.parent / f"{ASIDE}_02") == restored
    assert f"kept {current.parent / ASIDE}_02" in capsys.readouterr().out
    later = NOW + timedelta(days=1000)
    assert backup.prune(current.parent, later, 1) == []  # aside files are never pruned
    assert (current.parent / ASIDE).exists() and (current.parent / f"{ASIDE}_02").exists()


def test_a_journal_side_file_moves_aside_too(
    snapshot: Path, current: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = Path(f"{current}-journal")
    journal.write_bytes(b"hot journal")
    assert restore(current.parent.parent / "settings.toml", snapshot) == 0
    assert not journal.exists()
    assert Path(f"{current.parent / ASIDE}-journal").read_bytes() == b"hot journal"
    assert f"kept {current.parent / ASIDE}-journal" in capsys.readouterr().out


@pytest.mark.parametrize("revision", ["0001", "0002"])
def test_snapshots_of_every_older_revision_are_migrated(
    tmp_path: Path,
    target: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
) -> None:
    old = tmp_path / "old.sqlite"
    engine = db.create_engine(old)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrate.command, "upgrade", upgrade_to(revision))
            migrate.upgrade_to_head(engine)
    finally:
        engine.dispose()
    snapshot_file = backup.take_snapshot(old, tmp_path / "snaps", NOW)
    assert restore(target, snapshot_file) == 0
    out = capsys.readouterr().out
    database = load_settings(target).database_path
    assert f"at revision {revision}\n" in out
    assert f"database {database} at revision {migrate.head_revision()}" in out
    assert migrate.revision_of_file(database) == migrate.head_revision()


def test_a_read_only_snapshot_restores_as_a_writable_database(snapshot: Path, target: Path) -> None:
    snapshot.chmod(0o444)
    before = sha(snapshot)
    assert restore(target, snapshot) == 0
    database = load_settings(target).database_path
    assert database.stat().st_mode & 0o200
    engine = cli._open_current_database(load_settings(target))
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO app_setting (user_id, key, value) VALUES (1, 'after', 'restore')")
            )
    finally:
        engine.dispose()
    assert sha(snapshot) == before


def test_a_bare_name_prefers_the_backups_folder(
    source: Settings,
    snapshot: Path,
    current: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (current.parent / "backups").mkdir(exist_ok=True)
    shutil.copyfile(snapshot, current.parent / "backups" / snapshot.name)
    decoy = tmp_path / "cwd"
    decoy.mkdir()
    (decoy / snapshot.name).write_bytes(b"not this one")
    monkeypatch.chdir(decoy)
    assert restore(current.parent.parent / "settings.toml", snapshot.name) == 0
    assert dump(current) == dump(source.database_path)


@pytest.mark.xfail(
    strict=True,
    reason="product bug: restore copies only the main file of a WAL-mode database "
    "(storage/backup.py restore_snapshot, shutil.copyfile): the rows of its -wal are silently lost",
)
def test_restoring_a_wal_mode_aside_set_keeps_its_latest_rows(
    current: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    aside = current.parent / "rack.sqlite.before-restore-20261101T000000Z"
    _wal_set(aside, tmp_path / "scratch")
    code = restore(current.parent.parent / "settings.toml", aside)
    capsys.readouterr()
    assert code == 1 or _latest(current) == ("in the wal",)  # refused, or restored with its rows


@pytest.mark.xfail(
    strict=True,
    reason="product bug: check_copy/revision_of_file open the staged WAL-mode copy read-only and "
    "leave .tmp-rack.sqlite-*-wal / -shm behind (storage/backup.py _check_staged)",
)
def test_restoring_a_wal_mode_file_leaves_no_temp_side_files(
    current: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "other.sqlite"
    _wal_set(other, tmp_path / "scratch")
    restore(current.parent.parent / "settings.toml", other)
    capsys.readouterr()
    assert [name.name for name in current.parent.iterdir() if name.name.startswith(".tmp-")] == []


@pytest.mark.xfail(
    strict=True,
    reason="product bug: a failed side-file rename leaves rack.sqlite-wal behind; the rerun moves "
    "it to a new aside name (_02-wal), apart from its database (storage/backup.py _set_aside)",
)
def test_a_failed_side_file_rename_keeps_the_aside_wal_with_its_database(
    snapshot: Path,
    target: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = load_settings(target).database_path
    database.parent.mkdir()
    _wal_set(database, tmp_path / "scratch")
    real_rename = os.rename

    def failing(source_path: os.PathLike[str], target_path: os.PathLike[str]) -> None:
        if str(source_path).endswith("-wal"):
            raise OSError(5, "Input/output error")
        real_rename(source_path, target_path)

    with monkeypatch.context() as patch:
        patch.setattr(os, "rename", failing)
        assert restore(target, snapshot) == 1
    assert restore(target, snapshot) == 0
    capsys.readouterr()
    assert _latest(database.parent / ASIDE) == ("in the wal",)


# --- forms disable every button, rendered


class _Forms(HTMLParser):
    """Ids of the page and the `hx-disabled-elt` of each form."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.forms: list[tuple[str | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "form":
            self.forms.append((values.get("id"), values.get("hx-disabled-elt")))


def _audit(html: str) -> int:
    parser = _Forms()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids)), sorted(parser.ids)
    checked = 0
    for form_id, disabled in parser.forms:
        if disabled is None:
            continue
        assert form_id is not None
        assert disabled == f"#{form_id} button"
        checked += 1
    return checked


def test_rendered_forms_disable_their_own_buttons(client: TestClient, migrated_engine: Engine) -> None:
    populate(migrated_engine)
    with migrated_engine.connect() as connection:

        def one(sql: str) -> int:
            return connection.exec_driver_sql(sql).scalar_one()

        press = one("SELECT id FROM exercise WHERE name = 'Presse « test »; maison'")
        grip = one("SELECT id FROM variable WHERE label = 'Prise'")
        template = one("SELECT id FROM template WHERE name = 'Essai'")
    paths = [
        "/variables/nouvelle",
        f"/variables/{grip}",
        "/exercices/nouveau",
        f"/exercices/{press}",
        "/seances-types/nouvelle",
        f"/seances-types/{template}",
        "/reglages",
        f"/rm/{press}",
    ]
    checked = 0
    for path in paths:
        response = client.get(path, headers=PAGE)
        assert response.status_code == 200, path
        checked += _audit(response.text)
    client.cookies.clear()
    pairing = client.get("/appairage", headers=PAGE)
    assert pairing.status_code == 200
    assert _audit(pairing.text) == 1
    assert checked >= 6
