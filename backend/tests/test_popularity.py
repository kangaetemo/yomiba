"""Popüler seriler: stores' bestseller lists lead the home ranking."""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import SeriesPopularity, Store, StoreListing, Volume
from app.services.popularity import parse_bkm, parse_idefix, refresh
from tests.test_import_service import seed_catalog_series


def idefix_page(names):
    items = [{"brandName": brand, "variants": [{"name": name}]} for name, brand in names]
    data = {"props": {"pageProps": {"categoryData": {"items": items}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


def bkm_page(products):
    def one(p):
        raw = json.dumps(json.dumps(p))[1:-1].replace("'", "\\'")
        return f"<script>PRODUCT_DATA.push(JSON.parse('{raw}'));</script>"
    return "".join(one(p) for p in products)


def test_parsers_read_title_publisher_and_isbn():
    assert parse_idefix(idefix_page([("Blue Lock Cilt - 27 - Komik Şeyler", "Komik Şeyler")])) == [("Blue Lock Cilt - 27", "Komik Şeyler", None)]
    assert parse_bkm(bkm_page([{"name": "Haikyu!! 2. Cilt", "brand": "Gerekli Şeyler", "code": "9786052172568"}])) == [
        ("Haikyu!! 2. Cilt", "Gerekli Şeyler", "9786052172568")]


def _seed(db_session):
    now = datetime.now(timezone.utc)
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    out = {}
    for title, pub in (("Blue Lock", "Komik Şeyler"), ("Haikyu!!", "Gerekli Şeyler"), ("Az Bilinen", "Yayınevi")):
        series = seed_catalog_series(db_session, title, pub, volumes=(1, 2))
        vols = list(db_session.scalars(select(Volume).where(Volume.series_id == series.id)))
        for v in vols:
            v.catalog_present = v.catalog_released = True
            # The obscure series is the easiest to buy: three offers per volume before.
            db_session.add(StoreListing(volume_id=v.id, store_id=store.id, product_url=f"https://x/{v.id}",
                                        price=20000, in_stock=True, last_checked=now))
        out[title] = (series, vols)
    out["Haikyu!!"][1][1].isbn = "9786052172568"
    db_session.commit()
    return out


def test_bestsellers_lead_the_home_shelf(client, db_session):
    seeded = _seed(db_session)
    pages = {
        "idefix": idefix_page([("Blue Lock Cilt - 2 - Komik Şeyler", "Komik Şeyler"), ("Blue Lock Cilt - 1 - Komik Şeyler", "Komik Şeyler")]),
        "bkm": bkm_page([{"name": "Haikyu!! 2. Cilt", "brand": "Gerekli Şeyler", "code": "9786052172568"}]),
    }

    def get(url):
        if url.endswith(("sayfa=1", "pg=1")):
            return pages["idefix" if "idefix" in url else "bkm"]
        return ""

    assert refresh(db_session, get) == 2
    scores = dict(db_session.execute(select(SeriesPopularity.series_id, SeriesPopularity.bestseller_score)).all())
    assert scores[seeded["Blue Lock"][0].id] == 1.5  # rank 0 -> 1, rank 1 -> 0.5
    assert scores[seeded["Haikyu!!"][0].id] == 1.0
    titles = [s["title"] for s in client.get("/home?popular=3").json()["popular_series"]]
    assert titles == ["Blue Lock", "Haikyu!!", "Az Bilinen"]


def test_unreadable_lists_keep_previous_scores(db_session):
    seeded = _seed(db_session)
    db_session.add(SeriesPopularity(series_id=seeded["Blue Lock"][0].id, bestseller_score=2.0, updated_at=datetime.now(timezone.utc)))
    db_session.commit()

    def down(url):
        raise OSError("blocked")

    assert refresh(db_session, down) == 0
    assert db_session.scalar(select(SeriesPopularity.bestseller_score)) == 2.0
