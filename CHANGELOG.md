# Changelog

All notable changes are listed here, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow semantic versioning.

## [Unreleased]

- Configuration: one TOML settings file passed with `--config` (default `config.toml`), secrets in the `.env` beside it; committed `config.example.toml` for development; a missing or invalid file is an error (D-044) (L1a).
- `rack migrate`: creates or upgrades the SQLite database (full V1 schema, Alembic revisions shipped in the package), idempotent, snapshots an existing database before pending revisions (D-046) (L1a).
- `rack backup` and a daily backup in the server: `rack-<UTC timestamp>.sqlite` snapshots by `VACUUM INTO`, integrity checked, 30-day retention keeping the newest; a corrupt database is refused, never moved or deleted (D-045) (L1a).
- `rack serve`: web app with the base layout, home page and French error pages, vendored htmx and `json-enc`, light and dark themes; refuses to start on a database that is not up to date (L1a).
- Security middleware on every response: `Host`, `Origin` / `Sec-Fetch-Site` and JSON-only checks, 64 KiB body limit, CSP and security headers, `no-store` on pages and error responses (D-047, D-048) (L1a).
- Tests: isolation guard ported from Equinox (D-043); Playwright browser tests on Chromium and WebKit, marker `browser` (D-042) (L1a).
- Removed: the template `hello` command (L1a).
- Project initialised from the Python template: package `rack_overflow`, CLI `rack` (B0).
- Approved V1 brief, roadmap (L1a to L6), decisions D-012 to D-043, architecture overview and UI rules (B0).
- CI runs on manual dispatch only until V1 is done (D-012).
- From the template: `src/` layout managed with uv, pure `domain/` layer with a layering test, atomic file writer, Claude Code agents, skills and hooks, commit-msg check, pre-commit (ruff, duplicate code, gitleaks).
