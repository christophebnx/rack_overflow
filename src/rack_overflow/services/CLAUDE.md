# services/ — rules

- Business operations: each public function is one use case (one transaction when it touches the database), callable from the CLI, the web routes and later a JSON API.
- Imports allowed: the standard library, third-party libraries, `domain` and `storage` (`tests/unit/test_layering.py`). Never `web`, `cli` or `config`: values (paths, `now`, settings fields) are passed in.
- No clock or environment read implicitly: `now` comes from the caller.
- Business rules stay in `domain/`; disk and SQL stay in `storage/`. A service orchestrates them.
- Every public function has tests (`tests/unit/` or `tests/integration/` when it needs a database).

## Modules

| Module | Owns |
|---|---|
| `backups.py` | `backup_now(database_path, backups_dir, now, retention_days)` (snapshot, then prune) and `backup_if_due(...)` (only when the newest snapshot is ≥ 24 h old) |
