"""The one place pages and fragments are rendered (Jinja2, autoescape on, `t` bound to the catalog)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from rack_overflow.web.display import Display
from rack_overflow.web.locale import Catalog

TEMPLATES = Path(__file__).resolve().parent / "templates"


def create_environment(catalog: Catalog) -> Environment:
    """The Jinja2 environment of the app: templates folder, autoescape, strict undefined, `t()`,
    `show` (value display, `web.display.Display`)."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.globals["t"] = catalog.text
    environment.globals["show"] = Display(catalog)
    return environment


def render(
    request: Request, template: str, context: Mapping[str, Any] | None = None, status: int = 200
) -> HTMLResponse:
    """Render `template` with `context` (plus `request`) into an HTML response."""
    environment: Environment = request.app.state.templates
    page = environment.get_template(template).render({"request": request, **(context or {})})
    return HTMLResponse(page, status_code=status)
