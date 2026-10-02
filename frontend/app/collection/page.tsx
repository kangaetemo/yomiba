import { volumePath } from "@/lib/paths";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Badge, type BadgeTone, Cover, SectionHeading, formatTL } from "@/components/ui";
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

const STATUS_TONE: Record<CollectionStatus, BadgeTone> = {
  owned: "stock",
  missing: "soldout",
  wanted: "lowest",
};

/** A cover-first card, the same look as the series page's volume grid. */
function Tile({
  item,
  badge,
  footer,
}: {
  item: MyVolume;
  badge?: React.ReactNode;
  footer: React.ReactNode;
}) {
  const href = volumePath(item.series_slug, item.volume_number);
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card transition-shadow hover:shadow-lift">
      <Link href={href} className="group relative block px-3 pt-3" aria-label={`${item.series_title} ${volumeLabel(item.volume_number)}`}>
        <Cover
          url={item.cover_url}
          alt={`${item.series_title} ${volumeLabel(item.volume_number)} kapağı`}
          className="w-full transition-transform duration-300 group-hover:-translate-y-0.5"
        />
        {badge && <span className="absolute top-5 left-5">{badge}</span>}
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="min-w-0">
          <p className="eyebrow truncate">{item.series_title}</p>
          <Link href={href} className="text-[1.02rem] font-semibold text-ink hover:text-accent">
            {volumeLabel(item.volume_number)}
          </Link>
          <p className="truncate text-xs text-muted">{item.publisher}</p>
        </div>
        <div className="mt-auto border-t border-line pt-2">{footer}</div>
      </div>
    </li>
  );
}

/** "En düşük fiyat" with the price, or a plain "Stokta yok". */
function PriceFooter({ price, label = "En düşük fiyat" }: { price: number | null; label?: string }) {
  return price !== null ? (
    <div>
      <p className="text-[0.7rem] text-faint">{label}</p>
      <p className="tabular text-lg leading-tight font-bold text-ink">{formatTL(price)}</p>
    </div>
  ) : (
    <div>
      <p className="text-[0.7rem] text-faint">Şu an satışta değil</p>
      <p className="tabular text-lg leading-tight font-bold text-faint">—</p>
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">{children}</ul>;
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-center text-sm text-muted">
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

  const count = (status: CollectionStatus) => collection.filter((c) => c.status === status).length;

  return (
    <div className="space-y-12">
      <header className="space-y-3">
        <p className="eyebrow">Kitaplığın</p>
        <h1 className="text-3xl font-semibold text-ink sm:text-4xl">Koleksiyonum</h1>
        <p className="max-w-2xl text-sm text-muted sm:text-base">
          İşaretlediğin ciltler, istek listen ve fiyat alarmların.
        </p>
        {collection.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {(["owned", "missing", "wanted"] as const).map((status) => (
              <Badge key={status} tone={STATUS_TONE[status]}>
                {STATUS_LABEL[status]} · {count(status)}
              </Badge>
            ))}
          </div>
        )}
      </header>

      <section className="space-y-5" aria-labelledby="koleksiyon">
        <SectionHeading id="koleksiyon" title={`Koleksiyon (${collection.length})`} />
        {collection.length === 0 ? (
          <Empty text="Henüz işaretlediğin cilt yok — bir cildi açıp Sahibim / Eksik / İstediğim seç." />
        ) : (
          <Grid>
            {collection.map((item) => (
              <Tile
                key={item.volume_id}
                item={item}
                badge={<Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Badge>}
                footer={<PriceFooter price={item.best_price} />}
              />
            ))}
          </Grid>
        )}
      </section>

      <section className="space-y-5" aria-labelledby="istek-listesi">
        <SectionHeading id="istek-listesi" title={`İstek listesi (${wishlist.length})`} />
        {wishlist.length === 0 ? (
          <Empty text="İstek listen boş." />
        ) : (
          <Grid>
            {wishlist.map((item) => (
              <Tile key={item.volume_id} item={item} footer={<PriceFooter price={item.best_price} />} />
            ))}
          </Grid>
        )}
      </section>

      <section className="space-y-5" aria-labelledby="fiyat-alarmlari">
        <SectionHeading id="fiyat-alarmlari" title={`Fiyat alarmları (${alerts.length})`} />
        {alerts.length === 0 ? (
          <Empty text="Kurulu fiyat alarmın yok." />
        ) : (
          <Grid>
            {alerts.map((item) => (
              <Tile
                key={item.volume_id}
                item={item}
                badge={<Badge tone={item.is_active ? "alert" : "neutral"}>{item.is_active ? "Alarm açık" : "Alarm kapalı"}</Badge>}
                footer={
                  <div className="space-y-1">
                    <p className="text-[0.7rem] text-faint">Hedef fiyat</p>
                    <p className={`tabular text-lg leading-tight font-bold ${item.is_active ? "text-ok" : "text-muted"}`}>
                      ≤ {formatTL(item.threshold_price / 100)}
                    </p>
                    <p className="text-xs text-muted">
                      {item.best_price !== null ? `Şu an ${formatTL(item.best_price)}` : "Şu an satışta değil"}
                    </p>
                  </div>
                }
              />
            ))}
          </Grid>
        )}
      </section>
    </div>
  );
}
