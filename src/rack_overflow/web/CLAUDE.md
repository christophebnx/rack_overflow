# web/ — rules

- HTTP only: routes parse the request, call `services/` (never `storage/`), and render a page or fragment. Business rules stay in `domain/`.
- Imports allowed: third-party web libraries, `domain`, `services`, `config` (`tests/unit/test_layering.py`). The database arrives as an `Engine` passed to `app.create_app`.
- No module-level app: `app.create_app(settings, engine, *, clock, run_scheduler=True)` builds it; the clock is injected (no implicit `datetime.now`).
- Every page or fragment goes through `rendering.render`. Templates never hard-code French text: every string comes from `locales/fr.json` through `t("key")` (D-036); a new key is added to `docs/ui-spec.md` and `fr.json` together.
- No inline script, inline style, `style=` or `on*=` attribute, no external URL (CSP, D-034). htmx is configured by the `htmx-config` meta in `base.html`.
- Every non-GET request is JSON (`json-enc`) and passes `security.SecurityMiddleware` (D-034, D-047); never add a CORS header or an exception to these checks without a decision.
- Errors: `errors.py` maps HTTP statuses to stable English codes and message keys explicitly; a browser navigation gets `error.html`, anything else `{"error": "<code>"}`.
- CSS: `tokens.css` holds every colour, size and spacing (values in `docs/ui-spec.md`); `base.css`, `components.css`, one `pages/<page>.css` per page. Use tokens only.
- Vendored files in `static/vendor/` are never edited by hand: replace them from the source URL and update `manifest.json` (version, URL, SHA-256); a test checks the hashes.
- One router module per area in `routes/`; user-visible URL paths in French, route functions in English.

## Modules

| Module | Owns |
|---|---|
| `app.py` | `create_app(settings, engine, *, clock, run_scheduler=True)`: static mount, routes, error handling, security middleware (outermost), lifespan (backup scheduler, engine dispose); `app.state` holds settings, engine, catalog, clock, templates |
| `security.py` | `SecurityMiddleware` (pure ASGI: `Host`, `Origin` / `Sec-Fetch-Site`, JSON-only, 64 KiB body limit; CSP and security headers on every response), `hostname(host)` |
| `locale.py` | `load_catalog(path)`, `Catalog.text(key, **params)`, `LocaleError`; imports no other project module |
| `rendering.py` | `create_environment(catalog)` (Jinja2, autoescape, `t` global) and `render(request, template, context, status)` |
| `errors.py` | Status → code → message key maps, `error_response(request, status)`, `UnhandledErrorMiddleware` (500 inside the security headers), `install(app)` |
| `scheduler.py` | `backup_once(settings, clock)`, `run_daily_backup(settings, clock, interval_s)`: daily backup through `services.backups.backup_if_due` |
| `routes/home.py` | `GET /` → `home.html` |
| `templates/` | `base.html` (layout), `home.html`, `error.html` |
| `static/css/` | `tokens.css`, `base.css`, `components.css`, `pages/home.css` |
| `static/vendor/` | `htmx.min.js` (htmx 2.0.11), `json-enc.js` (htmx-ext-json-enc 2.0.3), `manifest.json` |
| `locales/fr.json` | Flat `{key: text}` French catalog |
