# domain/ — rules

- Pure business logic. No file system, no network, no database, no model calls, no environment variables, no current time read implicitly (pass `now` as an argument). Ids and random tokens come from callers.
- Imports allowed: the standard library, declared pure libraries (e.g. `pydantic` if added), and other `domain` modules. Nothing else from `template_python` (`tests/unit/test_layering.py`).
- Every public function has unit tests in `tests/unit/test_<module>.py`.
- Before adding a function, check the responsibility map in `docs/architecture.md`. If the responsibility exists, reuse or extend it. If you add a cross-cutting responsibility, add it to the map.
- Errors derive from `errors.DomainError`.

## Modules

| Module | Owns |
|---|---|
| `errors.py` | `DomainError(ValueError)`, base of every module's error class |
| `greeting.py` | Example module (replace it): `greeting(name)`, `GreetingError`, `NAME_LIMIT` |
