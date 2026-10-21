""""Hatalı içerik bildir": the public form and the admin list."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import optional_user, require_admin
from ..database import get_db
from ..models import User
from ..services import content_reports

router = APIRouter(tags=["reports"])


@router.post("/hata-bildir", status_code=204)
def submit_report(request: Request, payload: dict = Body(...), session: Session = Depends(get_db),
                  user: User | None = Depends(optional_user)) -> Response:
    if int(request.headers.get("content-length") or 0) > 16_384:
        raise HTTPException(status_code=413, detail="Bildirim çok uzun.")
    content_reports.submit(
        session, payload, headers=request.headers,
        client_host=request.client.host if request.client else None, user=user,
    )
    return Response(status_code=204)


@router.get("/admin/reports", dependencies=[Depends(require_admin)])
def list_reports(status: str | None = Query(default="new"), session: Session = Depends(get_db)) -> dict:
    return content_reports.admin_list(session, status)


@router.get("/admin/reports/count", dependencies=[Depends(require_admin)])
def count_reports(session: Session = Depends(get_db)) -> dict:
    return {"new": content_reports.open_count(session)}


@router.patch("/admin/reports/{report_id}", dependencies=[Depends(require_admin)])
def update_report(report_id: int, payload: dict = Body(...), session: Session = Depends(get_db)) -> dict:
    content_reports.set_status(session, report_id, payload.get("status"))
    return {"id": report_id, "status": payload.get("status")}
