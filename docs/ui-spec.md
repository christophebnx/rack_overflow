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
