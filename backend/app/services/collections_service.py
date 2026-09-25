"""Per-user collection tracking for catalog volumes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import UserVolumeCollection, Volume
from ..utils import utcnow

#: The only valid collection statuses (also used by the API schemas).
COLLECTION_STATUSES: tuple[str, ...] = ("owned", "missing", "wanted")


def get_volume_status(session: Session, user_id: int | None, volume_id: int) -> str | None:
    if user_id is None:
        return None
    return session.scalar(select(UserVolumeCollection.status).where(
        UserVolumeCollection.user_id == user_id,
        UserVolumeCollection.volume_id == volume_id,
    ))


def set_volume_status(
    session: Session, user_id: int, volume_id: int, status: str | None
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
    row = session.scalar(select(UserVolumeCollection).where(
        UserVolumeCollection.user_id == user_id,
        UserVolumeCollection.volume_id == volume_id,
    ))
    if status is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(UserVolumeCollection(user_id=user_id, volume_id=volume_id, status=status))
    else:
        row.status = status
        row.updated_at = utcnow()
    session.commit()
    return volume
