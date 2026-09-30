import Link from "next/link";
import { Cover, SectionHeading, formatTL } from "@/components/ui";
import { ShelfTabs } from "@/components/home/ShelfTabs";
import type { PopularSeries as Series } from "@/types";

/** Series shelf with two tabs: popular series (readers' collection /
 * wishlist interest first, then how widely the series is in stock) and one
 * shots (a single volume, completed in Japan and Turkey). Both lists are
 * ranked server-side, see GET /home. */
export function PopularSeries({ series, oneShots }: { series: Series[]; oneShots: Series[] }) {
  if (series.length === 0 && oneShots.length === 0) return null;
  const shelves = [
    {
      label: "Popüler",
      lead: "Okurların koleksiyonlarında ve istek listelerinde en çok yer alan, rafta en kolay bulunan seriler.",
      items: series,
    },
    {
      label: "One shot",
      lead: "Tek ciltte başlayıp biten hikâyeler: Japonya'da da Türkiye'de de tamamlanmış, tek cildi olan seriler.",
      items: oneShots,
    },
  ].filter((s) => s.items.length > 0);

  return (
    <section id="populer" aria-labelledby="populer-title" className="scroll-mt-28 space-y-6">
      <SectionHeading id="populer-title" folio="01" eyebrow="Keşfet" title="Seriler" />
      <ShelfTabs tabs={shelves.map((s) => ({ label: s.label }))}>
        {shelves.map((s) => (
          <div key={s.label} className="space-y-6">
            <p className="max-w-2xl text-sm text-muted sm:text-base">{s.lead}</p>
            <SeriesGrid series={s.items} />
          </div>
        ))}
      </ShelfTabs>
    </section>
  );
}

function SeriesGrid({ series }: { series: Series[] }) {
  return (
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
                {s.lowest_price !== null ? (
                  <span className="tabular font-semibold text-ink">
                    {formatTL(s.lowest_price)}
                    <span className="font-normal text-muted">&apos;den</span>
                  </span>
                ) : (
                  <span className="text-faint">Stokta yok</span>
                )}
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
