# web/ — rules

- HTTP only: routes parse the request, call `services/` (never `storage/`), and render a page or fragment. Business rules stay in `domain/`.
- Imports allowed: third-party web libraries, `domain`, `services`, `config` (`tests/unit/test_layering.py`). The database arrives as an `Engine` passed to `app.create_app`.
- No module-level app: `app.create_app(settings, engine, *, clock, run_scheduler=True)` builds it; the clock is injected (no implicit `datetime.now`).
- Every page or fragment goes through `rendering.render`. Templates never hard-code French text: every string comes from `locales/fr.json` through `t("key")` (D-036); a new key is added to `docs/ui-spec.md` and `fr.json` together.
- No inline script, inline style, `style=` or `on*=` attribute, no external URL (CSP, D-034). htmx is configured by the `htmx-config` meta in `base.html`.
- Every path except `auth.PUBLIC_PATHS` and `/static/` needs a paired device (`auth.DeviceAuthMiddleware`, deny by default, D-049): a new route is protected without any code. Routes read the device from `request.state.device` and take `user_id` from it, never from `domain/users`.
- Every non-GET request is JSON (`json-enc`) and passes `security.SecurityMiddleware` (D-034, D-047); never add a CORS header or an exception to these checks without a decision.
- Errors: `errors.py` maps HTTP statuses to stable English codes and message keys explicitly; a browser navigation gets `error.html`, anything else `{"error": "<code>"}`.
- CSS: `tokens.css` holds every colour, size and spacing (values in `docs/ui-spec.md`); `base.css`, `components.css`, one `pages/<page>.css` per page. Use tokens only.
- Vendored files in `static/vendor/` are never edited by hand: replace them from the source URL and update `manifest.json` (version, URL, SHA-256); a test checks the hashes.
- One router module per area in `routes/`; user-visible URL paths in French, route functions in English.

## Modules

| Module | Owns |
|---|---|
| `app.py` | `create_app(settings, engine, *, clock, run_scheduler=True)`: static mount, routes, middlewares from the outside in (security, unhandled errors, device authentication), lifespan (backup scheduler, engine dispose); `app.state` holds settings, engine, catalog, clock, templates |
| `security.py` | `SecurityMiddleware` (pure ASGI: `Host`, `Origin` / `Sec-Fetch-Site`, JSON-only, 64 KiB body limit; CSP and security headers on every response, `no-store` outside `/static/` and on every error status, D-048), the rejection codes (`INVALID_HOST`, `FORBIDDEN_ORIGIN`, `UNSUPPORTED_MEDIA_TYPE`, `PAYLOAD_TOO_LARGE`, reused by `errors.py`), `hostname(host)` |
| `locale.py` | `load_catalog(path)`, `Catalog.text(key, **params)`, `LocaleError`; imports no other project module |
| `rendering.py` | `create_environment(catalog)` (Jinja2, autoescape, `t` global) and `render(request, template, context, status)` |
| `errors.py` | Status → code → message key maps (401 → `not_paired`), `wants_page(request)` (browser navigation without `HX-Request`), `error_response(request, status)` (« Réessayer » links to the raw path), `UnhandledErrorMiddleware` (500 inside the security headers), `install(app)` |
| `auth.py` | `DeviceAuthMiddleware` (pure ASGI: `rack_device` cookie → `services.devices.authenticate` in the thread pool → `scope["state"]["device"]`; unpaired navigation `303` to `PAIRING_PATH`, else `401 not_paired` + `HX-Redirect` for htmx; invalid cookie cleared, renewed cookie re-sent, appended to the route's headers), `device_cookie(token, https)`, `cleared_cookie(https)`, `is_public(path)`, `unpaired_response(request)`, `COOKIE_NAME`, `PAIRING_PATH`, `PUBLIC_PATHS` |
| `scheduler.py` | `backup_once(settings, clock)`, `run_daily_backup(settings, clock, interval_s)`: daily backup through `services.backups.backup_if_due` |
| `routes/home.py` | `GET /` → `home.html` |
| `routes/pairing.py` | `GET /appairage` → `pairing.html` (form, or "already paired"); `POST /appairage` (`PairingRequest`): success → device cookie + `HX-Redirect: /`; refusal → `200` + `pairing_form.html` with the message and the out-of-band `#annonce` (D-050); explicit outcome → message key map |
| `templates/` | `base.html` (layout), `home.html`, `error.html`, `pairing.html`, `pairing_form.html` (swappable fragment) |
| `static/css/` | `tokens.css`, `base.css`, `components.css` (buttons, actions, message page, form fields `.field`, `.input`, `.field__error`, `.field__hint`), `pages/home.css`, `pages/pairing.css` |
| `static/vendor/` | `htmx.min.js` (htmx 2.0.11), `json-enc.js` (htmx-ext-json-enc 2.0.3), `manifest.json` |
| `locales/fr.json` | Flat `{key: text}` French catalog |
