# rack_overflow — project rules

Read this file at the start of every session. It is the source of truth for how to work on this repository. When a rule here conflicts with your own habit, the rule wins. When a request conflicts with a rule, say so before doing anything.

## What this is

Rack Overflow is a personal training tracker (strength, kettlebell, bodyweight, cardio) for a single user. It is one responsive web app, rendered on the server with FastAPI, Jinja2 and htmx, backed by SQLite, and deployed natively (no Docker) on a Synology NAS; the user logs sessions from Safari on an iPhone at the gym or at home, and manages the catalog and reviews progress from a desktop browser. No offline mode in V1. Its main capabilities:

1. Create exercises and shared variables (measures and equipment settings).
2. Create session templates as menus by movement pattern.
3. Log a session fast: prefilled sets and settings, steppers, one tap per unchanged set.
4. Track progress: history, records, RM measured or estimated, charts.

The V1 scope, milestones and settled questions are in `docs/release-1.0.0-brief.md` (approved). Read next: `docs/architecture.md` (how), `docs/decisions.md` (why), `docs/roadmap.md` (what to build, in order), `docs/progress.md` (where the build stands).

## Commands

```bash
uv sync                                   # install (creates .venv and uv.lock)
uv run pre-commit install                 # pre-commit and commit-msg hooks
uv run pytest -q -n auto -m "not live"    # tests in parallel; drop -n auto to debug one test
uv run pytest -q -n auto -m "not live and not browser"   # skip the Playwright browser tests
uv run pytest -q tests/e2e                # browser tests only; an engine not installed is skipped
RACK_REQUIRE_BROWSER=1 uv run pytest -q tests/e2e        # fail instead of skip (Chromium and WebKit)
uv run pytest -q tests/integration/test_session_performance.py   # time the set confirmation alone (median < 100 ms, D-066)
uv run ruff check . && uv run ruff format --check .
uv run pylint --disable=all --enable=duplicate-code src
uv run rack --version                                  # the CLI
uv run rack migrate --config config.example.toml       # create / upgrade the dev database (.local/dev-data/), seed exercises and the four templates (D-057, D-060), then seed the exercise catalog (versioned, idempotent, D-057)
uv run rack backup --config config.example.toml        # snapshot the dev database now, prune expired snapshots
uv run rack serve --config config.example.toml         # dev server on http://127.0.0.1:8765 (run migrate first)
uv run rack device add NAME --config config.example.toml     # print a one-time pairing code (also: list, revoke NAME)
uv run rack supervise --config config.example.toml     # run serve, restart on crash, logs in <data_dir>/logs/ (POSIX)
uv run rack update --config config.toml                # deployed clone only: pull main, sync, migrate, restart (D-052)
```

Always pass `--config config.example.toml` in development: the default `config.toml` is the machine's real settings file (invariant 4). For `rack device`, `--config` comes after the action (`rack device list --config …`). Session dates and times use `[calendar] time_zone` of the settings file (default `Europe/Brussels`, D-065). Every page except `/appairage` needs a paired device: pair the dev browser with `rack device add`. NAS install: `docs/deployment/nas.md`.

## Invariants — never violate

1. **Layering.** `domain/` is pure business logic: it imports nothing from other packages of `rack_overflow`, does no I/O, reads no clock or environment implicitly (pass `now`, paths and values in). Everything else may depend on `domain/`. `tests/unit/test_layering.py` enforces this.
2. **One responsibility, one implementation.** Before writing a function, check the responsibility map in `docs/architecture.md` and search the codebase. Reuse or extend; write new code only when nothing fits, and say why in your summary. Similar-looking code with a different responsibility is fine.
3. **File writes are atomic.** Every write of a user or state file goes through `storage/files.atomic_write` (temp file + fsync + rename). No partial state on failure.
4. **Never read secrets.** Never read `.env`, `config.toml`, `.local/credentials/`, or any real user data. Work only with `.local/dev-data/` and `tests/fixtures/`. A hook enforces this.
5. **Tests never call paid or remote services by default.** Such tests carry `@pytest.mark.live` and are excluded by `addopts`.
6. **Decisions are recorded.** A decision that changes how the system behaves goes into `docs/decisions.md`. A decision is never reversed silently: add an entry that supersedes it.
7. **Canonical integer units.** Weights in grams, durations in seconds, distances in metres, stored as integers; conversion to kg and km only on display (D-020). A `decimal` variable is an integer with the variable's scale; an `enum` value is stored by its stable key, never its label (D-032).
8. **History is never physically deleted.** Exercises, variables and templates are archived; sessions and sets are soft-deleted with `deleted_at` (D-021). A variable linked to exercises with history cannot be deleted.
9. **Facts are stored, indicators computed.** Last performance, e1RM, records and volume are computed from stored facts, never stored themselves; one write per fact (D-021, D-033).
10. **Schema changes go through Alembic migrations**, SQL kept Postgres-compatible, `user_id` on root tables (D-016, D-017).
11. **Every non-GET request is JSON** and passes the security middleware; no form-encoded body, no inline script or style, no external resource in pages (D-034).
12. **No French text in code.** User-facing strings come from `locales/fr.json` (D-036).

## Language convention

- English: code, identifiers, JSON keys, file and folder names, every `.md` in the repo, prompts, skills, agents, commit messages.
- User language, French only in V1 (D-027): UI strings, seed data, exported content, messages shown to the end user. URL paths seen by the user are in French; route functions stay in English. The CLI is a technical tool and stays in English (D-004).

## How to work

- For any feature or change, use the `/feature` skill: architect → ui-designer (UI changes only) → developer → tester → reviewer (+ ui-designer review for UI changes) → documentation.
- To build the roadmap autonomously, or resume it, use `/build-roadmap`. Progress and blocking questions live in `docs/progress.md`.
- Each agent returns at most ten lines. Details go into `docs/`, not into the conversation.
- Definition of done, checked locally (no automatic CI, D-012): tests green (`not live`), ruff clean, no new duplicate-code finding, docs and the relevant `CLAUDE.md` updated, `CHANGELOG.md` entry added.
- Each package under `src/rack_overflow/` has its own `CLAUDE.md` (rules and module table). Read it before touching the package; keep it true after.

## Git workflow

- **Never commit on `main`.** Work on a feature branch or on `dev` (in a cloud session, the session's designated branch plays the role of `dev`). The user merges into `main` through a pull request.
- **Clean commits.** One commit per coherent unit of work (a module and its tests, a fix, a docs update), never one commit per agent and never "WIP". Every commit leaves the tree green.
- **Message format** (Conventional Commits, English):
  ```
  <type>(<scope>): <imperative summary, max 72 chars>

  <why and what, wrapped at 72 chars>

  Milestone: <id from docs/roadmap.md, e.g. B0, L1a, L4>
  ```
  Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`. Scope: the layer or area (`domain`, `storage`, `cli`, `docs`, `claude`, `ci`, `deps`…).
- Code and the docs it changes go in the same commit. Milestone-wide doc updates (roadmap, progress, changelog) go in a final `docs` commit for that milestone.
- To correct the last unpushed commit, use `git commit --amend`. Never rewrite earlier history, never force-push, never delete a branch.
- Stage files explicitly (`git add <paths>`); never commit `.env`, `config.toml` or anything under `.local/`.
- Enforced: a Claude Code hook blocks `git commit` and `git push` on `main`; the `commit-msg` hook (`tools/check_commit_message.py`) rejects malformed messages; pre-commit runs ruff, duplicate detection and gitleaks.

## Out of scope (do not build unless asked)

V1 excludes (brief section 3.2):

- Offline mode, PWA, service worker, separate mobile app (D-015).
- HTTPS, reverse proxy (D-013) and automatic CI (D-012): V2 / after V1.
- Rest timer, work / rest ratio of intervals, unit switch (D-028, D-041, D-029).
- Excel import, %1RM targets (V1.x); AI features, body metrics, actual multi-user (V2).
- External integrations (Garmin, Apple Health, Strava), scanned log import, social, nutrition, auto-progression programs.
