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
        <p className="text-sm text-neutral-500">
          Mağazalar arası fiyat karşılaştırmak için yazmaya başlayın.
        </p>
      )}

      {status === "loading" && <ResultsSkeleton />}

      {status === "error" && (
        <div className="rounded-xl border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
          <p className="font-medium">Arama başarısız</p>
          <p className="mt-1 text-red-400/80">{error}</p>
        </div>
      )}

      {isEmpty && (
        <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-8 text-center">
          <p className="text-3xl" aria-hidden>🔍</p>
          <p className="mt-2 font-medium text-neutral-200">
            “{query.trim()}” katalogda bulunamadı
          </p>
          <p className="mt-1 text-sm text-neutral-500">
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
