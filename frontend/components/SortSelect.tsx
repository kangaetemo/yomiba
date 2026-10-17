"use client";

/** SortSelect: the sort order as one native select (compact on phones); each
 * option is a URL, so choosing one navigates like the old sort links did. */

import { useRouter } from "next/navigation";

export function SortSelect({
  options,
  active,
}: {
  options: { key: string; label: string; href: string }[];
  active: string;
}) {
  const router = useRouter();
  return (
    <label className="relative inline-flex">
      <span className="sr-only">Sırala</span>
      <select
        value={active}
        onChange={(e) => {
          const next = options.find((o) => o.key === e.target.value);
          if (next) router.push(next.href, { scroll: false });
        }}
        className="min-h-10 appearance-none rounded-lg border border-line bg-surface pr-9 pl-3 text-sm font-semibold text-ink-2 transition-colors hover:border-line-strong focus-visible:border-accent"
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
      <svg aria-hidden viewBox="0 0 24 24" className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </label>
  );
}
