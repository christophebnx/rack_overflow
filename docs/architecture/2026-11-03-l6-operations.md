# L6 — Operations and release 1.0.0 (design note)

Status: APPROVED FOR AUTONOMOUS MODE

Every user-visible behaviour is set by the approved brief (§6 L6, §7.3 restore with the server stopped and local storage only, §8 `GET /api/export?format=json|csv`, §10 planned stop at the end of L6, §11 J and K, appendix A.8), the L6 "Done when" of `docs/roadmap.md`, invariants 3, 7, 8, 9, 11, 12 and D-013, D-021, D-024, D-038, D-045, D-051, D-052. This note fixes what they leave open and records it as D-072 to D-076; none is superseded (D-045 left "moving a corrupt database aside and restoring" to `rack restore`: D-075 refines it; D-038 left the Jelastic unit's details open: D-076 refines it). **No schema change**: 0001 to 0004 stay frozen and no revision is added. No new dependency (`json`, `csv`, `zipfile`, `io`, `socket` are stdlib). No `/build-roadmap` stop condition applies: no decision superseded, no released data format changed (V1 is not released yet; the export format is new and versioned from 1), nothing can be lost (restore never deletes: the current database is kept aside), and every choice either follows the brief or is a detail it leaves to the architect (CSV layout and encoding, where the export button lives, how a running server is detected). The end of L6 is the brief's **planned stop** (release), not an approval request.

## Context

Milestone L6: full JSON and CSV export (UI and `rack export`), `rack restore` (server stopped), NAS and Jelastic install and update docs, NAS ↔ Jelastic migration docs, release 1.0.0. Done when: restoring a backup on a blank instance yields identical data (test); the export contains every stored fact and re-reads without loss (test); the Jelastic docs put the database on the node's local disk, never a network volume; `CHANGELOG.md` has the 1.0.0 entry and a local annotated tag `v1.0.0` exists.

Current state (end of L5, head `0004`, version `0.1.0`): `storage/backup` (`check_integrity` read-write bare connection, `_is_sound(path, read_only)`, `take_snapshot` by `VACUUM INTO` through `files.atomic_produce`, `list_snapshots`, `prune`), `domain/backups` (snapshot naming, order, due-ness, retention), `services/backups` (`backup_now`, `backup_if_due`), `storage/migrate` (`head_revision`, `current_revision`, `is_up_to_date`, `upgrade_to_head`), `cli.run_migrate` (mkdir, snapshot when a revision is pending, upgrade, seed), `cli._open_current_database`, `ops/supervise` (`acquire_lock` flock on `<data_dir>/supervise.lock`, `supervise.pid`, `running_supervisor_pid`), `ops/update` (prints "no rack supervise running; restart the server yourself" when no supervisor holds the lock). `storage/schema.metadata` holds 16 tables; `device.token_hash` and `pairing_code.code_hash` are the only secret-derived columns. `/reglages` (`settings.html`) is the one settings page, linked from the progress index and the RM section, not from the nav (D-070). `docs/deployment/nas.md` covers install, supervise, update; its last line defers Jelastic to L6. Follow-up in `docs/progress.md`: nine older templates still use `hx-disabled-elt="find button"` (only the first button is disabled).

## Chosen design

### 0. Schema

None. The export reads the existing tables; restore swaps whole database files; the release changes only the version.

### 1. Modules

| Unit | New / changed | Owns |
|---|---|---|
| `domain/export.py` | new | The export format, pure (bytes in, bytes out, no file system, no clock: `exported_at` passed in): `FORMAT = "rack-overflow-export"`, `FORMAT_VERSION = 1`, `ExportMeta(format_version, app_version, schema_revision, exported_at)`, `ExportError(DomainError)`; `to_json(meta, tables) -> bytes`, `read_json(data) -> (ExportMeta, tables)` (checks `format` and `format_version`, tables a mapping of lists of objects; anything else → `ExportError`); `to_csv_zip(meta, tables, columns) -> bytes` (section 3); `file_name(kind, exported_at) -> str` (`rack-overflow-<UTC YYYYMMDDTHHMMSSZ>.json` / `rack-overflow-<…>-csv.zip`). `tables` is an ordered `{table: [row dict]}`, `columns` an ordered `{table: [column]}` |
| `storage/export.py` | new | `SECRET_COLUMNS = {("device", "token_hash"), ("pairing_code", "code_hash")}`; `exported_columns() -> {table: [column]}` (every table of `schema.metadata.sorted_tables`, parents before children, every column in schema order except `SECRET_COLUMNS`: the one definition of what an export holds); `dump(connection) -> {table: [row dict]}` (every row of each table ordered by `id`, soft-deleted and archived included; JSON columns as decoded values, `Boolean` as `true` / `false`, integers and text as stored) |
| `storage/migrate.py` | changed | `revision_of_file(path) -> str | None` (`alembic_version` read through a bare read-only `sqlite3` URI connection: never switches a snapshot to WAL, never writes it; no table → None; unreadable → `MigrationError`), `known_revisions() -> list[str]` (base → head, from the script directory), `revision_order(revision) -> "head" | "older" | "unknown"` (unknown covers a newer revision this code does not ship) |
| `storage/backup.py` | changed | `check_copy(path) -> bool` (public name of today's read-only `_copy_is_sound`, reused for the staged restore copy); `restore_snapshot(snapshot, database_path, now) -> Restored(revision, kept: list[Path])` (section 4) |
| `domain/backups.py` | changed | `aside_name(database_name, now, existing) -> str` (`<db name>.before-restore-<UTC ts>`, `_02`… on a collision; never parses as a snapshot, so `prune` never touches it) and `SIDE_SUFFIXES = ("-wal", "-shm", "-journal")` |
| `services/export.py` | new | `export(engine, fmt, now, app_version) -> ExportFile(file_name, media_type, data)`: one read of the whole database in one transaction (consistent), `migrate.current_revision`, then `domain/export` encoding. `FORMATS = ("json", "csv")`; unknown → `ExportError("unknown_format")` |
| `services/backups.py` | changed | `restore(snapshot, database_path, now) -> Restored` (calls `storage/backup.restore_snapshot`; the migration of an older snapshot is run by the CLI through the same path as `rack migrate`, section 4) |
| `ops/restore.py` | new | `server_stopped(data_dir, host, port)` context manager: takes `supervise.acquire_lock(data_dir)` for the whole restore (held: `OpsError("rack supervise is running on this data folder; stop it first")`, and no supervisor can start mid-restore), then refuses when a TCP connect to the server address succeeds within 1 s (`OpsError("a server answers on <addr>:<port>; stop it first")`: catches a plain `rack serve`, e.g. the Jelastic systemd unit); address `127.0.0.1` when `[server] host` is `0.0.0.0`, `::` or loopback, else the configured host. Socket factory injectable for tests |
| `cli.py` | changed | `rack export PATH [--format json|csv] --config …` (`run_export`): database must be current (`_open_current_database`), PATH must not exist (refused, exit 1: never overwrite a file by a typo, e.g. `config.toml`), written by `files.atomic_write`, prints the path and the row count. `rack restore SNAPSHOT --config …` (`run_restore`): SNAPSHOT is a path, or a bare snapshot name looked up in `<data_dir>/backups/`; inside `ops.restore.server_stopped`, `services.backups.restore`, then, when the restored revision is older, the same upgrade-and-seed step as `rack migrate` (extracted from `run_migrate` as `_upgrade_and_seed(engine)`, no pre-migration snapshot: the restored file is itself a backup). Prints the kept paths, the restored revision, the migrated revision. `create_app` gets nothing new: the export route reads `rack_overflow.__version__` (the package root is not a layer for `test_layering`) |
| `web/routes/progress.py` (owns `/reglages`) | changed | `GET /api/export?format=json|csv` beside `/reglages` (the page that links it): `services.export.export` in the thread pool, `Response(data, media_type, headers={"Content-Disposition": 'attachment; filename="…"'})`; unknown or missing `format` → 422 `invalid_request`. The `/api/` origin check, device auth, `no-store` and CSP apply unchanged (D-047, D-049) |
| `web/templates/settings.html` | changed | Section « Données » (h2) under the formula: one sentence and two download links-as-buttons « Exporter (JSON) », « Exporter (CSV) » (`<a href="/api/export?format=json" download>`: a plain navigation, no htmx, no script, no form). Texts fixed by the ui-designer in `docs/ui-spec.md` "L6 — Settings: export" and `fr.json` |
| `web/templates/*.html` (9 files of the follow-up) | changed | `hx-disabled-elt="find button"` → `#<form id> button` like L4 (section 6) |

Responsibility map additions (`docs/architecture.md`): "Export format (JSON document, CSV zip, file names, version)" → `domain/export`; "What an export holds (tables, columns, secret columns excluded) and the database dump" → `storage/export`; "Export operation" → `services/export`; "Revision of a database file without opening it read-write; order of a revision against the shipped ones" → `storage/migrate.revision_of_file`, `revision_order`; "Restore a snapshot as the database (stage, check, keep the current aside, swap)" → `storage/backup.restore_snapshot`; "Name of a database kept aside by a restore" → `domain/backups.aside_name`; "Refuse while a server runs on the data folder" → `ops/restore.server_stopped`. Layering unchanged (`ops/restore` imports `ops/supervise` and the stdlib only).

### 2. JSON export (D-072)

One UTF-8 document (no BOM, `ensure_ascii=False`, `indent=2`, keys in the order below, rows ordered by `id`): same database and `exported_at` → same bytes.

```json
{
  "format": "rack-overflow-export",
  "format_version": 1,
  "app_version": "1.0.0",
  "schema_revision": "0004",
  "exported_at": "2026-11-03T18:42:00Z",
  "units": {"weight": "g", "duration": "s", "distance": "m"},
  "tables": {
    "variable": [{"id": 1, "user_id": 1, "code": "siege", "...": "..."}],
    "exercise": ["..."],
    "...": ["..."]
  }
}
```

- **Contents**: every table of `schema.metadata` (parents before children, so a reader can insert in order), every row (archived exercises, variables and templates, soft-deleted sessions, sets, slots and measured RMs with their `deleted_at`; revoked devices), every column except the two secret hashes `device.token_hash` and `pairing_code.code_hash` (credential material, not a training fact: it has no business in a document meant to be opened in other tools; restore uses backups, which keep them). `alembic_version` is not a table of the export; its value is `schema_revision`.
- **Values as stored** (invariant 7): integers in canonical units (`weight_g`, `duration_s`, `distance_m`), decimal variables as their scaled integer with `decimal_scale` on the variable, enum values by key with the labels in `variable.enum_values`, timestamps as stored UTC text, local dates as text; JSON columns (`enum_values`, `discrete_values`) as nested JSON; `required` as a boolean; `NULL` as `null`. No computed value (invariant 9): no records, e1RM, volume.
- **V1 scope**: the whole database (V1 has one user, D-017). A V2 multi-user export filters by `user_id` through the foreign keys; the format does not change (rows keep `user_id`).
- **Version policy**: `format_version` is bumped only when an existing key changes meaning or disappears; a new table or column (a later revision) is additive and announced by `schema_revision`. `read_json` accepts version 1 only. No import in V1 (brief: not in scope); `read_json` is the format's reference reader, used by the tests and by a later import.

### 3. CSV export (D-073)

A zip (`rack-overflow-<ts>-csv.zip`, stdlib `zipfile`, deflated, entries dated `exported_at`): one `<table>.csv` per exported table, same tables, columns and rows as the JSON, plus `export.json` holding the JSON header without `tables` (format, versions, revision, date, units). Each CSV: **UTF-8 with BOM** (Excel otherwise reads accents as Latin-1), **`;` separator** (Excel in French locales splits only on `;` when a file is opened; LibreOffice and Numbers detect it), CRLF, minimal quoting (`csv` module), header row of column names (English identifiers, like the JSON keys; the data itself is the user's French), `NULL` → empty cell, booleans `1` / `0`, JSON columns as JSON text, integers in canonical units (column names carry the unit: `weight_g`). Rejected for V1: a flat sets-centric file (a computed projection that would need its own column choices and kg display, i.e. a second representation to keep right; one per table keeps every fact and joins by id in any spreadsheet). Known limit, documented: CSV cannot tell an empty text from `NULL`; the JSON is the lossless format.

### 4. Restore (D-075)

`rack restore SNAPSHOT --config …`, documented as "stop the server first":

1. **Server stopped** (`ops.restore.server_stopped`): the supervise lock is taken and held until the end; a server answering on the configured port is refused. Both refusals change nothing.
2. **Snapshot** must exist, be a regular file and not be the database itself (resolved paths). It is never opened read-write and never modified.
3. **Stage**: `files.atomic_produce(database_path, produce)`; `produce(temp)` copies the snapshot bytes into `temp` (same folder as the database, so the final rename is atomic), then checks `temp`: `backup.check_copy` (integrity; failure → `BackupError("snapshot failed the integrity check")`), `migrate.revision_of_file(temp)` and `revision_order`: `head` or `older` accepted; `unknown` (newer than this code, or foreign) → `MigrationError("snapshot is at revision X, unknown to this version (head Y); update the code first")`; no `alembic_version` → refused (not a Rack Overflow database). Any refusal: `atomic_produce` removes the temp, the current database and its side files are untouched, nothing kept aside.
4. **Keep the current database aside** (still inside `produce`, after every check passed): when `rack.sqlite` exists, it and each existing side file (`-wal`, `-shm`, `-journal`) are renamed to `rack.sqlite.before-restore-<ts>` and `…-wal` / `…-shm` / `…-journal`, so the aside copy opens with its uncheckpointed WAL intact, corrupt or not (D-045: never deleted; `prune` ignores the name). Not under `backups/`: the rename stays on the same file system and the file is not a snapshot.
5. **Swap**: `atomic_produce` renames the staged file to `rack.sqlite` and fsyncs the folder. The restored file is in rollback-journal mode (a `VACUUM INTO` copy); the first `create_engine` switches it to WAL as usual.
6. **Migrate** an older revision: the CLI opens the restored database and runs `_upgrade_and_seed` (the `rack migrate` path: upgrade in one transaction with the foreign-key check, then pending seed steps). A failure leaves the restored file at its revision (Alembic rolls back) and exits 1; `rack migrate` finishes it later.
7. A blank instance (no data folder, no database) is valid: the data folder is created (as `rack migrate` does), nothing is kept aside.

Interruption between step 4 and step 5 (power cut): no `rack.sqlite`, the aside file and a `.tmp-rack.sqlite-…` exist; `rack serve` refuses to start (`database is not up to date; run rack migrate` because the file is missing); rerunning `rack restore` completes (nothing to keep aside). The docs say so. The CLI prints every kept path.

### 5. Entry points and UI (D-074)

- `rack export PATH [--format json|csv]` (default `json`): see section 1. Safe while the server runs (WAL; one short read transaction).
- UI: `/reglages` section « Données » with two download links. `GET /api/export?format=json` answers `200`, `Content-Type: application/json; charset=utf-8` (CSV: `application/zip`), `Content-Disposition: attachment; filename="rack-overflow-20261103T184200Z.json"` (ASCII name, no user input), `Cache-Control: no-store`, the usual CSP; Safari on iOS saves it to Files, desktop browsers download it. A click is a same-origin navigation, so the `/api/` origin check passes; an unpaired browser is sent to pairing. Not in the nav (D-070: one rarely used setting page). The ui-designer fixes the texts, the layout at 360 / 1280 px, and the « Données » section in `docs/ui-spec.md`.

### 6. Follow-up fixed in L6: `find button`

Fixed in L6 as its own `fix(web)` commit before the release, because it is a known accessibility and double-submission defect (brief §11 I: button disabled during the request) in screens 1.0.0 ships: each of the nine templates listed in `docs/progress.md` gets `hx-disabled-elt="#<form id> button"` (forms without an id get a stable one), and `docs/ui-spec.md` lines that still write `find button` (pairing, exercise create, template create) are corrected. A template audit test fails on any `find button` left. The follow-up line is removed from `docs/progress.md`.

### 7. Deployment docs (D-076)

- `docs/deployment/nas.md`: version line `rack 1.0.0`; new sections "Export" (`rack export`, or « Réglages » → « Données »), "Restore a backup" (stop: `kill $(cat …/supervise.pid)`; `ls /volume1/rack/data/backups`; `.venv/bin/rack restore rack-<ts>.sqlite --config config.toml`; what is printed and kept aside; start with the task's **Run**; interrupted restore: rerun); the closing pointer to Jelastic now links `jelastic.md` and `migration.md`.
- `docs/deployment/jelastic.md` (new): Infomaniak Jelastic Cloud environment with one **Linux / VPS node** (e.g. Ubuntu or AlmaLinux; not the Python application server, which is WSGI-oriented, D-038); dedicated user `rack`; `git`, uv and Python 3.12 as on the NAS; clone of `main` in `/home/rack/rack_overflow`; `config.toml` with `data_dir = "/home/rack/data"` **on the node's own disk, never a Shared Storage container or any mounted network volume** (SQLite locking and WAL need local storage, brief §7.3); systemd unit `/etc/systemd/system/rack.service` running `rack serve` directly as `User=rack` with `WorkingDirectory`, `ExecStart=/home/rack/rack_overflow/.venv/bin/rack serve --config config.toml`, `Restart=on-failure`, `RestartSec=5`, `After=network-online.target`, `WantedBy=multi-user.target`; logs through `journalctl -u rack` (systemd replaces `rack supervise` there, D-038; the daily backup runs in the server as on the NAS); exposure over plain HTTP (D-013): a high, non-standard port reached through the node's public IP or a Jelastic TCP endpoint, `public_host` = the host name typed in the browser, no Jelastic SSL / load-balancer HTTPS in V1; firewall rule for that port only. Update: `rack update` (prints "no rack supervise running; restart the server yourself") then `sudo systemctl restart rack`. Restore: `sudo systemctl stop rack`, `rack restore …`, `sudo systemctl start rack`. Each step with a **Check**, like `nas.md`.
- `docs/deployment/migration.md` (new): NAS ↔ Jelastic in both directions: install the target from its guide up to the settings (same `time_zone`, code at the same version or newer: an unknown revision is refused), do not create a database there; stop the source server; `rack backup` on the source; copy the printed snapshot (`scp`) into the target's `<data_dir>/backups/`; `rack restore <name>` on the target; start; devices: the cookie is bound to the host name, so on the target `rack device revoke <name>` then `rack device add <name>` for each device and pair again at the new URL; update bookmarks; keep the source stopped (DSM task disabled or `systemctl disable rack`) and its data until the target is confirmed. Checks: `rack device list`, the latest session visible in « Historique ».

### 8. Release 1.0.0

Through `/release` at the end of L6, version **1.0.0** (brief §3.1, §11 N): full checks, `version = "1.0.0"` in `pyproject.toml`, `uv lock`, CHANGELOG `[Unreleased]` → `## [1.0.0] - 2026-11-03` (all L1a–L6 entries; a short summary line on top), roadmap and progress checked, commit `chore(release): release v1.0.0`, local annotated tag `git tag -a v1.0.0 -m "v1.0.0"`, branch pushed, tag **not** pushed (the user pushes it after merging, per the skill). Then the run stops (planned stop, brief §10): user validations pending are listed in `docs/progress.md` (NAS restore, Jelastic install if wanted, WebKit run, earlier ones).

### 9. Errors

| Failure | User sees | On disk |
|---|---|---|
| `rack export` path exists / folder missing | `rack: error: …`, exit 1 | nothing |
| `rack export` on a stale database | `database is not up to date; run rack migrate`, exit 1 | nothing |
| `GET /api/export` unknown format | 422 `invalid_request` (error page on a navigation) | nothing |
| Restore while supervise or a server runs | exit 1, "stop it first" | nothing |
| Snapshot missing, corrupt, foreign, newer | exit 1, reason | temp removed; current database untouched |
| Rename fails mid-restore | exit 1 with the paths | aside copy and/or temp kept; rerun completes |
| Migration of an older snapshot fails | exit 1, "run rack migrate" | restored file at its own revision; aside kept |

## UI design

Status: APPROVED FOR AUTONOMOUS MODE (the brief and D-074 settle the entry point and the two formats; what is left is wording and layout). Full spec: `docs/ui-spec.md` "L6 — Settings: export", "L6 — Forms disable every button", "L6 — Strings".

- **Task and decision.** Take a complete copy of the data out of the app, to keep or to open elsewhere; the one decision is the format. The section answers it with one hint per button (JSON: one complete, lossless file for a program; CSV: a zip of one table per kind of data for a spreadsheet), and two notes that prevent the two likely mistakes: reading `62500` as kilograms (« Les poids y sont en grammes… ») and taking the export for a backup (« Cet export ne sert pas à restaurer l’application… »).
- **Layout.** A second `section.settings` « Données » (`#donnees`) after the formula, before « Voir la progression »: muted intro, `ul.exports` of two `li.export` (link-button + hint tied by `aria-describedby`), then the two notes. 360 px: buttons full width, hint under each. From 40rem: grid `12rem minmax(0, 1fr)`, button left, hint right. Secondary buttons (no accent), ≥ 48 px, 16 px apart; tokens only, so light and dark need nothing new. CSS in `pages/progress.css` (the settings page's sheet): `.exports`, `.export`, `.export__hint`, `.export__note`.
- **Links.** Labels « Exporter en JSON » / « Exporter en CSV » (replacing the note's placeholder « Exporter (JSON) »). `<a href="/api/export?format=…">` **without the `download` attribute** (refines section 1's `settings.html` row): `Content-Disposition: attachment` already saves the file and keeps the page, while without `download` a failure navigates to the designed error page and an unpaired browser follows the 303 to pairing, instead of a silent failed download.
- **States.** Downloading and done are the browser's own (download bar, Safari's save sheet, Files); the page does not change, focus stays on the link, nothing is announced. Failure 500: the L1a error page; its « Réessayer » must keep the query (`/api/export?format=json`): today `errors._retry_path` drops it, so retrying would answer 422. The developer keeps the query string as sent in the retry link (same-origin path + query, escaped by Jinja), for every 5xx page. Unknown format (typed URL): 422 page. Section always shown (an empty database exports fine).
- **Keyboard.** Tab: header, formula radios (one stop), « Exporter en JSON », « Exporter en CSV », « Voir la progression ».
- **Strings.** `settings.data_heading`, `settings.data_intro`, `settings.export_json`, `settings.export_json_hint`, `settings.export_csv`, `settings.export_csv_hint`, `settings.export_units`, `settings.export_not_backup` (texts in `docs/ui-spec.md` "L6 — Strings").
- **`find button` follow-up (section 6).** Ten forms in the nine templates; ids kept where they exist (`variable-formulaire`, `exercice-formulaire`, `{prefix}-formulaire`, `seance-type-formulaire`), new where missing: `appairage-formulaire`, `champ-ajout-formulaire`, `alias-formulaire`, `bloc-ajout-formulaire`, `{prefix}-option-ajout-formulaire` (all unused today). `docs/ui-spec.md` already corrected: the pairing, exercise create and template create lines and the L4 note; table in "L6 — Forms disable every button". The `exercise_form` and `session_template_form` « Annuler » are links, so only the submit is disabled there, as intended.

## Rejected options

- **Export of every column, hashes included**: a credential has no place in a file meant for spreadsheets and other tools; backups carry them for restore.
- **Export scoped by `user_id` now**: V1 has one user; scoping through every foreign key is V2 work with no V1 effect, and the format already carries `user_id`.
- **An import command** to prove "re-reads without loss": not in the brief (V1.x Excel import is a different feature); the test loader in `tests/support/` proves it without shipping an import path.
- **One flat sets CSV** (or both): see section 3.
- **Comma separator, no BOM**: opens as one column with broken accents in French Excel.
- **Export on its own page or in the nav**: one more page or a sixth nav link for a rare action (D-070); `/reglages` already holds rare settings.
- **Restore by `sqlite3` backup API into the live file, or by `VACUUM INTO` from the snapshot**: writes inside the current database (lost if it is the corrupt one being replaced) and needs it openable; a file copy of a closed, checked snapshot plus a rename is simpler and keeps the current file intact.
- **Deleting or overwriting the current database**: D-045 spirit, never delete.
- **Detecting a running server by the `-wal` file or SQLite locks**: a `-wal` also survives a power cut, and WAL lock semantics would make the check depend on SQLite internals; the supervise lock plus a port probe cover both ways the server runs (NAS supervise, Jelastic systemd).
- **`rack supervise` under systemd on Jelastic**: two supervisors stacked; systemd already restarts and keeps logs (D-038). Cost accepted: `rack update` there is followed by `systemctl restart`.
- **Leaving the `find button` follow-up after 1.0.0**: it is a defect in shipped screens and a few-line fix.

## Impacts

- Decisions added: D-072 (JSON export), D-073 (CSV export), D-074 (export entry points), D-075 (restore), D-076 (Jelastic deployment). None superseded.
- Docs: `docs/architecture.md` (map rows of section 1, "Operations" flow gains export and restore, overview "later possibly Jelastic" → Jelastic guide), package `CLAUDE.md` of `domain`, `storage`, `services`, `ops`, `web` (module tables), root `CLAUDE.md` commands (`rack export`, `rack restore`), `docs/ui-spec.md` (L6 export section; `find button` lines), `docs/deployment/nas.md`, new `jelastic.md` and `migration.md`, `docs/roadmap.md` (unchanged criteria), `docs/progress.md`, `CHANGELOG.md`.
- Compatibility: no schema change; existing snapshots restore (any revision 0001–0004 is `older` or `head`). The export format starts at version 1 with 1.0.0.

## Test plan

Unit:
- `domain/export`: JSON key order, determinism, `ensure_ascii=False` (accents raw), nested JSON columns, booleans, `null`; `read_json` round trip and refusals (not JSON, wrong `format`, `format_version` 2, `tables` not a mapping); CSV zip entry names, `export.json`, BOM, `;`, CRLF, quoting of a `;` / newline / quote in text, `NULL` → empty, `1` / `0`, JSON text cells, entry dates equal `exported_at`; `file_name`.
- `domain/backups.aside_name`: format, collision `_02`, never parsed by `parse_snapshot_time`.
- `ops/restore.server_stopped`: lock held by another descriptor → refused; listening loopback socket on the port → refused; free → yields and releases the lock; `0.0.0.0` probes `127.0.0.1`.
- Template audit: no `find button` in `web/templates/`.

Integration:
- **Export re-reads without loss (roadmap)**: a database with every table populated (tests/support/history.py plus variables of each type, enum and decimal values, archived exercise, variable and template, removed slot, soft-deleted session and set, deleted and live measured RM, app settings, a revoked device and used pairing code); `export(json)` → `read_json` → equals `storage/export.dump` of the database; `tests/support/export_loader.py` inserts the parsed rows into a fresh database migrated to the same head, and its dump equals the original (every column except the secret ones, which the loader fills with placeholders); every table and column of `schema.metadata` minus `SECRET_COLUMNS` appears in the export (a new table or column fails until classified); the CSV zip parsed back with the schema's column types equals the dump (empty cell ≡ `NULL`).
- **Restore on a blank instance yields identical data (roadmap)**: populated database → `rack backup` → a second config with an empty, absent data folder → `rack restore <snapshot path>` → `sqlite3.iterdump()` of both databases equal (every table, `alembic_version`, secrets included); the same with a bare snapshot name resolved in `backups/`, and onto an instance that already has a fresh seeded database (kept aside, then identical).
- Restore edges: snapshot at `0003` (helper `upgrade_to` moved from `test_migrations.py` to `tests/support/migrations.py`) → restored then at head, data preserved, seed steps applied once; `alembic_version` set to an unknown revision → refused, current database `iterdump` and bytes unchanged, no aside, no temp left; corrupt snapshot (garbage bytes, truncated file) → refused likewise; snapshot = database path → refused; snapshot bytes unchanged after any restore (SHA-256); current database with live `-wal` / `-shm` (open engine closed without checkpoint) → aside set opens and holds the latest rows; interrupted swap (patched `os.replace` raising) → rerun completes; supervise lock held → refused; server port answering → refused; `rack serve` starts on the restored database.
- `rack export`: writes JSON / CSV, refuses an existing path and a stale database (exit 1), works while another engine holds the database open.
- `GET /api/export`: `200` with media type, `Content-Disposition` name pattern, `no-store`, CSP; body equals `services.export`; unknown / missing format → 422; foreign `Origin` → 403; unpaired navigation → 303 to `/appairage`, htmx → 401.
- Browser (Chromium and WebKit, 360 / 1280, light / dark): `/reglages` with the « Données » section passes the page checks; a click on « Exporter (JSON) » fires a download whose name ends in `.json` (Chromium).
- Release: `rack --version` prints `rack 1.0.0` after the bump (existing CLI test reads the metadata).

## Commit plan (all with `Milestone: L6`)

1. `fix(web): disable every button of older forms during a request` — nine templates, `docs/ui-spec.md` lines, audit test, `docs/progress.md` follow-up removed.
2. `feat(export): JSON and CSV export format and database dump` — `domain/export`, `storage/export`, `services/export`, unit tests, round-trip integration test and `tests/support/export_loader.py`, package `CLAUDE.md` rows.
3. `feat(cli): rack export` — `run_export`, CLI tests, root `CLAUDE.md` command.
4. `feat(web): export downloads on the settings page` — route, `settings.html`, `fr.json`, CSS if any, `docs/ui-spec.md` L6 section, route and browser tests, `web/CLAUDE.md`.
5. `feat(storage): rack restore with the server stopped` — `domain/backups.aside_name`, `storage/migrate` additions, `storage/backup.restore_snapshot` / `check_copy`, `services/backups.restore`, `ops/restore`, `cli.run_restore` and `_upgrade_and_seed`, tests (incl. blank instance), `tests/support/migrations.py`, package `CLAUDE.md` rows, root `CLAUDE.md` command.
6. `docs(deployment): restore and export on the NAS, Jelastic guide, host migration` — `nas.md`, `jelastic.md`, `migration.md`.
7. `docs: close milestone L6` — `docs/architecture.md` map and flows, `docs/decisions.md` (already holds D-072 to D-076 from this note), `docs/roadmap.md`, `docs/progress.md`, `CHANGELOG.md` L6 entries.
8. `chore(release): release v1.0.0` — `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, progress; local annotated tag `v1.0.0` on it (not pushed).

## Review (reviewer, loop 1)

Checks: 2832 passed, 177 skipped (WebKit), 3 strict xfails; ruff and format clean; duplicate-code 10.00. Retry link sound (same-origin, percent-encoded, escaped); the find-button fix covers all ten forms; layering holds; reuse correct (`check_copy`, `atomic_produce` / `atomic_write`, `_upgrade_and_seed`); export complete (all tables minus the two hashes, format version 1, g/s/m, CSV with BOM, `;`, CRLF, minimal quoting); docs match D-013, D-076. The developer's test changes are legitimate (two of them stricter).

1. **BLOCKING** `storage/backup.py:168` (`shutil.copyfile`): restoring a WAL-mode file copies only the main file; rows still in its `-wal` are lost, exit 0. `docs/deployment/nas.md:180,185` documents undoing a restore from the `.before-restore-*` set, so this path loses data. Stage a consistent copy of the snapshot including its WAL contents (e.g. SQLite backup API or `VACUUM INTO` from the snapshot), never modifying the snapshot set and leaving no stray files; turn xfail (1) into a passing test.
2. **TO FIX** `storage/backup.py:125` (`_check_staged`): a WAL-mode staged file opened read-only leaves `.tmp-rack.sqlite-*-wal` / `-shm` in the data folder (xfail 2). The staged copy must be a non-WAL single file (fixed together with 1).
3. **TO FIX** `storage/backup.py:137-147` (`_set_aside`): if renaming a side file fails after the database moved, the `-wal` stays and a rerun moves it to `<aside>_02-wal`, apart from its database (invariant 8, D-075); the `BackupError` raised is not an `OSError`, so the "kept aside: …" message (`:178-181`) is skipped (xfail 3). On a rerun give orphan side files their database's aside name (or roll back), and report what was moved.
4. **SUGGESTION** `services/export.py:596-598`: the dump holds `BEGIN IMMEDIATE` (writers wait up to 5 s); read the schema revision inside the dump transaction; a read transaction would not block writers.
5. **SUGGESTION** `cli.py:105-110` `_new_file` then `atomic_write`: TOCTOU overwrite; low risk; link the temp file instead of replacing.
6. **SUGGESTION** `ops/restore.py:496`: the port probe misses a systemd unit between restarts; mention the window in `nas.md` §13 and `jelastic.md:174` (stop the service first).
7. **SUGGESTION** cover the error branches `backup.py:50-51, 170-171` (copy failure before any move) and `migrate.py:76-77`.

## UI review (ui-designer, loop 1)

Chromium at 360 (touch) and 1280, light and dark: no BLOCKING, no TO FIX. Export buttons 48 px, hints tied by `aria-describedby`, no `download` attribute, downloads named `rack-overflow-YYYYMMDDTHHMMSSZ.json` / `…-csv.zip`, page and focus stay; forced 500 retry keeps the query; 422 for unknown or missing format; unpaired → pairing; all ten forms disable every button during a held request with no layout change.

1. **SUGGESTION** `docs/ui-spec.md:2047-2048`: « Accueil » should read « Retour à l’accueil ».
2. **SUGGESTION** `templates/settings_formula.html:7`: use `.section__intro` so both intros on `/reglages` share the 14 px size.
3. **SUGGESTION** note in the states table that after a successful retry the error page stays displayed (the file downloads without navigation).

## Fix loop 1

- **Reviewer 1 and 2** (`768a003`): `restore_snapshot` copies the snapshot set (file, `-wal`, `-journal`; never `-shm`) into a scratch folder `.tmp-restore-*` beside the database, runs the integrity check on that copy, then `VACUUM INTO` the `atomic_produce` temp: one rollback-journal file holding every committed row, the `-wal` ones included; the scratch folder is removed. Chosen over opening the snapshot directly: opening a WAL file writes its `-shm` even read-only, and the last read-write close checkpoints and removes its `-wal`, so the snapshot set would be modified. Cost: free space for two copies during the restore (documented). Undoing a restore from a `.before-restore-*` set keeps every row; steps added to `nas.md` §13. D-075 refined (2026-11-04). Xfails (1) and (2) pass, (1) made stricter (exit 0, full dump equal, set bytes unchanged, no `-wal` / `-shm` beside the restored file).
- **Reviewer 3** (`768a003`): `_set_aside` moves back what it already renamed when a rename fails (roll back rather than guess an orphan's owner on a rerun, which could pair a `-wal` with the wrong database); the error names the failed move and either « moved back: … » or « still moved aside: X (was Y) ». Xfail (3) passes with message checks; a failed move-back is tested.
- **Reviewer 4** (`49d1dbb`): `storage/db.read_transaction` (`BEGIN DEFERRED`), with `migrate.revision_in(connection)`: the export reads revision and rows in one snapshot without blocking writers.
- **Reviewer 5** (`bd33a5c`): `files.atomic_write(..., overwrite=False)` hard-links the temp as PATH (check-then-rename where hard links are unsupported); `rack export` uses it. `test_export_write_failure_leaves_no_file` now also patches `os.link` (the call that publishes a new file); same assertion.
- **Reviewer 6** (`01321b6`): the one-shot port probe is documented in `nas.md` §13 and `jelastic.md` §12.
- **Reviewer 7** (`768a003`): tests for a failed snapshot copy, a failed staging `VACUUM`, `check_copy` and `revision_of_file` on a file SQLite cannot open.
- **UI 1, 2, 3** (`c59e1ad`): « Retour à l’accueil » in the export states table, `.section__intro` on the formula intro, the note that a successful retry leaves the error page displayed.
