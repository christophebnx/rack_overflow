# domain/ — rules

- Pure business logic. No file system, no network, no database, no model calls, no environment variables, no current time read implicitly (pass `now` as an argument). Ids and random tokens come from callers.
- Imports allowed: the standard library, declared pure libraries (e.g. `pydantic` if added), and other `domain` modules. Nothing else from `rack_overflow` (`tests/unit/test_layering.py`).
- Every public function has unit tests in `tests/unit/test_<module>.py`.
- Before adding a function, check the responsibility map in `docs/architecture.md`. If the responsibility exists, reuse or extend it. If you add a cross-cutting responsibility, add it to the map.
- Errors derive from `errors.DomainError`.

## Modules

| Module | Owns |
|---|---|
| `errors.py` | `DomainError(ValueError)`, base of every module's error class; `NotFoundError` (unknown id or another user's row) |
| `vocabulary.py` | Allowed values of enumerated columns (`VARIABLE_TYPES`, `VARIABLE_SCOPES`, `CORE_QUANTITIES`, `EXERCISE_CATEGORIES`, `LOCATIONS`, `SESSION_LOCATIONS`, `SESSION_STATUSES`, `SET_TYPES`): stable English keys, turned into `CHECK` constraints by `storage/schema` |
| `timestamps.py` | Database timestamp text: `to_text(dt)` (aware only, UTC `YYYY-MM-DDTHH:MM:SSZ`, seconds), `from_text(text)` (aware UTC); `TimestampError`. Every timestamp column written from L1b on goes through it |
| `users.py` | `SINGLE_USER_ID = 1`, the one user of V1 (D-017); read when creating a device and by `rack migrate` for the seed (D-057) |
| `devices.py` | Device pairing and token rules (D-049): constants (`CODE_DIGITS`, `CODE_TTL`, `MAX_ATTEMPTS`, `TOKEN_BYTES`, `TOKEN_LENGTH`, `TOKEN_LIFETIME`, `RENEW_AFTER`, `NAME_MAX`), `DeviceError`, `PairingOutcome`, `DeviceState`, `validate_name`, `normalise_code`, `format_code`, `hash_secret` (SHA-256 hex), `looks_like_token`, `is_live`, `judge_match` (a code whose hash matched), `judge_miss` (outcome and remaining attempts after charging live codes), `state_of`, `token_valid`, `needs_renewal`. Draws no random value |
| `supervision.py` | `RestartPolicy` (1 s doubling to 300 s, reset after 60 s of uptime) and `next_delay(policy, previous_delay_s, uptime_s)` (D-051) |
| `backups.py` | Snapshot rules (D-045): `snapshot_name(now, existing)`, `parse_snapshot_time(name)`, `ordered(names)` (oldest first by time then rank, the only snapshot ordering), `newest(names)`, `is_due(latest, now)`, `expired(names, now, retention_days)` (never the newest, never a name that does not parse) |
| `text.py` | `normalise(text)` (NFKD, accents removed, casefold, `œ`/`æ` expanded, every non-alphanumeric run → one space) and `slug(text)` (spaces → `_`): the one text normalisation (search, aliases, name uniqueness, codes, enum keys; D-056) |
| `units.py` | Canonical integers ↔ user text (D-055): `kind_of_quantity`, `NUMERIC_KINDS`, `parse(kind, raw, *, scale)` (`UnitError.code`: `not_a_number`, `too_many_decimals`, `negative`, `too_large`, `bad_duration`), `format(kind, value, *, scale) -> Display(number_text, unit_key)`, `input_text` (text `parse` reads back: an input prefilled in display units), `input_unit_key` (unit shown in an input label). Unit keys only (`unit.kg`…), no symbol |
| `catalog.py` | Catalog rules (D-054): `Problem`, `CatalogError` (every problem of a form at once); variables (`variable_draft`, `ValueInput`, `EnumValue`, `enum_values`, `variable_code`, `variable_change`, `value_column`); exercises (`exercise_draft`, `name_taken`, `check_name`, `known_spelling`, `with_known_spellings` (pattern and equipment of a draft in their first-seen spelling, used by the exercise service and the seed), `sort_key` (list order of names and labels), `default_fields`); fields (`FieldKind`, `core_kind`, `variable_kind`, `field_params` typed in display units, `check_field` on canonical values, shared with the seed, `cleared_for`, `FieldSource`, `check_measures`); aliases (`alias_draft`) |
| `search.py` | Fuzzy ranking (D-056): `Candidate(id, name, aliases)`, `rank(query, candidates, *, limit, recent)`, `score` tiers (exact, prefix, token prefixes, initials without stop-words, substring, edit distance 1 from 4 letters / 2 from 7 on token prefixes), `prefix_distance` (bounded Levenshtein) |
