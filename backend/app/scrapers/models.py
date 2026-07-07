from decimal import Decimal

from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    volume_number: float | None = None

    isbn: str | None = None

    price: Decimal

    product_url: str

    image_url: str | None = None

    publisher: str | None = None

    author: str | None = None

    in_stock: bool

    store: str