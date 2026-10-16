import { getJson, postJson } from "@/lib/api";

export type AuditStatus = "VERIFIED" | "CONFLICT" | "MISSING_ISBN" | "INSUFFICIENT_EVIDENCE" | "SOURCE_ERROR" | "SKIPPED_UPCOMING";
export type ReviewQueue = "APPROVAL" | "INVESTIGATE" | "AWAITING_EVIDENCE" | "REVIEWED";
export type IsbnSnapshot = {
  title: string; publisher: string; volume_number: number; isbn: string | null;
  release_date: string | null; catalog_released: boolean | null;
  covers_from: number | null; covers_to: number | null;
};
export type AuditRun = {
  id: number; status: string; total: number; processed: number; errors: number;
  started_at: string; finished_at: string | null; error: string | null;
};
export type IsbnSummary = {
  counts: Partial<Record<AuditStatus, number>>; pending: number; scanned: number; total: number;
  queues: Record<ReviewQueue, number>;
  run: AuditRun | null; approval_enabled: boolean;
};
export type IsbnReview = {
  volume_id: number; version: number; result_id: number; status: AuditStatus;
  queue: ReviewQueue;
  workflow: "REVIEW_PENDING" | "REVIEWED"; proposed_isbn: string | null;
  current_isbn: string | null;
  reason: string; checked_at: string; snapshot: IsbnSnapshot;
};
export type Evidence = {
  source: string; status: string; isbn: string | null; url: string | null;
  title: string | null; publisher?: string | null; language?: string | null;
  binding?: string | null; raw_isbns?: string[]; reason: string; checked_at: string;
};
export type IsbnDetail = IsbnReview & {
  evidence: Evidence[]; current: IsbnSnapshot | null; stale: boolean; approval_enabled: boolean;
  decisions: { id: number; action: string; reason: string; admin: string; old_isbn: string | null;
    new_isbn: string | null; decided_at: string; result_id: number; review_version: number }[];
};
export type DecisionAction = "KEEP" | "ACCEPT" | "MANUAL" | "DEFER";

export const getIsbnSummary = (signal?: AbortSignal) => getJson<IsbnSummary>("/admin/isbn/summary", signal);
export const getIsbnReviews = (params: URLSearchParams, signal?: AbortSignal) =>
  getJson<{ total: number; items: IsbnReview[] }>(`/admin/isbn/reviews?${params}`, signal);
export const getIsbnDetail = (id: number, signal?: AbortSignal) => getJson<IsbnDetail>(`/admin/isbn/reviews/${id}`, signal);
export const startIsbnAudit = () => postJson<AuditRun>("/admin/isbn/runs");
export const recheckIsbnConflicts = (volumeIds?: number[]) =>
  postJson<AuditRun>("/admin/isbn/runs/conflicts", volumeIds ? { volume_ids: volumeIds } : {});
export const controlIsbnAudit = (id: number, action: "pause" | "resume" | "stop") => postJson<AuditRun>(`/admin/isbn/runs/${id}/${action}`);
export const recheckIsbn = (id: number) => postJson<AuditRun>(`/admin/isbn/reviews/${id}/recheck`);
export const decideIsbn = (id: number, body: { version: number; result_id: number; action: DecisionAction; reason: string; isbn?: string }) =>
  postJson<{ id: number; old_isbn: string | null; new_isbn: string | null }>(`/admin/isbn/reviews/${id}/decisions`, body);

export type HealthVolume = {
  volume_id: number; series_id: number; series_slug: string | null; series: string;
  publisher: string | null; volume_number: number; isbn: string | null;
};
export type HealthOffer = { store: string; url: string; in_stock: boolean; price: number | null };
export type HealthRow = HealthVolume & Partial<HealthOffer> & {
  listings?: number; in_stock?: number;
  source_isbn?: string; source_url?: string; kind?: string;
  holder?: { volume_id: number; series: string | null; volume_number: number; series_slug: string | null } | null;
  url_number?: number; ratio?: number; others_median?: number;
  volume_median?: number; series_median?: number; offers?: HealthOffer[];
  problem?: string; volumes?: Partial<HealthVolume>[];
};
export type HealthCheckKey = "missing_isbn" | "deferred_catalog_isbn" | "off_by_one" | "url_volume_mismatch"
  | "listing_price_outlier" | "volume_price_outlier" | "invalid_isbn" | "shared_product";
export type IsbnHealth = {
  generated_at: string; last_sync_finished_at: string | null;
  totals: { catalog_volumes: number; released_volumes: number; released_with_isbn: number;
    released_without_isbn: number; without_isbn_but_listed: number; listings: number };
  checks: Record<HealthCheckKey, { count: number; items: HealthRow[] }>;
};

export const getIsbnHealth = (signal?: AbortSignal) => getJson<IsbnHealth>("/admin/isbn/health", signal);
