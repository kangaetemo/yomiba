/**
 * VolumeCard: one row in the series page volume grid, linking to /volume/[id].
 * Server-Component safe.
 *
 * ``best_price`` is the lowest current price across all stores, so when a
 * volume is listed at several stores the card says "from ₺X" to keep the
 * semantics unambiguous; a single-store volume shows its plain price.
 */

import Link from "next/link";
import type { CollectionStatus, SeriesVolume } from "@/types";
import { PriceBadge } from "@/components/PriceBadge";
import { volumeLabel } from "@/lib/volumeLabel";

const STATUS_CHIP: Record<CollectionStatus, string> = {
  owned: "bg-ok/10 text-ok",
  missing: "bg-bad/10 text-bad",
  wanted: "bg-accent/10 text-accent",
};

const STATUS_LABEL: Record<CollectionStatus, string> = {
  owned: "Sahibim",
  missing: "Eksik",
  wanted: "İstediğim",
};

export function VolumeCard({ volume }: { volume: SeriesVolume }) {
  const label = volumeLabel(volume.number);
  // No store has it in stock right now. If every store SAYS sold out, the
  // price is an out-of-stock price (struck through); if some listings are
  // just stale (the store stopped showing the product), stock is unknown.
  const noStock = volume.store_count > 0 && volume.in_stock_count === 0;
  const soldOut = noStock && volume.stale_count === 0;
  const stockUnknown = noStock && volume.stale_count > 0;
  const storeLabel =
    volume.store_count === 0
      ? "Henüz mağaza yok"
      : volume.in_stock_count === volume.store_count || noStock
        ? `${volume.store_count} mağaza`
        : `${volume.in_stock_count}/${volume.store_count} mağazada stokta`;

  return (
    <Link
      href={`/volume/${volume.id}`}
      className="group flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-colors hover:border-accent/60"
    >
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-medium text-ink">
          <span className="truncate">{label}</span>
          {volume.collection_status && (
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STATUS_CHIP[volume.collection_status]}`}
            >
              {volume.collection_status
                ? STATUS_LABEL[volume.collection_status]
                : ""}
            </span>
          )}
        </p>
        <p className="text-xs text-muted">{storeLabel}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {soldOut && (
          <span className="rounded bg-bad/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-bad">
            Stokta yok
          </span>
        )}
        {stockUnknown && (
          <span
            className="rounded bg-ink/5 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted"
            title="Mağaza bu ürünü son taramalarda göstermedi; tükenmiş olabilir."
          >
            Stok belirsiz
          </span>
        )}
        {!noStock && volume.in_stock_count > 1 && (
          <span className="text-xs text-muted">başlangıç</span>
        )}
        {/* A price nobody can buy right now is not shown as a price. */}
        {!noStock && <PriceBadge price={volume.best_price} />}
        <span
          aria-hidden
          className="text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
        >
          →
        </span>
      </div>
    </Link>
  );
}
