"""GET /covers/{key} — self-hosted cover files (see services/covers.py).

Keys are content-addressed, so a URL never changes meaning: cached for a
year and marked immutable. Only served for the local store; an object store
serves its files from its own CDN.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.covers import KEY_RE, get_cover_store

router = APIRouter(tags=["covers"])


@router.get("/covers/{key:path}")
def get_cover(key: str) -> FileResponse:
    if not KEY_RE.match(key):
        raise HTTPException(status_code=404, detail="Kapak bulunamadı.")
    path = get_cover_store().local_path(key)
    if path is None:
        raise HTTPException(status_code=404, detail="Kapak bulunamadı.")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
