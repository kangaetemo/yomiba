"""Price-alert endpoint schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PriceAlertDetail(BaseModel):
    id: int
    #: Threshold in CENTS (15000 = 150 TRY). Always a positive integer.
    threshold_price: int
    #: Paused alerts keep their threshold but are ignored by future checkers.
    is_active: bool
    updated_at: datetime


class PriceAlertOut(BaseModel):
    volume_id: int
    #: ``null`` when the volume has no alert.
    alert: PriceAlertDetail | None = None


class PriceAlertIn(BaseModel):
    """Body for PUT /volume/{id}/price-alert.

    * ``threshold_price``: cents, must be > 0. Required when no alert
      exists yet; optional afterwards (threshold-only update).
    * ``is_active``: optional; omit to keep the current state (new alerts
      default to active). Sending only ``is_active`` pauses / re-activates
      without changing the threshold.
    """

    threshold_price: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
