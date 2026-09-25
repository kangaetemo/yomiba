/**
 * Admin API calls: catalog sync status/trigger and store import management.
 * Same same-origin `/api` proxy as the rest of the frontend.
 */

import { getJson, postJson } from "@/lib/api";
import type {
  CatalogSyncStatus,
  ImportCoverage,
  ImportRecord,
  ImportReport,
} from "@/types";

export function getCatalogSyncStatus(): Promise<CatalogSyncStatus> {
  return getJson<CatalogSyncStatus>("/catalog/sync/status");
}

export function startCatalogSync(): Promise<{ status: string }> {
  return postJson<{ status: string }>("/catalog/sync");
}

export function runImport(query: string): Promise<ImportReport> {
  return postJson<ImportReport>("/import", { query });
}

export function getImportRecords(limit = 50): Promise<ImportRecord[]> {
  return getJson<ImportRecord[]>(`/import/records?limit=${limit}`);
}

export function getImportCoverage(): Promise<ImportCoverage> {
  return getJson<ImportCoverage>("/import/coverage");
}

/** Queue a background price import for every catalog series. Idempotent:
 * titles already importing are not re-queued. Returns the queued total. */
export function warmupCatalog(): Promise<{ total: number; queued: number }> {
  return postJson<{ total: number; queued: number }>("/import/warmup", {});
}
