"""Read-only report: where store listings are missing or stale.

Per store:
  * stale listings: not seen for ``listing_stale_hours`` while the same
    store's other listings were refreshed. The site shows them as
    "stok belirsiz" and hides them, so the store most likely no longer
    finds the product with the series query.
  * holes: catalog volumes missing between volumes the store does list
    ("has 12 and 14, not 13").

Run on the server (writes nothing):
  docker compose run --rm --no-deps -T backend python store_gaps_report.py > /tmp/eksik.txt
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import CatalogSeries, Series, Store, StoreListing, Volume
from app.services.catalog_service import _aware


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=25, help="series shown per store and section")
    args = parser.parse_args()
    window = timedelta(hours=get_settings().listing_stale_hours)

    with SessionLocal() as session:
        catalog = set(session.scalars(select(CatalogSeries.series_id).distinct()))
        titles = dict(session.execute(select(Series.id, Series.title)).all())
        stores = dict(session.execute(select(Store.id, Store.name)).all())
        volumes: dict[int, set[int]] = defaultdict(set)
        for series_id, number in session.execute(
            select(Volume.series_id, Volume.volume_number).where(Volume.volume_number > 0)
        ):
            if series_id in catalog:
                volumes[series_id].add(number)
        rows = session.execute(
            select(StoreListing.store_id, StoreListing.last_checked,
                   Volume.series_id, Volume.volume_number)
            .join(Volume, Volume.id == StoreListing.volume_id)
        ).all()

    newest: dict[int, object] = {}
    for store_id, checked, _, _ in rows:
        checked = _aware(checked)
        if checked and (store_id not in newest or checked > newest[store_id]):
            newest[store_id] = checked

    total: dict[int, int] = defaultdict(int)
    stale: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    listed: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for store_id, checked, series_id, number in rows:
        if series_id not in catalog:
            continue
        total[store_id] += 1
        listed[store_id][series_id].add(number)
        checked = _aware(checked)
        if checked is None or newest[store_id] - checked > window:
            stale[store_id][series_id].append(number)

    for store_id in sorted(stores, key=lambda s: stores[s]):
        if not total[store_id]:
            continue
        holes = {}
        for series_id, numbers in listed[store_id].items():
            positive = sorted(n for n in numbers if n > 0)
            if len(positive) < 2:
                continue
            missing = sorted(n for n in volumes[series_id]
                             if positive[0] < n < positive[-1] and n not in numbers)
            if missing:
                holes[series_id] = missing
        n_stale = sum(len(v) for v in stale[store_id].values())
        print(f"\n===== {stores[store_id]}: {total[store_id]} ilan, "
              f"{n_stale} stok belirsiz ({len(stale[store_id])} seri), "
              f"{sum(len(v) for v in holes.values())} arada eksik cilt ({len(holes)} seri)")
        ranked = sorted(stale[store_id].items(), key=lambda kv: -len(kv[1]))[: args.top]
        for series_id, numbers in ranked:
            print(f"  belirsiz  {titles.get(series_id)}: {sorted(numbers)}")
        ranked = sorted(holes.items(), key=lambda kv: -len(kv[1]))[: args.top]
        for series_id, numbers in ranked:
            print(f"  eksik     {titles.get(series_id)}: {numbers}")


if __name__ == "__main__":
    main()
