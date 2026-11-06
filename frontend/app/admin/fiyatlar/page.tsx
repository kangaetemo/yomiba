import type { Metadata } from "next";
import { CoveragePanel, MissingCoveragePanel } from "@/components/admin/AdminControls";
import { AdminHeader, requireAdmin } from "@/components/admin/AdminHeader";

export const metadata: Metadata = { title: "Fiyat yenileme" };

export default async function PricesPage() {
  await requireAdmin("/admin/fiyatlar");
  return <div className="space-y-6">
    <AdminHeader title="Fiyat yenileme ve kapsama">
      Katalogdaki serilerin mağaza fiyatlarını yenileyen döngünün durumu, kaç serinin fiyatı
      olduğu ve hiç fiyatı olmayan serilerin nedenleri.
    </AdminHeader>
    <CoveragePanel />
    <MissingCoveragePanel />
  </div>;
}
