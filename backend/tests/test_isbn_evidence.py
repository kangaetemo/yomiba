"""ISBN decisions from evidence (migration 0018, isbn_resolver, import rules).

Every scenario is a real case from the 2026-10-17 live health report:

* Blue Lock 28/29: Mangakol lists …626 on both; the publisher's store and
  Kitapseç sell Cilt 29 as …633.
* Yubooh Uyurken 1/2: Gerekli Şeyler and Büyülü Dükkan swapped the stock
  codes; Mangakol and the distributor (Bora) agree on …431 = Cilt 1.
* Happiness 6: Mangakol now lists Cilt 5's barcode on Cilt 6.
* Monster 9: Gerekli Şeyler's "MONSTER 09" is VIZ's English edition.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import IsbnChange, IsbnIssue, ListingExclusion, Store, StoreListing, StoreObservation, Volume
from app.scrapers.base import BaseScraper
from app.scrapers.search_result import SearchResult
from app.services.import_service import ImportService
from app.services.isbn_resolver import resolve_many, set_admin_isbn, store_votes
from tests.test_import_service import seed_catalog_series

BL28, BL29 = "9786258630626", "9786258630633"
YU1, YU2 = "9786255882431", "9786255882448"
HA5, HA6 = "9786259360492", "9786259324050"
VIZ_MONSTER_9 = "9781421569147"

NAMES = {"komikseyler": "Komikşeyler", "kitapsec": "Kitapseç", "gerekliseyler": "Gerekli Şeyler",
         "buyuludukkan": "Büyülü Dükkan", "bkm": "BKM Kitap", "edessa": "Edessa"}


def product(store, title, isbn, price="200", url=None, publisher=None, in_stock=True):
    return SearchResult(store_id=store, store_name=NAMES[store], title=title,
                        product_url=url or f"https://{store}.example/{title.lower().replace(' ', '-')}",
                        isbn=isbn, publisher=publisher, price=Decimal(price), currency="TRY", in_stock=in_stock)


def scrapers(by_store: dict[str, list[SearchResult]]) -> list[BaseScraper]:
    out = []
    for code, results in by_store.items():
        cls = type(f"Fake_{code}", (BaseScraper,), {
            "store_id": code, "store_name": NAMES[code],
            "search": lambda self, query, _r=results: list(_r)})
        out.append(cls())
    return out


def run(db_session, by_store, query="q"):
    return ImportService(db_session, scrapers=scrapers(by_store)).run_import(query)


def volumes(db_session, series):
    return {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id))}


def listings(db_session):
    return {(l.volume_id, l.product_url) for l in db_session.scalars(select(StoreListing))}


def catalog(db_session, series, isbns: dict[int, str | None], current: dict[int, str | None] | None = None):
    vols = volumes(db_session, series)
    for n, isbn in isbns.items():
        vols[n].catalog_isbn = isbn
        vols[n].catalog_released = vols[n].catalog_present = True
    for n, isbn in (current or {}).items():
        vols[n].isbn, vols[n].isbn_source = isbn, "legacy" if isbn else None
    db_session.commit()
    return vols


# -- Blue Lock: Mangakol gives Cilt 28 and 29 the same ISBN ----------------------------

def test_source_duplicate_is_written_to_neither_volume(db_session):
    series = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(28, 29))
    vols = catalog(db_session, series, {28: BL28, 29: BL28})
    resolve_many(db_session, [v.id for v in vols.values()])
    db_session.commit()
    assert (vols[28].isbn, vols[29].isbn) == (None, None)
    assert {i.kind for i in db_session.scalars(select(IsbnIssue))} == {"catalog_duplicate"}


def test_stores_settle_a_source_duplicate_and_free_it_for_the_other_volume(db_session):
    series = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(28, 29))
    # Worst case: the old sync wrote Mangakol's duplicate on Cilt 29.
    vols = catalog(db_session, series, {28: BL28, 29: BL28}, current={29: BL28})
    stores = {
        "komikseyler": [product("komikseyler", "Blue Lock Cilt 28", BL28),
                        product("komikseyler", "Blue Lock Cilt 29", BL29)],
        # (the Kitapseç scraper strips its "... Komikşeyler Yayıncılık" title suffix)
        "kitapsec": [product("kitapsec", "Blue Lock Cilt 29", BL29)],
    }
    run(db_session, stores, "Blue Lock")
    # Cilt 28's product carries the ISBN Cilt 29 held: title and ISBN disagree,
    # so nothing was attached to the wrong volume…
    assert not any(vid == vols[29].id and "28" in url for vid, url in listings(db_session))
    # …and two independent stores proved Cilt 29 = …633, which explains
    # Mangakol's duplicate: Cilt 28 takes …626.
    assert (vols[28].isbn, vols[29].isbn) == (BL28, BL29)
    assert vols[29].isbn_source == "stores"
    assert db_session.scalar(select(IsbnIssue)) is None

    run(db_session, stores, "Blue Lock")  # the next price refresh attaches every product
    assert listings(db_session) == {
        (vols[28].id, "https://komikseyler.example/blue-lock-cilt-28"),
        (vols[29].id, "https://komikseyler.example/blue-lock-cilt-29"),
        (vols[29].id, "https://kitapsec.example/blue-lock-cilt-29"),
    }


# -- Yubooh Uyurken: two stores of one feed swapped the codes ---------------------------

def _yubooh(db_session):
    series = seed_catalog_series(db_session, "Yubooh Uyurken", "Artemis", volumes=(1, 2))
    vols = catalog(db_session, series, {1: YU1, 2: YU2})
    resolve_many(db_session, [v.id for v in vols.values()])
    db_session.commit()
    assert (vols[1].isbn, vols[2].isbn) == (YU1, YU2)
    return vols


def _swapped(store):
    return [product(store, "Yubooh Uyurken 2", YU1, "276.25"), product(store, "Yubooh Uyurken 1", YU2, "276.25")]


def test_swapped_store_isbns_are_not_attached_and_the_old_listing_goes(db_session):
    vols = _yubooh(db_session)
    gs = db_session.scalar(select(Store).where(Store.code == "gerekliseyler")) or Store(code="gerekliseyler", name="Gerekli Şeyler")
    db_session.add(gs)
    db_session.flush()
    # What the live site showed: the "Cilt 2" product on the Cilt 1 page.
    db_session.add(StoreListing(volume_id=vols[1].id, store_id=gs.id, price=27625, in_stock=True,
                                product_url="https://gerekliseyler.example/yubooh-uyurken-2"))
    db_session.commit()

    run(db_session, {"gerekliseyler": _swapped("gerekliseyler"), "buyuludukkan": _swapped("buyuludukkan")})

    assert listings(db_session) == set()
    reasons = {o.reason for o in db_session.scalars(select(StoreObservation))}
    assert reasons == {"isbn_title_conflict"}
    # One shared feed is one vote: the catalog stays right.
    assert store_votes(db_session, vols[2].id) == {YU1: 1}
    assert (vols[1].isbn, vols[2].isbn) == (YU1, YU2)


def test_stores_never_override_a_usable_catalog_isbn(db_session):
    """Even two independent stores agreeing against Mangakol only open an
    issue: Mangakol is counter-evidence."""
    vols = _yubooh(db_session)
    run(db_session, {"gerekliseyler": _swapped("gerekliseyler"), "edessa": _swapped("edessa")})
    assert (vols[1].isbn, vols[2].isbn) == (YU1, YU2)
    assert db_session.get(IsbnIssue, vols[2].id).kind == "stores_vs_catalog"


# -- Happiness: Mangakol's off-by-one -----------------------------------------------------

def test_off_by_one_catalog_isbn_never_moves_the_right_one(db_session):
    series = seed_catalog_series(db_session, "Happiness", "Kayıp Kıta", volumes=(5, 6))
    # Mangakol lists Cilt 5's barcode on Cilt 6 too; our Cilt 6 is right.
    vols = catalog(db_session, series, {5: HA5, 6: HA5}, current={6: HA6})
    resolve_many(db_session, [v.id for v in vols.values()])
    db_session.commit()
    assert (vols[5].isbn, vols[6].isbn) == (HA5, HA6)
    assert db_session.get(IsbnIssue, vols[6].id).kind == "catalog_duplicate"
    assert {(c.volume_id, c.new_isbn) for c in db_session.scalars(select(IsbnChange))} == {(vols[5].id, HA5)}


# -- Monster 9: a title match that is another edition -------------------------------------

def test_foreign_isbn_found_later_removes_the_title_match(db_session):
    series = seed_catalog_series(db_session, "Monster", "Marmara Çizgi", volumes=(9,))
    vol = volumes(db_session, series)[9]
    url = "https://gerekliseyler.example/monster-tp-vol-09-perfect-ed"
    run(db_session, {"gerekliseyler": [product("gerekliseyler", "MONSTER 09", None, "1265", url=url)]})
    assert listings(db_session) == {(vol.id, url)}
    # The detail page later shows VIZ's ISBN.
    run(db_session, {"gerekliseyler": [product("gerekliseyler", "MONSTER 09", VIZ_MONSTER_9, "1265", url=url)]})
    assert listings(db_session) == set()


def test_high_title_only_price_is_refused_low_one_kept(db_session):
    series = seed_catalog_series(db_session, "Monster", "Marmara Çizgi", volumes=(9,))
    vol = volumes(db_session, series)[9]
    run(db_session, {"bkm": [product("bkm", "Monster 9", None, "385")],
                     "kitapsec": [product("kitapsec", "Monster 9", None, "380")]})
    run(db_session, {"gerekliseyler": [product("gerekliseyler", "Monster 9", None, "1265")],
                     "edessa": [product("edessa", "Monster 9", None, "99")]})
    stores = {url.split("//")[1].split(".")[0] for vid, url in listings(db_session) if vid == vol.id}
    assert stores == {"bkm", "kitapsec", "edessa"}
    refused = db_session.scalar(select(StoreObservation).where(StoreObservation.reason == "price_outlier"))
    assert refused.product_url.startswith("https://gerekliseyler")


# -- ISBN cache: a detail page read once is reused only for the same title ----------------

def test_known_isbn_is_reused_only_while_the_title_is_unchanged(db_session):
    series = seed_catalog_series(db_session, "Vinland Destanı", "Kurukafa", volumes=(5, 6))
    vols = catalog(db_session, series, {5: "9786059479745", 6: "9786059479752"})
    resolve_many(db_session, [v.id for v in vols.values()])
    db_session.commit()
    url = "https://bkm.example/derin-tarih-aralik-2024-sayi-153"
    run(db_session, {"bkm": [product("bkm", "Vinland Destanı 6", "9786059479752", url=url)]})
    service = ImportService(db_session)
    known = service._known_isbns("bkm")
    same = service._with_known_isbn(product("bkm", "Vinland Destanı 6", None, url=url), known)
    renamed = service._with_known_isbn(product("bkm", "Vinland Destanı 5", None, url=url), known)
    assert (same.isbn, renamed.isbn) == ("9786059479752", None)


def test_ideasoft_enrichment_skips_known_isbns(monkeypatch):
    from app.scrapers.gerekliseyler import GerekliseylerScraper

    from dataclasses import replace

    scraper = GerekliseylerScraper()
    scraper.settings = replace(scraper.settings, max_detail_requests=1)
    known_url, other_url = "https://gs.example/a", "https://gs.example/b"
    scraper.known_isbns = {known_url: ("Naruto 1", "9786055686000")}
    fetched = []
    monkeypatch.setattr(scraper, "_enrich_one", lambda r: (fetched.append(r.product_url), r)[1])
    out = scraper._enrich_with_details([product("gerekliseyler", "Naruto 1", None, url=known_url),
                                        product("gerekliseyler", "Naruto 2", None, url=other_url)])
    assert out[0].isbn == "9786055686000"
    assert fetched == [other_url]  # the budget of 1 went to the unknown product


# -- admin decisions -----------------------------------------------------------------------

def test_admin_isbn_is_logged_and_never_overwritten(db_session, client):
    series = seed_catalog_series(db_session, "Happiness", "Kayıp Kıta", volumes=(5,))
    vol = catalog(db_session, series, {5: HA5})[5]
    res = client.post(f"/admin/isbn/volumes/{vol.id}", json={"isbn": "978-625-93240-5-0", "reason": "Kitabın barkodu"})
    assert res.status_code == 200, res.text
    db_session.expire_all()
    vol = db_session.get(Volume, vol.id)
    assert (vol.isbn, vol.isbn_source) == (HA6, "admin")
    resolve_many(db_session, [vol.id])
    assert vol.isbn == HA6  # the catalog never overwrites an admin decision
    change = db_session.scalar(select(IsbnChange).where(IsbnChange.source == "admin"))
    assert (change.new_isbn, change.reason) == (HA6, "Kitabın barkodu")

    bad = client.post(f"/admin/isbn/volumes/{vol.id}", json={"isbn": "9786259324051", "reason": "yazım"})
    assert bad.status_code == 409
    back = client.post(f"/admin/isbn/volumes/{vol.id}", json={"reason": "kataloğa bırak", "automatic": True})
    assert back.status_code == 200 and back.json()["isbn_source"] != "admin"


def test_admin_cannot_take_an_isbn_without_choosing_move(db_session):
    a = seed_catalog_series(db_session, "Seri A", "Yayınevi", volumes=(1,))
    b = seed_catalog_series(db_session, "Seri B", "Yayınevi", volumes=(1,))
    va, vb = volumes(db_session, a)[1], volumes(db_session, b)[1]
    va.isbn = HA5
    db_session.commit()
    import pytest
    with pytest.raises(ValueError):
        set_admin_isbn(db_session, vb, HA5, user_id=1, reason="deneme")
    with pytest.raises(ValueError):
        set_admin_isbn(db_session, vb, HA5, user_id=1, reason="deneme", share=True)  # not the same book
    set_admin_isbn(db_session, vb, HA5, user_id=1, reason="deneme", move=True)
    assert (va.isbn, vb.isbn) == (None, HA5)


def test_admin_removal_still_excludes_the_product(db_session, client):
    series = seed_catalog_series(db_session, "Monster", "Marmara Çizgi", volumes=(9,))
    vol = volumes(db_session, series)[9]
    url = "https://bkm.example/monster-9"
    run(db_session, {"bkm": [product("bkm", "Monster 9", None, url=url)]})
    listing = db_session.scalar(select(StoreListing))
    assert client.delete(f"/volume/{vol.id}/listings/{listing.id}?reason=yanlış").status_code == 200
    assert db_session.scalar(select(ListingExclusion)).product_url == url
    run(db_session, {"bkm": [product("bkm", "Monster 9", None, url=url)]})
    assert listings(db_session) == set()


# -- shared ISBN, plain title: the price band picks the edition --------------------------

def test_plain_title_with_a_shared_isbn_goes_to_the_edition_its_price_fits(db_session):
    from app.services.catalog_sync import CatalogSyncService
    from tests.test_catalog_variants import SHARED, _SoloFake, _solo, _volume

    CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    limited = _volume(db_session, "Solo Leveling (Limitli Baskı)")
    variant = _volume(db_session, "Solo Leveling (Varyant Kapak)")
    # Other stores already price both editions by their own titles.
    run(db_session, {
        "bkm": [product("bkm", "Solo Leveling 5 (Limitli Baskı)", None, "1400"),
                product("bkm", "Solo Leveling 5 (Varyant Kapak)", None, "550")],
        "kitapsec": [product("kitapsec", "Solo Leveling 5 (Limitli Baskı)", None, "1390"),
                     product("kitapsec", "Solo Leveling 5 (Varyant Kapak)", None, "560")],
    })
    run(db_session, {"komikseyler": [product("komikseyler", "Solo Leveling Webtoon Cilt 5", SHARED, "553")]})
    plain = db_session.scalar(select(StoreListing).where(StoreListing.product_url.like("https://komikseyler%")))
    assert plain.volume_id == variant.id != limited.id
