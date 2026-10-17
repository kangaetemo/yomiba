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


class LowestPointOut(BaseModel):
    """From ``at`` on, the cheapest in-stock offer was ``price`` at
    ``store`` (both None: no store had it in stock)."""

    at: datetime
    price: float | None
    store: str | None


class PriceHistoryOut(BaseModel):
    volume_id: int
    listings: list[HistoryListingOut] = []
    #: The volume's lowest in-stock price over time, as steps (the chart).
    lowest: list[LowestPointOut] = []
