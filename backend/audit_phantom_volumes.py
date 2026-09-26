"""Read-only phantom report; optional AniList evidence. No --apply option."""
import argparse
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models import Volume, StoreListing, PriceHistory
from app.services.phantom_review import plan_merge
from app.services.anilist_audit import AniListAuditClient, enrich_plan, summarize


def validate_write_path(parser, candidate, db_path):
    """Cache/report outputs must never overwrite SQLite or the evidence input."""
    path = candidate.resolve()
    protected = [db_path, Path(__file__).with_name("yomiba.db").resolve()]
    if (path in protected or path.suffix.lower() in (".db", ".sqlite", ".sqlite3")
        or str(path).endswith(("-wal", "-shm", "-journal"))
        or any(path.exists() and p.exists() and os.path.samefile(path, p) for p in protected)):
        parser.error("Cache/output must not point to a database or SQLite sidecar")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--evidence", type=Path, help="Optional reviewed JSON keyed by phantom volume ID")
    parser.add_argument("--anilist", action="store_true", help="Enable optional public metadata queries")
    parser.add_argument("--offline", action="store_true", help="Use fresh cache only; never query AniList")
    parser.add_argument("--cache", type=Path, help="Optional AniList JSON cache; no DB tables")
    parser.add_argument("--output", type=Path, help="Write JSON report instead of stdout")
    args = parser.parse_args()
    path = args.db.resolve()
    production = Path(__file__).with_name("yomiba.db").resolve()
    if (path == production or not path.is_file()
        or (production.exists() and os.path.samefile(path, production))):
        parser.error("Use an existing staging snapshot, not backend/yomiba.db")
    for destination in (args.cache, args.output):
        if destination:
            validate_write_path(parser, destination, path)
            if args.evidence and destination.resolve() == args.evidence.resolve():
                parser.error("Cache/output must not overwrite evidence")
    if args.cache:
        validate_write_path(parser, args.cache.with_suffix(args.cache.suffix + ".tmp"), path)
    if args.cache and args.output and args.cache.resolve() == args.output.resolve():
        parser.error("Cache and output must use different files")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else {}
    engine = create_engine(f"sqlite:///{path.as_uri()}?mode=ro&uri=true")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA query_only=ON")
            connection.exec_driver_sql("BEGIN")  # Consistent snapshot; released before HTTP requests.
            with Session(bind=connection) as session:
                rows = []
                for v in session.scalars(select(Volume).where(Volume.volume_number == -1).order_by(Volume.id)):
                    item = evidence.get(str(v.id), {})
                    rows.append(plan_merge(session, v.id, item.get("target_id"),
                                           products=item.get("products", []),
                                           catalog_confirmed=item.get("catalog_confirmed", False)))
                zeros = [{"volume_id": v.id, "series_id": v.series_id, "volume_number": 0,
                          "series_title": v.series.title, "final_recommendation": "KEEP",
                          "reason": "explicit_zero_is_not_phantom"}
                         for v in session.scalars(select(Volume).where(Volume.volume_number == 0).order_by(Volume.id))]
                safe_targets = [row['target_id'] for row in rows if row['action'] == 'SAFE_MERGE']
                for row in rows:
                    if row['action'] == 'SAFE_MERGE' and safe_targets.count(row['target_id']) > 1:
                        row.update(action='REVIEW', reason='multiple_candidate_isbn_conflict')
                before = {model.__tablename__: session.scalar(select(func.count()).select_from(model))
                          for model in (Volume, StoreListing, PriceHistory)}
                safe = [row for row in rows if row['action'] == 'SAFE_MERGE']
                after = {**before, 'volumes': before['volumes']-len(safe),
                         'store_listings': before['store_listings']-sum(r['listing_deletions'] for r in safe)}
                report = {"candidates": rows, "counts": {action: sum(r['action']==action for r in rows)
                    for action in ('SAFE_MERGE','REVIEW','KEEP')}, "before": before,
                    "expected_after_approved_plan": after, "applied": False,
                    "preserved_zero_volumes": zeros}
    finally:
        engine.dispose()
    client = AniListAuditClient(cache_path=args.cache, offline=args.offline) if args.anilist or args.offline else None
    try:
        enriched = []
        for row in rows:
            item = evidence.get(str(row["volume_id"]), {})
            data = client.lookup(series_id=row["series_id"], title=row["series_title"],
                original_title=row["original_title"], publisher=row["publisher"],
                alternatives=item.get("alternative_titles", [])) if client else {
                    "match_confidence": "NOT_FOUND", "metadata": None, "candidates": [],
                    "error": "anilist_disabled", "cache_status": "disabled"}
            enriched.append(enrich_plan(row, data, item))
        report.update(candidates=enriched, summary=summarize(enriched))
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
