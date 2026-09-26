# Railway staging runbook

This is a preparation and smoke-test plan. It does not deploy Yomiba or touch
the existing `backend/yomiba.db`.

## Service configuration

Railway's Railpack detects `backend/requirements.txt` as Python. Set the
service **Root Directory** to `/backend`; do not add a Dockerfile or Procfile.
Override Railpack's generic FastAPI command because this app is
`app.main:app`, not `main:app`:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

Use one replica, one worker, no `--reload`, and attach one persistent volume at
`/data`. Set the Railway healthcheck path to `/ready` (startup migration and
local DB checks finish before it returns 200). Railway supplies `PORT` and
`RAILWAY_VOLUME_MOUNT_PATH`; do not set either by hand. The process requires
Python 3.11+; use `RAILPACK_PYTHON_VERSION=3.11` for the staging build.

The staging DB is **only** `sqlite:////data/yomiba-staging.db`. On first boot,
`APP_ENV=staging` and `STAGING_DB_BOOTSTRAP=1` create that empty file only when
`/data` is a mounted Railway volume. Alembic then migrates it to head, seeds
stores, checks readiness, and starts the import runner. Once boot succeeds,
set `STAGING_DB_BOOTSTRAP=0`; subsequent restarts require the existing DB.
Wrong/missing mount, a different DB path, or missing opt-in abort startup.
Production's pre-existing-file rule remains unchanged.

## Variables

| Variable | Purpose | Required for initial staging? | Staging value |
| --- | --- | --- | --- |
| `APP_ENV` | Enables staging path and secure-cookie checks | Yes | `staging` |
| `DATABASE_URL` | Dedicated volume DB | Yes | `sqlite:////data/yomiba-staging.db` |
| `STAGING_DB_BOOTSTRAP` | Explicit first-boot creation | Yes on first boot | `1`, then `0` |
| `RAILPACK_PYTHON_VERSION` | Railpack Python selection | Recommended | `3.11` |
| `BACKEND_URL` | Allowed API origin for unsafe requests | Yes | Actual Railway HTTPS URL, without trailing slash |
| `CORS_ORIGINS` | Trusted browser frontend origins | Yes before browser use | Actual trusted HTTPS origin; API-only smoke can use the Railway URL |
| `AUTH_COOKIE_SECURE` | HTTPS-only session cookie | Yes | `1` |
| `AUTH_SESSION_DAYS` | Server session and cookie lifetime | No | `30` (default) |
| `AUTH_DEVICE_SECRET` | HMAC secret for trusted-device cookies (owner can log in while a third party rate-limits the email) | Recommended | Long random value; set in Railway, never commit |
| `AUTO_MIGRATION_BACKUP` | Online backup before a pending migration (`*.pre-migration-*.bak` next to the DB) | No | `1` (default) |
| `CATALOG_SYNC_ENABLED` | Catalog scheduler | Yes for first smoke | `0`, later deliberate `1` |
| `CATALOG_SYNC_INTERVAL_HOURS` | Catalog cycle interval | No | `24` (default) |
| `PRICE_REFRESH_ENABLED` | Price scheduler | Yes for first smoke | `0`, later deliberate `1` |
| `PRICE_REFRESH_INTERVAL_HOURS` | Price cycle interval | No | `12` (default) |
| `PRICE_REFRESH_STARTUP_DELAY_MINUTES` | Settle delay before a catch-up cycle after restart | No | `10` (default) |
| `LISTING_PRODUCT_SWITCH_HOURS` | Hours before a listing may switch to another product of the same store | No | `48` (default) |
| `IMPORT_MAX_CONCURRENT_JOBS` | Import worker count | No | `2` (default) |
| `IMPORT_QUEUE_CAPACITY` | Pending import limit | No | `16` (default) |
| `IMPORT_LOCK_TIMEOUT_SECONDS` | Query lock wait | No | `120` (default) |
| `CATALOG_GATE_TIMEOUT_SECONDS` | Catalog gate wait | No | `900` (default) |
| `IMPORT_FRESHNESS_TTL_MINUTES` | Price freshness | No | `60` (default) |
| `IMPORT_FAILURE_RETRY_MINUTES` | Retry spacing | No | `5` (default) |
| `SCRAPER_TIMEOUT` | HTTP request timeout | No | `20` (default) |
| `SCRAPER_MAX_DETAIL_REQUESTS` | Per-search detail cap | No | `15` (default) |
| `SCRAPER_MAX_RETRIES` | Transient retries | No | `2` (default) |
| `SCRAPER_RETRY_BACKOFF_SECONDS` | Retry spacing | No | `1.0` (default) |
| `SCRAPER_MIN_REQUEST_INTERVAL_SECONDS` | Per-store pacing | No | `0.5` (default) |
| `SCRAPER_USER_AGENT`, `SCRAPER_ACCEPT_LANGUAGE` | Request headers | No | Code defaults |
| `MANGAKOL_MAX_LIST_PAGES`, `MANGAKOL_MAX_VOLUME_PAGES` | Catalog scraper bounds | No | `40`, `20` (defaults) |
| `BKM_SEARCH_PAGE_SIZE`, `BKM_MAX_SEARCH_PAGES`, `BKM_MAX_SEARCH_RESULTS` | BKM bounds | No | `20`, `5`, `100` (defaults) |
| `KITAPSEPETI_MAX_SEARCH_PAGES`, `KITAPSEPETI_MAX_SEARCH_RESULTS` | Kitap Sepeti bounds | No | `5`, `60` (defaults) |
| `KITAPBULAN_MAX_SEARCH_PAGES`, `KITAPBULAN_MAX_SEARCH_RESULTS` | Kitapbulan bounds | No | `5`, `60` (defaults) |
| `GEREKLISEYLER_MAX_SEARCH_PAGES`, `GEREKLISEYLER_MAX_SEARCH_RESULTS` | Gerekli Şeyler bounds | No | `5`, `60` (defaults) |
| `CIZMAN_MAX_SEARCH_RESULTS` | Cizman bound | No | `60` (default) |
| `KITAPSEC_MAX_SEARCH_PAGES`, `KITAPSEC_MAX_SEARCH_RESULTS` | Kitapseç bounds | No | `5`, `60` (defaults) |
| `KOMIKSEYLER_MAX_SEARCH_PAGES`, `KOMIKSEYLER_MAX_SEARCH_RESULTS` | Komikşeyler bounds | No | `3`, `100` (defaults) |
| `LOG_LEVEL` | Backend log level | No | `INFO` |

`PORT` and `RAILWAY_VOLUME_MOUNT_PATH` are Railway-provided runtime variables.
Do not supply credentials in documentation or commit them to the repository.

## First deployment smoke procedure

1. Create an isolated Railway **staging** service from a reviewed source
   artifact. Deploy from a reviewed Git commit rather than a folder upload. Do not upload the local
   `backend/yomiba.db`, backup files, or kit ZIPs; `.gitignore` alone does not
   protect a direct folder upload. Set Root Directory `/backend`.
2. Configure the start command above, one replica, `/data` volume, `/ready`
   healthcheck, and the required variables. Keep both schedulers disabled.
3. Deploy staging only. Confirm startup logs report DB target
   `/data/yomiba-staging.db`, migration head, store seed, readiness, and a
   single import runner with two workers; confirm no crash loop.
4. From the assigned Railway HTTPS URL, request `/health` and `/ready`; both
   should return 200. The Railway healthcheck is a deployment gate, not
   continuous monitoring.
5. Inspect the running container with `railway ssh` or the Railway volume
   browser: `/data/yomiba-staging.db` exists, Alembic is at head, and `stores`
   has seeded rows. The database must not be at an app-relative path.
6. Set `STAGING_DB_BOOTSTRAP=0`. Register a unique disposable staging account
   via the API using `Origin: <Railway HTTPS origin>`; verify login, logout,
   revoked session, and `Secure; HttpOnly; SameSite=Lax` cookie attributes.
   Public registration must return `USER`. A CLI request without `Origin`
   intentionally receives 403 for unsafe methods.
7. Restart, then redeploy the service. Confirm the same account can log in
   after each operation and the DB file remains under `/data`. This is the
   controlled persistence marker. Confirm `/ready` returns 503 or startup
   fails if a test service is intentionally misconfigured with no/wrong
   mounted volume. Never test that fault on the only staging volume.
8. Optionally test `bootstrap_admin.py` interactively **inside staging only**
   after reviewing the exact target DB. Never pass the password in arguments.
9. On the Railway host, run `python outbound_smoke.py`. It makes one streamed
   GET per host, reads no response body, and prints DNS and HTTP status. The
   result must be collected on Railway: local results do not describe Railway
   egress. `403`, `429`, and `503` are classified `BLOCKED`; no bypass is used.
10. Deliberately enable the schedulers later. Verify the one-process setting,
    scheduler startup logs, admin-only queue status, and cycle logs. An empty
    first-run catalog has no price refresh jobs until catalog sync populates it.

## Resource and backup checks

Record idle RAM, active-scheduler RAM, peak RAM/CPU during a bounded scrape,
restart/OOM count, volume use, DB size, and WAL/SHM growth. The proposed
1 vCPU, 0.5 GB RAM, 0.5 GB volume are starting allocations, not validated
limits. Do not launch a full catalog import to measure connectivity.

On a temporary staging database, the local regression test runs the online
backup API and restore validation. On Railway, choose a separate backup
destination and run:

```text
python db_backup.py --source /data/yomiba-staging.db --output /tmp/yomiba-staging-check.db
python restore_check.py --db /tmp/yomiba-staging-check.db
```

Export the verified backup from the container to independent storage before
claiming disaster recovery. `/tmp` is ephemeral; a backup kept only on the
same Railway volume does not protect against volume loss. Do not run either
tool on `backend/yomiba.db` as part of this staging task.
