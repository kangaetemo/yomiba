import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { IsbnReviewCenter } from "@/components/admin/IsbnReviewCenter";
import { currentUser } from "@/services/auth";

export const metadata: Metadata = { title: "ISBN İnceleme Merkezi" };

export default async function IsbnPage() {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.role !== "ADMIN") redirect("/");
  return <div className="space-y-6">
    <header className="space-y-2">
      <Link href="/admin" className="text-sm text-new hover:underline">← Yönetim paneli</Link>
      <h1 className="text-2xl font-bold tracking-tight text-ink">ISBN İnceleme Merkezi</h1>
      <p className="max-w-3xl text-sm text-muted">Kataloğu bağımsız ürün kayıtlarıyla karşılaştırın, kanıtları inceleyin ve ISBN kararlarını kaydedin. Tarama sırasında katalog ISBN’leri değişmez.</p>
    </header>
    <IsbnReviewCenter />
  </div>;
}
