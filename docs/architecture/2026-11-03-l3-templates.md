# L3 — Session templates as menus (design note)

Status: APPROVED FOR AUTONOMOUS MODE

Every user-visible behaviour is set by the approved brief (§1 item 2, §6 L3, §6.1 templates, §7.2, §8), the L3 "Done when" of `docs/roadmap.md`, invariants 7 to 12 and D-021, D-023, D-034, D-046, D-050, D-053, D-054, D-057. This note fixes what they leave open and records it as new decisions D-058 to D-060 (D-060 refines D-057; none is superseded). One additive Alembic revision `0003` (nullable columns and unique indexes on tables that hold no template data yet); 0001 / 0002 stay frozen; no dependency is added. No stop condition of `/build-roadmap` applies: nothing released is altered, no data can be lost, every new behaviour is the roadmap's.

## Context

Milestone L3: templates as ordered slots (a specific exercise or a menu: label + proposed exercises), optional indicative targets, the template seed of brief §6.1 (Salle A, Salle B, Maison, Cardio). Done when: create « Salle 1 » with a « Tirage » menu slot offering three exercises, reorder slots, archive a template; the four seed templates exist after `rack migrate` on an empty database and a second seed creates no duplicate; template pages pass the browser checks.

**Offline pack.** The original pre-brief criterion "the template appears in the offline pack" does not apply: offline mode, pack and outbox were dropped by D-015 (brief §11 P). The current `docs/roadmap.md` L3 lines already omit it, so no roadmap edit is needed; L4 reads templates straight from the server.

Current state (end of L2): schema head `0002` holds `template(user_id, name, location, position, archived_at)`, `template_slot(template_id, position, exercise_id | movement_pattern, target_sets, target_reps_min, target_reps_max, target_duration_s, target_distance_m, target_note)` with `one_source` and target CHECKs, `template_slot_option(template_slot_id, exercise_id, position, uq(slot, exercise))`, `session.template_id` and `session_exercise.template_slot_id` FKs. No template query, service, route or page exists. The seed (D-057) has step 1 (41 exercises) and matches exercises by normalised name only; `exercise` has no stable seed identity. Field reordering lives inline in `services/exercises.move_field` + `storage/exercises.set_positions`.

## Chosen design

### 0. Schema: revision `0003_template_slot_deleted_and_seed_keys` (D-058, D-060)

| Change | Why |
|---|---|
| `template_slot.deleted_at TEXT NULL` | Removing a slot is a soft delete: once L4 writes `session_exercise.template_slot_id`, a physical delete would break the FK (no `ON DELETE`, D-046) or rewrite history. One rule from L3 on: removal always sets `deleted_at` (D-058) |
| `exercise.seed_key TEXT NULL` + unique index `uq_exercise_user_id_seed_key (user_id, seed_key)` | Seed templates reference exercises by stable key, not by name, so a seeded exercise the user renamed is still found (D-060). NULL for user-created exercises (several NULLs allowed on SQLite and Postgres) |
| unique index `uq_template_user_id_name (user_id, name)` | Database backstop for template name uniqueness, like `uq(user_id, name)` on `exercise`; the service checks the normalised name first (`guarded_write` turns the race into `name_taken`) |

Unique **indexes** (`op.create_index(..., unique=True)`), not table constraints, so SQLite needs no batch table rebuild; both are declared in `schema.py` as `sa.Index(..., unique=True)`. Columns added with `batch_alter_table` as in 0002. Literal SQL only, no import of `schema` / `domain`. The target columns of 0001 fit (section 3): no change to them. The `template` table is empty on every existing database, so the new unique index cannot fail; `exercise.seed_key` starts NULL everywhere and is filled by the seed (section 5).

### Layering and modules

| Unit | New / changed | Owns |
|---|---|---|
| `domain/ordering.py` | new | `UP`, `DOWN`, `moved(ids, item_id, direction) -> (list[int], int)`: swap with the neighbour, clamp at the ends, new index; invalid direction → `CatalogError(Problem("direction", "invalid_choice"))`. The one reordering rule of fields, templates, slots and options |
| `domain/templates.py` | new | Template rules (D-058, D-059), raising `domain.catalog.CatalogError` with `Problem`s (one problem type for every catalog form, reused by `web/forms.form_errors`): `template_draft(name, location) -> TemplateDraft` (name 1–60 chars stripped, location in `vocabulary.LOCATIONS`), `menu_label(raw)` (1–40 chars stripped), `Target` (frozen: `sets`, `reps_min`, `reps_max`, `duration_s`, `distance_m`, `note`, all optional), `target(sets, reps, duration, distance, note) -> Target` typed in display units (durations / distances through `domain.units.parse`), `check_target(Target)` on canonical values (shared with the seed), `reps_text(min, max)` (input text read back by `target`), limits `MAX_SLOTS = 30`, `MAX_OPTIONS = 12`, `check_option_added(existing_ids, exercise_id)` (`option_taken`, `too_many_options`), `check_option_removed(count)` (`last_option`) |
| `domain/catalog.py` | unchanged | `name_taken` (normalised uniqueness) reused for template names |
| `storage/positions.py` | new | `set_positions(connection, table, ids)`: `position = index` for each id in one statement each. Replaces the body of `storage/exercises.set_positions` (which now calls it), used by templates, slots, options |
| `storage/templates.py` | new | Queries on a caller's `Connection`: templates `insert` / `update` (name taken → `NameTakenError` through `db.guarded_write`), `get(user_id, id)`, `list_all(user_id, include_archived)` (with live slot count), `names(user_id)`, `set_archived(id, at)`, `next_position(user_id)`; slots `slots_of(template_id)` (live only, ordered, joined with the exercise's name and `archived_at`), `get_slot(template_id, slot_id)` (live only), `insert_slot`, `update_slot`, `soft_delete_slot(id, at)`, `next_slot_position`; options `options_of(slot_ids)` (ordered, with exercise name and `archived_at`), `insert_option` (same exercise twice → `NameTakenError`), `delete_option`, `get_option`; `target_of(row) -> Target` / `target_values(Target)` (row ↔ domain) |
| `storage/exercises.py` | changed | `insert(..., seed_key=None)`, `set_seed_key(id, key)`, `ids_by_seed_key(user_id) -> dict[str, int]`, `unkeyed_by_name(user_id) -> dict[str, int]` (normalised name → id, `seed_key IS NULL`), `options(user_id)` (id, name, movement pattern, archived; for selects); `set_positions` delegates to `storage/positions` |
| `storage/seed.py` + `seed_data/templates.json` | changed / new | `load_templates()` like `load_exercises`; `exercises.json` items gain a stable `key` (ASCII slug, e.g. `squat_rack_barre`, `kettlebell_swing`); a unit test checks keys are unique slugs and every template reference exists |
| `services/templates.py` | new | One transaction each, `user_id` passed in: `create(TemplateForm)` (position last), `update`, `set_archived(now | None)` (restore → position last), `move(direction)` (among non-archived templates), `list_templates(include_archived)`, `get_detail` (`TemplateDetail`: template, live slots as `SlotView` with exercise or label + `OptionView`s, archived flags, `Target`; addable exercises (non-archived) and label suggestions = `storage/exercises.movement_patterns`), `add_slot(SlotForm)` (kind `exercise` with `exercise_id`, or `menu` with `label` + first `exercise_id`), `update_slot(SlotForm)` (fixed: exercise; menu: label; both: target), `move_slot`, `remove_slot(now)` (soft), `add_option`, `move_option`, `remove_option`. Unknown or foreign id → `NotFoundError`; an archived or foreign exercise when adding → `exercise_unavailable` problem |
| `services/exercises.py` | changed | `move_field` uses `domain.ordering.moved`; `UP` / `DOWN` re-exported from `domain/ordering` |
| `services/seed.py` | changed | Step 1 writes `seed_key` and adopts a same-name user exercise (sets its key); step 2 = templates (section 5); `seed_catalog` returns `SeedReport(exercises, templates)` |
| `cli.py` | changed | `run_migrate` prints `seeded N exercises` and `seeded M templates` (each only when > 0) |
| `web/routes/session_templates.py` | new | Routes of section 6 (module name avoids confusion with Jinja templates); thin: Pydantic body → service → render; `CatalogError` → fragment re-rendered `200` (D-050) |
| `web/display.py` | changed | `Display.target(Target)` → « 4 × 6–8 », « 3 × 0:30 / 12 · par côté »: the one target text (L4 reuses it); numbers through `domain/units.format` (D-055) |
| `web/templates/` | new / changed | `session_templates.html` (list), `session_template_new.html`, `session_template_form.html` (name / location, create and edit), `session_template.html` (detail), `session_template_slots.html` (slots editor fragment, options editor inside menu slots), `session_template_slot_form.html` (one slot's label / exercise / target in `<details>`), `session_template_archive.html`; `_nav.html` gains « Séances types » (`section = "templates"`) |
| `web/static/css/pages/templates.css` | new | slot rows, option list; reuses `components.css` (`.rows`, `.row`, `.tag`, `.actions--inline`, `.detail`, `.form-status`) and the L2 field-row pattern |
| `web/locales/fr.json` | changed | template strings, `catalog.error.*` new codes, nav label (ui-designer fixes texts in `docs/ui-spec.md` "L3 — …") |

Layering unchanged (`tests/unit/test_layering.py` untouched).

### 1. Templates (D-058)

- **Create**: name (1–60 chars, unique per user after `normalise`, archived included → `name_taken`), location (`gym` « Salle », `home` « Maison », `both` « Salle et maison »; no default, the L4 start screen filters by it). New templates go last. An empty template is allowed (slots are added on its page).
- **Edit** (`PATCH`): name and location.
- **Order among templates**: « Monter » / « Descendre » on the list rows (non-archived only), `domain/ordering.moved` over the non-archived ids, renumbered `0..n-1`; archived templates keep their stale position and are listed apart.
- **Archive / restore**: `archived_at` set / cleared, always allowed, nothing else touched; restore puts the template last. Archived templates leave the list unless « afficher les archivées » is on, are still viewable and editable (like L2 exercises) and are not offered when starting a session (L4). **Never deleted** (invariant 8; `session.template_id` will reference them). No duplicate-template action in L3 (not in the brief).

### 2. Slots and menus (D-058)

- **Kinds**, fixed at creation: **exercise** (`exercise_id`, `movement_pattern` NULL) or **menu** (`movement_pattern` = the user's label, e.g. « Tirage horizontal », `exercise_id` NULL, options in `template_slot_option`). The `one_source` CHECK already enforces it. A fixed slot shows the exercise name; a menu shows its label (the word « Menu » is UI text, not stored). The label is free text with suggestions from the existing movement patterns (`<datalist>`, D-054), stored as typed (it names the menu, not an exercise attribute).
- **Add**: one form: kind (radio), then for an exercise a `<select>` of non-archived exercises; for a menu the label plus its first exercise. A menu therefore never exists empty. At most 30 live slots (`too_many_slots`). New slots go last.
- **Edit**: fixed slot → its exercise (another non-archived exercise); menu → its label; both → target (section 3). Changing kind is not offered: remove and add (rare; avoids a two-table rewrite with history references).
- **Options** of a menu: ordered; add (`<select>` of non-archived exercises not already in the menu; `option_taken` backstop through the unique), move up / down, remove (physical delete of the option row: configuration, not history; history stores `exercise_id` on `session_exercise`). The last option cannot be removed (`last_option`; remove the slot instead). At most 12 options (`too_many_options`). The same exercise may appear in several slots or menus.
- **Order**: « Monter » / « Descendre » buttons (no drag, as L2 fields), `domain/ordering.moved`, live slots renumbered `0..n-1`.
- **Remove a slot** = soft delete: `deleted_at` set, the slot leaves the editor and L4, its options rows stay untouched, remaining live slots are renumbered. Not restorable from the UI (re-add instead) and not confirmed, like L2 field removal. Once L4 exists, past `session_exercise` rows keep pointing to the removed slot, so history can still say which menu an exercise came from. Editing a slot that history references is allowed: history facts are the exercise and its sets, the slot is only provenance.
- **Archived exercises inside slots and menus**: archiving an exercise touches no template row. The template page shows them with the tag « Archivé » and they stay movable / removable; add selects never offer archived exercises. L4 rule recorded now (D-058): at session start archived options are not offered, a fixed slot whose exercise is archived and a menu with no non-archived option are skipped; a menu with exactly one available option is picked automatically. Restoring the exercise brings it back everywhere.

### 3. Indicative targets (D-059)

The 0001 columns fit; their exact meaning is fixed now:

| Column | Meaning | Input (display units) | Rule |
|---|---|---|---|
| `target_sets` | number of sets (rounds for intervals, D-041) | integer | 1–20 |
| `target_reps_min`, `target_reps_max` | reps range; a single value is stored `min = max` | one text input: « 10 », « 8–10 », « 8-10 », « 8 à 10 » | 1–100, min ≤ max, both set or both NULL |
| `target_duration_s` | duration per set | `domain/units` duration (`0:30`, `30`, `30:00`) | > 0, ≤ 24 h |
| `target_distance_m` | distance per set | `domain/units` distance (`400 m`, `5`) | > 0 |
| `target_note` | short free text (« par côté ») | text | ≤ 40 chars, empty → NULL |

Every part is optional and any combination is allowed: a menu mixing a plank (duration) and a crunch (reps) carries both « 30 s » and « 12 » (brief « 3 × 30 s / 12 »); L4 uses the parts that match the chosen exercise's fields (prefill: last performance, else the target, brief §6 L4). No weight target (%1RM targets are V1.x). Problems: `target_sets_range`, `target_reps_format`, `target_reps_range`, `target_reps_order`, plus `domain/units` codes for duration and distance, `text_too_long` for the note. Display: `Display.target` → `sets × parts · note`, parts joined by « / » in the order duration, distance, reps (as the brief writes them); `×` only when sets is set; nothing when the target is empty. Whether durations get a compact target form (« 30 s », « 30 min ») instead of D-055's `m:ss` is the ui-designer's call; if adopted it is a `domain/units` function, not a second conversion.

### 4. Reordering: one implementation

`domain/ordering.moved` + `storage/positions.set_positions` serve exercise fields (refactor, behaviour unchanged, L2 tests keep passing), templates, slots and options. Every move service returns the new index so routes put `autofocus` on the moved row's same button (or the other one at an end), as L2 does.

### 5. Seed step 2: templates (D-060)

- **Seed keys**: each item of `exercises.json` gains `key` (stable ASCII slug, never changed). Step 1 now inserts with `seed_key`; when it skips an item because a user exercise has the same normalised name, it **adopts** that exercise (sets its `seed_key` when NULL), so the templates use the user's own « Planche ».
- **Existing databases at `seed.version = 1`** (L2 already seeded, keys absent): step 2 starts with the same adoption pass for every seed item whose key has no row: the unkeyed exercise with the item's normalised name gets the key. This name match runs once, on databases seeded before keys existed; afterwards, references are by key only (a seeded exercise renamed later is still found). One function `_attach_keys(connection, user_id, items)` serves step 1's skip case and step 2's pass.
- **Data**: `seed_data/templates.json`, a list of `{name, location, slots: [{exercise: key} | {menu: label, options: [key, …]}, target: {sets, reps_min, reps_max, duration_s, distance_m, note}]}` in canonical integers, validated with `template_draft`, `menu_label`, `check_target` (same rules as the UI).
- **Step 2**: for each template, skip it when its normalised name exists for the user (archived included; consistent with D-057); else insert it last with its slots and options. A reference whose key resolves to no exercise (only possible when an L2 user renamed a seeded exercise before L3, so the name match failed) is dropped: a fixed slot without exercise and a menu without any option are not created. Archived referenced exercises are kept (the L4 rule hides them). Step 2 returns the number of templates created; `seed.version` becomes `2`.
- **Content** (brief §6.1; template names are the brief's titles; G gym, H home, B both):

| Template (location) | Slots: exercise, or Menu « label » [options]; target |
|---|---|
| Salle A — Squat & poussée horizontale (G) | Squat au rack (barre) 4 × 6–8 · Développé couché (barre) 4 × 6–8 · Menu « Tirage horizontal » [Rowing barre au rack, Rowing assis machine, Tirage horizontal poulie] 3 × 8–10 · Menu « Jambes unilatéral » [Fentes haltères, Split squat bulgare, Presse à cuisses] 3 × 10 · Curl barre EZ 3 × 10–12 · Menu « Gainage » [Planche, Crunch poulie haute, Relevé de jambes suspendu] 3 × 30 s / 12 |
| Salle B — Charnière & poussée verticale (G) | Soulevé de terre roumain (RDL) 4 × 8 · Développé militaire haltères 4 × 8 · Menu « Tirage vertical » [Tirage vertical poulie, Tractions assistées machine, Tractions] 3 × 8–10 · Développé incliné à la Smith 3 × 8–10 · Menu « Ischios / fessiers » [Leg curl allongé, Hip thrust à la Smith, Extension lombaire] 3 × 10–12 · Menu « Triceps » [Extension triceps poulie, Barre au front EZ, Dips] 3 × 10–12 |
| Maison — Kettlebell, barre EZ, haltères (H) | Kettlebell swing 5 × 15 · Goblet squat kettlebell 4 × 10 · Menu « Poussée » [Pompes, Développé haltères au sol, Développé militaire kettlebell] 3 × 10 · Rowing haltère un bras 3 × 10, note « par côté » · Menu « Bras » [Curl barre EZ, Curl marteau haltères, Barre au front EZ] 3 × 12 · Menu « Gainage » [Planche, Turkish get-up kettlebell] 3 × 30 s / 3, note « par côté » |
| Cardio — Course 30 min (B) | Menu « Cardio » [Course extérieure, Tapis de course, Vélo, Rameur] 1 × 30 min (duration 1800 s; « durée + distance » are the exercises' fields, not a target) |

### 6. Routes (French paths, JSON bodies through `json-enc`, D-034)

Same conventions as L2: pages on navigation, fragments for htmx, refusals `200` with the fragment and the OOB `#annonce` (D-050), unknown or foreign ids `404`, body strings with max lengths parsed by the domain, ids as path integers or `str` body values parsed by the route (a non-integer → 422).

| Method and path | Function | Answer |
|---|---|---|
| `GET /seances-types` (`?archivees=1`) | `list_templates` | page: templates in order (name, location, slot count), move buttons; archived apart |
| `POST /seances-types/{id}/deplacement` | `move_template` | list fragment (`{"direction": "up" | "down"}`) |
| `GET /seances-types/nouvelle` | `new_template` | page: create form |
| `POST /seances-types` | `create_template` | `HX-Redirect` to `/seances-types/{id}` |
| `GET /seances-types/{id}` | `show_template` | page: info form, slots editor, archive block |
| `PATCH /seances-types/{id}` | `update_template` | form fragment |
| `POST` · `DELETE /seances-types/{id}/archive` | `archive_template` · `restore_template` | archive fragment |
| `POST /seances-types/{id}/blocs` | `add_slot` | slots fragment (`{"kind": "exercise" | "menu", "exercise_id", "label"}`) |
| `PATCH /seances-types/{id}/blocs/{slot_id}` | `update_slot` | slots fragment (`exercise_id` or `label`; `sets`, `reps`, `duration`, `distance`, `note`) |
| `POST /seances-types/{id}/blocs/{slot_id}/deplacement` | `move_slot` | slots fragment |
| `DELETE /seances-types/{id}/blocs/{slot_id}` | `remove_slot` | slots fragment (soft delete) |
| `POST /seances-types/{id}/blocs/{slot_id}/options` | `add_option` | slots fragment (`{"exercise_id"}`) |
| `POST /seances-types/{id}/blocs/{slot_id}/options/{option_id}/deplacement` | `move_option` | slots fragment |
| `DELETE /seances-types/{id}/blocs/{slot_id}/options/{option_id}` | `remove_option` | slots fragment |

`blocs` is the path word for slots (short on the phone; the UI word is the ui-designer's). Every htmx form or action group carries the `_form_status.html` slot (the L2 audit test covers the new templates automatically). Navigation: « Séances types » added to `_nav.html`; at 360 px brand + three links exceed the bar, so the existing `flex-wrap` fallback or a shorter layout is decided by the ui-designer (the bottom thumb zone stays reserved for L4).

### 7. Error handling

| Failure | User sees | Left in the database |
|---|---|---|
| Invalid input (name, duplicate name, label, target parts, last option, too many slots / options, option already in the menu, archived exercise picked) | `200` fragment re-rendered, message per input, announced (D-050) | nothing (transaction not started or rolled back) |
| Race on a unique (template name, option) | same as the duplicate message (`NameTakenError` → `name_taken` / `option_taken`) | nothing |
| Unknown, foreign or soft-deleted slot / option / template id | 404 page or `{"error": "not_found"}` → « Non enregistré, réessayer » (D-053) | nothing |
| 5xx, network failure, timeout | form kept, « Non enregistré, réessayer », focus rules of D-053 | nothing or the whole transaction |
| Seed templates invalid or unreadable | `rack migrate` exits 1 after the schema upgrade committed; `seed.version` unchanged | schema at `0003`, seed transaction rolled back |

## Rejected options

- **Reference seed exercises by name** (no migration): a seeded exercise renamed by the user between two seed steps is lost, and every future seed step would carry the same fragility. Keys cost one nullable column.
- **Seed keys in `app_setting` as a JSON map**: a second copy of the exercise identity outside the row it describes, stale-able, and invisible to export / restore checks; the column is one fact on its row.
- **Physical delete of a slot when unreferenced, soft delete otherwise**: two paths for one action; L3 would only ever take the first, leaving the second untested until L4.
- **Setting `session_exercise.template_slot_id` to NULL when a slot is removed**: rewrites history (invariant 8).
- **New target columns** (target per field, JSON target, weight target): the five typed columns cover the brief's targets; %1RM / weight targets are V1.x; JSON would hide canonical integers from SQL.
- **Separate « reps min » / « reps max » inputs**: two inputs for one idea on the phone; one text « 8–10 » parsed by the domain is what the user writes and reads.
- **Menu label as a closed movement-pattern list**: D-054 rules it out; menus are named by the user (« Bras », « Ischios / fessiers »).
- **Menus defined by movement pattern only (options computed from exercises with that pattern)**: brief §7.2 lists options explicitly (`template_slot_option`) and §6.1 menus mix patterns (« Bras » = biceps + triceps).
- **Changing a slot's kind in place**: rare; remove and add is clear and avoids rewriting rows history may reference.
- **Duplicate a template**: not in the brief; revisit if the user asks.
- **Drag and drop ordering**: needs script and is hard to make accessible; buttons as in L2.
- **Seeding templates through an Alembic data migration**: D-057 rules it out.
- **A templates-specific error class**: `CatalogError` / `Problem` already carry per-input problems and `web/forms.form_errors` renders them; a second class would duplicate that path.

## Impacts

- Decisions appended to `docs/decisions.md` with this note: D-058 (template, slot and menu rules, slot soft delete), D-059 (target shape), D-060 (seed step 2 and seed keys; refines D-057, which gets a "Refined by" line). None superseded.
- Migration `0003` (additive). `tests/unit/test_cli.py` revision text `0002` → `0003`; the migration test covers upgrade from empty and from `0002` with seeded data (keys NULL, then adopted).
- `rack migrate` on the NAS database (seed version 1): schema to `0003` (pre-migration snapshot, D-045), keys attached by name once, four templates created.
- Docs to update in the milestone: `docs/architecture.md` responsibility map (reordering → `domain/ordering` + `storage/positions`; template rules → `domain/templates`; template queries → `storage/templates`; template operations → `services/templates`; target text → `web/display.Display.target`; seed keys and template seeding → `services/seed`); package `CLAUDE.md` tables (`domain`, `storage` incl. migrations list, `services`, `web`); `docs/ui-spec.md` L3 sections and nav; root `CLAUDE.md` (`rack migrate` seeds exercises and templates); `CHANGELOG.md`; `docs/progress.md`. `docs/roadmap.md` needs no change (no offline criterion left in L3).

## Test plan

- **Unit, domain**: `ordering.moved` (middle, first up, last down, single item, unknown direction); `templates.template_draft` (empty, 60 / 61 chars, bad location); `menu_label`; `target` / `check_target`: each input form of reps (« 10 », « 8–10 », « 8-10 », « 8 à 10 », spaces), min > max, 0, 101, sets 0 / 21, duration and distance through `units` (codes kept), note length, all-empty → empty `Target`, round trip `reps_text`; option checks (`option_taken`, `too_many_options`, `last_option`).
- **Unit, data**: `exercises.json` keys unique ASCII slugs; `templates.json` validates and holds exactly the four templates of §6.1 with their slots, options and targets; every key it references exists.
- **Integration, services / storage** (unseeded `migrated_engine`): roadmap scenario — create « Salle 1 » (gym), add menu « Tirage » with three exercises (first at creation, two added), add a fixed slot, reorder slots and options, archive then restore the template (position last, rows unchanged); name unique case / accent-insensitive including archived; last option refused; archived exercise refused when adding but kept and flagged when archived afterwards; slot removal sets `deleted_at`, leaves options, renumbers, and a `session_exercise` row inserted directly against the removed slot still satisfies `foreign_key_check`; move among non-archived templates; foreign user / other template's slot ids → `NotFoundError`; `NameTakenError` race branches (monkeypatched) for name and option; `move_field` unchanged behaviour (L2 tests).
- **Seed**: `rack migrate` on an empty database → 41 exercises with keys, 4 templates (slots, options, targets as above), `seed.version = 2`; second run creates nothing; a database at version 1 without keys (step 1 only, via `seed_catalog(steps={1: …})`) then full seed → keys attached, 4 templates; a seeded exercise renamed after keys exist is still referenced; a user exercise « planche » is adopted and used by both « Gainage » menus; a pre-existing template named « cardio — course 30 min » is kept, not duplicated; an unresolved key drops the option / slot; invalid template data rolls back the whole seed.
- **Migration**: upgrade from empty and from `0002` (with exercises) to `0003`; `foreign_key_check` clean; columns and unique indexes present; downgrade follows the pattern of 0002.
- **Web (TestClient, paired)**: every route's page / fragment; JSON only (form-encoded → 415); refusals `200` with `aria-invalid` and OOB `#annonce`; 404 for unknown / foreign / soft-deleted ids; invalid direction or kind → 422; slot audit (every htmx action in a `[data-request-status]` scope); every `t()` key exists; no inline script / style; `Display.target` for each §6.1 target.
- **Browser** (`tests/e2e/`, Chromium and WebKit × 360 / 1280 px × light / dark): template list and detail pages (seeded database) with no external request, no CSP violation, no horizontal scroll (longest seed template name, a menu with 12 options); the « Salle 1 » scenario through the UI (create, menu « Tirage » with three exercises, reorder, archive); focus after a move and after a failed move (D-053); nav with three items fits or wraps without scroll at 360 px.

## Commit plan (each leaves the tree green; footer `Milestone: L3`)

1. `refactor(domain): extract reordering for fields and future lists` — `domain/ordering.py`, `storage/positions.py`, `services/exercises.move_field` and `storage/exercises.set_positions` delegating, unit tests, `domain/` and `storage/` `CLAUDE.md`.
2. `feat(storage): add revision 0003 for slot soft delete and seed keys` — `schema.py`, `migrations/versions/0003_…py`, migration tests, `test_cli` revision, `storage/CLAUDE.md`.
3. `feat(domain): add template, menu and target rules` — `domain/templates.py`, unit tests, `domain/CLAUDE.md`.
4. `feat(storage): add template queries and services` — `storage/templates.py`, `storage/exercises` additions, `services/templates.py`, integration tests (roadmap scenario), `storage/` and `services/` `CLAUDE.md`.
5. `feat(storage): seed the four templates of brief 6.1` — `exercises.json` keys, `templates.json`, `storage/seed.load_templates`, `services/seed` (keys, adoption, step 2, `SeedReport`), `cli.run_migrate` output, tests.
6. `feat(web): add the session template pages` — `routes/session_templates.py`, templates, `Display.target`, `_nav.html`, `pages/templates.css`, `fr.json`, TestClient + e2e tests, `docs/ui-spec.md` L3 sections, `web/CLAUDE.md`.
7. `docs(docs): close milestone L3` — `docs/architecture.md`, root `CLAUDE.md`, `CHANGELOG.md`, `docs/progress.md`.

<!-- ui-designer adds a "UI design" section here. -->
