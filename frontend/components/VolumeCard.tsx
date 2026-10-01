/**
 * VolumeCard: one row of the series page LIST view, linking to /volume/[id].
 * Server-Component safe. The grid view uses <VolumeTile>; both share the
 * stock vocabulary from volumeStock.tsx.
 */

import Link from "next/link";
import type { CollectionStatus, SeriesVolume } from "@/types";
import { PriceBadge } from "@/components/PriceBadge";
import { volumePath } from "@/lib/paths";
import { volumeLabel } from "@/lib/volumeLabel";
import { StockBadge, storeSummary, volumeStock } from "@/components/volumeStock";

const STATUS_CHIP: Record<CollectionStatus, string> = {
  owned: "bg-ok-soft text-ok",
  missing: "bg-bad-soft text-bad",
  wanted: "bg-accent-soft text-accent",
};

const STATUS_LABEL: Record<CollectionStatus, string> = {
  owned: "Sahibim",
  missing: "Eksik",
  wanted: "Takipte",
};

export function VolumeCard({ volume, seriesSlug }: { volume: SeriesVolume; seriesSlug: string }) {
  const label = volumeLabel(volume.number);
  const stock = volumeStock(volume);
  const buyable = stock === "in_stock";

  return (
    <Link
      href={volumePath(seriesSlug, volume.number)}
      className="group flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-card transition-colors hover:border-line-strong"
    >
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-semibold text-ink">
          <span className="truncate">{label}</span>
          {volume.collection_status && (
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${STATUS_CHIP[volume.collection_status]}`}
            >
              {STATUS_LABEL[volume.collection_status]}
            </span>
          )}
        </p>
        <p className="truncate text-xs text-muted">
          {storeSummary(volume)}
          {buyable && volume.best_store ? ` · En ucuz: ${volume.best_store}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {!buyable && <StockBadge volume={volume} />}
        {/* A price nobody can buy right now is not shown as a price. */}
        {buyable && <PriceBadge price={volume.best_price} />}
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
