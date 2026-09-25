"""FastAPI application entrypoint.

Run locally from the ``backend/`` directory:

    python -m uvicorn app.main:app --reload

The app creates tables and seeds the known stores on startup (idempotent).
Tests build the app with ``create_app(auto_init=False)`` against an
in-memory database.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .routes import api_router

logger = logging.getLogger("yomiba")


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(auto_init: bool = True) -> FastAPI:
    _configure_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from sqlalchemy import update

        from .database import SessionLocal, init_db
        from .models import ImportRecord
        from .routes.catalog import try_start_sync
        from .seed import seed_stores
        from .services.background_import import BackgroundImportRunner
        from .services.catalog_scheduler import CatalogSyncScheduler
        from .services.price_refresh_scheduler import PriceRefreshScheduler

        # One background import runner per app; jobs use their own sessions.
        # Tests preset app.state.import_runner before entering the TestClient
        # context, so never clobber a preset runner.
        if getattr(app.state, "import_runner", None) is None:
            app.state.import_runner = BackgroundImportRunner(SessionLocal)

        # Periodic catalog sync: production shape only (auto_init) and
        # enabled via env. No catch-up at startup — the first run happens
        # one interval after process start (see catalog_scheduler).
        scheduler = None
        if auto_init and settings.catalog_sync_enabled:
            scheduler = CatalogSyncScheduler(
                lambda: try_start_sync(app.state.import_runner),
                settings.catalog_sync_interval_hours * 3600.0,
                gate_wait_seconds=settings.catalog_gate_timeout_seconds,
            )
            scheduler.start()
        app.state.catalog_scheduler = scheduler

        # Periodic price refresh: re-imports stale search queries in the
        # background so searches find fresh data instead of waiting for a
        # store scrape (see price_refresh_scheduler).
        price_refresh = None
        if auto_init and settings.price_refresh_enabled:
            price_refresh = PriceRefreshScheduler(
                app.state.import_runner,
                SessionLocal,
                settings.price_refresh_interval_hours * 3600.0,
            )
            price_refresh.start()
        app.state.price_refresh_scheduler = price_refresh

        if auto_init:
            init_db()
            with SessionLocal() as session:
                seed_stores(session)
                # The runner was just created with an empty queue, so no
                # import job can actually be running here: any record still
                # marked "running" belongs to a process that died
                # mid-import (e.g. a sandbox restart). Mark it failed so
                # search status and the admin page stop lying.
                zombie_count = session.execute(
                    update(ImportRecord)
                    .where(ImportRecord.status == "running")
                    .values(
                        status="failed",
                        error="içe aktarma yarıda kesildi (süreç yeniden başlatıldı)",
                    )
                ).rowcount
                if zombie_count:
                    session.commit()
                    logger.info(
                        "startup: marked %d interrupted import record(s) as failed",
                        zombie_count,
                    )
        yield
        # Stop the schedulers FIRST so no new sync/import job is started
        # while the import runner and its in-flight jobs are shut down.
        if price_refresh is not None:
            price_refresh.stop(timeout=5)
        if scheduler is not None:
            scheduler.stop(timeout=10)
        app.state.import_runner.shutdown(timeout=10)

    app = FastAPI(
        title="Yomiba API",
        version=__version__,
        description="Manga price comparison and collection tracking for the Turkish market.",
        lifespan=lifespan,
    )
    app.state.auto_init = auto_init

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

    return app


app = create_app()
