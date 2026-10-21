import type { Metadata } from "next";
import { AdminControls } from "@/components/admin/AdminControls";
import { currentUser } from "@/services/auth";
import { redirect } from "next/navigation";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Admin",
};

export default async function AdminPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin");
  if (user.role !== "ADMIN") redirect("/");
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          İçe aktarma ve senkron
        </h1>
        <p className="text-sm text-muted">
          Katalog senkronunu manuel çalıştırın, mağaza içe aktarın ve son
          denemeleri izleyin.
        </p>
      </header>
      <Link href="/admin/analiz" className="block rounded-xl border border-line bg-surface p-5 transition-colors hover:bg-surface-2">
        <h2 className="font-semibold text-ink">Analiz →</h2>
        <p className="mt-1 text-sm text-muted">Ziyaretçiler, en çok bakılan seri ve ciltler, mağazalara giden tıklamalar, aramalar ve trafik kaynakları.</p>
      </Link>
      <Link href="/admin/isbn/saglik" className="block rounded-xl border border-line bg-surface p-5 transition-colors hover:bg-surface-2">
        <h2 className="font-semibold text-ink">ISBN Sağlık Raporu →</h2>
        <p className="mt-1 text-sm text-muted">ISBN çelişkileri, Mangakol hataları, bağlanmayan ürünler, aykırı fiyatlar ve son ISBN değişiklikleri. Cilt bazında karar cilt sayfasındaki admin panelinde.</p>
      </Link>
      <AdminControls />
    </div>
  );
}
