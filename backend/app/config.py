"""Runtime configuration.

All configuration is read from environment variables so that nothing is
hard-coded for a particular deployment. A local ``.env`` file (see
``.env.example``) is loaded if present, but real environment variables always
take precedence.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

# Load backend/.env if it exists (never overrides real environment variables).
load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, ".env"))


@dataclass(frozen=True)
class Settings:
    """Central, immutable application settings."""

    # Database URL. SQLite by default; swap in a PostgreSQL URL in production.
    # The rest of the application only ever talks to SQLAlchemy, so the engine
    # can be replaced without touching business logic.
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///./yomiba.db"
    )
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    staging_db_bootstrap: bool = os.getenv("STAGING_DB_BOOTSTRAP", "0").lower() in {"1", "true", "yes", "on"}

    # Public URL of this backend (used for documentation / CORS hints).
    backend_url: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

    # Origins the browser frontend is allowed to call us from directly.
    cors_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if o.strip()
    )

    auth_cookie_secure: bool = os.getenv("AUTH_COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    auth_session_days: int = int(os.getenv("AUTH_SESSION_DAYS", "30"))


    # HTTP client defaults shared by all scrapers.
    http_timeout: float = float(os.getenv("SCRAPER_TIMEOUT", "20"))
    http_user_agent: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    )
    http_accept_language: str = os.getenv(
        "SCRAPER_ACCEPT_LANGUAGE", "tr-TR,tr;q=0.9,en;q=0.7"
    )

    # How many product detail pages a single search may additionally request
    # (used to enrich results with metadata such as ISBN / publisher).
    max_detail_requests: int = int(os.getenv("SCRAPER_MAX_DETAIL_REQUESTS", "15"))

    # BKM paginated search (WAW Labs ``search_v2`` endpoint) limits.
    # Pagination always stops at whichever bound is hit first, so a search
    # can never loop forever.
    bkm_search_page_size: int = int(os.getenv("BKM_SEARCH_PAGE_SIZE", "20"))
    bkm_max_search_pages: int = int(os.getenv("BKM_MAX_SEARCH_PAGES", "5"))
    bkm_max_search_results: int = int(os.getenv("BKM_MAX_SEARCH_RESULTS", "100"))

    # Kitap Sepeti / Kitapbulan (same T-Soft CMS, paginated SSR search with
    # the ``pg`` parameter) limits. Same stop-earliest-bound rule.
    kitapsepeti_max_search_pages: int = int(os.getenv("KITAPSEPETI_MAX_SEARCH_PAGES", "5"))
    kitapsepeti_max_search_results: int = int(os.getenv("KITAPSEPETI_MAX_SEARCH_RESULTS", "60"))
    kitapbulan_max_search_pages: int = int(os.getenv("KITAPBULAN_MAX_SEARCH_PAGES", "5"))
    kitapbulan_max_search_results: int = int(os.getenv("KITAPBULAN_MAX_SEARCH_RESULTS", "60"))

    # Gerekli Şeyler (WAW ``/arama/<q>?tp=N``), Cizman (single-page public
    # search form), Kitapsec (``/Arama/index.php`` microdata), Komikşeyler
    # (public WooCommerce Store API, per_page=100).
    gerekliseyler_max_search_pages: int = int(os.getenv("GEREKLISEYLER_MAX_SEARCH_PAGES", "5"))
    gerekliseyler_max_search_results: int = int(os.getenv("GEREKLISEYLER_MAX_SEARCH_RESULTS", "60"))
    cizman_max_search_results: int = int(os.getenv("CIZMAN_MAX_SEARCH_RESULTS", "60"))
    kitapsec_max_search_pages: int = int(os.getenv("KITAPSEC_MAX_SEARCH_PAGES", "5"))
    kitapsec_max_search_results: int = int(os.getenv("KITAPSEC_MAX_SEARCH_RESULTS", "60"))
    komikseyler_max_search_pages: int = int(os.getenv("KOMIKSEYLER_MAX_SEARCH_PAGES", "3"))
    komikseyler_max_search_results: int = int(os.getenv("KOMIKSEYLER_MAX_SEARCH_RESULTS", "100"))
    # Edessa Kitabevi (ikas; no server-side search): product/collection
    # sitemaps cached per process, plus a bounded number of ~0.8 MB product
    # pages per search for volumes the series collection page does not show.
    edessa_max_detail_requests: int = int(os.getenv("EDESSA_MAX_DETAIL_REQUESTS", "15"))
    edessa_index_ttl_minutes: float = float(os.getenv("EDESSA_INDEX_TTL_MINUTES", "360"))

    # Mangakol catalog sync (catalog source, NOT a store): bounded list
    # pages (445 manga / ~23 per page) and per-manga volume fragment pages.
    mangakol_max_list_pages: int = int(os.getenv("MANGAKOL_MAX_LIST_PAGES", "40"))
    mangakol_max_volume_pages: int = int(os.getenv("MANGAKOL_MAX_VOLUME_PAGES", "20"))
    # Volume detail pages a catalog sync may open to read ISBNs (only for
    # released volumes that have none yet). The sync holds the write gate,
    # so this bounds how long price refresh waits; the backlog is spread
    # over consecutive syncs.
    mangakol_max_isbn_requests: int = int(os.getenv("MANGAKOL_MAX_ISBN_REQUESTS", "600"))

    # Background price import policy. Search never schedules an import.
    import_freshness_ttl_minutes: int = int(
        os.getenv("IMPORT_FRESHNESS_TTL_MINUTES", "60")
    )
    # Minimum gap between any two import attempts for the same query
    # (prevents hammering the stores after a failure or an empty result).
    import_failure_retry_minutes: int = int(
        os.getenv("IMPORT_FAILURE_RETRY_MINUTES", "5")
    )
    # At most this many background import jobs run concurrently.
    import_max_concurrent_jobs: int = int(
        os.getenv("IMPORT_MAX_CONCURRENT_JOBS", "2")
    )
    # Waiting jobs are bounded independently of the fixed worker pool.
    import_queue_capacity: int = int(os.getenv("IMPORT_QUEUE_CAPACITY", "16"))
    # How long a background import waits for its query's lock when a manual
    # /import holds it (the two paths share one per-query import lock).
    import_lock_timeout_seconds: float = float(
        os.getenv("IMPORT_LOCK_TIMEOUT_SECONDS", "120")
    )
    # How long a background import waits for the catalog write gate when a
    # Mangakol catalog sync is running. The gate (one shared import-lock
    # key) keeps imports from creating/renaming publisher rows under a
    # running catalog sync; the sync itself refuses to start (409) while
    # an import holds the gate.
    catalog_gate_timeout_seconds: float = float(
        os.getenv("CATALOG_GATE_TIMEOUT_SECONDS", "900")
    )

    # A (volume, store) listing keeps its product: another product of the
    # same store resolving to the same volume (a different printing or
    # edition) only replaces it when cheaper, when the current product is
    # out of stock, or when the current product has not been seen for this
    # many hours. Prevents A/B price flips between import runs.
    listing_product_switch_hours: float = float(
        os.getenv("LISTING_PRODUCT_SWITCH_HOURS", "48")
    )

    # Periodic catalog sync (scheduler). Only active when the app runs with
    # auto_init (production shape — tests run auto_init=False and never
    # start it). The first run happens one full interval AFTER process
    # start (deliberately no catch-up at startup), so the gap between
    # syncs always stays within [interval, 2*interval) across restarts.
    catalog_sync_enabled: bool = os.getenv(
        "CATALOG_SYNC_ENABLED", "1"
    ).strip().lower() in {"1", "true", "yes", "on"}
    catalog_sync_interval_hours: float = float(
        os.getenv("CATALOG_SYNC_INTERVAL_HOURS", "24")
    )

    # Periodic price refresh: the scheduler walks current CatalogSeries,
    # including series without ImportRecords, and dispatches gradually.
    price_refresh_enabled: bool = os.getenv(
        "PRICE_REFRESH_ENABLED", "1"
    ).strip().lower() in {"1", "true", "yes", "on"}
    price_refresh_interval_hours: float = float(
        os.getenv("PRICE_REFRESH_INTERVAL_HOURS", "12")
    )
    # Several stores drop sold-out products from search instead of marking
    # them, so their listing silently keeps its last "in stock" flag. A
    # listing not seen for this long while the SAME store's other listings
    # were refreshed is shown as "stock unknown" (never as in stock).
    listing_stale_hours: float = float(os.getenv("LISTING_STALE_HOURS", "48"))
    # After a (re)start the first cycle is derived from persisted freshness
    # (catch-up when stale) but never sooner than this settle delay.
    price_refresh_startup_delay_minutes: float = float(
        os.getenv("PRICE_REFRESH_STARTUP_DELAY_MINUTES", "10")
    )

    # Scraper reliability: retries, backoff and politeness.
    # Transient failures (network errors, 429/5xx) are retried with
    # exponential backoff + jitter; bot walls (403/429/503 with wall
    # markers) fail fast instead of retrying.
    scraper_max_retries: int = int(os.getenv("SCRAPER_MAX_RETRIES", "2"))
    scraper_retry_backoff_seconds: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_SECONDS", "1.0")
    )
    #: Minimum gap between two HTTP requests of one scraper instance
    #: (per-store rate limit; stores never wait for each other).
    # Stores that block the production host (Amazon: HTTP 503 robot check,
    # D&R: HTTP 403, Cizman: Cloudflare 403 — see RAILWAY_STAGING.md) are
    # not scraped by scheduled/background imports. Comma-separated store ids;
    # set DISABLED_STORES="" to re-enable all. Explicitly requested store ids
    # (get_scrapers(["cizman"])) still run, e.g. for a manual probe.
    disabled_stores: tuple[str, ...] = tuple(
        s.strip().lower()
        for s in os.getenv("DISABLED_STORES", "amazon,dr,cizman").split(",")
        if s.strip()
    )

    scraper_min_request_interval_seconds: float = float(
        os.getenv("SCRAPER_MIN_REQUEST_INTERVAL_SECONDS", "0.5")
    )


STAGING_DB_PATH = Path("/data/yomiba-staging.db")


def _staging_volume_mounted(path: Path) -> bool:
    return os.path.ismount(path)


def validate_database_settings(settings: Settings) -> None:
    """Refuse a cwd-dependent or in-memory production SQLite database."""
    url = make_url(settings.database_url)
    if settings.app_env in {"production", "prod"} and url.get_backend_name() == "sqlite":
        if not url.database or not Path(url.database).is_absolute():
            raise ValueError("Production SQLite DATABASE_URL must use an absolute file path")
        if not Path(url.database).is_file():
            raise ValueError("Production SQLite database file must already exist")
    if settings.app_env == "staging":
        if url.get_backend_name() != "sqlite" or url.database != str(STAGING_DB_PATH):
            raise ValueError("Staging requires the dedicated /data/yomiba-staging.db SQLite database")
        volume_path = STAGING_DB_PATH.parent
        if os.getenv("RAILWAY_VOLUME_MOUNT_PATH") != str(volume_path) or not _staging_volume_mounted(volume_path):
            raise ValueError("Staging requires a mounted Railway volume at /data")
        if volume_path.is_symlink() or STAGING_DB_PATH.is_symlink():
            raise ValueError("Staging database path cannot be a symlink")
        if STAGING_DB_PATH.exists() and not STAGING_DB_PATH.is_file():
            raise ValueError("Staging database path is not a file")
        if not STAGING_DB_PATH.exists() and not settings.staging_db_bootstrap:
            raise ValueError("Staging database is missing; set STAGING_DB_BOOTSTRAP=1 for first boot")


def prepare_staging_database(settings: Settings) -> bool:
    """Create only the explicitly approved empty staging DB on its volume."""
    if settings.app_env != "staging":
        return False
    validate_database_settings(settings)
    if STAGING_DB_PATH.exists():
        return False
    descriptor = os.open(STAGING_DB_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    return True


def validate_runtime_settings(settings: Settings) -> None:
    validate_database_settings(settings)
    if settings.auth_session_days < 1:
        raise ValueError("AUTH_SESSION_DAYS must be positive")
    if settings.app_env in {"production", "prod", "staging"} and not settings.auth_cookie_secure:
        raise ValueError("Production and staging require AUTH_COOKIE_SECURE=1")
    if settings.app_env == "staging":
        if not settings.backend_url.startswith("https://") or not settings.cors_origins or any(
            not origin.startswith("https://") for origin in settings.cors_origins
        ):
            raise ValueError("Staging requires HTTPS BACKEND_URL and CORS_ORIGINS")


def safe_database_target(settings: Settings) -> str:
    """Operational target label without credentials or URL query secrets."""
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        return f"sqlite:{Path(url.database).resolve() if url.database and url.database != ':memory:' else 'memory'}"
    return url.get_backend_name()


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
