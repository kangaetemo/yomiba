"use client";

/**
 * Admin: what imports changed on store listings, series → volume → store.
 * Series with a volume on sale for the first time open by default.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Badge, type BadgeTone } from "@/components/ui";
import { formatDateTime } from "@/lib/time";
import { volumeLabel } from "@/lib/volumeLabel";
import type { ChangedSeries, ListingChange } from "@/services/listingChanges";

const tl = (value: number | null) =>
  value === null ? "fiyatsız" : `${value.toLocaleString("tr-TR", { maximumFractionDigits: 2 })} TL`;
const stock = (value: boolean | null) => (value === null ? "?" : value ? "stokta" : "tükendi");

const REMOVE_REASONS: Record<string, string> = {
  foreign_edition: "yabancı baskı",
  foreign_url: "başka sitenin ürünü",
  isbn_conflict: "ISBN uyuşmuyor",
};

/** Re-renders the server page while a price refresh is running. */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}

export function ChangeLogList({ series }: { series: ChangedSeries[] }) {
  if (series.length === 0) {
    return <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-8 text-center text-sm text-muted">
      Bu dönemde bu türde değişiklik yok.
    </p>;
  }
  return <ul className="space-y-3">
    {series.map((s) => <SeriesCard key={s.id} series={s} />)}
  </ul>;
}

function SeriesCard({ series }: { series: ChangedSeries }) {
  return <li className="rounded-xl border border-line bg-surface shadow-card">
    <details open={series.first_listings > 0} className="group">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 p-4 text-sm">
        <span className="font-semibold text-ink">{series.title}</span>
        {series.first_listings > 0 && <Badge tone="new">{series.first_listings} cilt ilk kez satışta</Badge>}
        <span className="text-muted">{series.volumes.length} cilt · {series.changes} değişiklik</span>
        <span className="text-faint">· {formatDateTime(series.latest)}</span>
        <Link href={series.path} className="ml-auto text-xs text-accent underline">seri sayfası</Link>
      </summary>
      <ul className="divide-y divide-line border-t border-line">
        {series.volumes.map((v) => <li key={v.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:gap-4">
          <div className="shrink-0 sm:w-32">
            <Link href={v.path} className="font-semibold text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-accent">
              {volumeLabel(v.number)}
            </Link>
            {v.release_date && <p className="text-xs text-faint">çıkış {v.release_date}</p>}
          </div>
          <ul className="min-w-0 flex-1 space-y-1.5">
            {v.changes.map((c) => <ChangeRow key={c.id} change={c} />)}
          </ul>
        </li>)}
      </ul>
    </details>
  </li>;
}

function describe(c: ListingChange): { tone: BadgeTone; label: string; detail: string } {
  if (c.kind === "new") {
    return {
      tone: c.note === "first" ? "new" : "stock",
      label: c.note === "first" ? "İlk kez satışta" : c.note === "moved" ? "Bu cilde taşındı" : "Yeni kayıt",
      detail: `${tl(c.new_price)} · ${stock(c.new_in_stock)}`,
    };
  }
  if (c.kind === "removed") {
    const why = c.note === "moved" ? "başka cilde taşındı" : REMOVE_REASONS[c.note ?? ""] ?? c.note ?? "";
    return { tone: "soldout", label: "Kaldırıldı", detail: `${tl(c.old_price)}${why ? ` · ${why}` : ""}` };
  }
  const parts: string[] = [];
  const priceChanged = c.old_price !== c.new_price && c.new_price !== null;
  if (priceChanged) parts.push(`${tl(c.old_price)} → ${tl(c.new_price)}`);
  if (c.old_in_stock !== c.new_in_stock) parts.push(`${stock(c.old_in_stock)} → ${stock(c.new_in_stock)}`);
  if (c.note === "gone") parts.push("mağaza ürünü kaldırdı");
  if (c.note === "recheck") parts.push("ürün sayfasından");
  if (c.kind === "product") {
    return { tone: "stale", label: "Başka ürüne geçti", detail: parts.join(" · ") || tl(c.new_price) };
  }
  const cheaper = priceChanged && c.old_price !== null && c.new_price !== null && c.new_price < c.old_price;
  const tone: BadgeTone = c.old_in_stock !== c.new_in_stock
    ? (c.new_in_stock ? "stock" : "soldout")
    : cheaper ? "lowest" : "neutral";
  const label = priceChanged ? (cheaper ? "Fiyat düştü" : "Fiyat arttı") : "Stok";
  return { tone, label, detail: parts.join(" · ") };
}

function ChangeRow({ change }: { change: ListingChange }) {
  const { tone, label, detail } = describe(change);
  return <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
    <Badge tone={tone}>{label}</Badge>
    <span className="font-medium text-ink">{change.store}</span>
    <span className="text-ink-2 tabular">{detail}</span>
    <span className="text-xs text-faint">{formatDateTime(change.at)}</span>
    {change.product_url && <a href={change.product_url} target="_blank" rel="noopener noreferrer"
      className="text-xs text-accent underline">ürün</a>}
  </li>;
}
