"""Back-cover texts from store product pages (services/volume_descriptions.py).

Dry run by default: reads up to --pages product pages, opening volumes
first, prints what it found per store, the volumes it found nothing for and
a few samples, writes nothing.
--apply stores the texts (the background worker does the same once
DESCRIPTION_FETCH_ENABLED=1).

Run on the server:
  docker compose run --rm --no-deps -T backend python fetch_descriptions.py --pages 60 > /tmp/aciklama.txt
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Series, Volume
from app.services.volume_descriptions import DescriptionFetcher


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=60, help="product pages to read")
    parser.add_argument("--samples", type=int, default=12, help="texts printed in a dry run")
    parser.add_argument("--apply", action="store_true", help="store the texts")
    args = parser.parse_args()

    with SessionLocal() as session:
        report = DescriptionFetcher(session, dry_run=not args.apply).run(args.pages)
        print(report)
        if report.volumes:
            print(f"found for {report.stored} of {report.volumes} volumes tried")
        def name(volume_id: int) -> str:
            title, number = session.execute(
                select(Series.title, Volume.volume_number).join(Volume, Volume.series_id == Series.id)
                .where(Volume.id == volume_id)
            ).one()
            return f"{title} {number}"

        if report.misses:
            print("\nno text found:")
            for volume_id, urls in report.misses:
                print(f"  {name(volume_id)}: {', '.join(urls) or 'no store page'}")
        for volume_id, store, text in report.samples[: args.samples]:
            print(f"\n--- {name(volume_id)} ({store}, {len(text)} chars)\n{text}")


if __name__ == "__main__":
    main()
