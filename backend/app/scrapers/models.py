from decimal import Decimal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    # Scraper bilgisi
    source_name: str
    source_id: str | None = None

    # Ürün bilgisi
    title: str
    series_title: str
    volume_number: float | None = None

    # Kimlik bilgileri
    isbn: str | None = None

    # Yayın bilgileri
    publisher: str | None = None
    author: str | None = None

    # Satış bilgileri
    price: Decimal
    currency: str = "TRY"
    in_stock: bool = True

    # Linkler
    product_url: str
    image_url: str | None = None

    # İleride sıralama için
    relevance: float = Field(default=1.0)