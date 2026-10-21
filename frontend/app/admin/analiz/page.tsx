import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnalyticsDashboard } from "@/components/admin/AnalyticsDashboard";
import { Segmented } from "@/components/Segmented";
import { currentUser } from "@/services/auth";
import { ANALYTICS_PERIODS, getAnalytics } from "@/services/analytics";

export const metadata: Metadata = { title: "Analiz" };

export default async function AnalyticsPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fanaliz");
  if (user.role !== "ADMIN") redirect("/");
  const query = await searchParams;
  const days = ANALYTICS_PERIODS.some((p) => p.days === Number(query.gun)) ? Number(query.gun) : 30;
  const report = await getAnalytics(days);
  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">Analiz</h1>
      <p className="max-w-3xl text-sm text-muted">Ziyaretçiler, en çok bakılan seri ve ciltler, mağazalara giden tıklamalar, aramalar ve trafik kaynakları. Yönetici ziyaretleri ve botlar sayılmaz.</p>
    </header>
    <Segmented label="Dönem" items={ANALYTICS_PERIODS.map((p) => ({
      key: String(p.days), href: `/admin/analiz?gun=${p.days}`, active: p.days === days, children: p.label,
    }))} />
    <AnalyticsDashboard report={report} />
  </div>;
}
