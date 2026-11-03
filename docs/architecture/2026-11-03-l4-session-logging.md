# L4 — Session logging (design note)

Status: APPROVED FOR AUTONOMOUS MODE

Every user-visible behaviour is set by the approved brief (§2, §4 speed targets and "no silent loss", §6 L4, §7 storage model, §8 session routes, §11 H records server-side, §11 I double submission), the L4 "Done when" of `docs/roadmap.md`, invariants 7 to 12 and D-015, D-018 to D-021, D-031 to D-035, D-041, D-053 to D-059. This note fixes what they leave open and records it as new decisions D-061 to D-066; none is superseded. One additive Alembic revision `0004` (one index); 0001 to 0003 stay frozen. One dependency is added with a measured reason (`tzdata`, section 7; brief §10 allows it). One optional settings key is added (backward compatible: a NAS `config.toml` without it keeps working). No `/build-roadmap` stop condition applies: no decision is superseded, no released data format changes, no data can be lost, and every choice below either follows a documented rule or is a detail the brief explicitly leaves to the architect (record rule, time-zone source, prefill definition).

## Context

Milestone L4: start a session (empty or from a template, location), pick from menus, add an exercise by search (recent first), prefill sets from the last performance (else the target) and settings from the last session, steppers and discrete values, ✓ with server-side record detection (⭐), set types, optional variables collapsed, layout by category, resume an open session, close with a summary. Done when: a full « Salle A » session is logged in the WebKit browser test at 360 px; the speed targets are counted in that test; set confirmation < 100 ms on one year of simulated history; a failed request keeps the form and shows « Non enregistré, réessayer »; settings and sets are prefilled as specified.

Current state (end of L3): schema head `0003`. `session(user_id, local_date, time_zone, started_at, ended_at, location ∈ {gym, home}, template_id, notes, status ∈ {open, closed}, deleted_at)` with CHECK `status_ended_at` and the partial unique index `uq_session_one_open (user_id) WHERE status = 'open' AND deleted_at IS NULL`; `session_exercise(session_id, exercise_id NOT NULL, template_slot_id, position, notes)` indexed on `session_id` only; `exercise_setting(session_exercise_id, variable_id, value_int | value_text, uq(session_exercise_id, variable_id))`; `set_entry(session_exercise_id, position, type ∈ {warmup, work, rm_test}, reps, weight_g, duration_s, distance_m, completed_at, deleted_at)` indexed on `session_exercise_id`; `set_value(set_entry_id, variable_id, value_int | value_text, uq)`. No session query, service, route or page exists. Reusable: `domain/units` (parse / format / input_text, D-055), `domain/catalog` (`FieldKind`, `FieldParams`, `core_kind`, `variable_kind`, `value_column`, `Problem` / `CatalogError`, `text_input`, `choice_input`), `domain/search.rank(recent=…)` (D-056, recency tie-break built for L4), `domain/templates.Target`, `services/templates` (`SlotView.skipped`, D-058 rule), `storage/exercises` (`fields_of`, `params_of`, `search_candidates`), `storage/positions.next_position`, `storage/db.guarded_write`, `domain/timestamps`, `web/display.Display` (`value`, `input_text`, `target`), `web/forms` (`RowId`, `row_id`, `form_errors`), `_form_status.html`, `request-errors.js` (D-053). `home.html` is the L1a empty state.

## Chosen design

### 0. Schema: revision `0004_session_exercise_exercise_index`

| Change | Why |
|---|---|
| index `ix_session_exercise_exercise_id` on `session_exercise (exercise_id)` | Every per-exercise read of L4 (last performance, last settings, record history, recent exercises) and of L5 starts from an exercise id; without it each one scans `session_exercise`. Additive, `op.create_index`, no table rebuild |

Declared in `schema.py` as `sa.Index(None, "exercise_id")` on `session_exercise` (naming convention gives the name). No other schema change: every L4 fact fits the 0001 columns. If the performance test (section 9) shows another index is needed, it goes into this same 0004 before the milestone's commit (the revision is not released until then); otherwise none is added speculatively.

### 1. Modules

| Unit | New / changed | Owns |
|---|---|---|
| `domain/sessions.py` | new | Session logging rules, pure: `SessionError(DomainError)` with a stable `code`; `local_start(now, tz) -> (local_date_text, tz_name)`; `default_location(last_location)` (`gym` when none); `templates_for(location, templates)` (non-archived, location equal or `both`, template order); `start_plan(slots) -> StartPlan` (D-058: skipped slots dropped, fixed slot → row, menu with one available option → row, other menus pending); `display_sequence(slots, rows)` (section 3); `SetFacts` (type, reps, weight_g, duration_s, distance_m, values by variable id); `prefill(position, today, last, target, fields) -> SetFacts` (section 4); `stepped(kind, params, value, direction)` (section 5); `set_draft(fields, raw_type, raw_values) -> SetFacts` (parse and check one set form through `domain/units` and the field kinds; `CatalogError` per input: `required`, unit codes, `invalid_choice`, `too_long`, `empty_set`); `setting_draft(fields, raw_values)` (same for settings) |
| `domain/indicators.py` | new | Indicators computed from facts (D-021), the module L5 extends (e1RM, max load per rep count): `RECORD_TYPES = ("work", "rm_test")`; `is_record(category, candidate, previous) -> bool` and `records(category, ordered_sets) -> set[index]` (section 6); `volume(category, sets) -> Volume` (section 8); `round_count` for intervals |
| `domain/vocabulary.py` | changed | `SET_TYPES` docstring: warm-ups never count for records or volume; work and RM-test sets do (D-064). No value change |
| `config.py` | changed | Optional section `[calendar]`, key `time_zone` (IANA name, default `Europe/Brussels`), validated once with `zoneinfo.ZoneInfo` at load (unknown zone → `ConfigError`); `Settings.calendar.time_zone` (name) and `Settings.calendar.tz` (the `tzinfo`) (D-065) |
| `storage/sessions.py` | new | Queries on a caller's `Connection`, no rule: `insert_session` (open; the one-open unique index → `SessionOpenError` through `db.guarded_write`), `get_session(user_id, id)` (not deleted), `open_session(user_id)`, `last_location(user_id)`, `close_session(id, ended_at)` (only when open; returns whether written); `insert_session_exercise`, `session_exercises(session_id)` (with exercise name, category, archived), `get_session_exercise(session_id, id)`, `set_session_exercise_exercise(id, exercise_id)`, `has_facts(session_exercise_id)` (any set, deleted included, or setting); sets `insert_set` (position through `positions.next_position`), `insert_set_values`, `sets_of(session_exercise_ids)` (live, with their values), `get_set(user_id, set_id)` (joined to its session; live set, non-deleted session), `update_set`, `replace_set_values`, `soft_delete_set(id, at)`; `last_performance(user_id, exercise_id, except_session_id)` (section 4), `last_settings(user_id, exercise_id, except_session_id)` (latest value per variable), `settings_of(session_exercise_id)`, `upsert_settings`; `record_history(user_id, exercise_id)` (live `work` / `rm_test` sets of non-deleted sessions, ordered by `(completed_at, id)`); `recent_exercise_ids(user_id)` (exercise ids by their latest non-deleted session, newest first) |
| `storage/exercises.py` | unchanged | `fields_of`, `params_of`, `search_candidates` reused |
| `services/sessions.py` | new | One transaction each, `user_id`, `now` and `tz` passed in: `start_page(user_id)` (open session or the start choices: default location, templates with location, `D-061`), `start(user_id, template_id | None, location, now, tz) -> session_id` (section 2), `get_session_view(user_id, session_id, tz) -> SessionView` (rows in display order, each with fields, settings, live sets with ⭐, next-set prefill, pending menus; or the summary when closed), `pick(user_id, session_id, slot_id | None, exercise_id) -> session_exercise_id` (menu pick or added exercise), `change_exercise(...)` (re-pick while the row holds no fact), `search(user_id, session_id, query)` (`domain/search.rank` with `recent`), `set_form(user_id, session_id, session_exercise_id, raw, step)` (stepper: no write), `confirm_set(user_id, session_id, session_exercise_id, raw, now) -> ConfirmedSet` (section 6), `update_set(user_id, set_id, raw)`, `delete_set(user_id, set_id, now)`, `save_settings(user_id, session_id, session_exercise_id, raw)`, `close(user_id, session_id, now)`, `summary(...)` |
| `services/templates.py` | unchanged | `SlotView`, `skipped`, `_slots` reused through a small public reader `slots_for_session(connection, template_id)` (renamed from the private `_slots` and kept the one slot reader) |
| `web/routes/sessions.py` | new | Routes of section 10; thin: Pydantic body → service → render; `CatalogError` → fragment re-rendered `200` (D-050) |
| `web/routes/home.py` | changed | `GET /`: open session → « Reprendre la séance »; else the start form (section 2) |
| `web/display.py` | changed | `Display.local_time(utc_text, tz_name)` (« 18:42 »), `Display.volume(Volume)`; values through `domain/units` |
| `web/templates/` | new / changed | `home.html` (start or resume), `session.html` (page), `session_exercise.html` (one exercise block: settings, sets, set form; the confirm / edit / delete fragment), `session_set_form.html` (stepper fragment), `session_pending_menu.html`, `session_search.html` + `session_search_results.html`, `session_summary.html`, `session_close_confirm.html`; `_nav.html` unchanged (the brand link is home) |
| `web/static/css/pages/session.css` | new | Set rows, steppers, chips, thumb-zone ✓, summary |
| `web/locales/fr.json` | changed | L4 strings, `session.error.*` codes (ui-designer fixes the texts in `docs/ui-spec.md` "L4 — …") |
| `pyproject.toml`, `uv.lock` | changed | `tzdata` (section 7) |
| `config.example.toml` | changed | `[calendar] time_zone = "Europe/Brussels"` documented |

Layering unchanged (`tests/unit/test_layering.py` untouched): the `tzinfo` object is built in `config.py` and passed down; `domain/sessions.local_start` only calls `astimezone` on it.

### 2. Start, resume, close (D-061)

- **Home page = start or resume.** With an open session (`storage.open_session`), home shows one primary « Reprendre la séance » (template name or « Séance libre », local start time, exercise and set counts) and nothing to start: one open session per user (index `uq_session_one_open`). Otherwise home shows the start form: location radios « Salle » / « Maison » preselected from the last non-deleted session's location (else `gym`), then one button per non-archived template whose location is the chosen one or `both`, in template order, and « Séance libre » (empty session). The template filter is a CSS `:has()` switch on the radios (the L2 / L3 pattern, no script, no request). **Taps:** nominal 1 (tap the template), 2 when the location changes; the first set is then 1 tap: within ≤ 3.
- **`POST /seances` `{template_id | "", location}`** → `services.sessions.start`: validates location in `SESSION_LOCATIONS` and that the template is the user's and not archived (`template_unavailable`); writes `session` (`status = open`, `started_at = to_text(now)`, `local_date` and `time_zone` from `local_start(now, tz)`, `template_id`), then one `session_exercise` per row of `start_plan` (fixed slots whose exercise is not archived, menus with exactly one non-archived option; `template_slot_id` set; `position` 0..n-1). Answer: `HX-Redirect: /seances/{id}`. **A session already open** (seen first, or the unique index race through `guarded_write`) is not an error: the answer redirects to the open session. A double tap or a second device therefore lands on the same session (brief §11 I).
- **Resume**: `GET /seances/{id}` of the open session renders the whole state from the database; nothing lives in the browser. A closed session renders its summary; a deleted or foreign one is 404.
- **Close**: « Terminer la séance » at the bottom asks an in-place confirmation (L2 component; reason: closing ends logging in V1, no reopen), then `POST /seances/{id}/cloture` → `status = closed`, `ended_at = now`, `HX-Redirect: /seances/{id}` (summary). Closing an already closed session is a no-op redirect. A session with no set can be closed (it shows an empty summary; deletion of a session is L5, `DELETE /seances/{id}`). Actions on a closed session (confirm, edit, pick…) answer `HX-Redirect: /seances/{id}` instead of writing (`session_closed`), so a second device never writes into a closed session and the user sees why.
- Location is not editable during the session in L4 (L5 corrects sessions).

### 3. Slots, menus and added exercises (D-061)

- `session_exercise.exercise_id` is NOT NULL, so a menu without a choice has no row: it is **pending**, derived at render time from the session's template slots (`slots_for_session`, live, not skipped) that have no row with their `template_slot_id` in this session.
- **Pick** (`POST /seances/{id}/exercices` `{slot_id, exercise_id}`): the exercise must be a non-archived option of that live menu slot of the session's template, and the slot must still be pending (`slot_already_picked`, else `exercise_unavailable`). One tap per menu (the options are buttons). Row appended (`next_position`).
- **Add outside the template** (`{exercise_id}` with no slot): a search block « Ajouter un exercice » on the session page. `GET /seances/{id}/recherche?q=` (fragment) ranks with `domain/search.rank(q, candidates, recent=recent_exercise_ids)`; with an empty query it lists the 20 most recent then the rest by name, so the usual case needs no keyboard; non-archived exercises only. Each result has « Ajouter ». The row has `template_slot_id = NULL`. The same exercise may be added twice (two rows; rare, allowed like the brief's model).
- **Change a pick**: `PATCH /seances/{id}/exercices/{row_id}` `{exercise_id}` while the row holds no fact (no set, deleted included, no setting; `exercise_has_sets` otherwise); for a menu row, the new exercise must be another available option of the same slot; for an added row, any non-archived exercise. A wrong menu tap is corrected without leaving an empty row.
- **Display order** (`domain/sessions.display_sequence`): the template's live slots in their current order, each showing its row(s) or its pending menu card; then every other row (added exercises, rows whose slot was removed) by `position`. History order is `position` (order of addition); the page follows the template so the plan reads top to bottom. Rows without sets stay in the database (they hold no fact) and are ignored by the summary, history and every indicator.
- Archived during the session: rows keep working (the exercise is still logged); new picks and searches never offer archived exercises. Archived variables are hidden and never written (L2 note).

### 4. Prefill (D-062)

- **Last performance** of an exercise, for a session S: the live sets (`deleted_at IS NULL`, every type) of this exercise in the most recent other non-deleted session (by `started_at`, then id) that holds at least one live set of it, ordered by row position then set position. Open or closed does not matter (only S can be open). L5's « dernière performance » uses the same query and definition.
- **Next set** `N` (0-based count of live sets of this row today), `domain/sessions.prefill`:
  - type: last performance set `N`'s type, else today's set `N−1`'s type, else `work`;
  - values: today's set `N−1` when it exists and has the same type (the user's choices of today carry forward: after « + 2,5 kg » on set 2, set 3 is 1 tap); else last performance set `N`; else today's set `N−1` (any type); else **target** parts matching the exercise's fields (reps = `target_reps_min`, duration, distance; D-059) for the first set, and for each field still empty its `exercise_field` default; else empty.
  - measure variables (`set_value`) follow the same source as the core values; values of archived or unlinked variables are dropped.
- **Settings**: per variable, the latest value of that variable for this exercise across the user's other non-deleted sessions (`exercise_setting`), else the field default, else empty. They are written as facts on the row when its first set is confirmed (missing variables only, values recomputed by the server from the same rule, never taken from hidden inputs), or earlier when the user saves them (`PATCH …/reglages`, upsert on the unique `(session_exercise_id, variable_id)`). Changing a setting later updates that row's fact (one fact per row and variable).
- First use of an exercise with no default weight leaves the load empty: the user types it once (keyboard fallback, not the nominal case); from the second session on, the nominal path needs no keyboard.

### 5. Set form, steppers and discrete values (D-063)

- One form per exercise row (the next set): set type radios (« Échauffement » / « Travail » / « Test RM », the last only for `strength`), then the fields in `exercise_field` order: required fields and core quantities visible, **optional variables in a closed `<details>`** whose summary shows their current values. Layout by category (template branches only, no rule): `strength` / `kettlebell` / `bodyweight` « reps × charge », `cardio` « durée / distance », `intervals` « Tour {n} » with the work duration (D-041).
- Every value is an `<input>` prefilled with `Display.input_text` (display units) and parsed by `domain/units.parse` on the server: one parser, one formatter (D-055). Tapping the input opens the keyboard (fallback).
- **Steppers** « − » / « + » for numeric fields with an increment: `hx-get` of `GET /seances/{id}/exercices/{row_id}/serie?…&pas=<field>:<up|down>` with the form's current values (`hx-include`), answered with the re-rendered form; `domain/sessions.stepped` adds or removes the increment (empty + « + » → one increment; never below 0; a value off the grid snaps to the next grid value). A GET: no write, no JSON body rule, idempotent; `hx-sync` replaces a pending step so fast taps never interleave. Why server-side: no JavaScript may hold business or formatting rules (D-015, invariant 2), and the LAN round trip is a few ms.
- **Discrete values** (e.g. 16 / 20 / 24 kg): native radio chips, no request; a stored value not in the list is shown as an extra checked chip.
- `bool` and `enum` fields: native selects / radios; `text`: input (≤ 40 chars).
- **Taps**: unchanged set = ✓ (1); one field changed by one step = « + » then ✓ (2); two fields or two steps = 3; a discrete chip = 1 + ✓.

### 6. Confirm a set and records (D-064)

- `POST /seances/{id}/series` `{session_exercise_id, type, <field values>…}` (variable inputs named `var_<variable_id>`). `services.sessions.confirm_set`, one transaction: session open and the user's (`session_closed` → redirect), row in the session (else 404); `set_draft` (refusal → `200` with the form re-rendered, values kept, messages per input, D-050); insert `set_entry` (`completed_at = now`, position last) and its `set_value` rows; write missing settings (section 4); compute ⭐; answer the row's block: the confirmed set appended (with ⭐ when a record) and the next set's form prefilled. The ✓ has `hx-disabled-elt` (disabled while the request runs); a failure keeps the form values and shows « Non enregistré, réessayer » in the block's slot (D-053, request-errors.js unchanged). No idempotency token (brief §11 I).
- **Edit / delete during the session**: each confirmed set row has « Modifier » (`<details>` with the same fields, `PATCH /series/{id}`) and « Supprimer » (`DELETE /series/{id}`: `deleted_at = now`, soft, no confirmation: the set is kept in the database and can be logged again). The services `update_set` / `delete_set` accept any live set of a non-deleted session of the user, so L5's history correction reuses them; L4 only offers them while the session is open.
- **Record rule** (`domain/indicators`, computed, never stored, D-021): only `work` and `rm_test` sets count (warm-ups never); a set is a record when at least one earlier counted set of the same exercise exists and **no earlier counted set dominates it**: dominates = at least as good on every compared quantity (a tie is not a record). Earlier = `(completed_at, id)` before it, across the user's non-deleted sessions. Compared quantities by category, missing values read as 0:
  - `strength`, `kettlebell`, `bodyweight`: reps, weight, duration, distance, each « more is better ». This one Pareto rule yields L5's indicators: a heavier load at a rep count (strength « max load per rep count »), more reps at a load (kettlebell « reps at a given load »), more reps or more added load (bodyweight), a longer hold (plank).
  - `cardio`: distance « more is better » and speed (distance / duration) « more is better » when both are set; else the single quantity present, « more is better ».
  - `intervals`: the record is per session, not per round: the round that makes this session's count of counted rounds exceed every earlier session's count for the exercise gets ⭐ (L5 main indicator: number of rounds).
  - Variables never enter the rule. The first ever counted set of an exercise is not a record (no star on the first session).
- **Recomputed on every render**: the session page and every block recompute ⭐ for their sets from `record_history` (one query per exercise, ordered), so an edited or deleted earlier set changes later stars, and a reloaded page shows the same stars as the confirmation answer.

### 7. Timestamps and time zone (D-065)

- `started_at`, `ended_at`, `completed_at`, `deleted_at`: UTC through `domain/timestamps.to_text(now)`, `now` from the app's injected clock.
- `session.local_date` (`YYYY-MM-DD`) and `session.time_zone` (IANA name) come from the **configured** zone `[calendar] time_zone` (default `Europe/Brussels`, where the user trains: brief §2), fixed at session start. Local times on pages are the stored UTC shown in the session's stored zone.
- Why not the browser's zone: reading it needs a script (`Intl`) sending it with each start, a fourth script role beyond the ui-spec's allowed list, for a single user who trains in one country; the stored per-session zone keeps history right if the setting changes later.
- `tzdata` dependency, measured reason: `zoneinfo` needs the system zone files or the `tzdata` package; uv's standalone Python ships neither, and DSM's `/usr/share/zoneinfo` is not guaranteed. Without it `ZoneInfo("Europe/Brussels")` can fail on the NAS and `rack serve` would refuse to start. `tzdata` is pure data from the Python core team, no code, no compiled part.

### 8. Summary (D-064)

`GET /seances/{id}` of a closed session: date and local start / end times, duration, then per exercise with at least one live set: name, counted sets (warm-ups listed apart), its volume, ⭐ count; then session totals: exercises, sets, total load volume, records. `domain/indicators.volume(category, sets)` over work and RM-test sets:

| Category | Volume shown |
|---|---|
| `strength`, `kettlebell` | Σ reps × load (kg) |
| `bodyweight` | Σ reps; plus Σ reps × load when weighted; Σ duration for holds |
| `cardio` | Σ distance and Σ duration |
| `intervals` | rounds and Σ work duration (D-041) |

The session total is the sum of load volumes (kg). L5 reuses `volume` as its « volume » secondary indicator.

### 9. Performance target

- Writes per confirmation: one `set_entry`, its `set_value`s, the settings once per row. Reads: session, row, fields, record history (one indexed query per exercise), last performance for the next prefill (index from 0004). All under `BEGIN IMMEDIATE`, one connection.
- **Test** `tests/integration/test_session_performance.py`: a fixture builds one year of simulated history through `storage` inserts in one transaction (4 sessions a week × 52 weeks, 6 exercises × 4 sets each with warm-ups, settings and one measure variable on some exercises: about 5 000 sets, 1 250 rows), then times 30 `POST /seances/{id}/series` through the TestClient (paired, middlewares on) and asserts the **median < 100 ms** and every one < 250 ms (noise margin on a loaded machine). The time includes routing, validation, writes, records, the next prefill and rendering. If it fails, the first remedy is the index or query shape, not caching (D-021: no cache to invalidate).

### 10. Routes (French paths, JSON bodies through `json-enc`, D-034)

Conventions of L2 / L3: pages on navigation, fragments for htmx, refusals `200` with the fragment and the OOB `#annonce`, ids as `RowId` / `row_id`, unknown or foreign ids 404.

| Method and path | Function | Answer |
|---|---|---|
| `GET /` | `home` | page: resume, or start form (location, templates, « Séance libre ») |
| `POST /seances` | `start_session` | `HX-Redirect: /seances/{id}` (also to the already open session) |
| `GET /seances/{id}` | `show_session` | page: open session, or summary when closed |
| `POST /seances/{id}/exercices` | `add_session_exercise` | session exercises fragment (`{slot_id?, exercise_id}`) |
| `PATCH /seances/{id}/exercices/{row_id}` | `change_session_exercise` | the row's block |
| `GET /seances/{id}/recherche` | `search_session_exercises` | results fragment (`?q=`) |
| `GET /seances/{id}/exercices/{row_id}/serie` | `set_form` | the set form (stepped values; `?pas=field:up|down`) |
| `PATCH /seances/{id}/exercices/{row_id}/reglages` | `save_settings` | settings fragment |
| `POST /seances/{id}/series` | `confirm_set` | the row's block (confirmed set + next form) |
| `PATCH /series/{id}` | `update_set` | the row's block |
| `DELETE /series/{id}` | `delete_set` | the row's block |
| `GET /seances/{id}/cloture` | `close_confirm` | in-place confirmation (`?annuler=1` → the block back) |
| `POST /seances/{id}/cloture` | `close_session` | `HX-Redirect: /seances/{id}` |

Every htmx form or action group carries the `_form_status.html` slot (the existing audit test covers the new templates). Every answer on a closed session is `HX-Redirect: /seances/{id}`.

### 11. Error handling

| Failure | User sees | Left in the database |
|---|---|---|
| Invalid set or setting input (unit parse, required empty, empty set, bad type, unknown enum key, text too long) | `200` block re-rendered, values kept, message per input, announced (D-050) | nothing |
| Start while a session is open (double tap, second device, index race) | redirected to the open session | nothing new |
| Archived or foreign template, unavailable menu option, slot already picked, change of a row with facts | `200` fragment with the message | nothing |
| Action on a closed session | `HX-Redirect` to its summary | nothing |
| Unknown, foreign, deleted session / row / set | 404 page or `{"error": "not_found"}` → « Non enregistré, réessayer » | nothing |
| 5xx, network failure, timeout (10 s) | form kept, « Non enregistré, réessayer », focus per D-053; ✓ enabled again | nothing or the whole transaction |
| Unknown `[calendar] time_zone` | `rack serve` / `rack …` exit 1 with `ConfigError` | nothing |

## Rejected options

- **Rows for menus at start with the first option as placeholder**: stores a fact that did not happen (an exercise the user may not do).
- **Pending menus as nullable `exercise_id`**: schema change on a frozen NOT NULL column with a table rebuild, and every reader must handle a row without exercise.
- **Snapshotting the slot order onto rows**: a second copy of the template order; positions as order of addition plus the live template order cover the page, and history needs only the addition order.
- **Client-side steppers (script holding increments and formats)**: duplicates `domain/units` formatting and field rules in JavaScript (invariant 2, D-015).
- **Numeric `<input type="number">` spin buttons**: no spinner on iOS; needs the keyboard.
- **Hidden canonical inputs beside display text**: two values per field that can disagree; one display text parsed by the domain is the L2 / L3 rule.
- **Prefill = always last performance set N**: a change made today (heavier set 2) would revert on set 3, costing taps on every set.
- **Prefill = always today's previous set**: warm-up values would leak into the first work set.
- **Target reps = max of the range**: the range's low end is the minimum to reach; the user steps up when stronger, and last performance takes over from the second session.
- **Settings sent back from hidden inputs at the first set**: the client would be a source of facts the server can compute; the server recomputes them.
- **Record = e1RM above the best e1RM**: needs the formula setting (L5) and ignores kettlebell / bodyweight indicators; the dominance rule needs no formula and is consistent with every L5 table row.
- **Storing a record flag on `set_entry`**: invariant 9; stale after any correction.
- **A star on the first ever set**: every set of a new exercise would be a « record ».
- **Time zone from the browser**: needs a script and a body field on start; see section 7.
- **Time zone from the host OS**: implicit environment read, and the NAS may run in UTC.
- **An idempotency token on confirmation**: brief §11 I.
- **Reopening a closed session**: not in the brief; L5 corrects sets of closed sessions.
- **Physically removing rows without sets at close**: invariant 8 wording covers sessions and sets; rows without facts are harmless and ignored by every reader.

## Impacts

- Decisions appended to `docs/decisions.md` with this note: D-061 (session start, menus, added exercises, order, close), D-062 (last performance and prefill), D-063 (steppers, inputs and taps), D-064 (records and volume), D-065 (time zone and `tzdata`), D-066 (revision 0004 and the reusable set edit services). None superseded.
- Migration `0004` (additive index). `tests/unit/test_cli.py` revision text `0003` → `0004`; the migration test covers upgrade from empty and from `0003` with seeded data.
- Configuration: optional `[calendar] time_zone`; `config.example.toml`, `docs/architecture.md` "Configuration", `docs/deployment/nas.md` (mention of the key, default fits the user).
- Dependency: `tzdata` in `pyproject.toml` and `uv.lock`.
- Docs to update in the milestone: `docs/architecture.md` responsibility map (session rules and prefill → `domain/sessions`; records and volume → `domain/indicators`; session queries → `storage/sessions`; session operations → `services/sessions`; recent exercises → `storage/sessions.recent_exercise_ids`; time zone → `config` / `Settings.calendar`; local time display → `Display.local_time`); package `CLAUDE.md` tables (`domain`, `storage` incl. migrations list, `services`, `web`); `docs/ui-spec.md` L4 sections and the L1a home note; `CHANGELOG.md`; `docs/progress.md` (user validation: a real session at the gym).

## Test plan

- **Unit, domain**: `local_start` (UTC late evening → next local day in Brussels; DST change dates); `default_location`; `templates_for` (both included, archived excluded, order); `start_plan` (fixed, archived fixed skipped, menu with 0 / 1 / 3 available options); `display_sequence` (template order, pending menus, added rows after, row whose slot was removed after); `prefill` (each branch: today same type, last performance N, beyond last performance, target reps_min / duration / distance only for matching fields, field default, empty; warm-up then work sequence; variables); `stepped` (increment up / down, empty start, floor 0, off-grid snap, duration and weight kinds); `set_draft` (each refusal code, enum key, bool, text length, empty set, type not allowed for the category); `indicators.is_record` per category (tie, strictly better on one quantity, dominated, warm-up ignored, first set, cardio speed, intervals per-session count); `volume` per category.
- **Integration, services / storage** (seeded `migrated_engine`): start from « Salle A » (rows for the four fixed slots, pending menus), start while open → same id, index race (monkeypatched) → same id; pick, slot already picked, unavailable option, change pick with / without facts; add by search with recent first; confirm set (set_entry + set_values, settings written once, recomputed not from body); edit, delete (soft), stars recomputed after editing an earlier set; prefill across two sessions (sets and settings, roadmap criterion); closed session refuses writes; foreign / deleted ids → `NotFoundError`; summary volumes; local date and zone stored.
- **Config**: `[calendar]` absent → `Europe/Brussels`; valid zone; unknown zone, wrong type, unknown key → `ConfigError`.
- **Migration**: upgrade from empty and from `0003` (seeded) to `0004`; index present; `foreign_key_check` clean.
- **Performance**: section 9.
- **Web (TestClient, paired)**: each route's page / fragment; JSON only (415); refusals `200` with `aria-invalid` and OOB `#annonce`; closed session → `HX-Redirect`; 404 for foreign ids; `?pas=` stepping; status-slot audit; every `t()` key exists; no inline script / style; home in both states.
- **Browser** (`tests/e2e/`, Chromium and WebKit × 360 / 1280 px × light / dark for the pages; the flow at 360 px in WebKit, also run in Chromium): a `Taps` helper counts every click and fails on any `fill` / `type` / `press` in the nominal path. Scenario (roadmap): a database with one earlier « Salle A » session (history, settings on « Presse à cuisses »): start « Salle A » from home (≤ 3 taps, counted), log every slot (menu picks), each unchanged set in 1 tap, a modified set (« + » then ✓) in ≤ 3 taps, a warm-up set, edit and delete a set, settings prefilled and shown, ⭐ on a heavier set, reload mid-session (resumed), close with confirmation, summary with volume and records. Failure case: the route is made to fail (`page.route` abort) on ✓ → form values kept, « Non enregistré, réessayer », ✓ disabled during the request and enabled after. No external request, no CSP violation, no horizontal scroll at 360 px, targets ≥ 48 px.

## Commit plan (each leaves the tree green; footer `Milestone: L4`)

1. `feat(config): add the calendar time zone setting` — `config.py`, `tzdata` in `pyproject.toml` / `uv.lock`, `config.example.toml`, tests, `docs/architecture.md` "Configuration".
2. `feat(storage): index session exercises by exercise (revision 0004)` — `schema.py`, `migrations/versions/0004_…py`, migration tests, `test_cli` head, `storage/CLAUDE.md`.
3. `feat(domain): add session logging rules` — `domain/sessions.py`, unit tests, `domain/CLAUDE.md`.
4. `feat(domain): add record and volume indicators` — `domain/indicators.py`, `vocabulary.SET_TYPES` docstring, unit tests, `domain/CLAUDE.md`.
5. `feat(services): add session logging operations` — `storage/sessions.py`, `services/sessions.py`, `services/templates.slots_for_session`, integration tests, performance test, `storage/` and `services/` `CLAUDE.md`.
6. `feat(web): add the session logging pages` — `routes/sessions.py`, `routes/home.py`, templates, `Display` additions, `pages/session.css`, `fr.json`, TestClient tests, `docs/ui-spec.md` L4 sections, `web/CLAUDE.md`.
7. `test(e2e): log a full Salle A session with counted taps` — browser flow and page checks.
8. `docs(docs): close milestone L4` — `docs/architecture.md` map, root `CLAUDE.md` if commands change, `CHANGELOG.md`, `docs/progress.md`.

## UI design

Status: APPROVED FOR AUTONOMOUS MODE. Every choice below either applies a rule of the brief (§4 speed targets, « no silent loss »), D-053, D-061 to D-064 and the L1a–L3 ui-spec, or is a presentation detail left to the ui-designer. The full screen specification, every French string and its key, and the tap count table of the browser test are in `docs/ui-spec.md` "L4 — …" (one copy; this section gives the reasons and the deltas the developer must know).

### Task and decision

- **Home** (`GET /`): task « start the right session, or get back to the one running ». Decision: which template (or none), at which place. Information: the place (preselected), the templates of that place in the user's order, which one was done last (the user alternates A / B), or the session already open.
- **Session** (`GET /seances/{id}`): task « log the set I just did, exactly, then the next ». Decision per set: confirm as prefilled, or adjust first. Information: which exercise and set number, the prefilled values, the set type, the machine settings, the sets already done today with ⭐. Every other element (plan, search, close) is secondary and stays out of the way.
- **Summary** (closed session): task « see what I did ». Information: duration, per exercise the counted sets, volume and records, session totals.

### Main layout choice: one current exercise, the rest as a plan

The session page is an ordered plan (`display_sequence`): every item is a one-line card (number, name, target, « Séries : 3 », records) except **the current item, shown expanded in place**: its settings, its sets of today, and the next-set form ending with the large ✓. A pending menu, when current, shows its options as full-width buttons.

- Why: one form on screen means one ✓ on screen, so a set can never be confirmed on the wrong exercise (the main error the brief guards against), and the ✓ sits at a predictable place. Six expanded forms would make a page of ~3 000 px at 360 px where the right ✓ has to be found by scrolling.
- Current item: the query `?exercice={row_id}` or `?menu={slot_id}` when present (and valid), else the row of the latest live set of the session, else the first item. Pure rule, `domain/sessions.current_item(sequence, latest_set_row_id, requested)` (new, beside `display_sequence`; unit tested). Picking, adding or changing an exercise makes that row current.
- Moving between exercises: each card is a plain link `/seances/{id}?exercice={row_id}#exercice-{row_id}` (full page, works without htmx; the anchor scrolls the expanded block to the top of the viewport, above the header). Under the ✓ of the current block, a secondary link « Suivant : {name} » goes to the next item; on the last item it is replaced by « Terminer la séance » (opens the close confirmation at the bottom of the page).
- Rejected: exclusive `<details name>` accordion (open state not known by the server, so a confirmation or reload could re-open the wrong one; `name` needs Safari 17.2); a sticky bottom bar holding the ✓ (covers set rows and the iOS toolbar area, needs a « current » notion anyway, and `position: sticky` inside swapped fragments jumps in WebKit).

### Header and thumb zone at 360 px

The two-row header (97 px) stays, not sticky, as on every protected page (L3). Nothing is fixed at the bottom. The ✓ reaches the thumb zone by scrolling, never by overlay:

- after a page load on an item (link with `#exercice-{row_id}`): the block starts at the top of the viewport, the header is scrolled away; a strength block with no set yet is ~420 px high, so its ✓ lands in the lower half of a 640 px viewport;
- after each confirmation: the swap `hx-swap="outerHTML show:#exercice-{row_id}-actions:bottom"` aligns the block's action bar (✓ and « Suivant ») with the bottom of the viewport; the latest set row and the prefilled form stay visible just above it;
- after a start (`HX-Redirect: /seances/{id}`), the first item is current right under the page title: ✓ at ~560 px of a 640 px viewport.

The ✓ is the one primary button of the block, full width, 56 px high (`calc(var(--target-min) + var(--space-2))`).

### Components and reused helpers

- Status slot (`_form_status.html`) first in: the start form, each set form, each set edit form, the settings form, each menu block, the change-exercise block, the search form (`data-message` = `error.search_failed`), the close block. Field pieces `_fields.html` (`described`, `field_error`, `field_hint`, `oob_announce`). In-place confirmation (L2) for the close. `.rows` / `.row` for plan cards and search results; `.tag` for « Menu », « Archivé », set types and « Record »; `.empty` for empty states; `Display.value` / `input_text` / `target` / `duration_compact`; `LOCATION_KEYS`, `CATEGORY_KEYS`.
- New shared component **choice chips** (`components.css`, `.chips` / `.chip`): a native radio inside its label, the radio visually hidden but focusable, the label a 48 × 48 px minimum chip; checked = accent fill and on-accent text (fill and weight, not hue alone); focus ring on the chip through `:has(:focus-visible)`. Used for the location (home), the set type, discrete values, `bool` and `enum` fields (≤ 12 values; a `<select class="input">` above that).
- New **stepper** (`pages/session.css`, `.stepper`): label above, then `[ − ] [ value ] [ + ]` on one row, buttons 56 × 56, input `--text-2xl` tabular figures centred. Only for numeric fields with an increment; discrete fields get chips; numeric fields with neither get a plain input.
- New `Display` helpers (web): `set_text(set, fields)` (« 8 × 60 kg », « 12 rép. », « 30:00 · 5,2 km », « 0:30 », measures appended « · Résistance 8 »), `local_time(utc_text, tz_name)` (« 18:42 », from the note), `local_date(local_date_text)` (« 03/11/2026 »), `volume(Volume)` (from the note).

### Deltas to sections 2 to 10 (developer)

| Where | Change | Why |
|---|---|---|
| `services.sessions.start_page` | also returns `last_template_id` (template of the latest non-deleted session; same query as `last_location`) | the « Dernière séance » tag on home: the user alternates templates |
| `GET /seances/{id}` | accepts `?exercice={row_id}` / `?menu={slot_id}` (unknown or foreign → ignored, default rule) and `?terminee=1` | current item; closed-session notice |
| closed-session redirects | `HX-Redirect: /seances/{id}?terminee=1` for every write refused with `session_closed`; a plain navigation to a closed session gets no notice | « no silent loss »: the summary says the last action was not saved |
| `GET /seances/{id}/recherche` | result groups « Récents » / « Tous les exercices » when `q` is empty (the service marks which results are recent); `?ligne={row_id}` renders result buttons that change that added row (`PATCH`) instead of adding | the empty query is the no-keyboard path; an added exercise tapped by mistake is corrected in place |
| `POST /seances/{id}/exercices`, `PATCH …/exercices/{row_id}` | answer the plan fragment `#seance-plan` with the new row current | the picked exercise is ready for its first ✓ |
| `PATCH …/reglages` | sent on each `change` of the settings form (no save button) | a setting changed but not saved would be silently replaced by the server's prefill at the first ✓ |
| set form fragment | `session_exercise.html` renders the whole current block; `session_set_form.html` the `<form id="exercice-{row_id}-serie">` alone (stepper answers) | stepper answers replace only the form |
| `services.sessions.close` | the confirmation fragment shows « Exercices sans série : {count}. » (rows without live set + pending menus) when > 0 | a forgotten exercise is seen before the session is final |

### Request, focus and announcement rules

| Action | Request | During the request | Focus after | `#annonce` |
|---|---|---|---|---|
| Start | `POST /seances` (submitter `template_id`) | every start button disabled | new page | — |
| Step « − » / « + » | `GET …/serie` with `name="pas" value="<field>:<up\|down>"`, `hx-include="closest form"`, `hx-target="#exercice-{row}-serie"`, `hx-swap="outerHTML"`, `hx-sync="closest form:replace"` | ✓ disabled (`hx-disabled-elt="#exercice-{row}-valider"`) so a step still running is never confirmed with the old value | same stepper button (stable id `exercice-{row}-{field}-plus` / `-moins`) | — (the value is visible; announcing every step chatters) |
| ✓ | `POST /seances/{id}/series`, `hx-disabled-elt="find button"` on the form | every button of the form disabled (✓ 50 % opacity) | the next form's ✓ (`autofocus`) | « Série 3 enregistrée : 8 × 62,5 kg. » (+ « Nouveau record. ») |
| ✓ refused | same | — | first invalid input | first message |
| ✓ failed (5xx, network, 10 s) | — | — | D-053: first visible field of the form (the first set-type chip); the ✓ enabled again, values kept, « Non enregistré, réessayer » above the form | same text |
| Pick an option | `POST …/exercices` | that menu's option buttons disabled | the new block's ✓ | « Exercice choisi : {name}. » |
| Add from search | `POST …/exercices` | the tapped result disabled | the new block's ✓ | « Exercice ajouté : {name}. » |
| Edit a set | `PATCH /series/{id}` | that form's buttons disabled | that row's « Modifier » | « Série 2 modifiée. » |
| Delete a set | `DELETE /series/{id}` | same | next row's « Modifier », else the previous row's, else the ✓ | « Série 2 supprimée. » |
| Change a setting | `PATCH …/reglages` on `change` | — | kept on the chip / input (same ids) | « Réglages enregistrés. » |
| Close | `GET` / `POST …/cloture` | buttons disabled | « Annuler » in the confirmation; then the summary page | — |

Keyboard order on the session page: skip link, brand, nav, h1, the plan in order (cards are links; inside the current block: « Changer d’exercice » when offered, the settings summary, each set's « Modifier », the set-type chips (one tab stop, arrows inside), each field (−, input, +), « Autres valeurs », ✓, « Suivant »), « Ajouter un exercice », « Terminer la séance ». Enter in a field submits the set form (= ✓) on desktop.

### Style changes

No new token, no new breakpoint. `components.css`: `.chips`, `.chip`. New `pages/session.css` (session page and summary) and `pages/home.css` rewritten (start and resume; L1a empty-state classes removed). Session pages also link `pages/catalog.css` (`.empty`, search). At 1280 px the home and session pages are one column of `--text-max` (logging on the desktop is rare; the same DOM serves both), the summary totals are four tiles on one row.
