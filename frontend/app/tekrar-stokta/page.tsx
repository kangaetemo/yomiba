import type { Metadata } from "next";
import Link from "next/link";
import { RestockGrid } from "@/components/home/Restocks";
import { openGraph } from "@/lib/site";
import { getRestocks } from "@/services/catalog";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Tekrar stokta: yeniden satışa çıkan mangalar",
  description:
    "Türk kitapçılarında bir süre hiç bulunmayıp yeniden stoğa giren manga ciltleri ve güncel en ucuz fiyatları.",
  alternates: { canonical: "/tekrar-stokta" },
  openGraph: openGraph({
    title: "Tekrar stokta: yeniden satışa çıkan mangalar",
    description: "Türk kitapçılarında tükendikten sonra yeniden satışa çıkan manga ciltleri.",
    url: "/tekrar-stokta",
  }),
};

const PAGE_SIZE = 24;
const WINDOWS = [7, 14, 30];

export default async function RestocksPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const days = WINDOWS.includes(Number(query.days)) ? Number(query.days) : 14;
  const rawPage = Number(query.page);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? Math.min(rawPage, 100000) : 1;
  const feed = await getRestocks(days, PAGE_SIZE, (page - 1) * PAGE_SIZE).catch(() => null);
  const gap = feed?.min_gap_days ?? 7;
  const pageLink = (value: number) => `/tekrar-stokta?${new URLSearchParams({ days: String(days), page: String(value) })}`;
  return (
    <div className="space-y-8">
      <Link href="/#tekrar-stokta" className="text-sm text-muted hover:text-accent">← Ana sayfa</Link>
      <header className="space-y-3">
        <p className="eyebrow">Stok takibi</p>
        <h1 className="text-4xl font-semibold text-ink">Tekrar stokta</h1>
        <p className="max-w-2xl text-muted">
          En az {gap} gün hiçbir mağazada bulunmayıp yeniden satışa çıkan ciltler. Listede sadece şu an stokta olanlar var.
        </p>
      </header>
      <nav aria-label="Dönem" className="flex flex-wrap gap-2">
        {WINDOWS.map((value) => (
          <Link key={value} href={`/tekrar-stokta?days=${value}`} aria-current={value === days ? "page" : undefined}
            className={`inline-flex min-h-11 items-center rounded-lg border px-4 text-sm font-semibold ${value === days ? "border-ink bg-ink text-paper" : "border-line bg-surface text-ink-2 hover:border-line-strong"}`}>
            Son {value} gün
          </Link>
        ))}
      </nav>
      {!feed ? <p role="status" className="text-muted">Liste şu an yüklenemedi. Biraz sonra tekrar deneyebilirsin.</p>
        : feed.items.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
            Bu dönemde tükenip geri gelen cilt yok. Beklediğin bir cilt varsa sayfasındaki &quot;Stoğa girince haber ver&quot; düğmesine bas, geri geldiğinde e-posta atalım.
          </p>
        )
        : <><p className="text-sm text-muted">{feed.total} cilt · en yeni önce</p><RestockGrid items={feed.items} /></>}
      {feed && (page > 1 || page * PAGE_SIZE < feed.total) && (
        <nav aria-label="Sayfalar" className="flex flex-wrap items-center justify-center gap-4">
          {page > 1 && <Link href={pageLink(page - 1)} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4">← Önceki</Link>}
          <span className="text-sm text-muted">Sayfa {page}</span>
          {page * PAGE_SIZE < feed.total && <Link href={pageLink(page + 1)} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4">Sonraki →</Link>}
        </nav>
      )}
      <p className="max-w-3xl text-xs leading-relaxed text-faint">
        Fiyatı ve stoğu güncel en az bir mağaza satıyorsa cildi stokta sayıyoruz. Bir mağazanın ürünü bir gün göstermemesi gibi kısa kesintiler listeye girmez. Fiyatlara kargo dahil değil, almadan önce mağazadaki son durumu kontrol et.
      </p>
    </div>
  );
}
