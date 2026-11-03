# Test fixtures

One folder per case, `tests/fixtures/<slug>/`, created with the `/add-fixture` skill:

- the input file(s) the code under test reads;
- `expected.json` — the expected result (`"format": 1`, `"synthetic": true|false`);
- `response.json` (optional) — recorded replies of a remote service, replayed by a fake;
- `notes.md` — what the fixture covers.

Never real user data: anonymised or synthetic only.

Scripts used as fake child processes (not cases) live at the top level:

- `fake_server.py` — a fake `rack serve` for the supervisor tests (`tests/integration/test_supervise.py`): records each start, prints lines, exits with a given code after a given time, optionally ignores SIGTERM.
