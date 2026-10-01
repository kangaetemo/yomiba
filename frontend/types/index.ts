/**
 * TypeScript types mirroring the Yomiba API contract
 * (see backend/app/schemas).
 */

// -- home feed (GET /home, GET /price-drops) ---------------------------------------------

export interface PopularSeries {
  id: number;
  slug: string;
  title: string;
  publisher: string;
  author: string | null;
  cover_url: string | null;
  volume_count: number;
  /** In-stock priced store offers across the series' volumes. */
  in_stock_offers: number;
  /** Lowest current in-stock price of any volume. */
  lowest_price: number | null;
}

export interface NewVolume {
  id: number;
  series_id: number;
  series_slug: string;
  series_title: string;
  publisher: string;
  number: number;
  covers_from: number | null;
  covers_to: number | null;
  cover_url: string | null;
  /** Local release date from the catalog (YYYY-MM-DD). */
  release_date: string;
  lowest_price: number | null;
  in_stock_offers: number;
}

export interface HomeFeed {
  popular_series: PopularSeries[];
  /** Single-volume series completed in Japan and Turkey (same card shape);
   * optional so an older backend without it still renders. */
  one_shots?: PopularSeries[];
  new_volumes: NewVolume[];
  stats: { series: number; stores: number; offers: number };
}

export interface PriceDrop {
  listing_id: number;
  volume_id: number;
  series_id: number;
  series_slug: string;
  series_title: string;
  volume_number: number | null;
  store_name: string;
  old_price: number | null;
  new_price: number | null;
  drop_pct: number;
  changed_at: string;
  in_stock: boolean;
  product_url: string;
  image_url: string | null;
  /** The lowest price this store listing has ever been seen at. */
  lowest_ever?: boolean;
}

export interface SeriesSummary {
  id: number;
  slug: string;
  title: string;
  publisher: string;
  cover_url: string | null;
  volume_count: number;
  /** In-stock priced store offers across the series' volumes. */
  in_stock_offers?: number;
  /** Lowest current in-stock price of any volume; null when none. */
  lowest_price?: number | null;
}

/** Legacy response envelope: DB search found matches or found none. */
export type CatalogImportState = "fresh" | "idle";

export interface CatalogImportStatus {
  state: CatalogImportState;
  detail: string | null;
  last_success_at: string | null;
}

export interface SearchResponse {
  results: SeriesSummary[];
  status: CatalogImportStatus;
}

/** Collection status for the authenticated user; null for anonymous views. */
export type CollectionStatus = "owned" | "missing" | "wanted";

export interface SeriesVolume {
  id: number;
  /** Volume number; null for unnumbered items (boxes / sets). */
  number: number | null;
  /** Cheapest current price; null when unknown. */
  best_price: number | null;
  store_count: number;
  /** Stores with the volume in stock; 0 with store_count > 0 = sold out
   * everywhere (best_price is then an out-of-stock price). */
  in_stock_count: number;
  /** Stores whose stock flag is stale (not seen lately): stock unknown. */
  stale_count: number;
  /** Store offering best_price (e.g. "Edessa Kitabevi"). */
  best_store?: string | null;
  /** Collection status; null when the volume is not tracked. */
  collection_status: CollectionStatus | null;
  cover_url?: string | null;
  /** Local release date (YYYY-MM-DD); null when unknown. */
  release_date?: string | null;
}

/** Another edition of the same work ("Soichi" <-> "Soichi (Bez Cilt)"). */
export interface SeriesEdition {
  id: number;
  slug: string;
  title: string;
  publisher: string;
  volume_count: number;
  in_stock_offers: number;
  lowest_price: number | null;
}

export interface SeriesDetail {
  id: number;
  title: string;
  publisher: string;
  slug: string;
  author?: string | null;
  cover_url: string | null;
  volumes: SeriesVolume[];
  /** Other editions of the same work; usually empty. */
  editions?: SeriesEdition[];
}

export interface VolumeStore {
  /** Listing id (admin removal). */
  id?: number | null;
  store: string;
  price: number | null;
  currency: string;
  stock: boolean;
  /** Not seen by the store's recent scrapes: `stock` may be outdated. */
  stale: boolean;
  product_url: string;
  image_url: string | null;
  last_checked: string | null;
}

export interface SeriesRef {
  id: number;
  slug: string;
  title: string;
  publisher: string;
  author?: string | null;
  illustrator?: string | null;
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
  /** Legacy unresolved store volume; its old store prices are withheld. */
  unverified?: boolean;
  /** Catalog details; null when unknown. */
  isbn?: string | null;
  page_count?: number | null;
  /** Local release date (YYYY-MM-DD). */
  release_date?: string | null;
  /** Original volumes of an omnibus book (2-in-1: 9–10). */
  covers_from?: number | null;
  covers_to?: number | null;
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
    /** Volume pages read for ISBNs / ISBNs stored / ISBNs held elsewhere. */
    isbn_pages?: number | null;
    isbns_added?: number | null;
    isbn_conflicts?: number | null;
    isbn_conflict_details?: string[];
    /** Legacy "Cilt -1" rows folded into the volume whose ISBN they held. */
    isbn_phantoms_merged?: number | null;
    errors: string[];
  } | null;
}

/** GET /catalog/foreign-editions: foreign-edition clean-up job. */
export interface ForeignEditionStatus {
  state: "idle" | "scanning" | "ready" | "applying" | "done" | "failed";
  error: string | null;
  result: { removed_listings: number; cleared_isbns: number; backup: string | null } | null;
  plan: {
    scanned: number;
    total_candidates: number;
    foreign_isbn_volumes: { volume_id: number; isbn: string; volume_number: number; series: string }[];
    listings: {
      listing_id: number;
      volume_id: number;
      series: string;
      volume_number: number;
      store: string;
      product_url: string;
      page_isbn: string | null;
      page_language: string | null;
      action: "remove" | "keep";
      why: string | null;
    }[];
  } | null;
}

/** GET /catalog/covers: self-hosted cover progress. */
export interface CoverStatus {
  enabled: boolean;
  running: boolean;
  total: number;
  stored: number;
  last: { volumes: number; downloads: number; stored: number; without_source: number; remaining: number; finished_at: string } | null;
}

/** POST /catalog/isbn-fix: known wrong-volume ISBNs, previewed or applied. */
export interface IsbnFixResult {
  mode: "dry-run" | "apply";
  applied: boolean;
  moved_listings: number;
  backup: string | null;
  cases: {
    series: string;
    isbn: string;
    from_volume: number;
    to_volume: number;
    status: "ok" | "blocked";
    reason: string | null;
    listings: {
      listing_id: number;
      store: string;
      product_url: string;
      price: number | null;
      page_isbn?: string | null;
      action?: "move" | "keep";
      why?: string;
    }[];
  }[];
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
  /** Per-store rejection counts of the last attempt ({store: {reason: n}}). */
  reasons: Record<string, Record<string, number>> | null;
}

/** GET /import/coverage/missing — a catalog series with no store listing. */
export interface MissingCoverage {
  series_id: number;
  title: string;
  publisher: string | null;
  volume_count: number;
  query: string;
  outcome: "never" | "failed" | "empty" | "unmatched" | "other_series" | "variant_no_isbn" | "variant_unsold";
  status: string | null;
  last_attempt_at: string | null;
  results_found: number;
  reasons: Record<string, Record<string, number>> | null;
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

export interface PriceRefreshStatus {
  enabled: boolean;
  interval_hours: number;
  worker_concurrency: number;
  queue_capacity: number;
  queue_size: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  pending: number;
  total_catalog_series: number;
  current_cycle_total: number;
  current_cycle_started_at: string | null;
  /** "full" = whole catalog, "unpriced" = only series without a price. */
  current_cycle_mode?: "full" | "unpriced" | null;
  last_cycle_completed_at: string | null;
  last_successful_refresh: string | null;
  next_scheduled_refresh: string | null;
}

// ---------------------------------------------------------------------------
// Signed-in user's own lists (GET /me/*)
// ---------------------------------------------------------------------------
export interface MyVolume {
  volume_id: number;
  /** 0 is a real volume; null = unknown number. */
  volume_number: number | null;
  series_id: number;
  series_slug: string;
  series_title: string;
  publisher: string;
  cover_url: string | null;
  best_price: number | null;
}

export interface MyCollectionItem extends MyVolume {
  status: CollectionStatus;
  updated_at: string;
}

export interface MyWishlistItem extends MyVolume {
  added_at: string;
}

export interface MyPriceAlert extends MyVolume {
  /** Threshold in CENTS. */
  threshold_price: number;
  is_active: boolean;
  updated_at: string;
}
