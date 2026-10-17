/** EditionLinks: other editions of the same work (Soichi <-> Soichi (Bez
 * Cilt)). On the series page, and on a single volume's page, whose series
 * page only redirects to it. */

import Link from "next/link";
import { formatTL } from "@/components/ui";
import { seriesPath } from "@/lib/paths";
import type { SeriesEdition } from "@/types";

export function EditionLinks({ editions }: { editions: SeriesEdition[] }) {
  if (editions.length === 0) return null;
  return (
    <section aria-labelledby="baskilar" className="space-y-3">
      <h2 id="baskilar" className="eyebrow">
        Bu serinin başka baskıları
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2">
        {editions.map((e) => (
          <li key={e.id}>
            <Link
              href={seriesPath(e.slug)}
              className="group flex items-center justify-between gap-4 rounded-xl border border-line bg-surface px-4 py-3 shadow-card transition-colors hover:border-line-strong"
            >
              <div className="min-w-0">
                <p className="truncate font-semibold text-ink group-hover:text-accent">{e.title}</p>
                <p className="truncate text-sm text-muted">
                  {e.publisher} · {e.volume_count} cilt
                </p>
              </div>
              <div className="shrink-0 text-right text-sm">
                {e.lowest_price !== null ? (
                  <span className="tabular font-bold text-ink">
                    {formatTL(e.lowest_price)}
                    <span className="font-normal text-muted">&apos;den</span>
                  </span>
                ) : (
                  <span className="text-faint">Stokta yok</span>
                )}
                <span aria-hidden className="ml-2 text-ink-2">→</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
