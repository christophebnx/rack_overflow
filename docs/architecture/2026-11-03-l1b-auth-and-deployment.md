# L1b — Per-device authentication and NAS deployment (design note)

Status: APPROVED FOR AUTONOMOUS MODE

Every point is settled by the approved brief (sections 4, 6 L1b, 7.2, 8, 10, 11 C and K) and by D-013, D-024, D-034, D-038, D-040, D-044 to D-048. This note fixes the implementation details the brief leaves open and records them as new, non-superseding decisions D-049 to D-051. No decision is superseded, no released data format changes, no schema migration is needed, and every user-visible behaviour (pairing page, redirect of an unpaired browser, refusal of expired / reused / wrong codes, attempt limit, revocation) is described in the brief and the roadmap.

## Context

Milestone L1b (`docs/roadmap.md`): `rack device add | list | revoke`, the public pairing page, the hashed token cookie (D-040), every route except pairing and static assets behind a paired device, `rack supervise` (D-038), `rack update`, NAS install docs (LAN only, D-013).

Current state (end of L1a): `cli.py` has `migrate`, `backup`, `serve` (flat `COMMANDS` of `Callable[[Settings], None]`); `web/app.create_app` installs, from inside out, router → `UnhandledErrorMiddleware` → `SecurityMiddleware`; `web/errors` maps statuses to codes and has `wants_page`; the schema (head `0002`) already has `device` (user_id, name, token_hash null, created_at, last_seen_at null, revoked_at null; `uq(token_hash)`; partial unique `(user_id, name) WHERE revoked_at IS NULL`) and `pairing_code` (device_id, code_hash, expires_at, attempts ≥ 0, used_at null). No timestamp-text helper exists yet. `tests/conftest.client` is an unauthenticated `TestClient`; e2e `live_server` serves the app on loopback.

## Chosen design

### Layering

| Unit | May import (project) | New in L1b |
|---|---|---|
| `domain/` | nothing | `timestamps.py`, `users.py`, `devices.py`, `supervision.py` |
| `storage/` | `domain` | `devices.py` (queries) |
| `services/` | `domain`, `storage` | `devices.py` |
| `web/` | `domain`, `services`, `config` | `auth.py`, `routes/pairing.py`, `templates/pairing.html` (+ fragments), `static/css/pages/pairing.css` |
| `ops/` (new package) | `domain`, `storage` | `supervise.py`, `update.py`, `CLAUDE.md` |
| `cli.py` | everything | `device`, `supervise`, `update` commands |

`ops/` holds host process management (supervision, self-update). It is neither a business operation (`services/`) nor HTTP (`web/`). Add `"ops": {"domain", "storage"}` to `ALLOWED` in `tests/unit/test_layering.py`, a layers row in `docs/architecture.md` and `ops/CLAUDE.md`.

### 1. Domain rules (pure)

- `domain/timestamps.py` — new cross-cutting responsibility, "database timestamp text": `to_text(dt) -> str` (UTC, `YYYY-MM-DDTHH:MM:SSZ`, aware datetimes only, else `DomainError`), `from_text(text) -> datetime` (aware UTC). Every timestamp column written from L1b on goes through it (L4 reuses it).
- `domain/users.py` — `SINGLE_USER_ID = 1`: the one user of V1 (D-017). Only the device creation uses it; once paired, the `user_id` comes from the device row (`request.state.device.user_id`), so later routes never read the constant and multi-user (V2) changes one place.
- `domain/devices.py`:
  - Constants: `CODE_DIGITS = 8`, `CODE_TTL = 10 min`, `MAX_ATTEMPTS = 5`, `TOKEN_BYTES = 32`, `TOKEN_LIFETIME = 400 days`, `RENEW_AFTER = 1 h`, `NAME_MAX = 40`.
  - `DeviceError(DomainError)`.
  - `validate_name(raw) -> str`: stripped, 1 to `NAME_MAX` characters, no control character; else `DeviceError`.
  - `normalise_code(raw) -> str | None`: removes spaces and hyphens; `None` unless exactly 8 ASCII digits. `format_code(code) -> "1234 5678"` (display).
  - `hash_secret(secret) -> str`: SHA-256 hex digest. Used for both the pairing code and the token (D-049 explains why no salt and no slow hash).
  - `PairingOutcome` (str enum, stable English codes): `paired`, `wrong_code`, `code_expired`, `too_many_attempts`.
  - `judge_match(expires_at, used_at, attempts, device_revoked, device_paired, now) -> PairingOutcome` for a code row whose hash matched: used, expired, device revoked or already paired → `code_expired`; `attempts >= MAX_ATTEMPTS` → `too_many_attempts`; else `paired`.
  - `is_live(expires_at, used_at, attempts, now) -> bool` (unused, unexpired, attempts left) — the codes a wrong guess is charged to.
  - `token_valid(last_seen_at, now) -> bool` (`now - last_seen_at < TOKEN_LIFETIME`), `needs_renewal(last_seen_at, now) -> bool` (`now - last_seen_at >= RENEW_AFTER`).
- `domain/supervision.py`: `RestartPolicy` (frozen: `initial_s = 1`, `factor = 2`, `max_s = 300`, `stable_after_s = 60`) and `next_delay(policy, previous_delay_s: float | None, uptime_s: float) -> float`: `initial_s` on the first crash or after a run of at least `stable_after_s`, else `min(previous * factor, max_s)`.

Randomness: the domain never draws random values (domain `CLAUDE.md`). `services/devices.py` draws them with `secrets.randbelow(10**8)` (code, zero-padded) and `secrets.token_urlsafe(TOKEN_BYTES)` (43-character token); the plaintext is returned to the caller once, so tests need no seeding.

### 2. Storage — `storage/devices.py`

SQLAlchemy Core queries on `schema.device` / `schema.pairing_code`, each taking a `Connection` (the service owns the transaction, `BEGIN IMMEDIATE` through `db.create_engine`): `insert_device`, `insert_pairing_code`, `active_device_by_name`, `all_devices` (with derived state), `revoke`, `codes_by_hash(code_hash)` (newest first, joined with the device's `revoked_at` / `token_hash`), `live_codes(now_text)`, `add_attempt(code_ids)`, `mark_used`, `set_token`, `device_by_token_hash` (active only), `touch(device_id, now_text)`. A unique violation on the active-name index becomes `DeviceNameTakenError(StorageError)`. No schema change: the existing columns hold everything; `pairing_code` stays unindexed on `code_hash` (a handful of rows ever).

### 3. Services — `services/devices.py` (one transaction each)

- `add_device(engine, name, now) -> NewDevice(name, code, expires_at)`: validates the name, refuses an active device with the same name (`DeviceError`: `device "<name>" already exists; revoke it first`), inserts the device (`user_id = SINGLE_USER_ID`, `token_hash` null) and one pairing code (`code_hash`, `expires_at = now + CODE_TTL`). Re-pairing a device = revoke, then add (no "reissue" path: one way to do it).
- `list_devices(engine) -> list[DeviceInfo]` (name, state `pending` / `paired` / `revoked`, created_at, last_seen_at), oldest first.
- `revoke_device(engine, name, now)`: sets `revoked_at` on the active device of that name; none → `DeviceError: no active device named "<name>"`. Its token and pending codes stop working at once (every check filters on `revoked_at IS NULL`).
- `pair(engine, raw_code, now) -> PairingResult(outcome, token | None, remaining_attempts | None, device_name | None)`:
  1. `normalise_code`; malformed input → `wrong_code`, not charged (it guesses nothing).
  2. Newest code row with the same hash → `judge_match`. `paired`: `mark_used`, `set_token(hash_secret(token))`, `last_seen_at = now`, return the token. `code_expired` / `too_many_attempts`: return the outcome, nothing written.
  3. No match: `add_attempt` on every live code (in practice the one just issued); the outcome is `too_many_attempts` if that exhausted every live code, else `wrong_code` with the smallest remaining count (`None` when no code is live). Charging every live code is what makes the limit real: a wrong guess cannot be tied to the code it aimed at, and an attacker gets at most `MAX_ATTEMPTS` guesses per issued code.
- `authenticate(engine, token, now) -> Device | None` (`Device`: id, user_id, name, `renewed: bool`): returns `None` without touching the database unless the token has the token shape (43 characters of `[A-Za-z0-9_-]`); else one transaction: active device by `hash_secret(token)`, refused if `not token_valid(last_seen_at)`; when `needs_renewal`, `touch` (`last_seen_at = now`) and `renewed = True`.

Cost of `last_seen_at`: one indexed `SELECT` per authenticated request and at most one `UPDATE` per device per hour, not one write per request (which would add an fsync with `synchronous = FULL` to every request against the < 100 ms budget of L4). `rack device list` therefore shows last use to within the hour.

### 4. CLI — `rack device`, `rack supervise`, `rack update`

`cli.py` moves from `Callable[[Settings], None]` to handlers receiving `(settings, args)` and supports one level of nested sub-commands (`device add NAME`, `device list`, `device revoke NAME`). The "database must be current" check of `run_serve` becomes one helper `_open_current_database(settings) -> Engine` used by `serve` and `device` (one implementation). Exit codes and the `rack: error:` format are unchanged (D-004); `DeviceError` is a `DomainError`, `DeviceNameTakenError` a `StorageError`, `OpsError` (new, `ops/errors.py`) is added to the mapped errors.

- `rack device add NAME` prints `device "iPhone" added; pairing code 1234 5678, valid until 2026-11-03T18:14:05Z (10 minutes)` then `open http://<public_host>:<port>/appairage on the device and type the code` (`https` when `[server] https`). The code is printed once and never stored in clear or logged.
- `rack device list` prints one aligned row per device: name, state, created, last seen (`-` when never).
- `rack device revoke NAME` prints `device "iPhone" revoked`.
- All three work while the server runs (WAL, `busy_timeout`).

### 5. Web — authentication and pairing

**Middleware order** (outermost first): `SecurityMiddleware` → `UnhandledErrorMiddleware` → `DeviceAuthMiddleware` (new) → Starlette's exception middleware → router. So `Host`, `Origin`, JSON-only and body-size checks run before any database access (an unpaired form-encoded POST still gets `415`), every redirect and `401` carries the security headers and `no-store`, and a database failure during the check becomes the 500 page. In `create_app`: `add_middleware(DeviceAuthMiddleware, …)` first, then `errors.install(app)`, then `SecurityMiddleware` (Starlette: last added is outermost).

**`web/auth.py`** — `DeviceAuthMiddleware` (pure ASGI, like `SecurityMiddleware`; deny by default, so a route added later is protected without anyone remembering to):
- Public: `/appairage` (GET, POST) and everything under `/static/`. Static requests skip the check entirely (no database hit per asset). Error responses are rendered for whatever path was requested, so a 404 under `/static/` or a 405 on `/appairage` stays public; an unpaired request to any other path, existing or not, gets the unpaired answer, never a 404 that reveals the route table.
- Reads the `rack_device` cookie; when present (and the path is not static) calls `services.devices.authenticate` through `starlette.concurrency.run_in_threadpool` with the injected clock, and stores the result in `scope["state"]["device"]` (read by routes as `request.state.device`).
- Unpaired (no cookie, unknown, revoked or expired token) on a protected path: a browser navigation (`errors.wants_page`, method GET / HEAD) → `303 See Other`, `Location: /appairage`; anything else → `errors.error_response(request, 401)` = `{"error": "not_paired"}`, plus `HX-Redirect: /appairage` when `HX-Request` is present (htmx follows `HX-Redirect` before its status handling, so a revoked phone in the middle of an action lands on the pairing page). No `next` parameter (no open redirect; the app has one entry point).
- A cookie that did not authenticate is cleared on the same response (`Set-Cookie: rack_device=; Max-Age=0; …`). A renewed device gets the cookie re-sent with a fresh `Max-Age` (same token, no rotation).
- Cookie owner functions: `device_cookie(token, https) -> str` and `cleared_cookie(https) -> str`: `rack_device=<token>; Path=/; Max-Age=34560000; HttpOnly; SameSite=Strict`, plus `; Secure` only when `[server] https = true` (D-013, D-040). No `Domain` attribute (host-only cookie). Header values are appended to the `http.response.start` message, never replacing a `Set-Cookie` set by the route.
- Logging: pairing success (device name) at INFO, refusals (outcome) at WARNING; never the code or the token.

**`web/errors.py`**: `CODES[401] = "not_paired"`, `MESSAGE_KEYS["not_paired"] = "error.not_paired"` (D-036: every code has its string).

**`web/routes/pairing.py`**:
- `GET /appairage` → `pairing.html`: the code form; when `request.state.device` is set, the "already paired" state with a link to the home page instead. Public, so the page also covers the `SameSite=Strict` case where a cross-site link opens the app without the cookie: its home link is a same-site navigation that carries the cookie.
- `POST /appairage`, JSON body `{"code": "<text>"}` sent by htmx `json-enc` (`PairingRequest`, Pydantic, `code: str`, max 32 characters; a missing or oversized field is the generic 422 JSON, unreachable from the page). Calls `services.devices.pair(engine, code, clock())`.
  - `paired` → `200`, `Set-Cookie` (`device_cookie`), `HX-Redirect: /`, body: a short success fragment (shown only to a client that ignores `HX-Redirect`).
  - `wrong_code` (with remaining attempts when known), `code_expired`, `too_many_attempts` → `200` with the form fragment re-rendered in place (`hx-target` the form, `hx-swap="outerHTML"`), carrying the outcome's message tied to the input (`aria-describedby`, `aria-invalid`), the input emptied, and the live region filled out of band (D-050). For `code_expired` and `too_many_attempts` the message says to generate a new code with `rack device add`.
- The form: `<form hx-post="/appairage" hx-disabled-elt="find button">`, one `<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="9">` with its `<label>`, one primary submit button. A native (non-htmx) submit would be form-encoded and get `415`: htmx is required, as on every page (D-015, D-034).
- Exact layout, strings and keys: ui-designer, in `docs/ui-spec.md` ("L1b — Pairing") and this note's "UI design" section. Outcome → message key mapping is explicit in the route (`pairing.wrong_code`, `pairing.wrong_code_remaining`, `pairing.code_expired`, `pairing.too_many_attempts`).

**htmx error display (L1a open point)**: L1b needs to show refusals of user input only, and D-050 settles that narrow case (200 + re-rendered form). Display of 4xx / 5xx and network failures (« Non enregistré, réessayer ») stays with L2, which has the first protected htmx action.

### 6. `rack supervise` — `ops/supervise.py`

- `Supervisor(command, log_path, policy, *, monotonic, wait, logger)` with `run(stop: threading.Event) -> int`: start `command` with `stdout=PIPE, stderr=STDOUT`, copy each line to the rotating log, wait for the exit; unless `stop` is set, log `server exited with code N; restarting in D s`, wait `next_delay(...)` with `stop.wait(delay)` (interruptible), restart. Uptime from the injected `monotonic`; the restart policy from `domain/supervision`.
- `stop()` path: SIGTERM to the child, wait up to 10 s, then SIGKILL; return 0.
- Logs: `<data_dir>/logs/rack.log`, `logging.handlers.RotatingFileHandler` (`maxBytes = 1 MiB`, `backupCount = 5`, UTF-8). Child lines are written as they come (the server already timestamps them); the supervisor's own lines get the same UTC format as `cli.configure_logging` (one formatter constant, reused). Append-only logs are not user or state files: invariant 3 (atomic writes) does not apply to them (D-051). No new dependency and no hand-written rotation.
- `run_supervise(settings, config_path)` in `cli.py`: validates the settings, creates `logs/`, takes the supervisor lock, writes the PID file, installs handlers (SIGTERM / SIGINT → `stop`; SIGHUP → stop the child, then `os.execv(sys.executable, [sys.executable, "-m", "rack_overflow", "supervise", "--config", <absolute config path>])`), and runs `Supervisor` on `[sys.executable, "-m", "rack_overflow", "serve", "--config", <absolute config path>]`. `sys.executable` is the clone's `.venv` Python, and `uv sync` installs the project in editable mode, so both the restarted server and the re-executed supervisor run the updated code.
- Single instance: `fcntl.flock(LOCK_EX | LOCK_NB)` on `<data_dir>/supervise.lock`, held for the process lifetime (released by the kernel on any death, so a reboot or crash never leaves a stale lock, unlike a bare PID file whose PID may be reused). A second `rack supervise` exits 1 (`another rack supervise is running`). The PID goes to `<data_dir>/supervise.pid` through `storage/files.atomic_write`, removed on clean exit. `ops/supervise.running_supervisor_pid(data_dir) -> int | None`: tries the lock non-blocking (acquired → none running, released at once), else reads the PID file.
- POSIX only (`fcntl`, signals): the NAS and the Jelastic Linux node (D-038). On Jelastic systemd supervises `rack serve` directly (L6).

### 7. `rack update` — `ops/update.py`

`update(repo, config_path, *, run, find_supervisor, send_signal, out) -> int` with an injected command runner `run(argv, cwd) -> CompletedProcess` (CLI: `subprocess.run`, `check=False`, captured output echoed), so tests never run git or uv:
1. Preconditions: `repo` (two levels above the installed package, `Path(rack_overflow.__file__).parents[2]`) contains `.git` and `pyproject.toml`; `git rev-parse --abbrev-ref HEAD` is `main`; `git status --porcelain` is empty (git-ignored `config.toml`, `.env`, `.venv`, `.local/` do not count). Else `OpsError` (`the deployed clone must be on main with no local changes`), nothing changed.
2. `git rev-parse HEAD`, `git pull --ff-only`, `git rev-parse HEAD`: unchanged → print `already up to date` and stop (no sync, no restart).
3. `uv sync --frozen` (`uv` from `shutil.which`, missing → `OpsError`).
4. `<sys.executable> -m rack_overflow migrate --config <config>` in a **new process**, so the migrations of the pulled code run (the current process holds the old modules); it takes its own pre-migration backup (D-045).
5. Restart: `find_supervisor(data_dir)`; found → SIGHUP, print `restart requested (supervisor pid N)`; none → print `no rack supervise running; restart the server yourself` and exit 0.

Any failing step stops the sequence, prints the step and its output, exits 1, and requests no restart; the running server keeps its loaded code. Window accepted: between `uv sync` / `migrate` and the restart (seconds), the old process serves on the new files and schema; the user runs `rack update` when not logging (documented). Rejected alternatives below.

### 8. NAS install docs — `docs/deployment/nas.md` (English, D-011)

For the DS224+ on DSM 7.2, as a dedicated non-admin DSM user: enable SSH; install Git (Package Center "Git Server", which provides the `git` command); install uv into `~/.local/bin` (it provides Python 3.12); clone `main` to `/volume1/rack/rack_overflow` (local volume); data folder `/volume1/rack/data` on the local volume, never a mounted share; `cp config.example.toml config.toml` and set `host = "0.0.0.0"`, `port = 8765`, `public_host` = the LAN IP or name typed in the browser, `https = false`, absolute `data_dir`; `uv sync --frozen`; `.venv/bin/rack migrate --config config.toml`; DSM Task Scheduler → Create → Triggered Task → User-defined script, event **Boot-up**, user = the dedicated user, script `cd /volume1/rack/rack_overflow && .venv/bin/rack supervise --config config.toml`; run it once by hand; DSM firewall rule allowing the port from the LAN subnet only and **no router port forward** (LAN only during development, D-013; no reverse proxy, no certificate); pair the iPhone (`rack device add iPhone`, open the printed URL in Safari, type the code); logs in `<data_dir>/logs/`; stop with `kill $(cat <data_dir>/supervise.pid)`; update with `.venv/bin/rack update --config config.toml` (when not logging); reboot check. A "Later" section: exposure on a high, non-standard port through the DDNS is a user-made router change; `public_host` then becomes the DDNS name, and since the cookie is bound to the host name typed in the browser, each device pairs again under the new name. Jelastic stays L6. Each step ends with a check command and its expected output, for the user validation.

### Responsibility map additions (`docs/architecture.md`)

Database timestamp text → `domain/timestamps`; the V1 user id → `domain/users.SINGLE_USER_ID`; device, code and token rules → `domain/devices`; restart delay policy → `domain/supervision`; device and pairing-code queries → `storage/devices`; device operations (add, list, revoke, pair, authenticate) → `services/devices`; request authentication and the device cookie → `web/auth`; supervise `rack serve` (restart, logs, single instance) → `ops/supervise`; self-update of a deployed clone → `ops/update`. Reused: `web/errors.wants_page` / `error_response`, `storage/files.atomic_write` (PID file), `db.create_engine`, the log format of `cli.configure_logging`.

### Error handling summary

| Failure | What the user sees | Left on disk |
|---|---|---|
| Wrong / malformed code | form again, « wrong code » message (remaining attempts when known) | one attempt charged to live codes (malformed: nothing) |
| Expired, reused, revoked device's code | form again, "generate a new code" message | nothing |
| Fifth wrong attempt | form again, "too many attempts, generate a new code" | the code is dead |
| Unpaired / revoked / expired cookie, navigation | 303 to `/appairage`, cookie cleared | nothing |
| Same, htmx or JSON request | 401 `not_paired`, `HX-Redirect: /appairage` for htmx | nothing |
| Database error during the auth check | 500 page / JSON `internal` | nothing |
| `rack device add` with a taken name | `rack: error: …`, exit 1 | nothing (transaction rolled back) |
| Server crash | restart after 1, 2, 4… ≤ 300 s, logged | log lines |
| `rack update` step fails | the failing step and its output, exit 1, no restart | git / venv as left by the failed tool; database rolled back by the migration transaction |

## Rejected options

- **Authentication as a FastAPI dependency per router**: allow-by-default; a forgotten dependency on a later router exposes it. The middleware is deny-by-default with an explicit public list.
- **Slow password hash (scrypt / argon2) or HMAC with a server secret**: the token has 256 bits of entropy, so a fast hash is enough and keeps the per-request lookup indexed; the code lives 10 minutes and allows 5 guesses, so a stolen hash is useless by the time it is cracked. A secret would be the first entry of `.env` and one more thing to back up and migrate.
- **Rotating the token on renewal**: a lost response (phone network drop) would lock the device out; renewal only refreshes the cookie lifetime.
- **Writing `last_seen_at` on every request**: one fsync per request for an informational field.
- **Counting attempts per client IP or globally**: IPs behind NAT / DDNS say nothing; a global counter lets anyone lock out pairing permanently. Per issued code, charged to every live code, bounds guesses per code and recovers with a new `rack device add`.
- **Separate refusals for expired and reused codes**: both mean "get a new code"; one outcome, one message.
- **4xx + htmx `responseHandling` for pairing refusals**: would make every 422 swappable, including Pydantic's JSON body, and anticipates L2's general error display; deferred to L2 (D-050).
- **Reissuing a code for an existing device name**: a second way to do what revoke + add already does.
- **Bare PID file for single instance**: a stale PID reused after a reboot would stop the supervisor from starting at boot, the exact case it exists for.
- **Supervisor restarting the child only (no re-exec) on update**: supervisor code would stay old until the next reboot; re-exec costs nothing.
- **Stopping the server before `migrate` in `rack update`**: needs a pause / resume protocol between update and supervisor; the brief's order with a seconds-long window is enough for one user who runs the update himself.
- **`logrotate` / DSM log rotation**: not available or configurable the same way on DSM and Jelastic; stdlib `RotatingFileHandler` needs nothing.
- **Hand-written log rotation through `atomic_write`**: rewriting a log on every line is wrong for append-only files and duplicates the stdlib.
- **`__Host-` cookie prefix**: requires `Secure`, impossible over plain HTTP (D-013); renaming the cookie when HTTPS arrives would unpair every device.

## Impacts

- Decisions appended (none superseded): D-049 device authentication details, D-050 refusals of user input in htmx forms, D-051 supervision and self-update.
- No schema change, no migration (head stays `0002`). No new dependency (`fcntl`, `signal`, `secrets`, `hashlib`, `logging.handlers` are stdlib).
- Docs to update: `docs/architecture.md` (layers row `ops/`, responsibility map, main flows: device cookie in the request flow, `rack update`); `src/rack_overflow/{domain,storage,services,web}/CLAUDE.md` module tables; new `src/rack_overflow/ops/CLAUDE.md`; root `CLAUDE.md` commands (`rack device …`, `rack supervise`, `rack update`); `config.example.toml` comment on `https` (also sets the cookie `Secure` flag); `docs/ui-spec.md` "L1b — Pairing" (ui-designer); new `docs/deployment/nas.md`; `CHANGELOG.md`; `docs/progress.md` (planned stop, user validations).
- Compatibility: every existing page now requires a paired device. Existing tests that request protected pages switch to a paired client fixture; the e2e server pairs its browser context.

## Test plan

- **Unit, domain**: `timestamps` round trip, naive datetime refused; `devices` name validation, `normalise_code` (spaces, hyphens, 7 / 9 digits, letters, non-ASCII digits refused), `format_code`, `hash_secret` (known vector), `judge_match` for each outcome and boundary (`expires_at == now` is expired, attempts 4 / 5), `is_live`, `token_valid` / `needs_renewal` at the boundaries; `supervision.next_delay` (1, 2, 4… capped at 300, reset after 60 s uptime).
- **Integration, services / storage** (migrated temp database, injected `now`): add → code works once, second use `code_expired`; expired at +10 min; wrong code charges the live code and reports remaining attempts; fifth wrong attempt → `too_many_attempts` and the right code is then refused; malformed input charges nothing; a wrong guess with no live code changes nothing; revoked device's code refused; duplicate active name refused, same name allowed after revoke; `authenticate`: valid, unknown, revoked, expired after 400 days, malformed token skips the database, renewal writes `last_seen_at` only after 1 h; token and code never stored in clear (scan the database file bytes for them).
- **CLI**: `device add | list | revoke` output and exit codes, unmigrated database refused, usage errors exit 2.
- **Web (TestClient)**: unpaired `GET /` (navigation) → 303 `/appairage`; unpaired htmx and JSON requests → 401 `not_paired`, `HX-Redirect` only with `HX-Request`; unknown path while unpaired → 303, not 404; `/static/…` and `/appairage` public; pairing POST success sets the cookie (`HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age`, **no** `Secure` with `https = false`, `Secure` with `https = true`) and `HX-Redirect: /`; then `GET /` → 200; each refusal re-renders the form with its message and no cookie; revoke via the service → next request 303 and cookie cleared; renewal re-sends the cookie after 1 h (clock), not before; form-encoded unpaired POST → 415 (security first); security headers on 303 / 401; a route-table test asserts that every registered route except the public list answers 303 / 401 unpaired.
- **ops (no real network, no git / uv)**: `Supervisor` with a fake server (`tests/fixtures/fake_server.py`: prints lines, exits with a given code after a given time, records each start in `tmp_path`): restarts after a crash, recorded delays 1, 2, 4 with a fake `wait`, reset after a long run (fake `monotonic`), log rotation with a small `maxBytes` (files `rack.log.1…` exist, at most `backupCount`), stop terminates the child (and kills one that ignores SIGTERM); single-instance lock refuses a second holder and is free after the holder's process exits; one subprocess test runs `python -m rack_overflow supervise` on a temp config whose child is real `rack serve` on a free loopback port, waits for the log line, sends SIGTERM, expects exit 0 and no orphan. `update` with a fake runner: exact command sequence; refusal off `main` or with local changes; "already up to date" stops before sync; each failing step stops with exit 1 and no SIGHUP; SIGHUP sent to the found supervisor (fake `send_signal`); no supervisor → message, exit 0.
- **Browser** (`tests/e2e/`, Chromium and WebKit × 360 / 1280 px × light / dark): pairing page renders with no external request and no CSP violation; typing a code issued through the service pairs the browser and lands on home; a wrong code shows the message in place; the existing page tests run in a paired context. The `HX-Redirect` on a protected htmx action is checked in L2, the first milestone with one.
- **User validation** (noted in `docs/progress.md`): install from `docs/deployment/nas.md`, reboot the NAS, the app answers on the LAN, the iPhone pairs.

## Commit split (each leaves the tree green; footer `Milestone: L1b`)

1. `feat(auth): add device pairing rules, storage and rack device` — `domain/{timestamps,users,devices}.py`, `storage/devices.py`, `services/devices.py`, CLI `device add | list | revoke` and `_open_current_database`, tests, package `CLAUDE.md` tables.
2. `feat(web): require a paired device and add the pairing page` — `web/auth.py`, middleware order in `app.py`, `errors.py` 401, `routes/pairing.py`, templates, `pages/pairing.css`, `fr.json` keys, `docs/ui-spec.md` L1b section, paired test fixtures, e2e updates, `web/CLAUDE.md`.
3. `feat(ops): add rack supervise with restart delay and log rotation` — `domain/supervision.py`, `ops/` package (`supervise.py`, `errors.py`, `CLAUDE.md`), layering row, CLI `supervise`, fake server fixture and tests.
4. `feat(ops): add rack update` — `ops/update.py`, CLI `update`, tests with the fake runner.
5. `docs(deployment): add the NAS install and update guide` — `docs/deployment/nas.md`, `config.example.toml` comment.
6. `docs(docs): close milestone L1b` — `docs/architecture.md`, root `CLAUDE.md` commands, `CHANGELOG.md`, `docs/progress.md` (planned stop, user validations), `docs/roadmap.md` notes if any.

## UI design

Status: APPROVED FOR AUTONOMOUS MODE. Every user-visible behaviour is set by the brief (sections 4, 6 L1b), D-040, D-049 and D-050; the choices below are presentation only. Full specification, wireframes and strings: `docs/ui-spec.md`, "L1b — Pairing" (canonical; this section summarises it for the developer).

**Task and decision.** Once per device, type the 8-digit code printed by `rack device add` and send it. The user needs: what to type and where it comes from, whether it worked, what to do when it did not. Frequent path: open the URL, tap the field, type 8 digits on the numeric keypad, tap « Appairer », land on home. No confirmation (nothing irreversible).

**Layout.** One column at 360 and 1280 px: h1 « Appairer cet appareil », intro, then the form (max 24rem): label, large input, error (when any), hint, primary button. At 360 px input and button are full width; at 1280 px the column sits left in the 72rem main, as on every page. The submit button sits directly under the input, not in the bottom thumb zone: the iOS numeric keypad has no return key and covers the bottom half, so a bottom button would hide behind it; under the input it stays visible and reachable. The "already paired" state (no keyboard) uses the L1a pair `main--message` + `.actions--thumb`.

```
360 px                         360 px, refusal                360 px, already paired
| Appairer cet appareil  |     | Code d’appairage       |     | Appairer cet appareil  |
| Pour utiliser Rack ... |     | [======== empty =====] |     | Cet appareil est déjà  |
| Code d’appairage       |     | Code incorrect. Essais |     | appairé.               |
| [ 1234 5678          ] |     | restants : 4.          |     |                        |
| 8 chiffres, valable 10 |     | 8 chiffres, valable 10 |     |                        |
| minutes.               |     | minutes.               |     | [ Ouvrir l’application]|
| [      Appairer      ] |     | [      Appairer      ] |     +------------------------+
```

**Components and reuse.** `base.html`, `rendering.render`, `t()`, `.button` / `.button--primary`, `.actions--thumb` + `.main--message`, the `#annonce` live region (filled out of band by the refusal fragment, D-050), `error.html` for a `GET` failure. New: `templates/pairing.html` (page, both states) including `templates/pairing_form.html` (the swapped fragment; also rendered alone by `POST` with the outcome message and the OOB `#annonce`). New reusable CSS in `components.css`: `.field`, `.field__label`, `.input`, `.input[aria-invalid="true"]`, `.field__error`, `.field__hint` (L2 forms reuse them). `pages/pairing.css`: `.pairing-form`, `.input--code` (`--text-2xl`, tabular figures, letter spacing 0.08em). No new token.

**Input.** `id="code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" enterkeyhint="go" maxlength="9" required autofocus spellcheck="false" autocapitalize="off" autocorrect="off"`, `aria-describedby="code-aide"` (or `"code-erreur code-aide"` with `aria-invalid="true"` after a refusal). No `pattern`: the server's `normalise_code` is the one rule; a malformed entry gets « Code incorrect » uncharged. Emptied after every refusal.

**States.** Unpaired form; sending (button disabled through `hx-disabled-elt`); paired (`HX-Redirect: /`, fallback fragment « Cet appareil est appairé. » + « Ouvrir l’application »); wrong code with or without remaining attempts; expired / used / revoked code; too many attempts; already paired; `GET` server error (500 page). `POST` server or network error: no swap in L1b (D-050), button enabled again, typed code kept; L2's general htmx error display (« Non enregistré, réessayer ») must cover this form too. A revoked device's htmx request gets `401` + `HX-Redirect: /appairage` and lands on the unpaired form.

**Keyboard and focus.** Skip link, brand, input, « Appairer »; Enter submits on desktop. Input autofocused on load and after a refusal (same `id`, so htmx keeps it); the refusal message is tied to the input and announced once through `#annonce`. Already paired: no autofocus.

**Strings** (`fr.json`; U+00A0 before « : » and inside « »):

| Key | Text |
|---|---|
| `pairing.title` | Appairer cet appareil |
| `pairing.intro` | Pour utiliser Rack Overflow ici, saisissez le code à 8 chiffres donné par « rack device add » sur le serveur. |
| `pairing.code_label` | Code d’appairage |
| `pairing.code_hint` | 8 chiffres, valable 10 minutes. |
| `pairing.submit` | Appairer |
| `pairing.wrong_code` | Code incorrect. Vérifiez les 8 chiffres et réessayez. |
| `pairing.wrong_code_remaining` | Code incorrect. Essais restants : {remaining}. |
| `pairing.code_expired` | Ce code n’est plus valable. Générez-en un nouveau sur le serveur. |
| `pairing.too_many_attempts` | Trop d’essais : ce code est bloqué. Générez-en un nouveau sur le serveur. |
| `pairing.paired` | Cet appareil est appairé. |
| `pairing.already_paired` | Cet appareil est déjà appairé. |
| `pairing.open_app` | Ouvrir l’application |
| `error.not_paired` | Cet appareil n’est pas appairé. |

**Note for the developer.** A pending device whose code expired or was blocked is still active, so `rack device add <same name>` is refused until `rack device revoke <name>`; the CLI error already says so (`revoke it first`), which is why the page says only « Générez-en un nouveau sur le serveur ». Checks: 360 and 1280 px, light and dark, WebKit numeric keypad, no horizontal scroll, contrast of the danger border on `--color-bg` (6.57 / 8.29).

## Review (reviewer, loop 1)

Checks: 688 passed, 24 skipped (WebKit), 3 xfailed (strict); ruff and format clean; duplicate-code 10.00. Layering holds; middleware order security → errors → auth is correct; static is the only bypass; hashed lookup needs no constant-time compare (D-049); cookie flags match the roadmap; tests were not weakened.

1. **BLOCKING** (duplication) the `python -m rack_overflow <cmd> --config <abs path>` self-invocation is built twice: `cli.py:123` (`_self_command`) and `ops/update.py:85`. One ops helper used by both.
2. **BLOCKING** (partial state) `ops/update.py:81`: if the pull succeeds and `uv sync` or migrate fails, a second `rack update` sees HEAD unchanged, says "already up to date" and never syncs or migrates; the next restart runs new code on old deps or schema, `rack serve` refuses, the supervisor loops. `docs/deployment/nas.md` §11 is wrong in that case. Fix: on unchanged HEAD still run sync + migrate (both idempotent). Record it as a decision refining D-051.
3. **TO FIX** (tester bug 1) `web/auth.py:92,106` append a cleared or renewed old cookie after the new token cookie of `routes/pairing.py:62`: the browser ends with no cookie or the old one and the code is spent. Skip the auth cookie update when the response already sets the device cookie.
4. **TO FIX** (tester bug 2) `ops/update.py:91`: `ProcessLookupError` / `PermissionError` from `os.kill` → traceback. Wrap in `OpsError`, saying the migration was applied.
5. **TO FIX** `ops/supervise.py:102`: `OSError` from `Popen` (e.g. interpreter missing while `uv sync` rebuilds `.venv`) kills the supervisor. Treat it as a failed run and go through the restart delay; same for `os.execv` at `cli.py:159`. Lock open failure (`ops/supervise.py:150-151`) is already correct: add a test.
6. **TO FIX** the "name taken" rule lives in `services/devices.py:72-73` and `storage/devices.py:25` with a duplicated message. Keep the storage guard as the single source (it also catches the race) and let the service translate it.
7. **SUGGESTION** `storage/devices.py:92` `mark_used` and `set_token` update unconditionally: add `used_at IS NULL` / `token_hash IS NULL` and check the row count.

## UI review (ui-designer, loop 1)

Rendered in Chromium at 360 and 1280 px, light and dark, every state: no BLOCKING; strings, keys, input attributes, aria, focus and sizes match the spec.

1. **TO FIX** `static/css/pages/pairing.css:24-28`: the button is full width at 1280 px (stretched by the `.pairing-form` flex column), not the compact button of the wireframe; add `align-self: flex-start` from 40rem.
2. **SUGGESTION** `static/css/components.css:106-108`: the error border goes from 1 to 2 px and shifts the layout by 2 px; keep 1 px and add a 1 px `--color-danger` box-shadow.
3. **For L2** (htmx error display): after a 5xx or network error, focus falls to `<body>` and the previous refusal message and `aria-invalid` stay; L2 must clear them and return focus to the input when it shows « Non enregistré, réessayer » (`templates/pairing_form.html:8-17`).
