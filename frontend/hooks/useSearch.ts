"use client";

/** Debounced, one-request catalog search. Prices are prepared in the DB. */

import { useEffect, useState } from "react";
import { searchSeries } from "@/services/catalog";
import type { SearchResponse, SeriesSummary, VolumeHit } from "@/types";

export type SearchStatus = "idle" | "loading" | "success" | "error";

export interface UseSearchResult {
  status: SearchStatus;
  results: SeriesSummary[];
  /** Single volumes for a "<series> <number>" query. */
  volumes: VolumeHit[];
  error: string | null;
  isEmpty: boolean;
}

const MIN_QUERY_LENGTH = 2;

interface SearchState {
  key: string;
  status: "loading" | "success" | "error";
  results: SeriesSummary[];
  volumes: VolumeHit[];
  error: string | null;
}

export function useSearch(query: string, debounceMs = 300): UseSearchResult {
  const [searched, setSearched] = useState<SearchState | null>(null);
  const trimmed = query.trim();
  const active = trimmed.length >= MIN_QUERY_LENGTH;

  useEffect(() => {
    if (trimmed.length < MIN_QUERY_LENGTH) return;
    let cancelled = false;

    const timer = setTimeout(async () => {
      try {
        const data = await searchSeries(trimmed);
        if (cancelled) return;
        const raw = data as Partial<SearchResponse>;
        setSearched({
          key: trimmed,
          status: "success",
          results: Array.isArray(raw.results) ? raw.results : [],
          volumes: Array.isArray(raw.volumes) ? raw.volumes : [],
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setSearched({
          key: trimmed,
          status: "error",
          results: [],
          volumes: [],
          error: error instanceof Error ? error.message : "Arama başarısız",
        });
      }
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [trimmed, debounceMs]);

  if (!active) {
    return { status: "idle", results: [], volumes: [], error: null, isEmpty: false };
  }
  const current = searched && searched.key === trimmed ? searched : null;
  if (!current) {
    return { status: "loading", results: [], volumes: [], error: null, isEmpty: false };
  }
  return {
    status: current.status,
    results: current.results,
    volumes: current.volumes,
    error: current.error,
    isEmpty: current.status === "success" && current.results.length === 0 && current.volumes.length === 0,
  };
}
