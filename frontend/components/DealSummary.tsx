import { Badge, formatTL } from "@/components/ui";
import type { PriceDeal } from "@/types";

/** One wording for the home shelf, price table and volume summary. */
export function DealSummary({ deal }: { deal: PriceDeal }) {
  const saving = deal.saving ?? Math.max(0, Number(deal.old_price) - Number(deal.new_price));
  if (saving <= 0) return null;
  const usual = deal.reference_kind === "usual";
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="deal">{formatTL(saving)} ucuzladı</Badge>
        {usual && deal.significant && <Badge tone="lowest">%{deal.drop_pct.toLocaleString("tr-TR")} daha uygun</Badge>}
      </div>
      <p className="text-xs leading-relaxed text-muted">
        {usual ? "Son 30 gündeki gözlemlerimizde tipik en düşük fiyat" : "Önceki gözlemimizde en düşük fiyat"}
        {" "}{formatTL(deal.old_price)}.
      </p>
    </div>
  );
}
