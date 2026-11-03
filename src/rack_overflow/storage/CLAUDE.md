# storage/ — rules

- Everything that touches the disk lives here (or in a later outer layer). Business rules stay in `domain/`.
- Every write of a user or state file goes through `files.atomic_write` (bytes) or `files.atomic_produce` (a writer that creates the temp file, e.g. `VACUUM INTO`). Never `Path.write_text` / `open(..., "w")` on such a file.
- No partial state on failure: write the new file completely, then switch to it.
- Tests use `tmp_path` only.
- The database is opened only through `db.create_engine` (pragmas, `BEGIN IMMEDIATE`). Queries use SQLAlchemy Core on `schema` tables; SQL stays Postgres-compatible (D-016, D-046).
- Schema changes: edit `schema.py` **and** add a new revision in `migrations/versions/` (autogenerate, then review; literal value lists, no import of `schema` or `domain`). A committed migration is never edited.
- Errors derive from `errors.StorageError`.

## Modules

| Module | Owns |
|---|---|
| `files.py` | `atomic_produce(path, produce)`: unused temp name in the same folder, `produce(temp)`, fsync, `os.replace`, folder fsync (POSIX), temp removed on failure; `atomic_write(path, data)` built on it |
| `errors.py` | `StorageError`, `MigrationError`, `BackupError`, `CorruptDatabaseError(BackupError)`, `DeviceNameTakenError`, `NameTakenError` (catalog uniques) |
| `db.py` | `create_engine(database_path)`: WAL, `foreign_keys`, `synchronous = SYNCHRONOUS` (tests: OFF), `busy_timeout`, `BEGIN IMMEDIATE` on every transaction; `guarded_write(connection, write, refusal)`: a write in a savepoint whose unique-constraint violation raises `refusal` (other integrity errors propagate), the one savepoint guard of every unique check |
| `schema.py` | `metadata` (naming convention) and one `Table` per table of brief section 7.2 |
| `migrate.py` | `upgrade_to_head(engine)`, `current_revision(engine)`, `head_revision()`, `is_up_to_date(engine)`; Alembic configured in code; an unreadable database or unknown revision raises `MigrationError` |
| `migrations/` | Alembic `env.py`, `script.py.mako`, `versions/` (frozen revisions, `0001_initial_schema.py`, `0002_variable_decimal_scale_not_null.py`) |
| `backup.py` | `check_integrity(database_path)` (bare `sqlite3` connection, no engine pragmas; the copy is checked read-only), `take_snapshot(database_path, backups_dir, now)` (`VACUUM INTO` through `atomic_produce`, copy checked before the rename; corrupt source → `CorruptDatabaseError`, nothing written), `list_snapshots(backups_dir)` (in `domain.backups.ordered` order), `prune(backups_dir, now, retention_days)`; every `OSError` becomes `BackupError` |
| `devices.py` | Device and pairing-code queries on a caller's `Connection`: `insert_device` (active name taken → `DeviceNameTakenError`: the one check of that rule), `insert_pairing_code`, `active_device_by_name`, `all_devices`, `revoke`, `codes_by_hash` (newest first, with the device's `revoked_at`, `token_hash`, `name`), `unused_codes` (of active unpaired devices), `add_attempt`, `mark_used` (only an unused code) and `set_token` (only an active unpaired device), both returning whether the row was written, `device_by_token_hash` (active only), `touch`. No rule decided here |
| `variables.py` | Variable queries on a caller's `Connection`: `insert` (code taken → `NameTakenError`), `update`, `get(user_id, id)`, `codes`, `list_all` (with `linked_count`), `set_archived`, `delete` (its `exercise_field` links first), `has_values` (any `set_value` / `exercise_setting` row, soft-deleted included), `used_enum_keys`, `linked_exercises`, `draft_of(row)` (row → `domain.catalog.VariableDraft`; enum values stored as JSON `[{key, label}]`, absent values as SQL `NULL`) |
| `exercises.py` | Exercise, field and alias queries on a caller's `Connection`: `insert` / `update` (name taken → `NameTakenError`), `get`, `list_all`, `names`, `set_archived`, `has_history`, `movement_patterns` / `equipments` (distinct, first-seen first), `search_candidates` (one query → `domain.search.Candidate`); fields `fields_of` (with the variable's columns), `fields_of_variable`, `params_of(row)`, `insert_field` (last position; linked twice → `NameTakenError`), `update_field`, `delete_field`, `set_positions`; aliases `aliases_of`, `insert_alias`, `delete_alias` |
| `app_settings.py` | `get(connection, user_id, key)`, `put(connection, user_id, key, value)` (insert or update): per-user settings (`seed.version`, later the RM formula) |
