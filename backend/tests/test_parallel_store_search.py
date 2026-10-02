"""Stores of one import are searched at the same time, not one by one."""

import threading

from app.scrapers.base import BaseScraper
from app.services.import_service import ImportService


class _Store(BaseScraper):
    def __init__(self, store_id: str, barrier: threading.Barrier, fail: bool = False):
        super().__init__()
        self.store_id = store_id
        self.store_name = store_id
        self._barrier = barrier
        self._fail = fail

    def search(self, query):
        # Passes only when every store is inside search() at once.
        self._barrier.wait(timeout=5)
        if self._fail:
            raise RuntimeError("store down")
        return []


def test_stores_are_searched_concurrently_and_in_order():
    barrier = threading.Barrier(3)
    scrapers = [_Store("a", barrier), _Store("b", barrier, fail=True), _Store("c", barrier)]
    outcomes = ImportService._search_all(scrapers, "berserk")
    assert outcomes[0] == [] and outcomes[2] == []
    assert isinstance(outcomes[1], RuntimeError)  # one store failing is isolated


def test_run_import_reports_a_failing_store(db_session):
    barrier = threading.Barrier(2)
    service = ImportService(db_session, scrapers=[_Store("a", barrier), _Store("b", barrier, fail=True)])
    report = service.run_import("berserk")
    assert [s.store_code for s in report.stores] == ["a", "b"]
    assert report.stores[0].error is None
    assert "store down" in report.stores[1].error
