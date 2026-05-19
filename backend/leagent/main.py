"""FastAPI application factory — standalone local deployment."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from leagent.api.middleware import (
    APIVersionMiddleware,
    AccessLogMiddleware,
    ContentSizeLimitMiddleware,
    RequestIDMiddleware,
)
from leagent.api.router import api_router
from leagent.config.settings import get_settings
from leagent.exceptions.handlers import register_exception_handlers
from leagent.utils.logging import setup_logging

if TYPE_CHECKING:
    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)

_service_manager: ServiceManager | None = None


def get_service_manager() -> "ServiceManager":
    assert _service_manager is not None, "ServiceManager not initialised"
    return _service_manager


def set_service_manager(sm: "ServiceManager | None") -> None:
    global _service_manager
    _service_manager = sm


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: start services on startup, stop on shutdown."""
    global _service_manager

    settings = get_settings()
    setup_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        json_output=not settings.debug,
        log_file=settings.log_file,
    )

    logger.info("LeAgent starting up (standalone local mode)...")

    from leagent.services.service_manager import ServiceManager

    _service_manager = ServiceManager(settings)
    await _service_manager.start_all()

    try:
        await _run_db_migrations()
    except Exception:
        logger.warning("Database migration skipped (non-fatal)", exc_info=True)

    # Tool registry must be populated before accepting HTTP traffic; deferred
    # warmup runs concurrently and chat/agent requests used to race ahead of
    # bootstrap_tools(), yielding intermittent tool_not_found for curated tools.
    await _bootstrap_tool_system()

    app.state.post_startup_warmup = asyncio.Event()
    app.state._warmup_task = asyncio.create_task(
        _post_startup_warmup(app, _service_manager),
        name="post-startup-warmup",
    )

    logger.info("LeAgent ready")
    yield

    logger.info("LeAgent shutting down...")
    wt = getattr(app.state, "_warmup_task", None)
    if wt is not None:
        wt.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await wt
    try:
        from leagent.api.v1.chat import manager as chat_ws_manager
        await chat_ws_manager.aclose()
    except Exception:
        logger.debug("ws manager close failed", exc_info=True)
    await _service_manager.stop_all()
    _service_manager = None
    logger.info("LeAgent stopped")


async def _post_startup_warmup(app: FastAPI, sm: "ServiceManager") -> None:
    """Deferred startup: tools, skills, routes.

    When ``LEAGENT_DESKTOP=1`` (Electron shell), Playwright browser
    installation check and other heavyweight optional services are
    skipped to minimise cold-start time.
    """
    import os

    is_desktop = os.environ.get("LEAGENT_DESKTOP") == "1"
    ev: asyncio.Event = app.state.post_startup_warmup
    try:
        # ``tests/conftest.py`` sets ``LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES`` and
        # mounts the same deferred routers synchronously. Skip registering them again
        # here — duplicate paths can produce spurious 405 Method Not Allowed.
        if os.environ.get("LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES") != "1":
            from fastapi import APIRouter
            from leagent.api.router_deferred import (
                mount_v1_deferred_routes,
                mount_v2_deferred_routes,
            )

            deferred_v1_router = APIRouter(prefix="/api/v1")
            deferred_v2_router = APIRouter(prefix="/api/v2")
            mount_v1_deferred_routes(deferred_v1_router)
            mount_v2_deferred_routes(deferred_v2_router)
            app.include_router(deferred_v1_router)
            app.include_router(deferred_v2_router)

        await _load_skills()

        mount_frontend_spa_if_configured(app)

        if is_desktop:
            logger.info("Desktop mode — skipping optional heavyweight service warmup")
        logger.info("Post-startup warmup complete")
    finally:
        ev.set()


async def _run_db_migrations() -> None:
    """Apply Alembic migrations (in-process for SQLite).

    Delegates to :func:`leagent.alembic.sync_runner.run_sync_migrations`, which
    uses ``alembic.command.upgrade`` so ``env.run_migrations_online`` can use the
    injected connection. Skips when no revision scripts exist.
    """
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text

    from leagent.alembic.runtime_config import load_alembic_config
    from leagent.alembic.sync_runner import run_sync_migrations

    settings = get_settings()

    def _migrate() -> None:
        cfg = load_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
        url = settings.database.sync_url
        eng = create_engine(url)
        try:
            if head is None:
                logger.info("No Alembic revisions in script directory; skipping migrations")
                return
            with eng.connect() as conn:
                try:
                    row = conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).fetchone()
                    current = row[0] if row else None
                except Exception:
                    current = None
            if current == head:
                logger.info("Database migrations already at head: %s", head)
                return
            with eng.connect() as connection:
                run_sync_migrations(connection)
            logger.info("Database migrations applied (in-process)")
        finally:
            eng.dispose()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _migrate)


async def _bootstrap_tool_system() -> None:
    try:
        from leagent.bootstrap import bootstrap_tools
        summary = await bootstrap_tools()
        logger.info(
            "Tool system ready: %d tools, %d workflow nodes",
            summary["tools"],
            len(summary["nodes"]),
        )
    except Exception:
        logger.warning("Tool bootstrap failed (non-fatal)", exc_info=True)


async def _load_skills() -> None:
    try:
        from leagent.config.settings import get_settings
        from leagent.skills.manager import get_skills_manager

        manager = get_skills_manager()
        count = await manager.load_all()
        logger.info("Skills loaded: %d skill(s)", count)
        if get_settings().skills_activate_all_on_start and count:
            results = await manager.activate_all()
            n_on = sum(1 for v in results.values() if v)
            logger.info("Skills activated on start: %d / %d", n_on, len(results))
    except Exception:
        logger.warning("Skills loading skipped (non-fatal)", exc_info=True)


def mount_frontend_spa_if_configured(app: FastAPI) -> None:
    """Serve the built SPA from ``/`` **after** all API routers are registered.

    Mounting ``StaticFiles`` at ``/`` too early shadows later ``include_router``
    calls (deferred v1 routes), producing 404/405 on paths like
    ``POST /api/v1/streams/rtsp/token``. A bare ``LEAGENT_FRONTEND_DIST`` must
    not be treated as a path: ``Path('').resolve()`` is the process cwd, which
    is always a directory and would incorrectly mount the cwd as the SPA.
    """
    if getattr(app.state, "frontend_spa_mounted", False):
        return
    raw = (os.environ.get("LEAGENT_FRONTEND_DIST") or "").strip()
    if not raw:
        return
    dist = Path(raw).expanduser().resolve()
    if not dist.is_dir():
        logger.warning("LEAGENT_FRONTEND_DIST is not a directory: %s", dist)
        return
    from starlette.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
    app.state.frontend_spa_mounted = True
    logger.info("Mounted frontend static files from %s", dist)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="LeAgent API",
        description="Intelligent Office Agent Platform (Local)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    from leagent.utils.metrics import MetricsMiddleware

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        APIVersionMiddleware,
        deprecation_date=settings.api_v1_deprecation_date,
        sunset_date=settings.api_v1_sunset_date,
        policy_url=settings.api_deprecation_policy_url,
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(
        ContentSizeLimitMiddleware,
        max_content_size=max(1, settings.files.max_upload_bytes),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)

    app.include_router(api_router, prefix="/api")

    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "version": "0.1.0"}

    spa_raw = (os.environ.get("LEAGENT_FRONTEND_DIST") or "").strip()
    spa_ready = bool(spa_raw and Path(spa_raw).expanduser().resolve().is_dir())
    if not spa_ready:

        @app.get("/")
        async def root(request: Request) -> dict:
            return {
                "name": "LeAgent",
                "version": "0.1.0",
                "docs": str(request.url_for("swagger_ui_html")) if settings.debug else None,
            }

    return app


app = create_app()
