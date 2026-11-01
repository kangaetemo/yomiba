# Store Access Research — D&R (Phase 24.5)

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

# Recommended implementation plan (NOT implemented)

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
| **D&R** | 🔴 **Not currently viable** | Hard 403 on every URL from the backend (live), no documented API/feed exists (searched), and the only conceivable automation would be reverse-engineering the mobile app's private backend — out of bounds. Viable only via a negotiated data partnership. |

---

# Verification log (this session)

**Live probes (plain client, app's normal headers, no cookies/proxy/bypass,
3–4 s spacing):**

| Request | Result |
|---|---|
| `GET dr.com.tr/robots.txt` | **403**, 2.1 KB branded block page |
| `GET dr.com.tr/arama?q=berserk` | **403**, same page |
| `GET dr.com.tr/kitap/berserk-1-athica` | **403**, same page |

**Documentation reviewed:** D&R public web (no API surface found).

**No production code was modified.**
