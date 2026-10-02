"use client";

/** Search prepared catalog data once per query; normal loading stays local. */

import { useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { SearchBar } from "@/components/SearchBar";
import { SeriesCard } from "@/components/SeriesCard";
import { VolumeHitCard } from "@/components/VolumeHitCard";
import { ResultsSkeleton } from "@/components/LoadingSkeleton";
import { useSearch } from "@/hooks/useSearch";

export function SearchSection({
  syncUrl = false,
  autoFocus = false,
  onNavigate,
}: {
  /** Keep the query in the address bar (?q=) so Back restores the results. */
  syncUrl?: boolean;
  autoFocus?: boolean;
  /** Called when a result is chosen (the search dialog closes itself). */
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const initial = useSearchParams().get("q") ?? "";
  const [query, setQuery] = useState(syncUrl ? initial : "");
  const { status, results, volumes, error, isEmpty } = useSearch(query);

  function change(value: string) {
    setQuery(value);
    if (!syncUrl) return;
    // replaceState, not push: typing must not fill the history with entries.
    const q = value.trim();
    window.history.replaceState(null, "", q ? `${pathname}?q=${encodeURIComponent(q)}` : pathname);
  }

  return (
    <div className="space-y-4">
      <SearchBar
        value={query}
        onChange={change}
        onSubmit={() => {
          /* The debounced search already tracks typing. */
        }}
        loading={status === "loading"}
        autoFocus={autoFocus}
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
              Türkçe ya da orijinal adıyla deneyin.
            </p>
          </div>
        )}

        {status === "success" && volumes.length > 0 && (
          <div className="grid gap-3">
            {volumes.map((hit) => (
              <VolumeHitCard key={`${hit.series_slug}-${hit.number}`} hit={hit} onNavigate={onNavigate} />
            ))}
          </div>
        )}

        {status === "success" && results.length > 0 && (
          <div className="grid gap-3">
            {results.map((series) => (
              <SeriesCard key={series.id} series={series} onNavigate={onNavigate} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
