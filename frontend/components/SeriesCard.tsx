/**
 * SeriesCard: a search result linking to /series/[id].
 * Server-Component safe.
 */

import Link from "next/link";
import { Cover } from "@/components/ui";
import type { SeriesSummary } from "@/types";

export function SeriesCard({ series }: { series: SeriesSummary }) {
  return (
    <Link
      href={`/series/${series.id}`}
      className="group flex items-center gap-4 rounded-xl border border-line bg-surface p-3 shadow-card transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-lift"
    >
      <Cover url={series.cover_url} alt={series.title} className="w-14" />
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-[1.05rem] font-semibold text-ink group-hover:text-accent">
          {series.title}
        </h3>
        <p className="truncate text-sm text-muted">{series.publisher}</p>
        <p className="mt-1 text-xs text-faint">{series.volume_count} cilt</p>
      </div>
      <span aria-hidden className="pr-1 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-accent">
        →
      </span>
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
