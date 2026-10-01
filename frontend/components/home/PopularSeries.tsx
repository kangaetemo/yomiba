import Link from "next/link";
import { pickRandom } from "@/lib/random";
import { seriesPath } from "@/lib/paths";
import { Cover, SectionHeading, formatTL } from "@/components/ui";
import type { PopularSeries as Series } from "@/types";

/** Home shelves: popular series (readers' collection / wishlist interest
 * first, then how widely the series is in stock) and, as a separate section
 * below, one shots (a single volume, completed in Japan and Turkey). Both
 * lists are ranked server-side, see GET /home. */
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
      <SeriesGrid series={series} />
    </section>
  );
}

const ONE_SHOT_SHELF = 8;

/** A rotating handful of one shots that are in stock somewhere (sold-out
 * ones are not shown on the home page; the full list is on /one-shot). */
export function OneShots({ series }: { series: Series[] }) {
  const buyable = series.filter((s) => s.in_stock_offers > 0 && s.lowest_price !== null);
  if (buyable.length === 0) return null;
  const shelf = pickRandom(buyable, ONE_SHOT_SHELF);
  return (
    <section id="one-shot" aria-labelledby="one-shot-title" className="scroll-mt-28 space-y-6">
      <SectionHeading
        id="one-shot-title"
        folio="04"
        eyebrow="Tek ciltlik hikâyeler"
        title="One shot"
        action={{ href: "/one-shot", label: "Tümünü göster" }}
        lead="Tek ciltte başlayıp biten hikâyeler: Japonya'da da Türkiye'de de tamamlanmış, tek cildi olan seriler."
      />
      <SeriesGrid series={shelf} />
    </section>
  );
}

export function SeriesGrid({ series }: { series: Series[] }) {
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
      {series.map((s) => (
        <li key={s.id}>
          <Link href={seriesPath(s.slug)} className="group block space-y-3">
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
