# domain/ — rules

- Pure business logic. No file system, no network, no database, no model calls, no environment variables, no current time read implicitly (pass `now` as an argument). Ids and random tokens come from callers.
- Imports allowed: the standard library, declared pure libraries (e.g. `pydantic` if added), and other `domain` modules. Nothing else from `rack_overflow` (`tests/unit/test_layering.py`).
- Every public function has unit tests in `tests/unit/test_<module>.py`.
- Before adding a function, check the responsibility map in `docs/architecture.md`. If the responsibility exists, reuse or extend it. If you add a cross-cutting responsibility, add it to the map.
- Errors derive from `errors.DomainError`.

## Modules

| Module | Owns |
|---|---|
| `errors.py` | `DomainError(ValueError)`, base of every module's error class |
| `vocabulary.py` | Allowed values of enumerated columns (`VARIABLE_TYPES`, `VARIABLE_SCOPES`, `CORE_QUANTITIES`, `EXERCISE_CATEGORIES`, `LOCATIONS`, `SESSION_LOCATIONS`, `SESSION_STATUSES`, `SET_TYPES`): stable English keys, turned into `CHECK` constraints by `storage/schema` |
| `timestamps.py` | Database timestamp text: `to_text(dt)` (aware only, UTC `YYYY-MM-DDTHH:MM:SSZ`, seconds), `from_text(text)` (aware UTC); `TimestampError`. Every timestamp column written from L1b on goes through it |
| `users.py` | `SINGLE_USER_ID = 1`, the one user of V1 (D-017); read only when creating a device |
| `devices.py` | Device pairing and token rules (D-049): constants (`CODE_DIGITS`, `CODE_TTL`, `MAX_ATTEMPTS`, `TOKEN_BYTES`, `TOKEN_LENGTH`, `TOKEN_LIFETIME`, `RENEW_AFTER`, `NAME_MAX`), `DeviceError`, `PairingOutcome`, `DeviceState`, `validate_name`, `normalise_code`, `format_code`, `hash_secret` (SHA-256 hex), `looks_like_token`, `is_live`, `judge_match` (a code whose hash matched), `judge_miss` (outcome and remaining attempts after charging live codes), `state_of`, `token_valid`, `needs_renewal`. Draws no random value |
| `backups.py` | Snapshot rules (D-045): `snapshot_name(now, existing)`, `parse_snapshot_time(name)`, `ordered(names)` (oldest first by time then rank, the only snapshot ordering), `newest(names)`, `is_due(latest, now)`, `expired(names, now, retention_days)` (never the newest, never a name that does not parse) |
