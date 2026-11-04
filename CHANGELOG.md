# Changelog

All notable changes are listed here, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow semantic versioning.

## [Unreleased]

## [1.0.0] - 2026-11-04

- Export of every stored fact: `rack export PATH [--format json|csv]` and « Exporter en JSON » / « Exporter en CSV » in « Réglages » → « Données » (`GET /api/export?format=json|csv`); JSON format version 1 in canonical units, CSV a zip of one `;`-separated UTF-8 file per table; credential hashes excluded (D-072 to D-074) (L6).
- The export reads the database in one read-only transaction (consistent, never blocks a write) and publishes a new file atomically, never replacing an existing one (L6).
- `rack restore SNAPSHOT` with the server stopped (supervisor lock and port probe): the snapshot is checked and staged as one file holding its WAL contents, the current database and its side files are kept aside as `.before-restore-<ts>`, an older snapshot is migrated; a blank instance is restored as is (D-075) (L6).
- Guides: Infomaniak Jelastic install on a Linux node with the database on local disk (`docs/deployment/jelastic.md`, D-076), NAS ↔ Jelastic migration (`docs/deployment/migration.md`), export and restore in `docs/deployment/nas.md` (L6).
- Fixed: older forms disable every button during a request, not only the first (L6).
- Fixed: « Réessayer » on a server-error page keeps the query string (L6).

- History (`/historique`): sessions newest first, grouped by month, 20 per page with « Plus anciennes »; a 12-week chart of sessions per week with the average above (D-067, D-070) (L5).
- Closed session detail: sets and settings corrected in place, every indicator recomputed; a session (open or closed) soft-deleted after confirmation, kept in the database (D-067) (L5).
- Progress (`/progression`, `/progression/{id}`): per exercise the last performance, records by category, a chart of the main indicator drawn by vendored Chart.js 4.6.1 from `GET /api/progression/{id}`, and its data table (D-068) (L5).
- RM measured or estimated: Epley, Brzycki, Lombardi, O'Conner or Wathan chosen in « Réglages » (`/reglages`); measured RMs entered or read from RM-test sets win on display, an estimate above an older test is flagged (D-069) (L5).
- Navigation « Historique » / « Progression »; the phone header takes three rows (brand, tracking, catalog) (D-070) (L5).
- Performance test: progress page plus chart JSON and history pages on one year of simulated history, median < 1 s (D-071) (L5).
- Fixed: numbers in requests are read as ASCII digits only, so « ² » in an id, a count or `Content-Length` is refused (413 for the header) instead of a server error (L5).

- Home page starts a session (place preselected from the last one, templates of that place, « Séance libre ») or resumes the open one; one open session at a time, a double start lands on the same session (D-061) (L4).
- Session page (`/seances/{id}`): the template's plan in order, one current exercise expanded, menus picked in one tap, exercises added by search with recent ones first, a pick changed while it has no set (D-061) (L4).
- Set logging: sets and settings prefilled from today's previous set, the last performance, the target or the field default; server-side « − » / « + » steppers, choice chips for discrete, yes / no and enum values, optional values collapsed under « Autres valeurs »; set types warm-up / work / RM test; one tap per unchanged set (D-062, D-063) (L4).
- Settings saved on each change; sets edited and soft-deleted during the session (D-062, D-066) (L4).
- Records (⭐) computed on every render from stored sets, never on the first session of an exercise; volume per category; close with confirmation, then a summary (duration, sets, volume, records) (D-064) (L4).
- Configuration: optional `[calendar] time_zone` (IANA, default `Europe/Brussels`) fixes each session's local date and zone; new dependency `tzdata` (D-065) (L4).
- Migration `0004`: index on `session_exercise (exercise_id)` (D-066) (L4).
- Performance test: set confirmation on one year of simulated history, median ≈ 15–20 ms (limit 100 ms) (D-066) (L4).
- A failed ✓ keeps focus on the ✓ and its message in view (D-053 refinement) (L4).

- Session templates (`/seances-types`): name unique after case and accent folding, location, order with « Monter » / « Descendre »; archive and restore, no delete (D-058) (L3).
- Template blocs: a fixed exercise or a menu (user label + up to 12 proposed exercises), at most 30 per template, reordered, removed by soft delete; archived exercises stay listed and tagged (D-058) (L3).
- Indicative targets per bloc (sets, reps or range, duration, distance, note), shown as « 4 × 6–8 », « 3 × 30 s / 12 · par côté »; compact target durations (D-059, D-055) (L3).
- Migration `0003`: `template_slot.deleted_at`, `exercise.seed_key` and unique indexes on `(user_id, seed_key)` and template `(user_id, name)` (L3).
- `rack migrate` seeds the four templates of the brief (Salle A, Salle B, Maison, Cardio); seed exercises carry stable keys, same-name user exercises are adopted (D-060) (L3).
- Navigation « Séances types »; below 40rem the nav takes its own row under the brand (L3).
- Ids beyond the database integer range return 404 on every route instead of a server error (L3).
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
