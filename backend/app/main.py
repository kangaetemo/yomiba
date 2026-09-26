"""FastAPI application factory and ordered process lifecycle."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from . import __version__
from .config import get_settings, prepare_staging_database, safe_database_target, validate_runtime_settings
from .database import get_db
from .readiness import check_database_ready, expected_revision
from .login_rate_limit import LoginRateLimiter
from .routes import api_router

logger = logging.getLogger("yomiba")


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(auto_init: bool = True) -> FastAPI:
    _configure_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from . import database
        from .models import ImportRecord
        from .routes.catalog import try_start_sync, wait_for_active_sync
        from .seed import seed_stores
        from .services.background_import import BackgroundImportRunner
        from .services.catalog_scheduler import CatalogSyncScheduler
        from .services.price_refresh_scheduler import PriceRefreshScheduler

        runner = None
        price_refresh = None
        scheduler = None
        try:
            logger.info("startup: begin")
            validate_runtime_settings(settings)
            logger.info("startup: database target %s", safe_database_target(settings))
            if auto_init:
                if database.engine.url != make_url(settings.database_url):
                    raise RuntimeError("Runtime engine and Alembic DATABASE_URL differ")
                if prepare_staging_database(settings):
                    logger.info("startup: created empty staging database on mounted volume")
                with database.engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                logger.info("startup: database reachable")
                database.init_db()
                logger.info("startup: migration complete (head=%s)", expected_revision())
                database.enable_sqlite_wal(database.engine)
                with database.SessionLocal() as session:
                    created_stores = seed_stores(session)
                    logger.info("startup: store seed complete (created=%s)", created_stores)
                    # Workers have not started yet; RUNNING rows belong to an old process.
                    zombie_count = session.execute(
                        update(ImportRecord)
                        .where(ImportRecord.status == "running")
                        .values(status="failed", error="içe aktarma yarıda kesildi (süreç yeniden başlatıldı)")
                    ).rowcount
                    session.commit()
                    logger.info("startup: recovered %d stale RUNNING records", zombie_count)
                check_database_ready(database.engine, check_foreign_keys=True)
                logger.info("startup: database readiness checks passed")

            # Tests may preset a runner; production creates it only after DB setup.
            runner = getattr(app.state, "import_runner", None)
            if runner is None:
                runner = BackgroundImportRunner(database.SessionLocal)
                app.state.import_runner = runner
            logger.info("startup: import runner ready (workers=%d, queue=%d)", runner.worker_count, runner.queue_capacity)
            if auto_init and settings.price_refresh_enabled:
                price_refresh = PriceRefreshScheduler(
                    runner, database.SessionLocal, settings.price_refresh_interval_hours * 3600.0,
                )
                price_refresh.start()
                logger.info("startup: price scheduler started")
            app.state.price_refresh_scheduler = price_refresh
            if auto_init and settings.catalog_sync_enabled:
                from .services.background_import import SYNC_GATE_KEY

                scheduler = CatalogSyncScheduler(
                    lambda: try_start_sync(runner),
                    settings.catalog_sync_interval_hours * 3600.0,
                    gate_wait_seconds=settings.catalog_gate_timeout_seconds,
                    poll_seconds=min(60.0, max(1.0, settings.catalog_gate_timeout_seconds / 10)),
                    announce_intent=lambda active: runner.lock.set_exclusive_intent(SYNC_GATE_KEY, active),
                )
                scheduler.start()
                logger.info("startup: catalog scheduler started")
            app.state.catalog_scheduler = scheduler
            app.state.ready = auto_init
            logger.info("startup: app ready")
            yield
        finally:
            app.state.ready = False
            if price_refresh is not None:
                price_refresh.stop(timeout=5)
                logger.info("shutdown: price scheduler stopped=%s", not price_refresh.is_running)
            if scheduler is not None:
                scheduler.stop(timeout=10)
                logger.info("shutdown: catalog scheduler stopped=%s", not scheduler.is_running)
            if not wait_for_active_sync(timeout=10):
                logger.warning("shutdown: catalog sync still active after timeout")
            if runner is not None:
                runner.shutdown(timeout=10)
                logger.info("shutdown: import runner stopped (active=%d queued=%d)", runner.active_count, runner.queued_count)

    app = FastAPI(
        title="Yomiba API",
        version=__version__,
        description="Manga price comparison and collection tracking for the Turkish market.",
        lifespan=lifespan,
    )
    app.state.auto_init = auto_init
    app.state.ready = False
    app.state.login_limiter = LoginRateLimiter()

    @app.middleware("http")
    async def reject_cross_origin_writes(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = set(settings.cors_origins) | {settings.backend_url.rstrip("/")}
            if origin not in allowed:
                return JSONResponse(status_code=403, content={"detail": "Geçersiz istek kaynağı."})
        return await call_next(request)

    @app.middleware("http")
    async def prevent_personal_response_caching(request: Request, call_next):
        response = await call_next(request)
        # Public search/prices can use ordinary cache policy. Any response
        # tied to a session, and all auth/personal endpoints, must not be
        # stored by a shared intermediary.
        personal_path = request.url.path.startswith(("/auth/", "/me/")) or any(
            marker in request.url.path for marker in ("/wishlist", "/price-alert", "/collection-status")
        )
        if personal_path or request.cookies.get("yomiba_session"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        elif request.url.path.startswith(("/series/", "/volume/")):
            response.headers["Vary"] = "Cookie"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["meta"])
    def ready(session: Session = Depends(get_db)) -> dict:
        if not app.state.ready:
            raise HTTPException(status_code=503, detail="Application not ready")
        try:
            validate_runtime_settings(settings)
            check_database_ready(session.get_bind())
        except Exception:
            logger.exception("readiness check failed")
            raise HTTPException(status_code=503, detail="Database not ready") from None
        return {"status": "ready"}

    return app


app = create_app()
