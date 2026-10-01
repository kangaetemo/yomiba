import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { FollowMissingButton } from "@/components/FollowMissingButton";
import { Cover, formatTL, volumeTitle } from "@/components/ui";
import { SortBar } from "@/components/SortBar";
import { VolumeCard } from "@/components/VolumeCard";
import { VolumeTile } from "@/components/VolumeTile";
import { ApiError } from "@/lib/api";
import { seriesPath } from "@/lib/paths";
import { currentUserOrNull } from "@/services/auth";
import { getSeries } from "@/services/catalog";
import type { CollectionStatus, SeriesVolume } from "@/types";

export const dynamic = "force-dynamic";

interface SeriesPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ status?: string; all?: string; sort?: string; view?: string; stock?: string }>;
}

type Filter = CollectionStatus | "all";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "owned", label: "Sahibim" },
  { value: "missing", label: "Eksik" },
  { value: "wanted", label: "Takipte" },
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
  const user = await currentUserOrNull();
  const signedIn = Boolean(user);

  const { status: rawStatus, all, sort, view, stock } = await searchParams;
  const activeFilter: Filter =
    signedIn && (rawStatus === "owned" || rawStatus === "missing" || rawStatus === "wanted")
      ? rawStatus
      : "all";
  const activeSort = SORTS.find((o) => o.key === sort)?.key ?? "no";
  const stockOnly = stock === "1";
  const listView = view === "list";

  const byStatus =
    activeFilter === "all"
      ? detail.volumes
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
  const priced = detail.volumes.filter((v) => v.store_count > 0);
  const inStock = detail.volumes.filter((v) => v.in_stock_count > 0);
  const owned = detail.volumes.filter((v) => v.collection_status === "owned").length;
  const tracked = detail.volumes.filter((v) => v.collection_status === "wanted").length;
  const untrackedIds = detail.volumes
    .filter((v) => v.collection_status !== "owned" && v.collection_status !== "wanted")
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
                {[detail.author, detail.publisher, `${detail.volumes.length} cilt`].filter(Boolean).join(" · ")}
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
                  : priced.length > 0
                    ? "Şu an stokta cilt yok"
                    : "Henüz fiyat yok"}
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

      {/* -- other editions (e.g. Soichi <-> Soichi (Bez Cilt)) ---------------- */}
      {(detail.editions ?? []).length > 0 && (
        <section aria-labelledby="baskilar" className="space-y-3">
          <h2 id="baskilar" className="eyebrow">
            Bu serinin başka baskıları
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {(detail.editions ?? []).map((e) => (
              <li key={e.id}>
                <Link
                  href={seriesPath(e.slug)}
                  className="group flex items-center justify-between gap-4 rounded-xl border border-line bg-surface px-4 py-3 shadow-card transition-colors hover:border-line-strong"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-ink group-hover:text-accent">{e.title}</p>
                    <p className="truncate text-sm text-muted">
                      {e.publisher} · {e.volume_count} cilt
                    </p>
                  </div>
                  <div className="shrink-0 text-right text-sm">
                    {e.lowest_price !== null ? (
                      <span className="tabular font-bold text-ink">
                        {formatTL(e.lowest_price)}
                        <span className="font-normal text-muted">&apos;den</span>
                      </span>
                    ) : (
                      <span className="text-faint">Stokta yok</span>
                    )}
                    <span aria-hidden className="ml-2 text-ink-2">→</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* -- other editions (e.g. Soichi <-> Soichi (Bez Cilt)) ---------------- */}
      {(detail.editions ?? []).length > 0 && (
        <section aria-labelledby="baskilar" className="space-y-3">
          <h2 id="baskilar" className="eyebrow">
            Bu serinin başka baskıları
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {(detail.editions ?? []).map((e) => (
              <li key={e.id}>
                <Link
                  href={seriesPath(e.slug)}
                  className="group flex items-center justify-between gap-4 rounded-xl border border-line bg-surface px-4 py-3 shadow-card transition-colors hover:border-line-strong"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-ink group-hover:text-accent">{e.title}</p>
                    <p className="truncate text-sm text-muted">
                      {e.publisher} · {e.volume_count} cilt
                    </p>
                  </div>
                  <div className="shrink-0 text-right text-sm">
                    {e.lowest_price !== null ? (
                      <span className="tabular font-bold text-ink">
                        {formatTL(e.lowest_price)}
                        <span className="font-normal text-muted">&apos;den</span>
                      </span>
                    ) : (
                      <span className="text-faint">Stokta yok</span>
                    )}
                    <span aria-hidden className="ml-2 text-ink-2">→</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* -- volumes ------------------------------------------------------ */}
      <section aria-labelledby="ciltler" className="space-y-4">
        <div className="rule" aria-hidden />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="ciltler" className="text-2xl font-semibold text-ink">
            Ciltler{" "}
            <span className="font-sans text-sm font-normal text-muted">
              {activeFilter === "all" && !stockOnly ? `${detail.volumes.length} cilt` : `${stockOnly ? "Stokta" : activeLabel} · ${volumes.length}`}
            </span>
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="Görünüm" className="flex overflow-hidden rounded-lg border border-line">
              {[
                { key: null, label: "Izgara", icon: "▦" },
                { key: "list", label: "Liste", icon: "☰" },
              ].map((opt) => {
                const active = (opt.key === "list") === listView;
                return (
                  <Link
                    key={opt.label}
                    href={hrefWith({ view: opt.key })}
                    aria-label={`${opt.label} görünümü`}
                    aria-current={active ? "true" : undefined}
                    className={`grid min-h-9 w-10 place-items-center text-base transition-colors ${
                      active ? "bg-accent text-on-accent" : "bg-surface text-muted hover:text-ink"
                    }`}
                  >
                    <span aria-hidden>{opt.icon}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>

        <SortBar
          sorts={SORTS}
          active={activeSort}
          stockOnly={stockOnly}
          hrefFor={(c) => hrefWith({ ...c, all: null })}
        />

        {signedIn && (
          <nav aria-label="Ciltleri koleksiyon durumuna göre filtrele" className="flex flex-wrap gap-2">
            {FILTERS.map((f) => {
              const active = f.value === activeFilter;
              return (
                <Link
                  key={f.value}
                  href={hrefWith({ status: f.value === "all" ? null : f.value, all: null })}
                  aria-current={active ? "page" : undefined}
                  className={`${chip} ${
                    active
                      ? "border-accent bg-accent font-semibold text-on-accent"
                      : "border-line bg-surface text-ink-2 hover:border-line-strong"
                  }`}
                >
                  {f.label}
                </Link>
              );
            })}
          </nav>
        )}

        {volumes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-8 text-center text-sm text-muted">
            {stockOnly
              ? "Şu an stokta cilt yok."
              : activeFilter === "all"
              ? "Bu seri için henüz cilt yok."
              : activeFilter === "wanted"
                ? "Takip ettiğin cilt yok. Kartlardaki zil simgesiyle takibe alabilirsin."
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
            <Link href={hrefWith({ all: "1" })} className={`${chip} border-line bg-surface text-ink-2 hover:border-accent hover:text-accent`}>
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
                  ? "Sahip olduklarını ✓ ile işaretle; eksiklerini tek tıkla takibe al."
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
