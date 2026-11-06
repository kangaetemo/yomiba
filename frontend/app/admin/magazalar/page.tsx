import type { Metadata } from "next";
import { ImportPanel, StoreProbePanel } from "@/components/admin/AdminControls";
import { AdminHeader, requireAdmin } from "@/components/admin/AdminHeader";

export const metadata: Metadata = { title: "Mağazalar" };

export default async function StoresPage() {
  await requireAdmin("/admin/magazalar");
  return <div className="space-y-6">
    <AdminHeader title="Mağazalar">
      Bir sorguyu bütün mağazalarda elle içe aktar, son içe aktarmaları gör ve mağazaların bu
      sunucudan erişilebilir olup olmadığını test et.
    </AdminHeader>
    <ImportPanel />
    <StoreProbePanel />
  </div>;
}
