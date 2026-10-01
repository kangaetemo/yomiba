/**
 * VolumeTile: a cover-first volume card for the series grid.
 *
 * Answers, in reading order: which volume, where it is cheapest, whether
 * it can be bought now, and what to do next. Server-Component safe; the
 * owned / track buttons are a small client island shown to signed-in users.
 */

import Link from "next/link";
import { volumePath } from "@/lib/paths";
import { Cover, formatTL, volumeTitle } from "@/components/ui";
import { VolumeQuickActions } from "@/components/VolumeQuickActions";
import { StockBadge, storeSummary, volumeStock } from "@/components/volumeStock";
import type { SeriesVolume } from "@/types";

export function VolumeTile({
  volume,
  seriesTitle,
  seriesSlug,
  signedIn,
}: {
  volume: SeriesVolume;
  seriesTitle: string;
  seriesSlug: string;
  signedIn: boolean;
}) {
  const href = volumePath(seriesSlug, volume.number);
  const label = volumeTitle(volume.number);
  const stock = volumeStock(volume);
  // A price nobody can buy right now is not shown as a price.
  const hasPrice = stock === "in_stock" && volume.best_price !== null;
  const priceLabel = hasPrice
    ? "En düşük fiyat"
    : stock === "none"
      ? "Fiyat bekleniyor"
      : "Şu an satışta değil";

  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card transition-shadow hover:shadow-lift">
      <Link href={href} className="group relative block px-3 pt-3" tabIndex={-1} aria-hidden>
        <Cover
          url={volume.cover_url ?? null}
          alt=""
          className={`w-full transition-transform duration-300 group-hover:-translate-y-0.5 ${
            stock === "sold_out" ? "opacity-60 grayscale-[35%]" : ""
          }`}
        />
      </Link>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="eyebrow truncate">{seriesTitle}</p>
            <Link href={href} className="text-[1.02rem] font-semibold text-ink hover:text-accent">
              {label}
            </Link>
          </div>
          {signedIn && (
            <VolumeQuickActions volumeId={volume.id} label={label} initial={volume.collection_status} />
          )}
        </div>

        <p className="text-xs text-muted">{storeSummary(volume)}</p>

        <div className="mt-auto space-y-1.5 border-t border-line pt-2">
          <div className="flex flex-wrap items-end justify-between gap-x-2 gap-y-1">
            <div className="min-w-0 whitespace-nowrap">
              <p className="text-[0.7rem] text-faint">{priceLabel}</p>
              <p className={`tabular text-lg leading-tight font-bold ${hasPrice ? "text-ink" : "text-faint"}`}>
                {hasPrice ? formatTL(volume.best_price) : "—"}
              </p>
            </div>
            <StockBadge volume={volume} />
          </div>
          {hasPrice && volume.best_store && (
            <p className="truncate text-xs text-ink-2">
              <span className="text-faint">En ucuz: </span>
              {volume.best_store}
            </p>
          )}
          <Link
            href={href}
            className="group/cta inline-flex min-h-9 items-center gap-1 text-sm font-semibold text-accent hover:text-accent-hover"
          >
            {volume.store_count > 1 ? "Fiyatları karşılaştır" : "Cildi incele"}
            <span aria-hidden className="transition-transform group-hover/cta:translate-x-0.5">→</span>
          </Link>
        </div>
      </div>
    </li>
  );
}
