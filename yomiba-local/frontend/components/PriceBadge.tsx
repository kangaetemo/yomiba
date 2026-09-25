/**
 * PriceBadge: consistent price typography.
 *
 * Pure presentational component (Server-Component safe).
 */

export function formatPrice(price: number | null, currency = "TRY"): string {
  if (price === null || Number.isNaN(price)) return "—";
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(price);
}

export function PriceBadge({
  price,
  currency = "TRY",
  size = "md",
  className = "",
}: {
  price: number | null;
  currency?: string;
  size?: "md" | "lg";
  className?: string;
}) {
  const base =
    price === null
      ? "text-neutral-500"
      : "font-semibold tabular-nums text-neutral-50";
  const sizeClass = size === "lg" ? "text-2xl" : "text-base";
  return (
    <span className={`${base} ${sizeClass} ${className}`}>
      {formatPrice(price, currency)}
    </span>
  );
}
