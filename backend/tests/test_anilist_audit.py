"""Offline fixtures only: AniList edition evidence never mutates catalog data."""
import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select, func

from app.models import Volume, StoreListing, PriceHistory
from app.services.anilist_audit import (
    AniListAuditClient, match_candidates, title_key, volume_signals, enrich_plan, summarize,
)
from app.services.phantom_review import plan_merge
from tests.test_phantom_review import setup_pair
from tests.test_import_service import seed_catalog_series, make_result
from app.services.import_service import ImportAction


def media(title="Sayonara Eri", *, id=1, format="ONE_SHOT", volumes=1, synonyms=None):
    return dict(id=id, title=dict(romaji=title, english=None, native=None),
                synonyms=synonyms or [], format=format, volumes=volumes, chapters=1,
                status="FINISHED", countryOfOrigin="JP", source="ORIGINAL",
                siteUrl=f"https://anilist.co/manga/{id}")


def response(items, **kwargs):
    return httpx.Response(200, json={"data": {"Page": {
        "media": items, "pageInfo": {"hasNextPage": False}}}}, **kwargs)


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0
        self.waits = []

    def time(self):
        return self.now

    def sleep(self, delay):
        self.waits.append(delay)
        self.now += delay


def api(handler, tmp_path, clock=None, **kwargs):
    clock = clock or Clock()
    return AniListAuditClient(client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.json", clock=clock.time, sleep=clock.sleep, **kwargs)


def lookup(client):
    return client.lookup(series_id=6, title="Sayonara Eri", publisher="Gerekli Şeyler")


@pytest.mark.parametrize("fmt,vols,expected", [
    ("ONE_SHOT", None, (True, False, False, True)),
    ("MANGA", 1, (False, True, False, False)),
    ("MANGA", 100, (False, False, True, False)),
    ("MANGA", None, (False, False, False, True)),
])
def test_independent_volume_signals(fmt, vols, expected):
    flags = volume_signals(media(format=fmt, volumes=vols))
    assert tuple(flags[k] for k in ("ANILIST_ONE_SHOT", "ANILIST_SINGLE_VOLUME",
                                  "ANILIST_MULTI_VOLUME", "ANILIST_UNKNOWN")) == expected


def test_exact_synonym_native_and_conservative_matching():
    assert match_candidates(["Sayonara Eri"], [media()])["match_confidence"] == "MATCHED_HIGH"
    assert match_candidates(["Elveda Eri"], [media(synonyms=["Elveda Eri"])])["match_confidence"] == "MATCHED_HIGH"
    native = media(); native["title"]["native"] = "さよなら絵梨"
    assert title_key("さよなら絵梨")
    assert match_candidates(["さよなら絵梨"], [native])["match_confidence"] == "MATCHED_HIGH"
    assert match_candidates(["City"], [media("City")])["match_confidence"] == "MATCHED_MEDIUM"
    assert match_candidates(["Goodbye Eri Sayonara Eri"], [media()])["match_confidence"] == "MATCHED_MEDIUM"
    assert match_candidates(["Sayonara Eri"], [media(), media(id=2)])["match_confidence"] == "AMBIGUOUS"
    assert match_candidates(["Sayonara Eri"], [media()], incomplete=True)["match_confidence"] == "AMBIGUOUS"
    assert match_candidates(["Sayonara Eri"], [media("Sayonara Tokyo")])["match_confidence"] == "AMBIGUOUS"
    assert match_candidates(["Unknown Title"], [media()])["match_confidence"] == "NOT_FOUND"


def test_cache_miss_hit_stale_refresh(tmp_path):
    calls = []
    clock = Clock()
    def handle(request):
        calls.append(json.loads(request.content))
        return response([media()])
    client = api(handle, tmp_path, clock)
    assert lookup(client)["cache_status"] == "miss"
    assert len(calls) == 1
    assert calls[0]["variables"] == {"search": "Sayonara Eri", "page": 1}
    assert lookup(client)["cache_status"] == "hit"
    assert len(calls) == 1
    clock.now += 8 * 86400
    assert lookup(client)["cache_status"] == "stale"
    assert len(calls) == 2
    cached = json.loads((tmp_path / "cache.json").read_text())
    assert next(iter(cached["entries"].values()))["fetched_at"]
    offline = api(lambda _: pytest.fail("offline network"), tmp_path, clock, offline=True)
    assert lookup(offline)["cache_status"] == "hit"
    clock.now += 8 * 86400
    result = lookup(offline)
    assert result["metadata"] is None and result["error"] == "offline_cache_unavailable"


@pytest.mark.parametrize("mode", ["transport", "graphql", "invalid", "forbidden", "server"])
def test_api_failure_closed(tmp_path, mode):
    calls = []
    def handle(request):
        calls.append(request)
        if mode == "transport":
            raise httpx.ConnectError("offline")
        if mode == "graphql":
            return httpx.Response(200, json={"errors": [{"message": "unavailable"}]})
        if mode == "invalid":
            return httpx.Response(200, json={"data": None})
        return httpx.Response(403 if mode == "forbidden" else 503)
    result = lookup(api(handle, tmp_path))
    assert result["metadata"] is None and result["error"]
    assert result["match_confidence"] == "NOT_FOUND"
    assert len(calls) <= 2
    assert not (tmp_path / "cache.json").exists()


def test_rate_limit_does_not_retry_early(tmp_path):
    clock, calls = Clock(), []
    def handle(request):
        calls.append(clock.now)
        return httpx.Response(429, headers={"Retry-After": "120"})
    client = api(handle, tmp_path, clock)
    assert lookup(client)["error"] == "rate_limited"
    assert lookup(client)["error"] == "rate_limit_cooldown"
    assert len(calls) == 1


def test_short_retry_after_and_pagination_truncation(tmp_path):
    clock, calls = Clock(), []
    def handle(request):
        calls.append(clock.now)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"data": {"Page": {
            "media": [media()], "pageInfo": {"hasNextPage": True}}}})
    result = lookup(api(handle, tmp_path, clock))
    assert calls[1] - calls[0] >= 3
    assert len(calls) == 3
    assert result["match_confidence"] == "AMBIGUOUS"


def test_stale_cache_network_failure_never_promotes(tmp_path):
    clock = Clock()
    lookup(api(lambda _: response([media()]), tmp_path, clock))
    clock.now += 8 * 86400
    result = lookup(api(lambda _: httpx.Response(503), tmp_path, clock))
    assert result["error"] and result["metadata"] is None


def reviewed_fixture(session, title="Elveda Eri"):
    source, target, products = setup_pair(session)
    from app.normalization import normalize_text
    series = session.get(Volume, source).series
    series.title = title
    series.normalized_title = normalize_text(title)
    session.commit()
    for product in products:
        product["title"] = title
        product.update(isbn_verified=True, edition_verified=True, source_url=product["product_url"])
    evidence = dict(target_id=target, catalog_confirmed=True, products=products)
    plan = plan_merge(session, source, **evidence)
    anilist = {**match_candidates(["Sayonara Eri"], [media()]), "error": None}
    return source, target, evidence, plan, anilist


def test_elveda_candidate_never_applies_merge(db_session):
    source, target, evidence, plan, anilist = reviewed_fixture(db_session)
    before = [db_session.scalar(select(func.count()).select_from(m)) for m in (Volume, StoreListing, PriceHistory)]
    result = enrich_plan(plan, anilist, evidence)
    assert result["final_recommendation"] == "SAFE_MERGE_CANDIDATE"
    assert db_session.get(Volume, source).isbn == "9786258237559"
    assert db_session.get(Volume, target).isbn is None
    assert not db_session.dirty and not db_session.deleted and not db_session.new
    assert before == [db_session.scalar(select(func.count()).select_from(m)) for m in (Volume, StoreListing, PriceHistory)]


@pytest.mark.parametrize("kind", ["wrong_isbn", "publisher", "edition", "bundle", "unverified", "outage", "ambiguous", "multi"])
def test_conflicts_block_candidates(db_session, kind):
    source, target, evidence, plan, anilist = reviewed_fixture(db_session)
    product = evidence["products"][0]
    if kind == "wrong_isbn": product["isbn"] = "9786051234567"
    if kind == "publisher": product["publisher"] = "Other Publisher"
    if kind == "edition": product["conflicts"] = ["edition_conflict"]
    if kind == "bundle": product["title"] = "Elveda Eri Kutu Seti"
    if kind == "unverified": product.pop("isbn_verified")
    if kind == "outage": anilist["error"] = "offline"
    if kind == "ambiguous": anilist["match_confidence"] = "AMBIGUOUS"
    if kind == "multi": anilist["metadata"]["volumes"] = 2
    plan = plan_merge(db_session, source, **evidence)
    assert enrich_plan(plan, anilist, evidence)["final_recommendation"] == "REVIEW"


@pytest.mark.parametrize("title,volumes,expected", [
    ("Look Back", 1, "SAFE_MERGE_CANDIDATE"),
    ("Solanin", 1, "SAFE_MERGE_CANDIDATE"),  # Hypothetical fixture, not live metadata.
    ("Solanin", 2, "REVIEW"),
    ("One Piece", 110, "REVIEW"),
])
def test_work_signals_do_not_override_edition_evidence(db_session, title, volumes, expected):
    source, target, evidence, plan, _ = reviewed_fixture(db_session, title)
    anilist = {**match_candidates([title], [media(title, format="MANGA", volumes=volumes)]), "error": None}
    if title == "One Piece":
        series_id = db_session.get(Volume, source).series_id
        db_session.add_all(Volume(series_id=series_id, volume_number=n) for n in range(2, 63))
        db_session.commit()
        plan = plan_merge(db_session, source, **evidence)
    assert enrich_plan(plan, anilist, evidence)["final_recommendation"] == expected


def test_jjk_zero_preserved_in_plan_and_import(db_session, import_service):
    series = seed_catalog_series(db_session, "Jujutsu Kaisen", "Gerekli Şeyler", volumes=(0, 1))
    zero = db_session.scalar(select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 0))
    zero.isbn = "9786257590303"
    db_session.commit()
    plan = plan_merge(db_session, zero.id)
    result = enrich_plan(plan, {"metadata": media(volumes=99), "match_confidence": "AMBIGUOUS"})
    assert result["final_recommendation"] == "KEEP"
    product = make_result("bkm", "Jujutsu Kaisen 0", "100", isbn=zero.isbn, publisher="Gerekli Şeyler")
    assert import_service.import_result(product) == ImportAction.CREATED
    assert db_session.scalar(select(StoreListing)).volume_id == zero.id
    assert zero.volume_number == 0
    no_isbn = make_result("dr", "Jujutsu Kaisen Cilt 0", "110", publisher="Gerekli Şeyler")
    assert import_service.import_result(no_isbn) == ImportAction.CREATED
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 2
    unnumbered = make_result("amazon", "Jujutsu Kaisen", "100", publisher="Gerekli Şeyler")
    assert import_service.import_result(unnumbered) == ImportAction.SKIPPED


def test_legacy_phantom_isbn_resolves_to_real_volume_without_moving_isbn(db_session, import_service):
    """H1: an ISBN still held by a legacy phantom no longer starves the real
    catalog volume. The product resolves by title (single-volume fallback);
    the phantom is never a target and keeps its ISBN (no merge, no move)."""
    source, target, _ = setup_pair(db_session)
    phantom_listings = select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == source)
    before = db_session.scalar(phantom_listings)
    product = make_result("bkm", "Elveda Eri", "100", isbn="9786258237559", publisher="Gerekli Şeyler")
    assert import_service.import_result(product) == ImportAction.CREATED
    db_session.commit()
    listing = db_session.scalar(select(StoreListing).where(StoreListing.volume_id == target))
    assert listing is not None
    assert db_session.get(Volume, source).volume_number == -1
    assert db_session.get(Volume, source).isbn == "9786258237559"
    assert db_session.get(Volume, target).isbn is None
    assert db_session.scalar(phantom_listings) == before


def test_cli_offline_excludes_zero_and_is_readonly(db_session, engine, monkeypatch, capsys, tmp_path):
    import sys
    from audit_phantom_volumes import main
    source, target, _ = setup_pair(db_session)
    series = seed_catalog_series(db_session, "Jujutsu Kaisen", "Gerekli Şeyler", volumes=(0, 1))
    db_session.commit()
    db_path = __import__('pathlib').Path(engine.url.database)
    before = db_path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["audit", "--db", str(db_path), "--offline", "--cache", str(tmp_path / "empty.json")])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["total_minus_one_candidates"] == 1
    assert report["summary"]["final"] == {"SAFE_MERGE_CANDIDATE": 0, "REVIEW": 1, "KEEP": 0}
    assert len(report["preserved_zero_volumes"]) == 1
    assert report["preserved_zero_volumes"][0]["final_recommendation"] == "KEEP"
    assert report["applied"] is False
    assert before == db_path.read_bytes()
    assert report["candidates"][0]["stores"][0]["code"] == "bkm"
    monkeypatch.setattr(sys, "argv", ["audit", "--db", str(db_path), "--output", str(db_path)])
    with pytest.raises(SystemExit): main()
    assert before == db_path.read_bytes()
