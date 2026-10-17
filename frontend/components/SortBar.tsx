/**
 * SortBar: the sort order (one select) plus an "only in stock" toggle.
 * Plain URLs (state lives in the URL), so it works in Server Components and
 * can be shared.
 */

import Link from "next/link";
import { SortSelect } from "@/components/SortSelect";

export function SortBar({
  sorts,
  active,
  stockOnly,
  hrefFor,
  children,
}: {
  /** The first entry is the default order. */
  sorts: { key: string; label: string }[];
  active: string;
  stockOnly: boolean;
  /** Link to the same page with these params changed (null clears one). */
  hrefFor: (changes: { sort?: string | null; stock?: string | null }) => string;
  /** More controls on the same row (e.g. the grid / list switch). */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SortSelect
        active={active}
        options={sorts.map((s) => ({ key: s.key, label: s.label, href: hrefFor({ sort: s.key === sorts[0].key ? null : s.key }) }))}
      />
      <Link
        href={hrefFor({ stock: stockOnly ? null : "1" })}
        scroll={false}
        aria-pressed={stockOnly}
        className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold transition-colors ${
          stockOnly ? "border-ok/40 bg-ok-soft text-ok" : "border-line bg-surface text-ink-2 hover:border-line-strong"
        }`}
      >
        <span aria-hidden className={`size-2 rounded-full ${stockOnly ? "bg-ok" : "border border-ok bg-transparent"}`} />
        Sadece stokta
      </Link>
      {children && <div className="ml-auto">{children}</div>}
    </div>
  );
}
