"""GET /search — side-effect-free catalog lookup from prepared DB data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.search import ImportStatusOut, SearchResponse, SeriesSummary
from ..services import catalog_service, series_slugs
from ..utils import from_cents

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
    offers = catalog_service.series_offer_summary(session, [m.series.id for m in matches])
    slugs = series_slugs.slugs_for(session, [m.series.id for m in matches])
    return SearchResponse(
        results=[
            SeriesSummary(
                id=match.series.id,
                slug=slugs[match.series.id],
                title=match.series.title,
                publisher=match.series.publisher.name,
                cover_url=match.cover_url,
                volume_count=match.volume_count,
                in_stock_offers=offers.get(match.series.id, (0, None))[0],
                lowest_price=from_cents(offers.get(match.series.id, (0, None))[1]),
            )
            for match in matches
        ],
        status=ImportStatusOut(
            state="fresh" if matches else "idle",
            detail=None,
            last_success_at=None,
        ),
    )
