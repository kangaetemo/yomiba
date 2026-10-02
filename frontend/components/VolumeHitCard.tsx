/**
 * VolumeHitCard: a search result for one specific volume ("one piece 47"),
 * linking straight to its page. Server-Component safe.
 */

import Link from "next/link";
import { Badge, Cover, formatTL } from "@/components/ui";
import { volumePath } from "@/lib/paths";
import type { VolumeHit } from "@/types";

export function VolumeHitCard({ hit, onNavigate }: { hit: VolumeHit; onNavigate?: () => void }) {
  const inStock = hit.in_stock_count > 0 && hit.best_price !== null;
  return (
    <Link
      href={volumePath(hit.series_slug, hit.number)}
      onClick={onNavigate}
      className="group grid grid-cols-[auto_1fr_auto] items-center gap-4 rounded-xl border border-line bg-surface p-4 shadow-card transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-lift"
    >
      <Cover url={hit.cover_url} alt={`${hit.series_title} Cilt ${hit.number} kapağı`} className="w-14 sm:w-16" />
      <div className="min-w-0">
        <p className="eyebrow">Cilt</p>
        <h3 className="text-lg leading-snug font-semibold text-ink group-hover:text-accent sm:text-xl">
          {hit.series_title} {hit.number}
        </h3>
        <p className="mt-0.5 truncate text-sm text-muted">
          {hit.publisher} ·{" "}
          {inStock ? `${hit.in_stock_count} mağazada stokta` : "Şu an satan mağaza yok"}
        </p>
      </div>
      <div className="text-right">
        {inStock ? (
          <p className="tabular text-xl leading-tight font-bold text-ink">{formatTL(hit.best_price as number)}</p>
        ) : (
          <Badge tone="soldout" dot>
            Stokta yok
          </Badge>
        )}
      </div>
    </Link>
  );
}
