import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ReportList } from "@/components/admin/ReportList";
import { Segmented } from "@/components/Segmented";
import { currentUser } from "@/services/auth";
import { getReports, type ReportStatus } from "@/services/reports";

export const metadata: Metadata = { title: "Hata bildirimleri" };

const FILTERS: { key: ReportStatus | "all"; label: string }[] = [
  { key: "new", label: "Yeni" },
  { key: "resolved", label: "Çözüldü" },
  { key: "dismissed", label: "Geçersiz" },
  { key: "all", label: "Tümü" },
];

export default async function ReportsPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fbildirimler");
  if (user.role !== "ADMIN") redirect("/");
  const query = await searchParams;
  const status = FILTERS.find((f) => f.key === query.durum)?.key ?? "new";
  const list = await getReports(status);
  const total = list.counts.new + list.counts.resolved + list.counts.dismissed;
  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">Hata bildirimleri</h1>
      <p className="max-w-3xl text-sm text-muted">Ziyaretçilerin seri ve cilt sayfalarındaki “Hatalı bilgi mi gördün?” formuyla gönderdikleri. Düzelttiğini “Çözüldü”, anlamsız ya da spam olanı “Geçersiz” olarak işaretle.</p>
    </header>
    <Segmented label="Durum" current="page" items={FILTERS.map((f) => ({
      key: f.key, href: f.key === "new" ? "/admin/bildirimler" : `/admin/bildirimler?durum=${f.key}`,
      active: f.key === status,
      children: <>{f.label}<span className="ml-1.5 tabular text-faint">{f.key === "all" ? total : list.counts[f.key]}</span></>,
    }))} />
    <ReportList items={list.items} />
  </div>;
}
