/**
 * SeriesCard: a search result linking to /series/[id].
 * Server-Component safe.
 */

import Link from "next/link";
import { Cover, formatTL } from "@/components/ui";
import { seriesPath } from "@/lib/paths";
import type { SeriesSummary } from "@/types";

export function SeriesCard({ series, onNavigate }: { series: SeriesSummary; onNavigate?: () => void }) {
  const price = series.lowest_price ?? null;
  return (
    <Link
      href={seriesPath(series.slug)}
      onClick={onNavigate}
      className="group grid grid-cols-[auto_1fr] gap-4 rounded-xl border border-line bg-surface p-4 shadow-card transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-lift sm:grid-cols-[auto_1fr_auto] sm:gap-6"
    >
      <Cover url={series.cover_url} alt={`${series.title} kapağı`} className="w-20 sm:w-24" />
      <div className="min-w-0 self-center">
        <p className="eyebrow">Seri</p>
        <h3 className="text-xl leading-snug font-semibold text-ink group-hover:text-accent sm:text-2xl">
          {series.title}
        </h3>
        <p className="mt-0.5 truncate text-sm text-muted">
          {series.publisher} · {series.volume_count} cilt
        </p>
      </div>
      <div className="col-span-2 flex items-end justify-between gap-4 border-t border-line pt-3 sm:col-span-1 sm:flex-col sm:items-start sm:justify-center sm:border-t-0 sm:border-l sm:pt-0 sm:pl-6">
        <div>
          <p className="text-xs text-faint">{price !== null ? "En düşük cilt fiyatı" : "Stokta cilt yok"}</p>
          <p className="tabular text-2xl leading-tight font-bold text-ink">{price !== null ? formatTL(price) : "—"}</p>
        </div>
        <span className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-accent px-4 text-sm font-semibold text-on-accent transition-colors group-hover:bg-accent-hover">
          Ciltleri gör <span aria-hidden>→</span>
        </span>
      </div>
    </Link>
  );
}

/** Kept for existing callers (series page); new code uses <Cover>. */
export function CoverImage({
  url,
  alt,
  className = "h-28 w-20",
}: {
  url: string | null;
  alt: string;
  className?: string;
}) {
  if (!url) {
    return (
      <div
        className={`${className} cover-art screentone flex shrink-0 items-center justify-center rounded-[5px] bg-surface-2`}
        aria-hidden
      >
        <span className="font-display text-2xl text-faint">読</span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt={alt} className={`${className} cover-art shrink-0 rounded-[5px] object-cover`} loading="lazy" />
  );
}
