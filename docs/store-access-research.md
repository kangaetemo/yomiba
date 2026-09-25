# Store Access Research — Amazon TR + D&R (Phase 24.5)

**Date:** 2026-09-10 · **Author:** research phase, no production code changed
**Method:** (1) minimal live HTTP probing from the Yomiba sandbox, (2) official
documentation review, (3) inspection of the existing scraper code.

**Safety boundary honored:** no bot-protection bypass of any kind — no CAPTCHA
handling, no stealth/anti-detection, no fingerprint or cookie tricks, no proxy
rotation, no reverse-engineering of private endpoints. Every 403/503 was
recorded as *blocked*. Live probing used a plain `httpx` client with the app's
own normal headers (standard User-Agent + `Accept-Language: tr`), no cookies,
no session, 3–4 s spacing, 6 store requests + 2 robots.txt requests total.

**Test environment:** the Yomiba dev sandbox (datacenter egress IP, EU region),
same environment that produced the earlier P18/P20 observations. Results from a
datacenter IP are representative of the *backend server's* position, not of a
residential Turkish browser.

Legend: **[LIVE]** = observed in this session · **[DOC]** = official/secondary
documentation · **[INFER]** = reasoned from the above.

---

# Amazon TR (amazon.com.tr)

## Accessibility

- **[LIVE]** `GET /s?k=<real ISBN>` → **HTTP 503** (2.8 KB generic Turkish
  "Üzgünüz… bir hata oluştu" error page; body contains an "automated" marker).
  No CAPTCHA form, no results, no product markup.
- **[LIVE]** `GET /s?k=Berserk Cilt 1` (title search) → **HTTP 503**, identical
  page.
- **[LIVE]** `GET /robots.txt` → **HTTP 200** (6.5 KB, standard Amazon
  disallow list). Notably, generic `/s` (search) and `/dp` (product) paths are
  **not** disallowed in robots.txt — only account/cart/checkout sub-paths.
  (robots.txt permissiveness does not imply scraping permission; Amazon's
  conditions of use separately prohibit automated access.)
- **[INFER]** Consistent with P18/P20/P21 history: from this environment Amazon
  is *intermittently* reachable — one "naruto" search got a real 200 once,
  everything else 503. **Intermittent 200s ≠ reliable access.** A datacenter
  client cannot count on Amazon web pages.
- **[DOC]** Amazon's web ToS prohibits automated access; the 503 wall is the
  enforcement. The only sanctioned programmatic path is the affiliate API
  (below).

## Search

- **[LIVE]** Not testable: both ISBN-keyword and title-keyword search requests
  are 503-walled from this environment.
- **[INFER]** When reachable (rare), the existing scraper's selectors
  (`div[data-asin]`, price `.a-offscreen`, title `h2 a`) match Amazon's real
  search markup and were validated against captured structure in P18. Search
  pages expose title/price/image/stock but **not** ISBN or publisher — those
  require product-detail requests (as the current scraper already does via
  `_enrich_one`).

## ISBN lookup

- **[LIVE]** Web ISBN search: 503 (blocked).
- **[DOC]** Via the **Creators API** (official, see below): `GetItems` accepts
  **ASIN only** (`ItemIdType` = `ASIN`; PA-API 5's ISBN/EAN/UPC item types are
  **not** carried over). ISBN-first therefore works as a **two-step** flow:
  `SearchItems(keyword=<ISBN>)` → read `ExternalIds` from the result → verify
  the ISBN matches → `GetItems(ASIN)`. This is *more* reliable than title
  search because an ISBN keyword is an exact identifier, and the ExternalIds
  check removes ambiguity.

## Product page data

- **[LIVE]** Not testable: detail pages are behind the same 503 wall (search is
  already blocked, so no ASIN could be resolved from here).
- **[INFER]** Amazon product pages do carry the data we need (detail bullets:
  ISBN-13/10, Yayıncı/publisher, author, language; price + availability in the
  buy box; JSON-LD `Book`/`Product` with `isbn` + `offers`). The current
  scraper already parses the bullet-table path. This is relevant *only* if a
  legitimate access path existed — it does not for a plain HTTP client.

## Structured data

- **[INFER]** Product pages expose JSON-LD (schema.org Book with `isbn`,
  `offers`); search results expose none. Could not be verified live because
  the wall blocks before any HTML is served.

## Official / documented APIs

- **[DOC]** **PA-API 5 is deprecated** — official deprecation notice: PA-API 5
  calls now return `403 AccessDeniedException` ("Product Advertising API is
  deprecated. Please migrate to Creators API"), with sunset announced for
  **15 May 2026**. **Creators API** is the supported successor (REST, OAuth 2.0
  client-credentials, Python SDK available).
  - **Operations:** `SearchItems` (keyword), `GetItems` (up to 10 ASINs,
    `ItemIdType` = **ASIN only**), `GetVariations`, `GetBrowseNodes`.
  - **Data available:** `itemInfo.title`, `itemInfo.byLineInfo` (publisher,
    author), `itemInfo.contentInfo` (publication date, language),
    `itemInfo.externalIds` (**ISBN**), `offersV2.listings` (**price,
    availability, buy-box winner, merchant**), `images`. All fields Yomiba
    needs are present.
  - **Turkey:** PA-API 5 officially listed Turkey (TR, marketplace id
    `A33AVAJ2PDY3EV`) as a supported marketplace; Creators API docs' locale
    selector includes Turkey and states credentials work globally with the
    target marketplace's partner tag + regional approval. TR coverage is
    **[DOC, high confidence]**; final confirmation happens at registration.
  - **Eligibility (the hard part):** approved Amazon Associates account
    **+ at least 10 qualified sales in the trailing 30 days** (per-locale).
    If sales drop below the threshold for 30 days, API access is temporarily
    revoked (restored when sales resume). No workaround exists for new
    accounts. **[DOC, multiple corroborating sources incl. official docs
    screenshot of the AssociateNotEligible error text]**
  - **Limits:** 1 request/second, 8,640 requests/day for the first 30 days,
    then scaled by sales performance; 429 on exceedance; Amazon recommends
    caching product data (~24 h is the common practice) and batching (GetItems
    takes 10 ASINs per call). **[DOC]**
  - **Usage rules:** data must be displayed on a public website with
    attribution/affiliate links — Yomiba (public price comparison linking out
    to Amazon) fits this model. **[DOC]**

## Current blockers

1. **[LIVE]** Web access 503-walled from the backend environment (consistent
   with all prior phases; intermittent single 200s are not reliable).
2. **[DOC]** The only legitimate API (Creators API) is **not obtainable today**:
   Yomiba has no Associates account and zero sales; the 10-qualified-sales
   rule cannot be met (or maintained) for a zero-traffic project.

## Production feasibility

- **Technically possible (web scraping):** yes, *when not walled* — the parser
  logic already exists and is correct.
- **Reliably accessible (web scraping):** **no.** 503 from datacenter egress is
   the norm; relying on intermittent 200s would produce flaky, untrustworthy
   catalog data and violates Amazon's ToS.
- **Officially supported (Creators API):** yes, **in principle** — but
  **not obtainable without qualifying affiliate sales**.
- **Suitable for production today:** **no.** Re-evaluate only if Yomiba ever
  becomes a public site with real affiliate traffic (10 sales / 30 days /
  locale).

---

# D&R (dr.com.tr)

## Accessibility

- **[LIVE]** `GET /robots.txt` → **HTTP 403** (2.1 KB).
- **[LIVE]** `GET /arama?q=berserk` (the scraper's search path) → **HTTP 403**.
- **[LIVE]** `GET /kitap/berserk-1-athica` (product URL) → **HTTP 403**.
- All three return the **same** branded page (`<title>Sizin İçin
  Çalışıyoruz</title>` — "we are working for you"): an edge/WAF-level block
  applied to *every* URL for this client class. No CAPTCHA challenge was
  served; it is a hard refusal, not a solvable challenge. Nothing was attempted
  beyond recording it.

## Search

- **[LIVE]** Not testable — 403 at the edge before any content.
- **[INFER]** The current scraper's search-grid selectors
  (`/kitap/…`, `/manga/…` product anchors, price spans) were written against
  D&R's public structure and validated with recorded fixtures in P18; they are
  plausible but **unverified against the live site** by anyone with server
  access.

## ISBN lookup

- **[LIVE]** Not testable (403).
- **[INFER]** D&R search accepts ISBN keywords in the browser (normal user
  behavior), so an ISBN-first flow would be natural *if* access existed.

## Product page data

- **[LIVE]** Not testable (403).
- **[INFER]** D&R detail pages historically carry schema.org JSON-LD
  (`Book`/`Product` with `isbn`, `publisher`, `offers`) — the same standard
  markup BKM uses; the current scraper already has the JSON-LD enrichment path
  (`_enrich_one` → `product_json_ld_node`). This is the stable target *if* a
  legitimate access path ever exists.

## Structured data

- **[INFER]** JSON-LD on detail pages as above; search pages carry price in
  plain markup. Unverified live.

## Official / documented APIs

- **[DOC]** None found. No developer portal, no documented product API, no
  public data feed, no affiliate API from D&R (searched multiple angles:
  "dr.com.tr API", "D&R açık api / kurumsal entegrasyon / developer"). The
  mobile app obviously talks to some backend API, but it is **undocumented and
  unofficial**; using it would mean reverse-engineering a private interface —
  outside the safety boundary of this phase, and not a durable dependency.
- **[INFER]** A legitimate route would require a business arrangement
  (data partnership / corporate integration contact via D&R). That is a
  commercial conversation, not an engineering one.

## Current blockers

1. **[LIVE]** Hard 403 on every URL from the backend environment (including
   robots.txt) — uniform edge-level WAF block.
2. **[DOC]** No documented or legitimate API/feed exists.

## Production feasibility

- **Technically possible (browser, residential TR):** probably, in principle
  (the site works for real users); **not verifiable from this environment**
  and not something we may force.
- **Reliably accessible from the backend:** **no.**
- **Officially supported:** **no** — no documented interface exists.
- **Suitable for production today:** **no**, unless a data partnership is
  negotiated.

---

# Recommended architecture

Keep the current contract as the backbone; add one *optional* capability for
stores that have an identifier-first source:

```
import for query Q
   │
   ├─ store supports ISBN-first lookup AND candidate ISBNs are known
   │     │  (e.g. the same batch already yielded an ISBN from another store,
   │     │   or a future catalog-driven refresh)
   │     ▼
   │   scraper.lookup_isbn(isbn)          ← new OPTIONAL method
   │     │  Amazon (Creators API): SearchItems(isbn) → verify ExternalIds
   │     │                         → GetItems(ASIN) → SearchResult(isbn=…)
   │     ▼
   │   return 0/1 validated SearchResult (never guess)
   │
   └─ otherwise (or lookup unavailable / no ISBN known)
         ▼
       scraper.search(Q)                  ← existing, unchanged
         ▼
       existing ImportService resolution (ISBN → series+vol → new)
```

Principles:
- **ISBN is the strongest identity** (unchanged): any ISBN-first result is
  still validated by `ImportService.import_result` exactly like a search
  result; the ISBN in the response is the dedup key.
- **No invented data:** a lookup that yields zero or ambiguous candidates
  returns nothing (or raises `ScraperError` for transport/blocked cases);
  ImportService's per-result isolation already handles that.
- **Search remains the fallback** (BKM today; any store later).

## Fit with the existing scraper contract (no changes made)

| Question | Finding |
|---|---|
| Reusable methods | `BaseScraper.get()` (throttle + retry + bot-wall fail-fast), `soup()`, `extract_json_ld()` / `product_json_ld_node()`, `stats`, `close()`/context manager — all reusable by an API-based Amazon scraper (API responses are JSON; `soup()` not needed, `get()` semantics fit). |
| New scraper method useful? | **Yes:** optional `BaseScraper.lookup_isbn(isbn: str) -> list[SearchResult]` with a base implementation that raises `NotImplementedError` (or returns `[]`); `ImportService` calls it only when the scraper declares support (e.g. `supports_isbn_lookup = True` class flag). BKM/D&R keep `search()` only. |
| `SearchResult` extension? | Consider a generic **`external_id: str | None`** (Amazon ASIN) + a nullable column on `StoreListing`. Enables cheap re-checks: a future price-refresh job calls `GetItems(ASIN)` (batch of 10) instead of re-searching. Not needed for correctness today — defer until the API route exists. |
| blocked/unavailable status? | Today a blocked store surfaces as `store_report.error` text (`"ScraperError: amazon: request blocked or robot-checked (HTTP 503)…"`) and search detail ("2 store(s) unreachable"). That is functional. A future per-store explicit enum (`ok` / `blocked` / `error`) on `StoreImportResult` → API response would make the frontend able to show a distinct "store unreachable" state — small, non-breaking schema addition, defer to a store-UX phase. |
| ISBN in scraper input/context? | Not available today (`search(query)` only). The optional `lookup_isbn` above is the minimal way in. ImportService would pass candidate ISBNs from the *same batch* (e.g. BKM's ISBN for volume N) — no new public API needed. |

## Rate limiting / reliability (must be kept, not loosened)

- **[DOC]** Creators API limits: **1 req/s** and **8,640 req/day** (first 30
  days), scaled by sales; 429 on exceedance.
- **[LIVE/INFER]** The current throttle is **global**
  (`scraper_min_request_interval_seconds`, default **0.5 s**, env-configured)
  and is read from shared `Settings` by every `BaseScraper`. 0.5 s spacing is
  *faster* than Amazon's 1 req/s allowance — a future Amazon API scraper must
  enforce ≥ 1.0 s per store (small future change: per-store interval override,
  e.g. class attribute or `SCRAPER_MIN_INTERVAL_AMAZON` env var). **Do not
  loosen the global limit to "help" Amazon; raise Amazon's floor instead.**
- Everything else from P20 stays: bounded retries with jittered exponential
  backoff (≤ 30 s cap), `Retry-After` honored, bot-wall (403/503-with-marker)
  **fail-fast without retry**, per-result and per-scraper isolation, shared
  per-query ImportLock. 429 from the API is a retryable-but-throttled state,
  not a wall: back off, and if it persists, record the store as
  unreachable for that run.
- API usage also implies **response caching** (Amazon policy + good citizen):
  a natural fit is the existing background refresh cadence (TTL 60 min) —
  well within the "don't hammer" envelope.

---

# Recommended implementation plan (NOT implemented)

## Now (no store-code changes)

1. Keep Amazon + D&R as **known-blocked stores**: the import already reports
   them per store with the exact error ("blocked or robot-checked (HTTP 503 /
   403)"), and search shows "2 store(s) unreachable". **No change needed** —
   but the frontend/README should stop implying they are "live stores"
   (honesty fix, P23/P28 territory).
2. Keep the existing Amazon/D&R scraper code (parsers are correct and
   fixture-tested); they cost one cheap request per import and report their
   block state. No removal, no loosening.

## Later, gated on external conditions

### Amazon — when Yomiba can become a public affiliate site

1. Register for Amazon Associates (TR), drive real affiliate traffic until
   **10 qualified sales / 30 days** → request **Creators API** access
   (OAuth 2.0 client credentials; store secrets via env vars, never in code).
2. Implement `AmazonApiScraper` (separate from the web scraper):
   - `lookup_isbn(isbn)`: `SearchItems(keyword=isbn)` → verify
     `ExternalIds.ISBN` → `GetItems(asin, resources=[title, byLineInfo,
     contentInfo, externalIds, offersV2.listings, images.primary.medium])`
     → `SearchResult` (price from buy-box/lowest offer, `in_stock` from
     availability, `external_id=ASIN`).
   - `search(query)`: optional later; keyword `SearchItems` with the same
     candidate-validation rules as today.
   - Per-store min interval **≥ 1.0 s**, honor 429 + `Retry-After`, batch
     GetItems (≤ 10 ASINs), cache responses ≥ the refresh TTL.
3. Add `StoreListing.external_id` + `SearchResult.external_id` (non-breaking,
   migration via the existing startup-ensure pattern until Alembic).
4. Wire `lookup_isbn` into ImportService as the optional pre-search step above.

### D&R — only via partnership

1. Contact D&R about a data/API partnership (commercial track; nothing to
   build until an agreement exists).
2. If an agreement produces an endpoint: a thin `DrApiScraper` using the same
   BaseScraper reliability infrastructure (throttle, retry, fail-fast,
   per-store interval), JSON/JSON-LD parsing, same ImportService boundary.
3. If no agreement ever happens: D&R stays **documented as unavailable** —
   remove or clearly label the scraper; the import report already degrades
   gracefully.

## Classification

| Store | Classification | Why |
|---|---|---|
| **Amazon TR** | 🔴 **Not currently viable** (web) · 🟡 **Possible with limitations** (Creators API, gated) | Web: 503-walled from backend egress (live, consistent with 4 prior observations), ToS-prohibited to force. API: official, TR-supported, has every needed field — but **unobtainable without 10 qualified affiliate sales/30 days**, then 1 TPS + 8.64k/day + public-attribution usage rules. Re-classify 🟢 only after an approved account is live. |
| **D&R** | 🔴 **Not currently viable** | Hard 403 on every URL from the backend (live), no documented API/feed exists (searched), and the only conceivable automation would be reverse-engineering the mobile app's private backend — out of bounds. Viable only via a negotiated data partnership. |

---

# Verification log (this session)

**Live probes (6 store requests + 2 robots, plain client, app's normal
headers, no cookies/proxy/bypass, 3–4 s spacing):**

| Request | Result |
|---|---|
| `GET amazon.com.tr/robots.txt` | 200, 6.5 KB (standard disallows; `/s`, `/dp` not disallowed) |
| `GET amazon.com.tr/s?k=9786256335424` (real Berserk v1 ISBN) | **503**, 2.8 KB generic error page |
| `GET amazon.com.tr/s?k=Berserk Cilt 1` | **503**, identical |
| `GET dr.com.tr/robots.txt` | **403**, 2.1 KB branded block page |
| `GET dr.com.tr/arama?q=berserk` | **403**, same page |
| `GET dr.com.tr/kitap/berserk-1-athica` | **403**, same page |

**Documentation reviewed:** Amazon Associates help (PA-API 5 launch FAQ — TR
in supported list), PA-API 5 deprecation notice, Creators API introduction /
GetItems reference / FAQ, 10-qualified-sales rule (official error-text
screenshot + multiple independent reports, Nov 2025 – May 2026), rate-limit
sources (1 TPS / 8,640 TPD), D&R public web (no API surface found).

**No production code was modified.** No database/catalog/collection data was
written by this research (probes were read-only GETs; the running app's own
scheduled background imports may have touched the DB independently of this
phase — that is normal app behavior, verified separately in the run log).
Existing test suite: unchanged, re-run green.
