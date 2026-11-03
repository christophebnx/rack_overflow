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
| `devices.py` | Device operations (D-049), one transaction each: `add_device` (name validated; unpaired device + pairing code, a taken active name is the storage `DeviceNameTakenError` turned into `DeviceError`; returns the code in clear once), `list_devices`, `revoke_device`, `pair` (match → `judge_match`, then `mark_used` and `set_token` in a savepoint: either refuses → rolled back, `code_expired`; miss → attempt charged to every live code, `judge_miss`; malformed input charges nothing), `authenticate` (token shape checked before any database access; `last_seen_at` refreshed at most once an hour). Draws the random code and token (`secrets`) |
| `variables.py` | Variable operations (D-054), one transaction each, `user_id` passed in: `create(VariableForm)` (code from `domain.catalog.variable_code`), `update` (`variable_change`: frozen type / scope / scale once values exist, used enum keys kept; field parameters the new kind refuses are cleared on every link), `set_archived(now | None)`, `delete` (only without values, else `variable_in_use`), `get_detail` (`VariableDetail`: links, `has_values`, `used_enum_keys`), `list_variables`. Unknown or foreign id → `domain.errors.NotFoundError` |
| `exercises.py` | Exercise operations (D-054, D-056), one transaction each: `create(ExerciseForm)` (name unique after normalisation, pattern / equipment in their first-seen spelling, default fields of the category), `update`, `set_archived`, `get_detail` (`ExerciseDetail`: fields as `FieldView` with kind and parameters, aliases, `has_history`, addable core quantities and non-archived variables), `list_exercises`, `search_exercises` (`domain.search.rank`), `suggestions`, `add_field` (core quantity or variable; `already_linked`), `update_field(FieldForm)` (display units parsed by `domain.catalog.field_params`), `remove_field` (`last_measure`; stored values kept), `move_field(up | down)`, `add_alias`, `remove_alias` |
| `seed.py` | `seed_catalog(engine, user_id, steps=STEPS)` (D-057): steps above `app_setting` `seed.version` run in one transaction, then the version is stored; step 1 inserts the seed exercises through the domain validators (`exercise_draft`, `check_field`, `check_measures`, `alias_draft`), skipping a normalised name that exists; malformed items → `StorageError`. Called by `rack migrate` |
