# UI specification

Global rules first, then one section per screen. The `ui-designer` agent adds each screen's section during its milestone, with every string in French exactly as shown to the user (and its key in `locales/fr.json`). Source rules: `docs/release-1.0.0-brief.md` section 4, appendix A.7, and decisions D-015, D-027, D-034, D-036.

## Global rules

### Platform

- One responsive web app for phone and desktop, rendered on the server (Jinja2) with htmx for partial updates (D-015). No front-end framework, no build step. JavaScript only for htmx configuration, the shared request-error display (`static/js/request-errors.js`, D-053) and charts (`static/js/progress-chart.js` with the vendored Chart.js, progress page only, L5).
- Checked at **360 px** (iPhone, Safari / WebKit) and **1280 px** (desktop), in **light and dark** following the system (`prefers-color-scheme`). No horizontal scroll at 360 px.
- No external resource: htmx, `json-enc`, Chart.js and fonts are served from `static/`. No inline script or style (CSP, D-034).

### Appearance

- CSS split: `tokens.css` (colours, type scale, spacing, radii, light and dark values), `base.css`, `components.css`, one file per page.
- One accent colour, neutral greys, one type scale; numbers right-aligned with tabular figures.
- System font stack (no font download).

### Touch and speed

- Touch targets **≥ 48 px** in both dimensions, with at least 8 px between adjacent targets.
- Logging path (L4): 1 tap to confirm an unchanged set, ≤ 3 taps for a modified set, ≤ 3 taps to start a session from a template, no keyboard in the nominal case. Steppers and discrete-value chips replace typing.
- Primary actions sit in the thumb zone (bottom half of the screen at 360 px).

### Accessibility (WCAG 2.2 AA, from Equinox)

- Real `<button>`, `<a>`, `<input>` with `<label>`; native elements before custom widgets (`<dialog>`, `<details>`, `<select>`).
- Text contrast ≥ 4.5:1 and control borders ≥ 3:1, in light and dark.
- Visible 3 px focus ring; full keyboard use on desktop.
- Dialogs use `<dialog>` with `aria-modal`; one shared confirmation dialog where, for a destructive choice, the safe answer has focus and Esc means « non ». From L2, a destructive confirmation that needs no script is an **in-place confirmation** instead (L2 — Components): it replaces the action block holding the button that asked for it, the safe answer « Annuler » has focus, and nothing is deleted until the explicit second button. Confirmation only for what cannot be undone (archiving, removing a field or an alias are not confirmed).
- Invalid fields are marked and their message is tied to them (`aria-describedby`).
- Action results are announced once through a permanent live region.

### States and messages

- Every screen designs its empty, loading, error and success states.
- htmx requests disable their trigger while running (`hx-disabled-elt`). A failed request keeps the form values and shows « Non enregistré, réessayer » (key `error.not_saved`) in the form's `[data-request-status]` slot, clears old field errors and returns focus: a trigger outside any `<form>` (row actions: move up / down, remove an alias, delete) keeps it while still in the page; otherwise the form's first visible field gets it, else the trigger (D-053; a field in a closed `<details>` cannot take focus). Placement and look: L2 — Form status.
- Errors from the server carry stable English codes, mapped to French strings by key (D-036). A missing key shows the key itself.

### Language and units

- French only (D-027), from `locales/fr.json`; no French text in templates or code.
- Units shown: kg, km, m, durations as `m:ss` or `h:mm:ss` (D-029). Decimal separator: comma. Exception from L3: indicative targets show durations in a compact form (« 30 s », « 30 min », L3 — Target text); inputs stay `m:ss`.

## Screens

Added by milestone: L1a (base layout, home, error pages), L1b (pairing), L2 (variables, exercises, search), L3 (templates), L4 (session), L5 (history, progress, RM), L6 (export).

### L1a — Tokens (`static/css/tokens.css`)

Light values on `:root` (with `color-scheme: light dark`), dark values under `@media (prefers-color-scheme: dark)`. Later screens use these tokens only; a new token is added here first.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--color-bg` | `#ffffff` | `#131518` | page background |
| `--color-surface` | `#f3f4f6` | `#1e2126` | header, raised blocks |
| `--color-text` | `#1b1d21` | `#e9ebee` | body text |
| `--color-muted` | `#565c66` | `#a6acb6` | secondary text |
| `--color-border` | `#767d88` | `#7f8792` | control borders |
| `--color-divider` | `#d5d8dd` | `#33373e` | decorative separators only (carry no meaning) |
| `--color-accent` | `#0b57b8` | `#7cb0ff` | the one accent: links, primary button, current item |
| `--color-on-accent` | `#ffffff` | `#0d1726` | text on accent |
| `--color-danger` | `#b42318` | `#ff8f84` | error text and invalid field border |
| `--color-focus` | `#0b57b8` | `#7cb0ff` | 3 px focus ring |

Contrast ratios (WCAG 2.x), required ≥ 4.5:1 for text, ≥ 3:1 for borders and focus:

| Pair | Light on bg / surface | Dark on bg / surface |
|---|---|---|
| text | 16.88 / 15.34 | 15.31 / 13.52 |
| muted | 6.73 / 6.12 | 8.01 / 7.07 |
| accent (link text) | 6.84 / 6.22 | 8.28 / 7.31 |
| danger | 6.57 / 5.97 | 8.29 / 7.31 |
| border | 4.15 / 3.77 | 5.04 / 4.45 |
| focus | 6.84 / 6.22 | 8.28 / 7.31 |
| on-accent on accent | 6.84 | 8.15 |

Type: `--font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` (no download). Scale: `--text-sm` 0.875rem / line-height 1.4 (muted notes, codes), `--text-md` 1rem / 1.5 (body, buttons, inputs: never below 1rem, so iOS Safari does not zoom on focus), `--text-lg` 1.25rem / 1.35 (brand, h2), `--text-xl` 1.5rem / 1.25 (h1), `--text-2xl` 2rem / 1.2 (large figures, from L4). Weights 400 and 600 (700 for the brand only).

Spacing (4 px base): `--space-1` 0.25rem, `--space-2` 0.5rem, `--space-3` 0.75rem, `--space-4` 1rem, `--space-6` 1.5rem, `--space-8` 2rem, `--space-12` 3rem. Radii: `--radius-sm` 4px, `--radius-md` 8px. Targets: `--target-min` 48px, `--target-gap` 8px. Layout: `--header-height` 3.5rem (56 px), `--content-max` 72rem, `--text-max` 40rem, side padding `--space-4` below 40rem, `--space-6` from 40rem. Single breakpoint in L1a: `40rem` (640 px).

### L1a — Base layout (`templates/base.html`)

```
360 px                               1280 px
+----------------------------+       +--------------------------------------------------------+
| Rack Overflow   {nav, L2+} | 56px  | Rack Overflow                         {nav, L2+}       |
+----------------------------+       +--------------------------------------------------------+
| main, padding 16 px        |       |      main, max 72rem centred, padding 24 px            |
+----------------------------+       +--------------------------------------------------------+
```

- Skip link first in the body, visually hidden until focused, then shown top-left over the header; target `<main id="contenu" tabindex="-1">`.
- Header on `--color-surface`, bottom `--color-divider` line; the brand « Rack Overflow » is a link to `/` (text `--text-lg`, weight 700, text colour, no underline, ≥ 48 px high), `aria-current="page"` on home. No navigation in L1a: the `nav` block is empty and the `<nav>` element is rendered only when a page fills it.
- Permanent live region at the end of the body: `<div id="annonce" role="status" aria-live="polite" aria-atomic="true">`, visually hidden, empty on load, filled by the server with `hx-swap-oob` (from L2).
- Page title in the tab: `layout.title`.
- Focus ring 3 px `--color-focus`, offset 2 px, on `:focus-visible` of interactive elements only; `<main>`, focused by the skip link, gets no ring. Links in text are underlined.
- Thumb-zone actions: `.actions--thumb` puts the actions at the bottom of the viewport below 40rem only inside a full-height flex `<main>`, so a page using it also sets `{% block main_class %}main--message{% endblock %}` (`.main--message`). The two always go together; later screens reuse the pair.
- Buttons (`.button`, `.button--primary`, also on `<a>`): ≥ 48 × 48 px, 8 px apart, text `--text-md` weight 600; disabled at 50 % opacity.

### L1a — Home (`GET /`, `templates/home.html`)

Task: check the app answers. No business data before L2–L4. **Replaced in L4** by « start or resume a session » (L4 — Home); kept here as the L1a record.

```
360 px                               1280 px
+----------------------------+       +--------------------------------------------------------+
| Rack Overflow              |       | Rack Overflow                                          |
+----------------------------+       +--------------------------------------------------------+
| Accueil                    |       |      Accueil                                           |
| Rien à afficher pour       |       |      Rien à afficher pour l’instant.                   |
| l’instant.                 |       |      Les séances et la progression apparaîtront ici.   |
| Les séances et la          |       |      (text column max 40rem)                           |
| progression apparaîtront   |       |                                                        |
| ici.                       |       |                                                        |
+----------------------------+       +--------------------------------------------------------+
```

States: this empty state is the only state in L1a (no loading: full server render; a failure renders the 500 page).

### L1a — Error pages (`templates/error.html`)

Shown for a browser navigation only; requests refused by the security middleware (`invalid_host`, `forbidden_origin`, `unsupported_media_type`, `payload_too_large`) and htmx requests receive JSON codes, never this page. The page reads no data, so it renders when the database fails. No path or user input is echoed.

```
360 px (500 shown)                   1280 px (500 shown)
+----------------------------+       +--------------------------------------------------------+
| Rack Overflow              |       | Rack Overflow                                          |
+----------------------------+       +--------------------------------------------------------+
| Erreur du serveur          |       |      Erreur du serveur                                 |
| Une erreur inattendue      |       |      Une erreur inattendue s’est produite.             |
| s’est produite. Réessayez  |       |      Réessayez dans un instant.                        |
| dans un instant.           |       |      Code 500                                          |
| Code 500                   |       |      [ Réessayer ]  [ Retour à l’accueil ]             |
|                            |       |                                                        |
|                            |       |                                                        |
| [       Réessayer        ] |       |                                                        |
| [  Retour à l’accueil    ] |       |                                                        |
+----------------------------+       +--------------------------------------------------------+
```

Below 40rem the actions sit at the bottom of the viewport (thumb zone), stacked, full width, primary first; from 40rem they follow the text in a row. « Réessayer » is a link to the current path and query as sent (still percent-encoded; from L6 the query is kept so a retried `/api/export?format=json` keeps its format, "L6 — Settings: export"; leading slashes collapsed, any byte outside the URL characters percent-encoded, so the link stays same-origin and echoes nothing unsafe; GET), primary; « Retour à l’accueil » is primary when alone, secondary otherwise.

| Case | Title | Message | Actions |
|---|---|---|---|
| 404 | « Page introuvable » | « Cette adresse ne correspond à aucune page. » | « Retour à l’accueil » |
| 500, unhandled exception | « Erreur du serveur » | « Une erreur inattendue s’est produite. Réessayez dans un instant. » | « Réessayer », « Retour à l’accueil » |
| 405 | « Demande non aboutie » | « Cette action n’est pas permise à cette adresse. » | « Retour à l’accueil » |
| other status | « Demande non aboutie » | the code's message if mapped, else « La demande n’a pas pu aboutir. » | « Retour à l’accueil » |

Under the message, muted `--text-sm`: « Code {status} ». Tab order: skip link, brand, actions. No autofocus.

### L1a — Strings (`web/locales/fr.json`)

Apostrophes are typographic (’, U+2019).

| Key | Text |
|---|---|
| `app.name` | Rack Overflow |
| `layout.title` | {page} · Rack Overflow |
| `layout.skip_to_content` | Aller au contenu |
| `layout.nav_label` | Navigation principale |
| `home.title` | Accueil |
| `home.empty_title` | Rien à afficher pour l’instant. |
| `home.empty_text` | Les séances et la progression apparaîtront ici. |
| `action.retry` | Réessayer |
| `action.home` | Retour à l’accueil |
| `error.title.not_found` | Page introuvable |
| `error.title.internal` | Erreur du serveur |
| `error.title.generic` | Demande non aboutie |
| `error.status` | Code {status} |
| `error.not_found` | Cette adresse ne correspond à aucune page. |
| `error.internal` | Une erreur inattendue s’est produite. Réessayez dans un instant. |
| `error.method_not_allowed` | Cette action n’est pas permise à cette adresse. |
| `error.generic` | La demande n’a pas pu aboutir. |
| `error.invalid_host` | Adresse du serveur non reconnue. |
| `error.forbidden_origin` | Demande refusée : elle ne provient pas de cette application. |
| `error.unsupported_media_type` | Format de demande non pris en charge. |
| `error.payload_too_large` | Demande trop volumineuse. |
| `error.not_saved` | Non enregistré, réessayer |

In `error.forbidden_origin` the space before « : » is a no-break space (U+00A0). The page title in the tab uses the page's title key as `{page}` (home: `home.title`; errors: their `error.title.*` key).

### L1b — Pairing (`GET` / `POST /appairage`, `templates/pairing.html`, `templates/pairing_form.html`)

Task: make this browser a trusted device, once per device, by typing the code `rack device add` printed on the server. Decision: none beyond "type the code and send". Information needed: what to type, where it comes from, whether it worked, and what to do when it did not. Seen on the iPhone (one hand, numeric keypad) and occasionally on the desktop. Public page (D-049): reached by typing the URL printed by the CLI, by a `303` from any protected page when unpaired, or by `HX-Redirect` when an htmx request of a revoked device fails (`401 not_paired`). The page does not say why the user landed here (no `next` parameter, no state): the intro covers first pairing and re-pairing alike.

```
360 px, unpaired                      1280 px, unpaired
+----------------------------+        +--------------------------------------------------------+
| Rack Overflow              |        | Rack Overflow                                          |
+----------------------------+        +--------------------------------------------------------+
| Appairer cet appareil      |        |      Appairer cet appareil                             |
| Pour utiliser Rack Overflow|        |      Pour utiliser Rack Overflow ici, saisissez le     |
| ici, saisissez le code à 8 |        |      code à 8 chiffres donné par « rack device add »   |
| chiffres donné par « rack  |        |      sur le serveur.        (text column max 40rem)    |
| device add » sur le        |        |                                                        |
| serveur.                   |        |      Code d’appairage                                  |
|                            |        |      +----------------------+                          |
| Code d’appairage           |        |      | 1234 5678            |  form column max 24rem   |
| +------------------------+ |        |      +----------------------+                          |
| | 1234 5678              | |  64px  |      8 chiffres, valable 10 minutes.                   |
| +------------------------+ |        |      [ Appairer ]                                      |
| 8 chiffres, valable 10     |        |                                                        |
| minutes.                   |        |                                                        |
| [        Appairer        ] | 48px   |                                                        |
|  ~~~ iOS numeric keypad ~~ |        |                                                        |
+----------------------------+        +--------------------------------------------------------+

360 px, wrong code                    360 px, already paired (GET with a valid cookie)
+----------------------------+        +----------------------------+
| ...intro...                |        | Rack Overflow              |
| Code d’appairage           |        +----------------------------+
| +========================+ | 2px    | Appairer cet appareil      |
| |                        | | danger | Cet appareil est déjà      |
| +========================+ |        | appairé.                   |
| Code incorrect. Essais     | danger |                            |
| restants : 4.              |        |                            |
| 8 chiffres, valable 10     |        | [  Ouvrir l’application  ] |
| minutes.                   |        +----------------------------+
| [        Appairer        ] |
+----------------------------+
```

Layout:

- One column: h1, intro (body text colour: it is the instruction), then the form (`.pairing-form`, max width 24rem): label, input, error (when any), hint, submit button. Below 40rem the input and the button are full width.
- **Thumb-zone exception, deliberate.** The submit button sits directly under the input, not at the bottom of the viewport: the iOS numeric keypad (`inputmode="numeric"`) has no return key and covers the bottom half of the screen, so a bottom-anchored button would be hidden behind it while typing. Under the input, it stays visible above the keypad and within thumb reach. The "already paired" state has no keyboard and uses the L1a pair `main--message` + `.actions--thumb`.
- The input shows large digits: `--text-2xl`, tabular figures, letter spacing 0.08em, left aligned with its label, height ≥ 48 px (≈ 64 px with padding). It accepts « 12345678 », « 1234 5678 » and « 1234-5678 » (server `normalise_code`), so the user may copy the code exactly as the CLI printed it.

Form (`templates/pairing_form.html`, the swappable fragment, included by `pairing.html`):

- `<form class="pairing-form" id="appairage-formulaire" hx-post="/appairage" hx-target="this" hx-swap="outerHTML" hx-disabled-elt="#appairage-formulaire button">` (JSON through `json-enc`, set on `<body>`).
- `<label for="code">` « Code d’appairage ».
- `<input id="code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" enterkeyhint="go" maxlength="9" required autofocus spellcheck="false" autocapitalize="off" autocorrect="off" aria-describedby="…">`: `aria-describedby` is `code-aide`, or `code-erreur code-aide` when a message is shown; then also `aria-invalid="true"`. No `pattern`: a malformed entry gets the server's « Code incorrect » message and is not charged (D-049), one rule in one place. `required` uses the browser's native message for an empty submit (no request).
- Error: `<p id="code-erreur" class="field__error">`, between the input and the hint, so it is read right after the field and seen above the keypad.
- Hint: `<p id="code-aide" class="field__hint">` « 8 chiffres, valable 10 minutes. »
- `<button class="button button--primary">` « Appairer ».

States:

| State | Trigger | What the user sees | Focus / announcement |
|---|---|---|---|
| Unpaired | `GET`, no valid cookie | intro and empty form | input focused (`autofocus`; on iOS the keypad opens on the first tap, as WebKit allows no programmatic keyboard) |
| Sending | form submitted | « Appairer » disabled (50 % opacity) until the answer; text unchanged | — |
| Paired | `POST`, outcome `paired` | `HX-Redirect: /`: htmx loads the home page; this device is now trusted for 400 days of inactivity | the home page loads normally |
| Paired, fallback | a client that ignores `HX-Redirect` | the form replaced by « Cet appareil est appairé. » and a primary link « Ouvrir l’application » to `/` | — |
| Wrong code, attempts known | outcome `wrong_code` with `remaining` | form re-rendered, input empty and `--color-danger` 2 px border, message « Code incorrect. Essais restants : {remaining}. » | input keeps focus (same `id`, `autofocus`); message announced once through `#annonce` (`hx-swap-oob`) |
| Wrong code, otherwise | `wrong_code` without `remaining` (malformed entry, or no live code) | same, message « Code incorrect. Vérifiez les 8 chiffres et réessayez. » | same |
| Expired / used / revoked | outcome `code_expired` | same, message « Ce code n’est plus valable. Générez-en un nouveau sur le serveur. » | same |
| Too many attempts | outcome `too_many_attempts` (fifth wrong guess) | same, message « Trop d’essais : ce code est bloqué. Générez-en un nouveau sur le serveur. » | same |
| Already paired | `GET` with a valid cookie | « Cet appareil est déjà appairé. » and primary « Ouvrir l’application » (thumb zone); no form | no autofocus |
| Server error on `GET` | unhandled exception (e.g. database down) | L1a 500 page, « Réessayer » reloads `/appairage` | — |
| Server or network error on `POST` | 5xx, no answer | **L1b: no swap** (htmx does not swap ≥ 400, D-050); the button is enabled again and the typed code stays in the field. The display of « Non enregistré, réessayer » under the form is settled by L2 for every htmx form, this one included | — |

The input is emptied after every refusal (the code is a secret and a wrong one is better retyped than corrected). The error border and the message text both carry the state; colour is never the only signal.

Revoked device during an htmx action (from L2): the server answers `401 {"error": "not_paired"}` with `HX-Redirect: /appairage`; htmx follows the redirect, so the user lands on this page in the "Unpaired" state with the cookie cleared. A navigation lands here through `303`. `error.not_paired` is the 401 message for the rare browser navigation that gets the error page instead, and for L2's generic htmx error display.

Keyboard and focus order: skip link, brand, code input, « Appairer » (already paired: skip link, brand, « Ouvrir l’application »). Enter in the input submits on desktop. Page title in the tab: `pairing.title`. The brand link stays (unpaired, it leads back here through `303`).

Style (no new token): `components.css` gains the reusable field pieces, also used from L2: `.field` (column, gap `--space-2`), `.field__label` (`--text-md`, weight 600), `.input` (min height `--target-min`, padding `--space-3`, 1 px `--color-border`, `--radius-md`, background `--color-bg`, text `--color-text`, font inherit at ≥ `--text-md` so iOS does not zoom), `.input[aria-invalid="true"]` (`--color-danger` border kept at 1 px plus a 1 px `--color-danger` box-shadow: reads as 2 px with no layout shift), `.field__error` (`--color-danger`, `--text-md`), `.field__hint` (`--color-muted`, `--text-sm`). `pages/pairing.css`: `.pairing-form` (column, gap `--space-3`, max width 24rem, top margin `--space-6`), `.input--code` (`--text-2xl` / `--leading-2xl`, `font-variant-numeric: tabular-nums`, letter spacing 0.08em), below 40rem the form button at 100 % width, from 40rem compact (`align-self: flex-start`).

Strings (`web/locales/fr.json`; typographic apostrophes; a no-break space U+00A0 before « : » and inside « » guillemets):

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

« Essais restants : {remaining} » avoids a plural form (the catalog has none); `{remaining}` is 1 to 4.

### L2 — Header and navigation (`templates/base.html`)

Task: reach the two catalog sections from any page, and know where one is. Decision: which section. Information: the section names and the current one.

```
360 px                                1280 px
+------------------------------+      +--------------------------------------------------------------+
| Rack Overflow Exercices Var. |      |    Rack Overflow                      Exercices   Variables    |
|               ~~~~~~~~~      |      |                                       ~~~~~~~~~                |
+------------------------------+      +--------------------------------------------------------------+
| main                         |      |    main (brand and h1 start at the same x)                     |
```

- `<header class="site-header">` keeps its full-width surface and divider; its content moves into `<div class="site-header__inner">` with `max-width: var(--content-max)`, `margin-inline: auto` and `padding-inline: var(--page-padding)` (the header itself loses its padding), so brand and `<main>` content share the same left edge at every width (browser check: equal `left` at 1280 px).
- The `nav` block is filled on every protected page by one include `_nav.html` (home included: pairing lands on `/`, which must reach the catalog; on home no link is current, the brand carries `aria-current`); pairing and error pages leave it empty (no `<nav>` rendered). Two links (three from L3: L3 — Header and navigation) in a `<ul class="site-nav__list">` (flex, gap `--target-gap`): « Exercices » → `/exercices`, « Variables » → `/variables`. The page passes `section` (`exercises` / `variables`); the matching link gets `aria-current="page"` on its list page **and** its detail / form pages.
- Link look: `--text-md` weight 600, text colour, no underline, `min-height: var(--target-min)`, `display: inline-flex; align-items: center`; padding-inline 0 below 40rem (the text is wider than 48 px; this keeps brand + two links within 360 px), `--space-2` from 40rem. Current link: `--color-accent` text and a 3 px `--color-accent` bottom border (inset `box-shadow`, no layout shift): colour plus bar, never colour alone. Hover: underline.
- Fit at 360 px (L2; replaced from L3 by the two-row phone header, L3 — Header and navigation): brand ≈ 150 px + 8 + « Exercices » ≈ 80 + 8 + « Variables » ≈ 75 = 321 px of the 328 px available. `.site-header__inner` is `flex-wrap: wrap` with `justify-content: space-between`, so a wider system font drops the nav to a second 48 px row, left aligned, instead of scrolling horizontally.
- Tab order: skip link, brand, « Exercices », « Variables » (« Séances types » from L3), main.

### L2 — Form status and request errors (D-053, `templates/_form_status.html`, `static/js/request-errors.js`)

One slot per htmx form or action group carries both outcomes of a request: the failure written by the script, and the server's success message. It is never the place for refused input (that stays next to the field, D-050).

```
+--------------------------------------+
| Non enregistré, réessayer            |  <- slot, first child of the form: danger text, 600,
+--------------------------------------+     1 px danger border, radius-md, padding space-3
Libellé
[ Siège                             ]  <- focus returns here (first field)
...
[ Enregistrer ]
```

- Markup (macro `form_status(message="", kind="")`): `<p class="form-status" data-request-status{% if kind %} data-kind="{{ kind }}"{% endif %}{% if not message %} hidden{% endif %}>{{ message }}</p>`.
- **Placement: the first child of the `<form>` (or of the `[data-request-scope]` container), above the first field.** D-053 returns focus to the first field, so the message sits right above the focused element: on a phone, scrolling to the focused field brings the message into view with it; at the bottom it would be off screen. One exception (L4 fix loop 1): the next-set form of the session page puts its slot in the action bar right after the ✓, so a failed ✓ leaves the ✓ in place and the message just under it, both in view (`docs/ui-spec.md` "L4 — Session page", next-set form).
- Failure (script): text from `<body data-not-saved>` (`error.not_saved`, « Non enregistré, réessayer »), or from the slot's own `data-message` when present (search form only, `error.search_failed`, « Recherche impossible, réessayer »: nothing is saved by a search). The script sets `data-kind="error"`, removes `hidden`, writes the same text in `#annonce`, clears `aria-invalid` and old `.field__error` in the scope, then moves focus: a trigger outside any `<form>` that is still in the document keeps it; otherwise the scope's first visible enabled `input` / `select` / `textarea`, else the trigger. Values stay as typed; the trigger is enabled again.
- Success (server, after a `PATCH` that saved): the re-rendered form carries the slot with `kind="ok"` and the success text (e.g. « Modifications enregistrées. »), and the same text goes to `#annonce` out of band. Creations, deletions and archive changes do not use the success slot: the page or block they change is the confirmation (see each screen).
- Clearing: at `htmx:beforeRequest` from the same scope the slot is hidden, emptied and loses `data-kind`; a successful swap replaces the whole form, so stale field errors and messages never survive a new answer.
- Look (`components.css`): `.form-status` `--text-md`, weight 600, padding `--space-3`, `--radius-md`, 1 px border; `[data-kind="error"]`: `--color-danger` text and border; `[data-kind="ok"]`: `--color-text` text, `--color-border` border. The text carries the meaning; the colour repeats it. Below 40rem (`pages/catalog.css`), a shown slot has `margin-bottom: var(--space-3)` so it does not touch the heading or field under it.
- Pairing form (L1b): the slot is added as the first child of `.pairing-form`; a 5xx or network failure on `POST /appairage` now shows « Non enregistré, réessayer » above the code input, the typed code is kept, focus on the input.
- Not paired (`401` + `HX-Redirect`): no message, the browser lands on `/appairage` (L1b).

### L2 — Components (`components.css`)

Reused by every catalog page and by L3–L5. No new token; new breakpoint `64rem` (two columns on detail pages).

| Component | Markup | Look |
|---|---|---|
| Page head | `<div class="page-head">` h1, then optional primary action | flex, wrap, `justify-content: space-between`, gap `--space-3`; below 40rem the action is full width under the h1 |
| Section | `<section class="section" aria-labelledby="…">` with an `h2` | top margin `--space-8`, h2 then a muted intro (`--text-sm`) |
| List of rows | `<ul class="rows">` of `<li>` holding one `<a class="row">` | each row a link to the detail, `min-height: var(--target-min)`, padding `--space-3` 0, `--color-divider` line between rows; title weight 600 in text colour, meta `--text-sm` muted on the next line below 40rem, in grid columns from 40rem; hover background `--color-surface`; focus ring on the whole row |
| Tag | `<span class="tag">` | `--text-sm`, muted text, 1 px `--color-border`, `--radius-sm`, padding 0 `--space-2`; used for « Archivé », « Mesure », « Réglage » |
| Choice | `<label class="choice"><input type="checkbox|radio"> text</label>` | the whole label is the target: `min-height: var(--target-min)`, flex, gap `--space-3`; input 1.25rem, `accent-color: var(--color-accent)`; groups in `<fieldset class="choices">` with a `<legend class="field__label">`, no border |
| Select / textarea | `<select class="input">`, `<textarea class="input">` | same as `.input`; textarea `min-height: 10rem`, `resize: vertical` |
| Optional mark | `<span class="field__optional">` after the label text | muted, weight 400: « facultatif » |
| Danger button | `.button.button--danger` | transparent, `--color-danger` text and border (6.57 / 8.29:1) |
| Inline actions | `<div class="actions actions--inline">` | `.actions` with no top margin; buttons keep their size |
| In-place confirmation | `<div class="confirm" role="group" aria-labelledby="…">` fragment swapped in place of the action block holding the button that asked (`hx-get`, `hx-swap="outerHTML"` on the block: its slot and explanation are replaced with it, so the confirmation stands alone where the button was) | 1 px `--color-danger` border, `--radius-md`, padding `--space-4`: question (weight 600), consequence, then « Annuler » (secondary, `autofocus`) and the danger button; « Annuler » swaps the original block back (`hx-get` of the same confirmation route with `?annuler=1`, which answers the block) and focus returns to the button that asked |
| Status slot | `.form-status` (above) | |

Focus after an htmx swap: the fragment marks the element that should receive focus with `autofocus` (htmx 2 focuses it after the swap); ids are stable (`champ-{id}-monter`…) so htmx also keeps focus on an element that is still present.

Two-column detail pages (from `64rem`): `.detail` grid `minmax(0, 1fr) minmax(0, 1fr)`, gap `--space-8`; forms stay within `--text-max`. Below 64rem one column, in DOM order.

### L2 — Units: display and input (D-055)

Values are typed and shown in display units; `domain/units` converts. A number and its unit are joined by `unit.with_value` (« {number} {unit} », no-break space). Numbers in lists and summaries use tabular figures; numeric columns are right aligned.

| Kind | Shown | Label unit | Input | `inputmode` | Hint key |
|---|---|---|---|---|---|
| reps, `int` | `12` (`int` with its free unit: `5 niveau`) | — / the variable's unit | digits | `numeric` | — |
| weight (core and variable) | `16 kg`, `2,5 kg`, `1,25 kg` | `kg` | number, `,` or `.` | `decimal` | `unit.hint.weight` |
| distance | `400 m`, `5,2 km` | `km` | bare number = km, or `500 m`, `5,2 km` | `text` (needs « m ») | `unit.hint.distance` |
| duration | `0:45`, `1:30`, `1:02:00` | `m:ss` | `m:ss`, `h:mm:ss`, or seconds | `text` (needs « : ») | `unit.hint.duration` |
| `decimal` | exactly `scale` decimals: `2,50` + its unit | the variable's unit | ≤ scale decimals | `decimal` | `unit.hint.decimal` |
| `bool` | « Oui » / « Non » | — | select | — | — |
| `enum` | the value's label | — | select of labels (value = key) | — | — |
| `text` | as typed | — | text | `text` | — |

Discrete values are shown once with the unit at the end: « 16 · 20 · 24 kg ». Input fields carry `autocomplete="off"`, `spellcheck="false"`, `enterkeyhint="done"`. A unit-parse refusal (`not_a_number`, `too_many_decimals`, `negative`, `too_large`, `bad_duration`) is a field error under that input, never a 422.

### L2 — Exercise list and search (`GET /exercices`, `templates/exercises.html`, `templates/exercise_results.html`)

Task: find an exercise to edit it, or check it exists before creating it. Decision: which row to open, or « Nouvel exercice ». Information: name, movement, equipment, location; archived ones only on demand. Mostly desktop; at the gym the user may search on the phone.

```
360 px, q empty (grouped)             1280 px, q = « dc » (ranked, flat)
+------------------------------+      +--------------------------------------------------------------+
| Rack Overflow Exercices Var. |      |    Rack Overflow                      Exercices   Variables    |
+------------------------------+      +--------------------------------------------------------------+
| Exercices                    |      |    Exercices                               [ Nouvel exercice ] |
| [      Nouvel exercice     ] |      |                                                              |
| Rechercher un exercice       |      |    Rechercher un exercice                                    |
| [ Q                        ] |      |    [ dc                              ]  form max 40rem       |
| Nom ou alias, par ex. « DC » |      |    Nom ou alias, par ex. « DC » ou « bench ».                 |
| ou « bench ».                |      |    [ ] Afficher les archivés                                  |
| [ ] Afficher les archivés    |      |                                                              |
|                              |      |    Développé couché (barre)  Poussée horizontale  Barre  Salle |
| Musculation                  |      |    Développé couché haltères Poussée horizontale Haltères S.&M.|
| Squat au rack (barre)        |      |    Développé militaire halt. Poussée verticale  Haltères S.&M. |
| Squat · Barre · Salle        |      |    ...                                                       |
| ---------------------------- |      |                                                              |
| Développé couché (barre)     |      |                                                              |
| Poussée horizontale · Barre  |      |                                                              |
| · Salle                      |      |                                                              |
+------------------------------+      +--------------------------------------------------------------+
```

- Page head: h1 « Exercices », primary link-button « Nouvel exercice » → `/exercices/nouveau`.
- Search form: `<form role="search" class="search" action="/exercices" method="get" hx-get="/exercices/recherche" hx-target="#resultats" hx-swap="innerHTML" hx-trigger="input changed delay:200ms from:find input[name=q], search from:find input[name=q], change from:find input[name=archives], submit">`. A plain `GET` form, so it works without htmx; htmx replaces only the results. Children: the status slot with `data-message="{{ t('error.search_failed') }}"`; `<label for="q">` « Rechercher un exercice »; `<input class="input" id="q" name="q" type="search" value="{{ q }}" autocomplete="off" spellcheck="false" autocapitalize="off" autocorrect="off" enterkeyhint="search" maxlength="80" aria-describedby="q-aide">`; hint `q-aide`; choice « Afficher les archivés » (`name="archives" value="1"`). No submit button: results follow typing; Enter (or the keyboard's « Rechercher ») triggers `submit`, which htmx turns into the same `GET`. No autofocus (screen-reader users keep the page context; one Tab after the nav).
- The fragment answer sets `HX-Replace-Url: /exercices?q=…[&archives=1]`, so reload and Back show the same results; a navigation to `/exercices?q=dc` renders the page with the field filled and the ranked results.
- Results container `<div id="resultats">` (not a live region; the count is announced through `#annonce`).
  - `q` empty: groups by category in vocabulary order (Musculation, Kettlebell, Poids du corps, Cardio, Intervalles), each an `h2` and a `.rows` list sorted by normalised name; empty categories omitted.
  - `q` not empty: one flat `.rows` list in rank order (at most 20), no headings.
  - Row: `<a class="row" href="/exercices/{id}">` name (weight 600), then meta: movement · equipment · location (missing parts left out); « Archivé » tag after the name when archived. From 40rem the row is one line on a grid `minmax(0,2fr) minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr)` (name, movement, equipment, location; fixed tracks, never `auto`, so each row being its own grid still lines up with the others), names and texts left aligned, ellipsis never: long names wrap.
- Announcement: each fragment answer for a non-empty `q` fills `#annonce` out of band with « Résultats : {count} » (debounce 200 ms, so typing does not chatter).

States:

| State | What the user sees | Focus / announcement |
|---|---|---|
| Loaded, `q` empty | grouped list | — |
| Typing | previous results stay until the answer replaces them (< 100 ms on the LAN); no spinner | focus stays in the field |
| Results | ranked list | « Résultats : 3 » |
| No match | « Aucun exercice ne correspond à « {query} ». » then muted « Essayez un autre mot, une abréviation ou un alias. » | « Résultats : 0 » |
| Catalog empty (no exercise, or all archived and the box unchecked) | « Aucun exercice. » and muted « Créez votre premier exercice avec « Nouvel exercice ». » | — |
| Archived shown | archived rows interleaved, each with the « Archivé » tag | — |
| Request failed (5xx, network, timeout) | previous results kept; « Recherche impossible, réessayer » in the slot above the label | text announced; focus on the search field |
| Page failure | L1a 500 page | — |

Tab order: skip link, brand, nav, « Nouvel exercice », search field, « Afficher les archivés », rows.

### L2 — New exercise (`GET /exercices/nouveau`, page `templates/exercise_new.html` including `templates/exercise_form.html` in create mode)

Task: add an exercise the catalog lacks. Decision: name, category (it sets the starting fields), location. Information: what each choice changes.

```
360 px                                1280 px
+------------------------------+      +--------------------------------------------------------------+
| Nouvel exercice              |      |    Nouvel exercice                                           |
| Nom                          |      |    Nom                                                       |
| [                          ] |      |    [                                ]  form max 40rem        |
| Catégorie                    |      |    Catégorie                                                 |
| ( ) Musculation              |      |    ( ) Musculation   ( ) Kettlebell   ( ) Poids du corps     |
| ( ) Kettlebell               |      |    ( ) Cardio        ( ) Intervalles                          |
| ( ) Poids du corps           |      |    Elle fixe les champs de départ, modifiables ensuite.      |
| ( ) Cardio                   |      |    Lieu                                                      |
| ( ) Intervalles              |      |    ( ) Salle  ( ) Maison  (o) Salle et maison                |
| Elle fixe les champs de ...  |      |    Mouvement  facultatif                                     |
| Lieu                         |      |    [ Tirage horizontal              ]                         |
| ( ) Salle                    |      |    Équipement  facultatif                                    |
| ( ) Maison                   |      |    [ Haltères                       ]                         |
| (o) Salle et maison          |      |    [ Créer l’exercice ]  [ Annuler ]                          |
| Mouvement  facultatif        |      |                                                              |
| [                          ] |      |                                                              |
| Équipement  facultatif       |      |                                                              |
| [                          ] |      |                                                              |
| [    Créer l’exercice      ] |      |                                                              |
| [         Annuler          ] |      |                                                              |
+------------------------------+      +--------------------------------------------------------------+
```

- `<form class="form" id="exercice-formulaire" hx-post="/exercices" hx-disabled-elt="#exercice-formulaire button" hx-target="this" hx-swap="outerHTML">`; status slot first.
- Nom: `.input`, `maxlength="80"`, `required`, `autocomplete="off"`, `autocapitalize="sentences"`, `autofocus` (the user came here to type it).
- Catégorie: `fieldset.choices` of five radios, `required`, **no preselection** (it decides the starting fields, so it must be a choice, not a default). From 40rem the choices flow in a wrapping row. Hint « Elle fixe les champs de départ, modifiables ensuite. »
- Lieu: three radios, « Salle et maison » preselected (most exercises of the seed fit it; fewer taps).
- Mouvement and Équipement: `.input` with `list="mouvements"` / `list="equipements"` (`<datalist>` of the user's existing values from `services.exercises.suggestions`), `maxlength="40"`, optional mark, hints. Typing « tirage horizontal » is stored as the existing « Tirage horizontal » (D-054); no message.
- Actions (`.actions`, below 40rem full width stacked): primary « Créer l’exercice », link-button « Annuler » → `/exercices`.

States: refused input → `200` form re-rendered with values kept, each problem under its field (`aria-invalid`, `aria-describedby="{id}-erreur {id}-aide"`), focus on the first invalid field (`autofocus` on it), first message announced (D-050). Name taken: « Un exercice porte déjà ce nom (archivés compris). » under Nom. Success → `HX-Redirect: /exercices/{id}` (the detail page, with its default fields, is the confirmation). Failure → status slot (D-053).

### L2 — Exercise detail (`GET /exercices/{id}`, `templates/exercise.html`)

Task: shape how this exercise is logged (its fields, their steps, defaults and order), keep it findable (aliases), retire it (archive). Decision per section; the fields are the heart of it.

```
360 px                                1280 px (from 64rem: two columns)
+------------------------------+      +--------------------------------------------------------------+
| Kettlebell swing   [Archivé] |      |    Kettlebell swing                                          |
|                              |      |                                                              |
| Informations                 |      |    Informations                 | Champs                     |
| Nom [ Kettlebell swing     ] |      |    Nom [ Kettlebell swing   ]   | Ce qui est noté pendant la |
| Catégorie (o) Kettlebell ... |      |    Catégorie ( ) ... (o) KB     | séance, dans cet ordre.    |
| ...                          |      |    Lieu ...                     | 1 Répétitions              |
| [       Enregistrer        ] |      |    Mouvement [ Charnière   ]    |   Obligatoire · Pas : 1    |
|                              |      |    Équipement [ Kettlebell ]    |   [Monter][Descendre]      |
| Champs                       |      |    [ Enregistrer ]              |   > Modifier               |
| Ce qui est noté pendant la   |      |                                 | 2 Charge                   |
| séance, dans cet ordre.      |      |    Alias                        |   Obligatoire · Valeurs :  |
| 1  Répétitions               |      |    Autres noms pour la recherche|   16 · 20 · 24 kg          |
|    Obligatoire · Pas : 1     |      |    Swing [Retirer] KB swing [R.]|   [Monter][Descendre]      |
|    [Monter] [Descendre]      |      |    Nouvel alias                 |   > Modifier               |
|    > Modifier Répétitions    |      |    [               ] [Ajouter]  | Ajouter un champ           |
| 2  Charge                    |      |                                 | [ Choisir…        v] [Ajouter]
|    Obligatoire · Valeurs :   |      |                                 | Créer une variable         |
|    16 · 20 · 24 kg           |      | ------------------------------------------------------------ |
|    [Monter] [Descendre]      |      |    Archivage                                                 |
|    > Modifier Charge         |      |    Un exercice archivé disparaît ... [ Archiver ]            |
| Ajouter un champ             |      +--------------------------------------------------------------+
| [ Choisir…               v ] |
| [         Ajouter          ] |
| Créer une variable           |
| Alias ...                    |
| Archivage ...                |
+------------------------------+
```

Order in the DOM (and on the phone): h1, Informations, Champs, Alias, Archivage. From 64rem: grid areas `"info fields" "aliases fields" "archive archive"`; focus order follows the rows (info → fields → aliases → archive).

**Header.** h1 = the exercise name (also the tab title). `<span id="exercice-etat">` after it holds the « Archivé » tag when archived (updated out of band by archive / restore).

**Informations** (`templates/exercise_form.html`, edit mode): same fields as creation, prefilled, no autofocus; category hint replaced by « La changer ne modifie pas les champs. ». `hx-patch="/exercices/{id}"`. Button « Enregistrer » (primary). Saved → form re-rendered with the slot « Modifications enregistrées. » (`kind="ok"`), announced; the h1 and tab title follow a rename on the next page load (the h1 is also updated out of band).

**Champs** (`templates/exercise_fields.html`, one `[data-request-scope]` section with its status slot first): intro « Ce qui est noté pendant la séance, dans cet ordre. », then an `<ol class="fields">`; each `<li class="field-row" id="champ-{id}">`:

- Line 1: position number (muted, tabular), the field name (weight 600: « Répétitions », « Charge », « Durée », « Distance », or the variable label), then for a variable its scope tag (« Mesure » / « Réglage ») and « Archivée » when the variable is archived (it stays linked; L4 hides it).
- Line 2, muted `--text-sm`: « Obligatoire » or « Facultatif » · « Pas : 2,5 kg » or « Valeurs : 16 · 20 · 24 kg » · « Par défaut : 20 kg » (parts absent when unset).
- Line 3: `.actions--inline` « Monter » and « Descendre » (`hx-post …/deplacement`, `{"direction": "up"|"down"}`, `aria-label` « Monter {field} » / « Descendre {field} »; label in name: the visible word starts the accessible name). First row: « Monter » `disabled`; last row: « Descendre » `disabled`. After a move the fragment puts `autofocus` on the same button of the moved field, or on its other move button when the same one is now disabled, or on its « Modifier » summary when the field is alone (both buttons disabled); `#annonce`: « {field} : position {position} sur {total}. ».
- `<details class="field-row__edit">` with `<summary class="button">` « Modifier » + visually hidden « {field} » (≥ 48 px). Inside, one form `hx-patch="…/champs/{field_id}"` (status slot first):
  - Choice « Obligatoire ».
  - Numeric kinds (reps, weight, duration, distance; variables `int`, `decimal`, `weight`, `distance`, `duration`): `fieldset.choices` legend « Saisie pendant la séance », radios « Par pas » / « Valeurs proposées » (`name="mode"`; checked from the stored params; « Par pas » when neither). Then « Pas ({unit}) » and « Valeurs proposées ({unit}) » inputs; CSS shows only the input of the checked mode (`.field-row__edit:has([value=values]:checked) .only-step { display: none }` and the reverse). The route passes the domain only the input of the chosen mode, so `increment_with_discrete` cannot arise from the page. Values hint « Séparées par des espaces : 16 20 24. » (`inputmode="text"`: the iOS decimal pad has no space); splitting on spaces / « ; » and parsing each value is `domain/catalog.field_params`'s, each refused value named in the message.
  - « Valeur par défaut ({unit}) »: numeric input for numeric kinds; `<select>` (« Aucune » + labels by key) for `enum`; `<select>` (« Aucune », « Oui », « Non ») for `bool`; text input for `text`. Hint « Proposée quand l’exercice n’a pas encore d’historique. »
  - Unit in labels: kg, km, m:ss, or the variable's free unit; no parentheses when there is none (`field.step_label` vs `field.step_label_unit`). Unit hint under the input per the units table.
  - `.actions--inline`: primary « Enregistrer », danger « Retirer ce champ » (`hx-delete`, no confirmation: the stored values are kept and the field can be added again) with hint « Les valeurs déjà enregistrées sont conservées. ».
  - Refused input → the fields fragment re-rendered with this row's `<details open>`, values kept, messages under the inputs, `autofocus` on the first invalid one. Saved → row summary updated, `<details>` closed, `autofocus` on its summary, `#annonce` « Modifications enregistrées. ».
- « Ajouter un champ » form (`hx-post …/champs`): `<label>` « Ajouter un champ », `<select class="input" name="source" required>`: first option « Choisir… » (empty), `<optgroup>` « Quantités de base » (core quantities not yet linked), « Mesures » and « Réglages » (non-archived variables not yet linked, by label); button « Ajouter ». When nothing is left: the select is replaced by muted « Tous les champs disponibles sont déjà ajoutés. ». Below, link « Créer une variable » → `/variables/nouvelle?exercice={id}`. After the variable is created the user returns to `/exercices/{id}?ajout={variable_id}`, where that variable is preselected in this select and the select has `autofocus` (one tap, « Ajouter », to link it). Added → the new row is rendered `<details open>` with `autofocus` on « Obligatoire » (the next step is almost always its parameters, e.g. the 16 / 20 / 24 kg of a kettlebell), `#annonce` « Champ ajouté : {field}. ».
- Removing the last measure is a refusal of input (D-050), not a request failure: « Un exercice garde au moins une mesure : ce champ ne peut pas être retiré. » under that row's « Retirer ce champ » (`aria-describedby`), row open, focus on the button. Removed → row gone, `autofocus` on the next row's summary (or the « Ajouter un champ » select when none), `#annonce` « Champ retiré : {field}. ».

**Alias** (`templates/exercise_aliases.html`, `[data-request-scope]` with its slot first): intro « Autres noms pour la recherche. »; `<ul class="aliases">` of chips (`.tag`-like, text colour, `--text-md`) each followed by a button « Retirer » (`aria-label` « Retirer l’alias {alias} », `hx-delete`, no confirmation); empty: muted « Aucun alias. ». Form `hx-post …/alias`: label « Nouvel alias », input (`maxlength="60"`, `autocomplete="off"`, `autocapitalize="off"`, `enterkeyhint="done"`), hint « Par ex. « DC » ou « Bench press ». », button « Ajouter » (from 40rem on the input's line). Added → chip appended, input emptied with `autofocus` (aliases often come in twos), `#annonce` « Alias ajouté : {alias}. ». Removed → `autofocus` on the alias input, `#annonce` « Alias retiré : {alias}. ». Refused: `alias_taken`, `alias_is_name`, `required`, `too_long` under the input. Below 40rem the hint sits under the label, before the input and button line (CSS `order`; DOM order unchanged). A chip never widens the page: `.alias` shrinks (`min-width: 0`, `max-width: 100%`) and its text breaks anywhere (`overflow-wrap: anywhere`). The input and the « Ajouter un champ » select carry `min-width: 0`: a select is otherwise as wide as its longest option (a long variable label overflowed 360 px).

**Archivage** (`[data-request-scope]`, slot first, full width): active → « Un exercice archivé disparaît des listes et de la recherche ; son historique est conservé. » and secondary « Archiver » (`hx-post …/archive`, no confirmation: reversible). Archived → « Exercice archivé : il n’apparaît plus dans les listes ni la recherche. Son historique est conservé. » and primary « Restaurer » (`hx-delete …/archive`). The answer swaps this block, updates `#exercice-etat` out of band, puts `autofocus` on the new button and announces « Exercice archivé. » / « Exercice restauré. ». An archived exercise stays fully editable. The buttons of this block and of the variable's archive block sit `--space-4` below the explanation.

States of the page: loaded (fields always ≥ 1); archived (tag + block); unknown or foreign id → L1a 404 page; each action's failure → its scope's slot (D-053), focus per the slot rule.

### L2 — Variable list (`GET /variables`, `templates/variables.html`)

Task: see the shared measures and settings, open one, or create one. Information: label, type and unit, how many exercises use it.

```
360 px                                1280 px
+------------------------------+      +--------------------------------------------------------------+
| Variables                    |      |    Variables                             [ Nouvelle variable ]|
| Mesures et réglages créés    |      |    Mesures et réglages créés par vous, partagés entre        |
| par vous, partagés entre     |      |    exercices.                     Afficher les archivées      |
| exercices.                   |      |                                                              |
| [    Nouvelle variable     ] |      |    Mesures                                                   |
| Afficher les archivées       |      |    Résistance           Nombre entier · niveau  Exercices liés : 1 |
|                              |      |    Réglages                                                  |
| Mesures                      |      |    Siège                Liste de choix          Exercices liés : 2 |
| Résistance                   |      |                                                              |
| Nombre entier · niveau ·     |      |                                                              |
| Exercices liés : 1           |      |                                                              |
| Réglages                     |      |                                                              |
| Siège                        |      |                                                              |
| Liste de choix ·             |      |                                                              |
| Exercices liés : 2           |      |                                                              |
+------------------------------+      +--------------------------------------------------------------+
```

- Page head: h1 « Variables », primary « Nouvelle variable » → `/variables/nouvelle`. Muted intro under it.
- Archived toggle: a plain link « Afficher les archivées » → `/variables?archivees=1` (and « Masquer les archivées » → `/variables`); no form needed, 48 px high.
- Two groups, h2 « Mesures » (scope `set`) then « Réglages » (`setting`); an empty group is omitted. Rows sorted by normalised label: `<a class="row">` label (weight 600) + « Archivée » tag; meta: type label · unit (when it has one: free unit, or « kg » / « km » / « m:ss » for the typed kinds) · « Exercices liés : {count} » (count tabular, right aligned in its column from 40rem; grid `minmax(0,2fr) minmax(0,2fr) minmax(0,1fr)`, fixed tracks so columns align across rows).

States: list; empty (« Aucune variable. » + muted « Une variable ajoute une mesure (résistance, élastique…) ou un réglage (hauteur du siège…) à vos exercices. »; the primary button stays in the page head); archived shown (rows with « Archivée »); page failure → L1a 500.

### L2 — Variable create and edit (`GET /variables/nouvelle`, `GET /variables/{id}`, `templates/variable.html`, `templates/variable_form.html`)

Task: define a measure or a setting once, so several exercises can use it; later rename it, add choices, or retire it. Decision: role (per set or per exercise), type, unit, choices. Information: what each role means, what can no longer change once values exist, which exercises are affected.

```
360 px, create (type = Liste de choix)    1280 px, edit (from 64rem: two columns)
+------------------------------+      +--------------------------------------------------------------+
| Nouvelle variable            |      |    Siège                                                     |
| Pour l’exercice « Presse à   |      |    Une modification s’applique à tous les exercices liés.    |
| cuisses ».                   |      |    Libellé                      | Exercices liés             |
| Libellé                      |      |    [ Siège              ]       | Presse à cuisses           |
| [ Siège                    ] |      |    Rôle  Réglage                | Développé couché machine   |
| Rôle                         |      |    Ne peut plus changer : ...   |                            |
| ( ) Mesure                   |      |    Type  Liste de choix         | Archivage et suppression   |
|     Notée à chaque série...  |      |    Valeurs                      | Des valeurs sont           |
| (o) Réglage                  |      |    Valeur 1 [ 1   ]             | enregistrées : elle ne peut|
|     Noté une fois par ...    |      |      Utilisée dans l’historique | pas être supprimée, ...    |
| Type                         |      |    Valeur 2 [ 2   ] [ ] Retirer | [ Archiver ]               |
| [ Liste de choix         v ] |      |    ...                          |                            |
| Valeurs, une par ligne       |      |    Ajouter des valeurs, une par |                            |
| +------------------------+   |      |    ligne [                ]     |                            |
| | 1                      |   |      |    [ Enregistrer ]              |                            |
| | 2  ...                 |   |      |                                 |                            |
| +------------------------+   |      +--------------------------------------------------------------+
| Dans l’ordre d’affichage,... |
| [   Créer la variable      ] |
| [         Annuler          ] |
+------------------------------+
```

Form (`hx-post="/variables"` or `hx-patch="/variables/{id}"`, status slot first, max `--text-max`):

- « Libellé »: `.input`, `maxlength="40"`, `required`, autofocus on create only; hint « Tel qu’affiché pendant la séance, par ex. Siège. ». The code is never shown (D-054).
- « Rôle »: radios « Mesure » (hint « Notée à chaque série, par ex. la résistance du vélo. ») / « Réglage » (hint « Noté une fois par exercice et par séance, par ex. la hauteur du siège. »), `required`, no preselection.
- « Type »: `<select class="input" required>`: « Choisir… » then the eight types; labels of the typed kinds carry their unit (« Poids (kg) », « Distance (km) », « Durée (m:ss) »).
- Conditional fields, shown with CSS `:has()` on the type select (`.variable-form:has(option[value="enum"]:checked) .only-enum { display: block }`, hidden by default; both target engines support `:has`, no script). The route passes the domain only the fields of the chosen type, so hidden values never refuse a save.
  - `int`, `decimal`: « Unité » (`maxlength="12"`, optional mark, hint « Par ex. niveau, cm. Laisser vide si aucune. »).
  - `decimal`: « Décimales » `<select>` 1 / 2 / 3, default 1.
  - `enum`, create: `<textarea class="input" name="values" rows="6">` « Valeurs, une par ligne », hint « Dans l’ordre d’affichage, par ex. 1 à 10. » (« Siège » 1–10: ten short lines, or a paste).
  - `enum`, edit: `fieldset` « Valeurs »: one row per existing value in its order: `<label>` « Valeur {position} », input with the label (`maxlength="40"`) and a hidden input with its key (D-054: key kept, label editable), then either the choice « Retirer » (+ visually hidden label) or, when the key is in `used_enum_keys`, muted « Utilisée dans l’historique » and no checkbox (the refusal `enum_value_in_use` is prevented, not reported). Then a textarea « Ajouter des valeurs, une par ligne » appended at the end. Reordering existing values is not offered in L2 (new values go last; see design note).
- Frozen once values exist (`has_values`): Rôle, Type and Décimales are shown as read-only text (« Rôle » then « Réglage ») with the muted hint « Ne peut plus changer : des valeurs sont enregistrées. », not as disabled controls.
- Edit only, above the form: muted « Une modification s’applique à tous les exercices liés. » when at least one exercise is linked.
- From an exercise (`?exercice={id}`): muted line « Pour l’exercice « {name} ». » under the h1; « Annuler » returns to that exercise; success redirects to `/exercices/{id}?ajout={variable_id}`.
- Actions: create « Créer la variable » (primary) + « Annuler » link-button; edit « Enregistrer ». Saved (edit) → slot « Modifications enregistrées. », announced; h1 updated out of band.

Edit page, second column (one column below 64rem, after the form):

- « Exercices liés »: `.rows` of links to each exercise (archived ones tagged); empty: muted « Aucun exercice lié. Ajoutez la variable depuis la page d’un exercice, section Champs. ».
- « Archivage et suppression » (`[data-request-scope]`, slot first):

| Variable | Text | Buttons |
|---|---|---|
| active, no stored value | « Une variable archivée n’est plus proposée pour les exercices ; ses liens et son historique sont conservés. » + « Aucune valeur enregistrée : elle peut aussi être supprimée. » | « Archiver » (secondary), « Supprimer… » (danger) |
| active, with values | first sentence + « Des valeurs sont enregistrées : elle ne peut pas être supprimée, seulement archivée. » | « Archiver » only (no delete button at all) |
| archived | « Variable archivée : elle n’est plus proposée pour les exercices. Ses liens et son historique sont conservés. » (+ the deletable sentence when no value) | « Restaurer » (primary), « Supprimer… » when no value |

- Archive / restore: block swapped, « Archivée » tag beside the h1 out of band, `autofocus` on the new button, `#annonce` « Variable archivée. » / « Variable restaurée. ».
- « Supprimer… » → `GET /variables/{id}/suppression` swaps the in-place confirmation: « Supprimer « {label} » ? » then « Elle sera retirée des exercices liés. Cette action est définitive. » (or « Cette action est définitive. » with no link), « Annuler » (`autofocus`; `GET /variables/{id}/suppression?annuler=1` swaps the block back, `autofocus` on « Supprimer… ») and danger « Supprimer la variable » (`hx-delete`). Deleted → `HX-Redirect: /variables` (the row is gone; the explicit confirmation just before is the acknowledgement). If values appeared meanwhile: block re-rendered in its "with values" state with the refusal « Des valeurs sont enregistrées : la variable ne peut être qu’archivée. » announced, focus on « Archiver ». If the variable is the last measure of a linked exercise: block re-rendered with the refusal « Cette variable est la seule mesure de : {exercises}. Ajoutez-leur d’abord une autre mesure. » announced, focus on « Archiver ».

States: create empty; refused input (per field, focus on the first invalid, D-050); saved; frozen; archived; deletable / not deletable; unknown id → 404; failures → slot (D-053).

### L2 — Strings (`web/locales/fr.json`)

Typographic apostrophes (’); a no-break space (U+00A0) before « : », « ? » and inside « » guillemets, and between a number and its unit.

| Key | Text |
|---|---|
| `nav.exercises` | Exercices |
| `nav.variables` | Variables |
| `action.save` | Enregistrer |
| `action.cancel` | Annuler |
| `action.add` | Ajouter |
| `action.remove` | Retirer |
| `action.archive` | Archiver |
| `action.restore` | Restaurer |
| `action.move_up` | Monter |
| `action.move_down` | Descendre |
| `action.edit` | Modifier |
| `form.optional` | facultatif |
| `form.choose` | Choisir… |
| `form.none` | Aucune |
| `status.saved` | Modifications enregistrées. |
| `tag.archived_m` | Archivé |
| `tag.archived_f` | Archivée |
| `error.search_failed` | Recherche impossible, réessayer |
| `error.invalid_request` | Demande non valable. |
| `unit.kg` | kg |
| `unit.km` | km |
| `unit.m` | m |
| `unit.duration` | m:ss |
| `unit.with_value` | {number} {unit} |
| `unit.hint.weight` | En kg, par ex. 2,5. |
| `unit.hint.distance` | En km (0,5) ou en mètres (500 m). |
| `unit.hint.duration` | En m:ss, h:mm:ss ou secondes : 1:30 ou 90. |
| `unit.hint.decimal` | Décimales au plus : {scale}. |
| `field.yes` | Oui |
| `field.no` | Non |
| `quantity.reps` | Répétitions |
| `quantity.weight` | Charge |
| `quantity.duration` | Durée |
| `quantity.distance` | Distance |
| `exercise.category.strength` | Musculation |
| `exercise.category.kettlebell` | Kettlebell |
| `exercise.category.bodyweight` | Poids du corps |
| `exercise.category.cardio` | Cardio |
| `exercise.category.intervals` | Intervalles |
| `exercise.location.gym` | Salle |
| `exercise.location.home` | Maison |
| `exercise.location.both` | Salle et maison |
| `variable.type.int` | Nombre entier |
| `variable.type.decimal` | Nombre décimal |
| `variable.type.duration` | Durée (m:ss) |
| `variable.type.distance` | Distance (km) |
| `variable.type.weight` | Poids (kg) |
| `variable.type.enum` | Liste de choix |
| `variable.type.bool` | Oui / non |
| `variable.type.text` | Texte |
| `variable.scope.set` | Mesure |
| `variable.scope.setting` | Réglage |
| `variable.scope.set_hint` | Notée à chaque série, par ex. la résistance du vélo. |
| `variable.scope.setting_hint` | Noté une fois par exercice et par séance, par ex. la hauteur du siège. |
| `catalog.group.core` | Quantités de base |
| `catalog.group.set` | Mesures |
| `catalog.group.setting` | Réglages |
| `exercises.title` | Exercices |
| `exercises.new` | Nouvel exercice |
| `exercises.search_label` | Rechercher un exercice |
| `exercises.search_hint` | Nom ou alias, par ex. « DC » ou « bench ». |
| `exercises.show_archived` | Afficher les archivés |
| `exercises.results` | Résultats : {count} |
| `exercises.no_match` | Aucun exercice ne correspond à « {query} ». |
| `exercises.no_match_hint` | Essayez un autre mot, une abréviation ou un alias. |
| `exercises.empty_title` | Aucun exercice. |
| `exercises.empty_text` | Créez votre premier exercice avec « Nouvel exercice ». |
| `exercise.new_title` | Nouvel exercice |
| `exercise.name_label` | Nom |
| `exercise.category_label` | Catégorie |
| `exercise.category_hint_new` | Elle fixe les champs de départ, modifiables ensuite. |
| `exercise.category_hint_edit` | La changer ne modifie pas les champs. |
| `exercise.location_label` | Lieu |
| `exercise.pattern_label` | Mouvement |
| `exercise.pattern_hint` | Par ex. Tirage horizontal. Sert à regrouper les exercices dans les menus. |
| `exercise.equipment_label` | Équipement |
| `exercise.equipment_hint` | Par ex. Barre, Haltères, Machine. |
| `exercise.create` | Créer l’exercice |
| `exercise.section_info` | Informations |
| `exercise.section_fields` | Champs |
| `exercise.fields_intro` | Ce qui est noté pendant la séance, dans cet ordre. |
| `exercise.section_aliases` | Alias |
| `exercise.aliases_intro` | Autres noms pour la recherche. |
| `exercise.alias_label` | Nouvel alias |
| `exercise.alias_hint` | Par ex. « DC » ou « Bench press ». |
| `exercise.alias_remove` | Retirer l’alias {alias} |
| `exercise.no_alias` | Aucun alias. |
| `exercise.section_archive` | Archivage |
| `exercise.archive_text` | Un exercice archivé disparaît des listes et de la recherche ; son historique est conservé. |
| `exercise.archived_text` | Exercice archivé : il n’apparaît plus dans les listes ni la recherche. Son historique est conservé. |
| `exercise.announce_archived` | Exercice archivé. |
| `exercise.announce_restored` | Exercice restauré. |
| `exercise.announce_alias_added` | Alias ajouté : {alias}. |
| `exercise.announce_alias_removed` | Alias retiré : {alias}. |
| `exercise.announce_field_added` | Champ ajouté : {field}. |
| `exercise.announce_field_removed` | Champ retiré : {field}. |
| `exercise.announce_field_moved` | {field} : position {position} sur {total}. |
| `field.add_label` | Ajouter un champ |
| `field.add_none` | Tous les champs disponibles sont déjà ajoutés. |
| `field.new_variable` | Créer une variable |
| `field.required` | Obligatoire |
| `field.optional` | Facultatif |
| `field.step` | Pas : {value} |
| `field.values` | Valeurs : {values} |
| `field.default` | Par défaut : {value} |
| `field.move_up_named` | Monter {field} |
| `field.move_down_named` | Descendre {field} |
| `field.mode_legend` | Saisie pendant la séance |
| `field.mode_step` | Par pas |
| `field.mode_values` | Valeurs proposées |
| `field.step_label` | Pas |
| `field.step_label_unit` | Pas ({unit}) |
| `field.values_label` | Valeurs proposées |
| `field.values_label_unit` | Valeurs proposées ({unit}) |
| `field.values_hint` | Séparées par des espaces : 16 20 24. |
| `field.default_label` | Valeur par défaut |
| `field.default_label_unit` | Valeur par défaut ({unit}) |
| `field.default_hint` | Proposée quand l’exercice n’a pas encore d’historique. |
| `field.remove` | Retirer ce champ |
| `field.remove_hint` | Les valeurs déjà enregistrées sont conservées. |
| `variables.title` | Variables |
| `variables.intro` | Mesures et réglages créés par vous, partagés entre exercices. |
| `variables.new` | Nouvelle variable |
| `variables.show_archived` | Afficher les archivées |
| `variables.hide_archived` | Masquer les archivées |
| `variables.linked_count` | Exercices liés : {count} |
| `variables.empty_title` | Aucune variable. |
| `variables.empty_text` | Une variable ajoute une mesure (résistance, élastique…) ou un réglage (hauteur du siège…) à vos exercices. |
| `variable.new_title` | Nouvelle variable |
| `variable.for_exercise` | Pour l’exercice « {name} ». |
| `variable.label_label` | Libellé |
| `variable.label_hint` | Tel qu’affiché pendant la séance, par ex. Siège. |
| `variable.scope_legend` | Rôle |
| `variable.type_label` | Type |
| `variable.unit_label` | Unité |
| `variable.unit_hint` | Par ex. niveau, cm. Laisser vide si aucune. |
| `variable.scale_label` | Décimales |
| `variable.values_label` | Valeurs, une par ligne |
| `variable.values_hint` | Dans l’ordre d’affichage, par ex. 1 à 10. |
| `variable.values_legend` | Valeurs |
| `variable.value_label` | Valeur {position} |
| `variable.value_in_use` | Utilisée dans l’historique |
| `variable.values_add_label` | Ajouter des valeurs, une par ligne |
| `variable.frozen_hint` | Ne peut plus changer : des valeurs sont enregistrées. |
| `variable.shared_hint` | Une modification s’applique à tous les exercices liés. |
| `variable.create` | Créer la variable |
| `variable.section_linked` | Exercices liés |
| `variable.no_linked` | Aucun exercice lié. Ajoutez la variable depuis la page d’un exercice, section Champs. |
| `variable.section_archive` | Archivage et suppression |
| `variable.archive_text` | Une variable archivée n’est plus proposée pour les exercices ; ses liens et son historique sont conservés. |
| `variable.archived_text` | Variable archivée : elle n’est plus proposée pour les exercices. Ses liens et son historique sont conservés. |
| `variable.deletable_text` | Aucune valeur enregistrée : elle peut aussi être supprimée. |
| `variable.in_use_text` | Des valeurs sont enregistrées : elle ne peut pas être supprimée, seulement archivée. |
| `variable.delete` | Supprimer… |
| `variable.confirm_delete_title` | Supprimer « {label} » ? |
| `variable.confirm_delete_text_linked` | Elle sera retirée des exercices liés. Cette action est définitive. |
| `variable.confirm_delete_text` | Cette action est définitive. |
| `variable.confirm_delete` | Supprimer la variable |
| `variable.announce_archived` | Variable archivée. |
| `variable.announce_restored` | Variable restaurée. |
| `catalog.error.required` | À renseigner. |
| `catalog.error.too_long` | {max} caractères au plus. |
| `catalog.error.invalid_choice` | Choix non valable. |
| `catalog.error.name_taken` | Un exercice porte déjà ce nom (archivés compris). |
| `catalog.error.not_a_number` | Nombre attendu, par ex. 2,5. |
| `catalog.error.too_many_decimals` | Trop de décimales. |
| `catalog.error.negative` | La valeur doit être positive. |
| `catalog.error.too_large` | Valeur trop grande. |
| `catalog.error.bad_duration` | Durée attendue en m:ss, h:mm:ss ou secondes. |
| `catalog.error.must_be_positive` | Doit être supérieur à zéro. |
| `catalog.error.increment_with_discrete` | Choisissez un pas ou des valeurs proposées, pas les deux. |
| `catalog.error.duplicate_value` | Valeur en double : {value}. |
| `catalog.error.too_many_values` | {max} valeurs au plus. |
| `catalog.error.values_required` | Au moins une valeur. |
| `catalog.error.default_not_in_values` | La valeur par défaut doit faire partie des valeurs proposées. |
| `catalog.error.enum_value_in_use` | Valeur utilisée dans l’historique : elle ne peut pas être retirée. |
| `catalog.error.frozen_after_use` | Ne peut plus changer : des valeurs sont enregistrées. |
| `catalog.error.last_measure` | Un exercice garde au moins une mesure : ce champ ne peut pas être retiré. |
| `catalog.error.variable_last_measure` | Cette variable est la seule mesure de : {exercises}. Ajoutez-leur d’abord une autre mesure. |
| `catalog.error.already_linked` | Ce champ est déjà dans l’exercice. |
| `catalog.error.alias_taken` | Cet alias existe déjà pour cet exercice. |
| `catalog.error.alias_is_name` | L’alias est identique au nom de l’exercice. |
| `catalog.error.variable_in_use` | Des valeurs sont enregistrées : la variable ne peut être qu’archivée. |

Problem codes are the domain's (`domain/catalog`, `domain/units`): the developer uses exactly these codes; a code without a key renders the key (D-036), and the "every `t()` key exists" test covers templates. Tab titles: `exercises.title`, `exercise.new_title`, `variables.title`, `variable.new_title`; detail pages use the exercise name / variable label as `{page}` (base template accepts a ready text as well as a key).

### L3 — Header and navigation (`templates/_nav.html`, `base.css`, `components.css`)

Task: reach the three management sections from any page. (Phone layout replaced from L5 by three rows: L5 — Tokens, components and header.) A third link « Séances types » → `/seances-types` (`section = "templates"`, `aria-current` on the list, new, and detail pages) does not fit beside the brand at 360 px: brand ≈ 150 + « Exercices » ≈ 80 + « Variables » ≈ 75 + « Séances types » ≈ 115 + 3 × 8 = 444 px for 328 px.

```
360 px (below 40rem: two rows)        1280 px (one row, unchanged)
+------------------------------+      +--------------------------------------------------------------+
| Rack Overflow                | 48   |    Rack Overflow          Exercices  Variables  Séances types |
| Exercices  Variables  Séances| 48   |                                                ~~~~~~~~~~~~~ |
| types  (one line, see below) |      +--------------------------------------------------------------+
|                      ~~~~~~~ |
+------------------------------+
| main                         |
```

- Below 40rem the nav always takes its own row under the brand (`.site-nav { flex-basis: 100% }`), links left aligned on the page edge with a gap of `--space-4` (80 + 75 + 115 + 2 × 16 = 302 px of 328): a deterministic layout instead of L2's wrap fallback, so the header does not jump between pages. `.site-nav__list` keeps `flex-wrap: wrap` as the last fallback for a very wide system font (a third 48 px row, never a horizontal scroll). Every link stays ≥ 48 px high; the 16 px gap exceeds `--target-gap`.
- Cost: the header is 97 px high on the phone (two 48 px rows and the divider), at the top of the page only (not sticky). The bottom of the screen stays free for the L4 session screen. `.main--message` (pages without nav: pairing, errors) keeps `--header-height`; a page with nav that later needs the full-height layout (L4) must account for the second row.
- Rejected: a menu button with `<details>` (one more tap on every navigation and a widget to make accessible), shortened labels (« Séances » will mean history in L5; « S. types » is unreadable), a horizontally scrolling nav (hides a section, breaks the no-scroll rule in spirit).
- From 40rem: one row as in L2 (brand left, links right, `--space-2` padding): 150 + 96 + 91 + 131 + 24 ≈ 492 px, fits from 640 px.
- Tab order: skip link, brand, « Exercices », « Variables », « Séances types », main.

### L3 — Target text (`web/display.Display.target`, `domain/units.compact_duration`)

One formatter for every indicative target (D-059), reused by L4. Built from the parts present, in this order:

| Target (canonical) | Shown |
|---|---|
| sets 4, reps 6–8 | « 4 × 6–8 » |
| sets 3, reps 10 | « 3 × 10 » |
| sets 3, duration 30 s, reps 12 | « 3 × 30 s / 12 » |
| sets 1, duration 1800 s | « 1 × 30 min » |
| sets 3, reps 10, note « par côté » | « 3 × 10 · par côté » |
| sets 3, duration 30 s, reps 3, note « par côté » | « 3 × 30 s / 3 · par côté » |
| sets 5, distance 400 m | « 5 × 400 m » |
| reps 8–10, no sets | « 8–10 » |
| sets 4 only | « Séries : 4 » |
| note only | « par côté » |
| empty | nothing (no line at all) |

- Parts: duration, distance, reps, joined by « / » (brief notation); reps « {min}–{max} » with an en dash, or one number when min = max. `×` only when sets and at least one part are present; between number and `×` a no-break space on both sides, so « 4 × 6–8 » never breaks.
- **Compact durations in targets** (decided for L3): a target is a plan read at a glance, and the brief writes « 30 s » and « 30 min »; « 30:00 » reads as thirty hours as easily as thirty minutes. `domain/units.compact_duration(seconds)` returns the text key and numbers, `Display.target` joins them; every other duration (inputs, logged values, L4 steppers) stays `m:ss` / `h:mm:ss` (D-055).

| Seconds | Shown | Key |
|---|---|---|
| < 60 | « 45 s » | `duration.compact.seconds` |
| < 3600, whole minutes | « 30 min » | `duration.compact.minutes` |
| < 3600, otherwise | « 1 min 30 » (seconds on two digits) | `duration.compact.minutes_seconds` |
| ≥ 3600, whole hours | « 1 h » | `duration.compact.hours` |
| ≥ 3600, whole minutes | « 1 h 15 » (minutes on two digits) | `duration.compact.hours_minutes` |
| ≥ 3600, with seconds | « 1:15:30 » (D-055 form, rare) | — |

- Inputs keep D-055: the duration input of a target is prefilled `0:30` / `30:00` and accepts `m:ss`, `h:mm:ss` or seconds; its hint says so. Reading « 30 min » and editing `30:00` is the accepted cost of one parser.
- Distances use `Display.value` (« 400 m », « 5 km »).

### L3 — Template list (`GET /seances-types`, `templates/session_templates.html`)

Task: see the templates in the order the session start (L4) will offer them, open one, create one, change the order. Decision: which to open, or which to move. Information: name, location, size (number of slots).

```
360 px                                1280 px
+------------------------------+      +--------------------------------------------------------------+
| Rack Overflow                |      |    Rack Overflow          Exercices  Variables  Séances types |
| Exercices Variables Séances t|      +--------------------------------------------------------------+
+------------------------------+      |    Séances types                     [ Nouvelle séance type ] |
| Séances types                |      |    Proposées dans cet ordre au démarrage d’une séance.       |
| [  Nouvelle séance type    ] |      |    Afficher les archivées                                    |
| Proposées dans cet ordre au  |      |                                                              |
| démarrage d’une séance.      |      |    Salle A — Squat & poussée…   Salle   Blocs : 6  [Monter][Descendre]
| Afficher les archivées       |      |    Salle B — Charnière & pou…   Salle   Blocs : 6  [Monter][Descendre]
|                              |      |    Maison — Kettlebell, barr…   Maison  Blocs : 6  [Monter][Descendre]
| Salle A — Squat & poussée    |      |    Cardio — Course 30 min   Salle et m. Blocs : 1  [Monter][Descendre]
| horizontale                  |      |                                                              |
| Salle · Blocs : 6            |      |    Archivées  (only with the toggle on)                      |
| [ Monter ] [ Descendre ]     |      |    Salle 1  [Archivée]          Salle   Blocs : 2            |
| ---------------------------- |      +--------------------------------------------------------------+
| Salle B — Charnière & ...    |
| Salle · Blocs : 6            |
| [ Monter ] [ Descendre ]     |
+------------------------------+
```

- Page head: h1 « Séances types », primary link-button « Nouvelle séance type » → `/seances-types/nouvelle`. Muted intro « Proposées dans cet ordre au démarrage d’une séance. » (it explains why the order matters).
- Toggle: link « Afficher les archivées » → `/seances-types?archivees=1`, « Masquer les archivées » → `/seances-types` (as variables).
- Active list `<section id="seances-types-liste" data-request-scope>` (the swappable fragment of `POST …/deplacement`, `templates/session_templates_list.html`), status slot first, then `<ul class="rows">` in stored order. Each `<li class="template-row" id="seance-type-{id}">`: `<a class="row row--template" id="seance-type-{id}-lien" href="/seances-types/{id}">` name (weight 600), meta location (`LOCATION_KEYS`, the exercise location words) · « Blocs : {count} » (tabular); then `.actions--inline` « Monter » / « Descendre » (`hx-post …/deplacement`, `{"direction": "up"|"down"}`, `hx-target="#seances-types-liste"`, `hx-swap="outerHTML"`, `hx-disabled-elt="this"`, `aria-label` « Monter {name} » / « Descendre {name} », ids `seance-type-{id}-monter` / `-descendre`; first « Monter » and last « Descendre » `disabled`; one template: no move buttons, and a move request for it focuses the row link `seance-type-{id}-lien`). The buttons are siblings of the link, never inside it.
- From 40rem the `<li>` is a grid `minmax(0, 1fr) auto` (link | buttons, centred vertically) and the link a grid `minmax(0, 3fr) minmax(0, 1fr) minmax(0, 1fr)` (name, location, count right aligned), fixed tracks so rows align. Below 40rem the buttons sit under the link (the link keeps its full width and 48 px).
- Archived (toggle on): a second section, h2 « Archivées », rows with the « Archivée » tag, no move buttons (their order is set when restored: last), in name order.
- After a move: fragment re-rendered, `autofocus` on the same button of the moved row, or on its other button when the same one is now disabled (L2 rule); `#annonce` « {name} : position {position} sur {total}. ».

States:

| State | What the user sees | Focus / announcement |
|---|---|---|
| Loaded | rows in order | — |
| Empty (no active template) | « Aucune séance type. » and muted « Une séance type liste les exercices et les menus proposés au démarrage d’une séance. »; the page-head button stays | — |
| Only archived ones, toggle off | the empty state, and the toggle link shown | — |
| Archived shown | second section | — |
| Moving | the clicked button disabled until the answer | — |
| Move failed | order unchanged, « Non enregistré, réessayer » in the list's slot | focus kept on the clicked button (D-053, trigger outside a form) |
| Unknown id in a move (deleted meanwhile) | 404 → same slot message | same |
| Page failure | L1a 500 page | — |

Tab order: skip link, brand, nav, « Nouvelle séance type », toggle, then per row: link, « Monter », « Descendre ».

### L3 — New template (`GET /seances-types/nouvelle`, `templates/session_template_new.html` including `templates/session_template_form.html` in create mode)

Task: name a new template and say where it is done. Decision: name and location (the location filters the L4 start screen, so it is a choice, not a default).

```
360 px                                1280 px
+------------------------------+      +--------------------------------------------------------------+
| Nouvelle séance type         |      |    Nouvelle séance type                                      |
| Nom                          |      |    Nom                                                       |
| [                          ] |      |    [                                ]  form max 40rem        |
| Par ex. Salle A ou Haut du   |      |    Par ex. Salle A ou Haut du corps.                         |
| corps.                       |      |    Lieu                                                      |
| Lieu                         |      |    ( ) Salle   ( ) Maison   ( ) Salle et maison              |
| ( ) Salle                    |      |    Le démarrage d’une séance propose les séances types du    |
| ( ) Maison                   |      |    lieu choisi.                                              |
| ( ) Salle et maison          |      |    [ Créer la séance type ]  [ Annuler ]                     |
| Le démarrage d’une séance... |      |                                                              |
| [  Créer la séance type    ] |      |                                                              |
| [         Annuler          ] |      |                                                              |
+------------------------------+      +--------------------------------------------------------------+
```

- `<form class="form" id="seance-type-formulaire" hx-post="/seances-types" hx-target="this" hx-swap="outerHTML" hx-disabled-elt="#seance-type-formulaire button">`, status slot first.
- « Nom »: `<input class="input" id="seance-nom" name="name" maxlength="60" required autocomplete="off" autocapitalize="sentences" autofocus aria-describedby="seance-nom-aide">`, hint « Par ex. Salle A ou Haut du corps. ».
- « Lieu »: `fieldset.choices.choices--row` (id `seance-lieu`), radios `name="location"` « Salle » / « Maison » / « Salle et maison » (values `gym` / `home` / `both`), `required`, **no preselection** (design note §1); hint « Le démarrage d’une séance propose les séances types du lieu choisi. ».
- Actions (`.actions`, stacked full width below 40rem): primary « Créer la séance type », link-button « Annuler » → `/seances-types`.
- Refused → form re-rendered `200`, values kept, messages under fields, `autofocus` on the first invalid one, first message in `#annonce` (D-050): « À renseigner. » (`required`), « 60 caractères au plus. » (`too_long`), « Une séance type porte déjà ce nom (archivées comprises). » (`template_name_taken`), « Choix non valable. » (`invalid_choice`). Created → `HX-Redirect: /seances-types/{id}` (the empty template page is the confirmation). Failure → slot (D-053).

### L3 — Template detail (`GET /seances-types/{id}`, `templates/session_template.html`)

Task: shape what a session from this template offers: which exercises and menus, in which order, with which indicative target; rename it, set its place, retire it. The slots are the heart of the page.

```
360 px                                1280 px (from 64rem: Blocs | Informations + Archivage)
+------------------------------+      +--------------------------------------------------------------+
| Salle A — Squat & poussée    |      |    Salle A — Squat & poussée horizontale                     |
| horizontale                  |      |    Salle                                                     |
| Salle                        |      |    Blocs                               | Informations         |
|                              |      |    Dans l’ordre de la séance. ...      | Nom [ Salle A — … ]  |
| Blocs                        |      |    1 Squat au rack (barre)             | Lieu (o) Salle ...   |
| Dans l’ordre de la séance.   |      |      4 × 6–8                           | [ Enregistrer ]      |
| Un bloc est un exercice ou   |      |      [Monter][Descendre] [Modifier]    |                      |
| un menu d’exercices au choix.|      |    2 Développé couché (barre)          | Archivage            |
| 1 Squat au rack (barre)      |      |      4 × 6–8                           | Une séance type      |
|   4 × 6–8                    |      |      [Monter][Descendre] [Modifier]    | archivée n’est plus  |
|   [Monter] [Descendre]       |      |    3 Tirage horizontal  [Menu]         | proposée ...         |
|   [Modifier]                 |      |      Rowing barre au rack · Rowing     | [ Archiver ]         |
| 3 Tirage horizontal  [Menu]  |      |      assis machine · Tirage horiz. p.  |                      |
|   Rowing barre au rack ·     |      |      3 × 8–10                          |                      |
|   Rowing assis machine ·     |      |      [Monter][Descendre] [Modifier]    |                      |
|   Tirage horizontal poulie   |      |    ...                                 |                      |
|   3 × 8–10                   |      |    Ajouter un bloc                     |                      |
|   [Monter] [Descendre]       |      |    Type (o) Exercice ( ) Menu          |                      |
|   [Modifier]                 |      |    Exercice [ Choisir…          v ]    |                      |
| ...                          |      |    [ Ajouter le bloc ]                 |                      |
| Ajouter un bloc              |      |                                        |                      |
| Informations ...             |      |                                        |                      |
| Archivage ...                |      |                                        |                      |
+------------------------------+      +--------------------------------------------------------------+
```

Order in the DOM (and on the phone): h1, location line, Blocs, Informations, Archivage. From 64rem: grid `minmax(0, 3fr) minmax(0, 2fr)`, areas `"slots info" "slots archive"`; focus order follows the DOM. The slots come first because they are what the user comes to change; name and location are set once at creation.

**Header.** h1 `<span id="seance-type-titre">{name}</span><span id="seance-type-etat">` (« Archivée » tag when archived, updated out of band). Under it, muted `<p id="seance-type-lieu">` the location word (updated out of band after a save).

**Blocs** (`templates/session_template_slots.html`, `<section id="blocs" class="section" data-request-scope>`, the fragment of every slot and option route; status slot first): h2 « Blocs », muted intro « Dans l’ordre de la séance. Un bloc est un exercice précis ou un menu d’exercices au choix. ». One `<datalist id="mouvements">` (movement patterns, D-054) for every menu-name input of the fragment. Then `<ol class="slots">`; each `<li class="slot" id="bloc-{id}">`:

- Line 1 `.slot__head`: position (muted, tabular), then
  - exercise slot: the exercise name (weight 600), « Archivé » tag when archived;
  - menu slot: the menu name (weight 600) then the tag « Menu ».
- Menu only, line 2 `.slot__options` (muted `--text-sm`): the options in order joined by « · », each archived option followed by « (archivé) ». It is a reading summary; options are edited inside « Modifier ».
- Target line `.slot__target` (text colour, tabular figures): `Display.target`; absent when the target is empty.
- Skipped warning (muted `--text-sm`, only when it applies, D-058): exercise slot with an archived exercise « Ignoré en séance : l’exercice est archivé. »; menu whose options are all archived « Ignoré en séance : tous ses exercices sont archivés. ».
- `.actions--inline` « Monter » / « Descendre » (as the list: `hx-post …/blocs/{slot_id}/deplacement`, `hx-target="#blocs"`, `aria-label` « Monter {name} » / « Descendre {name} », ids `bloc-{id}-monter` / `-descendre`, ends disabled), then `<details class="slot__edit">` with `<summary class="button" id="bloc-{id}-modifier">` « Modifier » + visually hidden « {name} ». `{name}` is the exercise name or the menu name.

Inside « Modifier » (`templates/session_template_slot_form.html`):

1. Slot form `hx-patch="/seances-types/{id}/blocs/{slot_id}"` (`class="slot-form"`, status slot first):
   - Exercise slot: « Exercice » `<select class="input" id="bloc-{id}-exercice" name="exercise_id" required>`: non-archived exercises grouped by movement pattern (`<optgroup>` per pattern in name order, then « Sans mouvement »), current one selected. When the current exercise is archived it is the first option, selected, labelled « {name} (archivé) », so a target can be saved without changing it (the service accepts an unchanged archived exercise; it refuses only a newly chosen one, `exercise_unavailable`).
   - Menu slot: « Nom du menu » `<input class="input" id="bloc-{id}-menu" name="label" maxlength="40" required list="mouvements" autocomplete="off" autocapitalize="sentences">`, hint « Par ex. Tirage horizontal ou Bras. ».
   - `<fieldset class="target">` legend « Objectif indicatif » + optional mark, muted intro « Proposé quand l’exercice n’a pas encore d’historique. » (L4 prefill rule). Inputs, all optional, `autocomplete="off"`, `spellcheck="false"`, `enterkeyhint="done"`:
     - « Séries » `id="bloc-{id}-series" name="sets" inputmode="numeric" maxlength="2"`;
     - « Répétitions » `id="bloc-{id}-reps" name="reps" inputmode="text" maxlength="12"` (the iOS number pad has no dash), hint « Un nombre ou une plage : 10 ou 8-10. »;
     - « Durée (m:ss) » `id="bloc-{id}-duree" name="duration" inputmode="text"`, hint `unit.hint.duration`;
     - « Distance (km) » `id="bloc-{id}-distance" name="distance" inputmode="text"`, hint `unit.hint.distance`;
     - « Note » `id="bloc-{id}-note" name="note" maxlength="40"`, hint « Par ex. par côté. ».
     Prefilled with `reps_text` and `Display.input_text` (`0:30`, `400 m`). Layout: one column below 40rem; from 40rem a two-column grid (Séries | Répétitions, Durée | Distance, Note full width), `align-items: start` so hints do not misalign rows. Emptying every input clears the target.
   - `.actions--inline`: primary « Enregistrer », danger « Retirer ce bloc » (`hx-delete`, `hx-target="#blocs"`, `hx-disabled-elt="this"` so a double tap cannot show « Non enregistré » over a removal that succeeded, no confirmation: the slot is soft deleted, sessions already done keep their exercises, and the slot can be added again), hint under it « Les séances déjà faites ne changent pas. ».
2. Menu only, options editor `<div class="menu-options" data-request-scope>` (slot first): h3 « Exercices proposés », muted « Dans l’ordre où ils sont proposés pendant la séance. ». `<ol class="options">`; each `<li class="option" id="option-{option_id}">`: name (+ « Archivé » tag), then `.actions--inline` « Monter » / « Descendre » / « Retirer » (`aria-label` « Monter {exercise} », « Descendre {exercise} », « Retirer {exercise} du menu »; ids `option-{id}-monter` / `-descendre` / `-retirer`; ends disabled). With a single option there is no « Retirer » and a muted line « Un menu garde au moins un exercice : retirez le bloc pour le supprimer. » (the `last_option` refusal is prevented, the server keeps it as a backstop shown under the list).
3. Menu only, add-option form `hx-post="…/blocs/{slot_id}/options"` (`class="add-field"`, the L2 add pattern, slot first): label « Ajouter un exercice au menu », `<select class="input" id="bloc-{id}-option-ajout" name="exercise_id" required>` « Choisir… » then non-archived exercises not yet in this menu, grouped by movement pattern, **the group whose pattern matches the menu name (after normalisation) first**, so « Tirage horizontal » lists its rowing variants on top; button « Ajouter ». At 12 options, or when no exercise is left, the select is replaced by muted « 12 exercices au plus dans un menu. » / « Tous les exercices disponibles sont déjà dans ce menu. » (same id, `tabindex="-1"`); after a refused add-option it takes the focus and references the message under it with `aria-describedby` (D-053: the focus is never lost).

**Ajouter un bloc** (form `class="add-slot"`, `hx-post="/seances-types/{id}/blocs"`, `hx-target="#blocs"`, slot first; h3 « Ajouter un bloc »):

- `fieldset.choices.choices--row` legend « Type »: radios `name="kind"` « Exercice » (`exercise`, checked by default: the cheap, frequent case) / « Menu » (`menu`), ids `bloc-ajout-exercice-type` / `bloc-ajout-menu-type`.
- « Nom du menu » (`id="bloc-ajout-menu"`, `list="mouvements"`, `maxlength="40"`), shown only when « Menu » is checked (`.add-slot:has(input[name="kind"][value="menu"]:checked) .only-menu`, hidden by default, as the L2 `:has()` switches; the route passes `label` only for a menu).
- « Exercice » `<select id="bloc-ajout-exercice" name="exercise_id" required>`: « Choisir… », non-archived exercises grouped by movement pattern; hint `bloc-ajout-exercice-aide`, shown for both kinds (the select always references it, and the kind switch is CSS only): « Pour un menu, le premier exercice proposé ; les autres s’ajoutent ensuite. ».
- Button « Ajouter le bloc » (primary; below 40rem full width).
- At 30 slots the form content is replaced by muted « 30 blocs au plus : retirez-en un pour en ajouter. »; with no non-archived exercise at all: muted « Aucun exercice disponible. » and a link « Créer un exercice » → `/exercices/nouveau`. The muted line has its own id `bloc-ajout-etat` (`tabindex="-1"`): it takes the add form's focus (after removing the last slot) and, after a refused add, the focus and the refusal message, linked with `aria-describedby`.

**Results and focus in Blocs** (the fragment marks the target with `autofocus`; announcements out of band in `#annonce`):

| Action | Result | Focus | Announcement |
|---|---|---|---|
| Add an exercise slot | new last row, its « Modifier » open | « Séries » of the new slot (next step: its target) | « Bloc ajouté : {name}. » |
| Add a menu | new last row, « Modifier » open | the menu's « Ajouter un exercice au menu » select (next step: more options) | same |
| Save a slot | row summary updated, `<details>` closed | its « Modifier » summary | « Modifications enregistrées. » |
| Refused slot input | row `<details open>`, values kept, messages under inputs | first invalid input | first message |
| Refused add | add form values kept, messages under inputs (a muted form: the message under its line) | first invalid input (a muted form: `bloc-ajout-etat`) | first message |
| Move a slot | rows reordered | same button of the moved row (other one at an end; a lone slot: its « Modifier ») | « {name} : position {position} sur {total}. » |
| Remove a slot | row gone, positions renumbered | next row's « Modifier », else the previous row's, else the « Exercice » radio of the add form (its muted line `bloc-ajout-etat` when the form is muted) | « Bloc retiré : {name}. » |
| Add an option | option last in the list, menu stays open | the add-option select again (options come in threes) | « Ajouté au menu : {exercise}. » |
| Move an option | menu stays open | same button of the moved option (other one at an end; a lone option: the add-option select or its muted line) | « {exercise} : position {position} sur {total}. » |
| Remove an option | menu stays open | next option's « Retirer », else the previous one's, else the add-option select | « Retiré du menu : {exercise}. » |
| Request failed | nothing changed, « Non enregistré, réessayer » in the nearest slot | D-053 (row buttons keep focus; forms: first visible field) | same text |

Empty template: instead of the list, « Aucun bloc pour l’instant. » and muted « Ajoutez un exercice ou un menu ci-dessous. »; the add form follows.

**Informations** (`templates/session_template_form.html`, edit mode, `hx-patch="/seances-types/{id}"`): h2 « Informations », same Nom and Lieu as creation, prefilled, no autofocus, button « Enregistrer ». Saved → slot « Modifications enregistrées. » (`kind="ok"`), announced; `#seance-type-titre` and `#seance-type-lieu` updated out of band. Refusals as at creation.

**Archivage** (`templates/session_template_archive.html`, `<section id="seance-type-archivage" data-request-scope>`, slot first): h2 « Archivage »; active → « Une séance type archivée n’est plus proposée au démarrage d’une séance ; les séances déjà faites sont conservées. » and secondary « Archiver » (no confirmation: reversible); archived → « Séance type archivée : elle n’est plus proposée au démarrage d’une séance. La restaurer la place en dernier. » and primary « Restaurer ». The answer swaps the block, updates `#seance-type-etat` out of band, puts `autofocus` on the new button, announces « Séance type archivée. » / « Séance type restaurée. ». An archived template stays fully editable. No delete (invariant 8).

States of the page: loaded; empty (no slot); archived (tag + block); slots with archived exercises (tags, skipped warnings); 30 slots (add form replaced); unknown, foreign → L1a 404 page; each action's failure → its scope's slot (D-053).

Keyboard and focus order: skip link, brand, nav; per slot « Monter », « Descendre », « Modifier » (and, when open, the slot form, the options and the add-option form); the add-slot form; Informations; Archivage. Enter in a text input submits its own form. Tab titles: `templates.title`, `template.new_title`; the detail page uses the template name as `{page}`.

### L3 — Style (`static/css/pages/templates.css`, `base.css`, `components.css`)

No new token, no new breakpoint.

- `base.css` / `components.css`: below 40rem `.site-nav { flex-basis: 100% }` and `.site-nav__list { gap: var(--space-4) }`; unchanged from 40rem.
- `pages/templates.css` (each template page also links `pages/catalog.css` for `.toggle-link`, `.empty`, `.catalog-intro`, `.add-field`):
  - `.template-row`: column, gap `--space-2`, padding-bottom `--space-3` below 40rem; from 40rem grid `minmax(0, 1fr) auto`, `align-items: center`, gap `--space-4`. `.row--template` from 40rem grid `minmax(0, 3fr) minmax(0, 1fr) minmax(0, 1fr)`, metas at `--text-md`, count `tabular-nums`, right aligned.
  - `.slots`, `.slot`: the L2 `.fields` / `.field-row` look (column, gap `--space-2`, padding `--space-3` 0, divider between rows), with `.slot__head` position muted tabular and name weight 600; `.slot__options` and the skipped warning muted `--text-sm`; `.slot__target` `tabular-nums`. `.slot__edit > summary` as `.field-row__edit > summary`. From 40rem « Modifier » sits on the line of « Monter » / « Descendre » (wireframe): `.slot` is `display: flow-root` with `--space-2` between children, `.slot > .actions` floats left with `margin-inline-end: --target-gap`, the summary flows beside it, and `.slot__edit > :not(summary)` clears it, so opening the form moves nothing and the form takes the full width below. Long names and option lists wrap (`overflow-wrap: anywhere` on `.slot__options` and option names); never an ellipsis.
  - `.slot-form`: column, gap `--space-3`, margin-top `--space-3`. `.target`: `fieldset` without border, `min-width: 0`; its inputs in one column, from 40rem `display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-3); align-items: start`, the note field `grid-column: 1 / -1`.
  - `.menu-options`: margin-top `--space-4`, top `--color-divider` line, padding-top `--space-3`; `h3` at `--text-md` weight 600. `.options` / `.option`: list without bullets; option name then its `.actions--inline` (from 40rem on one line: `display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between`).
  - `.add-slot`: like `.form` (column, gap `--space-4`, max `--text-max`), margin-top `--space-6`; `.only-menu { display: none }`, `.add-slot:has(input[name="kind"][value="menu"]:checked) .only-menu { display: flex }`; below 40rem its button full width.
  - From 64rem `.template-detail` grid `minmax(0, 3fr) minmax(0, 2fr)`, areas `"slots info" "slots archive"`, gap 0 `--space-8`, `align-items: start`.
- From 40rem a `.template-row` has `padding-block: --space-2` so the 48 px buttons of two rows do not touch; the detail grid has `grid-template-rows: auto 1fr` so Archivage follows Informations instead of stretching to the slots' height (developer, L3).
- 360 px check: a menu with 12 options, the longest seed template name (« Salle B — Charnière & poussée verticale ») and a slot whose « Modifier » is open fit without horizontal scroll; selects carry `min-width: 0`.

### L3 — Strings (`web/locales/fr.json`)

Same typography as L2: typographic apostrophes; a no-break space (U+00A0) before « : », « ? », inside « » guillemets, between a number and its unit, and on both sides of « × » in `target.sets_times`.

| Key | Text |
|---|---|
| `nav.templates` | Séances types |
| `templates.title` | Séances types |
| `templates.intro` | Proposées dans cet ordre au démarrage d’une séance. |
| `templates.new` | Nouvelle séance type |
| `templates.show_archived` | Afficher les archivées |
| `templates.hide_archived` | Masquer les archivées |
| `templates.archived_heading` | Archivées |
| `templates.slot_count` | Blocs : {count} |
| `templates.empty_title` | Aucune séance type. |
| `templates.empty_text` | Une séance type liste les exercices et les menus proposés au démarrage d’une séance. |
| `template.new_title` | Nouvelle séance type |
| `template.name_label` | Nom |
| `template.name_hint` | Par ex. Salle A ou Haut du corps. |
| `template.location_label` | Lieu |
| `template.location_hint` | Le démarrage d’une séance propose les séances types du lieu choisi. |
| `template.create` | Créer la séance type |
| `template.section_info` | Informations |
| `template.section_slots` | Blocs |
| `template.slots_intro` | Dans l’ordre de la séance. Un bloc est un exercice précis ou un menu d’exercices au choix. |
| `template.no_slot_title` | Aucun bloc pour l’instant. |
| `template.no_slot_text` | Ajoutez un exercice ou un menu ci-dessous. |
| `template.tag_menu` | Menu |
| `template.option_archived` | {name} (archivé) |
| `template.slot_skipped_exercise` | Ignoré en séance : l’exercice est archivé. |
| `template.slot_skipped_menu` | Ignoré en séance : tous ses exercices sont archivés. |
| `template.move_up_named` | Monter {name} |
| `template.move_down_named` | Descendre {name} |
| `template.exercise_label` | Exercice |
| `template.no_pattern_group` | Sans mouvement |
| `template.menu_label` | Nom du menu |
| `template.menu_hint` | Par ex. Tirage horizontal ou Bras. |
| `template.target_legend` | Objectif indicatif |
| `template.target_intro` | Proposé quand l’exercice n’a pas encore d’historique. |
| `template.sets_label` | Séries |
| `template.reps_label` | Répétitions |
| `template.reps_hint` | Un nombre ou une plage : 10 ou 8-10. |
| `template.duration_label` | Durée (m:ss) |
| `template.distance_label` | Distance (km) |
| `template.note_label` | Note |
| `template.note_hint` | Par ex. par côté. |
| `template.remove_slot` | Retirer ce bloc |
| `template.remove_slot_hint` | Les séances déjà faites ne changent pas. |
| `template.options_heading` | Exercices proposés |
| `template.options_intro` | Dans l’ordre où ils sont proposés pendant la séance. |
| `template.option_remove_named` | Retirer {name} du menu |
| `template.last_option_hint` | Un menu garde au moins un exercice : retirez le bloc pour le supprimer. |
| `template.add_option_label` | Ajouter un exercice au menu |
| `template.options_full` | 12 exercices au plus dans un menu. |
| `template.options_none_left` | Tous les exercices disponibles sont déjà dans ce menu. |
| `template.add_slot_heading` | Ajouter un bloc |
| `template.kind_legend` | Type |
| `template.kind_exercise` | Exercice |
| `template.kind_menu` | Menu |
| `template.first_option_hint` | Pour un menu, le premier exercice proposé ; les autres s’ajoutent ensuite. |
| `template.add_slot` | Ajouter le bloc |
| `template.slots_full` | 30 blocs au plus : retirez-en un pour en ajouter. |
| `template.no_exercise` | Aucun exercice disponible. |
| `template.create_exercise` | Créer un exercice |
| `template.section_archive` | Archivage |
| `template.archive_text` | Une séance type archivée n’est plus proposée au démarrage d’une séance ; les séances déjà faites sont conservées. |
| `template.archived_text` | Séance type archivée : elle n’est plus proposée au démarrage d’une séance. La restaurer la place en dernier. |
| `template.announce_archived` | Séance type archivée. |
| `template.announce_restored` | Séance type restaurée. |
| `template.announce_moved` | {name} : position {position} sur {total}. |
| `template.announce_slot_added` | Bloc ajouté : {name}. |
| `template.announce_slot_removed` | Bloc retiré : {name}. |
| `template.announce_option_added` | Ajouté au menu : {name}. |
| `template.announce_option_removed` | Retiré du menu : {name}. |
| `target.sets_times` | {sets} × {parts} |
| `target.sets_only` | Séries : {sets} |
| `target.reps_range` | {min}–{max} |
| `target.with_note` | {target} · {note} |
| `duration.compact.seconds` | {seconds} s |
| `duration.compact.minutes` | {minutes} min |
| `duration.compact.minutes_seconds` | {minutes} min {seconds} |
| `duration.compact.hours` | {hours} h |
| `duration.compact.hours_minutes` | {hours} h {minutes} |
| `catalog.error.template_name_taken` | Une séance type porte déjà ce nom (archivées comprises). |
| `catalog.error.too_many_slots` | 30 blocs au plus par séance type. |
| `catalog.error.too_many_options` | 12 exercices au plus dans un menu. |
| `catalog.error.option_taken` | Cet exercice est déjà dans ce menu. |
| `catalog.error.last_option` | Un menu garde au moins un exercice : retirez le bloc pour le supprimer. |
| `catalog.error.exercise_unavailable` | Exercice archivé ou introuvable : choisissez-en un autre. |
| `catalog.error.target_sets_range` | Entre 1 et 20 séries. |
| `catalog.error.target_reps_format` | Un nombre ou une plage, par ex. 10 ou 8-10. |
| `catalog.error.target_reps_range` | Entre 1 et 100 répétitions. |
| `catalog.error.target_reps_order` | Le premier nombre doit être le plus petit. |

Reused keys: `action.save`, `action.cancel`, `action.add`, `action.remove`, `action.archive`, `action.restore`, `action.move_up`, `action.move_down`, `action.edit`, `form.optional`, `form.choose`, `status.saved`, `tag.archived_m` (exercises), `tag.archived_f` (templates), `exercise.location.*` (location words), `unit.hint.duration`, `unit.hint.distance`, `catalog.error.required`, `catalog.error.too_long` (name 60, menu name 40, note 40), `catalog.error.invalid_choice`, the `domain/units` codes (`bad_duration`, `not_a_number`, `too_many_decimals`, `negative`, `too_large`, `must_be_positive`).

Problem code for a taken template name: `template_name_taken` (not `name_taken`, whose text names an exercise); the template service raises it, including from the `NameTakenError` race branch. The target note's length refusal uses the existing `too_long` (`{max}` = 40), not a new `text_too_long`.

### L4 — Components (`components.css`, `pages/session.css`)

Design reasons: design note `docs/architecture/2026-11-03-l4-session-logging.md`, "UI design". No new token, no new breakpoint.

| Component | Markup | Look |
|---|---|---|
| Choice chips | `<fieldset class="chips">` with a `<legend>`, then `<label class="chip"><input type="radio" class="chip__input"> text</label>` | the native radio is visually hidden (clip, still focusable and announced), the label is the target: `min-height` and `min-width: var(--target-min)`, padding 0 `--space-3`, 1 px `--color-border`, `--radius-md`, `--text-md` weight 600, centred text, tabular figures; gap `--target-gap`, `flex-wrap: wrap`. Checked (`:has(:checked)`): `--color-accent` background and border, `--color-on-accent` text. Focus: the 3 px ring on the chip through `:has(:focus-visible)`. One tab stop per group, arrows move inside (native radios). Used for location, set type, discrete values, `bool`, and `enum` fields with ≤ 12 values (a `<select class="input">` above) |
| Stepper | `<div class="stepper">`: `<label for>` then `<div class="stepper__row">` `[button −] [input] [button +]` | label `.field__label`; buttons `.button.stepper__button` 56 × 56 px (`calc(var(--target-min) + var(--space-2))`), glyph « − » / « + » at `--text-xl`; input `.input.stepper__input`: flex 1, `min-width: 0`, height 56 px, `--text-2xl` / `--leading-2xl`, weight 600, centred, `tabular-nums`. Row gap `--target-gap`. Error and hint under the row |
| Confirm button | `<button class="button button--primary button--confirm" id="exercice-{row}-valider">` | full width, `min-height` 56 px, `--text-lg`; a « ✓ » glyph before the text through `::before { content: "✓" / ""; margin-inline-end: var(--space-2) }` (decorative, the text names the action) |
| Set row | `<li class="set-row" id="serie-{id}">` | number (muted, tabular, 2ch), the set text (`tabular-nums`), tags (type when not work, « Record »), then « Modifier » on the right; min-height 48 px; divider between rows. Below 40rem the tags wrap under the text; never an ellipsis. Open, the `<details>` spans the row on the grid's next line: « Modifier » at the right edge, the edit form at the row's full width (no `display: contents`, L4 fix loop 1) |
| Record tag | `<span class="tag tag--record">` « Record » | `.tag` with `--color-accent` text and border (6.84 / 8.28:1) and a « ★ » before it (`::before { content: "★" / "" }`): the word carries the meaning, the star and the colour repeat it |
| Neutral confirmation | `.confirm.confirm--neutral` | the L2 in-place confirmation with a `--color-border` border, for a final but non-destructive choice (closing a session); the confirming button is primary, not danger |

Field labels with a unit use `session.field_unit` (« Charge (kg) », « Durée (m:ss) », « Distance (km) »); fields without unit use the quantity word or the variable label. Inputs: `autocomplete="off"`, `spellcheck="false"`, `enterkeyhint="done"`, `inputmode` per the L2 units table, text ≥ 1rem.

### L4 — Home: start or resume (`GET /`, `templates/home.html`)

Task: start the right session in one tap, or return to the one running. Decision: which template (or none), at which place. Information: the place (preselected), the templates of that place in the user's order, which one was done last.

```
360 px, no open session                  1280 px, no open session
+------------------------------+         +--------------------------------------------------------------+
| Rack Overflow                |         |    Rack Overflow          Exercices  Variables  Séances types |
| Exercices Variables Séances t|         +--------------------------------------------------------------+
+------------------------------+         |    Nouvelle séance                    (column max 40rem)      |
| Nouvelle séance              |         |    Lieu                                                      |
| Lieu                         |         |    [■ Salle ] [ Maison ]                                     |
| [■ Salle ] [ Maison ]        |         |    Séance type                                               |
| Séance type                  |         |    [ Salle A — Squat & poussée horizontale   Dernière séance ]|
| +--------------------------+ |         |    [ Salle B — Charnière & poussée verticale                ]|
| | Salle A — Squat &        | | 64px    |    [ Cardio — Course 30 min                                 ]|
| | poussée horizontale      | |         |    [ Séance libre ]                                          |
| | [Dernière séance]        | |         |    Sans séance type : vous ajoutez les exercices un à un.    |
| +--------------------------+ |         +--------------------------------------------------------------+
| | Salle B — Charnière &    | |
| | poussée verticale        | |         360 px, a session is open
| +--------------------------+ |         +------------------------------+
| | Cardio — Course 30 min   | |         | Séance en cours              |
| +--------------------------+ |         | Salle A — Squat & poussée    |
| [       Séance libre       ] |         | horizontale                  |
| Sans séance type : vous      |         | Salle · commencée à 18:42    |
| ajoutez les exercices un à un|         | Exercices : 2 · Séries : 7   |
+------------------------------+         | [   Reprendre la séance    ] |
                                         +------------------------------+
```

No open session — one form `<form class="start" id="demarrer" hx-post="/seances" hx-disabled-elt="#demarrer button">` (status slot first):

- h1 « Nouvelle séance ».
- `fieldset.chips` legend « Lieu »: radios `name="location"` « Salle » (`gym`) / « Maison » (`home`), the default checked (last session's place, else Salle). Changing it sends nothing: the template buttons are filtered by CSS `:has()` (`.start:has([name=location][value=home]:checked) .start__template[data-location=gym] { display: none }` and the reverse; `both` always shown), the L2 / L3 switch pattern.
- Legend-like heading `<h2 id="start-templates">` « Séance type », then one `<button class="button start__template" name="template_id" value="{id}" data-location="{gym|home|both}">` per non-archived template in template order: full width, left aligned, `min-height` 64 px, name weight 600 (wraps, never an ellipsis); the template of the latest session carries the tag « Dernière séance » (the user alternates A / B). json-enc sends the submitter's `template_id` and the checked `location`.
- `<button class="button" name="template_id" value="">` « Séance libre » (secondary, full width below 40rem), hint « Sans séance type : vous ajoutez les exercices un à un. ».
- No template for the checked place: a muted line per place, shown by the same switch: « Aucune séance type pour la salle. » / « Aucune séance type pour la maison. » and a link « Nouvelle séance type » → `/seances-types/nouvelle`. « Séance libre » stays.
- Started → `HX-Redirect: /seances/{id}#seance-plan` (L4 fix loop 1: the page opens scrolled to the plan, `scroll-margin-top` `--space-2`, so the first ✓ is above the fold at 360 × 640 instead of at 664–720 px). A session already open (double tap, other device) → the same redirect to it. Refused (`template_unavailable`, `invalid_choice`) → form re-rendered `200`, the message under the template heading, announced. Failure → slot « Non enregistré, réessayer », buttons enabled again.

Open session — no form, nothing to start (one open session at a time): h1 « Séance en cours », the template name or « Séance libre » (weight 600), muted « Salle · commencée à 18:42 » and « Exercices : 2 · Séries : 7 » (rows with a live set; live sets), then the primary link-button « Reprendre la séance » → `/seances/{id}` (full width below 40rem). The phone page uses `main--message` + `.actions--thumb` with the header height of the two-row header (`.main--nav` sets `min-height: calc(100dvh - 2 * var(--target-min) - 1px)` below 40rem; `3 *` from L5, three-row header), so « Reprendre la séance » sits at the bottom of the screen.

Tab order: skip link, brand, nav, location chips, template buttons, « Séance libre ». Tab title `home.title` (« Accueil »). The L1a empty state (`home.empty_title`, `home.empty_text`) is removed.

### L4 — Session page (`GET /seances/{id}`, `templates/session.html`, `session_exercise.html`, `session_set_form.html`, `session_pending_menu.html`, `session_search.html`, `session_search_results.html`, `session_close_confirm.html`)

Task: log the set just done, exactly, then the next. Decision per set: confirm as prefilled, or adjust then confirm. Information: exercise and set number, prefilled values, set type, settings, sets already done today with their records.

**One current item.** The page is the plan in display order (template slots, then added exercises); every item is a one-line card except the current one, expanded in place. Current = `?exercice={row_id}` or `?menu={slot_id}` when valid, else the row of the latest live set, else the first item. A card is a link `/seances/{id}?exercice={row_id}#exercice-{row_id}` (menu: `?menu={slot_id}#menu-{slot_id}`).

```
360 px, current = Développé couché, 2 sets done        1280 px (one column, max 40rem)
+------------------------------+                       +--------------------------------------------------------------+
| Salle A — Squat & poussée    |  h1                   |    Salle A — Squat & poussée horizontale                     |
| horizontale                  |                       |    Salle · commencée à 18:42                                 |
| Salle · commencée à 18:42    |                       |    1 Squat au rack (barre)                                   |
| ---------------------------- |                       |      4 × 6–8 · Séries : 4 · Records : 1                      |
| 1 Squat au rack (barre)      |  card (link)          |    2 Développé couché (barre)                                |
|   4 × 6–8 · Séries : 4 ·     |                       |      4 × 6–8                                                 |
|   Records : 1                |                       |      Réglages : Banc 3                                ▸      |
| ---------------------------- |                       |      1  8 × 60 kg                        [ Modifier ]        |
| 2 Développé couché (barre)   |  current, h2          |      2  8 × 62,5 kg   ★ Record           [ Modifier ]        |
|   4 × 6–8                    |                       |      Série 3                                                 |
| Réglages : Banc 3          ▸ |  <details>            |      [Échauffement] [■ Travail] [Test RM]                    |
| 1  8 × 60 kg      [Modifier] |                       |      Répétitions          Charge (kg)                        |
| 2  8 × 62,5 kg    [Modifier] |                       |      [−] [   8   ] [+]    [−] [ 62,5 ] [+]                   |
|    ★ Record                  |                       |      Autres valeurs ▸                                        |
| Série 3                      |  h3                   |      [ ✓ Valider la série 3                              ]   |
| [Échauffement][■Travail]     |  chips                |      [ Suivant : Tirage horizontal                       ]   |
| [Test RM]                    |                       |    3 Tirage horizontal [Menu]                                |
| Répétitions                  |                       |      À choisir · 3 × 8–10                                    |
| [ − ] [      8      ] [ + ] |  56 px                 |    ...                                                       |
| Charge (kg)                  |                       |    [ Ajouter un exercice ]                                   |
| [ − ] [    62,5     ] [ + ] |                        |    [ Terminer la séance ]                                    |
| Autres valeurs             ▸ |  only with optional    +--------------------------------------------------------------+
| [ ✓ Valider la série 3     ] |  56 px, primary
| [ Suivant : Tirage horizon.] |  secondary link
| ---------------------------- |
| 3 Tirage horizontal  [Menu]  |
|   À choisir · 3 × 8–10       |
| 4 Jambes unilatéral  [Menu]  |
| 5 Curl barre EZ · 3 × 10–12  |
| 6 Gainage  [Menu]            |
| [   Ajouter un exercice  ▸ ] |
| [   Terminer la séance     ] |
+------------------------------+
```

At 1280 px the stepper fields of a block sit two per row from 40rem (`grid-template-columns: repeat(2, minmax(0, 1fr))`, gap `--space-4`); below 40rem one per row. Everything else is the same DOM.

**Page head.** h1 = template name, or « Séance libre »; muted `session.meta` « Salle · commencée à 18:42 » (local time in the session's zone).

**Plan** `<ol class="session-plan" id="seance-plan">` (the fragment answered by pick, add and change). Each `<li>`:

- Card of a row: `<a class="row session-card">` number (muted tabular, display order 1..n), name (weight 600, « Archivé » tag when archived), meta (muted `--text-sm`) parts joined by « · »: target (`Display.target`, slot rows only), « Séries : {n} » when n > 0, « Records : {n} » when n > 0.
- Card of a pending menu: number, menu name + tag « Menu », meta « À choisir » · target.
- The current item: `<li aria-current="step">` holding the expanded block below.

**Current exercise block** `<section class="session-block" id="exercice-{row}" aria-labelledby="exercice-{row}-titre">` (`session_exercise.html`, the fragment of ✓, edit and delete):

1. h2 `exercice-{row}-titre` the exercise name (+ « Archivé » tag); muted target line when the row comes from a slot with a target.
2. « Changer d’exercice » — only while the row holds no fact (no set, deleted included, no setting): `<details class="session-change">` with summary `.button` « Changer d’exercice »; inside, a `[data-request-scope]` with its slot, muted « Aucune série enregistrée : vous pouvez choisir un autre exercice. » and, for a menu row, the other available options as full-width buttons (`hx-patch …/exercices/{row}`, `name="exercise_id"`); for an added row, the search of « Ajouter un exercice » in change mode (`?ligne={row}`). Answer: the plan, this row current with the new exercise, focus on its ✓, « Exercice choisi : {name}. ». Refusal `exercise_has_sets` (a set was logged from another device): message in the slot area under the summary, focus on the summary.
3. Settings — only when the exercise has non-archived setting variables: `<details class="session-settings">`, summary (48 px, full width, chevron) « Réglages : Siège 4 · Dossier 2 » (`session.settings_summary`; a variable without value shows « — »). Inside, `<form hx-patch="/seances/{id}/exercices/{row}/reglages" hx-trigger="change" hx-target="this" hx-swap="outerHTML">`, slot first, hint « Enregistrés à chaque changement et repris à la prochaine séance. », then per variable: chips (`enum` ≤ 12 values, `bool`, discrete values) or a plain input (numbers, text: saved on `change`, i.e. when the field is left). No save button: a changed but unsaved setting would otherwise be replaced by the server's prefill at the first ✓. Saved → the form re-rendered with slot « Réglages enregistrés. » (`kind="ok"`), the summary text updated out of band, focus kept (same ids), same text announced. Refused → message under the input. The settings are prefilled values (D-062): they are shown, not asked.
4. Sets of today `<ol class="set-list">` (absent when none), heading visually hidden « Séries de la séance ». Each set row: number, `Display.set_text`, type tag « Échauffement » / « Test RM » (work sets carry none), « Record » tag when ⭐ (recomputed on every render), and `<details class="set-row__edit">` with `<summary class="button" id="serie-{id}-modifier">` « Modifier » + visually hidden « la série {n} ».
5. Next-set form (`session_set_form.html`, below), ending with the block's action bar.

**Set texts** (`Display.set_text`, values through `Display.value`, durations `m:ss`):

| Fields of the set | Text |
|---|---|
| reps and load | « 8 × 62,5 kg » (no-break spaces around ×) |
| reps only | « 12 rép. » |
| duration (hold, round) | « 0:45 » |
| duration and distance (cardio) | « 30:00 · 5,2 km » |
| load only | « 24 kg » |
| + measure variables | « 30:00 · 5,2 km · Résistance 8 » (`session.set.variable`; `enum` by label, `bool` « Oui » / « Non ») |

**Next-set form** `<form class="set-form" id="exercice-{row}-serie" data-request-focus="trigger" hx-post="/seances/{id}/series" hx-target="#exercice-{row}" hx-swap="outerHTML show:#exercice-{row}-actions:bottom" hx-disabled-elt="#exercice-{row}-serie button">`, children in order:

1. (No slot here: the form's status slot (D-053) sits in the action bar right after the ✓, item 6, so a failure message never pushes the ✓ below the fold; L4 fix loop 1, the one exception to "slot first".)
2. Hidden `session_exercise_id`. h3 « Série {n} » (`intervals`: « Tour {n} »), `n` = live sets + 1.
3. Set type: `fieldset.chips.chips--row`, legend visually hidden « Type de série », radios `name="type"` « Échauffement » (`warmup`) / « Travail » (`work`) / « Test RM » (`rm_test`, `strength` only), checked from the prefill. (« Échauffement » + « Travail » + « Test RM » ≈ 321 px of 328 at 360 px; a wider font wraps the third chip.)
4. Fields in `exercise_field` order, required fields and core quantities visible:
   - numeric with an increment → stepper; « − » `id="exercice-{row}-{field}-moins"`, « + » `…-plus`, `type="button"`, `name="pas" value="{field}:down|up"`, `hx-get="/seances/{id}/exercices/{row}/serie"`, `hx-include="closest form"`, `hx-target="#exercice-{row}-serie"`, `hx-swap="outerHTML"`, `hx-sync="closest form:replace"`, `hx-disabled-elt="#exercice-{row}-valider"`, `aria-label` « Diminuer {field} de {step} » / « Augmenter {field} de {step} » (« Augmenter Charge de 2,5 kg »). « − » is `disabled` at 0.
   - discrete values → chips (« 16 », « 20 », « 24 », legend « Charge (kg) »); a prefilled value outside the list is an extra checked chip at its sorted place.
   - numeric with neither → plain `.input` (keyboard).
   - `bool`, `enum` → chips (or select); `text` → input, `maxlength="40"`.
   - Field names: `{field}` = `reps`, `weight`, `duration`, `distance` or `var_{id}`; input ids `exercice-{row}-{field}`.
   - A required field left empty by the prefill (first use, no default) carries the hint « Première fois : saisissez la valeur. »: the keyboard fallback of D-062.
5. Optional variables in `<details class="set-form__more">`, summary (chevron, as the settings summary) « Autres valeurs » or « Autres valeurs : Résistance 8 » (the current values); rendered `open` when the step that produced it targeted one of its fields or a refusal is inside.
6. Action bar, last child of the form, `<div class="session-block__actions" id="exercice-{row}-actions">`: the ✓ `<button type="submit" class="button button--primary button--confirm" id="exercice-{row}-valider">` « Valider la série {n} » (`intervals`: « Valider le tour {n} »), then the form's status slot (hidden while empty; « Non enregistré, réessayer » lands right under the ✓, scrolled fully into view if it is not, and the focus stays on the ✓ so the retry is one more tap in place: `data-request-focus="trigger"`, L4 fix loop 2), then the secondary link-button « Suivant : {name} » (the next item's card URL) or, on the last item, the secondary `type="button"` « Terminer la séance » (`hx-get="/seances/{id}/cloture" hx-target="#fin-de-seance" hx-swap="outerHTML show:#fin-de-seance:bottom" hx-disabled-elt="this"`).

Layout by category (template branches only):

| Category | Form fields (usual) | Set row | Heading / ✓ |
|---|---|---|---|
| `strength`, `kettlebell` | Répétitions stepper, Charge stepper or chips (16 · 20 · 24 kg) | « 8 × 62,5 kg » | « Série 3 » / « Valider la série 3 » |
| `bodyweight` | Répétitions stepper (+ Charge when weighted) or Durée stepper (plank) | « 12 rép. », « 10 × 10 kg », « 0:45 » | same |
| `cardio` | Durée stepper, Distance stepper (+ Résistance in « Autres valeurs ») | « 30:00 · 5,2 km » | same |
| `intervals` | Durée (work) stepper | « 0:30 » with number = round | « Tour 4 » / « Valider le tour 4 » |

**Edit / delete a confirmed set** (inside `set-row__edit`; open, the `<details>` spans the row's first line over the number and the text, so « Modifier » does not move, and the form takes the full width under it; the action column is at least `calc(var(--target-min) * 2 + var(--space-4))` wide so the text keeps its width, L4 fix loop 2): `<form class="set-edit" id="serie-{id}-form" hx-patch="/series/{id}" hx-target="#exercice-{row}" hx-swap="outerHTML" hx-disabled-elt="#serie-{id}-form button">`, slot first, type chips, every field as plain input or chips (no steppers: a correction is rare and the keyboard is accepted there), optional fields visible, `.actions--inline` primary « Enregistrer » and danger « Supprimer la série » (`hx-delete="/series/{id}"`, same target; no confirmation: soft delete, the set can be logged again, D-061/§6). Saved → `<details>` closed, row text and stars recomputed, focus on its « Modifier », « Série 2 modifiée. ». Deleted → row gone, rows renumbered, next form's number updated, focus on the next row's « Modifier » (else the previous one's, else the ✓), « Série 2 supprimée. ». Refused → the row's `<details open>`, messages under the inputs, focus on the first invalid one.

**Current pending menu** `<section class="session-block" id="menu-{slot}">` (`session_pending_menu.html`): h2 menu name + tag « Menu », muted target, muted « Choisissez l’exercice du jour. », then `<form class="menu-pick" id="menu-{slot}-choix" hx-post="/seances/{id}/exercices" hx-target="#seance-plan" hx-swap="outerHTML show:.session-block:top" hx-disabled-elt="#menu-{slot}-choix button">` (slot first, hidden `slot_id`) with one full-width submit button per available option in menu order (`name="exercise_id" value="{id}"`: json-enc sends the submitter, as the home start form), name weight 600, 56 px. The plan has a single `.session-block` (the current item), so `show:.session-block:top` scrolls the new block to the top. One tap. Then « Suivant : {name} » as for a row (skipping a menu is allowed: it stays « À choisir »). Refused (`slot_already_picked`: picked from another device; `exercise_unavailable`) → the plan re-rendered with the message in this menu's slot and focus on its first button (or on the row now holding the slot).

**Add an exercise** `<details class="session-add" id="ajout">` after the plan (rendered `open` when the plan is empty): summary `.button` full width « Ajouter un exercice ». Inside:

- Search form as L2 (`role="search"`, plain `GET` fallback, `hx-get="/seances/{id}/recherche"`, `hx-target="#ajout-resultats"`, same triggers, slot with `data-message` = `error.search_failed`), label « Rechercher un exercice », hint `exercises.search_hint`. No autofocus (it would open the keyboard: the nominal path is the list).
- `<div id="ajout-resultats" data-request-scope>` (outside the search form, so a failed add shows « Non enregistré, réessayer », not the search text): slot first; q empty → h3 « Récents » (up to 20, newest first) then h3 « Tous les exercices » (the rest by name), each hidden when empty; q not empty → one ranked list. Each result is a `<button class="row session-result" name="exercise_id" value="{id}" hx-post="/seances/{id}/exercices" hx-target="#seance-plan" hx-swap="outerHTML show:.session-block:top" hx-disabled-elt="this">`: name (600), meta category · equipment. Rendered with the page for q empty (no request to open it). Change mode (`?ligne={row}`): same rows, `hx-patch="…/exercices/{row}"`.
- No match: `exercises.no_match` + `exercises.no_match_hint`; empty catalog: `exercises.empty_title` and a link « Nouvel exercice » → `/exercices/nouveau`. Results count announced as L2.
- Added → the plan with the new row current (last), focus on its ✓, « Exercice ajouté : {name}. », `<details>` closed.

**Close** `<section id="fin-de-seance" class="section" data-request-scope>` at the end: slot, secondary « Terminer la séance » (full width below 40rem), `hx-get="/seances/{id}/cloture"`, `hx-target="#fin-de-seance"`, `hx-swap="outerHTML show:#fin-de-seance:bottom"`, `hx-disabled-elt="#fin-de-seance button"`. The confirmation (`.confirm.confirm--neutral`, `role="group"`): « Terminer la séance ? », « Vous ne pourrez plus y ajouter de séries. », when some items have no live set « Exercices sans série : {count}. », then « Annuler » (`autofocus`, `hx-disabled-elt="#fin-de-seance button"`, `?annuler=1` puts the block back, focus on « Terminer la séance ») and primary « Terminer » (`hx-post="/seances/{id}/cloture"` → `HX-Redirect: /seances/{id}`, the summary).

States of the session page:

| State | What the user sees | Focus / announcement |
|---|---|---|
| Fresh from a template | first item current, no set; fixed slots as cards, menus « À choisir » | — |
| Free session / no item | `.empty` « Aucun exercice pour l’instant. » + muted « Ajoutez un exercice ci-dessous. »; « Ajouter un exercice » open | — |
| Resumed (reload, home) | the same state rebuilt from the database; current = row of the latest set | — |
| Stepping | the value changes in place; ✓ disabled until the answer (< 100 ms on the LAN) | focus kept on « + » / « − » |
| Confirming | every button of the form disabled (50 %), labels unchanged | — |
| Confirmed | new set row (with « Record » when ⭐), form for set n + 1 prefilled, action bar scrolled to the bottom of the viewport | the ✓; « Série 3 enregistrée : 8 × 62,5 kg. » (+ « Nouveau record. ») |
| Refused input | block re-rendered `200`, values kept, message under each field (`aria-invalid`, `aria-describedby`), « Renseignez au moins une valeur. » for an empty set (under the h3, on the form) | first invalid input; first message |
| Request failed (5xx, network, 10 s timeout, 404 of a row deleted elsewhere) | nothing changed, values as typed, « Non enregistré, réessayer » in the form's slot right under the ✓ (fully in view), ✓ enabled again | D-053 refinement (L4 fix loop 2): the ✓ for a failed ✓, the « + » / « − » for a failed step; same text |
| Session closed meanwhile (other device) | `HX-Redirect: /seances/{id}?terminee=1`: the summary with the notice « Cette séance est terminée : la dernière action n’a pas été enregistrée. » | notice `role="alert"` |
| Archived exercise in a row | « Archivé » tag; logging works | — |
| Archived variable | hidden, never sent | — |
| Unknown, foreign or deleted session | L1a 404 page | — |
| Page failure | L1a 500 page | — |

Tab order: skip link, brand, nav, cards and the current block in plan order (inside the block: « Changer d’exercice », settings summary, each « Modifier », type chips, each field (−, input, +), « Autres valeurs », ✓, « Suivant »), « Ajouter un exercice », « Terminer la séance ». Tab title: the h1 text (`{page}`).

### L4 — Session summary (`GET /seances/{id}` of a closed session, `templates/session_summary.html`)

Task: see what was done. Information: when and how long, per exercise the counted sets, volume and records, the totals.

```
360 px                                   1280 px
+------------------------------+         +--------------------------------------------------------------+
| Salle A — Squat & poussée    |         |    Salle A — Squat & poussée horizontale                     |
| horizontale                  |         |    Séance terminée · Salle                                   |
| Séance terminée · Salle      |         |    03/11/2026 · 18:42–19:51 · 1 h 09                          |
| 03/11/2026 · 18:42–19:51 ·   |         |    +-----------+-----------+-------------+-----------+       |
| 1 h 09                       |         |    | 6         | 22        | 8450 kg     | 2         |       |
| +-----------+-----------+    |         |    | Exercices | Séries    | Volume      | Records   |       |
| | 6         | 22        |    |         |    +-----------+-----------+-------------+-----------+       |
| | Exercices | Séries    |    |         |    Squat au rack (barre)                                     |
| +-----------+-----------+    |         |    Séries : 4 · Échauffements : 2 · Volume : 1920 kg ·     |
| | 8450 kg   | 2         |    |         |    Records : 1                                               |
| | Volume    | Records   |    |         |    1 8 × 40 kg [Échauffement] ...                            |
| +-----------+-----------+    |         |    ...                                                       |
| Squat au rack (barre)        |         |    [ Retour à l’accueil ]                                    |
| Séries : 4 · Échauffements : |         +--------------------------------------------------------------+
| 2 · Volume : 1920 kg ·       |
| Records : 1                  |
| 1 8 × 40 kg   [Échauffement] |
| 3 8 × 62,5 kg  ★ Record      |
| ...                          |
| [   Retour à l’accueil     ] |
+------------------------------+
```

- h1 template name or « Séance libre »; muted « Séance terminée · Salle »; muted `Display.local_date` · start–end `Display.local_time` · duration (`Display.duration_compact`: summaries are read at a glance like targets; set rows keep `m:ss`).
- Totals `<dl class="summary-totals">`: tiles (2 × 2 below 40rem, 4 in a row from 40rem; `--color-surface`, `--radius-md`, padding `--space-3`): figure `--text-2xl` weight 600 tabular, label muted `--text-sm` under it: « Exercices » (rows with at least one live set), « Séries » (live work and RM-test sets), « Volume » (Σ load volume, `Display.value` kg; tile absent when 0), « Records ».
- Per exercise with a live set, in plan order, `<section>` h2 name, muted meta parts joined by « · »: « Séries : {n} » (when > 0), « Échauffements : {n} » (when > 0), the volume of its category (only its non-zero parts, none without a counted set: a warm-up-only exercise reads « Échauffements : 2 »), « Records : {n} » (when > 0). Then the read-only set rows (number, text, tags; no « Modifier »: correction is L5).

| Category | Volume meta |
|---|---|
| `strength`, `kettlebell` | « Volume : 1920 kg » |
| `bodyweight` | « Répétitions : 36 », + « Volume : 360 kg » when weighted, « Durée : 1 min 30 » for holds |
| `cardio` | « Distance : 5,2 km · Durée : 30 min » |
| `intervals` | « Tours : 8 · Durée : 4 min » |

- No set at all: `.empty` « Aucune série enregistrée. ».
- `?terminee=1`: the notice `.form-status[data-kind="error"]` `role="alert"` under the meta.
- Action: primary link-button « Retour à l’accueil » (`.actions`, full width below 40rem). Tab title `session.summary_title` « Séance terminée ».

### L4 — Tap counts (browser test, WebKit 360 px)

Counted by the `Taps` helper (every click; any `fill` / `type` / `press` fails the nominal path). Preconditions: one earlier « Salle A » session at the gym with history and settings on « Presse à cuisses ».

| Action | Taps | Sequence | Target |
|---|---|---|---|
| Start « Salle A », place preselected | 1 | template button | ≤ 3 |
| Start with the other place | 2 | « Maison », template | ≤ 3 |
| Resume from home | 1 | « Reprendre la séance » | — |
| Confirm an unchanged set | 1 | ✓ | 1 |
| Confirm after one step | 2 | « + », ✓ | ≤ 3 |
| Confirm after two steps or two fields | 3 | « + », « + », ✓ | ≤ 3 |
| Confirm with another discrete load | 2 | chip, ✓ | ≤ 3 |
| Confirm a warm-up set (type changed) | 2 | « Échauffement », ✓ | ≤ 3 |
| Go to the next exercise | 1 | « Suivant : … » | — |
| Go to a pending menu and pick | 2 | « Suivant : … », option | — |
| Pick in the current menu | 1 | option | — |
| Add a recent exercise | 2 | « Ajouter un exercice », result | — |
| Change a setting chip | 2 | settings summary, chip | — |
| Delete a set | 2 | « Modifier », « Supprimer la série » | — |
| Edit a set (keyboard allowed: correction) | 3 + typing | « Modifier », field, « Enregistrer » | — |
| Close from the last exercise | 2 | « Terminer la séance », « Terminer » | — |

The test also checks at 360 × 640: after each ✓ the next ✓ is inside the viewport's lower half; every target ≥ 48 × 48 px; no horizontal scroll; during the ✓ request the ✓ is disabled; on an aborted ✓ (`page.route` abort) the values stay, « Non enregistré, réessayer » is shown and the ✓ is enabled.

### L4 — Style (`components.css`, `pages/home.css`, `pages/session.css`)

- `components.css`: `.chips`, `.chip`, `.chip__input` (visually hidden radio), `.confirm--neutral` (`--color-border` border).
- `pages/home.css` (replaces the L1a rules): `.start` (column, gap `--space-4`, max `--text-max`), `.start__template` (full width, `justify-content: flex-start`, text left, `min-height: 4rem`, padding `--space-3` `--space-4`, wraps), the place switch, `.main--nav` (below 40rem `min-height: calc(100dvh - 2 * var(--target-min) - 1px)`, flex column) for the resume state with `.actions--thumb`.
- `pages/session.css`: `.session-plan` (list, divider between items), `.session-card` (L2 `.row`), `.session-block` (column, gap `--space-4`, padding-block `--space-4`), `.set-list`, `.set-row` (grid `2ch minmax(0, 1fr) auto`, gap `--space-2`, `align-items: center`; `.set-row__edit` in column 3, `[open]` on `1 / -1` with its summary `margin-inline-start: auto`, the edit form full width below), `.session-settings__summary` (flex, 48 px; the native marker is hidden and a muted `::before` chevron « ▸ » / « ▾ » when open, alt text empty), `.set-form` (column, gap `--space-4`; fields in a 2-column grid from 40rem), `.stepper`, `.stepper__row`, `.stepper__button`, `.stepper__input`, `.button--confirm`, `.session-block__actions` (column, gap `--target-gap`, full width), `.tag--record`, `.session-add` and `.session-result` (button reset to the `.row` look, full width, left aligned), `.summary-totals` (grid 2 columns, 4 from 40rem, gap `--space-2`).
- Page width: home and session pages one column, `max-width: var(--text-max)`. Long names wrap (`overflow-wrap: anywhere`); never an ellipsis.
- 360 px check: the longest seed names (« Tirage horizontal poulie », « Relevé de jambes suspendu », « Salle B — Charnière & poussée verticale »), three set-type chips, a 10-value « Siège » chip group (two rows) and an open set edit fit without horizontal scroll.

### L4 — Strings (`web/locales/fr.json`)

Same typography as L2 / L3: typographic apostrophes; a no-break space (U+00A0) before « : », « ? », « ! », inside « » guillemets, between a number and its unit, and on both sides of « × ». Times are joined by an en dash without spaces (« 18:42–19:51 »).

| Key | Text |
|---|---|
| `home.start_title` | Nouvelle séance |
| `home.location_legend` | Lieu |
| `home.templates_heading` | Séance type |
| `home.last_used` | Dernière séance |
| `home.free_session` | Séance libre |
| `home.free_session_hint` | Sans séance type : vous ajoutez les exercices un à un. |
| `home.no_template_gym` | Aucune séance type pour la salle. |
| `home.no_template_home` | Aucune séance type pour la maison. |
| `home.open_title` | Séance en cours |
| `home.open_counts` | Exercices : {exercises} · Séries : {sets} |
| `home.resume` | Reprendre la séance |
| `session.free_title` | Séance libre |
| `session.meta` | {location} · commencée à {time} |
| `session.item_sets` | Séries : {count} |
| `session.item_records` | Records : {count} |
| `session.menu_pending` | À choisir |
| `session.menu_intro` | Choisissez l’exercice du jour. |
| `session.change_exercise` | Changer d’exercice |
| `session.change_intro` | Aucune série enregistrée : vous pouvez choisir un autre exercice. |
| `session.settings_summary` | Réglages : {values} |
| `session.no_value` | — |
| `session.settings_hint` | Enregistrés à chaque changement et repris à la prochaine séance. |
| `session.settings_saved` | Réglages enregistrés. |
| `session.sets_heading` | Séries de la séance |
| `session.set_named` | la série {n} |
| `session.set.reps_weight` | {reps} × {weight} |
| `session.set.reps` | {reps} rép. |
| `session.set.variable` | {label} {value} |
| `session.set_type_legend` | Type de série |
| `session.set_type.warmup` | Échauffement |
| `session.set_type.work` | Travail |
| `session.set_type.rm_test` | Test RM |
| `session.record` | Record |
| `session.next_set` | Série {n} |
| `session.next_round` | Tour {n} |
| `session.field_unit` | {field} ({unit}) |
| `session.step_down` | Diminuer {field} de {step} |
| `session.step_up` | Augmenter {field} de {step} |
| `session.first_value_hint` | Première fois : saisissez la valeur. |
| `session.more_fields` | Autres valeurs |
| `session.more_fields_values` | Autres valeurs : {values} |
| `session.confirm_set` | Valider la série {n} |
| `session.confirm_round` | Valider le tour {n} |
| `session.next_item` | Suivant : {name} |
| `session.delete_set` | Supprimer la série |
| `session.add_exercise` | Ajouter un exercice |
| `session.recent_heading` | Récents |
| `session.all_heading` | Tous les exercices |
| `session.empty_title` | Aucun exercice pour l’instant. |
| `session.empty_text` | Ajoutez un exercice ci-dessous. |
| `session.close` | Terminer la séance |
| `session.close_confirm_title` | Terminer la séance ? |
| `session.close_confirm_text` | Vous ne pourrez plus y ajouter de séries. |
| `session.close_unlogged` | Exercices sans série : {count}. |
| `session.close_confirm` | Terminer |
| `session.announce_set_saved` | Série {n} enregistrée : {text}. |
| `session.announce_set_record` | Série {n} enregistrée : {text}. Nouveau record. |
| `session.announce_set_updated` | Série {n} modifiée. |
| `session.announce_set_deleted` | Série {n} supprimée. |
| `session.announce_picked` | Exercice choisi : {name}. |
| `session.announce_added` | Exercice ajouté : {name}. |
| `session.summary_title` | Séance terminée |
| `session.summary_meta` | Séance terminée · {location} |
| `session.summary_when` | {date} · {start}–{end} · {duration} |
| `session.total_exercises` | Exercices |
| `session.total_sets` | Séries |
| `session.total_volume` | Volume |
| `session.total_records` | Records |
| `session.summary.sets` | Séries : {count} |
| `session.summary.warmups` | Échauffements : {count} |
| `session.summary.records` | Records : {count} |
| `session.summary.volume` | Volume : {value} |
| `session.summary.reps` | Répétitions : {count} |
| `session.summary.duration` | Durée : {value} |
| `session.summary.distance` | Distance : {value} |
| `session.summary.rounds` | Tours : {count} |
| `session.summary_empty` | Aucune série enregistrée. |
| `session.closed_notice` | Cette séance est terminée : la dernière action n’a pas été enregistrée. |
| `date.numeric` | {day}/{month}/{year} |
| `catalog.error.empty_set` | Renseignez au moins une valeur. |
| `catalog.error.template_unavailable` | Séance type archivée ou introuvable : choisissez-en une autre. |
| `catalog.error.slot_already_picked` | Un exercice est déjà choisi pour ce menu. |
| `catalog.error.exercise_has_sets` | Des séries ou réglages sont enregistrés : l’exercice ne peut plus être changé. |

Removed: `home.empty_title`, `home.empty_text` (L1a placeholder). Implementation notes (L4 developer): the chip list of a discrete, `bool` or `enum` field is built by `Display.choices` (an optional field gets a « — » chip first, a value off the list is appended last); the change-exercise search of an added row loads on the first opening of its `<details>` (`hx-trigger="toggle once"`, no script); the « Exercices » tile counts exercises with a live set; « Récents » includes the exercises of the current session. The L4 forms disable every button of the form through an id selector (`#exercice-{row}-serie button`, `#demarrer button`, `#serie-{id}-form button`, `#menu-{slot}-choix button`, `#fin-de-seance button`), never `find button`: htmx's `find` takes the first match only, which on the set form is the « − » stepper, not the ✓. The older forms (L1b to L3) follow the same rule from L6 (L6 — Forms disable every button). Reused: `home.title`, `exercise.location.gym` / `.home` (place words), `template.tag_menu`, `tag.archived_m`, `action.edit`, `action.save`, `action.cancel`, `action.home`, `templates.new`, `exercises.search_label`, `exercises.search_hint`, `exercises.no_match`, `exercises.no_match_hint`, `exercises.empty_title`, `exercises.new`, `exercises.results`, `error.search_failed`, `error.not_saved`, `quantity.*`, `unit.*`, `field.yes` / `field.no`, `duration.compact.*`, `catalog.error.required`, `catalog.error.too_long`, `catalog.error.invalid_choice`, `catalog.error.exercise_unavailable`, the `domain/units` codes. Problem codes of L4 use the one `catalog.error.<code>` prefix of `web/forms.form_errors` (the design note's `session.error.*` placeholder is not used). `date.numeric` takes two-digit `{day}` and `{month}`. `session_closed` has no message: it is a redirect, and the summary shows `session.closed_notice`.

### L5 — Tokens, components and header (`tokens.css`, `components.css`, `_nav.html`)

Design reasons: design note `docs/architecture/2026-11-03-l5-tracking.md`, "UI design". No new breakpoint.

New tokens (chart series; each ≥ 4.5:1 on bg and surface, so text-grade and above the 3:1 non-text rule):

| Token | Light | Dark | Light on bg / surface | Dark on bg / surface |
|---|---|---|---|---|
| `--chart-1` | `#0b57b8` | `#7cb0ff` | 6.84 / 6.22 | 8.28 / 7.31 |
| `--chart-2` | `#b04a00` | `#ffa25c` | 5.49 / 4.99 | 9.21 / 8.13 |
| `--chart-3` | `#1f7a3a` | `#5fd38a` | 5.38 / 4.89 | 9.73 / 8.59 |
| `--chart-4` | `#9c2f8f` | `#f08ad8` | 6.53 / 5.93 | 8.13 / 7.17 |
| `--chart-5` | `#00707a` | `#4fd1d9` | 5.84 / 5.30 | 9.98 / 8.81 |
| `--chart-6` | `#5b5f00` | `#d9d55a` | 6.81 / 6.19 | 11.86 / 10.47 |

Series *i* always pairs colour `--chart-{i}` with a shape (Chart.js `pointStyle`: circle, rectRot, rect, triangle, crossRot, star; legend glyphs « ● ◆ ■ ▲ ✕ ★ »): never colour alone.

| Component | Markup | Look |
|---|---|---|
| Data table | `<table class="data-table">` with `<caption>` (visible or `.visually-hidden`), `<th scope="col">`, first cell of a row `<th scope="row">` | `--text-sm`, full width, cells padding `--space-2` `--space-2`, `--color-divider` line between rows, header muted weight 600; numeric columns `.num` (right, tabular); no cell wraps a number and its unit (no-break space). Wrapped in `<div class="data-table__scroll" role="region" tabindex="0" aria-labelledby="{caption id}">` with `overflow-x: auto`: the last fallback for a very wide font; the 360 px layout must not need it (browser check) |
| Inline link | `<a class="inline-link">` | a text link as a 48 px target: `display: inline-flex; align-items: center; min-height: var(--target-min)`, underlined, accent |
| Chip grid | `.chips.chips--grid6` | `display: grid; grid-template-columns: repeat(6, minmax(var(--target-min), 1fr))`, gap `--target-gap`: 6 × 48 + 5 × 8 = 328 px, two exact rows of six at 360 |
| Success notice on a page | `<p class="form-status" data-kind="ok" role="status">` | the slot look, outside a form (after a redirect) |

**Header (replaces the L3 phone layout).** Five links in two groups:

```
360 px (below 40rem: three rows)       1280 px (one row)
+------------------------------+       +--------------------------------------------------------------------------+
| Rack Overflow                | 48    |  Rack Overflow     Historique  Progression    Exercices  Variables  Séances types |
| Historique  Progression      | 48    |                    ~~~~~~~~~~                                              |
| ~~~~~~~~~~                   |       +--------------------------------------------------------------------------+
| Exercices  Variables  Séances| 48
| types (one line)             |
+------------------------------+
```

- `_nav.html`: one `<nav>` (unchanged label), two `<ul class="site-nav__list">`: first `site-nav__list--tracking` with « Historique » → `/historique` (`section = "history"`) and « Progression » → `/progression` (`section = "progress"`), then « Exercices », « Variables », « Séances types » as in L3. Link look unchanged (L2).
- Below 40rem: `.site-nav` takes its own row (`flex-basis: 100%`, L3) and is a column of the two lists, each a 48 px row, gap `--space-4` between links (row 2: 80 + 16 + 95 = 191 px; row 3: 302 px, of 328). Each list keeps `flex-wrap: wrap` (a very wide font adds a row, never a horizontal scroll). Header height on the phone: 145 px (3 × 48 + divider), not sticky; nothing fixed at the bottom of the screen.
- From 40rem: brand left, both lists on one row on the right, `--space-6` between the lists, `--target-gap` between links, links padded `--space-2`; ≈ 715 px in all, so one row from ≈ 760 px; below that the header wraps the whole nav to a second row (L2 fallback).
- `aria-current="page"`: « Historique » on `/historique` and on a closed session's page (the history detail); « Progression » on `/progression` and `/progression/{id}`; nothing on `/reglages`, home and an open session.
- Home (L4 resume state): `.main--nav` becomes `min-height: calc(100dvh - 3 * var(--target-min) - 1px)` below 40rem.
- Tab order: skip link, brand, « Historique », « Progression », « Exercices », « Variables », « Séances types », main.

### L5 — History (`GET /historique`, `templates/history.html`, `templates/history_page.html`)

Task: find a session to check or correct it; see whether training is regular. Decision: which session to open. Information: weekday and date, template, place, size, exercises; sessions per week.

```
360 px                                  1280 px (column max 40rem for the week chart, list full content width)
+------------------------------+        +---------------------------------------------------------------------+
| (header, 3 rows)             |        | (header)                                                            |
+------------------------------+        +---------------------------------------------------------------------+
| Historique                   |  h1    |  Historique                                                         |
| Séance supprimée.            |  ?supprimee=1 only                                                           |
| Régularité                   |  h2    |  Régularité                                                         |
| Cette semaine : 2            |        |  Cette semaine : 2                                                  |
| Séances par semaine, moyenne |        |  Séances par semaine, moyenne sur 12 semaines : 2,8                 |
| sur 12 semaines : 2,8        |        |   3  2  4  3  0  3  2  3  4  3  3  2                                 |
|  3 2 4 3 0 3 2 3 4 3 3 2     |        |   █  ▆  █  █  _  █  ▆  █  █  █  █  ▒                                 |
|  █ ▆ █ █ _ █ ▆ █ █ █ █ ▒     |  56 px |  18/08 25/08 ...                                 10/11              |
| 12 dernières semaines, la    |        |  12 dernières semaines, la semaine en cours à droite.               |
| semaine en cours à droite.   |        |                                                                     |
| Novembre 2026                |  h2    |  Novembre 2026                                                      |
| Salle A — Squat & poussée    |  row   |  lun. 03/11 · 18:42   Salle A — Squat & poussée horiz.  Séries : 22 |
| horizontale     [En cours]   |        |  Salle                Squat au rack · Développé couché  8450 kg      |
| lun. 03/11 · 18:42 · Salle   |        |  ...                                                                |
| Séries : 22 · Volume :       |        |  [ Plus anciennes ]                                                 |
| 8450 kg                      |        +---------------------------------------------------------------------+
| Squat au rack (barre) ·      |
| Développé couché (barre) · … |
| ---------------------------- |
| ...                          |
| [      Plus anciennes      ] |
+------------------------------+
```

- h1 « Historique ». After a session delete (`?supprimee=1`): « Séance supprimée. » (L5 success notice) under the h1.
- **Régularité** `<section class="section" aria-labelledby="regularite-titre">`, shown when the user has at least one session: « Cette semaine : {count} », « Séances par semaine, moyenne sur 12 semaines : {value} » (`Display.decimal1`, one decimal, comma; the wording avoids singular / plural agreement), then the week chart `<ol class="week-chart" aria-label="Séances par semaine, 12 dernières semaines">`, oldest first, 12 `<li>`: the count (visible, tabular, centred, `--text-sm`), a decorative bar `<span class="week-chart__bar week-chart__bar--{0..7}" aria-hidden="true">` (heights 2, 8, 16, … 56 px; 7 = « 7 et plus »; 0 is a 2 px `--color-divider` line so empty weeks show), and the week label: visually hidden below 40rem, shown under the bar from 40rem (`Display.week`, « 27/10 », muted `--text-sm`). Each `<li>` carries the accessible text « Semaine du 27/10 : 3 » (« Semaine du 10/11 (en cours) : 2 » for the current week). Bars `--color-accent`; the current week's bar is outlined (1 px accent border, `--color-surface` fill) and the caption under the chart says « 12 dernières semaines, la semaine en cours à droite. » (position and text carry the meaning). 12 equal columns, gap `--space-1`: ≈ 23 px each at 360.
- **List**: one `<section aria-labelledby>` per month, `h2` « Novembre 2026 » (`Display.month`, first letter capitalised by CSS), then `<ul class="rows history-list">`. Each item one `<a class="row history-item" href="/seances/{id}">`:
  - `.row__title`: template name or « Séance libre » (wraps), tag « En cours » for an open session;
  - meta line 1: « lun. 03/11 · 18:42 · Salle » (`history.item_when` + place; a no-break space before the place's « · », so the line never ends with one);
  - meta line 2: « Séries : 22 · Volume : 8450 kg » (counted sets; volume only when > 0), or « Aucune série » for a session with no live set; each count is a `.history-item__count` that never wraps inside (« Volume : » stays with its value), the « · » a `.history-item__sep` between them;
  - meta line 3: names of the exercises with a live set, joined by a no-break space + « · » + space, so a wrapped line never starts with « · » (never an ellipsis); absent when none.
  - From 40rem: grid `9rem minmax(0, 1fr) 10rem`: when and place | title and exercise names | counts right aligned, tabular, one count per line (`.history-item__sep` hidden).
- **« Plus anciennes »**: `<div id="historique-suite" data-request-scope>` with the slot, then `<a class="button" href="/historique?avant={id}" hx-get="/historique?avant={id}" hx-target="#historique-suite" hx-swap="outerHTML" hx-disabled-elt="this">` (full width below 40rem). The answer appends the next ≤ 20 items: a month already started on screen continues as a heading-less `.rows` list right under it; a new month gets its `h2`. The first new link has `autofocus`; « Séances chargées : {count} » is announced. Absent on the last page. Without htmx it is a plain link to the next page, which always starts with its month heading.

States:

| State | What the user sees | Focus / announcement |
|---|---|---|
| No session at all | `.empty` « Aucune séance pour l’instant. » + muted « Les séances apparaîtront ici dès la première. » + link-button « Nouvelle séance » → `/`; no Régularité section | — |
| Sessions, none in 12 weeks | the chart with 12 zero lines, « Cette semaine : 0 », average « 0,0 » | — |
| One page or less | list, no « Plus anciennes » | — |
| Loading the next page | button disabled, no spinner (< 1 s) | — |
| Next page failed | « Non enregistré, réessayer » in the `#historique-suite` slot, button enabled | the button (trigger outside a form) |
| After a delete | « Séance supprimée. » under the h1; the session is gone from the list and the chart | notice `role="status"` |
| Page failure | L1a 500 page | — |

Tab order: skip link, header, session links in order, « Plus anciennes ». The week chart has no tab stop (text, not controls). Tab title `history.title`.

Implementation notes (L5 developer): « Régularité » is shown on the first page only (a plain-link page `?avant=` starts with its month heading and the list); each week `<li>` holds its accessible text in a visually hidden span, the count, bar and week label are `aria-hidden`; a malformed `?avant=` is a 422.

### L5 — Session detail and corrections (`GET /seances/{id}` closed, `session_summary.html`, `session_detail_exercise.html`, `session_delete_confirm.html`)

Task: fix a set or a setting logged wrong; delete a session that should not exist. Decision: which set; delete or not. Information: every live set with type tag and ⭐, the settings, the totals.

```
360 px                                   1280 px (one column, max 40rem)
+------------------------------+         +--------------------------------------------------------------+
| Salle A — Squat & poussée    |         |    Salle A — Squat & poussée horizontale                     |
| horizontale                  |         |    Séance terminée · Salle                                   |
| Séance terminée · Salle      |         |    03/11/2026 · 18:42–19:51 · 1 h 09                          |
| 03/11/2026 · 18:42–19:51 ·   |         |    [ 6 Exercices ][ 22 Séries ][ 8450 kg Volume ][ 2 Records ]|
| 1 h 09                       |         |    Squat au rack (barre)                                     |
| [6 Exercices][22 Séries]     |         |    Séries : 4 · Échauffements : 2 · Volume : 1920 kg          |
| [8450 kg Vol.][2 Records]    |         |    Voir la progression                                        |
| Squat au rack (barre)        |  h2     |    Réglages : Barre 5                                    ▸   |
| Séries : 4 · Échauffements : |         |    1  8 × 40 kg  [Échauffement]                [ Modifier ]   |
| 2 · Volume : 1920 kg         |         |    3  8 × 62,5 kg ★ Record                     [ Modifier ]   |
| Voir la progression          |  48 px  |    ...                                                       |
| Réglages : Barre 5         ▸ |         |    [ Retour à l’accueil ]                                    |
| 1  8 × 40 kg      [Modifier] |         |                                                              |
|    [Échauffement]            |         |    [ Supprimer la séance ]                                   |
| 3  8 × 62,5 kg    [Modifier] |         +--------------------------------------------------------------+
|    ★ Record                  |
| ...                          |
| [   Retour à l’accueil     ] |
|                              |  section gap (32 px)
| [   Supprimer la séance    ] |  danger
+------------------------------+
```

- Head and totals as L4 — Session summary; the totals `<dl class="summary-totals" id="seance-totaux">` are re-rendered out of band after each correction (records and volume change). « Exercices » counts the exercises with a live set (`SummaryView.exercise_count`): a section emptied by deleting its last set stays on screen until reload but no longer counts.
- Per exercise with a live set: `<section class="session-block session-detail" id="exercice-{row}" aria-labelledby="exercice-{row}-titre">` (the correction fragment): h2 name (+ « Archivé »), the L4 meta line, `<a class="inline-link" href="/progression/{exercise_id}">` « Voir la progression », then the L4 settings `<details>` when the exercise has non-archived setting variables (same form, same `PATCH …/reglages`, hint « Corrections enregistrées à chaque changement. »), then the L4 set list with « Modifier » and the edit form (same macro, same ids `serie-{id}-…`, same « Enregistrer » / « Supprimer la série »; keyboard accepted, no steppers). No next-set form, no ✓, no « Changer d’exercice ».
- Corrections validate against the exercise's current fields; the stars, the meta line and the totals are recomputed in the answer.
- Last live set of an exercise deleted: the section stays with `.empty` « Plus aucune série pour cet exercice. »; focus on its « Voir la progression ».
- Actions: primary « Retour à l’accueil » (L4). Then, after a `--space-8` gap, `<section id="seance-suppression" data-request-scope>`: slot, danger button « Supprimer la séance » (full width below 40rem; `hx-get="/seances/{id}/suppression" hx-target="#seance-suppression" hx-swap="outerHTML"`). The in-place confirmation (L2, danger border, `role="group"`): « Supprimer la séance ? », « Elle disparaîtra de l’historique, des records et de la progression. La suppression ne peut pas être annulée. », « Annuler » (`autofocus`; `?annuler=1` puts the button back, focus on it) and danger « Supprimer la séance » (`hx-delete="/seances/{id}"` → `HX-Redirect: /historique?supprimee=1`).
- **Open session** (L4 page): the same `#seance-suppression` block after `#fin-de-seance`, `--space-8` above it.

States (added to L4 — Session summary):

| State | What the user sees | Focus / announcement |
|---|---|---|
| Set corrected | row text and ⭐ updated, `<details>` closed, totals updated | the row's « Modifier »; « Série 2 modifiée. » |
| Set deleted | row gone, rows renumbered, totals updated | next « Modifier », else previous, else « Voir la progression »; « Série 2 supprimée. » |
| Correction refused | row `<details open>`, messages under inputs | first invalid input; first message |
| Setting corrected | slot « Réglages enregistrés. », summary text updated | kept; same text |
| Correction failed / set deleted elsewhere (404) | « Non enregistré, réessayer » in the form's slot | D-053 |
| Delete asked | the confirmation in place of the button | « Annuler » |
| Session deleted | `/historique` with « Séance supprimée. » | notice |
| Deleted session reopened (old tab, link) | L1a 404 page | — |

Tab order: skip link, header, totals (no stops), per exercise « Voir la progression », settings summary, each « Modifier », then « Retour à l’accueil », « Supprimer la séance ».

Implementation notes (L5 developer): a setting correction on a closed session answers the settings form itself (the L4 form targets `this`; summary text and announcement out of band), which keeps the focus on the changed input; set corrections answer the whole exercise section. The set rows and edit forms are one macro (`_set_list.html`) shared with the open block. A set changed from an open session's page while another device closed it keeps the L4 redirect (`?terminee=1`).

### L5 — Progress index (`GET /progression`, `templates/progress_index.html`)

Task: open the exercise to review. Information: name, category, last date, number of sessions.

```
360 px                                  1280 px
+------------------------------+        +----------------------------------------------------------------+
| Progression                  |  h1    |  Progression                                     [ Réglages ]  |
| [         Réglages         ] |        |  Développé couché (barre)   Musculation   03/11/2026   Séances : 14 |
| Développé couché (barre)     |  row   |  Course à pied              Cardio        01/11/2026   Séances : 9  |
| Musculation · 03/11/2026 ·   |        |  ...                                                           |
| Séances : 14                 |        +----------------------------------------------------------------+
| ---------------------------- |
| ...                          |
+------------------------------+
```

- Page head: h1 « Progression », secondary link-button « Réglages » → `/reglages` (full width under the h1 below 40rem).
- `.rows` of `<a class="row" href="/progression/{id}">`, most recent first: title name (+ « Archivé »), meta « Musculation · 03/11/2026 · Séances : 14 » (category, `Display.local_date` of the last session, `progress.item_sessions`). From 40rem one line, grid `minmax(0, 2fr) minmax(0, 1fr) 7rem 8rem` (name, category, date, count right aligned).
- Empty: `.empty` « Aucune progression pour l’instant. » + muted « Elle apparaîtra après votre première série enregistrée. » + link-button « Nouvelle séance » → `/`.
- Tab order: header, « Réglages », rows. Tab title `progress.title`.

### L5 — Progress of an exercise (`GET /progression/{exercise_id}`, `templates/progress.html`, `templates/progress_rm.html`, `static/js/progress-chart.js`)

Task: see whether the exercise progresses and what the max is now. Decision (strength): which load to use, whether to retest. Information in order of use: last performance, RM, the main indicator over time, records.

```
360 px, strength                         1280 px, strength (from 64rem: 1fr | 2fr)
+------------------------------+         +------------------------------------------------------------------------+
| Développé couché (barre)     |  h1     |  Développé couché (barre)                                              |
| Musculation · Fiche de       |         |  Musculation · Fiche de l’exercice                                     |
| l’exercice                   |         |  +----------------------+  +--------------------------------------------+ |
| Dernière performance         |  h2     |  | Dernière performance |  | Évolution                                  | |
| 03/11/2026 · Salle A — …     |  link   |  | 03/11/2026 · Salle A |  | Meilleur 1RM estimé de chaque jour et 1RM  | |
| 1  8 × 40 kg [Échauffement]  |         |  | 1 8 × 40 kg  [Éch.]  |  | mesurés, en kg.                            | |
| 2  8 × 62,5 kg               |         |  | 2 8 × 62,5 kg        |  | ● 1RM estimé (Epley)  ◆ 1RM mesuré         | |
| RM (répétition maximale)     |  h2 #rm |  | RM                   |  | [ chart 320 px high ]                      | |
| 1RM                 105 kg   |         |  | 1RM          105 kg  |  | 48 jours, du 05/11/2025 au 03/11/2026.     | |
| Mesuré · test en séance du   |         |  | Mesuré · saisie du … |  | Dernière valeur : 102,5 kg ; meilleure :   | |
| 12/10/2026                   |         |  | Estimation (Epley) : |  | 107,5 kg.                                  | |
| Estimation (Epley) : 107,5 kg|         |  | 107,5 kg             |  | Voir les données ▸                         | |
| ▌Estimation supérieure au    |         |  | ▌Estimation sup. …   |  | Records                                    | |
| ▌test du 12/10/2026          |         |  | Formule : Epley ·    |  | Charge max par nombre de répétitions       | |
| 5RM                  92,5 kg |         |  | Changer              |  | Rép.  Charge    Date                       | |
| Mesuré · saisie du 01/10/2026|         |  | Saisir un RM mesuré ▸|  | 1     100 kg    12/10/2026                 | |
| Formule d’estimation : Epley |         |  +----------------------+  | ...                                        | |
| · Changer                    |         |                            +--------------------------------------------+ |
| [ Saisir un RM mesuré      ▸]|         +------------------------------------------------------------------------+
| Évolution                    |  h2
| Meilleur 1RM estimé de chaque|
| jour et 1RM mesurés, en kg.  |
| ● 1RM estimé (Epley)         |
| ◆ 1RM mesuré                 |
| [ chart 328 × 240 ]          |
| 48 jours, du 05/11/2025 au   |  figcaption
| 03/11/2026. Dernière valeur :|
| 102,5 kg ; meilleure : 107,5…|
| Voir les données           ▸ |
| Records                      |  h2
| ...                          |
+------------------------------+
```

**Head.** h1 exercise name (+ « Archivé »); muted line: category · `<a class="inline-link" href="/exercices/{id}">` « Fiche de l’exercice ». Tab title: the exercise name.

**Layout.** `<div class="progress">`: `<div class="progress__side">` (last performance; RM for strength) then `<div class="progress__main">` (chart, records). Below 64rem one column in that order; from 64rem grid `minmax(0, 1fr) minmax(0, 2fr)`, gap `--space-8`. Visual order = DOM order = tab order.

**Dernière performance** (`section`, h2): a link `<a class="inline-link" href="/seances/{id}">` « 03/11/2026 · Salle A — Squat & poussée horizontale » (or « Séance libre »), then the read-only L4 set rows (number, `Display.set_text`, type tags, ⭐). Empty: muted « Aucune série enregistrée pour cet exercice. ».

**RM** (strength only, `<section id="rm" aria-labelledby="rm-titre">`, the fragment of the RM routes, slot first): h2 « RM (répétition maximale) ».

- `<ul class="rm-rows">`, one `<li>` per row of `rm_table` (1RM always, then each measured n ascending): line 1 flex `space-between`: « 1RM » (weight 600) and the shown value (`--text-lg`, weight 600, tabular); then muted `--text-sm` lines:
  - origin (`Display.rm_origin`): « Mesuré · saisie du 01/10/2026 », « Mesuré · test en séance du 12/10/2026 », or « Estimé (Epley) · d’après 5 × 92,5 kg du 28/10/2026 »;
  - for a measured row with an estimate: « Estimation (Epley) : 107,5 kg »;
  - the flag, when D-069 raises it: `<p class="rm-flag">` « Estimation supérieure au test du 12/10/2026 » (weight 600, text colour, 3 px `--color-accent` left border, padding-inline `--space-3`; the words carry the meaning).
- No measure and no estimable set: muted « Aucun RM pour l’instant : saisissez un test, ou enregistrez des séries de travail de 1 à 12 répétitions. » (no rows).
- Muted line « Formule d’estimation : Epley · » + `<a class="inline-link" href="/reglages">` « Changer » (visually hidden « la formule »).
- `<details class="rm-add" id="rm-saisie">`, summary `.button` full width below 40rem, id `rm-saisir`, « Saisir un RM mesuré » (`open` when the answer carries a refusal). Inside `<form class="form" id="rm-form" hx-post="/rm/{exercise_id}" hx-target="#rm" hx-swap="outerHTML" hx-disabled-elt="#rm-form button">`: slot; `fieldset.chips.chips--grid6` legend « Nombre de répétitions », radios `name="n"` 1 … 12, « 1 » checked; field « Charge (kg) » (`session.field_unit`), `input.input` `name="weight"` `inputmode="decimal"`, hint `unit.hint.weight`, empty; field « Date du test », `<input class="input" type="date" name="date" value="{today}" max="{today}">`; primary « Enregistrer la mesure ». Saved → section re-rendered, `<details>` closed, focus on `#rm-saisir`, « 1RM mesuré enregistré : 105 kg. ». Refused → `200`, messages under the inputs (`rm_reps_range` under the chips' legend, `required` / unit codes / `must_be_positive` under the weight, `bad_date` / `date_in_future` under the date).
- « Mesures saisies » (h3 `.rm-measures__heading`, `margin-top: var(--space-6)`, only when a manual entry exists): `<ul class="rows">` newest first, each `<li>` a flex row: « 1RM · 100 kg · 12/10/2026 » (tabular) and a danger `.button` « Supprimer » (visually hidden « la mesure 1RM du 12/10/2026 »; `hx-delete="/rm/mesures/{id}" hx-target="#rm" hx-swap="outerHTML" hx-disabled-elt="this"`; no confirmation: re-entering takes three fields, like a set delete in L4). Deleted → section re-rendered, focus on the next measure's « Supprimer », else `#rm-saisir`, « Mesure supprimée. ». RM-test sets are not listed here: they are corrected in their session.

**Évolution** (`section`, h2 « Évolution »):

1. Muted intro by main series (`progress.chart_intro.*`), `.chart-note` (`--text-sm`, as the caption; the one-day text `progress.chart_one_point` uses the same class).
2. Legend `<ul class="chart-legend">` only with ≥ 2 series: per series `<li class="chart-legend__item chart-legend__item--{i}">` with the label; the glyph (● ◆ ■ ▲ ✕ ★ by index) in `--chart-{i}` through `::before` (alt text empty). Flex wrap, gap `--space-3`, `--text-sm`.
3. `<figure class="chart-figure">`: `<div class="chart" hidden>` `<canvas data-chart-src="/api/progression/{id}" role="img" aria-labelledby="evolution-titre evolution-resume"></canvas></div>`, `<p class="chart__error" data-chart-error hidden>` « Graphique indisponible. Les données restent consultables ci-dessous. », `<figcaption id="evolution-resume" class="muted">` « 48 jours, du 05/11/2025 au 03/11/2026. » + (single main series) « Dernière valeur : 102,5 kg ; meilleure : 107,5 kg. ». `.chart` height `15rem` below 64rem, `20rem` from 64rem, width 100 %, `font-size: var(--text-sm)`; the script removes `hidden` before drawing.
4. `<details class="chart-data">` summary (chevron, as the L4 settings summary, 48 px) « Voir les données », then the data table, caption visually hidden « Valeurs par jour, de la plus récente à la plus ancienne », newest first:

| Category | Columns (all but Date right aligned) |
|---|---|
| `strength` | Date · 1RM estimé · 1RM mesuré (only when any) · Volume |
| `kettlebell` | Date · Charge · Rép. max (one row per day and load) |
| `bodyweight` | Date · Rép. max (holds: Durée max) · Total rép. (holds: none) |
| `cardio` | Date · Distance (when the exercise has one) · Durée · Allure (when both) |
| `intervals` | Date · Tours · Travail |

Dates `Display.local_date` (« 03/11/2026 »); empty cell « — ». A column of weights, distances or paces carries its unit in the header (`progress.col.with_unit`: « 1RM estimé (kg) », « Distance (km) », « Allure (min/km) »; `Display.column_unit`) and its cells hold the number only (`Display.column_cell`, `units.column_number`: « 117,5 », a distance in km even under 1 km « 0,4 », « 5:20 »); headers may wrap. Per-set values (max reps, max duration) as `m:ss` / numbers; per-day sums (durations of a day) compact (« 30 min », L4 summary rule). The table has no side padding on its outer cells, so every table fits 328 px at 360 (strength with « 1RM mesuré », cardio with distance and pace).

Chart drawing (`progress-chart.js`, Chart.js): type line; series *i*: colour `--chart-{i}`, `pointStyle` *i*, line 2 px, point radius 4; a `kind: "points"` series (1RM mesuré) `showLine: false`, radius 5; `spanGaps: true`; `animation: false`; `responsive: true`, `maintainAspectRatio: false`; `locale` from `<html lang>`; `plugins.legend.display: false`; `interaction: {mode: "index", intersect: false}`; x category labels « 03/11 » (`autoSkip`, `autoSkipPadding: 12`: no overlap at 360 with ~100 days), y title from `axis`; y ticks by the JSON `scale`: `decimal` (Chart.js `fr` numbers), `count` (`precision: 0`, never « 6,0 »), `duration` (values in seconds, ticks every JSON `step` seconds, a clock-round step from `units.chart_duration_step`, written `m:ss` / `h:mm:ss` like every duration, D-029); ticks and titles `--color-muted`, grid `--color-divider`, tooltip background `--color-surface`, text `--color-text`, border 1 px `--color-border`; tooltip line from the JSON `tooltip` (« {label} : {value} kg »), `{value}` the series' server-written `texts` entry (« 102,5 », a duration `m:ss` / `h:mm:ss`, « Durée max : 1:35 »; only axis ticks are written by the script), `usePointStyle: true` (the series' shape), title from the JSON `titles` (« 03/11 », the full « 03/11/2026 » when the chart spans two calendar years). Font family and size read from `.chart`'s computed style. Tokens re-read on `prefers-color-scheme` change.

Chart states:

| State | What the user sees |
|---|---|
| No counted set | intro hidden; muted « Le graphique apparaîtra après la première séance avec cet exercice. »; no canvas, legend, table |
| One day | muted « Une seule journée enregistrée : le graphique apparaîtra dès la deuxième. »; no canvas; table with one row |
| Loading (JS) | the empty box, no spinner (< 1 s) |
| Ready | chart; `data-chart-state="ready"` |
| JSON or Chart.js failed | box hidden again, « Graphique indisponible. Les données restent consultables ci-dessous. » shown; caption and table stay |
| JavaScript off | no box; caption and table |

**Records** (`section`, h2 « Records »; counted sets of live sessions; each date is `<a class="inline-link" href="/seances/{id}">` with visually hidden « séance du »):

| Category | Shown |
|---|---|
| `strength` | table « Charge max par nombre de répétitions »: Rép. · Charge · Date, rows 1 … 12 with data, then « 13 et plus »; then « Meilleur volume en une séance » |
| `kettlebell` | table « Répétitions max par charge »: Charge · Rép. · Date; « Meilleure densité » (only with durations); « Meilleur volume en une séance » |
| `bodyweight` | « Répétitions max en une série », « Durée max », « Charge ajoutée max » (only when weighted), « Répétitions en une séance » |
| `cardio` | « Distance max », « Durée max », « Meilleure allure » (« 5:20 /km »), « Meilleure vitesse » (« 11,3 km/h ») (both only with sets holding distance and duration) |
| `intervals` | « Tours en une séance », « Travail en une séance » |

Single records: `<dl class="records">`, each item `dt` label, `dd` value (weight 600, tabular) and the date link; below 40rem label on one line, value and date on the next; from 40rem grid `minmax(0, 1fr) 8rem 8rem`. Table rows ≥ 48 px (the date link). A record absent (no data) is not listed. No record at all: muted « Aucun record pour l’instant. ».

States of the page:

| State | What the user sees |
|---|---|
| Exercise with history | as above |
| Strength exercise, no history | « Aucune série enregistrée pour cet exercice. », RM section (entry possible), chart and records empty texts |
| Exercise with one session | last performance, RM from that session, one-day chart text, records |
| No RM yet (strength) | `rm.no_data` text, « Saisir un RM mesuré » |
| Only an estimate | 1RM row « Estimé (Epley) · d’après … » |
| Measured, estimate higher and later | measured value shown, « Estimation (Epley) : … » and the flag |
| Archived exercise | « Archivé » tag; page works |
| Unknown or foreign id | L1a 404 page |

Tab order: header, « Fiche de l’exercice », last-performance link, (strength) « Changer », « Saisir un RM mesuré » and its form, each « Supprimer »; « Voir les données »; record date links. The canvas takes no tab stop.

Implementation notes (L5 developer): the chart is drawn (canvas, legend, scripts) when the series hold at least two distinct days in all (a kettlebell chart counts the days of every load); the caption counts those days. The tooltip key reads « {label} : {value} {unit} » (no-break space before the colon only); a unit-less series (reps, rounds, durations) drops the unit. Fix loop 1: duration axes read `m:ss` / `h:mm:ss` (axis title `progress.axis.duration` « Durée »; `progress.unit.minutes` removed); records `dd` is a flex row with a `--space-3` gap between value and date link (a grid with the same gap from 40rem). `Display.pace`, `speed` and `density` are one helper, `Display.rate(kind, value)`, and table / record values go through `Display.cell`. Chart.js 4.6.1 was checked in Chromium under the unchanged CSP: no `<style>` element, no violation; it sizes the canvas through the CSSOM only. The RM-test measurements are read from `record_history` (no separate `rm_test_sets` query).

### L5 — Settings (`GET /reglages`, `templates/settings.html`)

Task: choose the 1RM formula. Information: names, expressions, the current one.

```
360 px                                  1280 px (column max 40rem)
+------------------------------+        +---------------------------------------------------+
| Réglages                     |  h1    |  Réglages                                         |
| Estimation du 1RM            |  h2    |  Estimation du 1RM                                |
| Sert à estimer les RM à      |        |  Sert à estimer les RM à partir des séries de     |
| partir des séries de travail |        |  travail de 1 à 12 répétitions. Les RM mesurés    |
| de 1 à 12 répétitions. …     |        |  ne changent pas.                                 |
| (●) Epley  par défaut        |  48+   |  (●) Epley  par défaut                            |
|     charge × (1 + rép. / 30) |        |      charge × (1 + rép. / 30)                     |
| ( ) Brzycki                  |        |  ( ) Brzycki                                      |
|     charge × 36 / (37 − rép.)|        |      charge × 36 / (37 − rép.)                    |
| ...                          |        |  ...                                              |
| Une série d’une répétition   |        |  Une série d’une répétition compte pour sa charge,|
| compte pour sa charge, …     |        |  quelle que soit la formule.                      |
| [   Voir la progression    ] |        |  [ Voir la progression ]                          |
+------------------------------+        +---------------------------------------------------+
```

- `<form class="form" id="reglages-formule" hx-patch="/reglages" hx-trigger="change" hx-target="this" hx-swap="outerHTML">` (no save button, L4 settings pattern): slot first; muted intro (`.section__intro`, `--text-sm` like the « Données » intro; L6 fix loop 1); `<fieldset class="choices">` legend « Formule », five `<label class="choice">` radios `name="rm_formula"` (`epley`, `brzycki`, `lombardi`, `oconner`, `wathan`), each text: name (weight 600, « Epley » followed by the tag « par défaut ») and the expression on the next line (muted `--text-sm`, tabular). The current one checked. Then muted « Une série d’une répétition compte pour sa charge, quelle que soit la formule. ».
- Saved → form re-rendered, slot « Formule enregistrée : Brzycki. » (`kind="ok"`), focus kept on the radio (ids `formule-{key}`), same text announced. Refused (`invalid_choice`) → message under the legend. Failure → D-053.
- Secondary link-button « Voir la progression » → `/progression` (full width below 40rem).
- Tab order: header, the radio group (one stop, arrows inside), « Voir la progression ». Tab title `settings.title`.

### L5 — Exercise sheet link (`templates/exercise.html`)

The page head gains a secondary link-button « Voir la progression » → `/progression/{id}` (full width under the h1 below 40rem), every exercise, archived included.

### L5 — Units of computed values (`domain/units`, `web/display.Display`)

| Value | Shown | Key |
|---|---|---|
| e1RM, RM, loads | `Display.value` weight, 100 g precision: « 102,5 kg », « 105 kg » | `unit.with_value` |
| pace (s/km) | « 5:20 /km » (`m:ss`, no-break space before « /km ») | `unit.pace` |
| speed (m/h) | « 11,3 km/h » (one decimal) | `unit.speed` |
| density | « 12,5 rép./min » (one decimal) | `unit.density` |
| weekly average | « 2,8 » (one decimal) | — |
| chart values | numbers in kg, km or counts formatted by Chart.js with the `fr` locale; durations in seconds written `m:ss` / `h:mm:ss` by the chart script (`units.chart_number`) | — |
| per-session sums of durations | compact, « 4 min », « 1 h 15 » | `duration.compact.*` |
| per-set durations | `m:ss` / `h:mm:ss` | — |

### L5 — Style (`tokens.css`, `components.css`, `pages/history.css`, `pages/progress.css`)

- `tokens.css`: `--chart-1` … `--chart-6` (L5 — Tokens).
- `components.css`: the two-list nav (L5 — Header), `.data-table` and `.data-table__scroll`, `.inline-link`, `.chips--grid6`.
- `pages/history.css`: `.week-chart` (grid `repeat(12, minmax(0, 1fr))`, gap `--space-1`, `align-items: end`, height of the bar zone 56 px), `.week-chart__count`, `.week-chart__bar` (`--color-accent`, `--radius-sm` top corners), `--0` … `--7` (2, 8, 16, 24, 32, 40, 48, 56 px; `--0` in `--color-divider`), `.week-chart__item--current .week-chart__bar` (1 px accent border, `--color-surface` fill), `.week-chart__week` (visually hidden below 40rem, muted `--text-sm` centred from 40rem), `.history-list`, `.history-item` (grid from 40rem), month heading `h2::first-letter { text-transform: uppercase }`.
- `pages/progress.css`: `.progress` (grid from 64rem), `.progress__side`, `.progress__main`, `.chart` (height 15rem / 20rem from 64rem, `position: relative`), `.chart-legend` and `--1` … `--6` glyphs, `.chart__error`, `.chart-data`, `.records`, `.rm-rows`, `.rm-flag`, `.rm-add`, settings `.choice` second line.
- Progress and settings pages link `pages/catalog.css` (`.empty`) and `pages/session.css` (set rows); `progress.html` alone loads `chart.umd.min.js` and `progress-chart.js` (`defer`) through `{% block scripts %}`.
- 360 px check: the longest seed names, the history item, the 12-column week chart, the RM rows with flag, two rows of six chips, every data table (strength with « 1RM mesuré », cardio) and the records tables fit without horizontal scroll (page and `.data-table__scroll`); every target ≥ 48 × 48 px except text inside the week chart (no control).

### L5 — Strings (`web/locales/fr.json`)

Typography as L4: typographic apostrophes; no-break space (U+00A0) before « : », « ; », « ? », inside « », between a number and its unit, before « /km ». Month and weekday names lowercase (headings capitalise through CSS).

| Key | Text |
|---|---|
| `nav.history` | Historique |
| `nav.progress` | Progression |
| `date.short` | {day}/{month} |
| `date.month.1` … `date.month.12` | janvier, février, mars, avril, mai, juin, juillet, août, septembre, octobre, novembre, décembre |
| `date.weekday.1` … `date.weekday.7` | lun., mar., mer., jeu., ven., sam., dim. (ISO: 1 = Monday) |
| `history.title` | Historique |
| `history.deleted_notice` | Séance supprimée. |
| `history.consistency_heading` | Régularité |
| `history.this_week` | Cette semaine : {count} |
| `history.week_average` | Séances par semaine, moyenne sur 12 semaines : {value} |
| `history.weeks_label` | Séances par semaine, 12 dernières semaines |
| `history.week_item` | Semaine du {date} : {count} |
| `history.week_item_current` | Semaine du {date} (en cours) : {count} |
| `history.weeks_caption` | 12 dernières semaines, la semaine en cours à droite. |
| `history.month_heading` | {month} {year} |
| `history.item_when` | {weekday} {date} · {time} |
| `history.open_tag` | En cours |
| `history.no_sets` | Aucune série |
| `history.more` | Plus anciennes |
| `history.loaded` | Séances chargées : {count} |
| `history.empty_title` | Aucune séance pour l’instant. |
| `history.empty_text` | Les séances apparaîtront ici dès la première. |
| `session.settings_hint_closed` | Corrections enregistrées à chaque changement. |
| `session.exercise_no_sets` | Plus aucune série pour cet exercice. |
| `session.delete` | Supprimer la séance |
| `session.delete_confirm_title` | Supprimer la séance ? |
| `session.delete_confirm_text` | Elle disparaîtra de l’historique, des records et de la progression. La suppression ne peut pas être annulée. |
| `progress.title` | Progression |
| `progress.link` | Voir la progression |
| `progress.settings_link` | Réglages |
| `progress.item_sessions` | Séances : {count} |
| `progress.empty_title` | Aucune progression pour l’instant. |
| `progress.empty_text` | Elle apparaîtra après votre première série enregistrée. |
| `progress.sheet_link` | Fiche de l’exercice |
| `progress.last_heading` | Dernière performance |
| `progress.last_session` | {date} · {name} |
| `progress.last_empty` | Aucune série enregistrée pour cet exercice. |
| `progress.chart_heading` | Évolution |
| `progress.chart_intro.e1rm` | Meilleur 1RM estimé de chaque jour et 1RM mesurés, en kg. |
| `progress.chart_intro.reps_by_load` | Répétitions max en une série, pour chaque charge. |
| `progress.chart_intro.max_reps` | Répétitions max en une série, chaque jour. |
| `progress.chart_intro.max_duration` | Durée max d’une série, chaque jour. |
| `progress.chart_intro.distance` | Distance totale de chaque jour, en km. |
| `progress.chart_intro.duration` | Durée totale de chaque jour. |
| `progress.chart_intro.rounds` | Tours effectués chaque jour. |
| `progress.series.e1rm` | 1RM estimé ({formula}) |
| `progress.series.measured_1rm` | 1RM mesuré |
| `progress.series.load` | {load} |
| `progress.series.max_reps` | Répétitions max |
| `progress.series.max_duration` | Durée max |
| `progress.series.distance` | Distance |
| `progress.series.duration` | Durée |
| `progress.series.rounds` | Tours |
| `progress.axis.weight` | Charge (kg) |
| `progress.axis.reps` | Répétitions |
| `progress.axis.distance` | Distance (km) |
| `progress.axis.duration` | Durée |
| `progress.axis.rounds` | Tours |
| `progress.chart_tooltip` | {label} : {value} {unit} |
| `progress.chart_span` | {count} jours, du {first} au {last}. |
| `progress.chart_latest` | Dernière valeur : {value} ; meilleure : {best}. |
| `progress.chart_one_point` | Une seule journée enregistrée : le graphique apparaîtra dès la deuxième. |
| `progress.chart_empty` | Le graphique apparaîtra après la première séance avec cet exercice. |
| `progress.chart_error` | Graphique indisponible. Les données restent consultables ci-dessous. |
| `progress.data_toggle` | Voir les données |
| `progress.data_caption` | Valeurs par jour, de la plus récente à la plus ancienne |
| `progress.col.date` | Date |
| `progress.col.e1rm` | 1RM estimé |
| `progress.col.measured` | 1RM mesuré |
| `progress.col.volume` | Volume |
| `progress.col.load` | Charge |
| `progress.col.reps` | Rép. |
| `progress.col.max_reps` | Rép. max |
| `progress.col.total_reps` | Total rép. |
| `progress.col.max_duration` | Durée max |
| `progress.col.distance` | Distance |
| `progress.col.duration` | Durée |
| `progress.col.pace` | Allure |
| `progress.col.rounds` | Tours |
| `progress.col.work` | Travail |
| `progress.col.with_unit` | {label} ({unit}) |
| `progress.col.unit_pace` | min/km |
| `progress.records_heading` | Records |
| `progress.records_empty` | Aucun record pour l’instant. |
| `progress.session_of` | séance du |
| `progress.reps_13_plus` | 13 et plus |
| `progress.record.max_load_by_reps` | Charge max par nombre de répétitions |
| `progress.record.max_reps_by_load` | Répétitions max par charge |
| `progress.record.session_volume` | Meilleur volume en une séance |
| `progress.record.density` | Meilleure densité |
| `progress.record.max_reps` | Répétitions max en une série |
| `progress.record.max_duration` | Durée max |
| `progress.record.max_added_load` | Charge ajoutée max |
| `progress.record.session_reps` | Répétitions en une séance |
| `progress.record.max_distance` | Distance max |
| `progress.record.best_pace` | Meilleure allure |
| `progress.record.best_speed` | Meilleure vitesse |
| `progress.record.session_rounds` | Tours en une séance |
| `progress.record.session_work` | Travail en une séance |
| `unit.pace` | {value} /km |
| `unit.speed` | {value} km/h |
| `unit.density` | {value} rép./min |
| `rm.heading` | RM (répétition maximale) |
| `rm.label` | {n}RM |
| `rm.origin.manual` | Mesuré · saisie du {date} |
| `rm.origin.rm_test` | Mesuré · test en séance du {date} |
| `rm.origin.estimated` | Estimé ({formula}) · d’après {set} du {date} |
| `rm.estimate_beside` | Estimation ({formula}) : {value} |
| `rm.flag` | Estimation supérieure au test du {date} |
| `rm.no_data` | Aucun RM pour l’instant : saisissez un test, ou enregistrez des séries de travail de 1 à 12 répétitions. |
| `rm.formula_line` | Formule d’estimation : {formula} · |
| `rm.formula_change` | Changer |
| `rm.formula_change_named` | la formule |
| `rm.add` | Saisir un RM mesuré |
| `rm.reps_legend` | Nombre de répétitions |
| `rm.date_label` | Date du test |
| `rm.submit` | Enregistrer la mesure |
| `rm.saved` | {n}RM mesuré enregistré : {value}. |
| `rm.measures_heading` | Mesures saisies |
| `rm.measure_text` | {n}RM · {value} · {date} |
| `rm.delete` | Supprimer |
| `rm.measure_named` | la mesure {n}RM du {date} |
| `rm.deleted` | Mesure supprimée. |
| `rm.formula.epley` | Epley |
| `rm.formula.brzycki` | Brzycki |
| `rm.formula.lombardi` | Lombardi |
| `rm.formula.oconner` | O’Conner |
| `rm.formula.wathan` | Wathan |
| `rm.formula_text.epley` | charge × (1 + rép. / 30) |
| `rm.formula_text.brzycki` | charge × 36 / (37 − rép.) |
| `rm.formula_text.lombardi` | charge × rép. ^ 0,10 |
| `rm.formula_text.oconner` | charge × (1 + rép. / 40) |
| `rm.formula_text.wathan` | 100 × charge / (48,8 + 53,8 × e ^ (−0,075 × rép.)) |
| `settings.title` | Réglages |
| `settings.formula_heading` | Estimation du 1RM |
| `settings.formula_intro` | Sert à estimer les RM à partir des séries de travail de 1 à 12 répétitions. Les RM mesurés ne changent pas. |
| `settings.formula_legend` | Formule |
| `settings.default_tag` | par défaut |
| `settings.formula_single` | Une série d’une répétition compte pour sa charge, quelle que soit la formule. |
| `settings.formula_saved` | Formule enregistrée : {formula}. |
| `catalog.error.rm_reps_range` | Entre 1 et 12 répétitions. |
| `catalog.error.bad_date` | Date non valable. |
| `catalog.error.date_in_future` | La date ne peut pas être dans le futur. |
| `catalog.error.rm_not_strength` | Les RM ne concernent que les exercices de musculation. |

« × », « − » (U+2212) and « ^ » in formula texts take no-break spaces on both sides. Reused: `session.summary.sets`, `session.summary.volume`, `session.summary_title`, `session.settings_saved`, `session.announce_set_updated`, `session.announce_set_deleted`, `session.delete_set`, `session.record`, `session.set_type.*`, `session.field_unit`, `home.free_session`, `home.start_title` (link « Nouvelle séance »), `exercise.location.*`, `exercise.category.*`, `tag.archived_m`, `action.cancel`, `action.home`, `action.save`, `unit.hint.weight`, `unit.with_value`, `date.numeric`, `duration.compact.*`, `quantity.weight`, `unit.kg`, `catalog.error.required`, `catalog.error.must_be_positive`, `catalog.error.invalid_choice`, the `domain/units` codes, `error.not_saved`. The design note's `Display.week` « sem. du 27/10 » is replaced by `date.short` « 27/10 » plus `history.week_item` (accessible text).

### L6 — Settings: export (`GET /reglages`, `templates/settings.html`; `GET /api/export?format=json|csv`, D-074)

Task: take a complete copy of the data out of the app, to keep it or to open it in another tool. Decision: which format (a spreadsheet, or one complete file for a program). Information: what each format is for, that everything is included, that the numbers are in canonical units, and that this is not the way to restore the app. Rare task, done on the desktop more often than on the phone; nothing is written, so no confirmation.

```
360 px                                  1280 px (column max 40rem)
+------------------------------+        +---------------------------------------------------+
| Réglages                     |  h1    |  Réglages                                         |
| Estimation du 1RM            |  h2    |  Estimation du 1RM                                |
| ... (L5 formula form)        |        |  ... (L5 formula form)                            |
| Données                      |  h2    |  Données                                          |
| Une copie complète de vos    |        |  Une copie complète de vos données, à garder ou à |
| données, … archivés et       |        |  ouvrir dans un autre logiciel, …                 |
| supprimés compris.           |        |                                                   |
| [    Exporter en JSON      ] |  48    |  [ Exporter en JSON ]  Un seul fichier, complet et|
| Un seul fichier, complet et  |        |                        sans perte, …              |
| sans perte, …                |        |  [ Exporter en CSV  ]  Un fichier zip avec un     |
| [    Exporter en CSV       ] |  48    |                        tableau par type …         |
| Un fichier zip avec un       |        |  Les poids sont en grammes, les durées en …       |
| tableau par type …           |        |  Cet export ne sert pas à restaurer …             |
| Les poids sont en grammes, … |        |                                                   |
| Cet export ne sert pas à …   |        |  [ Voir la progression ]                          |
| [   Voir la progression    ] |        |                                                   |
+------------------------------+        +---------------------------------------------------+
```

- A second `<section class="section settings" id="donnees" aria-labelledby="donnees-titre">` after the formula section, before the « Voir la progression » actions: h2 `id="donnees-titre"` « Données », then `<p class="muted">` intro (`.section > h2 + .muted`: small text under the heading).
- `<ul class="exports">`, two `<li class="export">`, JSON first (the complete format):
  - `<a class="button export__link" id="export-json" href="/api/export?format=json" aria-describedby="export-json-aide">` « Exporter en JSON », then `<p class="muted export__hint" id="export-json-aide">` its hint.
  - The same for CSV: `id="export-csv"`, `href="/api/export?format=csv"`, `export-csv-aide`.
  - Plain links (D-074): no htmx, no script, **no `download` attribute**. The server's `Content-Disposition: attachment` makes the browser save the file and stay on « Réglages »; without `download`, a failure is an ordinary navigation that shows the error page instead of a broken download (Chromium reports a `download` failure only in its download bar, with no explanation), and an unpaired browser follows the `303` to pairing.
  - Secondary buttons (no accent): nothing here is the page's main action.
- Then two `<p class="muted export__note">`: the units sentence and the restore sentence.
- Files: `rack-overflow-<UTC YYYYMMDDTHHMMSSZ>.json` (`application/json; charset=utf-8`) and `rack-overflow-<UTC YYYYMMDDTHHMMSSZ>-csv.zip` (`application/zip`); content D-072 / D-073. The names are not shown on the page (the browser shows them).

States:

| State | User sees | Focus |
|---|---|---|
| Default | the section as drawn; always present (the export of an empty database is valid) | — |
| Downloading | the browser's own download indicator (desktop bar or list; Safari on iOS asks where to save, then Files); the page does not change | stays on the link |
| Done | the file in the browser's downloads (iOS: Files → Téléchargements); no message in the page, none needed | stays on the link |
| Server failure (500) | the error page (L1a — Error pages): « Erreur du serveur », `error.internal`, « Code 500 », « Réessayer » then « Retour à l’accueil ». « Réessayer » must lead to the same export: the retry link keeps the request's query (`/api/export?format=json`), never `/api/export` alone, which would answer 422. A retry that succeeds downloads the file without navigating (`Content-Disposition: attachment`), so the error page stays displayed; the browser's download indicator is the only sign of success | error page, as L1a |
| Unknown or missing `format` (typed URL only) | error page `422`, `error.invalid_request` « Demande non valable. », « Retour à l’accueil » | as L1a |
| Unpaired browser | `303` to `/appairage` | as L1b |

Layout and style (`pages/progress.css`, tokens only, no new colour; light and dark come from the tokens):

- `.exports`: no list style, `margin-top: var(--space-4)`, flex column, `gap: var(--space-4)`.
- `.export`: below 40rem a column, the button full width (`width: 100%`) and the hint under it (`margin-top: var(--space-1)`, `--text-sm`). From 40rem a grid `grid-template-columns: 12rem minmax(0, 1fr)`, `column-gap: var(--space-4)`, `align-items: center`: button left (fixed width, so the two buttons align), hint right.
- `.export__note`: `margin-top: var(--space-3)`, `--text-sm`, `max-width: var(--text-max)` (the section's `.settings`).
- Targets: each link-button ≥ 48 px high (`.button`), 16 px between the two (≥ 8 px rule). No horizontal scroll at 360 px: the longest label « Exporter en JSON » fits a full-width button.

Keyboard and focus: Tab order header, the formula radio group (one stop), « Exporter en JSON », « Exporter en CSV », « Voir la progression ». Enter on a link starts the download; focus stays on it. Each link's hint is read with it (`aria-describedby`). No live announcement: the page does not change and the browser reports the download.

Browser check (Chromium and WebKit, 360 / 1280, light / dark): the page checks of `/reglages` pass with the section; a click on « Exporter en JSON » fires a download whose name ends in `.json` (Chromium).

### L6 — Forms disable every button (`hx-disabled-elt`)

Every htmx form disables all its buttons during its request through an id selector `#<form id> button` (L4 rule), never `find button` (htmx's `find` takes the first match only). Ids, existing ones kept, new ones added where the form had none:

| Template | Form | `hx-disabled-elt` |
|---|---|---|
| `pairing_form.html` | `id="appairage-formulaire"` (new) | `#appairage-formulaire button` |
| `variable_form.html` | `variable-formulaire` | `#variable-formulaire button` |
| `exercise_form.html` | `exercice-formulaire` | `#exercice-formulaire button` |
| `exercise_fields.html` (« Ajouter un champ ») | `id="champ-ajout-formulaire"` (new) | `#champ-ajout-formulaire button` |
| `exercise_field_form.html` | `{prefix}-formulaire` | `#{prefix}-formulaire button` |
| `exercise_aliases.html` | `id="alias-formulaire"` (new) | `#alias-formulaire button` |
| `session_template_form.html` | `seance-type-formulaire` | `#seance-type-formulaire button` |
| `session_template_slots.html` (add a slot) | `id="bloc-ajout-formulaire"` (new) | `#bloc-ajout-formulaire button` |
| `session_template_slot_form.html` (slot) | `{prefix}-formulaire` | `#{prefix}-formulaire button` |
| `session_template_slot_form.html` (add an option) | `id="{prefix}-option-ajout-formulaire"` (new) | `#{prefix}-option-ajout-formulaire button` |

No visible change other than every button of the form being disabled (`.button[disabled]`) while the request runs; the new ids style nothing (classes unchanged). A template audit test fails on any `find button`.

### L6 — Strings (`web/locales/fr.json`)

Typographic apostrophes (’); a no-break space (U+00A0) before « : ».

| Key | Text |
|---|---|
| `settings.data_heading` | Données |
| `settings.data_intro` | Une copie complète de vos données, à garder ou à ouvrir dans un autre logiciel. Les éléments archivés et supprimés sont compris. |
| `settings.export_json` | Exporter en JSON |
| `settings.export_json_hint` | Un seul fichier, complet et sans perte, pour un autre logiciel ou un programme. |
| `settings.export_csv` | Exporter en CSV |
| `settings.export_csv_hint` | Un fichier zip avec un tableau par type de données, à ouvrir dans Excel, Numbers ou LibreOffice. |
| `settings.export_units` | Les poids y sont en grammes, les durées en secondes et les distances en mètres. |
| `settings.export_not_backup` | Cet export ne sert pas à restaurer l’application : les sauvegardes quotidiennes du serveur s’en chargent. |

Reused: `settings.title`, `progress.link`, and on the error page `error.title.internal`, `error.internal`, `error.status`, `error.invalid_request`, `action.retry`, `action.home`.
