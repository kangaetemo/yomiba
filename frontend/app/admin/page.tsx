import type { Metadata } from "next";
import Link from "next/link";
import { AdminHeader, requireAdmin } from "@/components/admin/AdminHeader";
import { formatDateTime } from "@/lib/time";
import { getCatalogSyncStatus, getImportCoverage, getPriceRefreshStatus } from "@/services/admin";
import { getOpenReportCount } from "@/services/reports";

export const metadata: Metadata = {
  title: "Admin",
};

/** Every admin page, grouped like the menu, with one line on what it is for. */
const GROUPS: { title: string; links: { href: string; label: string; text: string }[] }[] = [
  {
    title: "Fiyatlar",
    links: [
      { href: "/admin/fiyatlar", label: "Yenileme ve kapsama", text: "Fiyat yenileme döngüsü, fiyatı olan seri oranı, fiyatsız seriler ve nedenleri." },
      { href: "/admin/degisiklikler", label: "Değişiklikler", text: "Hangi cildin hangi mağazada değiştiği: ilk kez satışa çıkanlar, fiyat ve stok değişiklikleri." },
      { href: "/admin/magazalar", label: "Mağazalar", text: "Elle içe aktarma, son içe aktarmalar ve mağaza erişim testi." },
    ],
  },
  {
    title: "Katalog",
    links: [
      { href: "/admin/katalog", label: "Senkron ve bakım", text: "Mangakol senkronu ve karşılaştırması, kapaklar, ISBN düzeltme, yabancı baskılar." },
      { href: "/admin/isbn/saglik", label: "ISBN sağlığı", text: "ISBN çelişkileri, bağlanmayan ürünler, aykırı fiyatlar ve son ISBN değişiklikleri." },
      { href: "/admin/ozel-setler", label: "Özel setler", text: "Kutulu set ve paket gibi tek bir cilde ait olmayan ürünler." },
    ],
  },
  {
    title: "Site ve paylaşım",
    links: [
      { href: "/admin/bildirimler", label: "Hata bildirimleri", text: "Ziyaretçilerin bildirdiği yanlış fiyat, stok, eşleşme ve cilt bilgileri." },
      { href: "/admin/analiz", label: "Analiz", text: "Ziyaretçiler, en çok bakılan sayfalar, mağaza tıklamaları, aramalar ve trafik kaynakları." },
      { href: "/admin/instagram", label: "Instagram", text: "Haftanın çıkanları, yeni seri, tekrar stokta ve açılış postları; görsel, video ve açıklama metni." },
    ],
  },
];

function StatusTile({ href, label, value, detail, tone = "ink" }: {
  href: string; label: string; value: string; detail: string; tone?: "ink" | "accent" | "ok" | "bad";
}) {
  const color = { ink: "text-ink", accent: "text-accent", ok: "text-ok", bad: "text-bad" }[tone];
  return (
    <Link href={href} className="block rounded-xl border border-line bg-surface p-4 transition-colors hover:bg-surface-2">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular ${color}`}>{value}</p>
      <p className="mt-1 text-xs text-muted">{detail}</p>
    </Link>
  );
}

export default async function AdminPage() {
  await requireAdmin("/admin");
  const [refresh, coverage, reports, sync] = await Promise.all([
    getPriceRefreshStatus().catch(() => null),
    getImportCoverage().catch(() => null),
    getOpenReportCount().then((r) => r.new).catch(() => null),
    getCatalogSyncStatus().catch(() => null),
  ]);

  const cycleActive = refresh?.current_cycle_started_at != null;
  const cycleTotal = refresh ? refresh.current_cycle_total || refresh.total_catalog_series : 0;
  const pct = coverage && coverage.catalog_series > 0
    ? Math.round((100 * coverage.series_with_listings) / coverage.catalog_series)
    : null;
  const problems = coverage?.problem_records?.length ?? 0;

  return (
    <div className="space-y-8">
      <AdminHeader title="Yönetim paneli">
        Sitenin durumu bir bakışta. Ayrıntı ve işlemler üstteki menüde.
      </AdminHeader>

      <section aria-label="Durum" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusTile
          href="/admin/fiyatlar"
          label="Fiyat yenileme"
          tone={cycleActive ? "accent" : refresh && !refresh.enabled ? "bad" : "ink"}
          value={!refresh ? "Bilinmiyor" : cycleActive
            ? `${refresh.completed + refresh.failed}/${cycleTotal} seri`
            : refresh.enabled ? "Beklemede" : "Kapalı"}
          detail={!refresh ? "Durum alınamadı." : cycleActive
            ? `${refresh.current_cycle_mode === "unpriced" ? "Fiyatsızlar yenileniyor" : "Çalışıyor"}, ${formatDateTime(refresh.current_cycle_started_at)} başladı.`
            : `Son bitiş ${formatDateTime(refresh.last_cycle_completed_at)}, sonraki ${formatDateTime(refresh.next_scheduled_refresh)}.`}
        />
        <StatusTile
          href="/admin/fiyatlar"
          label="Fiyatı olan seri"
          value={pct === null ? "Bilinmiyor" : `%${pct}`}
          detail={coverage
            ? `${coverage.series_with_listings}/${coverage.catalog_series} seri${problems > 0 ? `, ${problems} başarısız ya da kısmi kayıt` : ""}.`
            : "Durum alınamadı."}
        />
        <StatusTile
          href="/admin/bildirimler"
          label="Hata bildirimleri"
          tone={reports ? "accent" : "ink"}
          value={reports === null ? "Bilinmiyor" : reports ? `${reports} yeni` : "Yeni yok"}
          detail={reports ? "Bakılmayı bekleyen bildirim var." : "Bekleyen bildirim yok."}
        />
        <StatusTile
          href="/admin/katalog"
          label="Katalog senkronu"
          tone={sync?.running ? "accent" : sync?.last?.status === "failed" ? "bad" : "ink"}
          value={!sync ? "Bilinmiyor" : sync.running ? "Çalışıyor" : sync.last
            ? sync.last.status === "success" ? "Başarılı" : "Başarısız"
            : "Çalışmadı"}
          detail={sync?.last
            ? `Son senkron ${formatDateTime(sync.last.finished_at)}, ${sync.last.volumes_added} yeni cilt.`
            : "Sunucu son açıldığından beri senkron çalışmadı."}
        />
      </section>

      <div className="grid gap-6 md:grid-cols-3">
        {GROUPS.map((g) => (
          <section key={g.title} className="space-y-2">
            <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">{g.title}</h2>
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
              {g.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="block p-4 transition-colors hover:bg-surface-2">
                    <span className="font-semibold text-ink">
                      {l.label}
                      {l.href === "/admin/bildirimler" && reports ? (
                        <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-xs text-on-accent">{reports} yeni</span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-sm text-muted">{l.text}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
