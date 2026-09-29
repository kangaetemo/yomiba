"""CLI for app.services.isbn_conflict_fix (see its docstring).

The default run is read-only (it only fetches product pages). --apply must be
requested after the dry-run was reviewed. The same fix is available in the
admin panel (POST /catalog/isbn-fix) when no shell access is possible.

    python fix_isbn_conflicts.py --db /data/yomiba.db
    python fix_isbn_conflicts.py --db /data/yomiba.db --apply
    python fix_isbn_conflicts.py --db ... --case "Seri Adı|ISBN|yanlış_cilt|doğru_cilt"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from app.services.isbn_conflict_fix import page_isbn, parse_cases, run  # noqa: F401 - re-export


def main(argv: list[str] | None = None, fetch: Callable[[str], str | None] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=Path("yomiba.db"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--case", action="append", help="'Seri|ISBN|yanlış_cilt|doğru_cilt'")
    args = parser.parse_args(argv)
    db_path = args.db.resolve()
    if not db_path.is_file():
        parser.error(f"DB not found: {db_path}")
    result = run(db_path, cases=parse_cases(args.case), apply=args.apply, fetch=fetch)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.apply:
        if result["applied"]:
            print(f"Fixed, moved {result['moved_listings']} listing(s); backup: {result['backup']}")
        else:
            print("Nothing to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
