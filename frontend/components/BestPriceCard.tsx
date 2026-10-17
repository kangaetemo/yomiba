/** BestPriceCard: the volume page's lowest in-stock price, linking down to
 * the store table. Compact: label + link on one line, price + store on the
 * next, the drop (if any) on a third. */

import { DealSummary } from "@/components/DealSummary";
import { formatTL } from "@/components/ui";
import type { PriceDeal } from "@/types";

export function BestPriceCard({
  price,
  stores,
  deal,
  alternative,
}: {
  price: number;
  stores: string[];
  deal: PriceDeal | null | undefined;
  /** The cheapest offer of the other stores, when there is one. */
  alternative: number | null;
}) {
  return (
    <a
      href="#magazalar"
      className="group block space-y-2 rounded-2xl border border-accent/25 bg-accent-soft/60 px-4 py-3.5 transition-colors hover:border-accent/50 sm:px-5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm text-accent">En düşük fiyat</p>
        <span className="text-sm font-semibold whitespace-nowrap text-ink-2 group-hover:text-accent">
          Mağazaları karşılaştır <span aria-hidden>↓</span>
        </span>
      </div>
      <p className="flex flex-wrap items-baseline gap-x-3">
        <span className="tabular font-sans text-3xl font-bold tracking-tight text-ink">{formatTL(price)}</span>
        <span className="text-sm text-muted">{stores.join(" · ")}</span>
      </p>
      {deal ? (
        <DealSummary deal={deal} />
      ) : (
        alternative !== null && (
          <p className="text-sm font-semibold text-accent">
            Diğer mağazaların en ucuz teklifinden {formatTL(alternative - price)} daha uygun
          </p>
        )
      )}
    </a>
  );
}
