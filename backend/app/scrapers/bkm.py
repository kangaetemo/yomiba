import json
import re
from decimal import Decimal

import httpx

from app.scrapers.models import SearchResult


class BKMScraper:
    API_URL = "https://bkm-best.wawlabs.com/search_v2"

    def _extract_volume(self, title: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)$", title)

        if match:
            return float(match.group(1))

        return None

    def search(self, query: str) -> list[SearchResult]:

        search_params = {
            "query": query,
            "facet": [
                {"field": "category", "type": "value"},
                {"field": "writer", "type": "value"},
                {"field": "brand", "type": "value"},
            ],
            "filter": [
                {"field": "category", "type": "value", "values": []},
                {"field": "brand", "type": "value", "values": []},
                {"field": "writer", "type": "value", "values": []},
            ],
            "page_number": 1,
        }

        response = httpx.get(
            self.API_URL,
            params={
                "search_params": json.dumps(
                    search_params,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        results: list[SearchResult] = []

        for item in data["res"]:

            price = Decimal(
                item["price_sell"]
                .replace(".", "")
                .replace(",", ".")
            )

            results.append(
                SearchResult(
                    title=item["title"],
                    volume_number=self._extract_volume(item["title"]),
                    isbn=item.get("gtin"),
                    price=price,
                    product_url=item["link"],
                    image_url=item["image"],
                    publisher=item.get("publisher"),
                    author=item.get("writer"),
                    in_stock=item["stock_level"] != "0",
                    store="BKM Kitap",
                )
            )

        return results


if __name__ == "__main__":

    scraper = BKMScraper()

    results = scraper.search("berserk")

    print(f"{len(results)} sonuç bulundu.\n")

    for result in results:

        print(result.model_dump())
        print("-" * 80)