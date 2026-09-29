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
      className={`flex flex-col gap-3 rounded-xl border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between ${
        isCheapest
          ? "border-accent/70 ring-1 ring-accent/40"
          : "border-line"
      } ${outOfStock ? "opacity-70" : ""}`}
    >
      <div className="flex items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-ink">{listing.store}</p>
            {isCheapest && (
              <span className="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent">
                En düşük fiyat
              </span>
            )}
          </div>
          <p
            className={`text-xs ${
              !listing.stock
                ? "text-bad"
                : listing.stale
                  ? "text-muted"
                  : "text-ok"
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
              ? "border border-line-strong text-muted hover:bg-surface-2"
              : "bg-accent text-on-accent hover:bg-accent-hover"
          }`}
          >
            Mağazaya git ↗
          </a>
      </div>
    </div>
  );
}
