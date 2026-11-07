import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AnalyticsDashboard } from "@/components/admin/AnalyticsDashboard";
import { Segmented } from "@/components/Segmented";
import { currentUser } from "@/services/auth";
import { ANALYTICS_PERIODS, DEFAULT_ANALYTICS_PERIOD, getAnalytics } from "@/services/analytics";

export const metadata: Metadata = { title: "Analiz" };

export default async function AnalyticsPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fanaliz");
  if (user.role !== "ADMIN") redirect("/");
  const query = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const asked = query.saat !== undefined ? `saat=${one(query.saat)}` : `gun=${one(query.gun)}`;
  const period = ANALYTICS_PERIODS.find((p) => p.key === asked) ?? DEFAULT_ANALYTICS_PERIOD;
  const report = await getAnalytics(period);
  return <div className="space-y-6">
    <header className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Analiz</h1>
      <p className="max-w-3xl text-sm text-muted">Ziyaretçiler, en çok bakılan seri ve ciltler, mağazalara giden tıklamalar, aramalar ve trafik kaynakları. Yönetici ziyaretleri ve botlar sayılmaz.</p>
    </header>
    <Segmented label="Dönem" items={ANALYTICS_PERIODS.map((p) => ({
      key: p.key, href: `/admin/analiz?${p.key}`, active: p === period, children: p.label,
    }))} />
    <AnalyticsDashboard report={report} />
  </div>;
}
