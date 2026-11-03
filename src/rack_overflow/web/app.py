"""The FastAPI application factory (no module-level app)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.web import errors, scheduler
from rack_overflow.web.auth import DeviceAuthMiddleware
from rack_overflow.web.locale import load_catalog
from rack_overflow.web.rendering import create_environment
from rack_overflow.web.routes import (
    exercises,
    history,
    home,
    pairing,
    progress,
    session_templates,
    sessions,
    variables,
)
from rack_overflow.web.security import SecurityMiddleware

WEB = Path(__file__).resolve().parent
STATIC = WEB / "static"
CATALOG = WEB / "locales" / "fr.json"


def create_app(
    settings: Settings, engine: Engine, *, clock: Callable[[], datetime], run_scheduler: bool = True
) -> FastAPI:
    """Build the app: static files, routes, lifespan, and middlewares from the outside in:
    security checks, unhandled errors, device authentication (deny by default)."""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        task = asyncio.create_task(scheduler.run_daily_backup(settings, clock)) if run_scheduler else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            engine.dispose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    catalog = load_catalog(CATALOG)
    app.state.settings = settings
    app.state.engine = engine
    app.state.catalog = catalog
    app.state.clock = clock
    app.state.templates = create_environment(catalog)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.include_router(home.router)
    app.include_router(pairing.router)
    app.include_router(variables.router)
    app.include_router(exercises.router)
    app.include_router(session_templates.router)
    app.include_router(sessions.router)
    app.include_router(history.router)
    app.include_router(progress.router)
    # Starlette: the last middleware added is the outermost
    app.add_middleware(DeviceAuthMiddleware, engine=engine, clock=clock, https=settings.server.https)
    errors.install(app)
    app.add_middleware(
        SecurityMiddleware, public_host=settings.server.public_host, https=settings.server.https
    )
    return app
