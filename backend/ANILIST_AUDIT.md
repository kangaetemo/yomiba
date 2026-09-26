# AniList phantom audit

AniList is optional audit evidence, never catalog authority. Mangakol controls
catalog membership. No scraper, import runner or scheduler calls this client.
There are no migrations or new dependencies.

## Safety and interpretation

- The CLI opens SQLite with `mode=ro`, enables `query_only`, reads one snapshot,
  and closes the connection before network requests. It has no apply option.
- Only `volume_number == -1` is a candidate. Explicit zero volumes are separate
  `preserved_zero_volumes` entries with KEEP. Jujutsu Kaisen 0 is not a phantom.
- `action` is the existing planner's classification; `final_recommendation` is
  the stricter AniList-enriched recommendation. `applied` is always false.
- `expected_after_approved_plan` is the legacy planner's hypothetical count,
  not a change made by this command and not an AniList cleanup authorization.
- HIGH title confidence alone cannot produce SAFE_MERGE_CANDIDATE. It also needs
  sole catalog Volume 1, no zero, independent catalog confirmation, every listing's
  title/publisher/ISBN evidence, verified ISBN and edition with source URL, and
  no conflicts. Personal source records block the existing planner.
- No evidence file means all negative candidates remain REVIEW, even if AniList
  says ONE_SHOT. SAFE_MERGE_CANDIDATE still requires separate human approval.
- AniList describes a work, not a Turkish edition. Original multi-volume works
  can have a local omnibus; these remain REVIEW.

## Matching, signals, outages

Queries use original title, Turkish title, optional reviewed alternative titles,
and normalized title; Japanese characters are preserved by an audit-only key.
Flattened bilingual strings are not split into guessed aliases.
Exact non-generic titles score 100, generic/short exact or subtitle matches 65,
word overlap 30. A second candidate within 10 points or truncated search is
AMBIGUOUS. HIGH requires at least 90; MEDIUM at least 60. Only HIGH can support
the final candidate recommendation. This confidence concerns title identity,
not publisher/edition identity.

ONE_SHOT and volumes=1 are independent booleans. Null volumes are UNKNOWN;
volumes>1 is MULTI_VOLUME. Contradictory ONE_SHOT + multi-volume blocks promotion.
The summary format counters are signals and can overlap for contradictions.

Public GraphQL endpoint: https://graphql.anilist.co . Timeout 15 seconds, maximum
two attempts, minimum 2.1 seconds between requests, six title variants and two
pages of 50 results per variant. Retry-After/reset headers are respected; long
cooldowns fail closed. No auth, proxy or bypass. API errors produce REVIEW.

Optional JSON cache has a seven-day TTL. Its key includes series ID, publisher
and title variants. It stores fetched_at, metadata candidates and confidence;
cached candidates are re-evaluated. Stale evidence is never reused on outage.
`--offline` uses fresh cache only. Use one audit process per cache file.

## Railway isolated audit (no deployment)

Upload the supplied `yomiba-anilist-audit.tar.gz` into staging `/tmp` using the
Railway Console Files panel. This source-only bundle has no DB, secrets or env
file. Do not extract it into `/app` or `/data`. In the confirmed staging console:

```sh
test "$APP_ENV" = staging && test -f /data/yomiba-staging.db && mkdir -p /tmp/yomiba-anilist-audit && tar -xzf /tmp/yomiba-anilist-audit.tar.gz -C /tmp/yomiba-anilist-audit && /app/.venv/bin/python -B /tmp/yomiba-anilist-audit/audit_phantom_volumes.py --db /data/yomiba-staging.db --anilist --cache /tmp/yomiba-anilist-cache.json --output /tmp/yomiba-anilist-report.json
```

Summary (report contains all rows):

```sh
/app/.venv/bin/python -c "import json; r=json.load(open('/tmp/yomiba-anilist-report.json')); print(json.dumps(r['summary'],indent=2)); print('PRESERVED_ZERO',r['preserved_zero_volumes']); print('APPLIED',r['applied'])"
```

For a repeat with no network, replace `--anilist` with `--offline`. Download the
report through Console Files. Cache/report files in `/tmp` are ephemeral.

## Optional reviewed evidence

Example structure only; do not assert verification without inspecting sources.
Include every source listing and its real URL. Aliases need independent evidence.

```json
{
  "2336": {
    "target_id": 96,
    "catalog_confirmed": true,
    "alternative_titles": ["Sayonara Eri"],
    "products": [{
      "product_url": "REPLACE_WITH_ACTUAL_LISTING_URL",
      "source_url": "REPLACE_WITH_INSPECTED_EVIDENCE_URL",
      "title": "Elveda Eri",
      "publisher": "Gerekli Şeyler",
      "isbn": "9786258237559",
      "isbn_verified": false,
      "edition_verified": false,
      "conflicts": []
    }],
    "conflicts": []
  }
}
```

Add `--evidence /tmp/reviewed-evidence.json` to the audit command. False flags
above intentionally prevent promotion. A report does not authorize a merge.

## Output

Each candidate includes volume_id, series_id, series_title, original_title,
publisher, ISBN, positive_volume_count/numbers, listing_count, stores, action,
reason, nested anilist metadata (ID/titles/format/volumes/chapters/confidence),
single_volume_evidence, conflicts and final_recommendation.

Top-level summary includes total_minus_one_candidates; matched_high,
matched_medium, ambiguous, not_found; ONE_SHOT, MANGA volumes=1, multi-volume,
unknown; SAFE_MERGE_CANDIDATE, REVIEW, KEEP. Preserved zeros are counted separately.

## Verification

Targeted tests: 70 passed. Full backend: 540 passed, 41 warnings. Frontend
typecheck, lint, build passed. Build required access to Google Fonts.
Tests use temporary databases and mocked AniList fixtures. Solanin volumes=1
is a synthetic scenario, not a claim about current AniList data; volumes=2 is
also tested and remains REVIEW.

Live public lookup on 2026-09-26: Elveda Eri matched AniList 146983 with HIGH
confidence (ONE_SHOT, volumes=1, chapters=1). This does not verify its store ISBN
or authorize moving staging volume 2336. The legacy ISBN still blocks runtime
matching until a separately approved transition handles it.

## Completed staging run — 2026-09-26

The isolated command above was executed successfully against the confirmed
staging database. All 75 negative candidates were processed; no AniList API
error was recorded. Full per-candidate report is on Railway at
`/tmp/yomiba-anilist-report.json` (583.2 KB); cache is
`/tmp/yomiba-anilist-cache.json`. Download via Console Files before the ephemeral
filesystem is replaced. The browser download action did not yield a verified
local file, so no local copy of this full live report is claimed.

| Signal | Count |
| --- | ---: |
| MATCHED_HIGH | 22 |
| MATCHED_MEDIUM | 6 |
| AMBIGUOUS | 14 |
| NOT_FOUND | 33 |
| ONE_SHOT | 2 |
| MANGA volumes=1 | 13 |
| multi-volume | 8 |
| unknown | 52 |
| SAFE_MERGE_CANDIDATE | 0 |
| REVIEW | 75 |
| KEEP among negative candidates | 0 |
| Preserved real zero (separate) | 1 |

Live examples: 2336 Elveda Eri -> 146983, HIGH, ONE_SHOT/1 volume/1 chapter;
2338 Look Back -> 136807, HIGH, ONE_SHOT/1/1; 2351 Solanin -> 33731, HIGH,
MANGA/2/30. All remain REVIEW without independently reviewed listing evidence.
No candidate title containing `piece` occurred in this snapshot; One Piece
multi-volume behavior was verified with fixtures, not a live import.

The audit snapshot counted 2455 volumes, 3026 listings, 3025 history rows.
A subsequent read-only count showed 2455, 3204, 3203 respectively. The audit did
not write any database records; concurrent service writes mean this is not an
unchanging database snapshot across time. Negative and zero counts remained
75 and 1. A later approved cleanup must recheck every prerequisite in its own
protected transaction rather than act on this report blindly.
