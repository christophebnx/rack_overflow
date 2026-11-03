# Roadmap

V1 (release 1.0.0) as approved in `docs/release-1.0.0-brief.md`, which holds the full content of each milestone; this file holds the order and the acceptance criteria. Run each milestone through `/feature`, or all of them with `/build-roadmap`, on the session's designated branch (it plays the role of `dev`). A milestone is done when its acceptance criteria pass, the definition of done in CLAUDE.md is met (checked locally: no automatic CI, D-012) and its commits follow the git workflow. The branch is pushed at the end of each milestone; the user reviews and merges into `main` through a pull request.

Milestone ids go in the `Milestone:` footer of every commit. Order: **B0 → L1a → L1b → L2 → L3 → L4 → L5 → L6.** Criteria marked *(user validation)* can only be checked by the user on site; the run notes them in `docs/progress.md` and continues.

## B0 — Bootstrap

- Initialise the template: package `rack_overflow`, distribution `rack-overflow`, CLI `rack`; fill the `TODO(project)` markers from the brief.
- `uv sync` (versioned `uv.lock`), `uv run pre-commit install`.
- Check the Claude Code hooks: a read of a secret file is blocked, an edited Python file is formatted, a commit or push on `main` is blocked.
- Write the project docs from the brief: decisions D-014 to D-043, roadmap, architecture overview, `docs/ui-spec.md` global rules.
- Run ruff, duplicate-code and the tests locally. Push, then stop for the user.

Done when: the B0 commits are pushed, local checks pass, the hooks are confirmed working, no `TODO(project)` marker is left.

## L1a — Technical foundation

App factory and `rack serve`; configuration (machine settings file + secrets file, loaded once, passed explicitly); SQLAlchemy Core + Alembic with the full schema of brief section 7 and `rack migrate`; daily backup and `rack backup` (D-037); base layout (Jinja2, vendored htmx + `json-enc`, CSS tokens light / dark, `locales/fr.json`); security middleware (D-034); isolation guard (D-043); Playwright set-up on Chromium and WebKit (D-042). The template `hello` command and `domain/greeting.py` are removed.

Done when:
- `rack migrate` creates the database from scratch and is idempotent; a migration test runs upgrade from empty on a temp database.
- `rack serve` serves the home page; it renders at 360 and 1280 px, light and dark, in Chromium and WebKit, with no external resource and no inline script or style.
- A non-GET request without `Content-Type: application/json` gets `415`; a foreign `Origin` gets `403`; a wrong `Host` is refused; the security headers are on every response.
- `rack backup` writes a dated, consistent copy; retention keeps 30; a corrupt database is never backed up nor deleted.
- The isolation guard fails a test that writes under the real home, reads a secret file or opens a non-loopback connection.

## L1b — Per-device authentication and NAS deployment

`rack device add | list | revoke`, pairing page, hashed token cookie (D-040); every route except pairing and static assets requires a paired device; `rack supervise` (D-038); `rack update`; NAS install docs (LAN only during development, D-013).

Done when:
- An unpaired browser is redirected to the pairing page; a valid code pairs it once; an expired, reused or wrong code is refused; attempts are limited.
- A revoked device loses access on its next request.
- The cookie is `HttpOnly`, `SameSite=Strict`, and `Secure` only when `[server] https = true`.
- `rack supervise` restarts a crashed server with an increasing delay and rotates logs (tested with a fake server process).
- *(user validation)* Installed on the NAS from the docs; after a NAS reboot the app answers on the LAN; the iPhone pairs.

**Planned stop** at the end of L1b for the user validation.

## L2 — Catalog: exercises and variables

Variables (shared, created in the UI), exercises, `exercise_field` (D-031), aliases, fuzzy search, exercise seed of brief section 6.1.

Done when:
- Create a « Siège » setting variable (enum 1–10) in the UI and link it to « Presse à cuisses » and « Développé couché machine », with no schema migration.
- Create « Kettlebell swing » with discrete loads 16 / 20 / 24 kg; create « Vélo » with duration and distance plus a « Résistance » measure variable created in the UI.
- An unused variable can be archived; a variable linked to exercises with history cannot be deleted; archiving an exercise with history deletes no data.
- « Développé couché » is found by typing « DC », « bench » or « developpe ».
- Catalog pages pass the browser checks (360 / 1280 px, light / dark, Chromium / WebKit).

## L3 — Session templates (menus)

Templates as ordered slots (exercise or menu), indicative targets, template seed of brief section 6.1 (Salle A, Salle B, Maison, Cardio).

Done when:
- Create « Salle 1 » with a « Tirage » menu slot offering three exercises; reorder slots; archive a template.
- The four seed templates exist after `rack migrate` on an empty database, and seeding twice creates no duplicate.
- Template pages pass the browser checks.

## L4 — Session logging

Start a session (empty or from a template), pick from menus, add an exercise by search, prefill sets and settings, steppers and discrete values, ✓ with server-side record detection, set types, optional variables collapsed, layout by category, resume an open session, close with a summary.

Done when:
- A full session from « Salle A » is logged in the browser test, at 360 px in WebKit.
- Speed targets (brief section 4): an unchanged set is confirmed in 1 tap, a modified set in ≤ 3 taps, a session starts from a template in ≤ 3 taps, no keyboard in the nominal path (counted in the browser test).
- Server handling of a set confirmation < 100 ms on a database with one year of simulated history.
- A failed request keeps the form values and shows « Non enregistré, réessayer »; the button is disabled while its request runs.
- Settings are prefilled from the last session with the same exercise; sets from its last performance, else the target.
- *(user validation)* A real session at the gym on the iPhone.

## L5 — Minimal tracking

History (list, detail, correction, soft delete), per-exercise last performance, records and chart, indicators by category, RM measured / estimated with selectable formula, sessions per week.

Done when:
- Changing the formula recomputes estimates without touching measured RMs.
- A measured RM wins over an estimate on display; an estimate above an older test is flagged.
- Warm-up sets and sets above 12 reps are excluded from estimation.
- A corrected set changes the indicators; a deleted session disappears from history and indicators but stays in the database.
- Charts render in < 1 s with one year of simulated history.

## L6 — Operations and release 1.0.0

JSON and CSV export (UI and `rack export`), `rack restore`, NAS and Jelastic install and update docs, NAS ↔ Jelastic migration docs, release 1.0.0.

Done when:
- Restoring a backup on a blank instance yields identical data (test).
- The export contains every stored fact and re-reads without loss (test).
- The Jelastic docs put the database on the node's local disk, never a network volume.
- `CHANGELOG.md` has the 1.0.0 entry and a local annotated tag `v1.0.0` exists (`/release`).
