/**
 * StoreListingCard: one store's offer on the volume page.
 * Server-Component safe (plain anchors, no client state).
 */

import type { VolumeStore } from "@/types";
import { PriceBadge } from "@/components/PriceBadge";

export function StoreListingCard({
  listing,
  isCheapest,
}: {
  listing: VolumeStore;
  isCheapest: boolean;
}) {
  // A stale listing's "in stock" flag is only the last known value: the
  // store stopped showing the product (often because it sold out).
  const outOfStock = !listing.stock || listing.stale;
  const stockLabel = !listing.stock
    ? "Stokta yok"
    : listing.stale
      ? "Stok belirsiz · mağazada artık görünmüyor"
      : "Stokta var";
  return (
    <div
      className={`flex flex-col gap-3 rounded-xl border bg-neutral-900 p-4 sm:flex-row sm:items-center sm:justify-between ${
        isCheapest
          ? "border-orange-500/70 ring-1 ring-orange-500/40"
          : "border-neutral-800"
      } ${outOfStock ? "opacity-70" : ""}`}
    >
      <div className="flex items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-neutral-50">{listing.store}</p>
            {isCheapest && (
              <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-xs font-medium text-orange-400">
                En düşük fiyat
              </span>
            )}
          </div>
          <p
            className={`text-xs ${
              !listing.stock
                ? "text-red-400"
                : listing.stale
                  ? "text-neutral-400"
                  : "text-emerald-400"
            }`}
          >
            {stockLabel}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 sm:justify-end">
        <PriceBadge
          price={listing.price}
          currency={listing.currency}
          size="lg"
          className={
            !listing.stock ? "line-through opacity-60" : listing.stale ? "opacity-60" : ""
          }
        />
        <a
          href={listing.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            outOfStock
              ? "border border-neutral-700 text-neutral-400 hover:bg-neutral-800"
              : "bg-orange-500 text-neutral-950 hover:bg-orange-400"
          }`}
          >
            Mağazaya git ↗
          </a>
      </div>
    </div>
  );
}
