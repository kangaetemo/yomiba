import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { SpecialSetAdmin } from "@/components/admin/SpecialSetAdmin";
import { currentUser } from "@/services/auth";
import { getSeriesOptions, getSpecialSets } from "@/services/specialSets";

export const metadata: Metadata = { title: "Özel setler" };

export default async function SpecialSetsPage() {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fadmin%2Fozel-setler");
  if (user.role !== "ADMIN") redirect("/");
  const [sets, series] = await Promise.all([getSpecialSets(), getSeriesOptions()]);
  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">Özel setler</h1>
      <p className="max-w-3xl text-sm text-muted">Kutulu set, paket ya da özel ön sipariş gibi tek bir cilde ait olmayan ürünler. Mağazadaki ürün linkini ekle, hangi serilerin sayfasında görüneceğini seç. Fiyat ve stok, bağlı serinin her fiyat yenilemesinde ürün sayfasından güncellenir.</p>
    </header>
    <SpecialSetAdmin sets={sets.items} series={series.items} />
  </div>;
}
