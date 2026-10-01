import type { Metadata } from "next";
import Link from "next/link";
import { SeriesGrid } from "@/components/home/PopularSeries";
import { SortBar } from "@/components/SortBar";
import { SectionHeading } from "@/components/ui";
import { getAllOneShots } from "@/services/catalog";
import type { PopularSeries } from "@/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "One shot serileri" };

const TR = new Intl.Collator("tr");

/** Compare two optional values; missing ones always sort last. */
function byNullable<T extends number | string>(a: T | null | undefined, b: T | null | undefined, dir: 1 | -1): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return a < b ? -dir : a > b ? dir : 0;
}

type Compare = (a: PopularSeries, b: PopularSeries) => number;

/** The first entry is the default: the server's order (in stock, reader interest). */
const SORTS: { key: string; label: string; compare: Compare | null }[] = [
  { key: "one-cikan", label: "Öne çıkan", compare: null },
  { key: "az", label: "A → Z", compare: (a, b) => TR.compare(a.title, b.title) },
  { key: "za", label: "Z → A", compare: (a, b) => TR.compare(b.title, a.title) },
  { key: "fiyat", label: "Fiyat ↑", compare: (a, b) => byNullable(a.lowest_price, b.lowest_price, 1) },
  { key: "fiyat-azalan", label: "Fiyat ↓", compare: (a, b) => byNullable(a.lowest_price, b.lowest_price, -1) },
  { key: "yeni", label: "Yeni çıkan", compare: (a, b) => byNullable(a.release_date, b.release_date, -1) },
  { key: "eski", label: "İlk çıkan", compare: (a, b) => byNullable(a.release_date, b.release_date, 1) },
];

export default async function OneShotPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; stock?: string }>;
}) {
  const { sort, stock } = await searchParams;
  const active = SORTS.find((s) => s.key === sort) ?? SORTS[0];
  const stockOnly = stock === "1";

  const all = await getAllOneShots()
    .then((d) => d.one_shots)
    .catch((): PopularSeries[] | null => null);
  const shots = all && (stockOnly ? all.filter((s) => s.in_stock_offers > 0) : [...all]);
  if (shots && active.compare) shots.sort(active.compare); // stable: ties keep the default order

  const hrefFor = (changes: { sort?: string | null; stock?: string | null }) => {
    const next = new URLSearchParams();
    const current = { sort: active === SORTS[0] ? null : active.key, stock: stockOnly ? "1" : null };
    for (const [k, v] of Object.entries({ ...current, ...changes })) if (v) next.set(k, v);
    const qs = next.toString();
    return `/one-shot${qs ? `?${qs}` : ""}`;
  };

  return (
    <div className="space-y-8">
      <nav aria-label="Konum" className="text-sm text-muted">
        <Link href="/" className="hover:text-accent">
          ← Ana sayfa
        </Link>
      </nav>
      <SectionHeading
        eyebrow="Tek ciltlik hikâyeler"
        title="One shot"
        lead="Tek ciltte başlayıp biten hikâyeler: Japonya'da da Türkiye'de de tamamlanmış, tek cildi olan seriler."
      />
      <SortBar sorts={SORTS} active={active.key} stockOnly={stockOnly} hrefFor={hrefFor} />
      {shots === null ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          Liste şu an yüklenemedi. Biraz sonra tekrar dene.
        </p>
      ) : shots.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
          {stockOnly ? "Şu an stokta one shot yok." : "Henüz listelenecek one shot yok."}
        </p>
      ) : (
        <SeriesGrid series={shots} />
      )}
    </div>
  );
}
