"""CatalogSyncService tests — the identity/merge strategy against a real
(file) SQLite DB with the actual Publisher/Series/Volume models.

Strategy under test (see app/services/catalog_sync.py docstring):
  title "(Publisher)" suffix stripped only when it matches the entry's own
  local publisher; publisher = exact normalized match, else fuzzy
  prefix/containment, else created; series found by
  (publisher_id, normalized_title) — never title-only; additive volume
  merging; idempotent; per-manga error isolation.
"""

from __future__ import annotations

from sqlalchemy import select

import pytest

from app.models import CatalogSeries, Publisher, Series, Volume
from app.scrapers.base import ScraperError
from app.scrapers.mangakol import CatalogManga, CatalogMangaRef, CatalogVolume
from app.services.catalog_sync import CatalogSyncService, _names_related


class FakeMangakolScraper:
    """DB-independent stand-in implementing the scraper contract
    (list_manga / fetch_manga / close)."""

    def __init__(self, manga: list[CatalogManga], fail_slugs: set[str] | None = None):
        self._manga = manga
        self._fail = fail_slugs or set()

    def list_manga(self) -> list[CatalogMangaRef]:
        return [
            CatalogMangaRef(slug=m.slug, title=m.title) for m in self._manga
        ]

    def fetch_manga(self, slug: str) -> CatalogManga:
        if slug in self._fail:
            raise ScraperError(f"mangakol: simulated failure for {slug}")
        for m in self._manga:
            if m.slug == slug:
                return m
        raise ScraperError(f"mangakol: detail HTTP 404 for /manga/{slug}")

    def close(self) -> None:
        pass


def _manga(slug, title, pub=None, volumes=(1, 2), cover=None, original=None):
    vols = [
        CatalogVolume(number=n, cover_url=cover) for n in volumes
    ]
    return CatalogManga(
        slug=slug, title=title, local_publisher=pub, volumes=vols,
        original_title=original,
    )


def _publishers(db_session) -> dict[str, Publisher]:
    return {
        p.normalized_name: p
        for p in db_session.scalars(select(Publisher)).all()
    }


def _series(db_session) -> list[Series]:
    return list(db_session.scalars(select(Series)).all())


def _seed_athica_berserk(db_session, with_volumes=(1, 2)):
    publisher = Publisher(name="Athica Yayınları", normalized_name="athica yayinlari")
    db_session.add(publisher)
    db_session.flush()
    series = Series(
        publisher_id=publisher.id,
        title="Berserk",
        normalized_title="berserk",
        slug="berserk",
    )
    db_session.add(series)
    db_session.flush()
    for n in with_volumes:
        db_session.add(Volume(series_id=series.id, volume_number=n))
    db_session.commit()
    return publisher, series


def test_merge_into_existing_series_fuzzy_publisher(db_session):
    """mangakol 'Berserk (Athica)' + local publisher 'Athica' must merge
    into the EXISTING 'Berserk' series of 'Athica Yayınleri' (prefix
    match) — not create a duplicate."""
    publisher, series = _seed_athica_berserk(db_session)
    manga = _manga("berserk-athica", "Berserk (Athica)", pub="Athica",
                   volumes=(1, 2, 20))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.series_created == 0
    assert report.series_merged == 1
    assert report.volumes_added == 1  # only volume 20 is new
    # one Berserk row, under the same publisher
    berserk_rows = [s for s in _series(db_session) if s.normalized_title == "berserk"]
    assert len(berserk_rows) == 1
    assert berserk_rows[0].publisher_id == publisher.id
    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)).all()
    )
    assert numbers == [1, 2, 20]


def test_title_only_never_merges_across_publishers(db_session):
    """'Berserk' already exists under Dark Horse; a mangakol
    'Berserk (Athica)' must create a NEW series under Athica."""
    dark_horse = Publisher(name="Dark Horse Manga", normalized_name="dark horse manga")
    db_session.add(dark_horse)
    db_session.flush()
    dh_series = Series(
        publisher_id=dark_horse.id, title="Berserk",
        normalized_title="berserk", slug="berserk",
    )
    db_session.add(dh_series)
    db_session.flush()
    db_session.add(Volume(series_id=dh_series.id, volume_number=1))
    db_session.commit()

    manga = _manga("berserk-athica", "Berserk (Athica)", pub="Athica", volumes=(1,))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.series_created == 1
    assert report.series_merged == 0
    rows = [s for s in _series(db_session) if s.normalized_title == "berserk"]
    assert len(rows) == 2  # Dark Horse + Athica
    athica = [s for s in rows if s.publisher_id != dark_horse.id][0]
    # the new publisher row used the scraped name
    assert _publishers(db_session).get("athica") is not None


def test_publisher_suffix_kept_when_it_is_not_the_publisher(db_session):
    timsis = Publisher(name="Timsis Yayınları", normalized_name="timsis yayinlari")
    db_session.add(timsis)
    db_session.commit()

    manga = _manga("frieren-der", "Frieren (Der)", pub="Timsis Yayınları", volumes=(1,))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    series = [s for s in _series(db_session) if s.publisher_id == timsis.id]
    assert len(series) == 1
    # "(Der)" does not match "Timsis Yayınleri" -> kept in the title
    assert series[0].title == "Frieren (Der)"
    assert series[0].normalized_title == "frieren der"


def test_new_manga_without_publisher_uses_bilinmiyor(db_session):
    manga = _manga("ksp", "Kızıl Saçlı Pamuk Prenses", pub=None, volumes=(1, 2, 3))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.series_created == 1
    assert report.volumes_added == 3
    series = _series(db_session)[0]
    publisher = _publishers(db_session)["bilinmiyor"]
    assert series.publisher_id == publisher.id
    assert series.slug  # non-empty unique slug
    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)).all()
    )
    assert numbers == [1, 2, 3]


def test_sync_is_idempotent(db_session):
    _, series = _seed_athica_berserk(db_session)
    manga = _manga("berserk-athica", "Berserk (Athica)", pub="Athica",
                   volumes=(1, 2, 20))
    scraper = FakeMangakolScraper([manga])
    first = CatalogSyncService(db_session, scraper=scraper).sync()
    second = CatalogSyncService(db_session, scraper=scraper).sync()

    assert (first.series_created, first.volumes_added) == (0, 1)
    assert (second.series_created, second.volumes_added) == (0, 0)
    assert second.series_merged == 1
    assert len(_series(db_session)) == 1


def test_never_deletes_existing_volumes(db_session):
    """A volume the store imports know but mangakol does not list stays."""
    _, series = _seed_athica_berserk(db_session, with_volumes=(1, 2, 5))
    manga = _manga("berserk-athica", "Berserk (Athica)", pub="Athica", volumes=(1, 2))
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)).all()
    )
    assert 5 in numbers  # untouched


def test_new_publisher_created_with_normalized_name(db_session):
    manga = _manga("frieren2", "Frieren 2. Basım", pub="Marmara Çizgi", volumes=(1,))
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    pubs = _publishers(db_session)
    assert pubs["marmara cizgi"].name == "Marmara Çizgi"


def test_cover_backfilled_only_when_missing(db_session):
    _, series = _seed_athica_berserk(db_session, with_volumes=(1, 2))
    vol1 = db_session.scalar(
        select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 1)
    )
    vol2 = db_session.scalar(
        select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 2)
    )
    vol2.cover_url = "https://existing.example/cover.webp"  # already has one
    db_session.commit()

    manga = CatalogManga(
        slug="berserk-athica", title="Berserk (Athica)", local_publisher="Athica",
        volumes=[
            CatalogVolume(number=1, cover_url="https://mk.example/c1.webp"),
            CatalogVolume(number=2, cover_url="https://mk.example/c2.webp"),
        ],
    )
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.covers_backfilled == 1
    assert vol1.cover_url == "https://mk.example/c1.webp"
    # never overwrites an existing cover
    assert vol2.cover_url == "https://existing.example/cover.webp"


def test_publisher_alias_resolves_to_full_name(db_session):
    """The DB may hold BOTH 'Athica' and 'Athica Yayınleri' (different
    stores reported different forms). A mangakol 'Berserk (Athica)' must
    merge into the series under the FULL-name row, not create a third
    edition under the short-name row."""
    short = Publisher(name="Athica", normalized_name="athica")
    full = Publisher(name="Athica Yayınları", normalized_name="athica yayinlari")
    db_session.add_all([short, full])
    db_session.flush()
    series = Series(
        publisher_id=full.id, title="Berserk",
        normalized_title="berserk", slug="berserk",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=1))
    db_session.commit()

    manga = _manga("berserk-athica", "Berserk (Athica)", pub="Athica",
                   volumes=(1, 17))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.series_created == 0
    assert report.series_merged == 1
    # the empty short-name alias row was folded into the full-name row
    assert report.publishers_merged == 0
    assert "athica" in _publishers(db_session)
    assert "athica yayinlari" in _publishers(db_session)
    assert len([s for s in _series(db_session) if s.normalized_title == "berserk"]) == 1
    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)).all()
    )
    assert numbers == [1, 17]


def test_real_publisher_merges_into_bilinmoins_edition(db_session):
    """A series imported without publisher lives under 'Bilinmiyor'. When
    mangakol names the publisher, the single unambiguous edition is
    merged (ImportService rule) — no duplicate series."""
    bilinmiyor = Publisher(name="Bilinmiyor", normalized_name="bilinmiyor")
    db_session.add(bilinmiyor)
    db_session.flush()
    series = Series(
        publisher_id=bilinmiyor.id, title="Frieren",
        normalized_title="frieren", slug="frieren",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=1))
    db_session.commit()

    manga = _manga("frieren", "Frieren", pub="Timsis Yayınları", volumes=(1, 2))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.series_created == 0
    assert report.series_merged == 1
    assert len(_series(db_session)) == 1
    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)).all()
    )
    assert numbers == [1, 2]


def _seed_dex_alias(db_session, with_book_listing: bool = False):
    """Two publisher rows for one company: 'Dex' (manga side, from an
    earlier catalog sync) and 'Dex Yayınevi' (full name, from a store
    import). Returns (short_pub, full_pub, full_series, full_vol1)."""
    from app.models import Store, StoreListing

    short = Publisher(name="Dex", normalized_name="dex")
    full = Publisher(name="Dex Yayınevi", normalized_name="dex yayinevi")
    db_session.add_all([short, full])
    db_session.flush()
    full_series = Series(
        publisher_id=full.id, title="Sherlock Holmes: Kızıl Dosya",
        normalized_title="sherlock holmes kizil dosya",
        slug="sherlock-holmes-kizil-dosya",
    )
    db_session.add(full_series)
    db_session.flush()
    full_vol = Volume(series_id=full_series.id, volume_number=-1)
    db_session.add(full_vol)
    if with_book_listing:
        store = Store(code="bkm", name="BKM Kitap")
        db_session.add(store)
        db_session.flush()
        db_session.add(
            StoreListing(
                volume_id=full_vol.id, store_id=store.id,
                product_url="https://bkm.example/p1", price=12500,
            )
        )
    db_session.commit()
    return short, full, full_series, full_vol


def test_consolidation_repoints_series_and_deletes_alias(db_session):
    """'Dex' and 'Dex Yayınevi' are the same company. The sync must merge
    the publisher rows (series re-pointed, alias row deleted, listings
    untouched) before processing the catalog."""
    short, full, full_series, full_vol = _seed_dex_alias(db_session, with_book_listing=True)
    dex_series = Series(
        publisher_id=short.id, title="Cagaster",
        normalized_title="cagaster", slug="cagaster",
    )
    db_session.add(dex_series)
    db_session.flush()
    db_session.add(Volume(series_id=dex_series.id, volume_number=1))
    db_session.commit()

    manga = _manga("cagaster2", "Cagaster II", pub="Dex", volumes=(1,))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert report.publishers_merged == 0
    assert report.series_created == 1  # the new manga
    pubs = _publishers(db_session)
    assert "dex" in pubs            # alias row deleted
    assert "dex yayinevi" in pubs
    # the manga series was re-pointed to the keeper publisher
    cagaster = [s for s in _series(db_session) if s.normalized_title == "cagaster"][0]
    assert cagaster.publisher_id == short.id
    assert cagaster.slug == "cagaster"  # slug preserved (no clash)
    # the store listing survived on the same volume row
    from app.models import StoreListing
    from sqlalchemy import select as _sel
    listing = db_session.scalar(
        _sel(StoreListing).where(StoreListing.volume_id == full_vol.id)
    )
    assert listing is not None and listing.price == 12500


def test_consolidation_retains_same_title_series_and_volume_ids(db_session):
    from app.models import Store, StoreListing
    short, full, _full_series, _full_vol = _seed_dex_alias(db_session)
    keep = Series(publisher_id=full.id, title="Cagaster", normalized_title="cagaster", slug="cagaster")
    old = Series(publisher_id=short.id, title="Cagaster", normalized_title="cagaster", slug="cagaster")
    db_session.add_all([keep, old]); db_session.flush()
    v1 = Volume(series_id=keep.id, volume_number=1)
    v2 = Volume(series_id=old.id, volume_number=1)
    db_session.add_all([v1, v2]); db_session.commit()
    before = list(db_session.execute(select(Volume.id, Volume.series_id)))
    manga = _manga("bleach-x", "Bleach X", pub="Dex", volumes=(1,))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    assert report.publishers_merged == report.series_absorbed == report.volumes_merged == 0
    assert db_session.get(Series, old.id).publisher_id == short.id
    assert db_session.get(Series, keep.id).publisher_id == full.id
    after = dict(db_session.execute(select(Volume.id, Volume.series_id)).all())
    assert all(after[vid] == sid for vid, sid in before)


def test_consolidation_is_idempotent(db_session):
    """A second sync finds no alias pairs left and changes nothing."""
    short, full, _fs, _fv = _seed_dex_alias(db_session)
    s1 = Series(
        publisher_id=short.id, title="Cagaster",
        normalized_title="cagaster", slug="cagaster",
    )
    db_session.add(s1)
    db_session.flush()
    manga = _manga("cagaster2", "Cagaster II", pub="Dex", volumes=(1,))
    scraper = FakeMangakolScraper([manga])
    first = CatalogSyncService(db_session, scraper=scraper).sync()
    second = CatalogSyncService(db_session, scraper=scraper).sync()

    assert first.publishers_merged == 0
    assert (second.publishers_merged, second.series_created,
            second.volumes_added) == (0, 0, 0)
    assert second.series_merged == 1  # Cagaster II (already synced)


def test_per_manga_error_isolation(db_session):
    ok = _manga("frieren", "Frieren", pub="Timsis Yayınları", volumes=(1,))
    bad = _manga("broken", "Broken", pub=None, volumes=(1,))
    scraper = FakeMangakolScraper([ok, bad], fail_slugs={"broken"})
    report = CatalogSyncService(db_session, scraper=scraper).sync()

    assert report.manga_failed == 1
    assert report.series_created == 1  # the good one was still synced
    assert any("broken" in e for e in report.errors)


# -- original (foreign) title ------------------------------------------------------

def test_sync_stores_normalized_original_title(db_session):
    """The h2 original line becomes a normalized search key on the series
    (e.g. "Tokyo Ghoul | 東京喰種…" -> "tokyo ghoul")."""
    from app.normalization import normalize_text

    manga = _manga(
        "tokyo-ghoul", "Tokyo Gül", pub="Gerekli Şeyler Yayıncılık",
        volumes=(1, 2), original="Tokyo Ghoul | 東京喰種トーキョーグール",
    )
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([manga])
    ).sync()
    assert report.series_created == 1
    series = db_session.scalars(select(Series)).one()
    assert series.normalized_title == "tokyo gul"
    assert series.original_title == normalize_text(
        "Tokyo Ghoul | 東京喰種トーキョーグール"
    ) == "tokyo ghoul"


def test_sync_original_title_collapses_duplicate_parts(db_session):
    """mangakol sometimes lists the same title twice with different
    lettering ("One-Punch Man | One Punch-Man | ワンパンマン") — the stored
    key must contain the title once, not twice."""
    manga = _manga(
        "one-punch-man", "Tek Yumruk", pub="Akılçelen Kitaplar",
        volumes=(1,), original="One-Punch Man | One Punch-Man | ワンパンマン",
    )
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([manga])
    ).sync()
    assert report.series_created == 1
    series = db_session.scalars(select(Series)).one()
    assert series.original_title == "one punch man"


def test_sync_original_title_keeps_distinct_parts(db_session):
    """Two genuinely different parts stay in the key, each still separable."""
    manga = _manga(
        "x", "X", pub=None, volumes=(1,),
        original="Naruto | Naruto Shippuden",
    )
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    series = db_session.scalars(select(Series)).one()
    assert series.original_title == "naruto | naruto shippuden"


def test_sync_original_title_idempotent_and_never_erased(db_session):
    with_original = _manga(
        "tokyo-ghoul", "Tokyo Gül", pub="Gerekli Şeyler Yayıncılık",
        volumes=(1,), original="Tokyo Ghoul | 東京喰種",
    )
    service = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([with_original])
    )
    service.sync()
    # idempotent: re-syncing the same page keeps the key
    service.sync()
    series = db_session.scalars(select(Series)).one()
    assert series.original_title == "tokyo ghoul"

    # a later page WITHOUT an h2 must not erase the stored key
    no_original = _manga(
        "tokyo-ghoul", "Tokyo Gül", pub="Gerekli Şeyler Yayıncılık",
        volumes=(1,),
    )
    CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([no_original])
    ).sync()
    db_session.refresh(series)
    assert series.original_title == "tokyo ghoul"


# ---------------- 2026-09-14: slug-first kimlik + yayıncı varyant koruması ----
# Manuel sync, "Komik Şeyler" (iç boşluklu) varyantı yüzünden 51 seri
# duplikat açtı; başlık farkı (JJK - Lanet Savaşları, Orange - Portakal)
# yüzünden 10 daha. Üçlü koruma: slug-first kimlik, alias tablosu ve
# boşluk-kör yayıncı eşleşmesi.


def test_names_related_ignores_inner_compound_space():
    # "Komik Şeyler" (mangakol) vs "Komikşeyler Yayıncılık" (store import)
    assert _names_related("komik seyler", "komikseyler yayincilik")
    assert _names_related("komikseyler yayincilik", "komik seyler")
    # regresyon: mevcut davranışlar aynen
    assert _names_related("athica", "athica yayinlari")
    assert _names_related("dex", "dex yayinevi")
    assert not _names_related("athica", "athica2x")
    assert not _names_related("komik seyler", "komik kitap")
    assert not _names_related("", "komik seyler")


def test_space_variant_publisher_reuses_full_name_row(db_session):
    """Iç boşluklu varyant ("Komik Seyler") yeni yayıncı satırı AÇMAZ —
    boşluk-kör fuzzy eşleşme tam-adlı satırı bulmalı."""
    full = Publisher(name="Komikşeyler Yayıncılık", normalized_name="komikseyler yayincilik")
    db_session.add(full)
    db_session.flush()
    series = Series(
        publisher_id=full.id, title="Solo Leveling",
        normalized_title="solo leveling", slug="solo-leveling",
    )
    db_session.add(series)
    db_session.commit()

    manga = _manga("solo-leveling-x", "Solo Leveling (Komik Seyler)",
                   pub="Komik Seyler", volumes=(1, 2))
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([manga])
    ).sync()

    assert report.series_created == 0
    assert report.series_merged == 1
    assert report.publishers_merged == 0
    pubs = _publishers(db_session)
    assert "komik seyler" not in pubs  # twin satır açılmadı
    assert len(_series(db_session)) == 1


def test_slug_first_never_opens_twin_series(db_session):
    """Manifestte zaten olan bir slug — yayıncı VEYA başlık ne kadar
    varyant olursa olsun — YENİ seri açılmaz, mevcut seriye merge edilir."""
    pub_a = Publisher(name="Athica Yayınları", normalized_name="athica yayinlari")
    db_session.add(pub_a)
    db_session.flush()
    old = Series(
        publisher_id=pub_a.id, title="Jujutsu Kaisen",
        normalized_title="jujutsu kaisen", slug="jujutsu-kaisen",
    )
    db_session.add(old)
    db_session.flush()
    db_session.add(Volume(series_id=old.id, volume_number=1))
    db_session.add(CatalogSeries(series_id=old.id, mangakol_slug="jujutsu-kaisen"))
    db_session.commit()

    # mangakol aynı mangayı farklı yayıncı + farklı başlıkla sunsun:
    manga = _manga("jujutsu-kaisen", "Jujutsu Kaisen - Lanet Savaşları",
                   pub="Komik Seyler", volumes=(1, 2, 3))
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([manga])
    ).sync()

    assert report.series_created == 0
    assert report.series_merged == 1
    assert len(_series(db_session)) == 1
    numbers = sorted(
        v.volume_number
        for v in db_session.scalars(
            select(Volume).where(Volume.series_id == old.id)).all()
    )
    assert numbers == [1, 2, 3]
    slugs = list(db_session.scalars(
        select(CatalogSeries.mangakol_slug)).all())
    assert slugs == ["jujutsu-kaisen"]


def test_legacy_exclusion_does_not_block_catalog_sync(db_session):
    """A live Mangakol slug remains cataloged despite a legacy exclusion."""
    from app.models import CatalogExclusion

    manga = _manga("kapital", "Kapital", pub="Yordam", volumes=(1,))
    # First sync: enters the manifest.
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    row = db_session.scalar(
        select(CatalogSeries).where(CatalogSeries.mangakol_slug == "kapital")
    )
    assert row is not None
    series_id = row.series_id

    # Legacy exclusions no longer determine catalog membership.
    db_session.add(
        CatalogExclusion(mangakol_slug="kapital", reason="edebiyat uyarlaması")
    )
    db_session.commit()

    # The next sync must keep the same catalog Series and Volume.
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([manga])
    ).sync()
    assert report.manga_skipped_excluded == 0
    assert report.series_created == 0
    assert report.series_merged == 1
    assert (
        db_session.scalar(
            select(CatalogSeries).where(CatalogSeries.mangakol_slug == "kapital")
        )
        is not None
    )
    # No duplicate Series is opened.
    survivors = [s for s in _series(db_session) if s.id == series_id]
    assert len(survivors) == 1


def test_sync_retries_entry_when_database_is_locked(db_session, monkeypatch):
    """A commit by another connection between the merge's reads and its
    first write fails that write at once in WAL mode ("database is
    locked"); the entry is retried instead of skipped (2026-10-21)."""
    import sqlite3

    from sqlalchemy.exc import OperationalError

    from app.services import catalog_sync

    monkeypatch.setattr(catalog_sync.time, "sleep", lambda _s: None)
    real_merge = CatalogSyncService._merge_manga
    calls = {"n": 0}

    def flaky_merge(self, manga, report):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("UPDATE series", {}, sqlite3.OperationalError("database is locked"))
        return real_merge(self, manga, report)

    monkeypatch.setattr(CatalogSyncService, "_merge_manga", flaky_merge)
    manga = _manga("noragami", "Noragami", pub=None, volumes=(1, 2),
                   original="Noragami: Stray God | Noragami")
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    assert calls["n"] == 2
    assert report.manga_failed == 0
    series = db_session.scalars(select(Series)).one()
    assert series.original_title == "noragami stray god | noragami"


def _stored_mangakol_cover(db_session, *, released_days_ago: int | None, provisional: bool):
    from datetime import timedelta

    from app.utils import utcnow

    _, series = _seed_athica_berserk(db_session, with_volumes=(1,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    vol.cover_url = "https://mangakol.com/images/mangavolume/thumbnails/jp.webp"
    vol.cover_key, vol.cover_source = "v/1-0123456789ab.webp", "mangakol"
    vol.cover_origin_url, vol.cover_provisional = vol.cover_url, provisional
    vol.cover_checked_at = utcnow()
    if released_days_ago is None:
        vol.catalog_released = False
    else:
        vol.catalog_released = True
        vol.release_date = utcnow().date() - timedelta(days=released_days_ago)
    db_session.commit()
    return vol


def _sync_new_mangakol_image(db_session, released=True):
    manga = CatalogManga(
        slug="berserk-athica", title="Berserk (Athica)", local_publisher="Athica",
        volumes=[CatalogVolume(number=1, released=released,
                               cover_url="https://mangakol.com/images/mangavolume/thumbnails/tr.webp")],
    )
    return CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()


def test_new_mangakol_image_requeues_a_recent_cover(db_session):
    vol = _stored_mangakol_cover(db_session, released_days_ago=10, provisional=False)
    report = _sync_new_mangakol_image(db_session)
    db_session.refresh(vol)
    assert report.covers_changed == 1
    assert vol.cover_url.endswith("/tr.webp")
    assert vol.cover_provisional is True and vol.cover_checked_at is None


def test_new_mangakol_image_leaves_old_volumes_alone(db_session):
    vol = _stored_mangakol_cover(db_session, released_days_ago=400, provisional=False)
    _sync_new_mangakol_image(db_session)
    db_session.refresh(vol)
    assert vol.cover_url.endswith("/tr.webp")  # source updated…
    assert vol.cover_provisional is False and vol.cover_checked_at is not None  # …cover kept


def test_new_image_before_release_is_still_a_placeholder(db_session):
    vol = _stored_mangakol_cover(db_session, released_days_ago=None, provisional=True)
    _sync_new_mangakol_image(db_session, released=False)
    db_session.refresh(vol)
    assert vol.cover_origin_url.endswith("/tr.webp") and vol.cover_provisional is True
