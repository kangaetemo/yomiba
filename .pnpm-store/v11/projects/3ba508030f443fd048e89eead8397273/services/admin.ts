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
  PriceRefreshStatus,
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

export function getPriceRefreshStatus(): Promise<PriceRefreshStatus> {
  return getJson<PriceRefreshStatus>("/import/price-refresh/status");
}

export function startPriceRefresh(): Promise<PriceRefreshStatus> {
  return postJson<PriceRefreshStatus>("/import/price-refresh", {});
}
