import Link from "next/link";
import { DealSummary } from "@/components/DealSummary";
import { Cover, SectionHeading, formatTL } from "@/components/ui";
import { volumePath } from "@/lib/paths";
import { serverDate } from "@/lib/time";
import { volumeLabel } from "@/lib/volumeLabel";
import type { PriceDrop } from "@/types";

function timeAgo(iso: string): string {
  const hours = Math.max(0, Math.floor((Date.now() - serverDate(iso).getTime()) / 3_600_000));
  if (hours < 1) return "az önce";
  if (hours < 24) return `${hours} saat önce`;
  return `${Math.floor(hours / 24)} gün önce`;
}

export function HotDeals({ drops, windowDays }: { drops: PriceDrop[] | null; windowDays: number }) {
  if (drops === null) return null;
  const selected = drops.filter((d) => d.in_stock && d.significant);
  return (
    <section id="indirimler" aria-labelledby="indirimler-title" className="scroll-mt-28 space-y-6">
      <SectionHeading id="indirimler-title" folio="02" eyebrow="Fiyat takibi" title="Fiyatı düşenler"
        lead={`Son ${windowDays} günde, gözlediğimiz tipik en düşük satış fiyatının en az %20 altına inen ciltler. En yeni indirimler önce.`}
        action={{ href: "/indirimler", label: "Tüm indirimler" }} />
      {selected.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Şu an bu ölçüye uyan bir fırsat yok. Küçük düşüşleri de görmek için tüm indirimlere bakabilirsin.
        </p>
      ) : <DealGrid drops={selected} />}
    </section>
  );
}

export function DealGrid({ drops }: { drops: PriceDrop[] }) {
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {drops.map((drop) => <li key={drop.volume_id} className="min-w-0"><DealCard drop={drop} /></li>)}
    </ul>
  );
}

function DealCard({ drop }: { drop: PriceDrop }) {
  return (
    <Link href={volumePath(drop.series_slug, drop.volume_number)}
      className="group flex h-full min-w-0 items-start gap-4 rounded-xl border border-line bg-surface p-4 shadow-card transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-accent">
      <Cover url={drop.image_url} alt="" className="w-20 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2">
        <h3 className="line-clamp-2 text-base font-semibold text-ink group-hover:text-accent">{drop.series_title}</h3>
        <p className="text-sm text-muted">{volumeLabel(drop.volume_number)}</p>
        <p className="tabular text-2xl font-semibold text-ink">{formatTL(drop.new_price)}</p>
        <DealSummary deal={drop} />
        <p className="text-xs text-muted">{drop.store_name} · {timeAgo(drop.changed_at)}</p>
      </div>
    </Link>
  );
}
