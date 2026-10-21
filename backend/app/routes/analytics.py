"""Site analytics: the public beacon and the admin report."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import optional_user, require_admin
from ..database import get_db
from ..models import User
from ..services import analytics

logger = logging.getLogger("yomiba.analytics")

router = APIRouter(tags=["analytics"])


@router.post("/olay", status_code=204, include_in_schema=False)
async def beacon(request: Request, session: Session = Depends(get_db),
                 user: User | None = Depends(optional_user)) -> Response:
    """One browser event (sendBeacon, text/plain JSON). Always 204: a page
    never learns whether, or why, an event was dropped. Admin visits are
    not counted."""
    if user is None or user.role != "ADMIN":
        try:
            body = await request.body()
            payload = json.loads(body[:8192]) if body else None
            if isinstance(payload, dict):
                analytics.record(
                    session, payload, headers=request.headers,
                    client_host=request.client.host if request.client else None,
                    logged_in=user is not None,
                )
        except Exception:
            session.rollback()
            logger.exception("analytics: beacon failed")
    return Response(status_code=204)


@router.get("/admin/analytics", dependencies=[Depends(require_admin)])
def report(days: int = Query(default=30), session: Session = Depends(get_db)) -> dict:
    return analytics.build_report(session, days)
