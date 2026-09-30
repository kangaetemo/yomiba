/**
 * StoreListingCard: one store's offer in the volume page's price table.
 * Server-Component safe (plain anchors, no client state).
 */

import type { ReactNode } from "react";
import { Badge, formatTL } from "@/components/ui";
import type { VolumeStore } from "@/types";

const CHECKED = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function StoreListingCard({
  listing,
  isCheapest,
  adminAction,
}: {
  listing: VolumeStore;
  isCheapest: boolean;
  /** Admin-only control (e.g. remove a wrongly matched listing). */
  adminAction?: ReactNode;
}) {
  // A stale listing's "in stock" flag is only the last known value: the
  // store stopped showing the product (often because it sold out).
  const buyable = listing.stock && !listing.stale;
  return (
    <div
      className={`flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:gap-5 ${
        isCheapest ? "bg-accent-soft/50" : ""
      }`}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-ink">{listing.store}</p>
          {isCheapest && <Badge tone="lowest">En düşük fiyat</Badge>}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          {!listing.stock ? (
            <Badge tone="soldout" dot>
              Stokta yok
            </Badge>
          ) : listing.stale ? (
            <Badge tone="stale" dot>
              Stok belirsiz
            </Badge>
          ) : (
            <Badge tone="stock" dot>
              Stokta
            </Badge>
          )}
          {listing.last_checked && (
            <span className="text-faint">kontrol: {CHECKED.format(new Date(listing.last_checked))}</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 sm:justify-end">
        {adminAction}
        {buyable ? (
          <span className="tabular text-xl font-semibold text-ink">{formatTL(listing.price)}</span>
        ) : (
          // Not buyable now: the price is history, not an offer.
          <span className="text-right text-xs text-faint">
            son görülen fiyat
            <span className="tabular block text-sm text-muted">{formatTL(listing.price)}</span>
          </span>
        )}
        <a
          href={listing.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3.5 text-sm font-semibold transition-colors ${
            buyable
              ? "bg-ink text-paper hover:bg-accent"
              : "text-muted underline decoration-line-strong underline-offset-4 hover:text-ink"
          }`}
        >
          {buyable ? "Mağazaya git" : "Mağazada gör"}
          <span aria-hidden>↗</span>
          <span className="sr-only">({listing.store}, yeni sekmede açılır)</span>
        </a>
      </div>
    </div>
  );
}
