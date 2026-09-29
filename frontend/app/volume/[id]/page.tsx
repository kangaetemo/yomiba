import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { StoreListingCard } from "@/components/StoreListingCard";
import { CoverImage } from "@/components/SeriesCard";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { CollectionStatusPicker } from "@/components/CollectionStatusPicker";
import { WishlistToggle } from "@/components/WishlistToggle";
import { PriceAlertForm } from "@/components/PriceAlertForm";
import { ApiError } from "@/lib/api";
import { volumeLabel as labelFor } from "@/lib/volumeLabel";
import { currentUserOrNull } from "@/services/auth";
import { getPriceAlert, getPriceHistory, getVolume, getWishlist } from "@/services/catalog";
import type { PriceAlert, PriceHistory, WishlistState } from "@/types";

export const dynamic = "force-dynamic";

interface VolumePageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({
  params,
}: VolumePageProps): Promise<Metadata> {
  const { id } = await params;
  const numId = Number(id);
  if (!Number.isInteger(numId) || numId <= 0) return { title: "Cilt bulunamadı" };
  try {
    const detail = await getVolume(numId);
    return { title: `${detail.series.title} ${labelFor(detail.number)}` };
  } catch {
    return { title: "Cilt bulunamadı" };
  }
}

export default async function VolumePage({ params }: VolumePageProps) {
  const { id } = await params;
  const numId = Number(id);
  if (!Number.isInteger(numId) || numId <= 0) notFound();

  let detail;
  try {
    detail = await getVolume(numId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const volumeLabel = labelFor(detail.number);

  // The API already returns listings sorted by price ascending (cheapest
  // first, no-price last); the first priced listing that can actually be
  // bought (in stock, not stale) is the cheapest.
  const cheapestStore = detail.stores.find(
    (s) => s.price !== null && s.stock && !s.stale,
  )?.store;

  // Price history is a secondary view: a failed fetch must degrade to the
  // empty state, never break the volume page itself.
  let history: PriceHistory | null = null;
  try {
    history = await getPriceHistory(numId);
  } catch {
    history = null;
  }
  const historyListings = (history?.listings ?? []).filter(
    (l) => l.points.length > 0,
  );
  const user = await currentUserOrNull();

  // Wishlist / price-alert initial states (same graceful degradation).
  let wishlist: WishlistState | null = null;
  if (user) {
    try { wishlist = await getWishlist(numId); } catch { wishlist = null; }
  }
  let alertState: { alert: PriceAlert | null } | null = null;
  if (user) {
    try { alertState = await getPriceAlert(numId); } catch { alertState = null; }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link
          href="/"
          className="text-muted hover:text-accent"
        >
          ← Arama
        </Link>
        <span className="text-faint">/</span>
        <Link
          href={`/series/${detail.series.id}`}
          className="text-muted hover:text-accent"
        >
          {detail.series.title} — {detail.series.publisher}
        </Link>
      </div>

      <section className="flex gap-6">
        <CoverImage
          url={detail.cover_url}
          alt={`${detail.series.title} ${volumeLabel}`}
          className="h-44 w-32 sm:h-52 sm:w-36"
        />
        <div className="flex flex-col justify-center gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-ink">
            {detail.series.title}
          </h1>
          <p className="text-base text-muted">{volumeLabel}</p>
          <p className="text-sm text-muted">{detail.series.publisher}</p>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Koleksiyonum
        </h2>
        <div className="max-w-xl">
          {user ? <CollectionStatusPicker
            volumeId={numId}
            initial={detail.collection_status}
          /> : <Link href="/login" className="text-sm text-ink-2 underline decoration-accent/50 underline-offset-4 hover:text-accent">Koleksiyonunu takip etmek için giriş yap.</Link>}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          İstek listesi
        </h2>
        {user ? <WishlistToggle
          volumeId={numId}
          initial={wishlist?.wishlisted ?? false}
        /> : <Link href="/login" className="text-sm text-ink-2 underline decoration-accent/50 underline-offset-4 hover:text-accent">İstek listesi için giriş yap.</Link>}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Fiyat alarmı
        </h2>
        {user ? <PriceAlertForm
          volumeId={numId}
          initialAlert={alertState?.alert ?? null}
        /> : <Link href="/login" className="text-sm text-ink-2 underline decoration-accent/50 underline-offset-4 hover:text-accent">Fiyat alarmı için giriş yap.</Link>}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Mağazalar{" "}
          <span className="text-sm font-normal text-muted">
            (en ucuz önce)
          </span>
        </h2>

        {detail.unverified ? (
          <div className="rounded-xl border border-warn/40 bg-warn/10 p-8 text-center text-sm text-warn">
            Bu kaydın cilt numarası doğrulanamadı; eski mağaza fiyatları
            güncel olmadığı için gösterilmiyor.
          </div>
        ) : detail.stores.length === 0 ? (
          <div className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-muted">
            Bu cilt için henüz mağaza listelemesi yok.
          </div>
        ) : (
          <div className="space-y-3">
            {detail.stores.map((listing) => (
              <StoreListingCard
                key={listing.product_url + listing.store}
                listing={listing}
                isCheapest={cheapestStore !== null && listing.store === cheapestStore}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">
          Fiyat geçmişi
        </h2>

        {historyListings.length === 0 ? (
          <div className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-muted">
            Henüz fiyat geçmişi yok — bu cildin fiyatı içe aktarmalarla
            yeniden kontrol edildikçe burada görünecek.
          </div>
        ) : (
          <PriceHistoryChart listings={historyListings} />
        )}
      </section>
    </div>
  );
}
