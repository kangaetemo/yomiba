import pytest
from sqlalchemy import select, func, text
from app.models import Volume, Store, StoreListing, PriceHistory, WishlistItem
from app.services.phantom_review import plan_merge, apply_safe_merge
from tests.test_import_service import seed_catalog_series


def setup_pair(session, duplicate=False):
    series = seed_catalog_series(session, "Elveda Eri", "Gerekli Şeyler")
    target = session.scalar(select(Volume))
    source = Volume(series_id=series.id, volume_number=-1, isbn="9786258237559", cover_url="https://example.com/cover")
    store = Store(code="bkm", name="BKM")
    session.add_all([source, store]); session.flush()
    listing = StoreListing(volume_id=source.id, store_id=store.id, product_url="https://example.com/eri", price=10000)
    session.add(listing); session.flush()
    session.add(PriceHistory(listing_id=listing.id, price=10000))
    if duplicate:
        other = StoreListing(volume_id=target.id, store_id=store.id, product_url="https://example.com/other", price=12000)
        session.add(other); session.flush()
        session.add(PriceHistory(listing_id=other.id, price=12000))
    session.commit()
    evidence = [dict(product_url=listing.product_url, title="Elveda Eri", isbn=source.isbn, publisher="Gerekli Şeyler")]
    return source.id, target.id, evidence


@pytest.mark.parametrize("duplicate", [False, True])
def test_safe_merge_requires_a_new_decision_and_retains_history(db_session, duplicate):
    from app.services.isbn_safety import MutationPaused
    source, target, evidence = setup_pair(db_session, duplicate)
    plan = plan_merge(db_session, source, target, products=evidence, catalog_confirmed=True)
    assert plan["action"] == "SAFE_MERGE"  # preview remains available
    with pytest.raises(MutationPaused):
        apply_safe_merge(db_session, source, target, products=evidence, catalog_confirmed=True)
    assert db_session.get(Volume, source) is not None
    assert db_session.get(Volume, target).isbn is None
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == 1 + duplicate
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 1 + duplicate


def test_personal_data_and_volume_id_survive_a_paused_merge(db_session):
    from app.services.isbn_safety import MutationPaused
    source, target, evidence = setup_pair(db_session)
    db_session.add(WishlistItem(user_id=1, volume_id=source)); db_session.commit()
    with pytest.raises(MutationPaused):
        apply_safe_merge(db_session, source, target, products=evidence, catalog_confirmed=True)
    assert db_session.get(Volume, source) is not None
    assert db_session.scalar(select(WishlistItem.volume_id)) == source


def test_audit_command_is_readonly(db_session, engine, monkeypatch, capsys):
    import json
    import sys
    from audit_phantom_volumes import main
    source, target, evidence = setup_pair(db_session)
    monkeypatch.setattr(sys, "argv", ["audit_phantom_volumes.py", "--db", engine.url.database])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["counts"] == {"SAFE_MERGE": 0, "REVIEW": 1, "KEEP": 0}
    assert report["before"] == report["expected_after_approved_plan"]
    assert report["applied"] is False
    assert db_session.get(Volume, source) is not None
