# Changelog

All notable changes are listed here, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow semantic versioning.

## [Unreleased]

- Variables: shared measures and settings created in the UI (`/variables`), code and enum keys derived once from labels and never reused, type / scope / scale frozen once values exist, archive always, delete only without stored values (D-054) (L2).
- Exercises (`/exercices`): name unique after case and accent folding, category, free-text movement pattern and equipment with suggestions, location; archive and restore, no delete (D-054) (L2).
- Exercise fields: core quantities or variables, required flag, step or proposed values, default, order with « Monter » / « Descendre »; values typed and shown in display units (kg, m / km, m:ss) (D-055) (L2).
- Aliases per exercise and accent-insensitive fuzzy search over names and aliases (« DC », « bench », « developpe ») (D-056) (L2).
- `rack migrate` seeds the 41 exercises of the brief in versioned, idempotent steps; names the user already has are skipped (D-057) (L2).
- Header navigation « Exercices » / « Variables » on every protected page; brand and content share a left edge (L2).
- Failed htmx requests (error status, network failure, 10 s timeout) keep the form and show « Non enregistré, réessayer » in it, announced, focus returned (D-053) (L2).
- Per-device access: `rack device add | list | revoke NAME`; `add` prints a one-time 8-digit code, valid 10 minutes, blocked after 5 wrong attempts; codes and tokens stored only as SHA-256 hashes (D-049) (L1b).
- Pairing page `/appairage`; every other route except `/static/` requires a paired device (unpaired navigation redirected, other requests `401 not_paired`); refusals re-render the form in place (D-050) (L1b).
- Device cookie `rack_device`: `HttpOnly`, `SameSite=Strict`, 400 days renewed by use, `Secure` only when `[server] https = true`; a revoked device loses access on its next request (D-040) (L1b).
- `rack supervise`: runs `rack serve`, restarts it after a crash (1 s doubling to 300 s), rotating logs in `<data_dir>/logs/`, one instance per data folder (D-038, D-051) (L1b).
- `rack update`: on a clean `main` clone, pull, `uv sync --frozen`, `rack migrate`, then restart through the supervisor; it still syncs, migrates and restarts when nothing new was pulled, so a rerun completes a failed update (D-052) (L1b).
- NAS install and update guide, LAN only: `docs/deployment/nas.md` (L1b).
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
