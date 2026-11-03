# Rack Overflow — V1 pre-brief challenge

Status: **closed on 2026-11-03.** History of how the pre-brief became the approved brief. Every point is settled in `docs/release-1.0.0-brief.md` (sections 10 and 11) and recorded in `docs/decisions.md` (D-012 to D-043); where this file and the brief differ, the brief wins. Section D (scope change) supersedes the points of sections A to C that it names; section E holds the user's answers.

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

## C. Questions for the user (superseded by section E)

| # | Question | Recommendation | Answer |
|---|---|---|---|
| 1 | Are the DSM reverse proxy, certificate and DynDNS already working? | Only DDNS + port forwarding. **User decision (2026-11-03): no reverse proxy and no HTTPS in V1**; single user, unadvertised app; transport security is deferred to V2. See section F.1 and D-013. |
| 2 | Seeds (point 11.7): does the user supply the real exercise list and the content of "Salle 1", "Salle 2", "Maison", "Cardio bonus", or does Claude Code propose a list (Basic-Fit machines and home equipment) for correction? | — | open |
| 3 | Remove the work / rest ratio of intervals from V1 (B3)? | Yes | open |
| 4 | SQLAlchemy Core + Alembic (B2) and UUID v4 (B6)? | Yes | open |
| 5 | Intermediate tag 0.1.0 after L4b, to use the app at the gym before L5 and L6? | Yes | open |
| 6 | CI on Ubuntu + macOS, without Windows? | Yes | open |

## D. Scope change (user decision, 2026-11-03)

**V1 is a responsive web application, server-rendered with FastAPI + htmx. No PWA, no separate mobile app, no offline mode.** The same pages serve the iPhone (360 px) and the desktop (1280 px). Goal: simplify V1. The network at the gym (Basic-Fit Overijse) is reliable, so offline is not needed now. Offline is deferred to a later release, possibly as a mobile app talking to the FastAPI server: V1 keeps business logic in a service layer so a JSON API for such a client can be added without rewriting it, and builds nothing else for it.

### D.1 Removed from V1

- **L0 (offline spike)**: removed entirely.
- Manifest, service worker, IndexedDB (pre-brief 7.3), read-only pack, outbox, `GET /api/pack`, `POST /api/outbox`.
- Pre-brief decisions **D-002** (web + PWA), **D-003** (offline limited to the session screen) and **D-004** (pack + outbox keyed by UUID v7) are dropped; D-002 is replaced by the decision above.
- Requirement "the session screen works without network" and "set confirmation never waits for the network".
- Challenge points now obsolete: **A.5** split of L4 into L4a / L4b, **B5** (record thresholds in the pack: the server renders the star, no JS formula), **B6** (no client-generated id), **B7** (HTTPS no longer blocks a spike), **B8** (iOS PWA constraints), and the offline part of **B11** (strings cached offline).

### D.2 Consequences on what stays

- **Front end**: Jinja2 templates rendered by FastAPI, htmx for partial updates (fragments swapped in place). htmx and Chart.js are vendored under `static/` at a pinned version (no external resource). JavaScript is limited to htmx configuration and charts. Equinox appendix A.7 is reused for CSS (tokens, base, components) and accessibility rules, not for its ES-module client architecture.
- **Strings (A.6 adapted)**: one flat catalog `locales/fr.json`, resolved **server-side** in templates; no `GET /api/locale`, no `i18n.js`.
- **Routes**: HTML routes returning full pages or htmx fragments replace most of the JSON API sketch (pre-brief section 8). JSON stays only where a consumer needs it: chart data (L5) and export (L6). Business logic lives in a service layer under the routes, so a JSON API (or the V2 AI module) can be added without rewriting it.
- **Security (A.5 kept)**: the Equinox rules apply unchanged. htmx sends its requests as JSON through the vendored `json-enc` extension, enabled once on `<body>`, so every request other than GET/HEAD must carry `Content-Type: application/json` (`415` otherwise). Why it matters: a cross-site page can submit a plain HTML form (form-encoded) without any check by the browser, but a JSON request from another origin triggers a CORS preflight, which this server never answers; together with the `Origin` / `Sec-Fetch-Site` check and the `SameSite=Strict` `HttpOnly` cookie, this is the CSRF defence. Also kept: `Host` check, CSP `script-src 'self'` (htmx configured with `includeIndicatorStyles: false` so it injects no inline style). Consequence: form values arrive as JSON strings and are parsed by Pydantic; a future file upload (Excel import, V1.x) will need its own documented exception.
- **Double submission (B4 reduced)**: the button is disabled while its request runs (`hx-disabled-elt`), which prevents a double tap. On an error the form keeps its values and shows "non enregistré, réessayer"; nothing is lost silently. No idempotency token in V1.
- **Speed targets (pre-brief section 4)**: tap counts kept (1 tap for an unchanged set, ≤ 3 for a modified set, ≤ 3 to start from a template, no keyboard in the nominal case). "< 100 ms, never waits for the network" becomes: server handling of a set < 100 ms, and the confirmed set is visible as soon as the response arrives.
- **Auth (B9)**: unchanged (per-device pairing, `HttpOnly` cookie, revocable). Simpler now: pairing happens in Safari, no separate cookie jar.
- **Ids**: generated by the server. See question E4.
- **Browser tests**: Playwright with Chromium and WebKit, 360 / 1280 px, light / dark. No offline test.
- **Unchanged**: catalog and variables (L2), templates as menus (L3), tracking (L5), operations (L6), storage model (pre-brief 7.1-7.2, 7.4), B1, B2, B3, B10, deployment on the NAS / Jelastic.

### D.3 New milestone order

B0 → **L1a** (FastAPI app, Jinja2 + htmx layout, config, database, migrations, daily backup, Playwright; no CI, D-012) → **L1b** (per-device auth, NAS deployment; manual steps by the user) → **L2** (catalog) → **L3** (templates) → **L4** (in-session logging, online) → **L5** (tracking) → **L6** (operations).

## E. Questions for the user (answered 2026-11-03)

| # | Question | Answer |
|---|---|---|
| 1 | Are the DSM reverse proxy, certificate and DynDNS already working? | Only DDNS + port forwarding today, no reverse proxy. **HTTPS is required** (the auth cookie is `Secure`; over plain HTTP the pairing code and cookie travel in clear). Recommendation: the DSM built-in reverse proxy + a Let's Encrypt certificate for the DDNS name, forwarding 443 → NAS, and `rack serve` bound to `127.0.0.1`. To set up by the user before the end of L1b (planned stop); not needed before. Alternative rejected: TLS in uvicorn (certificate renewal to script by hand). See section F.1. |
| 2 | Seeds | Claude Code proposes three templates with classic exercises; **proposal in section F.2, awaiting the user's correction**. |
| 3 | Remove the work / rest ratio of intervals from V1? | **Yes, removed.** Intervals indicators: number of rounds and total work duration. |
| 4 | SQLAlchemy Core + Alembic, integer primary keys? | **Yes.** |
| 5 | Intermediate tag 0.1.0 after L4? | **No.** Build the whole V1 (L1a to L6) in one run, one release 1.0.0. |
| 6 | CI? | **No CI until V1 is done** (GitHub minutes cost money). Checks run locally through the tester and reviewer agents and pre-commit. The workflow is kept but runs only on manual dispatch. After V1, a minimal CI is designed. Recorded as D-012 in `docs/decisions.md`. B0's "CI green" criterion is replaced by "checks green locally". |

## F. Follow-ups of the answers

### F.1 Plain HTTP in V1 (user decision, 2026-11-03)

- **During development (L1a to L6): LAN only, no WAN exposure.** No port forwarding; the app is reached on the local network only.
- **Once in use**: `rack serve` listens on a high, non-standard port (configured, e.g. 40000-65000), forwarded through the DDNS; no reverse proxy, no certificate. A non-standard port cuts automated noise but does not hide the app from a full port scan, so the protections below stay.
- **Accepted risk**: traffic (pairing code, session cookie, training data) travels in clear, and the app is reachable by anyone who finds the address. The user accepts it for V1.
- **Kept, because it costs little and the app is on the internet**: per-device pairing and the `HttpOnly`, `SameSite=Strict` cookie, the `Origin` / `Sec-Fetch-Site` check and the JSON-only rule (A.5). Without them, anyone reaching the port could write data.
- The cookie `Secure` flag and HSTS are driven by configuration (`[server] https = false` in V1), so turning HTTPS on in V2 is a configuration change, not a code change.
- The `Host` check uses the configured DDNS host name.
- Option for later, noted only: a VPN such as Tailscale would encrypt traffic and remove the port forwarding, with no reverse proxy.

### F.2 Seed proposal (awaiting correction)

Exercise names in French as shown in the UI. Seeds carry core quantities only (D-019); targets are indicative. A **menu** slot offers several exercises, chosen during the session.

**Salle A — Squat & poussée horizontale**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Squat | Squat au rack (barre) | 4 × 6–8 |
| 2 | Poussée horizontale | Développé couché (barre) | 4 × 6–8 |
| 3 | Menu Tirage horizontal | Rowing barre au rack · Rowing assis machine · Tirage horizontal poulie | 3 × 8–10 |
| 4 | Menu Jambes unilatéral | Fentes haltères · Split squat bulgare · Presse à cuisses | 3 × 10 |
| 5 | Biceps | Curl barre EZ | 3 × 10–12 |
| 6 | Menu Gainage | Planche · Crunch poulie haute · Relevé de jambes suspendu | 3 × 30 s / 12 |

**Salle B — Charnière & poussée verticale**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Charnière | Soulevé de terre roumain (RDL) | 4 × 8 |
| 2 | Poussée verticale | Développé militaire haltères | 4 × 8 |
| 3 | Menu Tirage vertical | Tirage vertical poulie · Tractions assistées machine · Tractions | 3 × 8–10 |
| 4 | Poussée inclinée | Développé incliné à la Smith | 3 × 8–10 |
| 5 | Menu Ischios / fessiers | Leg curl allongé · Hip thrust à la Smith · Extension lombaire | 3 × 10–12 |
| 6 | Menu Triceps | Extension triceps poulie · Barre au front EZ · Dips | 3 × 10–12 |

**Maison — Kettlebell, barre EZ, haltères**

| # | Slot | Exercise(s) | Target |
|---|---|---|---|
| 1 | Charnière | Kettlebell swing (charges 16 / 20 / 24 kg) | 5 × 15 |
| 2 | Squat | Goblet squat kettlebell | 4 × 10 |
| 3 | Menu Poussée | Pompes · Développé haltères au sol · Développé militaire kettlebell | 3 × 10 |
| 4 | Tirage | Rowing haltère un bras | 3 × 10 / côté |
| 5 | Menu Bras | Curl barre EZ · Curl marteau haltères · Barre au front EZ | 3 × 12 |
| 6 | Menu Gainage | Planche · Turkish get-up kettlebell | 3 × 30 s / 3 par côté |

**Catalog without template** (available through search): Vélo, Tapis de course, Rameur, Elliptique (cardio, duration + distance), Squat à la Smith, Développé couché haltères, Leg extension, Mollets debout machine.

Open points for the user: equipment names as they appear at Basic-Fit Overijse; whether a fourth "Cardio" template is wanted; target ranges.
