/**
 * TypeScript types mirroring the Yomiba API contract
 * (see backend/app/schemas).
 */

export interface SeriesSummary {
  id: number;
  title: string;
  publisher: string;
  cover_url: string | null;
  volume_count: number;
}

/**
 * Background-import state for the searched (normalized) query.
 * - fresh: data is fresh, no work in progress
 * - refreshing: results served, background refresh running
 * - importing: no results yet, background import running
 * - stale: results served, refresh not (re)started (retry window)
 * - failed: last import attempt failed
 * - idle: no results, no import in progress
 */
export type CatalogImportState =
  | "fresh"
  | "refreshing"
  | "importing"
  | "stale"
  | "failed"
  | "idle";

export interface CatalogImportStatus {
  state: CatalogImportState;
  detail: string | null;
  last_success_at: string | null;
}

export interface SearchResponse {
  results: SeriesSummary[];
  status: CatalogImportStatus;
}

/** Collection status for the single local user (no auth in scope). */
export type CollectionStatus = "owned" | "missing" | "wanted";

export interface SeriesVolume {
  id: number;
  /** Volume number; null for unnumbered items (boxes / sets). */
  number: number | null;
  /** Cheapest current price; null when unknown. */
  best_price: number | null;
  store_count: number;
  /** Collection status; null when the volume is not tracked. */
  collection_status: CollectionStatus | null;
}

export interface SeriesDetail {
  id: number;
  title: string;
  publisher: string;
  slug: string;
  cover_url: string | null;
  volumes: SeriesVolume[];
}

export interface VolumeStore {
  store: string;
  price: number | null;
  currency: string;
  stock: boolean;
  product_url: string;
  image_url: string | null;
  last_checked: string | null;
}

export interface SeriesRef {
  id: number;
  title: string;
  publisher: string;
}

export interface VolumeDetail {
  id: number;
  number: number | null;
  cover_url: string | null;
  series: SeriesRef;
  /** Sorted by price ascending; the cheapest store is first. */
  stores: VolumeStore[];
  /** Collection status; null when the volume is not tracked. */
  collection_status: CollectionStatus | null;
}

export interface WishlistState {
  volume_id: number;
  /** Whether the current user has this volume on their wishlist. */
  wishlisted: boolean;
}

export interface PriceAlert {
  id: number;
  /** Threshold in CENTS (15000 = 150 TRY). Always a positive integer. */
  threshold_price: number;
  /** Paused alerts keep their threshold but are ignored. */
  is_active: boolean;
  updated_at: string;
}

export interface PriceAlertState {
  volume_id: number;
  /** null when the volume has no alert. */
  alert: PriceAlert | null;
}

export interface PriceHistoryPoint {
  price: number;
  checked_at: string;
}

export interface PriceHistoryListing {
  listing_id: number;
  store: string;
  points: PriceHistoryPoint[];
}

export interface PriceHistory {
  volume_id: number;
  listings: PriceHistoryListing[];
}

// -- admin (import / catalog sync management) -----------------------------------

export interface CatalogSyncStatus {
  running: boolean;
  last: {
    status: "success" | "failed";
    finished_at: string | null;
    manga_total: number;
    manga_failed: number;
    series_created: number;
    series_merged: number;
    volumes_added: number;
    covers_backfilled: number;
    publishers_merged: number;
    series_absorbed: number;
    volumes_merged: number;
    errors: string[];
  } | null;
}

export interface ImportStoreResult {
  store_code: string;
  store_name: string;
  results_found: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  error: string | null;
}

export interface ImportReport {
  query: string;
  started_at: string;
  finished_at: string | null;
  stores: ImportStoreResult[];
  total_created: number;
  total_updated: number;
  total_skipped: number;
  total_errors: number;
}

export interface ImportRecord {
  normalized_query: string;
  last_query: string | null;
  status: "running" | "success" | "partial" | "failed" | "skipped";
  last_attempt_at: string | null;
  last_success_at: string | null;
  stores_ok: number;
  stores_failed: number;
  results_found: number;
  created: number;
  updated: number;
  error: string | null;
}

/** GET /import/coverage — shelf-health summary (admin panel). */
export interface ImportCoverage {
  catalog_series: number;
  series_with_listings: number;
  listings_total: number;
  records_total: number;
  records_by_status: Record<string, number>;
  fresh_records: number;
  freshness_ttl_minutes: number;
}
