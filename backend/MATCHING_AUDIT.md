# Store product to catalog volume audit

## Verified root causes

Before this change, missing volume numbers became `-1`; a missing
`(series_id, volume_number)` created a new Volume. This explains the reported
Elveda Eri shape. No store product title/publisher snapshot is stored on
StoreListing, so its URL alone cannot prove the identity of an existing
phantom row.

The ten supplied One Piece title formats already parsed a number in all ten
cases. Nine derived `One Piece`; `One Piece Manga 1` derived `One Piece Manga`.
The 153 raw Railway products are unavailable here. Their publisher conflicts,
actual title formats and rejected fraction cannot be reconstructed from an
ImportRecord aggregate. Do not claim all failures were parser failures.

## New rules

Store imports attach to existing positive catalog volumes only. They do not
create Series, Publisher or Volume rows. Exact catalog ISBN wins over title
and publisher metadata, but cannot target a non-positive phantom. Sets and
strong non-book/alternate-edition signals are rejected.

Without exact ISBN: publisher/alias and exact normalized series identity must
match. Unknown publisher claims no longer use a cross-publisher title bridge.
The trailing generic `Manga` suffix is a secondary exact key when a volume
number exists; no fuzzy/prefix matching is used.

Missing number can match Volume 1 only when it is the sole positive volume,
the raw title matches the series, and no publisher/edition/set conflict
exists. A null ISBN can be enriched. A different stored ISBN rejects the
product; different-ISBN printing equivalence is no longer assumed. Duplicate
offers for the same proven volume still choose the cheapest price per store,
and unchanged prices create no history point.

Numeric metadata (years, ISBN fragments, prices, edition numbers) is not a
volume. The parser records evidence and keeps unrecognized numbers in the
base title. Non-positive/null volume numbers are displayed as unresolved,
never inferred to be a box set.

## Diagnostics and acceptance

Each store import summary logs result count, matched listing count, errors,
and reason counters, including publisher conflict, missing volume number,
missing volume, ambiguous volume, ISBN conflict, non-book, set and duplicate.
No DB migration is added for these diagnostics.

Tests include Elveda Eri, the ten supplied formats, and a **synthetic** 153
result set cycling across 62 known volumes. The latter expects 62 listings
and 91 duplicates. It is not the missing production/staging response replay.

## Read-only phantom audit

Use a staging snapshot with the current schema, never `backend/yomiba.db`:

```text
python audit_phantom_volumes.py --db /path/to/staging-snapshot.db
python audit_phantom_volumes.py --db /path/to/staging-snapshot.db --evidence reviewed-products.json
```

The command opens SQLite in read-only/query-only mode and has no apply option.
Without external product and Mangakol evidence, candidates remain REVIEW.
The optional JSON is keyed by source Volume ID, for example:

```json
{
  "2336": {
    "target_id": 96,
    "catalog_confirmed": true,
    "products": [
      {"product_url": "https://example.invalid/exact-stored-url", "title": "Elveda Eri", "publisher": "EXACT VERIFIED PUBLISHER", "isbn": "9786258237559"}
    ]
  }
}
```

This is a schema example, not approval or evidence for those IDs. Every
source listing URL must have verified title/publisher/ISBN evidence.
Personal source rows (collection, wishlist, alert), missing/conflicting ISBN,
multiple positive volumes, or incomplete evidence block automatic merging.

The transaction helper is exercised only by fixture tests. It retains all
PriceHistory rows, consolidates duplicate per-store listings, keeps the newer
listing snapshot, backfills only a missing target cover, preserves ISBN, and
is idempotent. It does not move personal source rows. Any future application
requires an approved dry-run and an exclusive maintenance window with imports
and catalog sync stopped. No destructive staging cleanup was run in this task.

Actual classification/counts for the reported 18 staging rows require the
staging snapshot and evidence. Positive row counts are reported separately
because the schema has no per-volume Mangakol provenance marker.
