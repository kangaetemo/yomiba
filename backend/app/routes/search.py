"""GET /search — side-effect-free catalog lookup from prepared DB data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.search import ImportStatusOut, SearchResponse, SeriesSummary
from ..services import catalog_service

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_series(
    q: str = Query(min_length=1, max_length=200, description="Series title to search for"),
    session: Session = Depends(get_db),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Sorgu 'q' boş olamaz.")

    matches = catalog_service.search_series(session, query)
    return SearchResponse(
        results=[
            SeriesSummary(
                id=match.series.id,
                title=match.series.title,
                publisher=match.series.publisher.name,
                cover_url=match.cover_url,
                volume_count=match.volume_count,
            )
            for match in matches
        ],
        status=ImportStatusOut(
            state="fresh" if matches else "idle",
            detail=None,
            last_success_at=None,
        ),
    )
