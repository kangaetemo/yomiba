/**
 * Catalog service: typed API calls used by both Server Components and
 * client hooks. UI components never call fetch() directly.
 */

import { deleteJson, getJson, patchJson, postJson, putJson } from "@/lib/api";
import type {
  CollectionStatus,
  HomeFeed,
  PriceAlertState,
  PriceDrop,
  PriceHistory,
  SearchResponse,
  SeriesDetail,
  VolumeDetail,
  WishlistState,
} from "@/types";

export function getHomeFeed(): Promise<HomeFeed> {
  return getJson<HomeFeed>("/home");
}

export function getPriceDrops(hours = 168, limit = 6): Promise<{ drops: PriceDrop[] }> {
  return getJson<{ drops: PriceDrop[] }>(`/price-drops?hours=${hours}&limit=${limit}`);
}

export function searchSeries(query: string): Promise<SearchResponse> {
  return getJson<SearchResponse>(`/search?q=${encodeURIComponent(query)}`);
}

export function getSeries(id: number): Promise<SeriesDetail> {
  return getJson<SeriesDetail>(`/series/${id}`);
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
