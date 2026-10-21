"""Mark stored covers that are probably the Japanese original as
provisional, so the cover worker replaces them with the Turkish cover.

Covers stored before this change carry no provisional flag. A cover is
marked provisional (see services/covers.py, ``is_provisional``) when

  * the volume is still not out ("Yakında" or a future release date), or
  * it was stored before the volume's release date, or, for a Mangakol
    image, within ``MANGAKOL_SETTLE`` days after it.

The day the cover was stored is ``cover_checked_at`` (it is not touched
again once a cover is stored). The source URL the cover came from is
recorded so the same image is not taken again as the "replacement".
Covers that came out long enough ago are marked final (no flag change
afterwards). Volumes that are already out are queued for the next cover
pass (hourly; the admin "Kapakları indir" button starts one now).

Read-only unless ``--apply``. Run on the server:
  docker compose run --rm --no-deps -T backend python mark_provisional_covers.py
  docker compose run --rm --no-deps -T backend python mark_provisional_covers.py --apply
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Series, Store, StoreListing, Volume
from app.services.catalog_service import _aware
from app.services.covers import is_provisional, volume_is_out
from app.utils import utcnow


def origin_url(session, volume: Volume) -> str | None:
    """Source URL of the stored cover, from its ``cover_source`` tag."""
    source = volume.cover_source or ""
    if source.startswith("store:"):
        return session.scalar(
            select(StoreListing.image_url)
            .join(Store, Store.id == StoreListing.store_id)
            .where(StoreListing.volume_id == volume.id, Store.code == source[6:])
            .limit(1)
        )
    return volume.cover_url  # "mangakol" / "catalog"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the flags (default: list only)")
    args = parser.parse_args()

    today = utcnow().date()
    counts: Counter[str] = Counter()
    with SessionLocal() as session:
        rows = session.execute(
            select(Volume, Series.title)
            .join(Series, Series.id == Volume.series_id)
            .where(Volume.cover_key.isnot(None), Volume.cover_provisional.is_(None))
            .order_by(Series.title, Volume.volume_number)
        ).all()
        for volume, title in rows:
            checked = _aware(volume.cover_checked_at)
            stored_on = checked.date() if checked else today
            provisional = is_provisional(volume, volume.cover_source, stored_on)
            if provisional:
                out = volume_is_out(volume, today)
                counts["geçici, yenilenecek" if out else "geçici, çıkınca yenilenecek"] += 1
                print(f"{title} #{volume.volume_number}: kaynak={volume.cover_source} "
                      f"kaydedildi={stored_on} çıkış={volume.release_date or '?'} "
                      f"{'(çıktı, sıraya alınır)' if out else '(henüz çıkmadı)'}")
            else:
                counts["kalıcı"] += 1
            if args.apply:
                volume.cover_provisional = provisional
                volume.cover_origin_url = origin_url(session, volume)
                if provisional and volume_is_out(volume, today):
                    volume.cover_checked_at = None  # next cover pass
        if args.apply:
            session.commit()

    print()
    for label, n in sorted(counts.items()):
        print(f"{label}: {n}")
    print("Uygulandı." if args.apply else "Deneme: hiçbir şey yazılmadı (--apply ile yazar).")


if __name__ == "__main__":
    main()
