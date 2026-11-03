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
| `cli.py` | Command-line entry point: parses arguments, calls the layers, maps errors to exit codes (D-004). | everything |

Add a row when adding a package, and the matching entry in `ALLOWED` of `tests/unit/test_layering.py`. Each package has a `CLAUDE.md` with its rules and module table.

## Responsibility map

One responsibility, one implementation (CLAUDE.md invariant 2). Check here before writing code; update this table when adding a cross-cutting responsibility.

| Responsibility | Implementation |
|---|---|
| Base class of business errors | `domain/errors.DomainError` |
| Write a file atomically (temp + fsync + rename) | `storage/files.atomic_write` |
| Map an error to a CLI exit code and message | `cli.main` |
| Check a commit message | `tools/check_commit_message.problems` |
| Block secrets, protected folders, commits and pushes on `main` (Claude Code) | `.claude/hooks/guard_paths.py` |
| Format and lint-fix an edited file (Claude Code) | `.claude/hooks/format.py` |

## Configuration

Settings live in a machine settings file at the repository root (git-ignored): data folder, host, port, public host name, `[server] https = false` in V1 (D-013). Secrets go in the secrets file (git-ignored, template in `.env.example`); V1 needs none. Both are loaded once at start-up by the configuration module and passed down explicitly; no layer reads the environment on its own. Convention of this template: secrets in `.env` (git-ignored, template in `.env.example`), machine-specific settings in `config.toml` (git-ignored), local runtime data in `.local/` (git-ignored; `.local/dev-data/` for development, `.local/credentials/` never read by Claude Code).
