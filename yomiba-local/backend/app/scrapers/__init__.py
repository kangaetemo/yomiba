"""Scraper package.

Scrapers are independent of the database: each one knows only how to talk to
one store and how to express the findings as :class:`SearchResult` objects.
Mapping those results into database entities is the job of
``app.services.import_service.ImportService``.
"""

from .registry import get_scrapers, registered_scrapers
from .search_result import SearchResult
from .base import BaseScraper, ScraperError

__all__ = [
    "SearchResult",
    "BaseScraper",
    "ScraperError",
    "get_scrapers",
    "registered_scrapers",
]
