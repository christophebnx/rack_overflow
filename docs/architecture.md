# Architecture

How the system is built. Why it is built that way: `docs/decisions.md`. Design notes of each change: `docs/architecture/`.

## Overview

Rack Overflow is one FastAPI server and one SQLite database on the same host (Synology NAS, or an Infomaniak Jelastic Linux node, D-076), used from Safari on the iPhone and from a desktop browser (D-015, D-024). Full content and order of the build: `docs/release-1.0.0-brief.md` and `docs/roadmap.md`.

```
browser (iPhone / desktop)
   │  HTML pages; htmx requests sent as JSON, answered with HTML fragments
   ▼
web/        FastAPI routes, Jinja2 templates, security middleware, device auth
   ▼
services/   business operations, one transaction each (reused later by a JSON API / AI)
   ▼
domain/     pure rules: units, records, e1RM, prefill, validation
storage/    SQLAlchemy Core queries, Alembic migrations, backups, atomic file writes
   ▼
SQLite (WAL) in the data folder  ──  daily VACUUM INTO backups

ops/        rack supervise (restarts rack serve, rotating logs), rack update, the server-stopped guard of rack restore (host side, beside the stack)
```

Main flows:
- **Every request**: security checks (`Host`, `Origin`, JSON-only, body size) → device cookie (`web/auth`; unpaired: navigation `303` to `/appairage`, otherwise `401 not_paired`). Only `/appairage` and `/static/` are public (D-049).
- **Page**: GET → route → service reads → Jinja2 page with strings from `locales/fr.json`.
- **Action** (e.g. confirm a set): htmx POST/PATCH with a JSON body → Pydantic validation → service (one transaction, domain rules) → HTML fragment swapped in place; a refused user input re-renders the form with `200` (D-050).
- **Session logging**: home (`GET /`) resumes the open session or starts one (`POST /seances` → `HX-Redirect`) → session page (`GET /seances/{id}`, whole state read from the database) → « − » / « + » are GETs re-rendering the set form (no write) → ✓ (`POST /seances/{id}/series`) writes the set and missing settings in one transaction, then returns the block with ⭐ and the next prefill, both recomputed from stored facts → close (`POST …/cloture`) → summary. Rules: `domain/sessions`, `domain/indicators`; design note `docs/architecture/2026-11-03-l4-session-logging.md` (D-061 to D-066).
- **History**: `GET /historique` (sessions per week, then month groups of 20 sessions by keyset, « Plus anciennes » appends the next page) → a closed `GET /seances/{id}` is the detail: sets and settings corrected through the L4 paths with `require_open=False`, answer the exercise section and the totals out of band; `DELETE /seances/{id}` sets `session.deleted_at` only, every reader filters it out (D-067, D-070).
- **Progress**: `GET /progression` (exercises with history) → `GET /progression/{id}` (last performance, RM table for strength, chart caption and data table, records) → `progress-chart.js` fetches `GET /api/progression/{id}` (display numbers and French labels from the server) and draws it with vendored Chart.js; `POST /rm/{id}` and `DELETE /rm/mesures/{id}` re-render the RM section; `PATCH /reglages` stores the 1RM formula (`app_setting` `rm.formula`). Every indicator is recomputed from stored facts on each request (D-068, D-069). Design note `docs/architecture/2026-11-03-l5-tracking.md`.
- **Pairing**: `rack device add NAME` prints a one-time code → the browser posts it to `/appairage` → hashed token stored, `rack_device` cookie set (D-040, D-049).
- **Operations**: `rack migrate` (upgrade, then the pending seed steps: exercises, then templates; D-057, D-060), `rack backup`, `rack export` (JSON or CSV to a new file, one read transaction; the same bytes as the « Réglages » download `GET /api/export`, D-074), `rack restore` (server stopped: supervisor lock and port probe; the current database kept aside, an older snapshot migrated, D-075), `rack device …`, `rack serve` (CLI calls the same services and storage); `rack supervise` runs `rack serve` as a child; `rack update` pulls `main`, syncs, migrates in a new process, then sends SIGHUP to the supervisor, which re-executes itself (D-051, D-052); on Jelastic, systemd runs `rack serve` instead of `rack supervise` (D-076). Install guides: `docs/deployment/nas.md`, `docs/deployment/jelastic.md`; moving between them: `docs/deployment/migration.md`.

## Layers

| Package | Role | May import (project packages) |
|---|---|---|
| `domain/` | Pure business logic: models, rules, validation. No I/O, no clock, no environment (D-003). | nothing |
| `storage/` | File system and persistence; the single atomic writer. | `domain` |
| `services/` | Business operations, one use case each, shared by the CLI and the web layer. | `domain`, `storage` |
| `web/` | FastAPI app factory, routes, Jinja2 templates, CSS, vendored htmx and Chart.js (`static/vendor/manifest.json`), string catalog, security middleware, daily backup task. | `domain`, `services`, `config` |
| `ops/` | Host process management: `rack supervise` (restart, rotating logs, single instance), `rack update` and the server-stopped guard of `rack restore`. POSIX only. | `domain`, `storage` |
| `config.py` | Load and validate the settings file and the secrets file beside it, once (D-044). | `domain` |
| `cli.py` | Command-line entry point: parses arguments, calls the layers, maps errors to exit codes (D-004). | everything |

Add a row when adding a package, and the matching entry in `ALLOWED` of `tests/unit/test_layering.py` (`MODULE_ALLOWED` for a top-level module). Each package has a `CLAUDE.md` with its rules and module table.

## Responsibility map

One responsibility, one implementation (CLAUDE.md invariant 2). Check here before writing code; update this table when adding a cross-cutting responsibility.

| Responsibility | Implementation |
|---|---|
| Base class of business errors | `domain/errors.DomainError` |
| Write a file atomically (temp + fsync + rename; `overwrite=False`: never replace an existing name) | `storage/files.atomic_write` (bytes), `storage/files.atomic_produce` (from a writer) |
| Map an error to a CLI exit code and message | `cli.main` |
| Load settings and secrets | `config.load_settings` |
| Time zone of session local dates and times | `config.Settings.calendar` (`[calendar] time_zone`, D-065) |
| Allowed values of enumerated columns | `domain/vocabulary` |
| Open the database with the project pragmas | `storage/db.create_engine` |
| A transaction that only reads (deferred: never blocks a writer) | `storage/db.read_transaction` |
| Database schema | `storage/schema.metadata` |
| Apply / inspect migrations | `storage/migrate` |
| Revision of the database inside the caller's transaction | `storage/migrate.revision_in` |
| Restart delay policy of the supervisor | `domain/supervision` |
| Supervise `rack serve` (restart, logs, single instance) | `ops/supervise` |
| Self-update of a deployed clone (pull, sync, migrate, restart) | `ops/update` |
| Log line format (UTC) of the server and the supervisor | `ops/logs.utc_formatter` |
| `rack <command> --config <path>` run by a given Python in a new process | `ops/commands.self_command` |
| Database timestamp text (UTC `YYYY-MM-DDTHH:MM:SSZ`) | `domain/timestamps` |
| The V1 user id | `domain/users.SINGLE_USER_ID` |
| Device, pairing code and token rules | `domain/devices` |
| Text normalisation (search, aliases, name uniqueness, codes) | `domain/text` |
| Text read as a non-negative integer (ASCII digits only, before `int()`) | `domain/text.is_digits` |
| Canonical integers ↔ display and input text (kg, km / m, m:ss; compact target durations; pace, speed, density, chart numbers `chart_number`, duration tick steps `chart_duration_step`, data-table numbers `column_number`, L5) | `domain/units` |
| Catalog rules (variables, exercises, fields, aliases) | `domain/catalog` |
| Movement pattern and equipment of an exercise in their first-seen spelling | `domain/catalog.with_known_spellings` |
| At least one measure per exercise (field removal, variable delete or scope change) | `domain/catalog.check_measures`, `check_linked_measures` |
| Name uniqueness after normalisation (exercises, templates; error code as a parameter) | `domain/catalog.check_name` |
| Template, menu, target and slot / option limit rules | `domain/templates` |
| Fuzzy ranking of exercises | `domain/search` |
| Session logging rules: start plan, plan order and current item, set prefill, steppers, set and settings validation | `domain/sessions` |
| Records (⭐) and volume, computed from set facts (the only place; counted set types `RECORD_TYPES`, read by storage) | `domain/indicators` |
| e1RM, RM table and formula, records by category, chart series, pace / speed / density, sessions per week (computed from facts, D-068 to D-070) | `domain/indicators` |
| RM entry and formula form rules, month grouping of the history | `domain/progress` |
| Reorder a list by « Monter » / « Descendre » (fields, templates, slots, options) | `domain/ordering.moved` + `storage/positions.set_positions` |
| Position of a row appended at the end of an ordered list (fields, templates, slots, options) | `storage/positions.next_position` |
| Variable queries | `storage/variables` |
| Exercise, field and alias queries | `storage/exercises` |
| Per-user settings (`app_setting`) | `storage/app_settings` |
| An id from a request within the database integer range (path, body), else 404 | `web/forms.RowId`, `row_id`, `select_id` (text from a select or button) |
| Unique-constraint guard of a write (savepoint) | `storage/db.guarded_write` |
| Unknown or foreign row | `domain/errors.NotFoundError` |
| Template, slot and menu-option queries | `storage/templates` |
| Template operations (templates, slots, menus, targets) | `services/templates` |
| Session, row, set and setting queries; last performance, last settings, record history, recent exercises; history pages, session dates, exercises with history, session soft delete (L5) | `storage/sessions` |
| Measured RM queries (`rm_measured`) | `storage/rm` |
| Session logging operations (start, plan, pick, sets, settings, close, summary); closed-session corrections and session delete (L5) | `services/sessions` |
| Number of exercises with a live set in a closed session (« Exercices » total) | `services/sessions.SummaryView.exercise_count` |
| History operations (pages by month, sessions per week) | `services/history` |
| Progress operations (progress page, chart data, RM entries, 1RM formula setting) | `services/progress` |
| One year of simulated history for performance tests | `tests/support/history.py` |
| Live slots of a template (template pages and sessions) | `services/templates.slots_for_session` |
| Fields of an exercise with kind and parameters (exercise page and session forms) | `services/exercises.field_views` |
| Exercises grouped by movement pattern for selects | `services/templates.exercise_groups` |
| Variable operations | `services/variables` |
| Exercise, field, alias and search operations | `services/exercises` |
| Seed data (packaged JSON: exercises with keys, templates) | `storage/seed` |
| Seeding the catalog: exercises, seed keys and adoption, templates (versioned steps) | `services/seed` (run by `cli.run_migrate`) |
| Device and pairing-code queries | `storage/devices` |
| Device operations (add, list, revoke, pair, authenticate) | `services/devices` |
| Open the database only when it is at the head revision (CLI) | `cli._open_current_database` |
| Snapshot naming, ordering, due-ness, retention | `domain/backups` |
| Take, list and prune database snapshots | `storage/backup` |
| Copy a database into a new single file by `VACUUM INTO` (snapshot, restore staging) | `storage/backup._vacuum_copy` |
| Integrity of a rollback-journal copy, read-only (snapshot, staged restore) | `storage/backup.check_copy` |
| Revision of a database file without opening it read-write; order of a revision against the shipped ones | `storage/migrate.revision_of_file`, `revision_order`, `known_revisions` |
| Restore a snapshot as the database (stage a single-file copy of the snapshot set, check, keep the current aside, swap) | `storage/backup.restore_snapshot` (through `services/backups.restore`) |
| Name of a database kept aside by a restore; SQLite side-file suffixes | `domain/backups.aside_name`, `SIDE_SUFFIXES`, `SNAPSHOT_SIDE_SUFFIXES` (the ones a restore copies with a snapshot) |
| Refuse while a server runs on the data folder (supervisor lock, port probe) | `ops/restore.server_stopped` |
| Upgrade then seed (the `rack migrate` step, reused for a restored older snapshot) | `cli._upgrade_and_seed` |
| Stop a test migration at an older revision | `tests/support/migrations.upgrade_to` |
| Backup operation (snapshot then prune, or only when due) | `services/backups` |
| Export format (JSON document, CSV zip, file names, format version; D-072, D-073) | `domain/export` |
| What an export holds (tables, columns, secret columns excluded) and the database dump | `storage/export` (`exported_columns`, `dump`, `SECRET_COLUMNS`) |
| Export operation (one consistent read, JSON or CSV bytes, file name, media type) | `services/export.export` |
| Export to a new file from the CLI (never overwrites) | `cli.run_export` |
| Export download from the settings page | `web/routes/progress.export_data` (`GET /api/export`) |
| A database with a row in every table; test readers of an export (JSON loader, CSV parser) | `tests/support/populated.py`, `tests/support/export_loader.py` |
| Daily backup in the server | `web/scheduler` |
| Build the web app | `web/app.create_app` |
| HTTP request checks and security headers | `web/security.SecurityMiddleware` |
| Request authentication by device and the device cookie | `web/auth` |
| User id of the paired device in a route | `web/auth.device_user` |
| User-facing strings | `web/locale.Catalog` (`web/locales/fr.json`) |
| Render a page or fragment | `web/rendering.render` |
| Values in display units in pages (number + unit text) | `web/display.Display` (`show` in templates) |
| Text of an indicative target (« 4 × 6–8 ») | `web/display.Display.target` |
| Text of a set, local time / date of a session, volume meta (L4) | `web/display.Display.set_text`, `local_time`, `local_date`, `volume` |
| Short date, weekday, month name, one-decimal number (L5) | `web/display.Display.short_date`, `weekday`, `month`, `decimal1` |
| Set rows and their edit forms (open block, closed detail, last performance) | `web/templates/_set_list.html` |
| « Oui » / « Non » of a `bool` value; chip values of a discrete, `bool` or `enum` field | `web/display.Display.yes_no` (`BOOL_KEYS`), `Display.choices` |
| Focus after a « Monter » / « Descendre » move, and its JSON body | `web/forms.move_focus`, `web/forms.MoveBody` |
| Word of a core quantity (quantity → string key) | `web/display.QUANTITY_KEYS` (`show.quantity` in templates) |
| Refused catalog input → messages per input | `web/forms.form_errors` |
| Show a failed htmx request (« Non enregistré, réessayer », focus back) | `web/static/js/request-errors.js` + `web/templates/_form_status.html` |
| Draw a progress chart from its JSON (no text, no rule, no conversion) | `web/static/js/progress-chart.js` (Chart.js vendored) |
| Chart JSON shape (labels, display numbers, French labels) | `web/routes/progress.chart_json` |
| Computed values, table cells, formula names, series labels, RM origin text (L5) | `web/display.Display.rate`, `cell`, `formula`, `series_label`, `rm_origin` |
| Today's local date in a route | `web/routes/history.local_today` (through `domain/sessions.local_start`) |
| HTTP error → error page or JSON code; « Réessayer » link of a 5xx page (path and query kept) | `web/errors` (`_retry_path`) |
| Check a commit message | `tools/check_commit_message.problems` |
| Block secrets, protected folders, commits and pushes on `main` (Claude Code) | `.claude/hooks/guard_paths.py` |
| Format and lint-fix an edited file (Claude Code) | `.claude/hooks/format.py` |
| Isolate tests from the real home, secret files and the network (D-043) | `tests/isolation.py` (wired in `tests/conftest.py`) |

## Configuration

Settings live in a TOML settings file (D-044), given to every command by `--config PATH` (default `config.toml` in the current folder, git-ignored): `[server]` host, port, public host name, `https = false` in V1 (D-013); `[storage] data_dir` (relative to the settings file's folder); `[backup] retention_days`; `[calendar] time_zone` (IANA name, default `Europe/Brussels`, checked at load through `zoneinfo`, which the `tzdata` dependency guarantees on uv's Python and on DSM; `Settings.calendar.tz` is passed to the session services, D-065). The committed `config.example.toml` documents every key and is the development configuration (`uv run rack <command> --config config.example.toml`, data in `.local/dev-data/`). Secrets go in the `.env` file beside the settings file (git-ignored, template in `.env.example`); V1 needs none. `config.load_settings` reads both once, in `cli.py`, and the frozen `Settings` are passed down explicitly; no other layer reads the environment or these files. A missing or invalid file is an error, never a silent default.
