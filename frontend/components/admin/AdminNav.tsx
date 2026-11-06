"use client";

/**
 * AdminNav: the one menu every admin page shares (rendered by
 * app/admin/layout.tsx). Top row: the sections. Second row: the pages of
 * the active section, when it has more than one.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

type Page = { href: string; label: string; match?: string[] };
type Section = { label: string; href: string; pages?: Page[]; match?: string[]; exact?: boolean };

export const ADMIN_SECTIONS: Section[] = [
  { label: "Genel bakış", href: "/admin", exact: true },
  {
    label: "Fiyatlar",
    href: "/admin/fiyatlar",
    pages: [
      { href: "/admin/fiyatlar", label: "Yenileme ve kapsama" },
      { href: "/admin/degisiklikler", label: "Değişiklikler" },
      { href: "/admin/magazalar", label: "Mağazalar" },
    ],
  },
  {
    label: "Katalog",
    href: "/admin/katalog",
    pages: [
      { href: "/admin/katalog", label: "Senkron ve bakım" },
      { href: "/admin/isbn/saglik", label: "ISBN sağlığı", match: ["/admin/isbn"] },
      { href: "/admin/ozel-setler", label: "Özel setler" },
    ],
  },
  { label: "Bildirimler", href: "/admin/bildirimler" },
  { label: "Analiz", href: "/admin/analiz" },
  { label: "Instagram", href: "/admin/instagram" },
];

const under = (path: string, prefix: string) => path === prefix || path.startsWith(`${prefix}/`);

function pageActive(path: string, page: Page): boolean {
  return [page.href, ...(page.match ?? [])].some((p) => under(path, p));
}

function sectionActive(path: string, section: Section): boolean {
  if (section.exact) return path === section.href;
  if (section.pages) return section.pages.some((p) => pageActive(path, p));
  return under(path, section.href);
}

export function AdminNav({ openReports }: { openReports: number | null }) {
  const path = usePathname();
  const active = ADMIN_SECTIONS.find((s) => sectionActive(path, s));
  return (
    <div className="mb-6 space-y-2 border-b border-line pb-3 sm:mb-8">
      <nav aria-label="Yönetim" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {ADMIN_SECTIONS.map((s) => {
            const on = s === active;
            return (
              <li key={s.href} className="shrink-0">
                <Link
                  href={s.href}
                  aria-current={on ? "page" : undefined}
                  className={`inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-sm whitespace-nowrap transition-colors ${
                    on ? "bg-ink font-semibold text-paper" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  {s.label}
                  {s.href === "/admin/bildirimler" && openReports ? (
                    <span className="rounded-full bg-accent px-1.5 py-0.5 text-[0.7rem] leading-none font-semibold text-on-accent tabular">
                      {openReports}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {active?.pages && (
        <nav aria-label={active.label} className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <ul className="flex gap-4 text-sm">
            {active.pages.map((p) => {
              const on = pageActive(path, p);
              return (
                <li key={p.href} className="shrink-0">
                  <Link
                    href={p.href}
                    aria-current={on ? "page" : undefined}
                    className={`inline-flex min-h-9 items-center border-b-2 whitespace-nowrap transition-colors ${
                      on ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"
                    }`}
                  >
                    {p.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
