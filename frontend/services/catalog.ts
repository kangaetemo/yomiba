/**
 * Catalog service: typed API calls used by both Server Components and
 * client hooks. UI components never call fetch() directly.
 */

import { ApiError, deleteJson, getJson, patchJson, postJson, putJson } from "@/lib/api";
import type {
  CollectionStatus,
  HomeFeed,
  ReleaseCalendar,
  PopularSeries,
  PriceAlertState,
  PriceDropsFeed,
  PriceHistory,
  SearchResponse,
  SeriesDetail,
  SeriesIndexItem,
  SitemapFeed,
  VolumeDetail,
  WishlistState,
} from "@/types";

/** The broad hero pool stays on the server; only three cards reach the client. */
export function getHomeFeed(popular = 24, oneShot = 48): Promise<HomeFeed> {
  return getJson<HomeFeed>(`/home?popular=${popular}&one_shot=${oneShot}&hero=true`);
}

/** Every one shot, in-stock first (the home shelf shows a rotating handful). */
export function getAllOneShots(): Promise<{ one_shots: PopularSeries[] }> {
  return getJson<{ one_shots: PopularSeries[] }>("/one-shots");
}

/** Every catalog series with a released or announced volume (A–Z page). */
export function getSeriesIndex(): Promise<{ series: SeriesIndexItem[] }> {
  return getJson<{ series: SeriesIndexItem[] }>("/series");
}

/** Every public series page and its volume numbers (sitemap.xml). */
export function getSitemapEntries(): Promise<SitemapFeed> {
  return getJson<SitemapFeed>("/sitemap");
}

/** All dated catalog volumes in a month, including announced releases. */
export function getReleaseCalendar(month: string): Promise<ReleaseCalendar> {
  return getJson<ReleaseCalendar>(`/releases?month=${encodeURIComponent(month)}`);
}

export function getPriceDrops(
  hours = 168, limit = 6,
  options: { offset?: number; significant?: boolean; sort?: "recent" | "percent" | "saving" | "price" } = {},
): Promise<PriceDropsFeed> {
  const query = new URLSearchParams({ hours: String(hours), limit: String(limit),
    offset: String(options.offset ?? 0), significant: String(options.significant ?? false),
    sort: options.sort ?? "recent" });
  return getJson<PriceDropsFeed>(`/price-drops?${query}`).then((feed) => {
    // During a rolling deploy, an old backend must not be presented as
    // the new market-price calculation.
    if (!Array.isArray(feed.drops) || typeof feed.total !== "number"
      || feed.drops.some((drop) => drop.reference_kind !== "usual" && drop.reference_kind !== "previous")) {
      throw new ApiError(503, "Fiyat karşılaştırması güncelleniyor.");
    }
    return feed;
  });
}

export function searchSeries(query: string): Promise<SearchResponse> {
  return getJson<SearchResponse>(`/search?q=${encodeURIComponent(query)}`);
}

/** `ref` is the public slug; a numeric id (old links) resolves too. */
export function getSeries(ref: string | number): Promise<SeriesDetail> {
  return getJson<SeriesDetail>(`/series/${encodeURIComponent(String(ref))}`);
}

export function getVolume(id: number): Promise<VolumeDetail> {
  return getJson<VolumeDetail>(`/volume/${id}`);
}

export function getPriceHistory(volumeId: number): Promise<PriceHistory> {
  return getJson<PriceHistory>(`/volume/${volumeId}/price-history`);
}

/** Set (or clear with null) the collection status of a volume. */
export function setVolumeCollectionStatus(
  volumeId: number,
  status: CollectionStatus | null,
): Promise<VolumeDetail> {
  return patchJson<VolumeDetail>(`/volume/${volumeId}/collection-status`, {
    status,
  });
}

// ---------------------------------------------------------------------------
// Wishlist (independent of collection status)
// ---------------------------------------------------------------------------
export function getWishlist(volumeId: number): Promise<WishlistState> {
  return getJson<WishlistState>(`/volume/${volumeId}/wishlist`);
}

/** Idempotent: adding a volume that is already wishlisted is a no-op. */
export function addToWishlist(volumeId: number): Promise<WishlistState> {
  return postJson<WishlistState>(`/volume/${volumeId}/wishlist`);
}

/** Idempotent: removing a volume that is not wishlisted is a no-op. */
export function removeFromWishlist(volumeId: number): Promise<WishlistState> {
  return deleteJson<WishlistState>(`/volume/${volumeId}/wishlist`);
}

// ---------------------------------------------------------------------------
// Price alerts (stored condition only; no notifications in this phase)
// ---------------------------------------------------------------------------
export function getPriceAlert(volumeId: number): Promise<PriceAlertState> {
  return getJson<PriceAlertState>(`/volume/${volumeId}/price-alert`);
}

/**
 * Create or update the single per-volume alert.
 * `thresholdCents` is required when no alert exists yet; `isActive` alone
 * pauses / re-activates. Providing a threshold activates the alert.
 */
export function setPriceAlert(
  volumeId: number,
  thresholdCents: number | null,
  isActive: boolean | null = null,
): Promise<PriceAlertState> {
  const body: { threshold_price?: number; is_active?: boolean } = {};
  if (thresholdCents !== null) body.threshold_price = thresholdCents;
  if (isActive !== null) body.is_active = isActive;
  return putJson<PriceAlertState>(`/volume/${volumeId}/price-alert`, body);
}

export function deletePriceAlert(volumeId: number): Promise<PriceAlertState> {
  return deleteJson<PriceAlertState>(`/volume/${volumeId}/price-alert`);
}
