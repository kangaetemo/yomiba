"""Live verification for Task 1 (merch relevance filter).

Runs every registered store scraper against the live stores for the four
queries demanded by the spec (naruto, one piece, berserk, jujutsu kaisen)
and reports accepted titles + rejection stats. Any accepted title that
looks like merchandise is flagged.
"""

from __future__ import annotations

import re
import sys
import time

from app.scrapers.base import ScraperError
from app.scrapers.registry import registered_scrapers

QUERIES = ["naruto", "one piece", "berserk", "jujutsu kaisen"]

# Conservative human eye-check list: if an ACCEPTED title contains one of
# these, a merch item slipped through the filter.
MERCH_RE = re.compile(
    r"\b(fig[üu]r|action|model\s*kit|plastik\s*model|banpresto|banzai|sony|"
    r"t[iı]s[öo]rt|shiritsuku|poster|tablo|tabela|kupa|mousepad|defter|"
    r"kalem|silgi|çizboy|chibi|blind\s*box|kart|oyuncak|oyun|tcg|"
    r"playing\s*cards|kurutakke|sticker|sticker|keychain|şapka|berre|"
    r"grandista|mini\s*fig|statü|statue|die-cast|peluş|plush|çantalık|"
    r"karton\b|puzzle|yapboz|battık|bornoz|çorap|ayakkabı)\b",
    re.IGNORECASE,
)

def main() -> int:
    registry = registered_scrapers()

    total_flagged = 0
    for store_id in sorted(registry):
        scraper = registry[store_id]()
        print(f"\n=== {store_id} ===", flush=True)
        for query in QUERIES:
            t0 = time.time()
            try:
                results = scraper.search(query)
            except ScraperError as exc:
                print(f"  {query!r}: SCRAPER ERROR ({exc})")
                continue
            except Exception as exc:  # noqa: BLE001 - verification script
                print(f"  {query!r}: UNEXPECTED {type(exc).__name__}: {exc}")
                continue
            title_list = ", ".join(r.title for r in results)
            print(
                f"  {query!r}: {len(results)} results "
                f"[{time.time() - t0:.0f}s] | {title_list or '—'}"
            )
            for r in results:
                if MERCH_RE.search(r.title):
                    total_flagged += 1
                    print(f"    !!! MERCH FLAG: {r.title!r}")
            rejected = scraper.stats.get("rejected", {})
            interesting = {k: v for k, v in rejected.items() if v}
            if interesting:
                print(f"      rejected: {interesting}")
    print(f"\nTOTAL FLAGGED: {total_flagged}")
    return 1 if total_flagged else 0

if __name__ == "__main__":
    sys.exit(main())
