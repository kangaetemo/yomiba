"use client";

/**
 * SearchSection: search box + result list with loading / error / empty
 * states. Owns the query state; data fetching lives in useSearch.
 *
 * Background-import aware:
 * - results + refreshing  -> small non-intrusive banner above the grid
 * - no results            -> honest "not in catalog" empty state. With the
 *   catalog-only policy the API never schedules an import for a query the
 *   catalog doesn't match, so a search can never end in a dead-end wait.
 *   (The legacy "importing" / "failed" empty states are kept defensively.)
 */

import { SearchBar } from "@/components/SearchBar";
import { SeriesCard } from "@/components/SeriesCard";
import { ResultsSkeleton } from "@/components/LoadingSkeleton";
import { useSearch } from "@/hooks/useSearch";
import { useState } from "react";

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-neutral-600 border-t-orange-500"
    />
  );
}

export function SearchSection() {
  const [query, setQuery] = useState("");
  const { status, results, error, isEmpty, importStatus } = useSearch(query);

  const isImporting = importStatus?.state === "importing";
  const isRefreshing = importStatus?.state === "refreshing";
  const isFailed = importStatus?.state === "failed";

  return (
    <section className="space-y-6">
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={() => {
          /* The debounced search already tracks typing; submit is a UX affordance. */
        }}
        loading={status === "loading"}
      />

      {status === "idle" && (
        <p className="text-sm text-neutral-500">
          Mağazalar arası fiyat karşılaştırmak için yazmaya başlayın.
        </p>
      )}

      {status === "loading" && results.length === 0 && <ResultsSkeleton />}

      {status === "error" && (
        <div className="rounded-xl border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
          <p className="font-medium">Arama başarısız</p>
          <p className="mt-1 text-red-400/80">{error}</p>
        </div>
      )}

      {isEmpty && (
        <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-8 text-center">
          {isImporting ? (
            <>
              <div className="flex items-center justify-center gap-3">
                <Spinner />
                <p className="font-medium text-neutral-200">
                  Katalog hazırlanıyor…
                </p>
              </div>
              <p className="mt-2 text-sm text-neutral-500">
                “{query.trim()}” için mağazalar taranıyor. Bu birkaç saniye
                sürebilir — sonuçlar hazır olduğunda otomatik görünecek.
              </p>
            </>
          ) : isFailed ? (
            <>
              <p className="text-3xl" aria-hidden>
                ⚠️
              </p>
              <p className="mt-2 font-medium text-neutral-200">
                Şu an sonuç bulunamadı
              </p>
              <p className="mt-1 text-sm text-neutral-500">
                Katalog güncellenemedi. Lütfen birazdan tekrar deneyin.
              </p>
            </>
          ) : (
            <>
              <p className="text-3xl" aria-hidden>
                🔍
              </p>
              <p className="mt-2 font-medium text-neutral-200">
                “{query.trim()}” katalogda bulunamadı
              </p>
              <p className="mt-1 text-sm text-neutral-500">
                Katalog yalnızca mangakol.com’dan beslenir ve her 12 saatte
                bir güncellenir — yeni seriler bir sonraki senkronda eklenir.
                Farklı bir başlık deneyin — örn. “Berserk”, “One Piece”,
                “Jujutsu Kaisen”.
              </p>
            </>
          )}
        </div>
      )}

      {results.length > 0 && status !== "error" && status !== "idle" && (
        <>
          {isRefreshing && (
            <div className="flex items-center gap-2.5 rounded-xl border border-neutral-800 bg-neutral-900/60 px-4 py-2.5 text-sm text-neutral-400">
              <Spinner />
              <span>
                Katalog güncelleniyor — en yeni fiyatlar birazdan burada
                olacak.
              </span>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            {results.map((series) => (
              <SeriesCard key={series.id} series={series} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
