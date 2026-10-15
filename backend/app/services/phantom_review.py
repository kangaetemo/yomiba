"""Phantom merge preview. P0 rejects both apply entry points."""
from sqlalchemy import select, func

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
    from .isbn_safety import reject_legacy_write
    reject_legacy_write()


def has_personal_rows(session, volume_id) -> bool:
    """Wishlist / price alert / collection rows point at ``volume_id``."""
    return any(
        session.scalar(select(func.count()).select_from(model).where(model.volume_id == volume_id))
        for model in (WishlistItem, PriceAlert, UserVolumeCollection)
    )


def merge_volume_rows(session, source_id, target_id):
    from .isbn_safety import reject_legacy_write
    reject_legacy_write()
