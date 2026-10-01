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
  CoverStatus,
  ForeignEditionStatus,
  IsbnFixResult,
  MissingCoverage,
  PriceRefreshStatus,
  StoreProbeStatus,
} from "@/types";

export function getCatalogSyncStatus(): Promise<CatalogSyncStatus> {
  return getJson<CatalogSyncStatus>("/catalog/sync/status");
}

export function startCatalogSync(): Promise<{ status: string }> {
  return postJson<{ status: string }>("/catalog/sync");
}

export function getForeignEditions(): Promise<ForeignEditionStatus> {
  return getJson<ForeignEditionStatus>("/catalog/foreign-editions");
}

export function scanForeignEditions(): Promise<{ status: string }> {
  return postJson<{ status: string }>("/catalog/foreign-editions/scan", {});
}

export function applyForeignEditions(): Promise<ForeignEditionStatus["result"]> {
  return postJson<ForeignEditionStatus["result"]>("/catalog/foreign-editions/apply", {});
}

export function getCoverStatus(): Promise<CoverStatus> {
  return getJson<CoverStatus>("/catalog/covers");
}

export function startCoverFetch(): Promise<{ status: string }> {
  return postJson<{ status: string }>("/catalog/covers/fetch", {});
}

/** Preview (apply=false) or apply the known ISBN conflict fixes. */
export function runIsbnFix(apply: boolean): Promise<IsbnFixResult> {
  return postJson<IsbnFixResult>(`/catalog/isbn-fix${apply ? "?apply=true" : ""}`, {});
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

export function getMissingCoverage(limit = 200): Promise<MissingCoverage[]> {
  return getJson<MissingCoverage[]>(`/import/coverage/missing?limit=${limit}`);
}

export function getPriceRefreshStatus(): Promise<PriceRefreshStatus> {
  return getJson<PriceRefreshStatus>("/import/price-refresh/status");
}

export function startPriceRefresh(): Promise<PriceRefreshStatus> {
  return postJson<PriceRefreshStatus>("/import/price-refresh", {});
}

/** Refresh only the catalog series that have no price yet. */
export function startMissingPriceRefresh(): Promise<PriceRefreshStatus> {
  return postJson<PriceRefreshStatus>("/import/price-refresh/missing", {});
}

export function getStoreProbe(): Promise<StoreProbeStatus> {
  return getJson<StoreProbeStatus>("/catalog/store-probe");
}

export function runStoreProbe(): Promise<{ status: string }> {
  return postJson<{ status: string }>("/catalog/store-probe/run", {});
}
