"""fix_isbn_conflicts.py: move a wrongly placed ISBN and the listings proven
(by their product page ISBN) to belong to the right volume."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import fix_isbn_conflicts as fix
from app.database import Base
from app.models import CatalogSeries, PriceHistory, Publisher, Series, Store, StoreListing, Volume

AKAME_3 = "9786256335523"
AKAME_2 = "9786256335080"


def _page(isbn: str) -> str:
    node = {"@context": "https://schema.org", "@type": "Product", "isbn": isbn}
    return f'<script type="application/ld+json">{json.dumps(node)}</script>'


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "yomiba.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(engine)()
    pub = Publisher(name="Athica", normalized_name="athica")
    session.add(pub)
    session.flush()
    series = Series(publisher_id=pub.id, title="Akame, Keser!", normalized_title="akame keser",
                    slug="akame-keser")
    session.add(series)
    session.flush()
    session.add(CatalogSeries(series_id=series.id, mangakol_slug="akame-ga-kill"))
    v2 = Volume(series_id=series.id, volume_number=2, isbn=AKAME_3)
    v3 = Volume(series_id=series.id, volume_number=3)
    bkm, ks, dr = Store(code="bkm", name="BKM"), Store(code="kitapsec", name="Kitapsec"), Store(code="dr", name="D&R")
    session.add_all([v2, v3, bkm, ks, dr])
    session.flush()
    wrong = StoreListing(volume_id=v2.id, store_id=bkm.id, product_url="https://bkm/akame-3", price=18000)
    right = StoreListing(volume_id=v2.id, store_id=ks.id, product_url="https://ks/akame-2", price=17000)
    unknown = StoreListing(volume_id=v2.id, store_id=dr.id, product_url="https://dr/akame", price=16000)
    session.add_all([wrong, right, unknown])
    session.flush()
    session.add(PriceHistory(listing_id=wrong.id, price=18000))
    session.commit()
    ids = {"v2": v2.id, "v3": v3.id, "wrong": wrong.id, "right": right.id, "unknown": unknown.id}
    session.close()
    return path, sessionmaker(engine), ids


PAGES = {"https://bkm/akame-3": _page(AKAME_3), "https://ks/akame-2": _page(AKAME_2)}


def _case():
    return ["--case", f"Akame, Keser!|{AKAME_3}|2|3"]


def test_dry_run_changes_nothing(db, capsys):
    path, sessions, ids = db
    assert fix.main(["--db", str(path), *_case()], fetch=PAGES.get) == 0
    out = json.loads(capsys.readouterr().out)
    actions = {l["listing_id"]: l["action"] for l in out["cases"][0]["listings"]}
    assert actions == {ids["wrong"]: "move", ids["right"]: "keep", ids["unknown"]: "keep"}
    with sessions() as s:
        assert s.get(Volume, ids["v2"]).isbn == AKAME_3
        assert s.get(StoreListing, ids["wrong"]).volume_id == ids["v2"]


def test_apply_moves_isbn_and_only_proven_listing(db, capsys):
    path, sessions, ids = db
    assert fix.main(["--db", str(path), "--apply", *_case()], fetch=PAGES.get) == 0
    with sessions() as s:
        assert s.get(Volume, ids["v2"]).isbn is None
        assert s.get(Volume, ids["v3"]).isbn == AKAME_3
        assert s.get(StoreListing, ids["wrong"]).volume_id == ids["v3"]
        assert s.get(StoreListing, ids["right"]).volume_id == ids["v2"]
        assert s.get(StoreListing, ids["unknown"]).volume_id == ids["v2"]  # no proof: stays
        assert s.scalar(select(PriceHistory.listing_id)) == ids["wrong"]
    assert list(path.parent.glob("yomiba.db.bak-isbn-fix-*"))


def test_apply_consolidates_into_existing_target_listing(db):
    path, sessions, ids = db
    with sessions() as s:
        bkm = s.scalar(select(Store).where(Store.code == "bkm"))
        s.add(StoreListing(volume_id=ids["v3"], store_id=bkm.id, product_url="https://bkm/akame-3", price=18500))
        s.commit()
    fix.main(["--db", str(path), "--apply", *_case()], fetch=PAGES.get)
    with sessions() as s:
        assert s.get(StoreListing, ids["wrong"]) is None
        kept = s.scalar(select(StoreListing).where(StoreListing.volume_id == ids["v3"]))
        assert s.scalar(select(PriceHistory.listing_id)) == kept.id  # history kept


def test_second_run_is_a_no_op(db, capsys):
    path, _, _ = db
    fix.main(["--db", str(path), "--apply", *_case()], fetch=PAGES.get)
    capsys.readouterr()
    fix.main(["--db", str(path), "--apply", *_case()], fetch=PAGES.get)
    out = capsys.readouterr().out
    assert "already fixed?" in out and "Nothing to apply." in out


def test_page_isbn_sources():
    assert fix.page_isbn(_page(AKAME_3)) == AKAME_3
    gs = '<div class="product-list-title">Stok Kodu</div><div class="product-list-content">9786256335523</div>'
    assert fix.page_isbn(gs) == AKAME_3
    assert fix.page_isbn("<html>anasayfa</html>") is None
