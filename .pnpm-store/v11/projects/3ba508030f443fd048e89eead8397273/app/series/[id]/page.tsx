import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CoverImage } from "@/components/SeriesCard";
import { VolumeCard } from "@/components/VolumeCard";
import { ApiError } from "@/lib/api";
import { getSeries } from "@/services/catalog";
import type { CollectionStatus, SeriesVolume } from "@/types";

export const dynamic = "force-dynamic";

interface SeriesPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ status?: string; all?: string }>;
}

const FILTERS: { value: CollectionStatus | "all"; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "owned", label: "Sahibim" },
  { value: "missing", label: "Eksik" },
  { value: "wanted", label: "İstediğim" },
];

/** Default view shows the first N volumes; the rest sit behind the
 * "+N cilt daha göster" toggle (server-rendered via ?all=1). With an
 * active status filter the list is never capped — it is a drill-down. */
const SHOW_FIRST = 12;

/** Compact header line: "19 cilt" plus the best-price span, e.g.
 * "19 cilt · ₺182–₺260". Compact (no decimals unless needed) so it fits. */
function seriesOverview(volumes: SeriesVolume[]): string {
  const count = volumes.length;
  const base = `${count} cilt`;
  const prices = volumes
    .map((v) => v.best_price)
    .filter((p): p is number => p !== null);
  if (prices.length === 0) return base;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const fmt = (v: number) =>
    Number.isInteger(v) ? String(v) : v.toFixed(2);
  return min === max
    ? `${base} · ₺${fmt(min)}`
    : `${base} · ₺${fmt(min)}–₺${fmt(max)}`;
}

export async function generateMetadata({
  params,
}: SeriesPageProps): Promise<Metadata> {
  const { id } = await params;
  const numId = Number(id);
  if (!Number.isInteger(numId) || numId <= 0) return { title: "Seri bulunamadı" };
  try {
    const detail = await getSeries(numId);
    return { title: `${detail.title} — ${detail.publisher}` };
  } catch {
    return { title: "Seri bulunamadı" };
  }
}

export default async function SeriesPage({
  params,
  searchParams,
}: SeriesPageProps) {
  const { id } = await params;
  const numId = Number(id);
  if (!Number.isInteger(numId) || numId <= 0) notFound();

  let detail;
  try {
    detail = await getSeries(numId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  // Collection filter: only the three known statuses; anything else
  // (absent or typo'd) means "all".
  const { status: rawStatus, all } = await searchParams;
  const activeFilter: CollectionStatus | "all" =
    rawStatus === "owned" || rawStatus === "missing" || rawStatus === "wanted"
      ? rawStatus
      : "all";
  const volumes =
    activeFilter === "all"
      ? detail.volumes
      : detail.volumes.filter((v) => v.collection_status === activeFilter);
  const activeLabel =
    FILTERS.find((f) => f.value === activeFilter)?.label ?? "Tümü";

  // Volume cap: only in the unfiltered view; ?all=1 lifts it.
  const expanded = activeFilter !== "all" || all === "1";
  const visibleVolumes = expanded ? volumes : volumes.slice(0, SHOW_FIRST);
  const hiddenCount = volumes.length - visibleVolumes.length;
  const statusSuffix = activeFilter === "all" ? "" : `?status=${activeFilter}`;
  const showAllHref = `/series/${numId}${
    statusSuffix ? `${statusSuffix}&all=1` : "?all=1"
  }`;
  const toggleClasses =
    "rounded-lg border border-neutral-800 bg-neutral-900 px-4 py-2 text-sm text-neutral-300 transition-colors hover:border-orange-500 hover:text-orange-400";

  return (
    <div className="space-y-8">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-orange-400"
      >
        ← Aramaya dön
      </Link>

      <section className="flex gap-6">
        <CoverImage
          url={detail.cover_url}
          alt={detail.title}
          className="h-44 w-32 sm:h-52 sm:w-36"
        />
        <div className="flex flex-col justify-center gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-neutral-50">
            {detail.title}
          </h1>
          <p className="text-base text-neutral-400">{detail.publisher}</p>
          <p className="text-sm text-neutral-500">{seriesOverview(detail.volumes)}</p>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-neutral-100">
            Ciltler
            {activeFilter !== "all" && (
              <span className="ml-2 text-sm font-normal text-neutral-500">
                · {activeLabel}
              </span>
            )}
          </h2>
          <nav aria-label="Ciltleri koleksiyon durumuna göre filtrele" className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => {
              const active = f.value === activeFilter;
              const href =
                f.value === "all"
                  ? `/series/${numId}`
                  : `/series/${numId}?status=${f.value}`;
              return (
                <Link
                  key={f.value}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg border px-2.5 py-1 text-xs transition-colors ${
                    active
                      ? "border-orange-500 bg-orange-500/10 text-orange-400"
                      : "border-neutral-800 bg-neutral-900 text-neutral-400 hover:border-neutral-600 hover:text-neutral-200"
                  }`}
                >
                  {f.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {volumes.length === 0 ? (
          <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-8 text-center text-sm text-neutral-500">
            {activeFilter === "all"
              ? "Bu seri için henüz cilt içe aktarılmadı."
              : `“${activeLabel}” olarak işaretlenmiş cilt yok — bir cildi açıp işaretleyin.`}
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              {visibleVolumes.map((volume) => (
                <VolumeCard key={volume.id} volume={volume} />
              ))}
            </div>
            {hiddenCount > 0 && (
              <div className="flex justify-center pt-1">
                <Link
                  href={showAllHref}
                  className={toggleClasses}
                >
                  +{hiddenCount} cilt daha göster
                </Link>
              </div>
            )}
            {activeFilter === "all" && all === "1" && volumes.length > SHOW_FIRST && (
              <div className="flex justify-center pt-1">
                <Link href={`/series/${numId}`} className={toggleClasses}>
                  Daha az göster
                </Link>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
