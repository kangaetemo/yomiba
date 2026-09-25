"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now (consistent across SQLite / PostgreSQL)."""
    return datetime.now(timezone.utc)


def to_cents(price: float | int | str | None) -> int | None:
    """Convert a decimal price to integer cents, rounding half-up.

    >>> to_cents("163.54")
    16354
    >>> to_cents(169)
    16900
    >>> to_cents(None) is None
    True
    """
    if price is None:
        return None
    from decimal import Decimal, ROUND_HALF_UP

    value = Decimal(str(price))
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_cents(cents: int | None) -> float | None:
    """Convert integer cents back to a decimal number for the API."""
    if cents is None:
        return None
    return round(cents / 100.0, 2)
