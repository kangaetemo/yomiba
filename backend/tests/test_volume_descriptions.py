"""Back-cover texts from store product pages (services/volume_descriptions.py)."""
import json
from types import SimpleNamespace

from app.models import Store
from app.services.volume_descriptions import (
    MAX_LENGTH,
    DescriptionFetcher,
    clean_description,
    description_from_page,
)
from tests.test_home_feed import _offer, _vol
from tests.test_import_service import seed_catalog_series

BLURB = ("Simsiyah ve kocaman bir adam, Guts! Sırtında devasa bir kılıç taşıyan bu yalnız savaşçı, "
         "peşine düşen iblislerle her gece yeniden savaşmak zorunda.")


def _page(description=None, og=None):
    ld = {"@context": "https://schema.org", "@type": ["Product", "Book"], "name": "Berserk 1"}
    if description is not None:
        ld["description"] = description
    meta = f'<meta property="og:description" content="{og}">' if og else ""
    return (f'<html><head>{meta}<script type="application/ld+json">{json.dumps(ld)}</script>'
            "</head><body></body></html>")


def test_clean_description_strips_html_and_spec_lines():
    raw = f"<p>{BLURB}</p><p>ISBN: 9786256335424<br>Sayfa Sayısı: 232</p>"
    assert clean_description(raw) == BLURB
    assert clean_description("Kısa metin.") is None
    assert clean_description(f"{BLURB} En uygun fiyatla hemen satın al!") is None
    long = clean_description(" ".join([BLURB] * 20))
    assert len(long) <= MAX_LENGTH and long.endswith(".")


def test_description_from_json_ld_then_og():
    assert description_from_page(_page(BLURB)) == BLURB
    assert description_from_page(_page(None, og=BLURB)) == BLURB
    shop = "Berserk 1 kitabını en uygun fiyatla satın al, hızlı kargo ile kapında. Bkmkitap güvencesiyle."
    assert description_from_page(_page(None, og=shop)) is None


class FakeScraper:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return SimpleNamespace(status_code=200, text=self.pages.get(url, _page()))


def test_fetcher_fills_first_volumes_first_and_series_shows_intro(client, db_session):
    bkm, ks = Store(code="bkm", name="BKM Kitap"), Store(code="ks", name="Kitapseç")
    db_session.add_all([bkm, ks])
    series = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    one, two = _vol(db_session, series, 1), _vol(db_session, series, 2)
    empty = _offer(db_session, one, bkm, 15000)
    described = _offer(db_session, one, ks, 16000)
    second = _offer(db_session, two, bkm, 15000)
    db_session.commit()
    pages = {described.product_url: _page(BLURB), second.product_url: _page("<p>" + BLURB.upper() + "</p>")}
    scrapers = {"bkm": FakeScraper(pages), "ks": FakeScraper(pages)}

    dry = DescriptionFetcher(db_session, scrapers=scrapers, dry_run=True).run(budget=1)
    assert dry.pages == 1 and dry.stored == 0 and one.description is None

    report = DescriptionFetcher(db_session, scrapers=scrapers).run(budget=10)
    assert report.stored == 2 and report.pages == 3
    assert scrapers["bkm"].urls[1] == empty.product_url  # volume 1 before volume 2
    db_session.refresh(one)
    assert (one.description, one.description_source) == (BLURB, "ks")
    assert one.description_checked_at is not None

    body = client.get(f"/series/{series.id}").json()
    assert body["description"] == BLURB and body["description_source"] == "Kitapseç"
    volume = client.get(f"/volume/{two.id}").json()
    assert volume["description"] == BLURB.upper() and volume["description_source"] == "BKM Kitap"

    # Nothing left to read: a second pass fetches no page.
    assert DescriptionFetcher(db_session, scrapers=scrapers).run(budget=10).pages == 0


def test_clean_description_repairs_pdf_copy_text():
    raw = ("Severek anne dedikleri kis¸i gerc¸ek anneleri degˆil. Gerc¸egˆi o¨gˆrenen u¨c¸lu¨yu¨ "
           "nasıl bir kader beklemektedir...!?\nDeiji, yarı-iblis köpeği ile birlikte para için iblis\n"
           "avına çıkar. Ölüm Tanrısı Ryuk`un defteri:Death Note.Bu deftere adı yazılanlar ölür…\n"
           "Yeni paragraf burada başlıyor.")
    assert clean_description(raw) == (
        "Severek anne dedikleri kişi gerçek anneleri değil. Gerçeği öğrenen üçlüyü "
        "nasıl bir kader beklemektedir...!?\nDeiji, yarı-iblis köpeği ile birlikte para için iblis "
        "avına çıkar. Ölüm Tanrısı Ryuk’un defteri: Death Note. Bu deftere adı yazılanlar ölür…\n"
        "Yeni paragraf burada başlıyor."
    )
