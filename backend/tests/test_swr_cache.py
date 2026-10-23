"""SwrCache: an expired feed is served at once and rebuilt in the background."""
import threading

from app.services.swr_cache import CacheWarmer, SwrCache


def test_cold_key_computes_once_then_serves_the_cached_value(db_session):
    cache = SwrCache("test", 300)
    calls = []
    compute = lambda session: calls.append(1) or len(calls)  # noqa: E731
    assert cache.get(db_session, ("a",), compute) == 1
    assert cache.get(db_session, ("a",), compute) == 1
    assert cache.get(db_session, ("b",), compute) == 2  # own entry per key
    assert len(calls) == 2


def test_expired_value_is_served_while_one_refresh_runs(db_session):
    cache = SwrCache("test", 0)  # every value is already stale
    release = threading.Event()
    refreshed = threading.Event()
    calls = []

    def compute(session):
        calls.append(1)
        if len(calls) > 1:  # the background refresh
            release.wait(5)
            refreshed.set()
        return len(calls)

    assert cache.get(db_session, ("k",), compute) == 1
    # Stale: the old value comes back at once, however many visitors ask.
    assert cache.get(db_session, ("k",), compute) == 1
    assert cache.get(db_session, ("k",), compute) == 1
    release.set()
    assert refreshed.wait(5)
    assert len(calls) == 2  # one refresh, not one per visitor
    seen = None
    for _ in range(50):  # the refresh thread stores its value right after
        seen = cache._values[next(iter(cache._values))][1]
        if seen == 2:
            break
        threading.Event().wait(0.02)
    assert seen == 2


def test_failed_refresh_keeps_serving_the_previous_value(db_session):
    cache = SwrCache("test", 0)
    done = threading.Event()

    def boom(session):
        done.set()
        raise RuntimeError("database busy")

    assert cache.get(db_session, ("k",), lambda s: "old") == "old"
    assert cache.get(db_session, ("k",), boom) == "old"
    assert done.wait(5)
    assert cache.get(db_session, ("k",), lambda s: "old") == "old"


def test_warmer_runs_at_once_and_stops(engine):
    from sqlalchemy.orm import sessionmaker

    ran = threading.Event()
    warmer = CacheWarmer(sessionmaker(bind=engine), lambda session: ran.set(), every_seconds=3600)
    warmer.start()
    assert ran.wait(5)
    warmer.stop(timeout=5)
