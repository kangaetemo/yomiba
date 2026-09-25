"use client";

/**
 * useSearch: debounced series search with loading / error / empty state.
 *
 * State updates happen only inside the (async) debounced callback; the
 * "idle" state is derived, so clearing the input needs no reset logic.
 *
 * Background-import aware: when the API reports that a background import or
 * refresh is in progress for this query, the hook re-polls on its own until
 * the catalog settles — existing results stay visible the whole time.
 */

import { useEffect, useState } from "react";
import { searchSeries } from "@/services/catalog";
import type { CatalogImportStatus, SearchResponse, SeriesSummary } from "@/types";

export type SearchStatus = "idle" | "loading" | "success" | "error";

export interface UseSearchResult {
  status: SearchStatus;
  results: SeriesSummary[];
  error: string | null;
  /** True when a search completed and found nothing. */
  isEmpty: boolean;
  /** Background import/refresh state for the current query (null: unknown). */
  importStatus: CatalogImportStatus | null;
}

const MIN_QUERY_LENGTH = 2;
/** How often to re-poll while a background import/refresh is in progress. */
const REFRESH_POLL_MS = 8000;

interface SearchState {
  key: string;
  status: "loading" | "success" | "error";
  results: SeriesSummary[];
  importStatus: CatalogImportStatus | null;
  error: string | null;
}

export function useSearch(query: string, debounceMs = 300): UseSearchResult {
  const [searched, setSearched] = useState<SearchState | null>(null);

  const trimmed = query.trim();
  const active = trimmed.length >= MIN_QUERY_LENGTH;

  useEffect(() => {
    if (trimmed.length < MIN_QUERY_LENGTH) return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const run = async () => {
      setSearched((prev) => ({
        key: trimmed,
        status: "loading",
        // Keep existing results visible while re-polling a refreshing catalog.
        results: prev && prev.key === trimmed ? prev.results : [],
        importStatus: prev && prev.key === trimmed ? prev.importStatus : null,
        error: null,
      }));
      try {
        const data = await searchSeries(trimmed);
        if (cancelled) return;
        // Defensive at the boundary: the API contract guarantees both fields,
        // but a partial/malformed 200 body (e.g. a broken proxy) must fail
        // with a clear error state, never a raw TypeError.
        const raw = data as Partial<SearchResponse>;
        const importStatus: CatalogImportStatus | null = raw.status ?? null;
        setSearched({
          key: trimmed,
          status: "success",
          results: Array.isArray(raw.results) ? raw.results : [],
          importStatus,
          error: null,
        });
        // Keep polling while the background import/refresh is in flight.
        if (
          importStatus &&
          (importStatus.state === "importing" ||
            importStatus.state === "refreshing")
        ) {
          retryTimer = setTimeout(() => {
            if (!cancelled) run();
          }, REFRESH_POLL_MS);
        }
      } catch (e) {
        if (cancelled) return;
        setSearched({
          key: trimmed,
          status: "error",
          results: [],
          importStatus: null,
          error: e instanceof Error ? e.message : "Arama başarısız",
        });
      }
    };

    const timer = setTimeout(() => {
      run();
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [trimmed, debounceMs]);

  if (!active) {
    return {
      status: "idle",
      results: [],
      error: null,
      isEmpty: false,
      importStatus: null,
    };
  }
  const current = searched && searched.key === trimmed ? searched : null;
  if (!current) {
    return {
      status: "loading",
      results: [],
      error: null,
      isEmpty: false,
      importStatus: null,
    };
  }
  return {
    status: current.status,
    results: current.results,
    error: current.error,
    isEmpty: current.status === "success" && current.results.length === 0,
    importStatus: current.importStatus,
  };
}
