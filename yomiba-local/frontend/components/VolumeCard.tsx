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

const STATUS_CHIP: Record<CollectionStatus, string> = {
  owned: "bg-emerald-500/10 text-emerald-400",
  missing: "bg-rose-500/10 text-rose-400",
  wanted: "bg-orange-500/10 text-orange-400",
};

const STATUS_LABEL: Record<CollectionStatus, string> = {
  owned: "Sahibim",
  missing: "Eksik",
  wanted: "İstediğim",
};

export function VolumeCard({ volume }: { volume: SeriesVolume }) {
  const label = volume.number === null ? "Kutu Seti" : `Cilt ${volume.number}`;
  const storeLabel =
    volume.store_count === 0
      ? "Henüz mağaza yok"
      : `${volume.store_count} mağaza`;

  return (
    <Link
      href={`/volume/${volume.id}`}
      className="group flex items-center justify-between gap-3 rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3 transition-colors hover:border-orange-500/60"
    >
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-medium text-neutral-100">
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
        <p className="text-xs text-neutral-500">{storeLabel}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {volume.store_count > 1 && (
          <span className="text-xs text-neutral-500">başlangıç</span>
        )}
        <PriceBadge price={volume.best_price} />
        <span
          aria-hidden
          className="text-neutral-600 transition-transform group-hover:translate-x-0.5 group-hover:text-orange-400"
        >
          →
        </span>
      </div>
    </Link>
  );
}
