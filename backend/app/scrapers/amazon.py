from decimal import Decimal
import re

import httpx
from bs4 import BeautifulSoup
import urllib.parse
from app.scrapers.models import SearchResult
from app.utils.title_parser import parse_title


class AmazonScraper:
    BASE_URL = "https://www.amazon.com.tr"

    def search(self, query: str) -> list[SearchResult]:

        response = httpx.get(
            f"{self.BASE_URL}/s",
            params={"k": query},
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0 Safari/537.36"
                ),
                "Accept-Language": "tr-TR,tr;q=0.9",
            },
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        results: list[SearchResult] = []
        seen: set[str] = set()


        for product in soup.select("div[data-asin]"):

            asin = product.get("data-asin", "").strip()

            if len(asin) != 10:
                continue

            title_element = product.select_one("h2 span")

            if not title_element:
                continue

            title = title_element.get_text(" ", strip=True)

            lower = title.lower()

            # Berserk olmayanları at
            if "berserk" not in lower:
                continue

            # Manga olmayan ürünleri ele
            banned = (
                "t-shirt",
                "compression",
                "poster",
                "tablo",
                "çerçeve",
                "kolsuz",
                "oversize",
                "hoodie",
                "sweatshirt",
                "mousepad",
                "kup",
                "mug",
            )

            if any(word in lower for word in banned):
                continue

            series_title, volume_number = parse_title(title)

            link = (
                product.select_one('a[href*="/dp/"]')
                or product.select_one("h2 a")
                or product.select_one("a.a-link-normal")
            )

            if not link:
                continue

            href = link.get("href")

            if not href:
                continue

            image = product.select_one("img.s-image")

            image_url = image.get("src") if image else None

            price_container = product.select_one("span.a-price")

            if not price_container:
                continue

            whole = price_container.select_one(".a-price-whole")

            if not whole:
                continue

            fraction = price_container.select_one(".a-price-fraction")

            whole_text = re.sub(
                r"[^\d]",
                "",
                whole.get_text(strip=True),
            )

            if not whole_text:
                continue

            if fraction:
                price = Decimal(
                    f"{whole_text}.{fraction.get_text(strip=True)}"
                )
            else:
                price = Decimal(whole_text)

            key = (asin, title)

            if key in seen:
                continue

            seen.add(key)

            if asin in seen:
                continue

            seen.add(asin)

            results.append(
                SearchResult(
                    store_name="Amazon",
                    store_id=asin,
                    title=title,
                    series_title=series_title,
                    volume_number=volume_number,
                    isbn=None,
                    publisher=None,
                    author=None,
                    language=None,
                    price=price,
                    currency="TRY",
                    in_stock=True,
                    product_url=self.BASE_URL + href,
                    image_url=image_url,
                    relevance=1.0,
                )
            )

        return results


if __name__ == "__main__":

    scraper = AmazonScraper()

    results = scraper.search("berserk")

    print(f"\n{len(results)} sonuç bulundu.\n")

    for result in results:
        print(result.model_dump())
        print("-" * 80)