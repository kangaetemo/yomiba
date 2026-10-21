import { getJson } from "@/lib/api";

export type ChangeWindow = "cycle" | "24h" | "7d" | "30d";
export type ChangeKind = "new" | "first" | "price" | "stock" | "product" | "removed";

export type ListingChange = {
  id: number; at: string;
  kind: "new" | "update" | "product" | "removed";
  /** "first" = no other store had the volume, "recheck" = product page
   * re-check, "gone" = the store removed it, "moved", or a drop reason. */
  note: string | null;
  store: string; store_code: string;
  old_price: number | null; new_price: number | null;
  old_in_stock: boolean | null; new_in_stock: boolean | null;
  product_url: string | null;
};

export type ChangedVolume = {
  id: number; number: number | null; path: string; release_date: string | null;
  changes: ListingChange[];
};

export type ChangedSeries = {
  id: number; title: string; path: string; latest: string;
  first_listings: number; changes: number; volumes: ChangedVolume[];
};

export type ChangeLog = {
  window: ChangeWindow; since: string;
  cycle_active: boolean; cycle_started_at: string | null; cycle_completed_at: string | null;
  total: number; shown: number; truncated: boolean;
  counts: Record<ChangeKind, number>;
  stores: { code: string; name: string; count: number }[];
  series: ChangedSeries[];
  kept_since: string | null; retention_days: number;
};

export function getChangeLog(window: ChangeWindow, kind?: ChangeKind, store?: string): Promise<ChangeLog> {
  const params = new URLSearchParams({ window });
  if (kind) params.set("kind", kind);
  if (store) params.set("store", store);
  return getJson<ChangeLog>(`/import/changes?${params}`);
}
