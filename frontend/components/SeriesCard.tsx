/**
 * SeriesCard: a clickable search result linking to /series/[id].
 * Server-Component safe.
 */

import Link from "next/link";
import type { SeriesSummary } from "@/types";

export function SeriesCard({ series }: { series: SeriesSummary }) {
  return (
    <Link
      href={`/series/${series.id}`}
      className="group flex gap-4 rounded-xl border border-line bg-surface p-4 transition-colors hover:border-accent/60 hover:bg-surface-2"
    >
      <CoverImage url={series.cover_url} alt={series.title} />
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-1">
        <h3 className="truncate text-base font-semibold text-ink group-hover:text-accent">
          {series.title}
        </h3>
        <p className="truncate text-sm text-muted">{series.publisher}</p>
        <p className="text-xs text-muted">
          {series.volume_count} cilt
        </p>
      </div>
      <span
        aria-hidden
        className="self-center text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
      >
        →
      </span>
    </Link>
  );
}

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
        className={`${className} flex shrink-0 items-center justify-center rounded-lg border border-line bg-surface-2 text-2xl text-faint`}
        aria-hidden
      >
        📖
      </div>
    );
  }
  return (
    // Plain <img>: covers are hot-linked from store CDNs; next/image would
    // require remotePatterns for every store domain.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={alt}
      className={`${className} shrink-0 rounded-lg border border-line object-cover`}
      loading="lazy"
    />
  );
}
