# Yomiba

Production process settings and safety checks: [backend/PRODUCTION.md](backend/PRODUCTION.md).
Railway staging setup and smoke checklist: [backend/RAILWAY_STAGING.md](backend/RAILWAY_STAGING.md).

**Manga price comparison and collection tracking for the Turkish market** —
think “Akakçe for manga”.

Search a series → see its editions (publisher-specific) → see every volume →
compare the same volume's price across stores → open the cheapest store.

```
Amazon   Berserk 1   ₺163,54   ← cheapest (highlighted)
BKM      Berserk 1   ₺169,00
D&R      Berserk 1   ₺260,00
```

---

## Repository layout

```
backend/                  FastAPI + SQLAlchemy (Python 3.11+)
  alembic/                schema migrations (env.py reads DATABASE_URL from settings)
    versions/             0001 baseline + 0002 series.original_title
  app/
    main.py               app factory, lifespan (migrate schema + seed stores)
    config.py             env-driven settings
    database.py           engine / session factory / Base
    models/               Publisher, Series, Volume, Store, StoreListing, PriceHistory
    normalization/        deterministic text/publisher/ISBN/volume-title rules
    scrapers/             BaseScraper + SearchResult + one module per store + registry
    services/             ImportService (dedup) + catalog_service (queries)
    schemas/              Pydantic API contract
    routes/               thin route handlers
    seed.py               idempotent store seeding
    dev_data.py           optional offline demo dataset (clearly labelled)
  tests/                  pytest suite (fixtures live in tests/fixtures)
  requirements.txt
  .env.example

frontend/                 Next.js (App Router) + TypeScript + Tailwind, no src/
  app/                    home, series/[id], volume/[id], not-found, error
  components/             SearchBar, SearchSection, SeriesCard, VolumeCard,
                          StoreListingCard, PriceBadge, LoadingSkeleton
  services/catalog.ts     typed API calls (single API layer)
  lib/api.ts              fetch wrapper (client → /api rewrite; server → direct)
  hooks/useSearch.ts      debounced search state
  types/index.ts          API contract types
```

## Quick start

### Accounts and personal data

Search, manga pages and prices remain public. Collection status, wishlist and
price alerts require an account. Register at `/register`, log in at `/login`,
and use **Çıkış Yap** in the navigation to revoke the current session.

The backend stores Argon2id password hashes and a hash of each random session
token. The browser receives a host-only, HttpOnly, SameSite=Lax cookie.
`AUTH_COOKIE_SECURE` defaults to `1`; set it to `0` only for local HTTP. All
state-changing requests require an `Origin` included in `CORS_ORIGINS` or equal
to `BACKEND_URL`, including requests proxied through the frontend `/api` path.
For a public frontend hostname, add that origin to `CORS_ORIGINS`.

Registration grants `USER` only. After intentionally upgrading the selected
database, run `python bootstrap_admin.py` from `backend/` to create the first
`ADMIN` with an interactively entered password. The command refuses to create
another active administrator. Do not start the new backend against the existing
`yomiba.db` until its migration has been reviewed and approved: backend startup
automatically upgrades the configured database to Alembic head.

The migration reserves legacy personal data under disabled account ID 1 (or
other historical user IDs). It does not assign that data to any new registrant.
An operator must verify its owner before a separate, explicit ownership transfer.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # optional; defaults work

# run (from the backend/ directory)
python -m uvicorn app.main:app --reload               # Windows: py -m uvicorn app.main:app --reload
```

* API: http://127.0.0.1:8000
* Interactive docs: http://127.0.0.1:8000/docs
* Health: `GET /health`

On startup the app creates tables (idempotent) and seeds the known stores
(see `SEED_STORES` in `app/seed.py`; Amazon, D&R and Cizman are disabled by
default via `DISABLED_STORES`). No fake prices are ever seeded.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

* App: http://localhost:3000

The frontend talks to the backend through one API layer
(`frontend/services/catalog.ts`):

* **Client components** call same-origin `/api/*`; a Next.js rewrite
  (`next.config.ts`) proxies those requests to the backend server-side —
  works from any origin without CORS setup.
* **Server components** fetch the backend directly via `BACKEND_URL`.

Configure with `frontend/.env.local`:

```
BACKEND_URL=http://127.0.0.1:8000
```

### 3. Import data

The catalog is populated by running scrapers through the ImportService:

```bash
curl -X POST http://127.0.0.1:8000/import \
  -H "Content-Type: application/json" \
  -d '{"query": "berserk"}'
```

The response reports, per store: results found, created, updated, skipped,
and any scraper error. **A failing store never aborts the run** — its error is
recorded and the other stores continue.

For offline UI development you can create a clearly-labelled demo dataset
through the same ImportService code path:

```bash
cd backend
python -m app.dev_data          # or --fresh to wipe catalog rows first
```

## API

| Method | Path                        | Description                                          |
| ------ | --------------------------- | ---------------------------------------------------- |
| GET    | `/search?q=…`               | Prepared catalog data only; never starts scraping (`{results, status}`) |
| GET    | `/series/{id}`              | Series + volumes with best price and store count (numeric order) |
| GET    | `/volume/{id}`              | Volume + store listings **sorted cheapest first**    |
| GET    | `/volume/{id}/price-history`| Price history grouped per store/listing              |
| POST   | `/import`                   | Run all scrapers for a query and import results; `409` while any import for the same (normalized) query is already running |
| GET    | `/import/price-refresh/status` | Price refresh cycle and bounded worker queue status |
| POST   | `/import/price-refresh`     | Start an admin price refresh cycle; `409` if one is active |
| GET    | `/health`                   | Liveness                                             |

Errors: unknown IDs → `404`, malformed IDs → `422`, blank query → `400`.

The price scheduler reads current `CatalogSeries` membership on each cycle
(default 12 hours) and feeds a fixed worker pool (default 2 workers) through
a bounded queue (default 16 waiting jobs). Search, series and volume requests
read the database only. The schedulers, queue, query locks and `SYNC_GATE` are
process-local; run one backend ASGI process until distributed coordination is
implemented. Multiple ASGI worker processes would start duplicate schedulers
and would not share import locks.

## Architecture

### Data model

```
Publisher 1──n Series 1──n Volume 1──n StoreListing 1──n PriceHistory
Store     1──────────────────────────n StoreListing
```

* **Publisher** — publishing company. Deduplicated by `normalized_name`
  (unique, DB-level).
* **Series** — a *publisher-specific edition*. “Berserk / Athica” and
  “Berserk / Dark Horse” are different Series and are never merged by title
  alone. Unique per `(publisher_id, normalized_title)`.
* **Volume** — belongs to exactly one Series. Unique per
  `(series_id, volume_number)`; `volume_number = -1` is the sentinel for
  unnumbered items (boxes/sets) so they dedupe too. `isbn` is globally
  unique and nullable.
* **Store** — seeded; matched by stable `code` (`bkm`, `kitapsepeti`, `edessa`, ...).
* **StoreListing** — one store's current offer for one volume; unique per
  `(volume_id, store_id)`. Price stored as **integer cents** (no float
  drift); API exposes decimals.
* **PriceHistory** — appended on creation and on price **change** only;
  unchanged re-checks just bump `last_checked` (no duplicate points).

### Scraper architecture

Every scraper implements one contract:

```python
class BaseScraper:
    store_id: str      # stable code, e.g. "bkm"
    store_name: str    # display name, e.g. "BKM Kitap"
    def search(self, query: str) -> list[SearchResult]: ...
```

`SearchResult` is a frozen Pydantic model — scrapers can never return
arbitrary dicts, and every metadata field except title/URL/store is
optional (missing information is handled gracefully, never guessed).

Scrapers **never touch the database**. They only:

1. request the store (BKM: bounded multi-page catalog search, stopping on
   completion / empty page / repeated items / configured caps),
2. parse results (BKM: deduplicated by product id within the search),
3. filter junk (non-manga keywords, collections/boxes, BKM non-book
   merchandise, — for Amazon also unrelated series that merely contain the
   query word),
4. resolve sponsored/redirect URLs to the canonical product page,
5. optionally enrich with product-detail metadata (bounded by
   `SCRAPER_MAX_DETAIL_REQUESTS`),
6. return normalized `SearchResult`s with a deterministic `relevance`.

### Import & dedup (ImportService)

The only place results become rows. Resolution priority (strongest first):

1. **ISBN** (globally unique — same ISBN is the same physical book);
2. **series + volume number** inside the resolved series;
3. **normalized series title + volume** when no publisher is available —
   merged only when *exactly one* series matches; otherwise a deterministic
   `Bilinmiyor` (“Unknown”) edition is created instead of guessing;
4. otherwise **create** a new record.

Normalizations are pure, unit-tested functions (`app/normalization`):
Turkish-character folding (`İ/I/ı/i → i`, `ş → s`, …), accent stripping,
whitespace/punctuation collapsing. Deliberately conservative:
`"Berserk"` and `"Berserk of Gluttony"` never collide.

### The mandatory scenario (covered by tests)

```
BKM:    Berserk 1  ISBN X  169.00
D&R:    Berserk 1  ISBN X  260.00
Amazon: Berserk 1  ISBN X  163.54
    ⇒ 1 Volume, 3 listings; volume page lists Amazon first.
```

See `tests/test_import_service.py::test_three_stores_same_isbn_merge_into_one_volume`
and `tests/test_api.py::test_volume_stores_sorted_cheapest_first`.

### Search & automatic import (DB-first)

`GET /search` **never waits for scraping**. It answers from the catalog and
decides, per *normalized query* (`"BERSERK"` == `"berserk"`), whether the data
is fresh:

```
search(q) ──► catalog lookup (always first)
             │
             ├─ data fresh ────────────────────────────► results, state "fresh"
             ├─ data stale / missing ─┬─ job running? ──► results, "refreshing"/"importing"
             │                         └─ no job & no cooldown
             │                              └► submit BackgroundImportRunner job
             └─ no data, last attempt failed ──────────► "failed"/"idle"
```

* **Freshness** — an `import_records` row per normalized query stores
  `last_success_at` (only successful/partial attempts) and `last_attempt_at`.
  Data is fresh for `IMPORT_FRESHNESS_TTL_MINUTES` (default 60) after the last
  successful import. A *failed* refresh never makes good data stale.
* **Anti-hammering** — no new attempt for the same query within
  `IMPORT_FAILURE_RETRY_MINUTES` (default 5) of the last attempt of any kind.
* **Background execution** — `BackgroundImportRunner` (plain daemon threads,
  no Redis/Celery) runs `ImportService` in its own DB session, bounded by
  `IMPORT_MAX_CONCURRENT_JOBS` (default 2). At most one job per normalized
  query; the entry point `submit(key, query)` is what a future scheduler
  would call, so the architecture is job-ready without extra infrastructure.
* **Failure isolation** — a crashing job records `status="failed"` and keeps
  all existing catalog rows (imports only upsert; nothing is ever deleted).
  Partial success (e.g. BKM ok, Amazon/D&R bot-walled) is recorded as
  `partial` and still refreshes freshness for the successful stores.
* **API contract** — `/search` returns
  `{"results": [SeriesSummary…], "status": {state, detail, last_success_at}}`
  with `state` ∈ fresh | refreshing | importing | stale | failed | idle.
* **Frontend** — existing results render immediately; a small
  “Katalog güncelleniyor…” banner shows while a refresh is in flight; with no
  results the UI shows “Katalog hazırlanıyor…” (the hook re-polls every 8 s
  until the catalog settles) or a clear failure state.

### Scraper reliability (verified 2026-09-09)

Every scraper shares the same transport layer in `BaseScraper`:

* **Timeout** — per-request `SCRAPER_TIMEOUT` (default 20s).
* **Retry + backoff** — transient failures (network errors, 429/5xx) are
  retried up to `SCRAPER_MAX_RETRIES` (default 2 → max 3 attempts) with
  exponential backoff + jitter (`SCRAPER_RETRY_BACKOFF_SECONDS`); `429`
  honours `Retry-After`. Bot walls (HTTP 403, or 429/5xx with wall markers
  like “Robot Check”, “captcha”, Amazon’s automated-access page) **fail fast
  — never retried, never faked**: the store simply reports its error in the
  import report and keeps zero results.
* **Per-store rate limit** — each scraper instance keeps a minimum gap of
  `SCRAPER_MIN_REQUEST_INTERVAL_SECONDS` (default 0.5s) between its own
  requests; stores are independent, one slow store never throttles another.
* **Isolation** — per-store (a failing store never aborts the run), per-page
  (BKM keeps already-fetched pages if a later page fails after retries), and
  per-product (one unparseable item is skipped, the rest are kept).
* **Shared per-query import lock** — manual `POST /import` and background
  imports acquire the **same** in-process `ImportLock` keyed by normalized
  query. Two imports for “berserk”/“BERSERK” can therefore never run at the
  same time: the manual route is non-blocking and returns `409` while a
  background job holds the lock (and vice versa — a background job waits for
  a manual import, then re-checks freshness and skips if already fresh).

## Adding a new store

1. Implement `app/scrapers/<store>.py` (`BaseScraper` subclass,
   `search() -> list[SearchResult]`). No DB access. Optionally fill
   `self.stats` (per-search diagnostics, e.g. BKM's page/count breakdown) —
   `ImportService` logs it automatically.
2. Register it in `app/scrapers/registry.py`.
3. Add `(code, name)` to `SEED_STORES` in `app/seed.py`.
4. Add fixture-backed tests (`tests/fixtures/`, `tests/test_<store>_scraper.py`)
   and update the store count in `tests/test_disabled_stores.py`.

Nothing else changes — ImportService, API and frontend are store-agnostic.

## Scraper status (verified 2026-09-28)

| Store (`code`)  | Status | Source |
| --------------- | ------ | ------ |
| BKM Kitap (`bkm`) | Active | WAW `search_v2` paginated search + detail JSON-LD |
| Kitap Sepeti (`kitapsepeti`) | Active | SSR search (`?pg=`) + detail JSON-LD (stock). Sold-out products drop out of search |
| Kitapbulan (`kitapbulan`) | Active | Same CMS as Kitap Sepeti |
| Gerekli Şeyler (`gerekliseyler`) | Active | SSR search (`?tp=`), ISBN from "Stok Kodu" |
| Kitapsec (`kitapsec`) | Active | SSR search with schema.org microdata |
| Komikşeyler (`komikseyler`) | Active | Public WooCommerce Store API (JSON) |
| Edessa Kitabevi (`edessa`) | Active | ikas store without server-side search: product/collection sitemaps, series collection `__NEXT_DATA__` (price + stock), capped product-page JSON-LD |
| Cizman (`cizman`) | Disabled | Implemented; Cloudflare 403 from the production host |
| Amazon TR (`amazon`) | Disabled | Implemented; HTTP 503 robot check from datacenter IPs |
| D&R (`dr`) | Disabled | Implemented; HTTP 403 on every URL |

Listings a store stops returning keep their last stock flag; one not seen for
`LISTING_STALE_HOURS` (default 48) while the same store's other listings were
refreshed is reported as **stock unknown** (`stale`), never as in stock.
Candidate stores and access research: `docs/new-store-candidates.md`.

Bot-wall behaviour is detected explicitly and reported per store in the
import report (isolated, never fatal).

## Testing

```bash
cd backend
python -m pytest -q
```

68 tests cover: title/publisher normalization, volume-title parsing,
series matching, ISBN matching, volume dedup, listing upsert, price-history
creation, scraper parsing/filtering (fixture-backed), and all API endpoints
including the mandatory cross-store scenario and error cases.

Frontend: `cd frontend && npm run build` (type-checks + compiles).

## Design decisions & deviations (documented)

* **`normalized_name` / `normalized_title` columns** — added beyond the
  minimal field list so duplicate prevention is a *database constraint*
  (spec rule 11), not an in-memory scan.
* **`Store.code`** — stable machine identifier so scraper→store matching is
  deterministic (spec rule 9).
* **Prices as integer cents** in the DB, decimals in the API — exact
  arithmetic, no float drift.
* **`volume_number = -1` sentinel** for boxes/sets — keeps the unique
  constraint effective for unnumbered items (NULLs are distinct in SQLite/PG).
* **`Bilinmiyor` reserved publisher** — isolated home for results with no
  publisher info and an ambiguous edition, per “create a new candidate rather
  than corrupt existing data”.
* **`POST /import`** — operational trigger for the ImportService; also
  refreshes the query's freshness record like background imports.
* **Background imports via daemon threads** — deliberate: a solo project does
  not need Redis/Celery. The runner's `submit(key, query)` interface is
  scheduler-ready for a future periodic job.
* **One shared `ImportLock` per normalized query** (in-memory, single
  process) — guarantees no two imports for the same query ever run
  simultaneously, regardless of entry point; a process crash releases it
  because it never outlives its owner.
* **Bot walls fail fast in the transport layer** (403 or wall markers in the
  body) while plain 5xx/429 are retried — retrying a wall is pointless and
  rude, retrying a transient 503 is usually worth it.
* **Amazon filters unrelated series** containing the query word (e.g.
  “Berserk of Gluttony” for query “Berserk”) per spec; searching that title
  explicitly imports it normally.
* **Deluxe/box titles are skipped** as separate editions/collections until
  edition modelling exists (future feature).
* **SQLite via SQLAlchemy** — swap `DATABASE_URL` for PostgreSQL without
  code changes.
* **Schema evolution is Alembic-owned** — `init_db()` applies pending
  migrations to head on startup (the app never hand-ALTERs its database
  anymore). New schema change workflow: model change →
  `alembic revision --autogenerate -m "..."` (run from `backend/`; the URL
  comes from `DATABASE_URL` via the app settings) → review the file →
  restart. The baseline migration is idempotent (`IF NOT EXISTS`), so
  un-stamped legacy databases created by older releases migrate on first
  start instead of crashing.

## Roadmap (not implemented, architecture ready)

More stores/scrapers · user accounts · collection & wishlist tracking ·
missing-volume detection · price alerts & notifications · price-history
chart on the volume page · scheduled scrape jobs · PostgreSQL + Redis ·
admin dashboard · search ranking · edition/language handling.
