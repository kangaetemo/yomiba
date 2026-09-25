"""Wishlist endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel


class WishlistOut(BaseModel):
    volume_id: int
    #: Whether the current user has this volume on their wishlist.
    wishlisted: bool
