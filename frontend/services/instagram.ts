import { getJson } from "@/lib/api";

export type InstagramOffer = { store: string; store_code: string; price: number };

export type InstagramVolume = {
  id: number;
  series_id: number;
  series_slug: string;
  series_title: string;
  publisher: string;
  number: number;
  covers_from: number | null;
  covers_to: number | null;
  cover_url: string | null;
  release_date: string;
  lowest_price: number | null;
  in_stock_offers: number;
  /** Time-weighted reader interest of the series (wishlist + collections). */
  interest: number;
  /** Current in-stock offers, cheapest first, one per store. */
  offers: InstagramOffer[];
};

export type InstagramReleases = { start: string; end: string; generated_at: string; volumes: InstagramVolume[] };

/** Releases between two YYYY-MM-DD dates (inclusive), admin only. */
export function getInstagramReleases(start: string, end: string): Promise<InstagramReleases> {
  return getJson<InstagramReleases>(`/admin/instagram/releases?${new URLSearchParams({ start, end })}`);
}

/** A launch-post example: any catalog volume, so it may have no release date. */
export type LaunchVolume = Omit<InstagramVolume, "release_date"> & { release_date: string | null };

export type LaunchStats = { series: number; volumes: number; publishers: number; stores: number; offers: number };

export type InstagramLaunch = {
  generated_at: string;
  stats: LaunchStats;
  /** Volumes sold by three or more stores, biggest price gap first. */
  examples: LaunchVolume[];
};

/** Catalog counts and price-gap examples for the "site açıldı" post, admin only. */
export function getInstagramLaunch(): Promise<InstagramLaunch> {
  return getJson<InstagramLaunch>("/admin/instagram/launch");
}
