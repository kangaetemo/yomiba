import type { Metadata } from "next";
import Link from "next/link";
import {
  CatalogAuditPanel, CatalogSyncPanel, CoverPanel, ForeignEditionsPanel,
} from "@/components/admin/AdminControls";
import { AdminHeader, requireAdmin } from "@/components/admin/AdminHeader";

export const metadata: Metadata = { title: "Katalog" };

export default async function CatalogPage() {
  await requireAdmin("/admin/katalog");
  return <div className="space-y-6">
    <AdminHeader title="Katalog senkronu ve bakım">
      Mangakol&apos;dan seri ve cilt senkronu, katalog karşılaştırması, kapak indirme ve yabancı
      baskı temizliği. ISBN sorunları için{" "}
      <Link href="/admin/isbn/saglik" className="font-medium text-accent underline">ISBN sağlık raporu</Link>.
    </AdminHeader>
    <CatalogSyncPanel />
    <CatalogAuditPanel />
    <CoverPanel />
    <ForeignEditionsPanel />
  </div>;
}
