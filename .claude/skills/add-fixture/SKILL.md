---
name: add-fixture
description: Adds an anonymised or synthetic test fixture (input + expected result) under tests/fixtures/. Use when a new kind of input or a regression case must be covered.
---

# Add a fixture

Fixtures live in `tests/fixtures/<slug>/` with:
- the input file(s) the code under test reads;
- `expected.json` — the expected result, with `"format": 1` and `"synthetic": true|false`;
- optionally `response.json` — recorded replies of a remote service, replayed by a fake in tests;
- `notes.md` — what the fixture covers and why it exists.

Rules:
1. Never copy real user data. The user provides an already anonymised file, or describes the case and you build a synthetic one (set `"synthetic": true`).
2. Anonymise: person names, addresses, phone numbers, e-mails, account and company numbers, dates of birth. Keep what matters for the test.
3. The slug is lowercase letters, digits and hyphens (`refund-negative-total`).
4. Add a test that loads the fixture and checks the result against `expected.json`. A new fixture can change another fixture's result: run the whole fixture test file and update every expectation it affects, on purpose.
5. Recorded replies from a real service are captured by a tool under `tools/`, run by the user (it needs a secret); never record from inside a test.
