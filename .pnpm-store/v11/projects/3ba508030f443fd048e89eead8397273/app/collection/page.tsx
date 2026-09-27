import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { formatPrice } from "@/components/PriceBadge";
import { volumeLabel } from "@/lib/volumeLabel";
import { currentUser } from "@/services/auth";
import { getMyCollection, getMyPriceAlerts, getMyWishlist } from "@/services/me";
import type { CollectionStatus, MyVolume } from "@/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Koleksiyonum" };

const STATUS_LABEL: Record<CollectionStatus, string> = {
  owned: "Sahibim",
  missing: "Eksik",
  wanted: "İstediğim",
};

const STATUS_CHIP: Record<CollectionStatus, string> = {
  owned: "bg-emerald-500/10 text-emerald-400",
  missing: "bg-rose-500/10 text-rose-400",
  wanted: "bg-orange-500/10 text-orange-400",
};

function Row({ item, children }: { item: MyVolume; children?: React.ReactNode }) {
  return (
    <Link
      href={`/volume/${item.volume_id}`}
      className="flex items-center justify-between gap-3 rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3 transition-colors hover:border-orange-500/60"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-neutral-100">
          {item.series_title}
          <span className="text-neutral-400"> · {volumeLabel(item.volume_number)}</span>
        </p>
        <p className="truncate text-xs text-neutral-500">{item.publisher}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-sm">{children}</div>
    </Link>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-6 text-center text-sm text-neutral-500">
      {text}
    </div>
  );
}

export default async function CollectionPage() {
  const user = await currentUser();
  if (!user) redirect("/login");

  const [collection, wishlist, alerts] = await Promise.all([
    getMyCollection(),
    getMyWishlist(),
    getMyPriceAlerts(),
  ]);

  return (
    <div className="space-y-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-neutral-50">Koleksiyonum</h1>
        <p className="text-sm text-neutral-500">
          İşaretlediğin ciltler, istek listen ve fiyat alarmların.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-neutral-100">
          Koleksiyon <span className="text-sm font-normal text-neutral-500">({collection.length})</span>
        </h2>
        {collection.length === 0 ? (
          <Empty text="Henüz işaretlediğin cilt yok — bir cildi açıp Sahibim / Eksik / İstediğim seç." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {collection.map((item) => (
              <Row key={item.volume_id} item={item}>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STATUS_CHIP[item.status]}`}>
                  {STATUS_LABEL[item.status]}
                </span>
              </Row>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-neutral-100">
          İstek listesi <span className="text-sm font-normal text-neutral-500">({wishlist.length})</span>
        </h2>
        {wishlist.length === 0 ? (
          <Empty text="İstek listen boş." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {wishlist.map((item) => (
              <Row key={item.volume_id} item={item}>
                <span className="tabular-nums text-neutral-200">{formatPrice(item.best_price)}</span>
              </Row>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-neutral-100">
          Fiyat alarmları <span className="text-sm font-normal text-neutral-500">({alerts.length})</span>
        </h2>
        {alerts.length === 0 ? (
          <Empty text="Kurulu fiyat alarmın yok." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {alerts.map((item) => (
              <Row key={item.volume_id} item={item}>
                <span className="text-xs text-neutral-500">
                  en ucuz {formatPrice(item.best_price)}
                </span>
                <span className={item.is_active ? "tabular-nums text-emerald-400" : "tabular-nums text-neutral-500"}>
                  ≤ {formatPrice(item.threshold_price / 100)}
                </span>
              </Row>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
