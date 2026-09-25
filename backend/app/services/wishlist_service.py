"""Wishlist service: track / untrack volumes for the current user.

Commit behavior mirrors :mod:`collections_service`: the service owns the
write and commits; routes stay thin.

The acting user ID is passed explicitly by the authenticated route.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Volume, WishlistItem


def add_to_wishlist(session: Session, volume_id: int, user_id: int) -> bool | None:
    """Add a volume to the wishlist (idempotent: re-adding creates nothing).

    Returns ``True`` when the volume is (now) on the wishlist, or ``None``
    when the volume does not exist.
    """
    if session.get(Volume, volume_id) is None:
        return None
    existing = session.scalar(
        select(WishlistItem).where(
            WishlistItem.user_id == user_id,
            WishlistItem.volume_id == volume_id,
        )
    )
    if existing is None:
        session.add(WishlistItem(user_id=user_id, volume_id=volume_id))
        session.commit()
    return True


def remove_from_wishlist(session: Session, volume_id: int, user_id: int) -> bool | None:
    """Remove a volume from the wishlist (idempotent: removing twice is safe).

    Returns ``True`` when the volume is (now) not on the wishlist, or
    ``None`` when the volume does not exist.
    """
    if session.get(Volume, volume_id) is None:
        return None
    item = session.scalar(
        select(WishlistItem).where(
            WishlistItem.user_id == user_id,
            WishlistItem.volume_id == volume_id,
        )
    )
    if item is not None:
        session.delete(item)
        session.commit()
    return True


def is_wishlisted(session: Session, volume_id: int, user_id: int) -> bool | None:
    """Return the wishlist state of a volume, or ``None`` when the volume
    does not exist."""
    if session.get(Volume, volume_id) is None:
        return None
    return (
        session.scalar(
            select(WishlistItem.id).where(
                WishlistItem.user_id == user_id,
                WishlistItem.volume_id == volume_id,
            )
        )
        is not None
    )
