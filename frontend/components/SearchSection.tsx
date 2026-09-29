"use client";

/** Search prepared catalog data once per query; normal loading stays local. */

import { useState } from "react";
import { SearchBar } from "@/components/SearchBar";
import { SeriesCard } from "@/components/SeriesCard";
import { ResultsSkeleton } from "@/components/LoadingSkeleton";
import { useSearch } from "@/hooks/useSearch";

export function SearchSection() {
  const [query, setQuery] = useState("");
  const { status, results, error, isEmpty } = useSearch(query);

  return (
    <div className="space-y-4">
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={() => {
          /* The debounced search already tracks typing. */
        }}
        loading={status === "loading"}
      />

      <div aria-live="polite" className="space-y-4">
        {status === "loading" && <ResultsSkeleton />}

        {status === "error" && (
          <div className="rounded-xl border border-bad/30 bg-bad-soft p-4 text-sm text-bad">
            <p className="font-semibold">Arama başarısız</p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {isEmpty && (
          <div className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-center">
            <p className="font-display text-lg text-ink-2">“{query.trim()}” katalogda bulunamadı</p>
            <p className="mt-1 text-sm text-muted">
              Türkçe ya da orijinal adıyla deneyin; katalog Mangakol&apos;dan beslenir.
            </p>
          </div>
        )}

        {status === "success" && results.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {results.map((series) => (
              <SeriesCard key={series.id} series={series} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
