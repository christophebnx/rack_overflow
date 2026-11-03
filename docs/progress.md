# Build progress

Maintained by the `/build-roadmap` skill. Branch: the session's designated branch (it plays the role of `dev`). One row per milestone of `docs/roadmap.md`. Status: `todo`, `in progress`, `done`, `BLOCKED`.

| Milestone | Status | Commit | Notes |
|---|---|---|---|
| B0 Bootstrap | done | 45ef5e4 | Package `rack_overflow`, CLI `rack`; approved brief, roadmap, decisions D-012 to D-043; hooks checked (secret read and push on `main` blocked, formatter runs); 52 tests, ruff and duplicate-code green locally. Commit on `main` not tried live; the hook code checks it like push, but `tests/unit/test_guard_paths.py` covers only the push case. |
| L1a Technical foundation | done | fabc6ed | Built: settings file, schema and migrations (head `0002`), `rack migrate`, `rack backup` and daily backup, web base and security middleware, `rack serve`, isolation guard, Playwright set-up; `hello` removed.<br>Tests: 447 passed, 12 WebKit skipped (WebKit not installed in the build environment; to be run where WebKit is available, `RACK_REQUIRE_BROWSER=1`).<br>Open: brand / content alignment and htmx error display decided in L2; the integrity check opens the source database read-write by design. |
| L1b Auth and NAS deployment | todo | | Planned stop: user validation on the NAS |
| L2 Catalog | todo | | |
| L3 Templates | todo | | |
| L4 Session logging | todo | | |
| L5 Tracking | todo | | |
| L6 Operations and release 1.0.0 | todo | | |

## User validations pending

- L1a: run the browser tests on WebKit (`RACK_REQUIRE_BROWSER=1 uv run pytest -q tests/e2e` on a machine with WebKit installed); only Chromium ran in the build environment.

## Blocking question

None.
