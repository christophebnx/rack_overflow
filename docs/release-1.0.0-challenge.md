# Rack Overflow — V1 pre-brief challenge

Status: **awaiting the user's answers** (section C). Written by Claude Code on 2026-11-03 after reading this repository (template, agents, skills) and the Equinox Management repository (findings in the appendix of `docs/release-1.0.0-brief.md`). Nothing has been built yet.

Once the user answers section C, the next step is to rewrite `docs/release-1.0.0-brief.md` as the approved release brief, and to write `docs/roadmap.md`, `docs/decisions.md`, `docs/architecture.md` and `docs/ui-spec.md` in one `docs` commit, then run B0 and the milestones through `/build-roadmap`.

## Resume in a new session

1. Read `CLAUDE.md`, `docs/release-1.0.0-brief.md` (pre-brief + Equinox appendix) and this file.
2. Show the user the questions of section C that are still open; do not start building before they are answered.
3. Work on the session's designated branch (it plays the role of `dev`); the user merges into `main` through a pull request.

---

## A. Adapting the brief to this repository's protocol

1. **The repository is still the template.** Start with B0 (`/init-project`): package `rack_overflow`, CLI `rack`, `TODO(project)` markers filled from the brief. Keep the `ui-designer` agent (there is a UI).
2. **Decision numbers collide.** The template already uses D-001 to D-011 (tooling, layering, Claude workflow). The brief's D-001 to D-019 are renumbered from D-012, with a mapping table in the brief. Some already exist: Python and uv (template D-001), English for code and user language for the UI (template D-011).
3. **Documents to produce**, in the Equinox format (appendix A.9 of the brief):
   - `docs/release-1.0.0-brief.md`: the brief, adapted, with "Approvals for the unattended run" and "Settled open points". It is the source that lets `/build-roadmap` run without stopping.
   - `docs/roadmap.md`: milestones L0 to L6, whose ids are used in the `Milestone:` commit footer.
   - `docs/architecture.md`, `docs/decisions.md`, and a new `docs/ui-spec.md` (tokens, 360 / 1280 px, light / dark, 48 px targets).
4. **Branch.** CLAUDE.md says `dev`; cloud sessions push to a designated branch, which plays the role of `dev`. The user merges into `main` through a pull request.
5. **Milestone split**, so each `/feature` run stays reviewable and testable:
   - **L1a**: app, config, database, migrations, CI, Playwright.
   - **L1b**: per-device auth, NAS deployment. Contains manual steps by the user, so a planned stop.
   - **L4a**: server pack + outbox, idempotency.
   - **L4b**: session screen.
6. **L2/L3 in parallel with L4 (point 11.5): no.** `/build-roadmap` is sequential on one branch, and L4 needs the catalog schema (L2) and templates (L3) for the pack. Order: B0 → L0 → L1a → L1b → L2 → L3 → L4a → L4b → L5 → L6.

## B. Points of the brief challenged

**B1. Backups come too late.** Real data exists from L4, but backup only arrives in L6. Move the daily backup (`VACUUM INTO`, 30-day retention) and `rack backup` into L1a; it is cheap. Export, documented restore and the Jelastic docs stay in L6.

**B2. Equinox uses neither SQLAlchemy nor Alembic (point 11.1).** It uses raw `sqlite3`, a SQL schema file, `PRAGMA user_version` and `journal_mode = DELETE`. But there SQLite is a projection rebuildable from JSON files. Here the database *is* the source of truth and its schema will evolve with real data. → **Recommendation: keep SQLAlchemy Core + Alembic** (batch mode for SQLite); the difference with Equinox is justified. WAL is right for a server. Consequence: a restore runs with the server stopped.

**B3. Hybrid storage is validated (point 11.2), with four gaps:**
- **Core quantity parameters.** Where do the increment, default and discrete values of `reps` and `weight` live? `exercise_variable` only points to variables. → One link table `exercise_field` referencing either a `variable_id` or a core quantity (CHECK constraint: exactly one of the two). Display order is then shared by both.
- **`decimal` and `enum` types in `set_value`.** → A decimal is stored as an integer with a scale fixed on the variable. An enum is stored by stable key, never by label, so a rename never breaks history.
- **Intervals.** The work / rest ratio has no column, and L5 cannot compute an indicator from variables created in the UI (D-019). → Proposal: 1 set = 1 round, `duration_s` = work time. V1 indicators: number of rounds and total work duration. The ratio is removed from V1.
- **RM stored twice.** An `rm_test` set and `rm_measured` could store the same fact twice. → `rm_measured` is only for manual entry outside a session. `rm_test` sets are read directly. One write per fact.

**B4. "No conflict" is not quite true.** Scenario: the user corrects a set online (L5), then the phone resends the old upsert and overwrites the correction. → Each operation carries an `op_id`, and the server keeps an `applied_op` table: an operation already applied is ignored, not re-applied. Processing is ordered and transactional, with one result per operation.

**B5. The record star risks a double implementation, Python + JS** (invariant 2): the client would need the e1RM formulas. → The pack carries, per exercise, thresholds computed on the server (best load per rep count, best reps at a given load…). The JavaScript only compares with `>`, no formula.

**B6. UUID v7 brings little.** Order already comes from the `order` and `completed_at` columns. Python 3.12 has no `uuid7`, and Safari only exposes `crypto.randomUUID()` (v4). → Recommendation: native UUID v4, no code to write.

**B7. The L0 spike requires HTTPS on the iPhone.** A service worker only runs over HTTPS, so the spike cannot be tested on `localhost` nor from the cloud. The DSM reverse proxy, certificate and DynDNS must be ready *before* L0. Only the user can do this, as well as the go / no-go on the iPhone. The spike code lives on a throwaway branch; only the report `docs/spikes/l0-report.md` is merged.

**B8. iOS PWA constraints (point 11.3):**
- **Separate cookies.** The installed app has its own cookies, distinct from Safari. The pairing page and the manifest must therefore be public, and pairing happens inside the installed app.
- **No Background Sync on iOS.** The outbox is sent when the app opens, on the `online` event, on `visibilitychange` and after each confirmed set, never while the app is closed.
- **Data eviction.** `navigator.storage.persist()` and the 7-day eviction cap, counted on the app's own use. To measure in L0.
- **Browser tests.** Playwright tests also run in **WebKit**, not only Chromium.

**B9. Auth (point 11.4): `HttpOnly` cookie, no token in IndexedDB.** A token in IndexedDB is readable through XSS. Since sends start from the page, the cookie is enough, and it also works from the service worker (same origin). To add:
- `Origin` check and mandatory `Content-Type: application/json`, as in Equinox (appendix A.5 of the brief);
- pairing code valid 10 minutes, attempt-limited;
- cookie renewed on use;
- on a 401, the outbox is kept and the app shows "pairing required".

**B10. Supervision without Docker (point 11.8).** A DSM boot-up task does not restart the service after a crash, and a systemd unit edited on DSM is overwritten by updates.
- **NAS:** DSM boot-up task launching `rack supervise` (restart with increasing delay, rotating logs).
- **Jelastic:** a Linux / VPS node with a systemd unit (`Restart=on-failure`). The Jelastic "Python" node is WSGI-oriented (Apache / mod_wsgi), a poor fit for an ASGI app like FastAPI.

**B11. Other points:**
- **i18n (point 11.9):** one catalog `locales/fr.json`, as in Equinox (appendix A.6). The API returns stable English error codes, translated by the client. The CLI stays in English (template D-004). The strings must also be available offline (service worker cache or pack).
- **Isolation guard:** port Equinox's (appendix A.3), with loopback bind allowed for Playwright.
- **CI:** the target server is Linux. Proposal: from 3 OS to Ubuntu + macOS, plus a browser job running Chromium and WebKit.
- **`DELETE /api/sessions/{id}`:** a soft delete (`deleted_at`), consistent with "no physical deletion".
- **Manual acceptance:** criteria only checkable on site (NAS reboot, smoothness on iPhone) are marked "user validation" in the roadmap.

## C. Questions for the user

| # | Question | Recommendation | Answer |
|---|---|---|---|
| 1 | Are the DSM reverse proxy, certificate and DynDNS already working? Otherwise L0 waits, or L1a runs first. | — | open |
| 2 | Seeds (point 11.7): does the user supply the real exercise list and the content of "Salle 1", "Salle 2", "Maison", "Cardio bonus", or does Claude Code propose a list (Basic-Fit machines and home equipment) for correction? | — | open |
| 3 | Remove the work / rest ratio of intervals from V1 (B3)? | Yes | open |
| 4 | SQLAlchemy Core + Alembic (B2) and UUID v4 (B6)? | Yes | open |
| 5 | Intermediate tag 0.1.0 after L4b, to use the app at the gym before L5 and L6? | Yes | open |
| 6 | CI on Ubuntu + macOS, without Windows? | Yes | open |
