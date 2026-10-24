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


def _stale_after(db_session, statement, *, commit=True):
    from sqlalchemy import text

    cache = SwrCache("test", 3600)
    cache.get(db_session, ("k",), lambda s: "v")
    db_session.execute(text(statement))
    db_session.commit() if commit else db_session.rollback()
    return cache._is_stale(cache._values[next(iter(cache._values))][0])


def test_committed_price_write_makes_cached_feeds_stale(db_session, monkeypatch):
    from app.services import swr_cache

    monkeypatch.setattr(swr_cache, "MIN_REBUILD_SECONDS", 0)
    assert _stale_after(db_session, "UPDATE store_listings SET price = price WHERE id = -1")
    assert _stale_after(db_session, "DELETE FROM series_popularity WHERE series_id = -1")


def test_unrelated_or_rolled_back_writes_keep_the_cache(db_session, monkeypatch):
    from app.services import swr_cache

    monkeypatch.setattr(swr_cache, "MIN_REBUILD_SECONDS", 0)
    assert not _stale_after(db_session, "UPDATE user_sessions SET revoked_at = NULL WHERE id = -1")
    assert not _stale_after(db_session, "UPDATE store_listings SET price = price WHERE id = -1", commit=False)
    assert not _stale_after(db_session, "SELECT 1 FROM store_listings")


def test_rebuilds_after_a_change_are_spaced_out(db_session):
    from sqlalchemy import text

    cache = SwrCache("test", 3600)
    cache.get(db_session, ("k",), lambda s: "v")
    db_session.execute(text("UPDATE volumes SET id = id WHERE id = -1"))
    db_session.commit()
    built_at = cache._values[next(iter(cache._values))][0]
    assert not cache._is_stale(built_at)  # just built: waits MIN_REBUILD_SECONDS


def test_description_worker_writes_keep_the_cache(db_session, monkeypatch):
    from app.models import Publisher, Series, Volume
    from app.services import swr_cache
    from app.utils import utcnow

    monkeypatch.setattr(swr_cache, "MIN_REBUILD_SECONDS", 0)
    pub = Publisher(name="P", normalized_name="p")
    db_session.add(pub)
    db_session.flush()
    series = Series(publisher_id=pub.id, title="S", normalized_title="s", slug="s")
    db_session.add(series)
    db_session.flush()
    volume = Volume(series_id=series.id, volume_number=1)
    db_session.add(volume)
    db_session.commit()

    cache = SwrCache("test", 3600)
    cache.get(db_session, ("k",), lambda s: "v")
    built_at = next(iter(cache._values.values()))[0]
    volume.description, volume.description_source = "Bir hikâye.", "bkm"
    volume.description_checked_at = utcnow()
    db_session.commit()
    assert not cache._is_stale(built_at)
    volume.cover_key = "covers/1.jpg"  # covers do show on the home page
    db_session.commit()
    assert cache._is_stale(built_at)
