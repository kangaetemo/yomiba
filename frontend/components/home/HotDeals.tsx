import { volumePath } from "@/lib/paths";
import Link from "next/link";
import { Badge, Cover, SectionHeading, formatTL } from "@/components/ui";
import { volumeLabel } from "@/lib/volumeLabel";
import type { PriceDrop } from "@/types";

function timeAgo(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "az önce";
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;
  return `${Math.round(hours / 24)} gün önce`;
}

/** Hot deals: price drops the app itself observed (price history), never a
 * store's own "discount" label. The biggest drop leads, editorial-style. */
export function HotDeals({ drops, windowDays }: { drops: PriceDrop[] | null; windowDays: number }) {
  if (drops === null) return null; // feed unreachable: hide, never break the page
  // The feed only returns in-stock drops; a sold-out deal is never shown.
  const sorted = drops.filter((d) => d.in_stock).sort((a, b) => b.drop_pct - a.drop_pct);
  const [feature, ...rest] = sorted;

  return (
    <section id="indirimler" aria-labelledby="indirimler-title" className="scroll-mt-28 space-y-6">
      <SectionHeading
        id="indirimler-title"
        folio="02"
        eyebrow="Fiyat takibi"
        title="Sıcak indirimler"
        lead={`Son ${windowDays} günde mağazalarda gözlediğimiz gerçek fiyat düşüşleri. Mağaza etiketi değil, kendi fiyat geçmişimiz.`}
      />

      {!feature ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Bu dönemde fiyat düşüşü gözlenmedi. Fiyatlar düzenli olarak kontrol edilir; düşüş olursa
          burada görünür.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
          <DealCard drop={feature} featured />
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {rest.map((d) => (
              <li key={d.listing_id} className="min-w-0">
                <DealCard drop={d} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function DealCard({ drop, featured = false }: { drop: PriceDrop; featured?: boolean }) {
  return (
    <Link
      href={volumePath(drop.series_slug, drop.volume_number)}
      className={`group flex h-full min-w-0 gap-4 rounded-xl border border-line bg-surface p-3.5 shadow-card transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-lift ${
        featured ? "items-center gap-5 p-5 lg:flex-col lg:items-start lg:justify-between" : "items-center"
      }`}
    >
      <Cover
        url={drop.image_url}
        alt=""
        className={featured ? "w-28 sm:w-36 lg:w-40" : "w-14"}
      />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="deal">%{drop.drop_pct} indirim</Badge>
          {drop.lowest_ever && <Badge tone="lowest">En düşük fiyat</Badge>}
        </div>
        <p className={`truncate font-display text-ink group-hover:text-accent ${featured ? "text-xl" : "text-base"}`}>
          {drop.series_title}
          <span className="font-sans text-sm text-muted"> · {volumeLabel(drop.volume_number)}</span>
        </p>
        <p className="flex items-baseline gap-2">
          <span className={`tabular font-semibold text-ink ${featured ? "text-2xl" : "text-lg"}`}>
            {formatTL(drop.new_price)}
          </span>
          {drop.old_price !== null && (
            <s className="tabular text-sm text-faint">{formatTL(drop.old_price)}</s>
          )}
        </p>
        <p className="truncate text-xs text-muted">
          {drop.store_name} · {timeAgo(drop.changed_at)}
        </p>
      </div>
    </Link>
  );
}
