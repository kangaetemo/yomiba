"""Runtime configuration.

All configuration is read from environment variables so that nothing is
hard-coded for a particular deployment. A local ``.env`` file (see
``.env.example``) is loaded if present, but real environment variables always
take precedence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

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

    # Mangakol catalog sync (catalog source, NOT a store): bounded list
    # pages (445 manga / ~23 per page) and per-manga volume fragment pages.
    mangakol_max_list_pages: int = int(os.getenv("MANGAKOL_MAX_LIST_PAGES", "40"))
    mangakol_max_volume_pages: int = int(os.getenv("MANGAKOL_MAX_VOLUME_PAGES", "20"))

    # Automatic background import / refresh policy (DB-first search).
    # Catalog data for a query is "fresh" until the TTL expires; after that
    # the next search schedules a background refresh instead of blocking.
    import_freshness_ttl_minutes: int = int(
        os.getenv("IMPORT_FRESHNESS_TTL_MINUTES", "60")
    )
    # Minimum gap between any two import attempts for the same query
    # (prevents hammering the stores on repeated searches after a failure
    # or an empty result).
    import_failure_retry_minutes: int = int(
        os.getenv("IMPORT_FAILURE_RETRY_MINUTES", "5")
    )
    # At most this many background import jobs run concurrently.
    import_max_concurrent_jobs: int = int(
        os.getenv("IMPORT_MAX_CONCURRENT_JOBS", "2")
    )
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

    # Periodic price refresh (scheduler): every interval, every query whose
    # last successful import is stale (older than
    # import_freshness_ttl_minutes) is re-imported in the background — so a
    # search almost never has to trigger a store scrape at request time.
    # Same production-only (auto_init) and env-gated pattern as the catalog
    # sync; the first run happens one interval after process start.
    price_refresh_enabled: bool = os.getenv(
        "PRICE_REFRESH_ENABLED", "1"
    ).strip().lower() in {"1", "true", "yes", "on"}
    price_refresh_interval_hours: float = float(
        os.getenv("PRICE_REFRESH_INTERVAL_HOURS", "6")
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
    scraper_min_request_interval_seconds: float = float(
        os.getenv("SCRAPER_MIN_REQUEST_INTERVAL_SECONDS", "0.5")
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
