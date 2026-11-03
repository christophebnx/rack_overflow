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
```

Main flows:
- **Page**: GET → route → service reads → Jinja2 page with strings from `locales/fr.json`.
- **Action** (e.g. confirm a set): htmx POST/PATCH with a JSON body → security checks (`Origin`, `Host`, JSON-only, device cookie) → Pydantic validation → service (one transaction, domain rules) → HTML fragment swapped in place.
- **Operations**: `rack migrate`, `rack backup`, `rack device …`, `rack serve`, `rack supervise` (CLI calls the same services and storage).

The packages `web/` and `services/` and the database part of `storage/` are created in L1a; the table below gains their rows then.

## Layers

| Package | Role | May import (project packages) |
|---|---|---|
| `domain/` | Pure business logic: models, rules, validation. No I/O, no clock, no environment (D-003). | nothing |
| `storage/` | File system and persistence; the single atomic writer. | `domain` |
| `services/` | Business operations, one use case each, shared by the CLI and the web layer. | `domain`, `storage` |
| `web/` | FastAPI app factory, routes, Jinja2 templates, CSS, vendored htmx, string catalog, security middleware, daily backup task. | `domain`, `services`, `config` |
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
| Snapshot naming, ordering, due-ness, retention | `domain/backups` |
| Take, list and prune database snapshots | `storage/backup` |
| Backup operation (snapshot then prune, or only when due) | `services/backups` |
| Daily backup in the server | `web/scheduler` |
| Build the web app | `web/app.create_app` |
| HTTP request checks and security headers | `web/security.SecurityMiddleware` |
| User-facing strings | `web/locale.Catalog` (`web/locales/fr.json`) |
| Render a page or fragment | `web/rendering.render` |
| HTTP error → error page or JSON code | `web/errors` |
| Check a commit message | `tools/check_commit_message.problems` |
| Block secrets, protected folders, commits and pushes on `main` (Claude Code) | `.claude/hooks/guard_paths.py` |
| Format and lint-fix an edited file (Claude Code) | `.claude/hooks/format.py` |
| Isolate tests from the real home, secret files and the network (D-043) | `tests/isolation.py` (wired in `tests/conftest.py`) |

## Configuration

Settings live in a TOML settings file (D-044), given to every command by `--config PATH` (default `config.toml` in the current folder, git-ignored): `[server]` host, port, public host name, `https = false` in V1 (D-013); `[storage] data_dir` (relative to the settings file's folder); `[backup] retention_days`. The committed `config.example.toml` documents every key and is the development configuration (`uv run rack <command> --config config.example.toml`, data in `.local/dev-data/`). Secrets go in the `.env` file beside the settings file (git-ignored, template in `.env.example`); V1 needs none. `config.load_settings` reads both once, in `cli.py`, and the frozen `Settings` are passed down explicitly; no other layer reads the environment or these files. A missing or invalid file is an error, never a silent default.
