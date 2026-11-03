# Decisions

Each entry: the decision, why, and what it rules out. Do not reverse a decision silently: add a new entry that supersedes it (skill `/add-decision`).

## Tooling

**D-001 — Python ≥ 3.12, managed with uv; `uv.lock` is versioned.**
One tool for the interpreter, the virtual environment, dependencies and the lock file. CI runs `uv sync --locked`, so a dependency change without a lock update fails. Rejected: pip + requirements files (no lock of transitive versions), Poetry (slower, second tool).

**D-002 — Lint and format with ruff; duplicate code detected with pylint `duplicate-code`.**
Ruff runs in CI, in pre-commit and after every Claude Code edit (`.claude/hooks/format.py`). Pylint runs only its duplicate-code checker: it is the mechanical half of the one-responsibility rule (D-006); the reviewer agent covers the other half.

## Code structure

**D-003 — Source layout `src/<package>/`, pure `domain/` layer at the centre.**
`domain/` holds business rules and imports nothing else from the project; it reads no file, network, clock or environment (callers pass them in). Outer layers depend on it, never the reverse. Enforced by `tests/unit/test_layering.py`. Why: business rules stay testable in isolation and do not change when storage or interfaces change.

**D-004 — The CLI is a technical tool: English messages, explicit exit codes.**
0 success, 1 error, 2 usage. Errors print `<prog>: error: <message>` on stderr. Tests call `main([...])` in-process.

**D-005 — Atomic file writes only.**
Every user or state file is written by `storage/files.atomic_write` (temp file in the same folder, fsync, rename, folder fsync). A crash leaves the old file or the new one, never a mix.

**D-006 — One responsibility, one implementation.**
Each responsibility has exactly one implementation, listed in the responsibility map of `docs/architecture.md`. Duplication with a different implementation is a blocking review finding. Similar-looking code with a different responsibility is allowed.

## Working with Claude Code

**D-007 — Every change goes through `/feature`: architect → (ui-designer) → developer → tester → reviewer → documentation.**
Each agent has one job, limited tools and a ten-line report; details go into `docs/`. The architect writes a design note in `docs/architecture/` before any code. Why: decisions and designs survive the conversation, and the review checks the change against written rules rather than memory.

**D-008 — Autonomous build from the roadmap, state in `docs/progress.md`.**
`/build-roadmap` runs the milestones of `docs/roadmap.md` in order and stops on documented conditions (repeated failures, a decision to supersede, anything only the user can provide), writing `BLOCKED` and the question in `docs/progress.md`.

**D-009 — Claude Code never reads secrets and never commits or pushes on `main`.**
Enforced by `permissions.deny` in `.claude/settings.json` and by the PreToolUse hook `.claude/hooks/guard_paths.py` (secret files, protected folders, `git commit` and `git push` on `main`). Force-push, hard reset and branch deletion are denied. The user merges into `main` through pull requests.

**D-010 — Conventional Commits with a `Milestone:` footer, checked by a commit-msg hook.**
`tools/check_commit_message.py` (installed by `uv run pre-commit install`) rejects malformed messages. The footer ties every commit to a roadmap item. Git's own merge, revert and fixup messages pass unchecked.

**D-011 — English for code and repository text; the user language for what the end user sees.**
Code, identifiers, docs, prompts, agents, skills and commits in English. UI strings and exported content in the user language, from locale files.

## Project

**D-012 — No automatic CI until V1 is done; checks run locally.**
GitHub Actions minutes cost money, so the workflow runs only on manual dispatch (`workflow_dispatch`). Until V1 is complete, the definition of done is checked locally: tests (`not live`), ruff and duplicate-code, run by the tester and reviewer agents and by pre-commit. Once V1 is done, a minimal CI is designed (which jobs, which OS) and recorded in a new decision. Refines D-001 and D-002 (the "runs in CI" parts apply only to manual runs). Rules out: automatic runs on push or pull request, the three-OS matrix as a default. Status: approved by the user on 2026-11-03.

**D-013 — V1 is served over plain HTTP; transport security is deferred to V2.**
During development the app is reachable on the LAN only, with no WAN exposure. Once in use, the server listens on a high, non-standard port (from configuration) forwarded through the DDNS, without reverse proxy or certificate. Why: single user, unadvertised app, simpler deployment. Accepted risk: data and the session cookie travel in clear. Kept in V1: per-device authentication, `HttpOnly` / `SameSite=Strict` cookie, `Origin` check and JSON-only requests. The cookie `Secure` flag and HSTS depend on a configuration switch, so V2 enables HTTPS without code change. Status: approved by the user on 2026-11-03.

The entries below come from the approved release brief `docs/release-1.0.0-brief.md` (pre-brief D-001 to D-019, renumbered; pre-brief D-002 to D-004 dropped by D-015). Status of each: approved by the user on 2026-11-03.

### Product and stack

**D-014 — Same stack and tooling as Equinox Management: FastAPI, uvicorn, Pydantic v2, uv, ruff, pylint duplicate-code, pre-commit.**
Existing know-how and conventions are reused (appendix of the brief). Rules out: another web framework, Node tooling in the product.

**D-015 — V1 is one responsive web app, rendered on the server with Jinja2 and htmx; no PWA, no offline mode, no separate mobile app.**
The same pages serve the iPhone (360 px) and the desktop (1280 px). The gym network is reliable, so offline brings complexity (pack, outbox, service worker) without need. Offline may return in a later release, possibly as a mobile app using a JSON API added over `services/`. Rules out in V1: service worker, IndexedDB, client-side business logic, a front-end framework or build step. Supersedes pre-brief D-002 to D-004.

**D-016 — SQLite (WAL) through SQLAlchemy Core and Alembic; SQL kept Postgres-compatible.**
Unlike Equinox, the database is the only source of truth and its schema will evolve with real data, so real migrations are needed (Alembic batch mode for SQLite). No ORM: queries are explicit. Rules out: raw `sqlite3` with `PRAGMA user_version`, an ORM, SQLite-only SQL.

**D-017 — `user_id` on root tables from V1.**
Single user in V1, but multi-user later needs no schema migration of history.

**D-018 — Hybrid storage: four fixed columns on `set_entry` plus catalogued variables.**
`reps`, `weight_g`, `duration_s`, `distance_m` drive the computations and stay plain columns; every other measure or setting is a row in a value table referencing the `variable` catalog, so adding a variable needs no migration. Rules out: a wide table with one column per measure, full EAV, a JSON column.

**D-019 — Measures (per set) and settings (per session exercise) are distinct.**
A setting (seat height, grip) is fixed for the exercise within a session and prefilled from last time.

**D-020 — Canonical integer units: grams, seconds, metres.**
Conversion to kg and km happens only on display. No rounding error in storage.

**D-021 — Facts are stored, indicators are computed; history is never physically deleted.**
Sessions, sets, settings and measured RMs are stored; last performance, e1RM, records and volume are computed on the fly (low volume, no cache to invalidate). Exercises and variables are archived, sessions and sets soft-deleted (`deleted_at`).

**D-022 — RM: measured or estimated origin is tracked; the estimation formula is a global setting.**
Changing the formula recomputes estimates and never touches measured RMs. A measured RM wins on display; an estimate above an older test is flagged.

**D-023 — Session templates are menus by movement pattern.**
A slot is a specific exercise or a menu of proposed exercises chosen during the session, matching a non-fixed training practice.

**D-024 — Hosting on a Synology NAS or Jelastic, native Python deployment without Docker.**
`git` clone on `main`, `uv sync --frozen`, `rack migrate`, `rack serve`. SQLite on local storage only. The choice of host is reversible (backup, restore, URL change).

**D-025 — AI features are deferred to V2, behind a module of domain tasks with a configurable provider.**
V1 only keeps tracking computations reusable through `services/`.

**D-026 — Name Rack Overflow: distribution `rack-overflow`, package `rack_overflow`, CLI `rack`.**

**D-027 — The user language is French, and only French, in V1.**
Refines D-011: UI strings, messages, seed data and exports in French; code, docs and the CLI in English (D-004).

**D-028 — No rest timer in V1.**

**D-029 — Display units are kg and km only in V1** (metres and seconds where relevant). No unit switch.

### Data model

**D-030 — No variable in the seed; variables are created in the UI and shared across exercises.**
A variable is defined once (code, label, type, unit, scope) and linked to any number of exercises; editing it applies to all of them. The seed holds exercises and templates with core quantities only.

**D-031 — One link table `exercise_field` for core quantities and variables.**
Each row references either a core quantity or a variable (CHECK: exactly one) and carries the per-exercise parameters: required, increment, default, discrete values, display order. One place for parameters and one shared display order. Rules out: parameters of core quantities as columns of `exercise`.

**D-032 — A `decimal` variable is stored as an integer with a scale fixed on the variable; an `enum` value is stored by its stable key, never its label.**
Renaming an enum label never breaks history.

**D-033 — One write per fact for RMs.**
`rm_measured` holds only RMs entered manually outside a session; `rm_test` sets are read directly from `set_entry`.

**D-035 — Integer primary keys generated by the database.**
No client creates rows, so UUIDs bring nothing; integers are Postgres-compatible and readable in URLs.

**D-041 — Intervals: one set is one round, `duration_s` is the work time; no work / rest ratio in V1.**
V1 indicators for intervals: number of rounds and total work duration.

### Web and security

**D-034 — Every request other than GET / HEAD is JSON; htmx sends JSON through the vendored `json-enc` extension.**
A cross-site page can post a plain form without browser checks, but a cross-origin JSON request needs a CORS preflight, which this server never answers. With the `Origin` / `Sec-Fetch-Site` check and the `SameSite=Strict` cookie, this is the CSRF defence (Equinox `web/security.py`). Other rules kept from Equinox: CSP `default-src 'self'` with no inline script or style (htmx `includeIndicatorStyles: false`), `Referrer-Policy: no-referrer`, `nosniff`, no CORS header, `Host` checked against the configured public host name. Rules out: form-encoded bodies (a file upload later gets its own documented exception).

**D-036 — User-facing strings live in one flat catalog `locales/fr.json`, resolved on the server.**
Templates never hard-code French text; errors carry stable English codes mapped to French strings. A missing key renders the key itself and logs a warning.

**D-039 — Layers: `domain/` (pure rules), `storage/` (database and files), `services/` (business operations, one transaction each), `web/` (HTTP, templates), `cli.py`.**
Routes stay thin: validate, call a service, render. A future JSON API or AI module reuses `services/`.

**D-040 — Per-device authentication with a one-time pairing code and a long-lived cookie.**
`rack device add` issues a code valid 10 minutes, attempt-limited; the pairing page exchanges it for a random token stored hashed, sent as an `HttpOnly`, `SameSite=Strict` cookie (`Secure` when HTTPS is on, D-013), renewed on use, revocable. Rules out: passwords, tokens readable by JavaScript.

### Operations and tests

**D-037 — Daily backup from the first milestone with a database.**
`VACUUM INTO` a dated file, written atomically, integrity check first, 30-day retention; a corrupt database is never backed up nor deleted. Why early: real data exists as soon as logging works.

**D-038 — Supervision without Docker: `rack supervise` on the NAS, systemd on Jelastic.**
A DSM boot-up task does not restart a crashed process, so `rack supervise` restarts `rack serve` with an increasing delay and rotates logs. On Jelastic, a Linux / VPS node with a systemd unit (`Restart=on-failure`); the WSGI-oriented Python node does not fit an ASGI app.

**D-042 — Browser tests with the Python Playwright package, on Chromium and WebKit.**
WebKit is the closest engine to iPhone Safari. Pages are checked at 360 and 1280 px, light and dark. Without installed browsers the tests are skipped locally; `RACK_REQUIRE_BROWSER=1` makes them mandatory.

**D-043 — The Equinox test isolation guard is ported.**
A process-wide audit hook, activated around each test, refuses writes under the real home and `.local/`, reads of the secret and machine config files, and non-loopback network access; refusals fail the test even if caught. Loopback stays allowed for the browser tests.

### Technical foundation (L1a, design note `docs/architecture/2026-11-03-l1a-technical-foundation.md`)

**D-044 — Configuration: one required TOML file passed with `--config`, secrets in the `.env` beside it, loaded once by the CLI.**
`--config` defaults to `config.toml` in the current folder; a missing or invalid file, an unknown key or a wrong type is an error (exit 1), never a silent default. Relative `data_dir` is resolved against the config file's folder; `.env` is read with `dotenv_values` without touching `os.environ`. The committed `config.example.toml` is the development configuration (`.local/dev-data`). Only `cli.py` calls the loader; every other layer receives values. Refines the configuration convention of `docs/architecture.md`. Rules out: environment variables read by inner layers, defaults that could put production data in a development folder.

**D-045 — Backups: `rack-<UTC timestamp>.sqlite` snapshots by `VACUUM INTO` through the atomic writer, age-based retention keeping the newest, snapshot before a migration.**
Refines D-037. The integrity check runs before the copy and on the copy before its rename; a corrupt database is refused and logged, never moved, never deleted, and pruning is skipped. Retention removes snapshots older than `[backup] retention_days` (30) but always keeps the newest one; files whose name does not parse are never touched. `rack migrate` snapshots an existing database before applying pending revisions. The server runs the backup when the last one is at least 24 h old (checked at start-up and hourly). Moving a corrupt database aside and restoring is left to `rack restore` (L6). Rules out: count-based retention, the SQLite backup API, auto-restore by the server.

**D-046 — Database conventions: `BEGIN IMMEDIATE` transactions, frozen migrations shipped in the package, portable column types.**
Refines D-016, D-017, D-035. Every transaction starts with `BEGIN IMMEDIATE` (no `SQLITE_BUSY` on a read-to-write upgrade under WAL). Alembic scripts live in `storage/migrations/` and are configured in code, so an installed clone needs no `alembic.ini`; a committed migration is never edited, changes add a revision; upgrades run with foreign keys off and must pass `PRAGMA foreign_key_check` before commit. Columns: timestamps as UTC ISO 8601 text, `archived_at` / `deleted_at` / `revoked_at` nullable timestamps, `position` for order, JSON only for definition lists (enum values, discrete values), constraint naming convention, no `ON DELETE` actions, enumerated values from `domain/vocabulary.py` as `CHECK`, partial indexes declared for both SQLite and Postgres.

**D-047 — HTTP security details: pure ASGI middleware, loopback host names allowed, stable error codes, 64 KiB body limit.**
Refines D-034 and D-013. `Host` is checked by hostname (port ignored, since the DDNS forward may change it) against the configured public host plus `localhost`, `127.0.0.1`, `[::1]`, which DNS rebinding cannot use. Rejections answer JSON codes: `400 invalid_host`, `403 forbidden_origin`, `415 unsupported_media_type`, `413 payload_too_large`. `Cache-Control: no-store` on every non-static response; HSTS only when `[server] https = true`. htmx is configured by a `<meta name="htmx-config">` (`includeIndicatorStyles`, `allowEval`, `allowScriptTags` off, `selfRequestsOnly` on, `methodsThatUseUrlParams: ["get"]` so `DELETE` also sends JSON). Rules out: `BaseHTTPMiddleware`, inline htmx configuration script. Refined by D-048 (2026-11-03).

**D-048 — `Cache-Control: no-store` also on `/static/` error responses.**
Refines D-047. Every response with status ≥ 400 carries `no-store`, including under `/static/`, so a browser never caches a missing or failed asset in place of the real file; successful static responses keep default caching. Why: found in the L1a review. Rules out: cacheable error responses.
