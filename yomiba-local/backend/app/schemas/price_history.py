"""Price-history endpoint schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HistoryPointOut(BaseModel):
    price: float
    checked_at: datetime


class HistoryListingOut(BaseModel):
    listing_id: int
    store: str
    points: list[HistoryPointOut] = []


class PriceHistoryOut(BaseModel):
    volume_id: int
    listings: list[HistoryListingOut] = []
