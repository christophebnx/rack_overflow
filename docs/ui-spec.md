# UI specification

Global rules first, then one section per screen. The `ui-designer` agent adds each screen's section during its milestone, with every string in French exactly as shown to the user (and its key in `locales/fr.json`). Source rules: `docs/release-1.0.0-brief.md` section 4, appendix A.7, and decisions D-015, D-027, D-034, D-036.

## Global rules

### Platform

- One responsive web app for phone and desktop, rendered on the server (Jinja2) with htmx for partial updates (D-015). No front-end framework, no build step. JavaScript only for htmx configuration and charts.
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
- Dialogs use `<dialog>` with `aria-modal`; one shared confirmation dialog where, for a destructive choice, the safe answer has focus and Esc means « non ».
- Invalid fields are marked and their message is tied to them (`aria-describedby`).
- Action results are announced once through a permanent live region.

### States and messages

- Every screen designs its empty, loading, error and success states.
- htmx requests disable their trigger while running (`hx-disabled-elt`). A failed request keeps the form values and shows « Non enregistré, réessayer » (key `error.not_saved`).
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
- Focus ring 3 px `--color-focus`, offset 2 px, on `:focus-visible`. Links in text are underlined.
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

Below 40rem the actions sit at the bottom of the viewport (thumb zone), stacked, full width, primary first; from 40rem they follow the text in a row. « Réessayer » is a link to the current path (GET), primary; « Retour à l’accueil » is primary when alone, secondary otherwise.

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
