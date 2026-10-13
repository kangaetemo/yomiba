import type { Metadata } from "next";
import Link from "next/link";
import { DealGrid } from "@/components/home/HotDeals";
import { getPriceDrops } from "@/services/catalog";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Tüm indirimler", description: "Mangalarda gözlediğimiz güncel fiyat düşüşleri." };
const PAGE_SIZE = 24;
const SORTS = { recent: "En son düşen", percent: "En yüksek oran", saving: "En çok TL ucuzlayan", price: "En düşük fiyat" } as const;
type Sort = keyof typeof SORTS;

export default async function DealsPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  const sort: Sort = typeof query.sort === "string" && Object.hasOwn(SORTS, query.sort) ? query.sort as Sort : "recent";
  const days = [7, 14, 30].includes(Number(query.days)) ? Number(query.days) : 14;
  const rawPage = Number(query.page);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? Math.min(rawPage, 100000) : 1;
  const feed = await getPriceDrops(days * 24, PAGE_SIZE, { sort, offset: (page - 1) * PAGE_SIZE }).catch(() => null);
  const pageLink = (value: number) => `/indirimler?${new URLSearchParams({ sort, days: String(days), page: String(value) })}`;
  return (
    <div className="space-y-8">
      <Link href="/#indirimler" className="text-sm text-muted hover:text-accent">← Ana sayfa</Link>
      <header className="space-y-3">
        <p className="eyebrow">Fiyat takibi</p>
        <h1 className="text-4xl font-semibold text-ink">Tüm indirimler</h1>
        <p className="max-w-2xl text-muted">Etiket fiyatına göre değil, gözlediğimiz satış fiyatlarına göre ucuzlayan ciltler. Küçük düşüşler de burada.</p>
      </header>
      <form action="/indirimler" className="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4">
        <label className="space-y-1 text-sm"><span className="block text-muted">Sırala</span>
          <select name="sort" defaultValue={sort} className="min-h-11 rounded-lg border border-line bg-paper px-3 text-ink">
            {Object.entries(SORTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm"><span className="block text-muted">Dönem</span>
          <select name="days" defaultValue={String(days)} className="min-h-11 rounded-lg border border-line bg-paper px-3 text-ink">
            {[7, 14, 30].map((value) => <option key={value} value={value}>Son {value} gün</option>)}
          </select>
        </label>
        <button className="min-h-11 rounded-lg bg-ink px-5 text-sm font-semibold text-paper hover:bg-accent">Göster</button>
      </form>
      {!feed ? <p role="status" className="text-muted">Fiyat düşüşleri şu an yüklenemedi. Biraz sonra tekrar deneyebilirsin.</p>
        : feed.drops.length === 0 ? <p className="text-muted">Bu dönemde gösterilecek fiyat düşüşü yok.</p>
        : <><p className="text-sm text-muted">{feed.total ?? feed.drops.length} cilt · yalnızca güncel ve stoktaki teklifler</p><DealGrid drops={feed.drops} /></>}
      {feed && (page > 1 || page * PAGE_SIZE < feed.total) && (
        <nav aria-label="İndirim sayfaları" className="flex flex-wrap items-center justify-center gap-4">
          {page > 1 && <Link href={pageLink(page - 1)} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4">← Önceki</Link>}
          <span className="text-sm text-muted">Sayfa {page}</span>
          {page * PAGE_SIZE < feed.total && <Link href={pageLink(page + 1)} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4">Sonraki →</Link>}
        </nav>
      )}
      <p className="max-w-3xl text-xs leading-relaxed text-faint">Tipik fiyat için son 30 gündeki fiyatların ne kadar süre gözlendiğine bakılır. En az 7 günlük geçmiş yoksa yalnızca önceki gözlemle karşılaştırılır. Fiyatlar kargo hariçtir; mağazadaki son fiyatı kontrol et.</p>
    </div>
  );
}
