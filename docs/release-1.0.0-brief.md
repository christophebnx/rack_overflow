# Rack Overflow — release 1.0.0 brief

Status: **approved by the user on 2026-11-03.** Source of truth for the V1 build. It replaces the pre-brief written outside the repository; the challenge that led from one to the other, with the user's answers, is kept in `docs/release-1.0.0-challenge.md` (history only: where the two differ, this file wins).

Repository `christophebnx/rack_overflow` · distribution `rack-overflow` · package `src/rack_overflow` · CLI `rack`.

**Languages:** the app speaks **French** to its user (UI, messages, seed data). Code, identifiers, docs and commits are in **English** (D-011).

---

## 1. Goal

Personal training tracker for strength training (machines, cables, barbell), kettlebell and bodyweight, and cardio.

V1 has four core functions:

1. **Create exercises and their variables.**
2. **Create session templates** organised as menus by movement pattern (push, pull, hinge, squat, core, cardio…) rather than a fixed program.
3. **Log a session**, fast, at the gym or at home.
4. **Minimal progress tracking.**

Single user in V1, without closing the door to multi-user.

## 2. Usage contexts

| Context | Device | Network | Main need |
|---|---|---|---|
| Session at the gym (Basic-Fit Overijse) | iPhone, Safari | Available | Logging speed, large buttons, prefill |
| Session at home (kettlebell, EZ bar, dumbbells) | iPhone, Safari | Available | Same |
| Management and review | Mac / PC, browser | Available | Catalog, templates, history, charts |

## 3. Scope

### 3.1 Versions

| Version | Content |
|---|---|
| **V1 (1.0.0)** | Milestones L1a to L6 (section 6), one release, no intermediate tag |
| **V1.x** | Excel import with review, %1RM targets in templates |
| **V2** | HTTPS and transport security (D-013); offline logging, possibly as a mobile app talking to the FastAPI server; AI features (section 9); body metrics; actual multi-user; minimal CI (D-012) |

### 3.2 Out of scope for V1

Offline mode, PWA, service worker, separate mobile app; HTTPS and reverse proxy; rest timer; work / rest ratio of intervals; external integrations (Garmin, Apple Health, Strava); scanned paper log import; social; nutrition; auto-progression programs; automatic CI.

## 4. Cross-cutting requirements

- **One responsive web app** for phone and desktop. Mobile first (360 px), usable at 1280 px, light and dark following the system, touch targets ≥ 48 px. French only.
- **Logging speed**:
  - confirm an unchanged set: **1 tap**;
  - confirm a modified set: **≤ 3 taps** in the common case;
  - start a session from a template: **≤ 3 taps**;
  - no keyboard in the nominal case;
  - server handling of a set confirmation **< 100 ms**; the confirmed set shows as soon as the response arrives.
- **No silent loss**: a request that fails leaves the form with its values and shows « Non enregistré, réessayer ». The confirm button is disabled while its request runs.
- **Display units**: kg and km (metres and seconds where relevant: swim distance, durations). No unit switch in V1.
- **Security** (D-013, D-034, D-040): plain HTTP in V1, LAN only during development, then a high non-standard port forwarded through the DDNS. Per-device authentication, `HttpOnly` `SameSite=Strict` cookie, `Origin` / `Sec-Fetch-Site` check, JSON-only requests, `Host` check, strict CSP. No secret in the repository.
- **Privacy**: pages load no external resource, no telemetry.
- **Portability**: same native Python deployment (no Docker) on Synology NAS (DS224+) and Jelastic Cloud (Infomaniak).
- **Cost**: no license, store fee or paid CI.

## 5. Architecture (summary)

### 5.1 Stack

| Layer | Choice |
|---|---|
| Language | Python ≥ 3.12, uv, hatchling |
| Web | FastAPI + uvicorn, Pydantic v2, **Jinja2 templates rendered on the server**, **htmx** for partial updates with the `json-enc` extension (D-015, D-034) |
| Static assets | htmx, `json-enc` and Chart.js vendored under `static/vendor/` at pinned versions; CSS split into tokens / base / components / pages; no build step |
| Database | SQLite (WAL) through SQLAlchemy Core (no ORM), Alembic migrations, Postgres-compatible SQL, integer primary keys (D-016, D-035) |
| Tests | pytest (+ xdist, cov), isolation guard ported from Equinox (D-043), `live` marker, Playwright (Python package) on Chromium and WebKit, 360 / 1280 px, light / dark (D-042) |
| Quality | ruff, pylint duplicate-code, pre-commit, gitleaks; **no automatic CI** (D-012) |
| Delivery | Native Python, no Docker: `git` + `uv sync --frozen` + `rack migrate` + `rack serve`, supervised by the host (D-024, D-038) |

### 5.2 Request flow

The browser requests a page; FastAPI renders a full Jinja2 page. User actions are htmx requests sent as JSON; the route validates the body with Pydantic, calls a **service** (business operation, one transaction), and returns an HTML fragment that htmx swaps in place. Business rules live in `domain/` (pure), persistence in `storage/` (SQLAlchemy Core), orchestration in `services/`, HTTP in `web/`. A JSON API for a future mobile client or the V2 AI module is added on top of `services/` without rewriting it.

## 6. Milestones

Order: **B0 → L1a → L1b → L2 → L3 → L4 → L5 → L6.** Each milestone is demonstrable on its own and depends only on the previous ones. `docs/roadmap.md` holds the same list with the "Done when" lines; ids go in the `Milestone:` commit footer.

### B0 — Bootstrap

Template initialised (package, CLI `rack`), project docs written from this brief, hooks checked, local checks green.

### L1a — Technical foundation

- FastAPI app factory, `rack serve` (host and port from configuration), logs.
- Configuration: `config.toml` (git-ignored) for machine settings: data folder, host, port, public host name, `[server] https = false`; `.env` for secrets (none needed in V1). Loaded once at start-up, passed down explicitly.
- Database: SQLAlchemy Core engine, SQLite WAL, `foreign_keys = ON`, `synchronous = FULL`, `busy_timeout`; Alembic set up with batch mode; first migration with the full schema of section 7; `rack migrate`.
- Daily backup (`VACUUM INTO` a dated file, integrity check first, 30-day retention, never delete a corrupt file) run by the server once a day, and `rack backup`.
- Web base: base layout (Jinja2), vendored htmx + `json-enc`, CSS tokens (light / dark), French string catalog `locales/fr.json` resolved on the server, security middleware (headers, CSP, `Origin`, `Host`, JSON-only, body size), error pages.
- Tests: isolation guard, markers, Playwright set-up (Chromium + WebKit, skipped locally when browsers are missing, see D-042).
- Replace the template `hello` command and `domain/greeting.py`.

### L1b — Per-device authentication and NAS deployment

- `rack device add <name>` prints a one-time pairing code (valid 10 minutes, attempt-limited). The public pairing page exchanges it for a long-lived random token, stored **hashed**, sent as an `HttpOnly`, `SameSite=Strict` cookie (`Secure` only when `[server] https = true`), renewed on use.
- `rack device list`, `rack device revoke <name>`.
- Every page and action except the pairing page and static assets requires a valid device.
- Deployment docs for the NAS: clone, `uv sync --frozen` (uv provides Python 3.12), `rack migrate`, `rack serve` on the configured port, DSM Task Scheduler boot-up task running `rack supervise` (restart with increasing delay, rotating logs). LAN only during development; WAN exposure on a high non-standard port is a later, user-made router change.
- `rack update`: `git pull --ff-only`, `uv sync --frozen`, `rack migrate`, restart. The deployed clone stays on `main` with no local edits.
- **Planned stop**: the user installs on the NAS and checks the "user validation" criteria.

### L2 — Catalog: exercises and variables

- **Variable** catalog: code, French label, type (`int`, `decimal`, `duration`, `distance`, `weight`, `enum`, `bool`, `text`), display unit, scope (`set` = measure, `setting` = equipment setting), enum values, decimal scale, archived. **The seed contains no variable**: every variable is created in the UI (D-030).
- **Shared variables**: defined once, linked to one or more exercises; editing the definition applies to every linked exercise.
- **Core quantities** (reps, load, duration, distance) are built-in fields, not variables.
- **Exercise fields** (`exercise_field`, D-031): one link table for both core quantities and variables, with required, increment (+2.5 kg, +1 rep, +30 s), default, discrete values (e.g. kettlebells 16 / 20 / 24 kg), display order.
- **Exercises**: name, category (`strength`, `kettlebell`, `bodyweight`, `cardio`, `intervals`), movement pattern, equipment, location (gym / home / both), archived.
- **Aliases**, normalised (case, accents) for search; fuzzy search on names and aliases.
- Exercise seed of section 6.1 (core quantities only).

### L3 — Session templates (menus)

- A template is an ordered list of **slots**; a slot is a specific exercise or a **menu** (movement pattern + proposed exercises, chosen during the session).
- Optional indicative target per slot (sets × reps, duration…).
- Template seed of section 6.1.

### L4 — Session logging

- Start a session: empty or from a template, choose location.
- Menu slot: pick the exercise from the proposed list. Add an exercise outside the template: fuzzy search, recent first.
- **Prefill** sets from the exercise's last performance (else the target), and **settings** from the last session with this exercise.
- Adjust with steppers (field increment) or discrete values; ✓ confirms the set (htmx request, button disabled while it runs); ⭐ when the server detects a new record.
- Set type: warm-up / work / RM test. Optional variables shown collapsed.
- Layout adapted to the category (reps × load; duration / distance; rounds).
- An open session is resumed when the app is reopened. Close: summary (exercises, volume, records).

### L5 — Minimal tracking

- Session history: list, detail, online correction of a set or setting, soft delete of a session (`deleted_at`).
- Per exercise: last performance, records, chart of the main indicator over time (Chart.js, data from a JSON route).

| Category | Main indicator | Secondary |
|---|---|---|
| `strength` | e1RM | max load per rep count, volume |
| `kettlebell` | reps at a given load | density (reps / duration), volume |
| `bodyweight` | reps | max duration, added load if weighted |
| `cardio` | distance or duration | pace / speed |
| `intervals` | number of rounds | total work duration |

- **RM** (`strength`): manual entry of a measured RM (1RM…nRM) outside a session; `rm_test` sets are read directly (one write per fact, D-033); estimation from work sets; origin shown (**mesuré** / **estimé**, with formula). Formulas: Epley (default), Brzycki, Lombardi, O'Conner, Wathan, global choice in settings. Warm-up sets and sets above 12 reps excluded from estimation.
- Consistency: sessions per week.

### L6 — Operations

- Full JSON and CSV export (UI and `rack export`).
- `rack restore` (server stopped), documented and tested.
- Install and update docs: Synology NAS and Jelastic (Linux / VPS node with a systemd unit, `Restart=on-failure`; database on the node's local disk, never a network volume).
- NAS ↔ Jelastic migration documented (backup, restore, URL change).
- Release 1.0.0 (`/release`).

### 6.1 Seed data (approved 2026-11-03)

Names in French as shown in the UI. Core quantities only (D-030); targets are indicative. A **menu** slot offers several exercises, chosen during the session.

**Salle A — Squat & poussée horizontale**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Squat | Squat au rack (barre) | 4 × 6–8 |
| 2 | Poussée horizontale | Développé couché (barre) | 4 × 6–8 |
| 3 | Menu Tirage horizontal | Rowing barre au rack · Rowing assis machine · Tirage horizontal poulie | 3 × 8–10 |
| 4 | Menu Jambes unilatéral | Fentes haltères · Split squat bulgare · Presse à cuisses | 3 × 10 |
| 5 | Biceps | Curl barre EZ | 3 × 10–12 |
| 6 | Menu Gainage | Planche · Crunch poulie haute · Relevé de jambes suspendu | 3 × 30 s / 12 |

**Salle B — Charnière & poussée verticale**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Charnière | Soulevé de terre roumain (RDL) | 4 × 8 |
| 2 | Poussée verticale | Développé militaire haltères | 4 × 8 |
| 3 | Menu Tirage vertical | Tirage vertical poulie · Tractions assistées machine · Tractions | 3 × 8–10 |
| 4 | Poussée inclinée | Développé incliné à la Smith | 3 × 8–10 |
| 5 | Menu Ischios / fessiers | Leg curl allongé · Hip thrust à la Smith · Extension lombaire | 3 × 10–12 |
| 6 | Menu Triceps | Extension triceps poulie · Barre au front EZ · Dips | 3 × 10–12 |

**Maison — Kettlebell, barre EZ, haltères**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Charnière | Kettlebell swing (charges 16 / 20 / 24 kg) | 5 × 15 |
| 2 | Squat | Goblet squat kettlebell | 4 × 10 |
| 3 | Menu Poussée | Pompes · Développé haltères au sol · Développé militaire kettlebell | 3 × 10 |
| 4 | Tirage | Rowing haltère un bras | 3 × 10 / côté |
| 5 | Menu Bras | Curl barre EZ · Curl marteau haltères · Barre au front EZ | 3 × 12 |
| 6 | Menu Gainage | Planche · Turkish get-up kettlebell | 3 × 30 s / 3 par côté |

**Cardio — Course 30 min**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Menu Cardio | Course extérieure · Tapis de course · Vélo · Rameur | 1 × 30 min (durée + distance) |

**Catalog without template** (through search): Elliptique (cardio), Squat à la Smith, Développé couché haltères, Leg extension, Mollets debout machine.

## 7. Storage model

### 7.1 Principles

- **Measures and settings are distinct** (D-019). A *measure* changes on every set (reps, load…). A *setting* is fixed for the exercise within the session (seat height, grip, incline) and is prefilled from last time.
- **Hybrid storage** (D-018): the four quantities that drive computations are `set_entry` columns (`reps`, `weight_g`, `duration_s`, `distance_m`). Other variables live in value tables linked to the `variable` catalog. Adding a variable needs no migration.
- **Canonical integer units** (D-020): grams, seconds, metres. A `decimal` variable is stored as an integer with the scale fixed on the variable; an `enum` value is stored by its stable key, never its label (D-032).
- **Facts stored, indicators computed** (D-021): sessions, sets, settings and measured RMs are stored; last performance, e1RM, records and volume are computed on the fly.
- **No physical deletion of history**: exercises and variables are archived; sessions and sets are soft-deleted (`deleted_at`); removing a field from an exercise keeps past values.
- **Ids**: integer primary keys generated by the database (D-035).
- **Timestamps**: UTC ISO 8601; sessions also keep local date and time zone.
- **`user_id`** on root tables (D-017).
- **Intervals**: one set = one round, `duration_s` = work time (D-041).

### 7.2 Schema

```
variable ──< exercise_field >── exercise ──< exercise_alias
                                    │
template ──< template_slot ─────────┤   (slot → exercise or menu: template_slot_option)
                                    │
session ──< session_exercise ───────┘
                │        └──< exercise_setting   (settings)
                └──< set_entry ──< set_value      (free measures)

rm_measured · device · pairing_code · app_setting
```

| Table | Main fields |
|---|---|
| `variable` | user_id, code, label, type, display unit, scope (`set` / `setting`), enum values (key + label), decimal scale, archived |
| `exercise` | user_id, name, category, movement pattern, equipment, location, archived |
| `exercise_field` | exercise_id, **either** core quantity (`reps` / `weight` / `duration` / `distance`) **or** variable_id (CHECK: exactly one), required, increment, default, discrete values, display order |
| `exercise_alias` | exercise_id, alias, normalised alias |
| `template` | user_id, name, location, order, archived |
| `template_slot` | template_id, order, exercise_id **or** movement pattern (menu), indicative target |
| `template_slot_option` | template_slot_id, exercise_id, order (exercises proposed by a menu) |
| `session` | user_id, local date, time zone, started_at, ended_at, location, template_id, notes, status (`open` / `closed`), deleted_at |
| `session_exercise` | session_id, exercise_id, template_slot_id, order, notes |
| `exercise_setting` | session_exercise_id, variable_id, `value_int` / `value_text` |
| `set_entry` | session_exercise_id, order, type (`warmup` / `work` / `rm_test`), `reps`, `weight_g`, `duration_s`, `distance_m`, completed_at, deleted_at |
| `set_value` | set_entry_id, variable_id, `value_int` / `value_text` |
| `rm_measured` | user_id, exercise_id, n, `weight_g`, date — manual entry only (D-033) |
| `device` | user_id, name, token hash, created_at, last_seen_at, revoked_at |
| `pairing_code` | device_id, code hash, expires_at, attempts, used_at |
| `app_setting` | user_id, key, value (RM formula…) |

### 7.3 SQLite operations

WAL, `foreign_keys = ON`, `synchronous = FULL` in production, `busy_timeout`; backup via `VACUUM INTO`; local storage only (never a network volume); restore with the server stopped.

## 8. Routes (sketch)

HTML routes return a full page (normal navigation) or a fragment (htmx request, `HX-Request` header). Every non-GET request is JSON (D-034).

| Area | Routes | Milestone |
|---|---|---|
| Pairing | `GET /appairage`, `POST /appairage` | L1b |
| Variables | `GET /variables`, `POST /variables`, `PATCH /variables/{id}` | L2 |
| Exercises | `GET /exercices`, `GET /exercices/{id}`, `POST /exercices`, `PATCH /exercices/{id}`, fields and aliases sub-routes, `GET /exercices/recherche?q=` | L2 |
| Templates | `GET /seances-types`, `POST`, `PATCH`, slots sub-routes | L3 |
| Session | `POST /seances`, `GET /seances/{id}`, `POST /seances/{id}/exercices`, `POST /seances/{id}/series`, `PATCH /series/{id}`, `POST /seances/{id}/cloture` | L4 |
| History | `GET /historique`, `PATCH /series/{id}`, `DELETE /seances/{id}` (soft) | L5 |
| Progress | `GET /progression/{exercise_id}`, `GET /api/progression/{exercise_id}` (JSON for the chart), `GET/POST /rm/{exercise_id}` | L5 |
| Export | `GET /api/export?format=json|csv` | L6 |

URL paths are in French because the user sees them; route function names stay in English. The architect of each milestone fixes the final list.

## 9. V2 preparation: AI features (not in V1)

- Server module `rack_overflow/ai/` exposing **domain tasks** (`analyse_session`, `propose_next_session`, `motivation`, `weekly_review`), never an SDK directly.
- One **Pydantic AI** agent per task, structured output, read-only tools over the data, configurable provider (`[ai] provider = "claude" | "bridge" | "none"`).
- AI is always asynchronous and optional, never in the logging path; results stored (`ai_insight`).

**V1 impact: none**, beyond clean data and tracking computations exposed through `services/` (D-025).

## 10. Approvals for the unattended run

The user approved this brief on 2026-11-03 for `/build-roadmap`:

- The architect records new decisions without stopping when this brief settles the point, and marks the design note APPROVED FOR AUTONOMOUS MODE.
- On a question this brief does not settle, the architect writes it in `docs/progress.md` and moves to the next independent milestone if there is one; otherwise the run stops (`BLOCKED`).
- Planned stops: end of B0 (user checks the result), end of L1b (installation on the NAS and "user validation" criteria), end of L6 (release).
- Criteria marked **user validation** in `docs/roadmap.md` are checked by the user; the run notes them in `docs/progress.md` and continues.
- Dependencies may be added when this brief names them (FastAPI, uvicorn, Pydantic, Jinja2, SQLAlchemy, Alembic, python-dotenv, tomli-w, httpx, Playwright, vendored htmx / json-enc / Chart.js). Any other dependency needs a measured reason in the design note.

## 11. Settled open points

**A. Offline and mobile app.** Dropped for V1: one responsive web app, server-rendered with htmx (D-015). The gym network is reliable. Offline is a later release, possibly a mobile app using a JSON API over `services/`.

**B. JSON-only requests.** Kept from Equinox: htmx sends JSON through `json-enc`; a cross-site form cannot post without a CORS preflight (D-034). A future file upload (Excel import, V1.x) gets its own documented exception.

**C. Transport security.** Plain HTTP in V1, LAN only during development, then a high non-standard port through the DDNS; HTTPS in V2 through a configuration switch (D-013).

**D. Database access.** SQLAlchemy Core + Alembic rather than Equinox's raw `sqlite3`: here the database is the only source of truth and its schema will evolve with real data (D-016). Integer primary keys (D-035).

**E. Core quantity parameters.** One `exercise_field` table for core quantities and variables (D-031).

**F. Intervals.** Work / rest ratio removed from V1; one set = one round (D-041).

**G. RM stored once.** `rm_measured` for manual entry only; `rm_test` sets read directly (D-033).

**H. Records.** Computed on the server when a set is confirmed; no formula in JavaScript.

**I. Double submission.** Button disabled during the request; no idempotency token in V1.

**J. Backups early.** Daily backup and `rack backup` in L1a; export, restore and Jelastic docs in L6.

**K. Supervision.** NAS: DSM boot-up task running `rack supervise`. Jelastic: Linux / VPS node with systemd (D-038).

**L. Strings.** One flat catalog `locales/fr.json` resolved on the server; stable English error codes mapped to French strings (D-036).

**M. CI.** None until V1 is done (D-012).

**N. Release.** One release 1.0.0, no intermediate tag.

**O. Seeds.** Section 6.1, approved.

**P. Decision numbering.** The pre-brief's D-001 to D-019 are recorded from D-014 on in `docs/decisions.md` (the template uses D-001 to D-011, the project D-012 and D-013). Pre-brief D-002 to D-004 (PWA, offline, pack + outbox) are dropped.

---

> **Reading the appendix with this brief.** Where the appendix and the brief differ, the brief wins: A.4 (no automatic CI, D-012; Playwright is the Python package, D-042), A.5 (no reverse proxy in V1: `Host` is checked against the configured host name, D-013), A.6 (strings resolved on the server, no `GET /api/locale` nor `i18n.js`, D-036), A.7 (server-rendered pages with htmx instead of an ES-module client; the CSS split and accessibility rules still apply, with 48 px targets).

## Appendix — Equinox reference (extracted 2026-11-03)

Read once from `christophebnx/equinox_management` (version 1.3.0) so this project never needs that repository again. Equinox decision numbers (D-xxx) below are **Equinox's**, not this project's. "Reuse" means re-implement the same design here; nothing is copied as a dependency.

### A.1 Tooling (already identical in this template)

- `pyproject.toml`: hatchling, `requires-python = ">=3.12"`, ruff `line-length = 110`, `target-version = "py312"`, lint `select = ["E", "F", "W", "I", "B", "UP", "SIM", "N", "RUF"]`; pylint `duplicate-code` only, `min-similarity-lines = 6`, comments and docstrings ignored. This template already has exactly these settings.
- Runtime dependencies Equinox uses that Rack Overflow will also need: `fastapi>=0.115`, `uvicorn>=0.30`, `pydantic>=2.8`, `python-dotenv>=1.0`, `tomli-w>=1.0`, `httpx>=0.27` (dev, for the FastAPI test client). `tzdata` only on Windows.
- Pre-commit (`default_install_hook_types: [pre-commit, commit-msg]`): local hooks `ruff format`, `ruff check --fix`, pylint duplicate-code, commit-message check (`tools/check_commit_message.py`, stage `commit-msg`); remote hook gitleaks `v8.21.2`. Same as this template.
- pytest markers in Equinox: `live`, plus three opt-outs of the isolation guard (A.3): `real_home(reason)`, `external_network(reason)`, `real_fsync(reason)`; `reason=` is required. `addopts = "-m 'not live'"`.

### A.2 Database access (answers point 11.1)

- **Equinox uses no SQLAlchemy and no Alembic.** Raw `sqlite3` everywhere, one module `storage/sqlite_index.py` owning every query, schema in `.sql` files (`schema_owned.sql`, `schema_projected.sql`), version in `PRAGMA user_version`.
- `connect(path)`: `sqlite3.connect(path, isolation_level=None)` (explicit transactions), `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`, `journal_mode = DELETE`, `synchronous = FULL`, `busy_timeout = 5000`. Writes go through a `_transaction` context manager: `BEGIN IMMEDIATE … COMMIT`, or a savepoint when already in a transaction.
- Why `journal_mode = DELETE` there: restore and set-aside of a corrupt database must be a single file. Side files to handle when moving a database: `-journal`, `-wal`, `-shm`.
- **Key difference:** in Equinox, SQLite is mostly a projection rebuildable from JSON files, so schema changes are cheap. In Rack Overflow, SQLite is the only source of truth: a real migration tool is justified, which is why this brief keeps SQLAlchemy Core + Alembic and WAL.
- Each web request opens its own connection (Equinox D-079 lock for mutations; single instance).

### A.3 Test isolation guard (Equinox D-107, `tests/isolation.py`, ~300 lines)

To re-implement in `tests/isolation.py` + `tests/conftest.py`:

- `pytest_configure` calls `isolation.install(Path.home())`, which records the real home before any redirection and adds **one process-wide audit hook** (`sys.addaudithook`); every xdist worker installs its own. The hook does nothing until activated by an **autouse fixture** around each test, so collection and plugins are unaffected.
- The autouse fixture also redirects the home folder (`HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_*`) to a temp folder.
- While active it refuses:
  - any write (open for writing — flags `O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC` —, `os.remove`, `rmdir`, `mkdir`, `chmod`, `truncate`, `rename`/`replace`, `link`, `symlink`, `shutil.rmtree`, `shutil.move`, SQLite connect) under the real home or the repository `.local/`;
  - any open, read included, under `<repo>/.local/`, of `<repo>/.env` or `<repo>/config.toml` (no opt-in);
  - any name lookup, TCP connect or bind that is not loopback or `AF_UNIX` (UDP `sendto` not watched). Loopback stays allowed, which the browser tests need.
- Forbidden zone = real home minus allowed roots: the repository checkout (its `.local/` excepted), the interpreter prefixes (venv), the system temp folder, pytest's base temp folder. Paths through `__pycache__` are allowed. Paths are compared after `realpath` of the parent folder (cached) and `normcase`; a last-component symlink is not followed.
- A refusal raises `IsolationError(AssertionError)` — not an `OSError`, so product code never swallows it — and is also recorded, so the fixture fails the test at teardown even if the refusal happened in a thread or was caught.
- Subprocesses are not hooked; they inherit the temp home only.
- Tests skip disk flushes: an autouse fixture makes `os.fsync` a no-op and sets `PRAGMA synchronous = OFF` on the project's `connect`; `@pytest.mark.real_fsync(reason=...)` keeps them. A `strict_network` variant refuses every lookup, loopback included.
- Other conftest helpers: a `snapshot` fixture that maps a folder tree to (kind, bytes, mtime) to assert "nothing changed"; system tools invoked by the app are replaced by a fake that fails if called for real.

### A.4 CI (Equinox `.github/workflows/ci.yml`)

- `lint` job on Ubuntu: `uv sync --locked`, ruff check, ruff format check, pylint duplicate-code.
- `test` job, matrix ubuntu / windows / macos, `timeout-minutes: 15`: `uv run pytest -q -n auto --dist worksteal -m "not live" --durations=30`; on Ubuntu only, `-W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning` so leaked files, sockets and SQLite connections fail the run. `workflow_dispatch` inputs `tests` and `repeat` to rerun chosen tests and hunt flakes.
- `browser` job on Ubuntu, `timeout-minutes: 20`: **Playwright is the Node package** (`npm install -g playwright@1.64.1`, Node 22), browsers cached in `~/.cache/ms-playwright`, `playwright install --with-deps chromium`, then pytest drives it (`tests/e2e/test_browser.py`); without Node/Playwright the test is skipped locally, and an env var (`EQUINOX_REQUIRE_BROWSER=1`) makes it mandatory in CI. Screenshots (360 / 1280 px) uploaded as an artifact, 30-day retention.
- `concurrency: ci-${{ github.ref }}`, `cancel-in-progress: true`; `astral-sh/setup-uv@v6` with cache, Python 3.12.
- For Rack Overflow: add WebKit to the browser job (closest engine to iOS Safari); decide whether to use Python Playwright instead of the Node package.

### A.5 Web security headers and request checks (Equinox `web/security.py`, one module)

- Every response: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`. API responses `Cache-Control: no-store`. No CORS header ever.
- On every request other than GET/HEAD, and on GET/HEAD under `/api/`: an `Origin`, when sent, must be this server; `Sec-Fetch-Site`, when sent, must be `same-origin` or `none`. Otherwise `403 forbidden_origin`, echoing nothing.
- Every request other than GET/HEAD needs `Content-Type: application/json` (`415`). Body size checked from `Content-Length` before reading where a limit applies.
- Equinox also checks `Host` against `127.0.0.1` / `localhost` (DNS rebinding) because it binds localhost without a proxy. Rack Overflow sits behind a reverse proxy: check `Host` against the configured public host name instead.
- Implemented as a Starlette `BaseHTTPMiddleware`.

### A.6 User-language strings (answers point 11.9)

- One loader `locale.py` (imports no other project module): strings in `web/locales/<lang>.json`, a **flat** `{key: text}` object, read as `utf-8-sig`, `{name}` placeholders. Missing keys fall back to `fr`. A malformed file raises `LocaleError`.
- Served to the front end by `GET /api/locale` (`{language, strings}`); `static/js/i18n.js` loads them, sets `<html lang>`, and a missing key shows the key itself and logs a warning, so a gap is visible. Until strings load, the page shows a skeleton with no text and retries every 5 s.
- The API returns stable English error codes (`forbidden_origin`, `stale`…); the UI maps them to French strings.
- For Rack Overflow: the session screen must work offline, so the strings must also be cached by the service worker (or included in the pack).

### A.7 Front end conventions

- Plain HTML, CSS and ES modules, no framework, no build step. CSS split into `tokens.css` (colours, type scale, radii, shadows, dark mode), `base.css`, `components.css`, plus one file per page. JS: one module per concern (`api.js` fetch wrapper, `dom.js`, `i18n.js`, `confirm.js`, `notice.js`…). Fonts vendored locally (no external resource).
- Accessibility rules in Equinox `docs/ui-spec.md` worth reusing: real `<button>`/`<a>`/`<input>` with `<label>`; text contrast ≥ 4.5:1 and control borders ≥ 3:1 in light and dark; no horizontal scroll at phone width; dialogs with `role="dialog"` and `aria-modal`; invalid fields marked and their message tied to them; action results announced once through permanent live regions; 3 px focus ring; one shared confirmation dialog where, for a destructive choice, the safe answer has focus and Esc means "no". Equinox uses 44 px touch targets; this brief asks for 48 px.
- `docs/ui-spec.md` structure: global rules (accessibility, appearance) first, then one section per screen, every string in French as shown to the user.

### A.8 Backups (Equinox `storage/backup.py`)

- Snapshots are taken with the SQLite backup API (never a file copy of a live database), written atomically with `files.atomic_write`, named `index-<YYYYMMDDTHHMMSSZ>.sqlite` (`_02` suffix on a same-second collision).
- An integrity check runs first; a corrupt database is never backed up and never deleted: it is moved aside as `<name>.corrupt-<ts>` with its side files, then restored from the latest snapshot.
- Retention 30 by default, configurable; rotation deletes the oldest.
- Rack Overflow plans `VACUUM INTO` instead of the backup API: equivalent consistency, compacted output; keep the integrity check, the atomic naming and the never-delete-a-corrupt-file rules.

### A.9 Process and docs conventions

- Release briefs (`docs/release-x.y.z-brief.md`): status line with the approval date; Goal; Findings (current state of the code); **"Approvals for the unattended run"** (the architect records new decisions without stopping when the brief settles the point; on an unsettled question it writes it in `docs/progress.md` and moves to the next independent lot); **"Settled open points"** (lettered A, B, C…, each with the answer, and "As built" notes when the implementation differs); **Work order** table (order, id, lot, deliverable) with the reason for the order; one section per lot.
- Roadmap: one section per milestone with its content and a "Done when" line; milestone ids in the commit footer.
- Decisions: one bold line `**D-nnn — statement.**`, then why, what it rules out, a `Status:` with approval date when user-approved, and "Refines / Supersedes D-xxx" links.
- Deployment rule (Equinox launcher): the deployed clone stays on `main`, updated by `git pull --ff-only` only, never edited locally.
