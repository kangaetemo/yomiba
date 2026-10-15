import { getJson, postJson } from "@/lib/api";

export type AuditStatus = "VERIFIED" | "CONFLICT" | "MISSING_ISBN" | "INSUFFICIENT_EVIDENCE" | "SOURCE_ERROR" | "SKIPPED_UPCOMING";
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
  run: AuditRun | null; approval_enabled: boolean;
};
export type IsbnReview = {
  volume_id: number; version: number; result_id: number; status: AuditStatus;
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
export const controlIsbnAudit = (id: number, action: "pause" | "resume") => postJson<AuditRun>(`/admin/isbn/runs/${id}/${action}`);
export const recheckIsbn = (id: number) => postJson<AuditRun>(`/admin/isbn/reviews/${id}/recheck`);
export const decideIsbn = (id: number, body: { version: number; result_id: number; action: DecisionAction; reason: string; isbn?: string }) =>
  postJson<{ id: number; old_isbn: string | null; new_isbn: string | null }>(`/admin/isbn/reviews/${id}/decisions`, body);
