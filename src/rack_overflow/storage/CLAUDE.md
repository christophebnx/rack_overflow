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
| `errors.py` | `StorageError`, `MigrationError`, `BackupError`, `CorruptDatabaseError(BackupError)` |
| `db.py` | `create_engine(database_path)`: WAL, `foreign_keys`, `synchronous = SYNCHRONOUS` (tests: OFF), `busy_timeout`, `BEGIN IMMEDIATE` on every transaction |
| `schema.py` | `metadata` (naming convention) and one `Table` per table of brief section 7.2 |
| `migrate.py` | `upgrade_to_head(engine)`, `current_revision(engine)`, `head_revision()`, `is_up_to_date(engine)`; Alembic configured in code; an unreadable database or unknown revision raises `MigrationError` |
| `migrations/` | Alembic `env.py`, `script.py.mako`, `versions/` (frozen revisions, `0001_initial_schema.py`, `0002_variable_decimal_scale_not_null.py`) |
| `backup.py` | `check_integrity(database_path)` (bare `sqlite3` connection, no engine pragmas; the copy is checked read-only), `take_snapshot(database_path, backups_dir, now)` (`VACUUM INTO` through `atomic_produce`, copy checked before the rename; corrupt source → `CorruptDatabaseError`, nothing written), `list_snapshots(backups_dir)` (in `domain.backups.ordered` order), `prune(backups_dir, now, retention_days)`; every `OSError` becomes `BackupError` |
