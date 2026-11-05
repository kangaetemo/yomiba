import Link from "next/link";
import { Badge, Cover, SectionHeading, formatTL, volumeTitle } from "@/components/ui";
import { volumePath } from "@/lib/paths";
import { serverDate } from "@/lib/time";
import type { Restock } from "@/types";

function timeAgo(iso: string): string {
  const hours = Math.max(0, Math.floor((Date.now() - serverDate(iso).getTime()) / 3_600_000));
  if (hours < 1) return "az önce";
  if (hours < 24) return `${hours} saat önce`;
  return `${Math.floor(hours / 24)} gün önce`;
}

/** "3 hafta aradan sonra": how long no store had it. */
export function restockGap(outDays: number | null | undefined): string {
  if (outDays === null || outDays === undefined) return "Uzun aradan sonra";
  if (outDays < 14) return `${outDays} gün aradan sonra`;
  if (outDays < 60) return `${Math.floor(outDays / 7)} hafta aradan sonra`;
  return `${Math.floor(outDays / 30)} ay aradan sonra`;
}

export function RestockShelf({ items, windowDays, minGapDays }: {
  items: Restock[] | null; windowDays: number; minGapDays: number;
}) {
  if (items === null) return null;
  return (
    <section id="tekrar-stokta" aria-labelledby="tekrar-stokta-title" className="scroll-mt-28 space-y-6">
      <SectionHeading id="tekrar-stokta-title" folio="03" eyebrow="Stok takibi" title="Tekrar stokta"
        lead={`En az ${minGapDays} gün hiçbir mağazada bulunmayıp son ${windowDays} günde yeniden satışa çıkan ciltler.`}
        action={{ href: "/tekrar-stokta", label: "Tümünü gör" }} />
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Son {windowDays} günde tükenip geri gelen cilt olmadı. Beklediğin bir cilt varsa sayfasından stok alarmı kurabilirsin.
        </p>
      ) : <RestockGrid items={items} />}
    </section>
  );
}

export function RestockGrid({ items }: { items: Restock[] }) {
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => <li key={item.volume_id} className="min-w-0"><RestockCard item={item} /></li>)}
    </ul>
  );
}

function RestockCard({ item }: { item: Restock }) {
  const stores = item.in_stock_count > 1 ? `${item.in_stock_count} mağazada` : item.store_name;
  return (
    <Link href={volumePath(item.series_slug, item.volume_number)}
      className="group flex h-full min-w-0 items-start gap-4 rounded-xl border border-line bg-surface p-4 shadow-card transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-accent">
      <Cover url={item.cover_url} alt="" className="w-20 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2">
        <h3 className="line-clamp-2 text-base font-semibold text-ink group-hover:text-accent">{item.series_title}</h3>
        <p className="text-sm text-muted">{volumeTitle(item.volume_number, item.covers_from, item.covers_to)}</p>
        <Badge tone="stock" dot>{restockGap(item.out_days)}</Badge>
        <p className="tabular text-2xl font-semibold text-ink">{formatTL(item.price)}</p>
        <p className="text-xs text-muted">{stores ? `${stores} · ` : ""}{timeAgo(item.restocked_at)}</p>
      </div>
    </Link>
  );
}
