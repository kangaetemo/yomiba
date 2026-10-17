import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { IsbnHealthReport } from "@/components/admin/IsbnHealthReport";
import { currentUser } from "@/services/auth";

export const metadata: Metadata = { title: "ISBN Sağlık Raporu" };

export default async function IsbnHealthPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fisbn%2Fsaglik");
  if (user.role !== "ADMIN") redirect("/");
  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">ISBN Sağlık Raporu</h1>
      <p className="max-w-3xl text-sm text-muted">Eksik ve şüpheli ISBN’lerin, yanlış cilde bağlanmış olabilecek ilanların ve aykırı fiyatların dökümü. Salt okunur: rapor hiçbir kaydı değiştirmez.</p>
    </header>
    <IsbnHealthReport />
  </div>;
}
