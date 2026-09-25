"""GET /search — DB-first series search with automatic background import.

The route stays thin: validate input, call the search service, map onto the
response model. Scraping never happens on the request path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.search import ImportStatusOut, SearchResponse, SeriesSummary
from ..services import search_service

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_series(
    request: Request,
    q: str = Query(min_length=1, max_length=200, description="Series title to search for"),
    session: Session = Depends(get_db),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Sorgu 'q' boş olamaz.")

    runner = request.app.state.import_runner
    outcome = search_service.search_with_auto_import(session, query, runner)
    return SearchResponse(
        results=[
            SeriesSummary(
                id=match.series.id,
                title=match.series.title,
                publisher=match.series.publisher.name,
                cover_url=match.cover_url,
                volume_count=match.volume_count,
            )
            for match in outcome.matches
        ],
        status=ImportStatusOut(
            state=outcome.import_status.state,
            detail=outcome.import_status.detail,
            last_success_at=outcome.import_status.last_success_at,
        ),
    )
