import Link from "next/link";
import { formatTL } from "@/components/ui";
import { seriesHref } from "@/lib/seriesIndex";
import type { SeriesIndexItem } from "@/types";

/** Compact text rows for long series lists (no cover images). */
export function SeriesRows({ series, showPublisher = true }: { series: SeriesIndexItem[]; showPublisher?: boolean }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {series.map((s) => {
        const facts = [
          showPublisher ? s.publisher : null,
          s.author,
          s.volume_count > 0 ? `${s.volume_count} cilt` : "yakında",
        ].filter(Boolean);
        return (
          <li key={s.id}>
            <Link href={seriesHref(s)} className="group flex items-baseline justify-between gap-4 py-2.5">
              <span className="min-w-0">
                <span className="font-semibold text-ink group-hover:text-accent">{s.title}</span>
                <span className="text-sm text-muted"> · {facts.join(" · ")}</span>
              </span>
              {s.lowest_price !== null ? (
                <span className="tabular shrink-0 text-sm font-semibold text-ink">
                  {formatTL(s.lowest_price)}
                  <span className="font-normal text-muted">&apos;den</span>
                </span>
              ) : (
                <span className="shrink-0 text-sm text-faint">Stokta yok</span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
