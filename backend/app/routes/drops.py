"""Observed market price drops: one current, buyable offer per volume."""
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.price_deals import current_price_deals
from ..utils import utcnow

router = APIRouter(tags=["drops"])


@router.get("/price-drops")
def price_drops(
    hours: int = Query(default=168, ge=1, le=24 * 30),
    limit: int = Query(default=12, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    significant: bool = False,
    sort: Literal["recent", "percent", "saving", "price"] = "recent",
    volume_id: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db),
) -> dict:
    # A copy: the site-wide list is cached and shared.
    drops = list(current_price_deals(session, volume_id=volume_id, hours=hours))
    if significant:
        drops = [d for d in drops if d["significant"]]
    if sort == "percent":
        drops.sort(key=lambda d: (-d["drop_pct"], -d["saving"], d["volume_id"]))
    elif sort == "saving":
        drops.sort(key=lambda d: (-d["saving"], -d["drop_pct"], d["volume_id"]))
    elif sort == "price":
        drops.sort(key=lambda d: (d["new_price"], d["volume_id"]))
    return {"drops": drops[offset:offset + limit], "total": len(drops),
            "offset": offset, "limit": limit, "window_hours": hours,
            "generated_at": utcnow().isoformat()}
