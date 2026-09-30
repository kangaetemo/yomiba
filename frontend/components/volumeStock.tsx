/**
 * Stock state of a volume across stores, shared by the grid tile and the
 * list row so both always tell the same story. Server-Component safe.
 */

import { Badge, type BadgeTone } from "@/components/ui";
import type { SeriesVolume } from "@/types";

export type VolumeStock = "none" | "in_stock" | "sold_out" | "unknown";

export function volumeStock(v: SeriesVolume): VolumeStock {
  if (v.store_count === 0) return "none";
  if (v.in_stock_count > 0) return "in_stock";
  // No store has it in stock: stores that SAY sold out vs listings that
  // simply stopped showing up (stale), where stock is unknown.
  return v.stale_count > 0 ? "unknown" : "sold_out";
}

const STOCK_BADGE: Record<Exclude<VolumeStock, "none">, { tone: BadgeTone; label: string }> = {
  in_stock: { tone: "stock", label: "Stokta" },
  sold_out: { tone: "soldout", label: "Tükendi" },
  unknown: { tone: "stale", label: "Stok belirsiz" },
};

export function StockBadge({ volume, className = "" }: { volume: SeriesVolume; className?: string }) {
  const state = volumeStock(volume);
  if (state === "none") return null;
  const { tone, label } = STOCK_BADGE[state];
  return (
    <Badge tone={tone} dot className={className}>
      {label}
    </Badge>
  );
}

/** "3/4 mağazada stokta", or "4 mağaza" when every store has it. */
export function storeSummary(v: SeriesVolume): string {
  if (v.store_count === 0) return "Henüz mağaza yok";
  if (v.in_stock_count === v.store_count || v.in_stock_count === 0) {
    return `${v.store_count} mağaza`;
  }
  return `${v.in_stock_count}/${v.store_count} mağazada stokta`;
}

// -- icons ----------------------------------------------------------------------

export function BellIcon({ filled = false, className = "size-4" }: { filled?: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" fill="none" />
    </svg>
  );
}

export function CheckIcon({ className = "size-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}
