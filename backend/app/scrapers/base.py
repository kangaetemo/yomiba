from abc import ABC, abstractmethod

from app.scrapers.models import SearchResult


class BaseScraper(ABC):

    @abstractmethod
    def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError