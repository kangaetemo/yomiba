"""Self-hosted covers: image checks, storage, source order (Mangakol off by
default), the /covers route and the URLs the API hands out."""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.models import Store, StoreListing, Volume
from app.services import covers
from app.services.covers import CoverFetcher, CoverWorker, LocalCoverStore, to_cover_webp
from app.utils import utcnow
from tests.test_import_service import seed_catalog_series

MANGAKOL = "https://mangakol.com/images/mangavolume/thumbnails/x.webp"
MANGAKOL_FULL = "https://mangakol.com/images/mangavolume/x.webp"
BKM_IMG = "https://cdn.bkmkitap.com/berserk-1.jpg"
KS_IMG = "https://cdn.kitapsepeti.com/berserk-1.jpg"


def _image(w=300, h=450, mode="RGB", fmt="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new(mode, (w, h), (200, 60, 40) if mode == "RGB" else (200, 60, 40, 128)).save(out, format=fmt)
    return out.getvalue()


# -- image checks -------------------------------------------------------------------------------

def test_cover_is_resized_to_webp():
    webp = to_cover_webp(_image(900, 1350))
    with Image.open(io.BytesIO(webp)) as img:
        assert img.format == "WEBP" and img.size == (480, 720)


def test_small_cover_is_kept_as_is():
    with Image.open(io.BytesIO(to_cover_webp(_image(300, 450)))) as img:
        assert img.size == (300, 450)


def test_transparent_png_gets_a_paper_background():
    assert to_cover_webp(_image(300, 450, mode="RGBA", fmt="PNG")) is not None


@pytest.mark.parametrize("data", [
    _image(1200, 400),        # banner, not a cover
    _image(400, 420),         # near-square logo
    _image(60, 90),           # thumbnail
    b"<html>not an image</html>",
])
def test_non_covers_are_rejected(data):
    assert to_cover_webp(data) is None


def test_store_keys_cannot_escape(tmp_path):
    store = LocalCoverStore(tmp_path, "/api/covers")
    for key in ("../x.webp", "v/1-../../etc.webp", "v/abc.webp", "/etc/passwd"):
        with pytest.raises(ValueError):
            store.save(key, b"x", "image/webp")


# -- fetching -----------------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path, monkeypatch):
    s = LocalCoverStore(tmp_path / "covers", "/api/covers")
    monkeypatch.setattr(covers, "get_cover_store", lambda settings=None: s)
    from app.routes import covers as covers_route
    monkeypatch.setattr(covers_route, "get_cover_store", lambda settings=None: s)
    return s


def _volume_with_offers(db_session, images: dict[str, str], catalog_cover: str | None = MANGAKOL):
    series = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    vol.cover_url = catalog_cover
    for code, url in images.items():
        st = Store(code=code, name=code.upper())
        db_session.add(st)
        db_session.flush()
        db_session.add(StoreListing(volume_id=vol.id, store_id=st.id, price=10000,
                                    product_url=f"https://{code}.example/b1", image_url=url))
    db_session.commit()
    return vol


class _Downloads:
    def __init__(self, pages):
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, url):
        self.asked.append(url)
        return self.pages.get(url)


def _fetcher(db_session, store, pages, **settings):
    download = _Downloads(pages)
    return CoverFetcher(db_session, store=store, download=download,
                        settings=replace(get_settings(), **settings)), download


def test_store_image_wins_and_is_served(client, db_session, store):
    vol = _volume_with_offers(db_session, {"kitapsepeti": KS_IMG, "bkm": BKM_IMG}, catalog_cover=None)
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: _image(), KS_IMG: _image()})

    report = fetcher.run(budget=10)

    assert download.asked == [BKM_IMG]  # store priority: BKM first; one hit is enough
    assert (report.stored, report.remaining) == (1, 0)
    assert vol.cover_source == "store:bkm" and vol.cover_key.startswith(f"v/{vol.id}-")

    body = client.get(f"/volume/{vol.id}").json()
    assert body["cover_url"] == f"/api/covers/{vol.cover_key}"
    served = client.get(f"/covers/{vol.cover_key}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    assert "immutable" in served.headers["cache-control"]


def test_mangakol_can_be_switched_off(db_session, store):
    vol = _volume_with_offers(db_session, {}, catalog_cover=MANGAKOL)
    fetcher, download = _fetcher(db_session, store, {MANGAKOL: _image()}, cover_allow_mangakol=False)

    report = fetcher.run(budget=10)

    assert download.asked == [] and report.without_source == 1
    assert vol.cover_key is None and vol.cover_checked_at is not None


def test_mangakol_full_size_first_by_default(db_session, store):
    """Default (owner's choice): Mangakol first, its full-size image before
    the thumbnail; store images only when Mangakol has none."""
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=MANGAKOL)
    fetcher, download = _fetcher(db_session, store, {MANGAKOL_FULL: _image(900, 1300), BKM_IMG: _image()})

    fetcher.run(budget=10)

    assert download.asked == [MANGAKOL_FULL]
    assert vol.cover_source == "mangakol"


def test_store_image_fills_in_when_mangakol_fails(db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=MANGAKOL)
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: _image()})  # Mangakol 404s

    fetcher.run(budget=10)

    assert download.asked == [MANGAKOL_FULL, MANGAKOL, BKM_IMG]
    assert vol.cover_source == "store:bkm"


def test_mangakol_last_when_not_preferred(db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=MANGAKOL)
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: b"broken", MANGAKOL: _image()},
                                 cover_prefer_mangakol=False)

    fetcher.run(budget=10)

    assert download.asked == [BKM_IMG, MANGAKOL_FULL, MANGAKOL]
    assert vol.cover_source == "mangakol"


def test_failed_volume_is_retried_after_a_week(db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=None)
    fetcher, download = _fetcher(db_session, store, {})
    fetcher.run(budget=10)
    fetcher.run(budget=10)
    assert download.asked == [BKM_IMG]  # not hammered again right away

    vol.cover_checked_at = utcnow() - timedelta(days=8)
    db_session.commit()
    fetcher.run(budget=10)
    assert download.asked == [BKM_IMG, BKM_IMG]


def test_budget_caps_downloads(db_session, store):
    series = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2, 3))
    st = Store(code="bkm", name="BKM")
    db_session.add(st)
    db_session.flush()
    pages = {}
    for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)):
        url = f"https://cdn.bkmkitap.com/{v.volume_number}.jpg"
        pages[url] = _image()
        db_session.add(StoreListing(volume_id=v.id, store_id=st.id, price=1, image_url=url,
                                    product_url=f"https://bkm.example/{v.id}"))
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, pages)

    report = fetcher.run(budget=2)
    assert (report.stored, report.remaining) == (2, 1)
    assert fetcher.run(budget=2).remaining == 0


def test_cover_route_rejects_bad_keys(client, store):
    assert client.get("/covers/..%2F..%2Fyomiba.db").status_code == 404
    assert client.get("/covers/v/1-0123456789ab.webp").status_code == 404  # well-formed, missing


def test_worker_run_once_records_last_pass(db_session, engine, store):
    from sqlalchemy.orm import sessionmaker

    _volume_with_offers(db_session, {"bkm": BKM_IMG})
    worker = CoverWorker(
        sessionmaker(bind=engine, expire_on_commit=False),
        fetcher_factory=lambda s: CoverFetcher(s, store=store, download=_Downloads({BKM_IMG: _image()})),
    )
    report = worker.run_once()
    assert report.stored == 1 and worker.last["stored"] == 1 and worker.running is False


def test_admin_cover_status_and_trigger(client, db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG})
    vol.cover_key = "v/1-0123456789ab.webp"
    db_session.commit()
    body = client.get("/catalog/covers").json()
    assert (body["total"], body["stored"], body["enabled"]) == (1, 1, False)
    assert client.post("/catalog/covers/fetch").status_code == 503  # no worker in tests

    class _Worker:
        running, last = False, None
        def trigger(self):
            return True
    client.app.state.cover_worker = _Worker()
    assert client.post("/catalog/covers/fetch").status_code == 202


def test_larger_store_rendition_is_tried_first(db_session, store):
    small = "https://cdn.bkmkitap.com/berserk-10-13888136-92-K.jpg"
    large = "https://cdn.bkmkitap.com/berserk-10-13888136-92-B.jpg"
    assert covers.larger_variants(small) == [large, small]
    assert covers.larger_variants(BKM_IMG) == [BKM_IMG]

    vol = _volume_with_offers(db_session, {"bkm": small}, catalog_cover=None)
    fetcher, download = _fetcher(db_session, store, {small: _image()})  # "-B" missing: falls back
    fetcher.run(budget=10)
    assert download.asked == [large, small] and vol.cover_key is not None


# -- provisional (pre-release, usually Japanese) covers ---------------------------------------------

MANGAKOL_TR = "https://mangakol.com/images/mangavolume/thumbnails/x-tr.webp"
MANGAKOL_TR_FULL = "https://mangakol.com/images/mangavolume/x-tr.webp"


def _image_b(w=300, h=450) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (20, 90, 200)).save(out, format="JPEG")
    return out.getvalue()


def _announced(db_session, store, images=None):
    """A "Yakında" volume whose Mangakol (Japanese) cover got stored."""
    vol = _volume_with_offers(db_session, images or {}, catalog_cover=MANGAKOL)
    vol.catalog_released = False
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {MANGAKOL_FULL: _image()})
    fetcher.run(budget=10)
    assert vol.cover_source == "mangakol" and vol.cover_provisional is True
    assert vol.cover_origin_url == MANGAKOL
    return vol


def _release(db_session, vol):
    vol.catalog_released = True
    vol.release_date = utcnow().date() - timedelta(days=2)
    db_session.commit()


def test_cover_of_a_released_volume_is_final(db_session, store):
    vol = _volume_with_offers(db_session, {}, catalog_cover=MANGAKOL)
    fetcher, _ = _fetcher(db_session, store, {MANGAKOL_FULL: _image()})
    fetcher.run(budget=10)
    assert vol.cover_key is not None and vol.cover_provisional is False


def test_provisional_cover_waits_while_the_volume_is_not_out(db_session, store):
    vol = _announced(db_session, store, {"bkm": BKM_IMG})
    vol.cover_checked_at = utcnow() - timedelta(days=30)
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: _image_b()})
    assert fetcher.run(budget=10).volumes == 0 and download.asked == []


def test_store_photo_replaces_the_japanese_cover_after_release(db_session, store):
    vol = _announced(db_session, store, {"bkm": BKM_IMG})
    old_key = vol.cover_key
    _release(db_session, vol)
    vol.cover_checked_at = utcnow() - timedelta(days=2)
    db_session.commit()
    # Mangakol still serves the same Japanese image: it is not asked again.
    fetcher, download = _fetcher(db_session, store, {MANGAKOL_FULL: _image(), BKM_IMG: _image_b()})

    report = fetcher.run(budget=10)

    assert download.asked == [BKM_IMG]
    assert report.replaced == 1 and vol.cover_key != old_key
    assert (vol.cover_source, vol.cover_provisional, vol.cover_origin_url) == ("store:bkm", False, BKM_IMG)


def test_provisional_cover_is_retried_daily_until_a_new_image_appears(db_session, store):
    vol = _announced(db_session, store)
    old_key = vol.cover_key
    _release(db_session, vol)
    vol.cover_checked_at = None
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {})
    report = fetcher.run(budget=10)
    assert report.without_source == 1 and vol.cover_key == old_key and vol.cover_provisional

    assert fetcher.run(budget=10).volumes == 0  # checked today already
    vol.cover_checked_at = utcnow() - timedelta(days=1, minutes=1)
    vol.cover_url = MANGAKOL_TR  # the catalog sync saw Mangakol's new image
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {MANGAKOL_TR_FULL: _image_b()})
    assert fetcher.run(budget=10).replaced == 1
    assert download.asked == [MANGAKOL_TR_FULL]
    assert (vol.cover_origin_url, vol.cover_provisional) == (MANGAKOL_TR, False)


def test_same_picture_at_a_new_address_is_not_a_replacement(db_session, store):
    vol = _announced(db_session, store, {"bkm": BKM_IMG})
    old_key = vol.cover_key
    _release(db_session, vol)
    vol.cover_checked_at = None
    db_session.commit()
    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image()})  # BKM re-hosts the JP file
    report = fetcher.run(budget=10)
    assert report.replaced == 0 and vol.cover_key == old_key and vol.cover_provisional


def test_provisional_retries_stop_long_after_release(db_session, store):
    vol = _announced(db_session, store, {"bkm": BKM_IMG})
    vol.catalog_released = True
    vol.release_date = utcnow().date() - covers.PROVISIONAL_GIVE_UP - timedelta(days=1)
    vol.cover_checked_at = None
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: _image_b()})
    assert fetcher.run(budget=10).volumes == 0 and download.asked == []


def test_mangakol_image_right_after_release_is_provisional(db_session, store):
    vol = _volume_with_offers(db_session, {}, catalog_cover=MANGAKOL)
    vol.catalog_released, vol.release_date = True, utcnow().date() - timedelta(days=3)
    db_session.commit()
    fetcher, _ = _fetcher(db_session, store, {MANGAKOL_FULL: _image()})
    fetcher.run(budget=10)
    assert vol.cover_source == "mangakol" and vol.cover_provisional is True


def test_mark_provisional_covers_script(db_session, engine, store, monkeypatch, capsys):
    import sys

    from sqlalchemy.orm import sessionmaker

    import mark_provisional_covers as script

    series = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2, 3))
    vols = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id))}
    stored = utcnow() - timedelta(days=60)
    for n, v in vols.items():
        v.cover_url, v.cover_key, v.cover_source, v.cover_checked_at = MANGAKOL, f"v/{v.id}-0123456789ab.webp", "mangakol", stored
        v.catalog_released = True
    vols[1].release_date = stored.date() - timedelta(days=300)  # old: final
    vols[2].release_date = stored.date() + timedelta(days=5)    # stored before release: replace now
    vols[3].catalog_released = False                             # still "Yakında"
    db_session.commit()

    monkeypatch.setattr(script, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(sys, "argv", ["x"])
    script.main()
    db_session.expire_all()
    assert all(v.cover_provisional is None for v in vols.values())  # dry run

    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    script.main()
    db_session.expire_all()
    assert [vols[n].cover_provisional for n in (1, 2, 3)] == [False, True, True]
    assert vols[2].cover_checked_at is None and vols[3].cover_checked_at is not None
    assert vols[2].cover_origin_url == MANGAKOL
    assert "geçici, yenilenecek: 1" in capsys.readouterr().out


# -- wrong store covers ---------------------------------------------------------------------------

def test_store_images_are_not_used_before_release(db_session, store):
    vol = _volume_with_offers(db_session, {"kitapbulan": BKM_IMG}, catalog_cover="https://cdn.example/en.jpg")
    vol.catalog_released = False
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {BKM_IMG: _image(), "https://cdn.example/en.jpg": _image()})
    report = fetcher.run(budget=10)
    assert download.asked == [] and report.without_source == 1 and vol.cover_key is None


def test_cover_of_a_deleted_listing_is_dropped_and_refetched(db_session, store):
    vol = _volume_with_offers(db_session, {"kitapbulan": BKM_IMG}, catalog_cover=MANGAKOL)
    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image()}, cover_prefer_mangakol=False)
    fetcher.run(budget=10)
    assert vol.cover_source == "store:kitapbulan"

    db_session.delete(db_session.scalar(select(StoreListing).where(StoreListing.volume_id == vol.id)))
    db_session.commit()
    fetcher, download = _fetcher(db_session, store, {MANGAKOL_FULL: _image_b()})
    report = fetcher.run(budget=10)
    assert report.dropped == 1 and download.asked == [MANGAKOL_FULL]
    assert vol.cover_source == "mangakol"


def test_store_cover_of_an_unreleased_volume_is_dropped(db_session, store):
    vol = _volume_with_offers(db_session, {"kitapbulan": BKM_IMG}, catalog_cover=None)
    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image()})
    fetcher.run(budget=10)
    vol.catalog_released = False  # e.g. Fairy Tail 38: not out in Turkey
    db_session.commit()
    report = fetcher.run(budget=10)
    assert report.dropped == 1 and vol.cover_key is None and vol.cover_source is None


def test_kept_store_cover_is_not_dropped(db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=None)
    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image()})
    fetcher.run(budget=10)
    assert fetcher.run(budget=10).dropped == 0 and vol.cover_source == "store:bkm"


def test_failure_reason_is_recorded_and_listed(client, db_session, store):
    vol = _volume_with_offers(db_session, {"bkm": BKM_IMG}, catalog_cover=None)
    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image(1200, 400)})  # a banner
    fetcher.run(budget=10)
    assert vol.cover_key is None and vol.cover_error == "store:bkm: kapağa benzemiyor (boyut ya da en/boy oranı)"

    body = client.get("/catalog/covers/missing").json()
    assert body["count"] == 1
    item = body["items"][0]
    assert (item["volume_id"], item["kind"], item["series"]) == (vol.id, "failed", "Berserk")
    assert "kapağa benzemiyor" in item["reason"] and item["sources"][0]["url"] == BKM_IMG

    fetcher, _ = _fetcher(db_session, store, {BKM_IMG: _image()})
    vol.cover_checked_at = utcnow() - timedelta(days=8)
    db_session.commit()
    fetcher.run(budget=10)
    assert vol.cover_key and vol.cover_error is None
    assert client.get("/catalog/covers/missing").json()["count"] == 0


def test_missing_list_explains_volumes_without_sources(client, db_session, store):
    vol = _volume_with_offers(db_session, {}, catalog_cover=None)
    other = seed_catalog_series(db_session, "Nana", "Gerekli Şeyler", volumes=(1,))
    queued = db_session.scalar(select(Volume).where(Volume.series_id == other.id))
    queued.cover_url = MANGAKOL
    vol.cover_checked_at = utcnow()
    db_session.commit()

    items = {i["volume_id"]: i for i in client.get("/catalog/covers/missing").json()["items"]}
    assert items[vol.id]["kind"] == "no_source" and "Hiçbir kaynakta" in items[vol.id]["reason"]
    assert items[queued.id]["kind"] == "queued"
