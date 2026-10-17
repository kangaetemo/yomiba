import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect, redirect } from "next/navigation";
import { FollowMissingButton } from "@/components/FollowMissingButton";
import { Cover, formatTL, volumeTitle } from "@/components/ui";
import { SortBar } from "@/components/SortBar";
import { Segmented } from "@/components/Segmented";
import { EditionLinks } from "@/components/EditionLinks";
import { VolumeCard } from "@/components/VolumeCard";
import { VolumeTile } from "@/components/VolumeTile";
import { ApiError } from "@/lib/api";
import { oneShotVolumeNumber, seriesPath, volumePath } from "@/lib/paths";
import { currentUserOrNull } from "@/services/auth";
import { getSeries } from "@/services/catalog";
import type { CollectionStatus, SeriesVolume } from "@/types";

export const dynamic = "force-dynamic";

interface SeriesPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ status?: string; all?: string; sort?: string; view?: string; stock?: string }>;
}

type Filter = CollectionStatus | "wishlist" | "all";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "owned", label: "Bende var" },
  { value: "missing", label: "Bende yok" },
  { value: "wishlist", label: "İstek listemde" },
];

/** Default view shows the first N volumes; the rest sit behind the
 * "+N cilt daha göster" toggle (server-rendered via ?all=1). With an
 * active status filter the list is never capped — it is a drill-down. */
const SHOW_FIRST = 15;

/** The first entry is the default (volume number, ascending). */
const SORTS = [
  { key: "no", label: "Cilt no ↑" },
  { key: "desc", label: "Cilt no ↓" },
  { key: "fiyat", label: "Fiyat ↑" },
  { key: "fiyat-azalan", label: "Fiyat ↓" },
];

/** Price order: volumes buyable today by price; the rest keep volume order
 * after them (an out-of-stock price is not a price). */
function byPrice(volumes: SeriesVolume[], dir: 1 | -1): SeriesVolume[] {
  const buyable = (v: SeriesVolume) => v.in_stock_count > 0 && v.best_price !== null;
  return [
    ...volumes.filter(buyable).sort((a, b) => dir * ((a.best_price as number) - (b.best_price as number))),
    ...volumes.filter((v) => !buyable(v)),
  ];
}

/** The cheapest volume anyone can buy today (in stock somewhere). */
function cheapestInStock(volumes: SeriesVolume[]): SeriesVolume | null {
  let best: SeriesVolume | null = null;
  for (const v of volumes) {
    if (v.in_stock_count === 0 || v.best_price === null) continue;
    if (best === null || v.best_price < (best.best_price as number)) best = v;
  }
  return best;
}

export async function generateMetadata({ params }: SeriesPageProps): Promise<Metadata> {
  const { slug } = await params;
  try {
    const detail = await getSeries(slug);
    return { title: `${detail.title} — ${detail.publisher}` };
  } catch {
    return { title: "Seri bulunamadı" };
  }
}

export default async function SeriesPage({ params, searchParams }: SeriesPageProps) {
  const { slug } = await params;

  let detail;
  try {
    detail = await getSeries(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  // Old numeric links (and any non-canonical spelling) land on the slug URL.
  if (detail.slug !== slug) permanentRedirect(seriesPath(detail.slug));
  // A one shot has a single volume: nothing to choose, open its prices.
  // Temporary redirect: a sequel volume would bring the list back.
  const only = oneShotVolumeNumber(detail);
  if (only !== null) redirect(volumePath(detail.slug, only));
  const user = await currentUserOrNull();
  const signedIn = Boolean(user);
  const upcoming = detail.upcoming_volumes ?? [];

  const { status: rawStatus, all, sort, view, stock } = await searchParams;
  // "wanted" is the old wishlist-like collection status (links in the wild).
  const requested = rawStatus === "wanted" ? "wishlist" : rawStatus;
  const activeFilter: Filter =
    signedIn && (requested === "owned" || requested === "missing" || requested === "wishlist")
      ? requested
      : "all";
  const activeSort = SORTS.find((o) => o.key === sort)?.key ?? "no";
  const stockOnly = stock === "1";
  const listView = view === "list";

  const byStatus =
    activeFilter === "all"
      ? detail.volumes
      : activeFilter === "wishlist"
        ? detail.volumes.filter((v) => v.wishlisted)
        : detail.volumes.filter((v) => v.collection_status === activeFilter);
  const filtered = stockOnly ? byStatus.filter((v) => v.in_stock_count > 0) : byStatus;
  const volumes =
    activeSort === "desc"
      ? [...filtered].reverse()
      : activeSort === "fiyat"
        ? byPrice(filtered, 1)
        : activeSort === "fiyat-azalan"
          ? byPrice(filtered, -1)
          : filtered;
  const activeLabel = FILTERS.find((f) => f.value === activeFilter)?.label ?? "Tümü";

  const expanded = activeFilter !== "all" || stockOnly || all === "1";
  const visibleVolumes = expanded ? volumes : volumes.slice(0, SHOW_FIRST);
  const hiddenCount = volumes.length - visibleVolumes.length;

  /** Link to this page with some query params changed (others kept). */
  const hrefWith = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams();
    const current = { status: activeFilter === "all" ? null : activeFilter, all: all ?? null, sort: activeSort === "no" ? null : activeSort, view: view ?? null, stock: stockOnly ? "1" : null };
    for (const [k, v] of Object.entries({ ...current, ...changes })) if (v) next.set(k, v);
    const qs = next.toString();
    return `${seriesPath(detail.slug)}${qs ? `?${qs}` : ""}`;
  };

  // Header facts.
  const cheapest = cheapestInStock(detail.volumes);
  const inStock = detail.volumes.filter((v) => v.in_stock_count > 0);
  const owned = detail.volumes.filter((v) => v.collection_status === "owned").length;
  const tracked = detail.volumes.filter((v) => v.wishlisted).length;
  const untrackedIds = detail.volumes
    .filter((v) => v.collection_status !== "owned" && !v.wishlisted)
    .map((v) => v.id);

  const chip = "inline-flex min-h-9 items-center rounded-lg border px-3 text-sm transition-colors";

  return (
    <div className="space-y-10">
      <nav aria-label="Konum" className="text-sm text-muted">
        <Link href="/" className="hover:text-accent">
          ← Ana sayfa
        </Link>
      </nav>

      {/* -- series header ------------------------------------------------ */}
      <section className="grid gap-6 sm:grid-cols-[auto_1fr] sm:gap-8">
        <Cover url={detail.cover_url} alt={`${detail.title} kapağı`} className="w-32 sm:w-44" eager />
        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 space-y-1.5">
              <p className="eyebrow">Seri</p>
              <h1 className="text-3xl leading-tight font-semibold text-ink sm:text-[2.6rem]">{detail.title}</h1>
              <p className="text-sm text-muted">
                {[detail.author, detail.publisher, `${detail.volumes.length} cilt`, upcoming.length > 0 ? `${upcoming.length} yakında` : null].filter(Boolean).join(" · ")}
              </p>
            </div>
            <FollowMissingButton signedIn={signedIn} untrackedIds={untrackedIds} trackedCount={tracked} />
          </div>

          <dl className="grid max-w-xl grid-cols-2 gap-x-8 gap-y-3 border-t border-line pt-4">
            <div>
              <dt className="text-xs text-faint">Başlangıç fiyatı</dt>
              <dd className="tabular text-3xl leading-tight font-bold text-ink">
                {cheapest ? formatTL(cheapest.best_price) : "—"}
              </dd>
              <dd className="text-xs text-muted">
                {cheapest
                  ? `${volumeTitle(cheapest.number)}${cheapest.best_store ? ` · ${cheapest.best_store}` : ""}`
                  : "Şu an stokta cilt yok"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Stokta</dt>
              <dd className="tabular text-3xl leading-tight font-bold text-ink">
                {inStock.length}
                <span className="text-lg font-semibold text-faint">/{detail.volumes.length}</span>
              </dd>
              <dd className="text-xs text-muted">
                {signedIn && owned > 0 ? `${owned} cilt sende` : "en az bir mağazada"}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      {upcoming.length > 0 ? (
        <section aria-labelledby="yakinda" className="space-y-3 rounded-xl border border-line bg-surface p-4">
          <h2 id="yakinda" className="eyebrow">Yakında</h2>
          <p className="text-sm text-muted">Duyurulan ciltler yayımlanmış cilt sayısına dahil değildir.</p>
          <ul className="flex flex-wrap gap-2">
            {upcoming.map((v) => <li key={v.id} className="rounded-lg border border-line px-3 py-2 text-sm text-ink">
              {volumeTitle(v.number)}{v.release_date ? ` · ${new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(v.release_date))}` : " · Çıkış tarihi henüz belli değil"}
            </li>)}
          </ul>
        </section>
      ) : null}

      {/* -- other editions (e.g. Soichi <-> Soichi (Bez Cilt)) ---------------- */}
      <EditionLinks editions={detail.editions ?? []} />

      {/* -- volumes ------------------------------------------------------ */}
      <section aria-labelledby="ciltler" className="space-y-4">
        <div className="rule" aria-hidden />
        <h2 id="ciltler" className="text-2xl font-semibold text-ink">
          Ciltler{" "}
          <span className="font-sans text-sm font-normal text-muted">
            {activeFilter === "all" && !stockOnly ? `${detail.volumes.length} cilt` : `${stockOnly ? "Stokta" : activeLabel} · ${volumes.length}`}
          </span>
        </h2>

        <SortBar
          sorts={SORTS}
          active={activeSort}
          stockOnly={stockOnly}
          hrefFor={(c) => hrefWith({ ...c, all: null })}
        >
          <Segmented
            label="Görünüm"
            items={[
              { key: "grid", label: "Izgara", icon: <GridIcon /> },
              { key: "list", label: "Liste", icon: <ListIcon /> },
            ].map((opt) => ({
              key: opt.key,
              href: hrefWith({ view: opt.key === "list" ? "list" : null }),
              active: (opt.key === "list") === listView,
              ariaLabel: `${opt.label} görünümü`,
              children: opt.icon,
            }))}
          />
        </SortBar>

        {signedIn && (
          <Segmented
            label="Ciltleri koleksiyon durumuna göre filtrele"
            current="page"
            items={FILTERS.map((f) => ({
              key: f.value,
              href: hrefWith({ status: f.value === "all" ? null : f.value, all: null }),
              active: f.value === activeFilter,
              children: f.label,
            }))}
          />
        )}

        {volumes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-8 text-center text-sm text-muted">
            {stockOnly
              ? "Şu an stokta cilt yok."
              : activeFilter === "all"
              ? "Bu seri için henüz cilt yok."
              : activeFilter === "wishlist"
                ? "İstek listende bu seriden cilt yok. Kartlardaki yer imi simgesiyle ekleyebilirsin."
                : `“${activeLabel}” olarak işaretlenmiş cilt yok.`}
          </div>
        ) : listView ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {visibleVolumes.map((volume) => (
              <VolumeCard key={volume.id} volume={volume} seriesSlug={detail.slug} />
            ))}
          </div>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
            {visibleVolumes.map((volume) => (
              <VolumeTile key={volume.id} volume={volume} seriesTitle={detail.title} seriesSlug={detail.slug} signedIn={signedIn} />
            ))}
          </ul>
        )}

        {hiddenCount > 0 && (
          <div className="flex justify-center pt-1">
            <Link href={hrefWith({ all: "1" })} scroll={false} className={`${chip} border-line bg-surface text-ink-2 hover:border-accent hover:text-accent`}>
              +{hiddenCount} cilt daha göster
            </Link>
          </div>
        )}
      </section>

      {/* -- collection nudge (collection is the second act) -------------- */}
      {!(signedIn && owned > 0) && (
        <section className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <span aria-hidden className="screentone grid size-12 shrink-0 place-items-center rounded-lg border border-line font-display text-xl text-ink-2">
              棚
            </span>
            <div>
              <p className="font-display text-lg font-semibold text-ink">Hangi ciltler sende var?</p>
              <p className="text-sm text-muted">
                {signedIn
                  ? "Elindekileri ✓ ile işaretle; istediklerini yer imiyle istek listene ekle."
                  : "Koleksiyonunu oluştur, eksik ciltlerini tek bakışta gör."}
              </p>
            </div>
          </div>
          {!signedIn && (
            <Link
              href="/register"
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-accent px-4 text-sm font-semibold text-accent transition-colors hover:bg-accent hover:text-on-accent"
            >
              Koleksiyonumu oluştur
            </Link>
          )}
        </section>
      )}

      <p className="text-xs text-faint">
        Fiyatlar mağazaların son kontrol edilen verilerini gösterir; stok bilgisi gecikmeli olabilir.
      </p>
    </div>
  );
}


function GridIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.2" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M5 7h14M5 12h14M5 17h14" />
    </svg>
  );
}
