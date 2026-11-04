# Build progress

Maintained by the `/build-roadmap` skill. Branch: the session's designated branch (it plays the role of `dev`). One row per milestone of `docs/roadmap.md`. Status: `todo`, `in progress`, `done`, `BLOCKED`.

| Milestone | Status | Commit | Notes |
|---|---|---|---|
| B0 Bootstrap | done | 45ef5e4 | Package `rack_overflow`, CLI `rack`; approved brief, roadmap, decisions D-012 to D-043; hooks checked (secret read and push on `main` blocked, formatter runs); 52 tests, ruff and duplicate-code green locally. Commit on `main` not tried live; the hook code checks it like push, but `tests/unit/test_guard_paths.py` covers only the push case. |
| L1a Technical foundation | done | fabc6ed | Built: settings file, schema and migrations (head `0002`), `rack migrate`, `rack backup` and daily backup, web base and security middleware, `rack serve`, isolation guard, Playwright set-up; `hello` removed.<br>Tests: 447 passed, 12 WebKit skipped (WebKit not installed in the build environment; to be run where WebKit is available, `RACK_REQUIRE_BROWSER=1`).<br>Open: brand / content alignment and htmx error display decided in L2; the integrity check opens the source database read-write by design. |
| L1b Auth and NAS deployment | done | c98c89e | Planned stop: user validation on the NAS pending (below).<br>Built: `rack device add / list / revoke`, pairing page and device cookie (every route except pairing and static), `rack supervise`, `rack update` (D-052), NAS guide `docs/deployment/nas.md`.<br>Tests: 708 passed, 32 WebKit skipped.<br>Open: a SIGTERM arriving between two supervise iterations after a failed re-exec is lost (`cli.py` `run_supervise`); htmx error display and focus after a network error on the pairing form go to L2; WebKit run pending. |
| L2 Catalog | done | 4872532 | Built: variables, exercises, fields, aliases, fuzzy search, seed of 41 exercises in `rack migrate` (D-057), catalog navigation, htmx error display (D-053).<br>Tests: 1477 passed, 116 WebKit skipped.<br>Open: WebKit run pending; existing enum values cannot be reordered in L2 (new values go last). |
| L3 Templates | done | fb545d1 | Built: session templates with blocs (exercise or menu), targets, archive, reordering; migration `0003`; seed of the four templates with seed keys (D-058 to D-060); « Séances types » nav, ids beyond int64 → 404.<br>Tests: 1921 passed, 156 WebKit skipped.<br>Open: WebKit run pending; on a full-menu or full-template refusal the limit text (« … au plus ») is shown and read twice (muted line + error) (`session_template_slot_form.html`, `session_template_slots.html`). |
| L4 Session logging | done | f4bdfb3 | Built: start or resume from home, session page (plan, menus, search recent first), prefill, server steppers, choice chips, settings saved on change, set types, edit / delete sets, records (⭐) and volume computed, close and summary; `[calendar] time_zone` and `tzdata`; migration `0004` (D-061 to D-066).<br>Tests: 2249 passed, 164 WebKit skipped; tap counts checked on Chromium; set confirmation median ≈ 15–20 ms.<br>Open: WebKit run pending, including a check for CSP messages on swaps; the « Autres valeurs » chevron not seen live in the Salle A flow. |
| L5 Tracking | done | 1a472d6 | Built: history by month with the weekly chart, closed-session corrections, session soft delete; progress per exercise (last performance, records, Chart.js 4.6.1 chart and data table), RM measured or estimated with five formulas and `/reglages`; three-row phone header; no migration (D-067 to D-071).<br>Tests: 2639 passed, 176 WebKit skipped.<br>Open: WebKit run pending; kg values above 999 have no thousands separator (no ui-spec rule). |
| L6 Operations and release 1.0.0 | done | ac4dd90 | Built: JSON / CSV export (`rack export`, « Réglages » → « Données »), `rack restore` with the server stopped, Jelastic and NAS ↔ Jelastic guides, every form button disabled during a request, retry link keeps the query (D-072 to D-076).<br>Tests: 2847 passed, 177 WebKit skipped.<br>Open: WebKit run pending; release 1.0.0 pending the user's check (planned stop). |

## Follow-ups

None.

## User validations pending

- L1a: run the browser tests on WebKit (`RACK_REQUIRE_BROWSER=1 uv run pytest -q tests/e2e` on a machine with WebKit installed); only Chromium ran in the build environment.
- L1b: install on the NAS following `docs/deployment/nas.md`.
- L1b: reboot the NAS; the app answers on the LAN.
- L1b: the iPhone pairs (`rack device add iPhone`, code typed in Safari).
- L2: browse the catalog on the iPhone (exercises, search, variables).
- L3: check the four seed templates (Salle A, Salle B, Maison, Cardio) on the iPhone.
- L4: log a real session at the gym on the iPhone.
- L5: check the history and progress pages (chart, RM, corrections) on the iPhone.
- L6: download both exports from « Réglages » → « Données » (iPhone and desktop) and open them.
- L6: run a restore drill on the NAS following `docs/deployment/nas.md` section 13.

## Blocking question

None.
