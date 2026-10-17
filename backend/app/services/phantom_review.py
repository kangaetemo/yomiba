"""Evidence-gated phantom merge planning. No automatic cleanup or commit."""
from sqlalchemy import select, func, update, delete

from ..models import (Volume, Series, CatalogSeries, StoreListing, PriceHistory,
                      WishlistItem, PriceAlert, UserVolumeCollection)
from ..normalization import normalize_text, normalize_publisher, parse_volume_title
from datetime import timezone


def aware_datetime(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def plan_merge(session, source_id, target_id=None, *, products=(), catalog_confirmed=False):
    source = session.get(Volume, source_id)
    if source is None:
        return {"volume_id": source_id, "action": "KEEP", "reason": "already_absent"}
    series = session.get(Series, source.series_id)
    real = session.scalars(select(Volume).where(Volume.series_id == series.id, Volume.volume_number > 0).order_by(Volume.volume_number)).all()
    zeros = session.scalars(select(Volume.id).where(Volume.series_id == series.id, Volume.volume_number == 0)).all()
    listings = session.scalars(select(StoreListing).where(StoreListing.volume_id == source.id)).all()
    personal = {model.__tablename__: session.scalar(select(func.count()).select_from(model).where(model.volume_id == source.id))
                for model in (WishlistItem, PriceAlert, UserVolumeCollection)}
    histories = session.scalar(select(func.count()).select_from(PriceHistory).where(PriceHistory.listing_id.in_([l.id for l in listings])))
    plan = {"volume_id": source.id, "volume_number": source.volume_number,
            "series_id": series.id, "series_title": series.title, "original_title": series.original_title,
            "publisher": series.publisher.name, "positive_volume_count": len(real),
            "zero_volume_ids": list(zeros),
            "positive_volume_numbers": [v.volume_number for v in real], "isbn": source.isbn,
            "listing_count": len(listings), "history_count": histories, "personal_counts": personal,
            "store_titles": [p.get("title") for p in products],
            "stores": [{"listing_id": l.id, "code": l.store.code, "name": l.store.name,
                        "product_url": l.product_url} for l in listings],
            "product_urls": [l.product_url for l in listings],
            "action": "REVIEW", "reason": "external_title_and_catalog_evidence_required"}
    if source.volume_number >= 0:
        return {**plan, "action": "KEEP", "reason": "explicit_catalog_volume"}
    if source.volume_number != -1:
        return {**plan, "reason": "unsupported_negative_number"}
    if zeros:
        return {**plan, "reason": "explicit_zero_requires_review"}
    if any(personal.values()):
        return {**plan, "reason": "personal_data_present"}
    if not catalog_confirmed or not listings or len(real) != 1 or real[0].volume_number != 1:
        return plan
    target = real[0]
    if target_id != target.id or session.scalar(select(CatalogSeries.series_id).where(CatalogSeries.series_id == series.id)) is None:
        return plan
    if not source.isbn or (target.isbn and target.isbn != source.isbn):
        return {**plan, "reason": "isbn_conflict_or_missing"}
    by_url = {p.get("product_url"): p for p in products}
    for listing in listings:
        evidence = by_url.get(listing.product_url)
        if not evidence:
            return plan
        parsed = parse_volume_title(evidence.get("title"))
        if (parsed.is_collection or parsed.volume_number is not None
            or normalize_text(parsed.base_title) != series.normalized_title
            or normalize_publisher(evidence.get("publisher")) != series.publisher.normalized_name
            or evidence.get("isbn") != source.isbn):
            return {**plan, "reason": "product_identity_not_proven"}
    duplicates = session.scalar(select(func.count()).select_from(StoreListing).where(
        StoreListing.volume_id == target.id, StoreListing.store_id.in_([l.store_id for l in listings])))
    return {**plan, "action": "SAFE_MERGE", "reason": "catalog_and_products_confirmed",
            "target_id": target.id, "listing_moves": len(listings)-duplicates,
            "listing_consolidations": duplicates, "history_relinks": histories,
            "volume_deletions": 1, "listing_deletions": duplicates}


def apply_safe_merge(session, source_id, target_id, *, products, catalog_confirmed=False):
    """Caller must explicitly approve, own the transaction and exclude imports.

    No CLI exposes this write operation. Personal source rows always block it.
    All history points survive, including duplicate store-listing consolidation.
    """
    if session.get(Volume, source_id) is None:
        return False
    plan = plan_merge(session, source_id, target_id, products=products, catalog_confirmed=catalog_confirmed)
    if plan["action"] != "SAFE_MERGE":
        raise ValueError(f"Unsafe merge: {plan['reason']}")
    merge_volume_rows(session, source_id, target_id)
    return True


def has_personal_rows(session, volume_id) -> bool:
    """Wishlist / price alert / collection rows point at ``volume_id``."""
    return any(
        session.scalar(select(func.count()).select_from(model).where(model.volume_id == volume_id))
        for model in (WishlistItem, PriceAlert, UserVolumeCollection)
    )


def merge_volume_rows(session, source_id, target_id):
    """Fold volume ``source_id`` into ``target_id``: listings move (or are
    consolidated per store, keeping the fresher offer), every price-history
    point survives, ISBN/cover carry over, the source row is deleted.
    Caller has proven identity and checked personal rows."""
    with session.begin_nested():
        source = session.get(Volume, source_id)
        target = session.get(Volume, target_id)
        isbn, cover = source.isbn, source.cover_url
        session.execute(update(Volume).where(Volume.id == source_id).values(isbn=None))
        for listing in session.scalars(select(StoreListing).where(StoreListing.volume_id == source_id)).all():
            existing = session.scalar(select(StoreListing).where(StoreListing.volume_id == target_id, StoreListing.store_id == listing.store_id))
            if existing is None:
                session.execute(update(StoreListing).where(StoreListing.id == listing.id).values(volume_id=target_id))
            else:
                session.execute(update(PriceHistory).where(PriceHistory.listing_id == listing.id).values(listing_id=existing.id))
                if aware_datetime(listing.last_checked) > aware_datetime(existing.last_checked):
                    session.execute(update(StoreListing).where(StoreListing.id == existing.id).values(
                        product_url=listing.product_url, price=listing.price, in_stock=listing.in_stock,
                        last_checked=listing.last_checked, image_url=listing.image_url or existing.image_url))
                session.execute(delete(StoreListing).where(StoreListing.id == listing.id))
        session.execute(update(Volume).where(Volume.id == target_id).values(
            isbn=target.isbn or isbn, cover_url=target.cover_url or cover))
        session.execute(delete(Volume).where(Volume.id == source_id))
    session.expire_all()
