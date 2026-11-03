# Build progress

Maintained by the `/build-roadmap` skill. Branch: the session's designated branch (it plays the role of `dev`). One row per milestone of `docs/roadmap.md`. Status: `todo`, `in progress`, `done`, `BLOCKED`.

| Milestone | Status | Commit | Notes |
|---|---|---|---|
| B0 Bootstrap | done | 45ef5e4 | Package `rack_overflow`, CLI `rack`; approved brief, roadmap, decisions D-012 to D-043; hooks checked (secret read and push on `main` blocked, formatter runs); 52 tests, ruff and duplicate-code green locally. Commit on `main` not tried (same guard as push, covered by `tests/unit/test_guard_paths.py`). |
| L1a Technical foundation | todo | | |
| L1b Auth and NAS deployment | todo | | Planned stop: user validation on the NAS |
| L2 Catalog | todo | | |
| L3 Templates | todo | | |
| L4 Session logging | todo | | |
| L5 Tracking | todo | | |
| L6 Operations and release 1.0.0 | todo | | |

## User validations pending

None.

## Blocking question

None.
