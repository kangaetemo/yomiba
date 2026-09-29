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
