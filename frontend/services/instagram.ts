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
