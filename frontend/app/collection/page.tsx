import { volumePath } from "@/lib/paths";
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
  owned: "bg-ok/10 text-ok",
  missing: "bg-bad/10 text-bad",
  wanted: "bg-accent/10 text-accent",
};

function Row({ item, children }: { item: MyVolume; children?: React.ReactNode }) {
  return (
    <Link
      href={volumePath(item.series_slug, item.volume_number)}
      className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 transition-colors hover:border-accent/60"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">
          {item.series_title}
          <span className="text-muted"> · {volumeLabel(item.volume_number)}</span>
        </p>
        <p className="truncate text-xs text-muted">{item.publisher}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-sm">{children}</div>
    </Link>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-6 text-center text-sm text-muted">
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
        <h1 className="text-2xl font-bold tracking-tight text-ink">Koleksiyonum</h1>
        <p className="text-sm text-muted">
          İşaretlediğin ciltler, istek listen ve fiyat alarmların.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Koleksiyon <span className="text-sm font-normal text-muted">({collection.length})</span>
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
        <h2 className="text-lg font-semibold text-ink">
          İstek listesi <span className="text-sm font-normal text-muted">({wishlist.length})</span>
        </h2>
        {wishlist.length === 0 ? (
          <Empty text="İstek listen boş." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {wishlist.map((item) => (
              <Row key={item.volume_id} item={item}>
                <span className="tabular-nums text-ink-2">{formatPrice(item.best_price)}</span>
              </Row>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Fiyat alarmları <span className="text-sm font-normal text-muted">({alerts.length})</span>
        </h2>
        {alerts.length === 0 ? (
          <Empty text="Kurulu fiyat alarmın yok." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {alerts.map((item) => (
              <Row key={item.volume_id} item={item}>
                <span className="text-xs text-muted">
                  en ucuz {formatPrice(item.best_price)}
                </span>
                <span className={item.is_active ? "tabular-nums text-ok" : "tabular-nums text-muted"}>
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
