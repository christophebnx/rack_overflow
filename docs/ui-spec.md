# UI specification

Global rules first, then one section per screen. The `ui-designer` agent adds each screen's section during its milestone, with every string in French exactly as shown to the user (and its key in `locales/fr.json`). Source rules: `docs/release-1.0.0-brief.md` section 4, appendix A.7, and decisions D-015, D-027, D-034, D-036.

## Global rules

### Platform

- One responsive web app for phone and desktop, rendered on the server (Jinja2) with htmx for partial updates (D-015). No front-end framework, no build step. JavaScript only for htmx configuration, the shared request-error display (`static/js/request-errors.js`, D-053) and charts.
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
- Dialogs use `<dialog>` with `aria-modal`; one shared confirmation dialog where, for a destructive choice, the safe answer has focus and Esc means « non ». From L2, a destructive confirmation that needs no script is an **in-place confirmation** instead (L2 — Components): it replaces the button that asked for it, the safe answer « Annuler » has focus, and nothing is deleted until the explicit second button. Confirmation only for what cannot be undone (archiving, removing a field or an alias are not confirmed).
- Invalid fields are marked and their message is tied to them (`aria-describedby`).
- Action results are announced once through a permanent live region.

### States and messages

- Every screen designs its empty, loading, error and success states.
- htmx requests disable their trigger while running (`hx-disabled-elt`). A failed request keeps the form values and shows « Non enregistré, réessayer » (key `error.not_saved`) in the form's `[data-request-status]` slot, clears old field errors and returns focus to the form's first field (D-053). Placement and look: L2 — Form status.
- Errors from the server carry stable English codes, mapped to French strings by key (D-036). A missing key shows the key itself.

### Language and units

- French only (D-027), from `locales/fr.json`; no French text in templates or code.
- Units shown: kg, km, m, durations as `m:ss` or `h:mm:ss` (D-029). Decimal separator: comma.

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

Task: check the app answers. No business data before L2–L4; L4 replaces the content with starting a session.

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

Below 40rem the actions sit at the bottom of the viewport (thumb zone), stacked, full width, primary first; from 40rem they follow the text in a row. « Réessayer » is a link to the current path as sent (still percent-encoded, query dropped; GET), primary; « Retour à l’accueil » is primary when alone, secondary otherwise.

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

- `<form class="pairing-form" hx-post="/appairage" hx-target="this" hx-swap="outerHTML" hx-disabled-elt="find button">` (JSON through `json-enc`, set on `<body>`).
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
- The `nav` block is filled on every protected page by one include `_nav.html` (home: not yet, the L1a test `test_home_page` still asserts no `<nav>` there; the catalog pages carry it); pairing and error pages leave it empty (no `<nav>` rendered). Two links in a `<ul class="site-nav__list">` (flex, gap `--target-gap`): « Exercices » → `/exercices`, « Variables » → `/variables`. The page passes `section` (`exercises` / `variables`); the matching link gets `aria-current="page"` on its list page **and** its detail / form pages.
- Link look: `--text-md` weight 600, text colour, no underline, `min-height: var(--target-min)`, `display: inline-flex; align-items: center`; padding-inline 0 below 40rem (the text is wider than 48 px; this keeps brand + two links within 360 px), `--space-2` from 40rem. Current link: `--color-accent` text and a 3 px `--color-accent` bottom border (inset `box-shadow`, no layout shift): colour plus bar, never colour alone. Hover: underline.
- Fit at 360 px: brand ≈ 150 px + 8 + « Exercices » ≈ 80 + 8 + « Variables » ≈ 75 = 321 px of the 328 px available. `.site-header__inner` is `flex-wrap: wrap` with `justify-content: space-between`, so a wider system font drops the nav to a second 48 px row, left aligned, instead of scrolling horizontally.
- Tab order: skip link, brand, « Exercices », « Variables », main.

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
- **Placement: the first child of the `<form>` (or of the `[data-request-scope]` container), above the first field.** D-053 returns focus to the first field, so the message sits right above the focused element: on a phone, scrolling to the focused field brings the message into view with it; at the bottom it would be off screen.
- Failure (script): text from `<body data-not-saved>` (`error.not_saved`, « Non enregistré, réessayer »), or from the slot's own `data-message` when present (search form only, `error.search_failed`, « Recherche impossible, réessayer »: nothing is saved by a search). The script sets `data-kind="error"`, removes `hidden`, writes the same text in `#annonce`, clears `aria-invalid` and old `.field__error` in the scope, then focuses the scope's first enabled `input` / `select` / `textarea`, else the trigger. Values stay as typed; the trigger is enabled again.
- Success (server, after a `PATCH` that saved): the re-rendered form carries the slot with `kind="ok"` and the success text (e.g. « Modifications enregistrées. »), and the same text goes to `#annonce` out of band. Creations, deletions and archive changes do not use the success slot: the page or block they change is the confirmation (see each screen).
- Clearing: at `htmx:beforeRequest` from the same scope the slot is hidden, emptied and loses `data-kind`; a successful swap replaces the whole form, so stale field errors and messages never survive a new answer.
- Look (`components.css`): `.form-status` `--text-md`, weight 600, padding `--space-3`, `--radius-md`, 1 px border; `[data-kind="error"]`: `--color-danger` text and border; `[data-kind="ok"]`: `--color-text` text, `--color-border` border. The text carries the meaning; the colour repeats it.
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
| In-place confirmation | `<div class="confirm" role="group" aria-labelledby="…">` fragment swapped in place of the button that asked (`hx-get`, `hx-swap="outerHTML"`) | 1 px `--color-danger` border, `--radius-md`, padding `--space-4`: question (weight 600), consequence, then « Annuler » (secondary, `autofocus`) and the danger button; « Annuler » swaps the original block back (`hx-get` of the same confirmation route with `?annuler=1`, which answers the block) and focus returns to the button that asked |
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
  - Row: `<a class="row" href="/exercices/{id}">` name (weight 600), then meta: movement · equipment · location (missing parts left out); « Archivé » tag after the name when archived. From 40rem the row is one line on a grid `minmax(0,2fr) minmax(0,1.5fr) minmax(0,1fr) auto` (name, movement, equipment, location), names and texts left aligned, ellipsis never: long names wrap.
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

- `<form class="form" hx-post="/exercices" hx-disabled-elt="find button" hx-target="this" hx-swap="outerHTML">`; status slot first.
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
- Line 3: `.actions--inline` « Monter » and « Descendre » (`hx-post …/deplacement`, `{"direction": "up"|"down"}`, `aria-label` « Monter {field} » / « Descendre {field} »; label in name: the visible word starts the accessible name). First row: « Monter » `disabled`; last row: « Descendre » `disabled`. After a move the fragment puts `autofocus` on the same button of the moved field, or on its other move button when the same one is now disabled; `#annonce`: « {field} : position {position} sur {total}. ».
- `<details class="field-row__edit">` with `<summary class="button">` « Modifier » + visually hidden « {field} » (≥ 48 px). Inside, one form `hx-patch="…/champs/{field_id}"` (status slot first):
  - Choice « Obligatoire ».
  - Numeric kinds (reps, weight, duration, distance; variables `int`, `decimal`, `weight`, `distance`, `duration`): `fieldset.choices` legend « Saisie pendant la séance », radios « Par pas » / « Valeurs proposées » (`name="mode"`; checked from the stored params; « Par pas » when neither). Then « Pas ({unit}) » and « Valeurs proposées ({unit}) » inputs; CSS shows only the input of the checked mode (`.field-row__edit:has([value=values]:checked) .only-step { display: none }` and the reverse). The route passes the domain only the input of the chosen mode, so `increment_with_discrete` cannot arise from the page. Values hint « Séparées par des espaces : 16 20 24. » (`inputmode="text"`: the iOS decimal pad has no space); splitting on spaces / « ; » and parsing each value is `domain/catalog.field_params`'s, each refused value named in the message.
  - « Valeur par défaut ({unit}) »: numeric input for numeric kinds; `<select>` (« Aucune » + labels by key) for `enum`; `<select>` (« Aucune », « Oui », « Non ») for `bool`; text input for `text`. Hint « Proposée quand l’exercice n’a pas encore d’historique. »
  - Unit in labels: kg, km, m:ss, or the variable's free unit; no parentheses when there is none (`field.step_label` vs `field.step_label_unit`). Unit hint under the input per the units table.
  - `.actions--inline`: primary « Enregistrer », danger « Retirer ce champ » (`hx-delete`, no confirmation: the stored values are kept and the field can be added again) with hint « Les valeurs déjà enregistrées sont conservées. ».
  - Refused input → the fields fragment re-rendered with this row's `<details open>`, values kept, messages under the inputs, `autofocus` on the first invalid one. Saved → row summary updated, `<details>` closed, `autofocus` on its summary, `#annonce` « Modifications enregistrées. ».
- « Ajouter un champ » form (`hx-post …/champs`): `<label>` « Ajouter un champ », `<select class="input" name="source" required>`: first option « Choisir… » (empty), `<optgroup>` « Quantités de base » (core quantities not yet linked), « Mesures » and « Réglages » (non-archived variables not yet linked, by label); button « Ajouter ». When nothing is left: the select is replaced by muted « Tous les champs disponibles sont déjà ajoutés. ». Below, link « Créer une variable » → `/variables/nouvelle?exercice={id}`. After the variable is created the user returns to `/exercices/{id}?ajout={variable_id}`, where that variable is preselected in this select and the select has `autofocus` (one tap, « Ajouter », to link it). Added → the new row is rendered `<details open>` with `autofocus` on « Obligatoire » (the next step is almost always its parameters, e.g. the 16 / 20 / 24 kg of a kettlebell), `#annonce` « Champ ajouté : {field}. ».
- Removing the last measure is a refusal of input (D-050), not a request failure: « Un exercice garde au moins une mesure : ce champ ne peut pas être retiré. » under that row's « Retirer ce champ » (`aria-describedby`), row open, focus on the button. Removed → row gone, `autofocus` on the next row's summary (or the « Ajouter un champ » select when none), `#annonce` « Champ retiré : {field}. ».

**Alias** (`templates/exercise_aliases.html`, `[data-request-scope]` with its slot first): intro « Autres noms pour la recherche. »; `<ul class="aliases">` of chips (`.tag`-like, text colour, `--text-md`) each followed by a button « Retirer » (`aria-label` « Retirer l’alias {alias} », `hx-delete`, no confirmation); empty: muted « Aucun alias. ». Form `hx-post …/alias`: label « Nouvel alias », input (`maxlength="60"`, `autocomplete="off"`, `autocapitalize="off"`, `enterkeyhint="done"`), hint « Par ex. « DC » ou « Bench press ». », button « Ajouter » (from 40rem on the input's line). Added → chip appended, input emptied with `autofocus` (aliases often come in twos), `#annonce` « Alias ajouté : {alias}. ». Removed → `autofocus` on the alias input, `#annonce` « Alias retiré : {alias}. ». Refused: `alias_taken`, `alias_is_name`, `required`, `too_long` under the input.

**Archivage** (`[data-request-scope]`, slot first, full width): active → « Un exercice archivé disparaît des listes et de la recherche ; son historique est conservé. » and secondary « Archiver » (`hx-post …/archive`, no confirmation: reversible). Archived → « Exercice archivé : il n’apparaît plus dans les listes ni la recherche. Son historique est conservé. » and primary « Restaurer » (`hx-delete …/archive`). The answer swaps this block, updates `#exercice-etat` out of band, puts `autofocus` on the new button and announces « Exercice archivé. » / « Exercice restauré. ». An archived exercise stays fully editable.

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
- Two groups, h2 « Mesures » (scope `set`) then « Réglages » (`setting`); an empty group is omitted. Rows sorted by normalised label: `<a class="row">` label (weight 600) + « Archivée » tag; meta: type label · unit (when it has one: free unit, or « kg » / « km » / « m:ss » for the typed kinds) · « Exercices liés : {count} » (count tabular, right aligned in its column from 40rem; grid `minmax(0,2fr) minmax(0,2fr) auto`).

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
- « Supprimer… » → `GET /variables/{id}/suppression` swaps the in-place confirmation: « Supprimer « {label} » ? » then « Elle sera retirée des exercices liés. Cette action est définitive. » (or « Cette action est définitive. » with no link), « Annuler » (`autofocus`; `GET /variables/{id}/suppression?annuler=1` swaps the block back, `autofocus` on « Supprimer… ») and danger « Supprimer la variable » (`hx-delete`). Deleted → `HX-Redirect: /variables` (the row is gone; the explicit confirmation just before is the acknowledgement). If values appeared meanwhile: block re-rendered in its "with values" state with the refusal « Des valeurs sont enregistrées : la variable ne peut être qu’archivée. » announced, focus on « Archiver ».

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
| `catalog.error.variable_last_measure` | Seule mesure de : {exercises}. Ajoutez-leur d’abord une autre mesure. |
| `catalog.error.already_linked` | Ce champ est déjà dans l’exercice. |
| `catalog.error.alias_taken` | Cet alias existe déjà pour cet exercice. |
| `catalog.error.alias_is_name` | L’alias est identique au nom de l’exercice. |
| `catalog.error.variable_in_use` | Des valeurs sont enregistrées : la variable ne peut être qu’archivée. |

Problem codes are the domain's (`domain/catalog`, `domain/units`): the developer uses exactly these codes; a code without a key renders the key (D-036), and the "every `t()` key exists" test covers templates. Tab titles: `exercises.title`, `exercise.new_title`, `variables.title`, `variable.new_title`; detail pages use the exercise name / variable label as `{page}` (base template accepts a ready text as well as a key).
