import json
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

from app.scrapers.models import SearchResult
from app.utils.title_parser import parse_title


class DRScraper:
    BASE_URL = "https://www.dr.com.tr"

    def search(self, query: str) -> list[SearchResult]:

        response = httpx.get(
            f"{self.BASE_URL}/search",
            params={"Q": query},
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0 Safari/537.36"
                )
            },
        )

        soup = BeautifulSoup(response.text, "lxml")

        results: list[SearchResult] = []

        for product in soup.select(".product-card"):

            try:
                gtm = json.loads(product["data-gtm"])

                series_title, volume_number = parse_title(gtm["item_name"])

                image = product.select_one("img")

                link = product.select_one("a.js-search-prd-item")

                results.append(
                    SearchResult(
                        store_name="D&R",
                        store_id=product["data-id"],
                        title=gtm["item_name"],
                        series_title=series_title,
                        volume_number=volume_number,
                        isbn=None,
                        publisher=gtm["publisher"],
                        author=gtm["author"],
                        price=Decimal(gtm["price"]),
                        currency="TRY",
                        in_stock=product["data-status-code"] == "1",
                        product_url=self.BASE_URL + link["href"],
                        image_url=image["data-src"],
                        relevance=1.0,
                    )
                )

            except Exception as e:
                print("Hata:", e)

        return results


if __name__ == "__main__":

    results = DRScraper().search("berserk")

    print(f"\n{len(results)} sonuç bulundu.\n")

    for r in results:
        print(r.model_dump())
        print("-" * 80)