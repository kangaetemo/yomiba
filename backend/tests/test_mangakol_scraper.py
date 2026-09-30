"""Mangakol catalog scraper tests (fixture-backed; endpoint contract
live-verified against mangakol.com on 2026-09-11: /manga/ list with
?tab=popular&page=N&partial=true fragments; SSR detail pages with the
info rows + volume grid; the first SSR page holds at most 24 volumes,
longer series continue at /manga/<id>/volumes/load-more?pageIndex=N
where N starts at 2 — One Piece TR = 62 volumes verified live)."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.mangakol import MangakolCatalogScraper
from tests.helpers import fixture_text, mock_client

LIST_P1 = fixture_text("mk_list_p1.html")
LIST_P2 = fixture_text("mk_list_p2.html")
LIST_P3 = fixture_text("mk_list_p3.html")
DETAIL_BERSERK = fixture_text("mk_detail_berserk.html")
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def _vol_item(num: int, cover: bool = True) -> str:
    img = (
        f'<img alt="x {num}" class="mk-vol-cover" loading="lazy" '
        f'src="/images/mangavolume/thumbnails/v{num}.webp"/>'
        if cover
        else ""
    )
    return (
        f'<div class="mk-vol-item" data-binding-format="SingleVolume">'
        f'<div class="mk-vol-card">'
        f'<a href="/manga/onepiece/cilt-{num}" class="mk-vol-card-link" aria-label="x {num}"></a>'
        f'<div class="mk-vol-badge">Cilt {num}</div>{img}'
        f'<div class="mk-vol-actions">'
        f'<button class="mk-vol-btn" data-volume-id="{num}" data-volume-number="{num}" title="Koleksiyona Ekle"></button>'
        f"</div></div></div>"
    )


def _detail_page(
    manga_id: str, numbers: list[int], title: str, original: str | None = None
) -> str:
    items = "".join(_vol_item(n) for n in numbers)
    # The original (foreign) title line sits in a muted h2 below the h1,
    # optionally with a Japanese part after a "|" separator (live shape).
    h2 = ""
    if original is not None:
        if "|" in original:
            left, right = original.split("|", 1)
            inner = f"{left.strip()} <span class='mx-2 opacity-50'>|</span> {right.strip()}"
        else:
            inner = original
        h2 = (
            f'<div class="mb-4">'
            f'<h2 class="text-muted fs-5 mb-4 fw-normal"> {inner}</h2></div>'
        )
    return (
        "<html><body>"
        f'<h1 class="display-5 fw-bold mb-1"><span>{title}</span></h1>'
        f"{h2}"
        f'<div class="mk-vol-grid" data-manga-id="{manga_id}">{items}</div>'
        "</body></html>"
    )


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = MangakolCatalogScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    return int(request.url.params.get("page", "1"))


def default_handler(request: httpx.Request) -> httpx.Response:
    url = request.url
    if url.path.rstrip("/") == "/manga":
        page = _page_of(request)
        if page == 1:
            return httpx.Response(200, text=LIST_P1)
        if page == 2:
            return httpx.Response(200, text=LIST_P2)
        return httpx.Response(200, text=LIST_P3)
    if url.path == "/manga/berserk-athica":
        return httpx.Response(200, text=DETAIL_BERSERK)
    # long series: 24 + 24 + 14 volumes
    if url.path == "/manga/onepiece":
        return httpx.Response(200, text=_detail_page("150", list(range(1, 25)), "One Piece"))
    if url.path == "/manga/150/volumes/load-more":
        page = int(url.params.get("pageIndex", "1"))
        if page == 2:
            return httpx.Response(200, text="".join(_vol_item(n) for n in range(25, 49)))
        if page == 3:
            return httpx.Response(200, text="".join(_vol_item(n) for n in range(49, 63)))
        return httpx.Response(200, text="")
    # short series with exactly one SSR page (24 volumes)
    if url.path == "/manga/bleach":
        return httpx.Response(200, text=_detail_page("117", list(range(1, 25)), "Bleach"))
    if url.path == "/manga/117/volumes/load-more":
        return httpx.Response(200, text="")
    return httpx.Response(404, text="not found")


@pytest.fixture()
def scraper():
    return make_scraper(default_handler)


def test_list_pagination_dedupe_and_stop(scraper):
    refs = scraper.list_manga()
    slugs = [r.slug for r in refs]
    assert slugs == ["berserk-athica", "frieren", "chainsaw-man"]
    assert len(slugs) == len(set(slugs))
    # p1 (2 new) -> p2 (1 new + 1 dup) -> p3 (all dups) -> stop
    assert scraper.settings is not None
    titles = {r.slug: r.title for r in refs}
    assert titles["berserk-athica"] == "Berserk (Athica)"
    # the /volume nav link is not a manga card
    assert "volume" not in slugs


def test_list_blocked_fails_fast():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.list_manga()


def test_detail_parses_original_title_h2():
    page = _detail_page(
        "40", [1, 2], "Tokyo Gul",
        original="Tokyo Ghoul | 東京喰種トーキョーグール",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manga/tokyo-ghoul":
            return httpx.Response(200, text=page)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    manga = scraper.fetch_manga("tokyo-ghoul")
    assert manga.title == "Tokyo Gul"
    assert manga.original_title == "Tokyo Ghoul | 東京喰種トーキョーグール"


def test_detail_parsing(scraper):
    manga = scraper.fetch_manga("berserk-athica")
    assert manga.slug == "berserk-athica"
    assert manga.title == "Berserk (Athica)"
    assert manga.local_publisher == "Athica"
    # the berserk fixture has no original-title h2
    assert manga.original_title is None
    assert [(v.number, v.cover_url) for v in manga.volumes] == [
        (1, "https://mangakol.com/images/mangavolume/thumbnails/b9a9b694ea74410b8d3ac62ce61ca3d2.webp"),
        (2, None),  # "Kapak yok" (no cover img)
        (3, "https://mangakol.com/images/mangavolume/thumbnails/c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3.webp"),
    ]


def test_detail_404_raises(scraper):
    with pytest.raises(ScraperError, match="404"):
        scraper.fetch_manga("no-such-manga")


def test_long_series_follows_load_more(scraper):
    """One Piece TR: 62 volumes = SSR(24) + pageIndex=2 (24) + pageIndex=3 (14)."""
    manga = scraper.fetch_manga("onepiece")
    numbers = [v.number for v in manga.volumes]
    assert numbers == list(range(1, 63))
    assert len(manga.volumes) == 62


def test_exactly_one_page_series_stops_on_empty_fragment(scraper):
    """Bleach-style: SSR grid full (24) but no fragment pages -> 24 volumes,
    exactly one load-more request then stop."""
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request.url.path)
        return default_handler(request)

    scraper = make_scraper(handler)
    manga = scraper.fetch_manga("bleach")
    assert len(manga.volumes) == 24
    load_more_hits = [p for p in requests_seen if p == "/manga/117/volumes/load-more"]
    assert load_more_hits == ["/manga/117/volumes/load-more"]  # one probe, then stop


SOICHI_TABS = (
    "<html><body><h1><span>Soichi</span></h1>"
    '<ul class="nav nav-tabs">'
    '<li><button class="nav-link active fw-bold" data-bs-target="#pane-SingleVolume">Tekli Cilt · 1</button></li>'
    '<li><button class="nav-link fw-bold" data-bs-target="#pane-Clothbound">Bez Cilt · 1</button></li>'
    "</ul>"
    '<div class="tab-content">'
    f'<div class="tab-pane fade show active" id="pane-SingleVolume">{_vol_item(1)}</div>'
    '<div class="tab-pane fade" id="pane-Clothbound" data-loaded="false" '
    'data-manga-id="455" data-format="Clothbound"></div>'
    "</div></body></html>"
)


def test_detail_reads_other_binding_tabs():
    """Soichi has a "Bez Cilt" (Clothbound) tab next to "Tekli Cilt": its
    lazily loaded volumes come back as a variant, not mixed into the main
    volume list."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/manga/soichi":
            return httpx.Response(200, text=SOICHI_TABS)
        if request.url.path == "/manga/455/volumes/load-more":
            assert request.url.params["format"] == "Clothbound"
            if request.url.params["pageIndex"] == "1":
                return httpx.Response(200, text=_vol_item(1).replace("cilt-1", "cilt-1-clothbound"))
            return httpx.Response(200, text="")
        return httpx.Response(404, text="not found")

    manga = make_scraper(handler).fetch_manga("soichi")
    assert [v.number for v in manga.volumes] == [1]
    assert manga.volumes[0].url.endswith("/cilt-1")
    assert len(manga.variants) == 1
    variant = manga.variants[0]
    assert (variant.format, variant.label) == ("Clothbound", "Bez Cilt")
    assert [v.url.rsplit("/", 1)[1] for v in variant.volumes] == ["cilt-1-clothbound"]
    assert sum("load-more" in u for u in seen) == 1  # short page: no second request


def test_single_format_page_has_no_variants(scraper):
    assert scraper.fetch_manga("onepiece").variants == ()
