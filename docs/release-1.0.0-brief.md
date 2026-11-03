# Rack Overflow — V1 pre-brief

> **Status: pre-brief, not approved.** Scoping document written outside the repository, to be challenged by Claude Code (repo access, agents, dev protocol) before producing `docs/architecture.md`, `docs/decisions.md`, `docs/roadmap.md` and `docs/ui-spec.md`. Once aligned with the user, this file becomes the approved release brief (with "Approvals for the unattended run" and "Settled open points").
> Repository `christophebnx/rack_overflow` · project `rack-overflow` · package `src/rack_overflow` · CLI `rack`.
> Date: 2026-11-03.
> **Languages:** the app speaks **French** to its users (UI, messages, seed data). Dev documents (briefs, ADRs, decisions, code, comments) are in **English**.
> **Equinox reference:** everything this project needs from the Equinox Management repository is recorded in the appendix at the end of this file. The Equinox repository is not consulted again.

---

## 1. Goal

Personal training tracker: strength training (machines, cables, barbell), kettlebell and bodyweight, cardio and HIIT.

V1 focuses on four core functions:

1. **Create exercises and their variables**
2. **Create sessions** (session templates and actual sessions)
3. **Log data during a session**, fast, including offline
4. **Minimal progress tracking**

Training follows **menus by movement pattern** (push, pull, hinge, squat, core, cardio…) rather than a fixed program.

Single user in V1, without closing the door to multi-user.

## 2. Usage contexts

| Context | Device | Network | Main need |
|---|---|---|---|
| Session at the gym (Basic-Fit) | iPhone | Often absent | Logging speed, large buttons, prefill |
| Session at home (kettlebell, EZ bar, dumbbells) | iPhone | Available | Same |
| Management and review | Mac / PC (browser) | Available | Catalog, templates, history, charts |

## 3. Scope

### 3.1 Roadmap

| Version | Content |
|---|---|
| **V1** | Deliverables L0–L6 (section 6): catalog and variables, templates, offline logging, minimal tracking, operations |
| **V1.x** | Excel import with review, %1RM targets in templates |
| **V2** | AI features (session analysis, suggestions, motivation) through a generic module (section 9), body metrics, actual multi-user |

### 3.2 Out of scope (not planned)

Rest timer (to add later if needed), external integrations (Garmin, Apple Health, Strava), scanned paper log import, native app, social, nutrition, auto-progression programs.

## 4. Cross-cutting requirements

- **Offline**: the session screen opens and works without network. No logged data is lost before it is sent.
- **Logging speed**:
  - confirm an unchanged set: **1 tap**;
  - confirm a modified set: **≤ 3 taps** in the common case;
  - start a session from a template: **≤ 3 taps, < 2 s**, online or offline;
  - no keyboard in the nominal case;
  - set confirmation **< 100 ms**, never waits for the network.
- **UI**: mobile first (360 px), usable on desktop (1280 px), light and dark following the system, touch targets ≥ 48 px. French only.
- **Display units**: kg and km only (metres and seconds where relevant: swim distance, durations). No unit switch in V1.
- **Security**: HTTPS only, authentication required, no secret in the repository, secrets in `.env` (`0600`).
- **Privacy**: pages load no external resource, no telemetry.
- **Portability**: same native Python deployment (no Docker) on Synology NAS (DS224+) and Jelastic Cloud (Infomaniak).
- **Cost**: no license or store fee (no Apple developer account).

## 5. Architecture (summary)

### 5.1 Stack — same as Equinox Management

| Layer | Choice |
|---|---|
| Language | Python ≥ 3.12 |
| API | FastAPI + uvicorn, Pydantic v2 |
| Front end | Static HTML / CSS / JS served by FastAPI, **no build step** |
| Offline | Service worker + IndexedDB, session screen only (PWA) |
| Database | SQLite (WAL) through SQLAlchemy Core (no ORM), Alembic migrations; Postgres-compatible SQL |
| Charts | JS library served locally (e.g. Chart.js) |
| Tooling | uv, hatchling, ruff (Equinox rules and line length), pylint, pre-commit |
| Tests | pytest (+ xdist, cov), isolation guard as in Equinox D-107, `live` marker, Playwright (360 / 1280 px, light / dark, offline) |
| CI | GitHub Actions: lint, tests, browser |
| Delivery | Native Python, no Docker: `git` + `uv sync --frozen` + `rack migrate` + `rack serve` behind a reverse proxy, supervised by the host |

### 5.2 Difference from Equinox

Equinox runs locally (`127.0.0.1`, data synced by kDrive). Rack Overflow runs on **one server** reachable from the iPhone: HTTPS reverse proxy, per-device authentication, the server's SQLite database as the source of truth.

### 5.3 Offline principle

- **Only in-session logging works offline.** Catalog, templates and history corrections are done online, directly on the server.
- Server → phone: a read-only **pack** (catalog, variables, templates, last performance and last settings per exercise, records), versioned by ETag.
- Phone → server: an **outbox** of idempotent operations (upsert by client-generated UUID v7), sent when the network is back.
- Result: no two-way sync, no conflict resolution.

## 6. V1 deliverables

Each deliverable can be demonstrated on its own. Order follows dependencies.

### L0 — Offline spike (validates the PWA choice)

**Goal**: prove that PWA logging on an iPhone is smooth and reliable in airplane mode, before investing in the rest.

**Content**
- Minimal session page installable on the home screen (manifest + service worker).
- Logging of dummy sets (reps × load, steppers, ✓).
- IndexedDB outbox, sent to a throwaway FastAPI endpoint, idempotent by UUID.
- Persistent storage request.

**Acceptance**
- The installed app opens in airplane mode and a full session can be logged.
- Once the network is back, everything reaches the server exactly once, even on resend.
- Smooth on the iPhone; no perceptible delay when confirming a set.
- Short report: go / no-go on the PWA, iOS friction points found.

**Output**: D-002 confirmed or revised. The spike code may be discarded.

### L1 — Technical foundation

**Content**
- Repository skeleton aligned with Equinox: `pyproject.toml`, uv, ruff, pylint, pre-commit, `CLAUDE.md`, `docs/`.
- Tests: isolation guard, markers, Playwright setup.
- GitHub Actions CI (lint, tests, browser).
- FastAPI app, configuration (`config.toml` + `.env`), logs.
- Database: SQLAlchemy Core, Alembic, first migration (section 7 tables), SQLite in WAL, `foreign_keys = ON`.
- Repository layer.
- Per-device auth: `rack device add <name>` issues a one-time pairing code; the server returns a long-lived token (`HttpOnly`, `Secure`, `SameSite=Strict` cookie), stored hashed, revocable.
- Native deployment on the NAS, no Docker: clone, `uv sync --frozen` (uv provides Python 3.12), `rack migrate`, `rack serve` bound to `127.0.0.1`, started at boot by a DSM Task Scheduler boot-up task, behind the DSM reverse proxy with a Let's Encrypt certificate.
- `rack update`: `git pull --ff-only`, `uv sync --frozen`, `rack migrate`, restart. Same rules as Equinox: the deployed clone stays on `main` with no local edits.

**Acceptance**
- After a NAS reboot, the app comes back on its own and answers over HTTPS through the DynDNS.
- An unpaired device is refused; a revoked device loses access.
- `uv run pytest` and CI pass.

### L2 — Catalog: exercises and variables

**Content**
- **Variable** catalog: code, label, type (`int`, `decimal`, `duration`, `distance`, `weight`, `enum`, `bool`, `text`), display unit, scope (`set` = measure, `setting` = equipment setting), enum values. **The seed contains no variable**: every variable is created in the UI.
- **Shared variables**: a variable is defined once and can be linked to one or more exercises (e.g. one "Siège" setting used by leg press, chest press and shoulder press). Editing the variable's definition applies to every linked exercise; per-exercise parameters live on the link.
- **Core quantities** (reps, load, duration, distance) are built-in fields, not variables: each exercise just enables the ones it uses.
- **Exercises**: name, category (`strength`, `kettlebell`, `bodyweight`, `cardio`, `intervals`), movement pattern, equipment, location (gym / home / both), archiving.
- **Exercise ↔ variable links** (many-to-many): which core quantities and variables the exercise uses, required or not, increment (+2.5 kg, +1 rep, +30 s), default, discrete values (e.g. kettlebells 16 / 20 / 24 kg), display order.
- **Aliases**: alternative names and abbreviations, normalized for search.
- Fuzzy search on names and aliases.
- Starter exercise seed covering current sessions.

**Acceptance**
- Create a "Siège" setting variable (enum 1–10) in the UI and link it to "Leg press" and "Chest press", with no schema migration.
- Each linked exercise remembers its own last seat value.
- Create "Kettlebell swing" with discrete loads 16 / 20 / 24 kg.
- Create "Bike" with duration and distance (core) plus a "Résistance" measure variable created in the UI.
- An unused variable can be archived; a variable linked to exercises with history cannot be deleted.
- Archiving an exercise with history deletes no data.
- Find "Développé couché" by typing "DC" or "bench".

### L3 — Session templates (menus)

**Content**
- A template is an ordered list of **slots**.
- A slot is either a specific exercise or a **menu** (movement pattern + proposed exercises, chosen during the session).
- Optional indicative target per slot (sets × reps, duration…).
- Seed examples: "Salle 1", "Salle 2", "Maison", "Cardio bonus".

**Acceptance**
- Create "Salle 1" with a "Pull" slot offering three exercises.
- The template appears in the offline pack.

### L4 — In-session logging (offline)

**Content**
- Start a session: empty or from a template, choose location.
- Menu slot: pick the exercise from the proposed list.
- Add an exercise outside the template: fuzzy search, recent first.
- **Prefill** sets from the exercise's last performance (else the target), and **settings** from the last session.
- Adjust with steppers (exercise increment) or discrete values.
- ✓ confirms the set: immediate local write, outbox entry, ⭐ on a new record (computed from the pack).
- Set type: warm-up / work / RM test.
- Optional variables (e.g. an RPE variable if the user creates one) are shown collapsed so they never slow down the nominal path.
- Layout adapted to category (reps × load; duration / distance / intensity; rounds).
- Resume the open session after the app is closed.
- Close: summary (exercises, volume, records).
- Discreet status: "all sent" / "n operations pending".
- Server: `GET /api/pack` (ETag), `POST /api/outbox` (batch of idempotent operations).

**Acceptance**
- Full session logged in airplane mode, then sent correctly when the network is back.
- A batch sent twice creates no duplicate; a partial batch resumes cleanly.
- Section 4 speed targets are met.
- Playwright tests of the session screen with network off.

### L5 — Minimal tracking

**Content**
- Session history (list, detail, online correction of a set or setting).
- Per exercise: last performance, records, chart of the main indicator over time.
- Indicators by category:

| Category | Main indicator | Secondary |
|---|---|---|
| `strength` | e1RM | max load per rep count, volume |
| `kettlebell` | reps at a given load | density (reps / duration), volume |
| `bodyweight` | reps | max duration, added load if weighted |
| `cardio` | distance or duration | pace / speed |
| `intervals` | rounds | work / rest ratio |

- **RM** (`strength` exercises): entry of a measured RM (1RM…nRM); estimation from work sets; origin shown (**measured** / **estimated**, with formula). Formulas: Epley (default), Brzycki, Lombardi, O'Conner, Wathan, global choice in settings. Warm-up sets excluded; sets above 12 reps excluded from estimation.
- Consistency: sessions per week.

**Acceptance**
- Changing the formula recomputes estimates without touching measured RMs.
- A measured RM wins over an estimate on display; an estimate above an older test is flagged.
- Charts render in < 1 s with one year of simulated history.

### L6 — Operations

**Content**
- Automatic daily backup (`VACUUM INTO` a dated file, 30-day retention).
- Full JSON and CSV export (UI and `rack export`).
- `rack backup`, `rack restore` (documented and tested).
- Install and update docs: Synology NAS and Jelastic.
- NAS ↔ Jelastic migration documented (backup, restore, URL change).

**Acceptance**
- Restoring a backup on a blank instance yields identical data.
- Jelastic: database on the node's local disk, never on a shared network volume.

## 7. Storage model

### 7.1 Principles

- **Measures and settings are distinct.** A *measure* changes on every set (reps, load, HR…). A *setting* is fixed for the exercise within the session (seat height, grip, incline) and is prefilled from last time.
- **Hybrid: fixed columns + catalogued variables.** The four quantities that drive computations are `set_entry` columns (`reps`, `weight_g`, `duration_s`, `distance_m`). All other variables live in value tables linked to the `variable` catalog. Adding a variable needs no migration.
- **Canonical integer units**: grams, seconds, metres. Display in kg and km. Conversion only on display.
- **Variables are shared**: `variable` is a catalog independent of exercises; `exercise_variable` is the many-to-many link and carries per-exercise parameters (required, increment, default, discrete values, order). Values always reference the variable, so a shared variable can be compared across exercises.
- **Store facts, compute the rest.** Sessions, sets, settings and measured RMs are stored. Last performance, e1RM, records and volume are computed on the fly. A materialized table comes only if performance requires it.
- **No physical deletion of history**: exercises and variables are archived; removing a variable from an exercise keeps past values.
- **IDs**: client-generated UUID v7 (`TEXT` in SQLite, `uuid` in Postgres).
- **Timestamps**: UTC ISO 8601; sessions also keep local date and time zone.
- **`user_id`** on root tables (`variable`, `exercise`, `template`, `session`, `rm_measured`, `device`, `setting`).

### 7.2 Schema

```
variable ──< exercise_variable >── exercise ──< exercise_alias
                                      │
template ──< template_slot ───────────┤   (slot → exercise or menu)
                                      │
session ──< session_exercise ─────────┘
                │        └──< exercise_setting   (settings)
                └──< set_entry ──< set_value      (free measures)

rm_measured · device · setting
```

| Table | Main fields |
|---|---|
| `variable` | code, label, type, display unit, scope (`set` / `setting`), enum values, archived — shared, linked to exercises through `exercise_variable` |
| `exercise` | name, category, movement pattern, equipment, location, archived |
| `exercise_variable` | exercise_id, variable_id, required, increment, default, discrete values, order |
| `exercise_alias` | exercise_id, normalized alias |
| `template` | name, location, order, archived |
| `template_slot` | template_id, order, exercise_id **or** movement pattern + proposed exercises, indicative target |
| `session` | local date, time zone, start, end, location, template_id, notes, status (`open` / `closed`), source |
| `session_exercise` | session_id, exercise_id, template_slot_id, order, notes |
| `exercise_setting` | session_exercise_id, variable_id, `value_int` / `value_text` |
| `set_entry` | session_exercise_id, order, type (`warmup` / `work` / `rm_test`), `reps`, `weight_g`, `duration_s`, `distance_m`, `completed_at`, `deleted_at` |
| `set_value` | set_entry_id, variable_id, `value_int` / `value_text` |
| `rm_measured` | exercise_id, n, `weight_g`, date, optional source set_entry_id |
| `device` | name, token hash, last seen, revoked |
| `setting` | key, value (RM formula, units, RPE shown…) |

### 7.3 Phone side (IndexedDB)

| Store | Content |
|---|---|
| `pack` | Catalog, variables, templates, last performance and last settings per exercise, records; versioned |
| `current_session` | Open session, for resume after close |
| `outbox` | Pending operations (`upsert_session`, `upsert_session_exercise`, `upsert_set`, `upsert_setting`, `delete_set`, `close_session`), each carrying the row UUID |

### 7.4 SQLite operations

WAL, `foreign_keys = ON`, `synchronous = FULL` in production; backup via `VACUUM INTO`; local storage only (never NFS).

## 8. API (sketch)

| Method | Route | Deliverable |
|---|---|---|
| `POST` | `/api/devices/pair` | L1 |
| `GET/POST/PATCH` | `/api/variables` | L2 |
| `GET/POST/PATCH` | `/api/exercises`, `/api/exercises/{id}/variables`, `/api/exercises/{id}/aliases` | L2 |
| `GET/POST/PATCH` | `/api/templates` | L3 |
| `GET` | `/api/pack` | L4 |
| `POST` | `/api/outbox` | L4 |
| `GET/PATCH/DELETE` | `/api/sessions`, `/api/sessions/{id}` | L5 |
| `GET` | `/api/progress/{exercise_id}` | L5 |
| `GET/POST` | `/api/rm/{exercise_id}` | L5 |
| `GET` | `/api/export` | L6 |

## 9. V2 preparation: AI features (not in V1)

Recorded so V1 closes no door:

- Server module `rack_overflow/ai/` exposing **domain tasks** (`analyse_session`, `propose_next_session`, `motivation`, `weekly_review`), never an SDK directly.
- One **Pydantic AI** agent per task, structured output (Pydantic model), read-only tools over the data.
- **Configurable provider** (`[ai] provider = "claude" | "bridge" | "none"`): Claude, or the user's in-progress FastAPI AI engine used as a bridge. Assumption: the engine exposes an **OpenAI-compatible API**, so it plugs in with no provider-specific code.
- AI is always **asynchronous and optional**: never in the logging path or offline mode. Results stored (`ai_insight`); the latest advice may be included in the pack.

**V1 impact: none**, beyond clean data and tracking computations exposed through a reusable service layer.

## 10. Proposed decisions (to be challenged)

| # | Decision | Rationale |
|---|---|---|
| D-001 | Same stack as Equinox | Existing know-how, reused tooling and conventions |
| D-002 | Web + PWA, no native app | No Apple fee, one codebase, instant updates; confirmed or refuted by L0 |
| D-003 | Offline limited to the session screen | Only context without network; removes two-way sync |
| D-004 | Read-only pack + idempotent outbox keyed by UUID v7 | No possible conflict, safe resends |
| D-005 | SQLite (WAL) via SQLAlchemy Core + Alembic, Postgres-compatible SQL | Enough for single user; move to Postgres without rewrite |
| D-006 | `user_id` on root tables from V1 | Multi-user possible without schema migration |
| D-007 | Hybrid storage: 4 fixed columns + catalogued variables | Simple computations on the core, extensible without migration |
| D-008 | Measures (per set) and settings (per session exercise) are distinct | Matches practice; machine settings prefilled |
| D-009 | Canonical integer units (g, s, m) | No rounding errors; conversion on display only |
| D-010 | Facts stored, indicators computed on the fly | No cache to invalidate; low volume |
| D-011 | RM: measured / estimated origin tracked, selectable formula, recomputable estimates | Transparent measurement, formula change without loss |
| D-012 | Templates as menus by movement pattern | Flexible, non-fixed training practice |
| D-013 | Hosting on Synology NAS or Jelastic, native Python deployment (no Docker): uv, reverse proxy, host supervision | Same tooling as Equinox, no container layer; reversible choice; SQLite on local storage only |
| D-014 | AI deferred to V2, through a Pydantic AI module with configurable provider | V1 focuses on the core; provider independence |
| D-015 | Name: Rack Overflow; repo and package `rack_overflow`, CLI `rack` | Naming aligned with Equinox |
| D-016 | UI in French; dev documents, code and comments in English | User-facing language vs token economy and standardization |
| D-017 | No rest timer in V1 | Not essential; added later if needed |
| D-018 | Display units kg and km only in V1 | Matches use; storage stays canonical (g, s, m) |
| D-019 | No variable in the seed; variables are created in the UI and shared across exercises (many-to-many) | The user defines their own measures and settings; one definition reused by several exercises |

Note: the template already uses D-001 to D-011 for tooling and workflow; these proposals will be renumbered from D-012 when recorded in `docs/decisions.md`.

## 11. Points for Claude Code to challenge

1. **Consistency with the Equinox repository**: SQLAlchemy Core + Alembic, or direct SQLite access as in Equinox? Pick what fits existing conventions without losing Postgres compatibility.
2. **Hybrid storage vs alternatives** (pure wide table, full EAV, JSON column): validate the trade-off against L5 queries.
3. **iOS standalone PWA**: the installed app has its own cookie jar, separate from Safari, so pairing must happen inside the installed app. Also check IndexedDB persistence and eviction policy.
4. **Auth**: `HttpOnly` cookie vs token in IndexedDB for outbox sends (service worker and `fetch` must be able to use it).
5. **Deliverable order**: can L2 / L3 run in parallel with L4 once L1 is done?
6. **Release split** and release briefs according to the repository's dev protocol.
7. **Seeds**: starter exercises and templates (supplied by the user or proposed), with core quantities only and no variable (D-019).
8. **Process supervision without Docker**: DSM boot-up task vs a user-level service on the NAS; Jelastic node type (Python application node vs plain Linux node with systemd). Restart on crash, log rotation, port binding.
9. **i18n**: French-only UI strings — centralize them from the start (single catalog) even without multi-language support.

## 12. Resolved questions

| Question | Answer | Decision |
|---|---|---|
| Rest timer in V1? | No, later if needed | D-017 |
| Units? | kg and km | D-018 |
| Variables in the seed? | None; created in the UI, shareable across exercises | D-019 |

---

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
