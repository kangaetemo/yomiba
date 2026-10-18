import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { CollectionView, type CollectionTab } from "@/components/collection/CollectionView";
import { currentUser } from "@/services/auth";
import { getMyCollection, getMyPriceAlerts, getMyWishlist } from "@/services/me";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Koleksiyonum", robots: { index: false } };

const TABS: CollectionTab[] = ["koleksiyon", "istek", "alarm"];

export default async function CollectionPage({ searchParams }: { searchParams: Promise<{ sekme?: string }> }) {
  const user = await currentUser();
  if (!user) redirect("/login?next=%2Fcollection");
  const { sekme } = await searchParams;
  const initialTab = TABS.find((t) => t === sekme) ?? "koleksiyon";

  const [collection, wishlist, alerts] = await Promise.all([
    getMyCollection(),
    getMyWishlist(),
    getMyPriceAlerts(),
  ]);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <p className="eyebrow">Kitaplığın</p>
        <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Koleksiyonum</h1>
        <p className="max-w-2xl text-sm text-muted sm:text-base">
          İşaretlediğin ciltler, istek listen ve fiyat alarmların.
        </p>
      </header>
      <CollectionView collection={collection} wishlist={wishlist} alerts={alerts} initialTab={initialTab} />
    </div>
  );
}
