/**
 * Stock state of a volume across stores, shared by the grid tile and the
 * list row so both always tell the same story. Server-Component safe.
 */

import { Badge, type BadgeTone } from "@/components/ui";
import type { SeriesVolume } from "@/types";

/** Only stores that have a volume in stock count anywhere on the site:
 * sold-out, stale ("stok belirsiz") and never-priced all read the same,
 * "Stokta yok" — a reader cannot buy it in any of those cases. */
export type VolumeStock = "in_stock" | "out_of_stock";

export function volumeStock(v: SeriesVolume): VolumeStock {
  return v.in_stock_count > 0 && v.best_price !== null ? "in_stock" : "out_of_stock";
}

const STOCK_BADGE: Record<VolumeStock, { tone: BadgeTone; label: string }> = {
  in_stock: { tone: "stock", label: "Stokta" },
  out_of_stock: { tone: "soldout", label: "Stokta yok" },
};

export function StockBadge({ volume, className = "" }: { volume: SeriesVolume; className?: string }) {
  const { tone, label } = STOCK_BADGE[volumeStock(volume)];
  return (
    <Badge tone={tone} dot className={className}>
      {label}
    </Badge>
  );
}

/** "3 mağazada stokta" — stores without stock are not counted. */
export function storeSummary(v: SeriesVolume): string {
  return volumeStock(v) === "in_stock" ? `${v.in_stock_count} mağazada stokta` : "Şu an satan mağaza yok";
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
