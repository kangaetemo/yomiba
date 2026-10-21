import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AutoRefresh, ChangeLogList } from "@/components/admin/ChangeLogList";
import { Segmented } from "@/components/Segmented";
import { formatDateTime } from "@/lib/time";
import { currentUser } from "@/services/auth";
import { getChangeLog, type ChangeKind, type ChangeWindow } from "@/services/listingChanges";

export const metadata: Metadata = { title: "Fiyat değişiklikleri" };

const WINDOWS: { key: ChangeWindow; label: string }[] = [
  { key: "cycle", label: "Son yenileme" },
  { key: "24h", label: "24 saat" },
  { key: "7d", label: "7 gün" },
  { key: "30d", label: "30 gün" },
];

const KINDS: { key: ChangeKind | "all"; label: string }[] = [
  { key: "all", label: "Tümü" },
  { key: "first", label: "İlk kez satışta" },
  { key: "new", label: "Yeni kayıt" },
  { key: "price", label: "Fiyat" },
  { key: "stock", label: "Stok" },
  { key: "product", label: "Ürün değişti" },
  { key: "removed", label: "Kaldırılan" },
];

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default async function ChangeLogPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fdegisiklikler");
  if (user.role !== "ADMIN") redirect("/");
  const query = await searchParams;
  const window = WINDOWS.find((w) => w.key === one(query.pencere))?.key ?? "cycle";
  const kind = KINDS.find((k) => k.key === one(query.tur))?.key ?? "all";
  const store = one(query.magaza) || undefined;
  const log = await getChangeLog(window, kind === "all" ? undefined : kind, store);

  const href = (next: { pencere?: string; tur?: string; magaza?: string | null }) => {
    const params = new URLSearchParams();
    const w = next.pencere ?? window;
    const k = next.tur ?? kind;
    const m = next.magaza === undefined ? store : next.magaza;
    if (w !== "cycle") params.set("pencere", w);
    if (k !== "all") params.set("tur", k);
    if (m) params.set("magaza", m);
    const qs = params.toString();
    return qs ? `/admin/degisiklikler?${qs}` : "/admin/degisiklikler";
  };

  const windowNote = log.window === "cycle"
    ? log.cycle_active
      ? `Şu an süren yenileme, ${formatDateTime(log.cycle_started_at)} başladı. Sayfa dakikada bir kendini yeniler.`
      : `Son biten yenileme: ${formatDateTime(log.cycle_started_at)} – ${formatDateTime(log.cycle_completed_at)}.`
    : window === "cycle"
      ? "Sunucu yeniden başladığından beri biten bir yenileme yok; son 24 saat gösteriliyor."
      : `${formatDateTime(log.since)} sonrası.`;

  return <div className="space-y-6">
    {log.cycle_active && log.window === "cycle" && <AutoRefresh seconds={60} />}
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">Fiyat değişiklikleri</h1>
      <p className="max-w-3xl text-sm text-muted">
        Fiyat yenilemede ve elle içe aktarmada hangi cildin hangi mağazada değiştiği: yeni kayıtlar,
        fiyat ve stok değişiklikleri, kaldırılan ürünler. Hiçbir mağazada olmayan bir cilt ilk kez
        bulunduğunda “İlk kez satışta” olarak işaretlenir ve o seriler en üstte durur.
      </p>
    </header>
    <div className="space-y-3">
      <Segmented label="Dönem" current="page" items={WINDOWS.map((w) => ({
        key: w.key, href: href({ pencere: w.key }), active: w.key === window, children: w.label,
      }))} />
      <Segmented label="Değişiklik türü" current="page" items={KINDS.map((k) => ({
        key: k.key, href: href({ tur: k.key }), active: k.key === kind,
        children: <>{k.label}{k.key !== "all" && <span className="ml-1.5 tabular text-faint">{log.counts[k.key]}</span>}</>,
      }))} />
      {log.stores.length > 1 && (
        <Segmented label="Mağaza" current="page" items={[
          { key: "", href: href({ magaza: null }), active: !store, children: "Tüm mağazalar" },
          ...log.stores.map((s) => ({
            key: s.code, href: href({ magaza: s.code }), active: s.code === store,
            children: <>{s.name}<span className="ml-1.5 tabular text-faint">{s.count}</span></>,
          })),
        ]} />
      )}
      <p className="text-xs text-muted">
        {windowNote} {log.total} değişiklik{log.shown !== log.total ? `, ${log.shown} gösteriliyor` : ""}
        {log.truncated ? " (en yeni 5000)" : ""}. Kayıtlar {log.retention_days} gün saklanır
        {log.kept_since ? `; en eskisi ${formatDateTime(log.kept_since)}` : ""}.
      </p>
    </div>
    <ChangeLogList series={log.series} />
  </div>;
}
