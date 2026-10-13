"""Compare a fixed DB snapshot with fresh Mangakol data, without DB writes."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CatalogSeries, Publisher, Series, Volume
from ..normalization import normalize_publisher, normalize_text
from ..scrapers.mangakol import MangakolCatalogScraper
from .catalog_service import legacy_phantom_condition, public_volume_condition
from .catalog_sync import CatalogSyncService, _names_related


def snapshot(session: Session) -> dict:
    """Catalog metadata only: no users, credentials, collections or sessions."""
    links = list(session.execute(select(CatalogSeries.series_id, CatalogSeries.mangakol_slug)))
    ids = {sid for sid, _ in links}
    public_ids = set(session.scalars(select(Volume.id).where(
        Volume.series_id.in_(ids), public_volume_condition(), ~legacy_phantom_condition()
    )))
    slugs = defaultdict(list)
    for sid, slug in links:
        slugs[sid].append(slug)
    volumes = defaultdict(list)
    for v in session.scalars(select(Volume).where(Volume.series_id.in_(ids)).order_by(Volume.volume_number)):
        volumes[v.series_id].append({
            "id": v.id, "number": v.volume_number, "isbn": v.isbn,
            "release_date": v.release_date.isoformat() if v.release_date else None,
            "page_count": v.page_count, "catalog_released": v.catalog_released,
            "public": v.id in public_ids,
            "covers": [v.covers_from, v.covers_to] if v.covers_from is not None else None,
        })
    rows = []
    for s, p in session.execute(select(Series, Publisher.name).join(Publisher).where(Series.id.in_(ids))):
        rows.append({"id": s.id, "title": s.title, "publisher": p, "slugs": slugs[s.id],
                     "volumes": volumes[s.id]})
    return {"taken_at": datetime.now(timezone.utc).isoformat(), "series": rows}


def audit(db: dict, scraper=None, *, details: bool = False, progress=None) -> dict:
    scraper = scraper or MangakolCatalogScraper()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "db_snapshot": db,
              "source": [], "differences": [], "errors": [], "details_requested": details,
              "details_checked": 0, "details_failed": 0, "applied": False}
    by_slug = defaultdict(list)
    for row in db["series"]:
        for slug in row["slugs"]:
            by_slug[slug].append(row)
    fetched, seen = set(), set()
    counters = Counter()
    consecutive_metadata_failures = 0

    def diff(kind, slug, **fields):
        counters[kind] += 1
        report["differences"].append({"kind": kind, "slug": slug, **fields})

    try:
        refs = scraper.list_manga()
        report["source_list_complete"] = bool(refs) and getattr(scraper, "catalog_list_complete", True)
        report["source_main_series"] = len(refs)
        consecutive_failures = 0
        for index, ref in enumerate(refs):
            if progress:
                progress({"scanned": index, "total": len(refs), "current": ref.title,
                          "details_checked": report["details_checked"]})
            try:
                manga = scraper.fetch_manga(ref.slug)
            except Exception as exc:
                report["errors"].append({"slug": ref.slug, "error": str(exc)})
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    break
                continue
            consecutive_failures = 0
            fetched.add(ref.slug)
            base = CatalogSyncService._clean_title(manga.title, manga.local_publisher)
            entries = [manga] + [replace(
                manga, slug=f"{manga.slug}~{v.format.lower()}", title=f"{base} ({v.label})",
                volumes=v.volumes, variants=(), original_title=None,
            ) for v in manga.variants if v.volumes]
            for entry in entries:
                seen.add(entry.slug)
                source = {"slug": entry.slug, "title": entry.title,
                          "publisher": entry.local_publisher, "complete": entry.volumes_complete,
                          "volumes": []}
                report["source"].append(source)
                matches = by_slug.get(entry.slug, [])
                row = matches[0] if len(matches) == 1 else None
                if not matches:
                    diff("missing_series", entry.slug, source_title=entry.title)
                elif len(matches) > 1:
                    diff("ambiguous_series", entry.slug, series_ids=[r["id"] for r in matches])
                if row:
                    clean = CatalogSyncService._clean_title(entry.title, entry.local_publisher)
                    if normalize_text(row["title"]) != normalize_text(clean):
                        diff("title_difference", entry.slug, db=row["title"], source=clean)
                    if entry.local_publisher and not _names_related(
                        normalize_publisher(row["publisher"]), normalize_publisher(entry.local_publisher)
                    ):
                        diff("publisher_difference", entry.slug, db=row["publisher"], source=entry.local_publisher)
                db_volumes = {v["number"]: v for v in row["volumes"]} if row else {}
                source_numbers = set()
                for cv in entry.volumes:
                    number = cv.number if cv.number is not None else -1
                    if number in source_numbers:
                        diff("duplicate_source_number", entry.slug, number=number)
                    source_numbers.add(number)
                    item = {"number": number, "released": cv.released, "url": cv.url,
                            "covers": list(cv.covers) if cv.covers else None}
                    source["volumes"].append(item)
                    existing = db_volumes.get(number)
                    if row and not existing:
                        diff("missing_volume", entry.slug, number=number, released=cv.released)
                    if existing:
                        if existing["catalog_released"] is None:
                            diff("release_unverified", entry.slug, number=number, source=cv.released,
                                 public=existing["public"])
                        elif existing["catalog_released"] != cv.released:
                            diff("release_difference", entry.slug, number=number,
                                 db=existing["catalog_released"], source=cv.released)
                        if not cv.released and existing["public"]:
                            diff("announced_visible", entry.slug, number=number,
                                 dated=existing["release_date"] is not None)
                        if item["covers"] and item["covers"] != existing["covers"]:
                            diff("span_difference", entry.slug, number=number,
                                 db=existing["covers"], source=item["covers"])
                    if details and cv.url:
                        try:
                            metadata = scraper.fetch_volume_details(cv.url)
                            if metadata is None:
                                raise ValueError("volume metadata unavailable")
                            report["details_checked"] += 1
                            consecutive_metadata_failures = 0
                            item.update(isbn=metadata.isbn, page_count=metadata.page_count,
                                        release_date=metadata.release_date.isoformat() if metadata.release_date else None)
                            if existing:
                                for field in ("isbn", "page_count", "release_date"):
                                    if item[field] is not None and item[field] != existing[field]:
                                        diff(field + "_difference", entry.slug, number=number,
                                             db=existing[field], source=item[field])
                        except Exception as exc:
                            consecutive_metadata_failures += 1
                            report["details_failed"] += 1
                            report["errors"].append({"slug": entry.slug, "number": number, "error": str(exc)})
                            # Do not keep hitting a source that rejects volume-page requests.
                            if consecutive_metadata_failures >= 3:
                                raise RuntimeError("volume metadata requests repeatedly failed") from exc
                        if progress:
                            progress({"scanned": index, "total": len(refs), "current": ref.title,
                                      "details_checked": report["details_checked"]})
                if row and entry.volumes_complete and source_numbers:
                    for number in sorted(set(db_volumes) - source_numbers):
                        old = db_volumes[number]
                        diff("extra_volume" if old["public"] else "retained_hidden_volume", entry.slug,
                             number=number, volume_id=old["id"], isbn=old["isbn"], public=old["public"])
                elif not entry.volumes_complete:
                    report["errors"].append({"slug": entry.slug, "error": "incomplete volume list; extras not inferred"})
        if report["source_list_complete"]:
            main_slugs = {r.slug for r in refs}
            for slug in sorted(set(by_slug) - seen):
                root = slug.split("~")[0]
                if root not in main_slugs or ("~" in slug and root in fetched):
                    diff("stale_series", slug, series_ids=[r["id"] for r in by_slug[slug]])
        report["source_scanned"] = len(fetched)
        report["complete"] = (report["source_list_complete"] and len(fetched) == len(refs)
                              and not report["errors"])
    except Exception as exc:
        report["complete"] = False
        report["errors"].append({"error": str(exc)})
    finally:
        scraper.close()
        report["source_scanned"] = len(fetched)
    report["counts"] = dict(counters)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report
