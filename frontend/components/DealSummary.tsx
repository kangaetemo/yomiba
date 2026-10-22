import { Badge, formatTL } from "@/components/ui";
import type { PriceDeal } from "@/types";

/** One wording for the home shelf, price table and volume summary. */
export function DealSummary({ deal }: { deal: PriceDeal }) {
  const saving = deal.saving ?? Math.max(0, Number(deal.old_price) - Number(deal.new_price));
  // Tiny drops (a few kuruş) are tracked but not advertised.
  if (saving <= 0 || deal.noticeable === false) return null;
  const usual = deal.reference_kind === "usual";
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <Badge tone="deal">{formatTL(saving)} ucuzladı</Badge>
      {usual && deal.significant && <Badge tone="lowest">%{deal.drop_pct.toLocaleString("tr-TR")} daha uygun</Badge>}
      <span className="text-xs text-muted">
        {usual ? "30 günün tipik en düşüğü" : "önceki en düşük"} {formatTL(deal.old_price)}
      </span>
    </div>
  );
}
