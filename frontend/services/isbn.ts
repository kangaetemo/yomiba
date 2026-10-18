import { getJson, postJson } from "@/lib/api";

export type HealthVolume = {
  volume_id: number; series_id: number; series_slug: string | null; series: string;
  publisher: string | null; volume_number: number; isbn: string | null;
  isbn_source: string | null; catalog_isbn: string | null;
};
export type HealthVolumeRef = {
  volume_id: number; series: string; volume_number: number; series_slug: string | null; isbn: string | null;
};
export type HealthOffer = { store: string; url: string; in_stock: boolean; price: number | null };
export type HealthRow = Partial<HealthVolume> & Partial<HealthOffer> & {
  listings?: number; in_stock?: number;
  last_checked?: string | null; seen_in_search?: string | null; reasons?: string[];
  kind?: string; detail?: Record<string, unknown>;
  title?: string; title_volume?: HealthVolumeRef | null; isbn_volume?: HealthVolumeRef | null;
  ratio?: number; others_median?: number;
  volume_median?: number; series_median?: number; offers?: HealthOffer[];
  problem?: string; volumes?: Partial<HealthVolume>[];
  old_isbn?: string | null; new_isbn?: string | null; source?: string; reason?: string | null; at?: string | null;
};
export type HealthCheckKey = "search_miss" | "stale_listing" | "suspect_listing" | "isbn_issues" | "catalog_duplicate" | "title_isbn_conflict" | "catalog_differs"
  | "volume_price_outlier" | "listing_price_outlier" | "missing_isbn" | "invalid_isbn" | "shared_product"
  | "recent_changes";
export type IsbnHealth = {
  generated_at: string;
  totals: { catalog_volumes: number; released_volumes: number; released_with_isbn: number;
    released_without_isbn: number; without_isbn_but_listed: number; listings: number;
    observations: number; catalog_isbn_read: number };
  checks: Record<HealthCheckKey, { count: number; items: HealthRow[] }>;
};

export type VolumeObservation = {
  store: string | null; url: string; title: string; isbn: string | null; price: number | null;
  in_stock: boolean | null; rule: string | null; reason: string | null;
  title_volume_id: number | null; isbn_volume_id: number | null; attached_volume_id: number | null;
  title_volume: string | null; isbn_volume: string | null; attached_volume: string | null; last_seen: string;
};
export type VolumeIsbnEvidence = {
  volume_id: number; isbn: string | null; isbn_source: string | null; catalog_isbn: string | null;
  shared: string[]; votes: Record<string, number>;
  issue: { kind: string; detail: Record<string, unknown>; updated_at: string } | null;
  observations: VolumeObservation[];
  changes: { old: string | null; new: string | null; source: string; reason: string | null; at: string }[];
};
export type IsbnDecision = { isbn?: string | null; reason: string; share?: boolean; move?: boolean; automatic?: boolean };

export const getIsbnHealth = (signal?: AbortSignal) => getJson<IsbnHealth>("/admin/isbn/health", signal);
export const getVolumeIsbn = (id: number, signal?: AbortSignal) => getJson<VolumeIsbnEvidence>(`/admin/isbn/volumes/${id}`, signal);
export const decideVolumeIsbn = (id: number, body: IsbnDecision) =>
  postJson<{ volume_id: number; isbn: string | null }>(`/admin/isbn/volumes/${id}`, body);
