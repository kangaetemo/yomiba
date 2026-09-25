"""Collection tracking: mark a volume as owned / missing / wanted.

There is no auth in this project scope, so there is exactly one implicit
user (the local operator). A volume carries at most one status; NULL means
it is not tracked. Imports never modify this column, so tracking survives
re-imports.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Volume

#: The only valid collection statuses (also used by the API schemas).
COLLECTION_STATUSES: tuple[str, ...] = ("owned", "missing", "wanted")


def set_volume_status(
    session: Session, volume_id: int, status: str | None
) -> Volume | None:
    """Set the collection status of a volume, or clear it when ``status``
    is ``None``.

    Returns the updated volume, or ``None`` when the volume does not exist.
    Commits on success.
    """
    if status is not None and status not in COLLECTION_STATUSES:
        raise ValueError(f"invalid collection status: {status!r}")
    volume = session.get(Volume, volume_id)
    if volume is None:
        return None
    volume.collection_status = status
    session.commit()
    return volume
