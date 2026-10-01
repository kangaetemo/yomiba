/**
 * SortBar: sort chips plus an "only in stock" toggle. Plain links (state
 * lives in the URL), so it works in Server Components and can be shared.
 */

import Link from "next/link";

const chip = "inline-flex min-h-9 items-center rounded-lg border px-3 text-sm transition-colors";
const on = "border-accent bg-accent font-semibold text-on-accent";
const off = "border-line bg-surface text-ink-2 hover:border-line-strong";

export function SortBar({
  sorts,
  active,
  stockOnly,
  hrefFor,
}: {
  /** The first entry is the default order. */
  sorts: { key: string; label: string }[];
  active: string;
  stockOnly: boolean;
  /** Link to the same page with these params changed (null clears one). */
  hrefFor: (changes: { sort?: string | null; stock?: string | null }) => string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div role="group" aria-label="Sırala" className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-faint">Sırala</span>
        {sorts.map((s) => (
          <Link
            key={s.key}
            href={hrefFor({ sort: s.key === sorts[0].key ? null : s.key })}
            aria-current={s.key === active ? "true" : undefined}
            className={`${chip} ${s.key === active ? on : off}`}
          >
            {s.label}
          </Link>
        ))}
      </div>
      <Link
        href={hrefFor({ stock: stockOnly ? null : "1" })}
        aria-pressed={stockOnly}
        className={`${chip} gap-1.5 ${stockOnly ? on : off}`}
      >
        <span aria-hidden className={`size-1.5 rounded-full ${stockOnly ? "bg-current" : "bg-ok"}`} />
        Sadece stokta
      </Link>
    </div>
  );
}
