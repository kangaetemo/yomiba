import { volumePath } from "@/lib/paths";
import Link from "next/link";
import { Badge, Cover, SectionHeading, formatDate, formatTL, volumeTitle } from "@/components/ui";
import type { NewVolume } from "@/types";

const NEW_DAYS = 14;

function isFresh(iso: string): boolean {
  const [y, m, d] = iso.split("-").map(Number);
  const days = (Date.now() - new Date(y, m - 1, d).getTime()) / 86_400_000;
  return days <= NEW_DAYS;
}

/** New volumes by their LOCAL release date from the catalog.
 * A horizontal shelf on phones, a grid from tablet up. */
export function NewVolumes({ volumes }: { volumes: NewVolume[] }) {
  if (volumes.length === 0) return null;
  return (
    <section id="yeni" aria-labelledby="yeni-title" className="scroll-mt-28 space-y-6">
      <SectionHeading
        id="yeni-title"
        folio="03"
        eyebrow="Raflarda"
        title="Yeni çıkan ciltler"
        lead="Türkiye'de en son yayımlanan ciltler, yayınevinin çıkış tarihine göre."
      />
      <ul className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 lg:grid-cols-5">
        {volumes.map((v) => (
          <li key={v.id} className="w-36 shrink-0 snap-start sm:w-auto">
            <Link href={volumePath(v.series_slug, v.number)} className="group block space-y-2.5">
              <div className="relative">
                <Cover url={v.cover_url} alt={`${v.series_title} ${volumeTitle(v.number)} kapağı`} className="w-full" />
                {isFresh(v.release_date) && (
                  <Badge tone="new" className="absolute top-2 left-2 shadow-card">
                    Yeni
                  </Badge>
                )}
              </div>
              <div className="space-y-0.5">
                <h3 className="line-clamp-2 text-[0.98rem] leading-snug font-semibold text-ink group-hover:text-accent">
                  {v.series_title}
                </h3>
                <p className="text-sm text-ink-2">{volumeTitle(v.number, v.covers_from, v.covers_to)}</p>
                <p className="truncate text-xs text-muted">{v.publisher}</p>
                <p className="flex items-baseline justify-between gap-2 pt-1 text-xs">
                  <time dateTime={v.release_date} className="text-faint">
                    {formatDate(v.release_date, true)}
                  </time>
                  {v.lowest_price !== null && (
                    <span className="tabular text-sm font-semibold text-ink">{formatTL(v.lowest_price)}</span>
                  )}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
