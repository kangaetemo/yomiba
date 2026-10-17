/**
 * Segmented: a quiet one-of-N switch made of links (state lives in the URL).
 * The same look as the price-history range picker: a tinted track, the
 * active segment lifted on a surface. Scrolls sideways instead of wrapping
 * when a phone is too narrow.
 */

import Link from "next/link";

export function Segmented({
  label,
  items,
  current = "true",
}: {
  label: string;
  items: { key: string; href: string; active: boolean; children: React.ReactNode; ariaLabel?: string }[];
  /** aria-current value for the active segment ("page" for filters). */
  current?: "true" | "page";
}) {
  return (
    <nav aria-label={label} className="-mx-4 max-w-[calc(100%+2rem)] overflow-x-auto px-4 sm:mx-0 sm:max-w-full sm:px-0">
      <div className="inline-flex gap-0.5 rounded-lg bg-surface-2 p-0.5">
        {items.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            scroll={false}
            aria-label={item.ariaLabel}
            aria-current={item.active ? current : undefined}
            className={`inline-flex min-h-9 shrink-0 items-center justify-center rounded-md px-3 text-sm whitespace-nowrap transition-colors ${
              item.active ? "bg-surface font-semibold text-ink shadow-card" : "text-muted hover:text-ink"
            }`}
          >
            {item.children}
          </Link>
        ))}
      </div>
    </nav>
  );
}
