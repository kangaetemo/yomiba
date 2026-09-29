import Link from "next/link";
import { Cover, SectionHeading, formatTL } from "@/components/ui";
import type { PopularSeries as Series } from "@/types";

/** Popular series: readers' collection / wishlist interest first, then how
 * widely the series is in stock (ranked server-side, see GET /home). */
export function PopularSeries({ series }: { series: Series[] }) {
  if (series.length === 0) return null;
  return (
    <section id="populer" aria-labelledby="populer-title" className="scroll-mt-28 space-y-6">
      <SectionHeading
        id="populer-title"
        folio="01"
        eyebrow="Keşfet"
        title="Popüler seriler"
        lead="Okurların koleksiyonlarında ve istek listelerinde en çok yer alan, rafta en kolay bulunan seriler."
      />
      <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
        {series.map((s) => (
          <li key={s.id}>
            <Link href={`/series/${s.id}`} className="group block space-y-3">
              <div className="overflow-hidden rounded-[5px]">
                <Cover
                  url={s.cover_url}
                  alt={`${s.title} kapağı`}
                  className="w-full transition-transform duration-500 group-hover:scale-[1.03]"
                />
              </div>
              <div className="space-y-1">
                <h3 className="line-clamp-2 text-[1.05rem] leading-snug font-semibold text-ink group-hover:text-accent">
                  {s.title}
                </h3>
                <p className="truncate text-sm text-muted">
                  {s.publisher}
                  {s.author && <span className="text-faint"> · {s.author}</span>}
                </p>
                <div className="flex items-baseline justify-between gap-2 border-t border-line pt-2 text-sm">
                  <span className="text-faint">{s.volume_count} cilt</span>
                  {s.lowest_price !== null && (
                    <span className="tabular font-semibold text-ink">
                      {formatTL(s.lowest_price)}
                      <span className="font-normal text-muted">&apos;den</span>
                    </span>
                  )}
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
