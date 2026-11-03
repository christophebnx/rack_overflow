# Architecture

How the system is built. Why it is built that way: `docs/decisions.md`. Design notes of each change: `docs/architecture/`.

## Overview

Rack Overflow is one FastAPI server and one SQLite database on the same host (Synology NAS, later possibly Jelastic), used from Safari on the iPhone and from a desktop browser (D-015, D-024). Full content and order of the build: `docs/release-1.0.0-brief.md` and `docs/roadmap.md`.

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

ops/        rack supervise (restarts rack serve, rotating logs), rack update (host side, beside the stack)
```

Main flows:
- **Every request**: security checks (`Host`, `Origin`, JSON-only, body size) → device cookie (`web/auth`; unpaired: navigation `303` to `/appairage`, otherwise `401 not_paired`). Only `/appairage` and `/static/` are public (D-049).
- **Page**: GET → route → service reads → Jinja2 page with strings from `locales/fr.json`.
- **Action** (e.g. confirm a set): htmx POST/PATCH with a JSON body → Pydantic validation → service (one transaction, domain rules) → HTML fragment swapped in place; a refused user input re-renders the form with `200` (D-050).
- **Pairing**: `rack device add NAME` prints a one-time code → the browser posts it to `/appairage` → hashed token stored, `rack_device` cookie set (D-040, D-049).
- **Operations**: `rack migrate` (upgrade, then the pending catalog seed steps, D-057), `rack backup`, `rack device …`, `rack serve` (CLI calls the same services and storage); `rack supervise` runs `rack serve` as a child; `rack update` pulls `main`, syncs, migrates in a new process, then sends SIGHUP to the supervisor, which re-executes itself (D-051, D-052). Install guide: `docs/deployment/nas.md`.

## Layers

| Package | Role | May import (project packages) |
|---|---|---|
| `domain/` | Pure business logic: models, rules, validation. No I/O, no clock, no environment (D-003). | nothing |
| `storage/` | File system and persistence; the single atomic writer. | `domain` |
| `services/` | Business operations, one use case each, shared by the CLI and the web layer. | `domain`, `storage` |
| `web/` | FastAPI app factory, routes, Jinja2 templates, CSS, vendored htmx, string catalog, security middleware, daily backup task. | `domain`, `services`, `config` |
| `ops/` | Host process management: `rack supervise` (restart, rotating logs, single instance) and `rack update`. POSIX only. | `domain`, `storage` |
| `config.py` | Load and validate the settings file and the secrets file beside it, once (D-044). | `domain` |
| `cli.py` | Command-line entry point: parses arguments, calls the layers, maps errors to exit codes (D-004). | everything |

Add a row when adding a package, and the matching entry in `ALLOWED` of `tests/unit/test_layering.py` (`MODULE_ALLOWED` for a top-level module). Each package has a `CLAUDE.md` with its rules and module table.

## Responsibility map

One responsibility, one implementation (CLAUDE.md invariant 2). Check here before writing code; update this table when adding a cross-cutting responsibility.

| Responsibility | Implementation |
|---|---|
| Base class of business errors | `domain/errors.DomainError` |
| Write a file atomically (temp + fsync + rename) | `storage/files.atomic_write` (bytes), `storage/files.atomic_produce` (from a writer) |
| Map an error to a CLI exit code and message | `cli.main` |
| Load settings and secrets | `config.load_settings` |
| Allowed values of enumerated columns | `domain/vocabulary` |
| Open the database with the project pragmas | `storage/db.create_engine` |
| Database schema | `storage/schema.metadata` |
| Apply / inspect migrations | `storage/migrate` |
| Restart delay policy of the supervisor | `domain/supervision` |
| Supervise `rack serve` (restart, logs, single instance) | `ops/supervise` |
| Self-update of a deployed clone (pull, sync, migrate, restart) | `ops/update` |
| Log line format (UTC) of the server and the supervisor | `ops/logs.utc_formatter` |
| `rack <command> --config <path>` run by a given Python in a new process | `ops/commands.self_command` |
| Database timestamp text (UTC `YYYY-MM-DDTHH:MM:SSZ`) | `domain/timestamps` |
| The V1 user id | `domain/users.SINGLE_USER_ID` |
| Device, pairing code and token rules | `domain/devices` |
| Text normalisation (search, aliases, name uniqueness, codes) | `domain/text` |
| Canonical integers ↔ display and input text (kg, km / m, m:ss) | `domain/units` |
| Catalog rules (variables, exercises, fields, aliases) | `domain/catalog` |
| Movement pattern and equipment of an exercise in their first-seen spelling | `domain/catalog.with_known_spellings` |
| Fuzzy ranking of exercises | `domain/search` |
| Variable queries | `storage/variables` |
| Exercise, field and alias queries | `storage/exercises` |
| Per-user settings (`app_setting`) | `storage/app_settings` |
| Unique-constraint guard of a write (savepoint) | `storage/db.guarded_write` |
| Unknown or foreign row | `domain/errors.NotFoundError` |
| Variable operations | `services/variables` |
| Exercise, field, alias and search operations | `services/exercises` |
| Seed data (packaged JSON) | `storage/seed` |
| Seeding the catalog (versioned steps) | `services/seed` (run by `cli.run_migrate`) |
| Device and pairing-code queries | `storage/devices` |
| Device operations (add, list, revoke, pair, authenticate) | `services/devices` |
| Open the database only when it is at the head revision (CLI) | `cli._open_current_database` |
| Snapshot naming, ordering, due-ness, retention | `domain/backups` |
| Take, list and prune database snapshots | `storage/backup` |
| Backup operation (snapshot then prune, or only when due) | `services/backups` |
| Daily backup in the server | `web/scheduler` |
| Build the web app | `web/app.create_app` |
| HTTP request checks and security headers | `web/security.SecurityMiddleware` |
| Request authentication by device and the device cookie | `web/auth` |
| User id of the paired device in a route | `web/auth.device_user` |
| User-facing strings | `web/locale.Catalog` (`web/locales/fr.json`) |
| Render a page or fragment | `web/rendering.render` |
| Values in display units in pages (number + unit text) | `web/display.Display` (`show` in templates) |
| Word of a core quantity (quantity → string key) | `web/display.QUANTITY_KEYS` (`show.quantity` in templates) |
| Refused catalog input → messages per input | `web/forms.form_errors` |
| Show a failed htmx request (« Non enregistré, réessayer », focus back) | `web/static/js/request-errors.js` + `web/templates/_form_status.html` |
| HTTP error → error page or JSON code | `web/errors` |
| Check a commit message | `tools/check_commit_message.problems` |
| Block secrets, protected folders, commits and pushes on `main` (Claude Code) | `.claude/hooks/guard_paths.py` |
| Format and lint-fix an edited file (Claude Code) | `.claude/hooks/format.py` |
| Isolate tests from the real home, secret files and the network (D-043) | `tests/isolation.py` (wired in `tests/conftest.py`) |

## Configuration

Settings live in a TOML settings file (D-044), given to every command by `--config PATH` (default `config.toml` in the current folder, git-ignored): `[server]` host, port, public host name, `https = false` in V1 (D-013); `[storage] data_dir` (relative to the settings file's folder); `[backup] retention_days`. The committed `config.example.toml` documents every key and is the development configuration (`uv run rack <command> --config config.example.toml`, data in `.local/dev-data/`). Secrets go in the `.env` file beside the settings file (git-ignored, template in `.env.example`); V1 needs none. `config.load_settings` reads both once, in `cli.py`, and the frozen `Settings` are passed down explicitly; no other layer reads the environment or these files. A missing or invalid file is an error, never a silent default.
