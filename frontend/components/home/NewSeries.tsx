import Link from "next/link";
import { seriesPath } from "@/lib/paths";
import { Badge, Cover, SectionHeading, formatDate, formatTL } from "@/components/ui";
import type { PopularSeries as Series } from "@/types";

const NEW_DAYS = 30;

function isFresh(iso: string): boolean {
  const [y, m, d] = iso.split("-").map(Number);
  const days = (Date.now() - new Date(y, m - 1, d).getTime()) / 86_400_000;
  return days <= NEW_DAYS;
}

/** Series that started in Turkey lately, by the LOCAL release date of
 * their first volume (ranked server-side, see GET /home). */
export function NewSeries({ series }: { series: Series[] }) {
  const dated = series.filter((s): s is Series & { release_date: string } => Boolean(s.release_date));
  if (dated.length === 0) return null;
  return (
    <section id="yeni-seriler" aria-labelledby="yeni-seriler-title" className="scroll-mt-28 space-y-6">
      <SectionHeading
        id="yeni-seriler-title"
        folio="04"
        eyebrow="İlk cilt raflarda"
        title="Yeni başlayan seriler"
        lead="Türkiye'de yayımlanmaya yeni başlayan seriler, ilk cildin çıkış tarihine göre."
      />
      <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
        {dated.map((s) => (
          <li key={s.id}>
            <Link href={seriesPath(s.slug)} className="group block space-y-3">
              <div className="relative overflow-hidden rounded-[5px]">
                <Cover
                  url={s.cover_url}
                  alt={`${s.title} kapağı`}
                  className="w-full transition-transform duration-500 group-hover:scale-[1.03]"
                />
                {isFresh(s.release_date) && (
                  <Badge tone="new" className="absolute top-2 left-2 shadow-card">
                    Yeni seri
                  </Badge>
                )}
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
                  <span className="text-faint">
                    <time dateTime={s.release_date}>{formatDate(s.release_date, true)}</time>
                    {s.volume_count > 1 && <> · {s.volume_count} cilt</>}
                  </span>
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
    </section>
  );
}
