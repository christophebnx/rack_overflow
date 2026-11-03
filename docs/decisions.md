# Decisions

Each entry: the decision, why, and what it rules out. Do not reverse a decision silently: add a new entry that supersedes it (skill `/add-decision`).

## Tooling

**D-001 — Python ≥ 3.12, managed with uv; `uv.lock` is versioned.**
One tool for the interpreter, the virtual environment, dependencies and the lock file. CI runs `uv sync --locked`, so a dependency change without a lock update fails. Rejected: pip + requirements files (no lock of transitive versions), Poetry (slower, second tool).

**D-002 — Lint and format with ruff; duplicate code detected with pylint `duplicate-code`.**
Ruff runs in CI, in pre-commit and after every Claude Code edit (`.claude/hooks/format.py`). Pylint runs only its duplicate-code checker: it is the mechanical half of the one-responsibility rule (D-006); the reviewer agent covers the other half.

## Code structure

**D-003 — Source layout `src/<package>/`, pure `domain/` layer at the centre.**
`domain/` holds business rules and imports nothing else from the project; it reads no file, network, clock or environment (callers pass them in). Outer layers depend on it, never the reverse. Enforced by `tests/unit/test_layering.py`. Why: business rules stay testable in isolation and do not change when storage or interfaces change.

**D-004 — The CLI is a technical tool: English messages, explicit exit codes.**
0 success, 1 error, 2 usage. Errors print `<prog>: error: <message>` on stderr. Tests call `main([...])` in-process.

**D-005 — Atomic file writes only.**
Every user or state file is written by `storage/files.atomic_write` (temp file in the same folder, fsync, rename, folder fsync). A crash leaves the old file or the new one, never a mix.

**D-006 — One responsibility, one implementation.**
Each responsibility has exactly one implementation, listed in the responsibility map of `docs/architecture.md`. Duplication with a different implementation is a blocking review finding. Similar-looking code with a different responsibility is allowed.

## Working with Claude Code

**D-007 — Every change goes through `/feature`: architect → (ui-designer) → developer → tester → reviewer → documentation.**
Each agent has one job, limited tools and a ten-line report; details go into `docs/`. The architect writes a design note in `docs/architecture/` before any code. Why: decisions and designs survive the conversation, and the review checks the change against written rules rather than memory.

**D-008 — Autonomous build from the roadmap, state in `docs/progress.md`.**
`/build-roadmap` runs the milestones of `docs/roadmap.md` in order and stops on documented conditions (repeated failures, a decision to supersede, anything only the user can provide), writing `BLOCKED` and the question in `docs/progress.md`.

**D-009 — Claude Code never reads secrets and never commits or pushes on `main`.**
Enforced by `permissions.deny` in `.claude/settings.json` and by the PreToolUse hook `.claude/hooks/guard_paths.py` (secret files, protected folders, `git commit` and `git push` on `main`). Force-push, hard reset and branch deletion are denied. The user merges into `main` through pull requests.

**D-010 — Conventional Commits with a `Milestone:` footer, checked by a commit-msg hook.**
`tools/check_commit_message.py` (installed by `uv run pre-commit install`) rejects malformed messages. The footer ties every commit to a roadmap item. Git's own merge, revert and fixup messages pass unchecked.

**D-011 — English for code and repository text; the user language for what the end user sees.**
Code, identifiers, docs, prompts, agents, skills and commits in English. UI strings and exported content in the user language, from locale files.

## Project

**D-012 — No automatic CI until V1 is done; checks run locally.**
GitHub Actions minutes cost money, so the workflow runs only on manual dispatch (`workflow_dispatch`). Until V1 is complete, the definition of done is checked locally: tests (`not live`), ruff and duplicate-code, run by the tester and reviewer agents and by pre-commit. Once V1 is done, a minimal CI is designed (which jobs, which OS) and recorded in a new decision. Refines D-001 and D-002 (the "runs in CI" parts apply only to manual runs). Rules out: automatic runs on push or pull request, the three-OS matrix as a default. Status: approved by the user on 2026-11-03.

**D-013 — V1 is served over plain HTTP; transport security is deferred to V2.**
During development the app is reachable on the LAN only, with no WAN exposure. Once in use, the server listens on a high, non-standard port (from configuration) forwarded through the DDNS, without reverse proxy or certificate. Why: single user, unadvertised app, simpler deployment. Accepted risk: data and the session cookie travel in clear. Kept in V1: per-device authentication, `HttpOnly` / `SameSite=Strict` cookie, `Origin` check and JSON-only requests. The cookie `Secure` flag and HSTS depend on a configuration switch, so V2 enables HTTPS without code change. Status: approved by the user on 2026-11-03.

The entries below come from the approved release brief `docs/release-1.0.0-brief.md` (pre-brief D-001 to D-019, renumbered; pre-brief D-002 to D-004 dropped by D-015). Status of each: approved by the user on 2026-11-03.

### Product and stack

**D-014 — Same stack and tooling as Equinox Management: FastAPI, uvicorn, Pydantic v2, uv, ruff, pylint duplicate-code, pre-commit.**
Existing know-how and conventions are reused (appendix of the brief). Rules out: another web framework, Node tooling in the product.

**D-015 — V1 is one responsive web app, rendered on the server with Jinja2 and htmx; no PWA, no offline mode, no separate mobile app.**
The same pages serve the iPhone (360 px) and the desktop (1280 px). The gym network is reliable, so offline brings complexity (pack, outbox, service worker) without need. Offline may return in a later release, possibly as a mobile app using a JSON API added over `services/`. Rules out in V1: service worker, IndexedDB, client-side business logic, a front-end framework or build step. Supersedes pre-brief D-002 to D-004.

**D-016 — SQLite (WAL) through SQLAlchemy Core and Alembic; SQL kept Postgres-compatible.**
Unlike Equinox, the database is the only source of truth and its schema will evolve with real data, so real migrations are needed (Alembic batch mode for SQLite). No ORM: queries are explicit. Rules out: raw `sqlite3` with `PRAGMA user_version`, an ORM, SQLite-only SQL.

**D-017 — `user_id` on root tables from V1.**
Single user in V1, but multi-user later needs no schema migration of history.

**D-018 — Hybrid storage: four fixed columns on `set_entry` plus catalogued variables.**
`reps`, `weight_g`, `duration_s`, `distance_m` drive the computations and stay plain columns; every other measure or setting is a row in a value table referencing the `variable` catalog, so adding a variable needs no migration. Rules out: a wide table with one column per measure, full EAV, a JSON column.

**D-019 — Measures (per set) and settings (per session exercise) are distinct.**
A setting (seat height, grip) is fixed for the exercise within a session and prefilled from last time.

**D-020 — Canonical integer units: grams, seconds, metres.**
Conversion to kg and km happens only on display. No rounding error in storage.

**D-021 — Facts are stored, indicators are computed; history is never physically deleted.**
Sessions, sets, settings and measured RMs are stored; last performance, e1RM, records and volume are computed on the fly (low volume, no cache to invalidate). Exercises and variables are archived, sessions and sets soft-deleted (`deleted_at`).

**D-022 — RM: measured or estimated origin is tracked; the estimation formula is a global setting.**
Changing the formula recomputes estimates and never touches measured RMs. A measured RM wins on display; an estimate above an older test is flagged.

**D-023 — Session templates are menus by movement pattern.**
A slot is a specific exercise or a menu of proposed exercises chosen during the session, matching a non-fixed training practice.

**D-024 — Hosting on a Synology NAS or Jelastic, native Python deployment without Docker.**
`git` clone on `main`, `uv sync --frozen`, `rack migrate`, `rack serve`. SQLite on local storage only. The choice of host is reversible (backup, restore, URL change).

**D-025 — AI features are deferred to V2, behind a module of domain tasks with a configurable provider.**
V1 only keeps tracking computations reusable through `services/`.

**D-026 — Name Rack Overflow: distribution `rack-overflow`, package `rack_overflow`, CLI `rack`.**

**D-027 — The user language is French, and only French, in V1.**
Refines D-011: UI strings, messages, seed data and exports in French; code, docs and the CLI in English (D-004).

**D-028 — No rest timer in V1.**

**D-029 — Display units are kg and km only in V1** (metres and seconds where relevant). No unit switch.

### Data model

**D-030 — No variable in the seed; variables are created in the UI and shared across exercises.**
A variable is defined once (code, label, type, unit, scope) and linked to any number of exercises; editing it applies to all of them. The seed holds exercises and templates with core quantities only.

**D-031 — One link table `exercise_field` for core quantities and variables.**
Each row references either a core quantity or a variable (CHECK: exactly one) and carries the per-exercise parameters: required, increment, default, discrete values, display order. One place for parameters and one shared display order. Rules out: parameters of core quantities as columns of `exercise`.

**D-032 — A `decimal` variable is stored as an integer with a scale fixed on the variable; an `enum` value is stored by its stable key, never its label.**
Renaming an enum label never breaks history.

**D-033 — One write per fact for RMs.**
`rm_measured` holds only RMs entered manually outside a session; `rm_test` sets are read directly from `set_entry`.

**D-035 — Integer primary keys generated by the database.**
No client creates rows, so UUIDs bring nothing; integers are Postgres-compatible and readable in URLs.

**D-041 — Intervals: one set is one round, `duration_s` is the work time; no work / rest ratio in V1.**
V1 indicators for intervals: number of rounds and total work duration.

### Web and security

**D-034 — Every request other than GET / HEAD is JSON; htmx sends JSON through the vendored `json-enc` extension.**
A cross-site page can post a plain form without browser checks, but a cross-origin JSON request needs a CORS preflight, which this server never answers. With the `Origin` / `Sec-Fetch-Site` check and the `SameSite=Strict` cookie, this is the CSRF defence (Equinox `web/security.py`). Other rules kept from Equinox: CSP `default-src 'self'` with no inline script or style (htmx `includeIndicatorStyles: false`), `Referrer-Policy: no-referrer`, `nosniff`, no CORS header, `Host` checked against the configured public host name. Rules out: form-encoded bodies (a file upload later gets its own documented exception).

**D-036 — User-facing strings live in one flat catalog `locales/fr.json`, resolved on the server.**
Templates never hard-code French text; errors carry stable English codes mapped to French strings. A missing key renders the key itself and logs a warning.

**D-039 — Layers: `domain/` (pure rules), `storage/` (database and files), `services/` (business operations, one transaction each), `web/` (HTTP, templates), `cli.py`.**
Routes stay thin: validate, call a service, render. A future JSON API or AI module reuses `services/`.

**D-040 — Per-device authentication with a one-time pairing code and a long-lived cookie.**
`rack device add` issues a code valid 10 minutes, attempt-limited; the pairing page exchanges it for a random token stored hashed, sent as an `HttpOnly`, `SameSite=Strict` cookie (`Secure` when HTTPS is on, D-013), renewed on use, revocable. Rules out: passwords, tokens readable by JavaScript.

### Operations and tests

**D-037 — Daily backup from the first milestone with a database.**
`VACUUM INTO` a dated file, written atomically, integrity check first, 30-day retention; a corrupt database is never backed up nor deleted. Why early: real data exists as soon as logging works.

**D-038 — Supervision without Docker: `rack supervise` on the NAS, systemd on Jelastic.**
A DSM boot-up task does not restart a crashed process, so `rack supervise` restarts `rack serve` with an increasing delay and rotates logs. On Jelastic, a Linux / VPS node with a systemd unit (`Restart=on-failure`); the WSGI-oriented Python node does not fit an ASGI app.

**D-042 — Browser tests with the Python Playwright package, on Chromium and WebKit.**
WebKit is the closest engine to iPhone Safari. Pages are checked at 360 and 1280 px, light and dark. Without installed browsers the tests are skipped locally; `RACK_REQUIRE_BROWSER=1` makes them mandatory.

**D-043 — The Equinox test isolation guard is ported.**
A process-wide audit hook, activated around each test, refuses writes under the real home and `.local/`, reads of the secret and machine config files, and non-loopback network access; refusals fail the test even if caught. Loopback stays allowed for the browser tests.

### Technical foundation (L1a, design note `docs/architecture/2026-11-03-l1a-technical-foundation.md`)

**D-044 — Configuration: one required TOML file passed with `--config`, secrets in the `.env` beside it, loaded once by the CLI.**
`--config` defaults to `config.toml` in the current folder; a missing or invalid file, an unknown key or a wrong type is an error (exit 1), never a silent default. Relative `data_dir` is resolved against the config file's folder; `.env` is read with `dotenv_values` without touching `os.environ`. The committed `config.example.toml` is the development configuration (`.local/dev-data`). Only `cli.py` calls the loader; every other layer receives values. Refines the configuration convention of `docs/architecture.md`. Rules out: environment variables read by inner layers, defaults that could put production data in a development folder.

**D-045 — Backups: `rack-<UTC timestamp>.sqlite` snapshots by `VACUUM INTO` through the atomic writer, age-based retention keeping the newest, snapshot before a migration.**
Refines D-037. The integrity check runs before the copy and on the copy before its rename; a corrupt database is refused and logged, never moved, never deleted, and pruning is skipped. Retention removes snapshots older than `[backup] retention_days` (30) but always keeps the newest one; files whose name does not parse are never touched. `rack migrate` snapshots an existing database before applying pending revisions. The server runs the backup when the last one is at least 24 h old (checked at start-up and hourly). Moving a corrupt database aside and restoring is left to `rack restore` (L6). Rules out: count-based retention, the SQLite backup API, auto-restore by the server.

**D-046 — Database conventions: `BEGIN IMMEDIATE` transactions, frozen migrations shipped in the package, portable column types.**
Refines D-016, D-017, D-035. Every transaction starts with `BEGIN IMMEDIATE` (no `SQLITE_BUSY` on a read-to-write upgrade under WAL). Alembic scripts live in `storage/migrations/` and are configured in code, so an installed clone needs no `alembic.ini`; a committed migration is never edited, changes add a revision; upgrades run with foreign keys off and must pass `PRAGMA foreign_key_check` before commit. Columns: timestamps as UTC ISO 8601 text, `archived_at` / `deleted_at` / `revoked_at` nullable timestamps, `position` for order, JSON only for definition lists (enum values, discrete values), constraint naming convention, no `ON DELETE` actions, enumerated values from `domain/vocabulary.py` as `CHECK`, partial indexes declared for both SQLite and Postgres.

**D-047 — HTTP security details: pure ASGI middleware, loopback host names allowed, stable error codes, 64 KiB body limit.**
Refines D-034 and D-013. `Host` is checked by hostname (port ignored, since the DDNS forward may change it) against the configured public host plus `localhost`, `127.0.0.1`, `[::1]`, which DNS rebinding cannot use. Rejections answer JSON codes: `400 invalid_host`, `403 forbidden_origin`, `415 unsupported_media_type`, `413 payload_too_large`. `Cache-Control: no-store` on every non-static response; HSTS only when `[server] https = true`. htmx is configured by a `<meta name="htmx-config">` (`includeIndicatorStyles`, `allowEval`, `allowScriptTags` off, `selfRequestsOnly` on, `methodsThatUseUrlParams: ["get"]` so `DELETE` also sends JSON). Rules out: `BaseHTTPMiddleware`, inline htmx configuration script. Refined by D-048 (2026-11-03).

**D-048 — `Cache-Control: no-store` also on `/static/` error responses.**
Refines D-047. Every response with status ≥ 400 carries `no-store`, including under `/static/`, so a browser never caches a missing or failed asset in place of the real file; successful static responses keep default caching. Why: found in the L1a review. Rules out: cacheable error responses.

### Authentication and deployment (L1b, design note `docs/architecture/2026-11-03-l1b-auth-and-deployment.md`)

**D-049 — Device authentication details: 8-digit code, SHA-256 hashes, attempts charged to every live code, deny-by-default middleware.**
Refines D-040 and D-017. `rack device add` issues an 8-digit code (typed on the iPhone numeric keypad), valid 10 minutes; a wrong guess is charged to every live code (unused, unexpired), and the fifth kills it; expired, reused and revoked-device codes get one refusal ("generate a new code"); a malformed entry is not charged. The token is 32 random bytes (`secrets.token_urlsafe`); code and token are stored as unsalted SHA-256 hex: the token's entropy makes a slow hash useless, the code is dead within 10 minutes, and no server secret is needed. Cookie `rack_device`: `Path=/`, `HttpOnly`, `SameSite=Strict`, `Max-Age` 400 days, `Secure` only when `[server] https = true`, no `Domain`. Renewal: when `last_seen_at` is at least 1 hour old, it is updated and the cookie re-sent with a fresh `Max-Age` (same token, no rotation); a token unused for 400 days is refused. A pure ASGI `DeviceAuthMiddleware`, inside the security and unhandled-error middlewares, protects every path except `/appairage` and `/static/`: an unpaired browser navigation gets `303` to `/appairage`, any other request `401 {"error": "not_paired"}` with `HX-Redirect: /appairage` for htmx; an invalid cookie is cleared. V1 devices are created with `domain/users.SINGLE_USER_ID = 1`; routes take `user_id` from the authenticated device. Re-pairing is revoke then add. Rules out: per-router auth dependencies, token rotation, a write per request, per-IP or global attempt counters, a server secret for hashing.

**D-050 — A refusal of user input in an htmx form is answered `200` with the form fragment re-rendered in place.**
The request was understood and processed; its outcome (e.g. a wrong pairing code) is shown next to the field (`aria-invalid`, `aria-describedby`) and announced through the live region. Status codes ≥ 400 stay for protocol, authentication and server errors, which htmx does not swap; how those show « Non enregistré, réessayer » is still decided by L2 (open point of the L1a design note). Why: settles the only error display L1b needs without anticipating L2. Rules out: making 422 swappable through htmx `responseHandling` for this case. Refined by D-053 (2026-11-03).

**D-051 — `rack supervise` runs `rack serve` as a child with a doubling restart delay and rotating logs; `rack update` restarts it through SIGHUP.**
Refines D-038 and D-024. Restart delay 1 s doubling to at most 300 s, back to 1 s after a run of 60 s; logs in `<data_dir>/logs/rack.log`, stdlib `RotatingFileHandler`, 1 MiB × 5. Append-only logs are not user or state files: invariant 3 (atomic writes) does not apply to them. One supervisor per data folder through an `flock` on `supervise.lock` (no stale lock after a reboot) and a PID file written atomically. SIGTERM / SIGINT stop the child (SIGKILL after 10 s) and exit; SIGHUP stops the child and re-executes the supervisor, so both run the updated code. `rack update` requires the clone on `main` with no local changes, then runs `git pull --ff-only` (unchanged HEAD: stop), `uv sync --frozen`, `rack migrate` in a new process, and sends SIGHUP to the running supervisor; a failing step stops with exit 1 and no restart. Commands run through an injected runner, so tests never run git or uv. POSIX only (NAS, Jelastic Linux node). Rules out: a bare PID file as the instance guard, logrotate, stopping the server before the migration (a pause protocol for a seconds-long window). Refined by D-052 (2026-11-03).

**D-052 — `rack update` runs `uv sync` and `rack migrate` and requests a restart even when the pull brings nothing new.**
Refines D-051, whose "unchanged HEAD: stop" left a half-applied update stuck: when the pull succeeded but `uv sync` or the migration failed, a second `rack update` saw HEAD unchanged and stopped, so the next restart ran the new code on old dependencies or an old schema and `rack serve` refused to start in a loop. Now an unchanged HEAD prints `already up to date; checking dependencies and database`, then sync, migrate (both idempotent: nothing to do is a no-op, no backup when no revision is pending) and the SIGHUP run as after a pull; rerunning `rack update` completes an interrupted update. A SIGHUP that cannot be delivered is an error (exit 1) saying the migration was applied. The supervisor also treats a server or re-execution that cannot start (e.g. `.venv` being rebuilt) as a failed run that goes through the restart delay, instead of dying. Cost: an update with nothing new restarts the server (seconds; the user runs it when not logging). Rules out: recording the last completed update in a state file (one more file to keep right for a case that rerunning covers). Status: found in the L1b review, 2026-11-03.

### Catalog (L2, design note `docs/architecture/2026-11-03-l2-catalog.md`)

**D-053 — A failed htmx request (4xx / 5xx, network failure, timeout) is shown by one first-party script: « Non enregistré, réessayer » in the form's status slot, old refusal messages cleared, focus back on the form.**
Refines D-050, which kept refusals of user input as `200` re-rendered forms and left the rest to L2. `web/static/js/request-errors.js` (CSP `script-src 'self'`, no French text, no business logic) handles `htmx:afterRequest` when the request did not succeed and the response carries no `HX-Redirect`: htmx has not swapped, so the form keeps its values and its button is enabled again; the script clears `aria-invalid` and old `.field__error` messages in the form, fills its `[data-request-status]` slot and `#annonce` with the text the server put in `<body data-not-saved>`, and focuses the form's first field (else the trigger). The slot is cleared when the next request starts. `htmx-config` gains `timeout: 10000`. Server answers are unchanged (`{"error": code}` for htmx). Why: network failures and timeouts, the likely gym case, produce no response the server could shape. Rules out: htmx `responseHandling` with HTML error fragments (misses network failures), `hx-on` handlers (need eval), a message per error code (the user's action is the same: retry).
Refinement (2026-11-03, L2 UI design): a slot may carry its own text in `data-message`, used instead of `<body data-not-saved>` (the search form: `error.search_failed`, « Recherche impossible, réessayer », since a search saves nothing); the script also sets `data-kind="error"` on the slot.

Refinement (2026-11-03, L2 fix loop 1): focus goes to the first *visible* field of the form or scope (a field inside a closed `<details>` cannot take focus), else the trigger.

Refinement (2026-11-03, L2 fix loop 2): a trigger outside any `<form>` (row actions: move up / down, remove an alias, delete) keeps focus when it is still in the document, so the user retries in place instead of being sent to an unrelated field; a form trigger, or a trigger no longer in the page, sends focus to the first visible field of the form or scope, else the trigger.

**D-054 — Catalog rules: codes and enum keys derived once from labels, type / scope / scale frozen once values exist, delete only without values, at least one measure per exercise, movement pattern and equipment as free text with suggestions.**
Refines D-030, D-031, D-032 and invariant 8. A variable's `code` is `slug(label)` (suffixed on collision), set at creation and never shown or changed; enum keys are slugs of the first label, kept when labels or order change, never reused; a used key cannot be removed. Label, unit and enum labels are always editable and, being stored once, apply to every linked exercise. Type, scope and decimal scale change only while no `set_value` / `exercise_setting` row references the variable. A variable without stored values can be deleted (with its links, after confirmation); with values, only archived. Exercises are only archived. Names are unique per user after case and accent folding. Field parameters live on `exercise_field`: increment and discrete values are exclusive and numeric only; a default must fit the discrete values or, for an enum, be a key. Creating an exercise adds the core fields of its category (strength / kettlebell: reps + weight; bodyweight: reps; cardio: duration + distance; intervals: duration). Movement pattern and equipment are free text, suggested from existing values and stored in their first-seen spelling, because L3 menus carry user-chosen names and list their exercises explicitly. Rules out: a movement-pattern vocabulary (migration per pattern), user-typed codes, physical deletion of history.

**D-055 — Display and input of quantities: decimal comma; kg up to 3 decimals; metres below 1 km, else km; durations `m:ss` / `h:mm:ss`; values typed in display units and parsed by the domain.**
Refines D-020 and D-029 (and brief §4 "metres where relevant"). `domain/units` owns the conversions both ways (L4 reuses them); a bare distance is read as km and a bare duration as seconds; more decimals than the unit allows, negatives and garbage are field errors, never 422. Unit symbols come from `locales/fr.json`. Rules out: a per-exercise distance unit (schema change for no V1 need), a unit switch (D-029).

**D-056 — Search: one text normalisation (NFKD, accents removed, casefold, punctuation to spaces) and a tiered fuzzy ranking in pure Python over names and aliases; no dependency, no stored normalised name.**
Tiers: exact, prefix, every token a token prefix, initials (stop-words ignored, « DC »), substring, edit distance 1–2 on token prefixes; ties by recency (L4) then name; 20 results. The catalog is about a hundred strings, so ranking in memory takes under a millisecond. Rules out: rapidfuzz (compiled dependency, not in brief §10), SQLite FTS5 (not Postgres-compatible, no accent folding), a `name_normalised` column (migration and a copy to keep in sync).

**D-057 — The seed is a packaged JSON data file applied by `rack migrate` after the schema upgrade, in versioned steps recorded in `app_setting` `seed.version`.**
Step 1 (L2) creates the 41 exercises of brief §6.1 with core-quantity fields and aliases for `SINGLE_USER_ID`; L3 adds step 2 (templates). Steps above the stored version run in one transaction, then the version is stored, so a second run adds nothing, and a seeded exercise the user renamed or archived never comes back; an exercise whose normalised name already exists is skipped. The data goes through the same domain validators as the UI. Rules out: an Alembic data migration (frozen, cannot be corrected, French data in a migration), a separate `rack seed` command, seeding at server start-up. Refined by D-060 (2026-11-03).

### Templates (L3, design note `docs/architecture/2026-11-03-l3-templates.md`)

**D-058 — Template rules: names unique after normalisation, archive only, ordered by buttons; a slot's kind (exercise or menu) is fixed at creation; a menu always keeps one option; removing a slot is a soft delete; archived exercises stay in slots and are skipped in sessions.**
Refines D-023 and D-021. Template name 1–60 chars, unique per user after case and accent folding (archived included, backstop unique index), location gym / home / both; archive and restore only (restore puts it last), never deleted. Order among non-archived templates, slots and menu options changes by « Monter » / « Descendre » through one rule (`domain/ordering`). A menu's label is free text (suggested from movement patterns) and its options are listed explicitly; it is created with its first exercise and its last option cannot be removed; at most 30 slots per template and 12 options per menu. Removing a slot sets `template_slot.deleted_at` (revision 0003), so `session_exercise.template_slot_id` keeps pointing to it; removing an option deletes the configuration row. Archiving an exercise changes no template; add selects never offer archived exercises; at session start (L4) archived options are not offered, a slot with no available exercise is skipped and a menu with one available option is picked automatically. Rules out: physical slot deletion, nulling history's slot reference, changing a slot's kind in place, drag and drop.

**D-059 — Indicative targets use the existing typed columns: sets, a reps range (single value stored min = max), duration, distance and a short note, all optional and combinable.**
Targets are typed in display units (one reps text « 8–10 », durations and distances through `domain/units`) and shown by one formatter (`web/display.Display.target`, « 3 × 0:30 / 12 · par côté »). A menu may carry parts for different exercises (plank duration and crunch reps); L4 uses the parts matching the chosen exercise's fields. No weight or %1RM target in V1 (V1.x). Rules out: new target columns, a JSON target, separate min / max inputs.

**D-060 — Seed exercises carry a stable `seed_key` (revision 0003); step 2 of the seed creates the four templates of brief §6.1 referencing exercises by key.**
Refines D-057. `exercise.seed_key` (nullable, unique per user) is set by step 1, and on an exercise the user had already created with the same normalised name (adopted). Databases seeded before keys existed get them once, by normalised name, at the start of step 2; from then on references are by key, so renaming a seeded exercise never breaks the template seed. A template whose normalised name exists is skipped; an unresolved key drops the option or slot (a menu left without option is not created). Template names are the brief's titles. Rules out: references by name only, a key map in `app_setting`.
