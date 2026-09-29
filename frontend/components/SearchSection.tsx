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
    <section className="space-y-6">
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={() => {
          /* The debounced search already tracks typing. */
        }}
        loading={status === "loading"}
      />

      {status === "idle" && (
        <p className="text-sm text-muted">
          Mağazalar arası fiyat karşılaştırmak için yazmaya başlayın.
        </p>
      )}

      {status === "loading" && <ResultsSkeleton />}

      {status === "error" && (
        <div className="rounded-xl border border-bad/30 bg-bad/5 p-4 text-sm text-bad">
          <p className="font-medium">Arama başarısız</p>
          <p className="mt-1 text-bad/80">{error}</p>
        </div>
      )}

      {isEmpty && (
        <div className="rounded-xl border border-line bg-surface p-8 text-center">
          <p className="text-3xl" aria-hidden>🔍</p>
          <p className="mt-2 font-medium text-ink-2">
            “{query.trim()}” katalogda bulunamadı
          </p>
          <p className="mt-1 text-sm text-muted">
            Katalog Mangakol’dan beslenir. Farklı bir başlık deneyin.
          </p>
        </div>
      )}

      {status === "success" && results.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {results.map((series) => (
            <SeriesCard key={series.id} series={series} />
          ))}
        </div>
      )}
    </section>
  );
}
