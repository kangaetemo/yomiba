import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { BestPriceCard } from "@/components/BestPriceCard";
import { EditionLinks } from "@/components/EditionLinks";
import { StoreListingCard } from "@/components/StoreListingCard";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { CollectionStatusPicker } from "@/components/CollectionStatusPicker";
import { WishlistToggle } from "@/components/WishlistToggle";
import { PriceAlertForm } from "@/components/PriceAlertForm";
import { JsonLd, breadcrumbs } from "@/components/JsonLd";
import { ReportIssue } from "@/components/ReportIssue";
import { RemoveListingButton } from "@/components/admin/RemoveListingButton";
import { VolumeIsbnPanel } from "@/components/admin/VolumeIsbnPanel";
import { Badge, Cover, formatDate, formatTL, volumeTitle } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/time";
import { oneShotVolumeNumber, parseVolumeSegment, seriesPath, volumePath } from "@/lib/paths";
import { SITE_URL, metaDescription, openGraph, pageTitle } from "@/lib/site";
import { publisherPath } from "@/lib/seriesIndex";
import { searchVolumeLabel } from "@/lib/volumeLabel";
import { currentUserOrNull } from "@/services/auth";
import { getPriceAlert, getPriceHistory, getSeries, getVolume, getWishlist } from "@/services/catalog";
import type { PriceAlert, PriceHistory, SeriesDetail, VolumeDetail, VolumeStore, WishlistState } from "@/types";
import { LoginLink } from "@/components/LoginLink";

export const dynamic = "force-dynamic";

interface VolumePageProps {
  params: Promise<{ slug: string; volume: string }>;
}

export async function generateMetadata({
  params,
}: VolumePageProps): Promise<Metadata> {
  try {
    const { series, volumeId } = await resolveVolume(await params);
    const detail = await getVolume(volumeId);
    const name = volumeName(detail, oneShotVolumeNumber(series) !== null);
    const title = pageTitle([`${name} fiyatları - ${detail.series.publisher}`, `${name} fiyatları`]);
    const description = volumeDescription(detail, name);
    const url = volumePath(detail.series.slug, detail.number);
    return {
      title,
      description,
      alternates: { canonical: url },
      openGraph: openGraph({ title, description, url, image: detail.cover_url }),
    };
  } catch {
    return { title: "Cilt bulunamadı" };
  }
}

/** "Berserk 3. Cilt", as people search for it; a one shot is just its
 * series title. */
function volumeName(detail: VolumeDetail, oneShot: boolean): string {
  return oneShot ? detail.series.title : `${detail.series.title} ${searchVolumeLabel(detail.number)}`;
}

/** Search snippet: the lowest price today and how many stores sell it. */
function volumeDescription(detail: VolumeDetail, name: string): string {
  const best = detail.unverified ? null : cheapest(detail.stores);
  const inStock = detail.stores.filter((s) => s.stock && !s.stale && s.price !== null).length;
  return metaDescription([
    best
      ? `${name} (${detail.series.publisher}) ${inStock} mağazada satışta, en ucuz fiyat ${formatTL(best.price)}.`
      : `${name} (${detail.series.publisher}) için Türk kitapçılarındaki fiyatlar ve stok durumu.`,
    "Mağazaları karşılaştır, fiyat geçmişine bak.",
    "Fiyat düşünce haber al.",
  ]);
}

/** schema.org Book for the volume; with buyable offers it is also a Product
 * with an AggregateOffer (Google needs offers on a Product). */
function volumeStructuredData(detail: VolumeDetail, name: string, url: string, best: number | null) {
  const offers = detail.unverified
    ? []
    : detail.stores.filter((s) => s.stock && !s.stale && s.price !== null).map((s) => Number(s.price));
  const image = detail.cover_url ? new URL(detail.cover_url, SITE_URL).href : undefined;
  const book: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": offers.length > 0 && best !== null ? ["Book", "Product"] : "Book",
    name,
    url,
    inLanguage: "tr",
    bookFormat: "https://schema.org/Paperback",
    publisher: { "@type": "Organization", name: detail.series.publisher },
    isPartOf: { "@type": "BookSeries", name: detail.series.title, url: `${SITE_URL}${seriesPath(detail.series.slug)}` },
  };
  if (detail.number !== null && detail.number >= 0) book.volumeNumber = String(detail.number);
  if (image) book.image = image;
  if (detail.series.author) book.author = { "@type": "Person", name: detail.series.author };
  if (detail.series.illustrator && detail.series.illustrator !== detail.series.author) {
    book.illustrator = { "@type": "Person", name: detail.series.illustrator };
  }
  if (detail.isbn) {
    book.isbn = detail.isbn;
    if (/^\d{13}$/.test(detail.isbn)) book.gtin13 = detail.isbn;
  }
  if (detail.page_count) book.numberOfPages = detail.page_count;
  if (detail.release_date) book.datePublished = detail.release_date;
  if (offers.length > 0 && best !== null) {
    book.brand = { "@type": "Brand", name: detail.series.publisher };
    book.offers = {
      "@type": "AggregateOffer",
      priceCurrency: "TRY",
      lowPrice: best.toFixed(2),
      highPrice: Math.max(...offers).toFixed(2),
      offerCount: offers.length,
      availability: "https://schema.org/InStock",
    };
  }
  return book;
}

/** Public URL -> volume: the series comes from the slug, the volume from its
 * number ("cilt-3"). Old numeric series links are sent to the slug URL. */
async function resolveVolume({ slug, volume }: { slug: string; volume: string }) {
  const number = parseVolumeSegment(volume);
  if (number === undefined) notFound();
  let series: SeriesDetail;
  try {
    series = await getSeries(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  if (series.slug !== slug) permanentRedirect(volumePath(series.slug, number));
  const found = series.volumes.find((v) => v.number === number);
  if (!found) notFound();
  return { series, volumeId: found.id };
}

const NEW_DAYS = 14;

function daysSince(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return (Date.now() - new Date(y, m - 1, d).getTime()) / 86_400_000;
}

/** Stores offering the lowest buyable price (in stock, not stale). Every
 * store at that price is marked — never just the first of equals. */
function cheapest(stores: VolumeStore[]): { price: number; stores: string[] } | null {
  const buyable = stores.filter((s) => s.price !== null && s.stock && !s.stale);
  if (buyable.length === 0) return null;
  const price = Math.min(...buyable.map((s) => Number(s.price)));
  return { price, stores: buyable.filter((s) => Number(s.price) === price).map((s) => s.store) };
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-line py-2.5">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="mt-0.5 text-[0.95rem] text-ink-2">{children}</dd>
    </div>
  );
}

export default async function VolumePage({ params }: VolumePageProps) {
  const { series: seriesDetail, volumeId: numId } = await resolveVolume(await params);

  let detail;
  try {
    detail = await getVolume(numId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const user = await currentUserOrNull();
  // Secondary views degrade to empty states; they never break the page.
  const series: SeriesDetail = seriesDetail;
  const [history, wishlist, alertState] = await Promise.all([
    getPriceHistory(numId).catch((): PriceHistory | null => null),
    user ? getWishlist(numId).catch((): WishlistState | null => null) : null,
    user ? getPriceAlert(numId).catch((): { alert: PriceAlert | null } | null => null) : null,
  ]);

  const lowestHistory = history?.lowest ?? [];
  const renderedAt = new Date().getTime();
  const best = detail.unverified ? null : cheapest(detail.stores);
  const buyable = detail.stores.filter((s) => s.stock && !s.stale);
  // A tiny drop (a few kuruş) is not shown as a deal; the store comparison takes its place.
  const deal = detail.price_deal && detail.price_deal.noticeable !== false && best
    && detail.price_deal.new_price === best.price ? detail.price_deal : null;
  const alternativePrices = best && best.stores.length === 1
    ? buyable.filter((s) => s.price !== null && Number(s.price) > best.price).map((s) => Number(s.price)) : [];
  const alternative = alternativePrices.length ? Math.min(...alternativePrices) : null;
  // Out-of-stock offers are never shown to readers; admins still see them
  // (to remove a wrong match).
  const isAdmin = user?.role === "ADMIN";
  const unavailable = isAdmin ? detail.stores.filter((s) => !s.stock || s.stale) : [];
  // Admin only (the API sends it to admins): stores with no record at all
  // here, to tell "does not sell it" from "the import went wrong".
  const missingStores = isAdmin && !detail.unverified ? (detail.missing_stores ?? []) : [];
  const inStock = buyable.length;
  const adminRemove = (listing: VolumeStore) =>
    user?.role === "ADMIN" && listing.id ? (
      <RemoveListingButton volumeId={numId} listingId={listing.id} store={listing.store} />
    ) : undefined;
  const title = volumeTitle(detail.number);
  const isNew = detail.release_date ? daysSince(detail.release_date) <= NEW_DAYS && daysSince(detail.release_date) >= 0 : false;
  const isOneShot = oneShotVolumeNumber(series) !== null;
  const siblings = (series?.volumes ?? []).filter((v) => v.number !== null && v.number >= 0);
  const here = siblings.findIndex((v) => v.id === detail.id);
  // A window of volumes around this one (the whole shelf can be long).
  const related = here < 0 ? siblings.slice(0, 8) : siblings.slice(Math.max(0, here - 3), Math.max(0, here - 3) + 8);
  const credits = detail.series.author && detail.series.author === detail.series.illustrator;
  const name = volumeName(detail, isOneShot);
  const pageUrl = `${SITE_URL}${volumePath(detail.series.slug, detail.number)}`;
  const structured = [
    volumeStructuredData(detail, name, pageUrl, best?.price ?? null),
    breadcrumbs([
      { name: "Yomiba", url: SITE_URL },
      // A one shot's series page only redirects to this one.
      ...(isOneShot ? [] : [{ name: detail.series.title, url: `${SITE_URL}${seriesPath(detail.series.slug)}` }]),
      { name, url: pageUrl },
    ]),
  ];

  return (
    <div className="space-y-12">
      {structured.map((data, i) => <JsonLd key={i} data={data} />)}
      <nav aria-label="Konum" className="flex flex-wrap items-center gap-2 text-sm">
        <Link href="/" className="text-muted hover:text-accent">
          Ana sayfa
        </Link>
        <span aria-hidden className="text-faint">/</span>
        {/* A one shot's series page only redirects back here: no link. */}
        {!isOneShot && (
          <>
            <Link href={seriesPath(detail.series.slug)} className="text-muted hover:text-accent">
              {detail.series.title}
            </Link>
            <span aria-hidden className="text-faint">/</span>
          </>
        )}
        <span className="text-ink-2" aria-current="page">
          {isOneShot ? detail.series.title : title}
        </span>
      </nav>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,19rem)_minmax(0,1fr)] lg:gap-14">
        {/* -- cover + personal actions ------------------------------------------------ */}
        <aside className="space-y-5 lg:sticky lg:top-28 lg:self-start">
          <Cover
            url={detail.cover_url}
            alt={`${detail.series.title} ${title} kapağı`}
            eager
            className="mx-auto w-52 sm:w-60 lg:w-full"
          />
          <div className="space-y-2 rounded-2xl border border-line bg-surface p-3 shadow-card">
            {user ? (
              <>
                <WishlistToggle volumeId={numId} initial={wishlist?.wishlisted ?? false} />
                <CollectionStatusPicker volumeId={numId} initial={detail.collection_status} />
              </>
            ) : (
              <div className="space-y-2 text-sm text-muted">
                <p>İstek listesi, koleksiyon ve fiyat alarmı için giriş yap.</p>
                <div className="flex gap-2">
                  <LoginLink className="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl border border-line-strong font-semibold text-ink hover:border-ink/40">
                    Giriş yap
                  </LoginLink>
                  <LoginLink to="/register" className="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl bg-ink font-semibold text-paper hover:bg-accent">
                    Kayıt ol
                  </LoginLink>
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* -- identity, facts, prices ------------------------------------------------- */}
        <div className="min-w-0 space-y-8">
          <header className="space-y-3">
            <p className="eyebrow">
              {isOneShot ? (
                detail.series.title
              ) : (
                <Link href={seriesPath(detail.series.slug)} className="hover:text-accent">
                  {detail.series.title}
                </Link>
              )}{" "}
              · {detail.series.publisher}
            </p>
            <h1 className="text-[2.2rem] leading-[1.05] font-semibold text-ink sm:text-5xl">
              {/* The space keeps "Berserk Cilt 3" apart in the page text
                  (search snippets, readers); the block span hides it. */}
              {detail.series.title}{" "}
              <span className="mt-1 block text-[0.6em] font-normal text-ink-2">{title}</span>
            </h1>
            <div className="flex flex-wrap gap-2">
              {detail.covers_from && detail.covers_to && (
                <Badge tone="neutral">
                  {detail.covers_to - detail.covers_from + 1} cilt bir arada · {detail.covers_from}–{detail.covers_to}
                </Badge>
              )}
              {isNew && <Badge tone="new">Yeni</Badge>}
              {!detail.unverified && inStock > 0 && (
                <Badge tone="stock" dot>
                  {inStock} mağazada stokta
                </Badge>
              )}
            </div>
          </header>

          {best && (
            <BestPriceCard price={best.price} stores={best.stores} deal={deal} alternative={alternative} />
          )}
          {!best && !detail.unverified && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-surface px-5 py-4">
              <div>
                <p className="font-display text-xl text-ink">Şu an hiçbir mağazada stokta yok</p>
                <p className="mt-1 text-sm text-muted">
                  Hedef fiyatını kaydet; stoğa girip fiyatı düştüğünde görebilirsin.
                </p>
              </div>
              <a href="#alarm-title" className="inline-flex min-h-11 items-center gap-1 font-semibold text-ink-2 hover:text-accent">
                Fiyat alarmı kur <span aria-hidden>↓</span>
              </a>
            </div>
          )}

          <section aria-labelledby="kunye-title" className="space-y-2">
            <h2 id="kunye-title" className="eyebrow">
              Künye
            </h2>
            <dl className="grid grid-cols-2 gap-x-6 sm:grid-cols-3">
              {credits ? (
                <Fact label="Yazar ve çizer">{detail.series.author}</Fact>
              ) : (
                <>
                  {detail.series.author && <Fact label="Yazar">{detail.series.author}</Fact>}
                  {detail.series.illustrator && <Fact label="Çizer">{detail.series.illustrator}</Fact>}
                </>
              )}
              <Fact label="Yayınevi">
                {detail.series.publisher_slug ? (
                  <Link href={publisherPath(detail.series.publisher_slug)} className="underline decoration-line-strong underline-offset-2 hover:text-accent">
                    {detail.series.publisher}
                  </Link>
                ) : (
                  detail.series.publisher
                )}
              </Fact>
              {detail.release_date && (
                <Fact label="Çıkış tarihi">
                  <time dateTime={detail.release_date}>{formatDate(detail.release_date)}</time>
                </Fact>
              )}
              {detail.page_count && <Fact label="Sayfa sayısı">{detail.page_count}</Fact>}
              {detail.isbn && (
                <Fact label="ISBN">
                  <span className="tabular tracking-wide">{detail.isbn}</span>
                </Fact>
              )}
              <Fact label="Dil">Türkçe</Fact>
            </dl>
          </section>

          <section id="magazalar" aria-labelledby="magazalar-title" className="scroll-mt-28 space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="magazalar-title" className="text-2xl font-semibold text-ink">
                Mağaza fiyatları
              </h2>
              <p className="text-xs text-faint">Stokta olanlar, ucuzdan pahalıya</p>
            </div>
            {detail.unverified ? (
              <p className="rounded-2xl border border-warn/30 bg-warn-soft p-6 text-sm text-warn">
                Bu kaydın cilt numarası doğrulanamadı; eski mağaza fiyatları güncel olmadığı için
                gösterilmiyor.
              </p>
            ) : buyable.length === 0 && unavailable.length === 0 && missingStores.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
                Bu cildi şu an stokta satan bir mağaza yok. Fiyatlar düzenli olarak kontrol edilir;
                stoğa giren ilk teklif burada görünür.
              </p>
            ) : (
              <>
                {buyable.length > 0 && (
                  <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
                    {buyable.map((listing) => (
                      <StoreListingCard
                        key={listing.product_url + listing.store}
                        listing={listing}
                        isCheapest={best !== null && listing.price !== null && Number(listing.price) === best.price}
                        adminAction={adminRemove(listing)}
                        deal={deal && deal.listing_id === listing.id ? deal : undefined}
                        comparisonSaving={!deal && best && listing.price !== null && Number(listing.price) === best.price && alternative !== null ? alternative - best.price : undefined}
                      />
                    ))}
                  </div>
                )}
                {unavailable.length > 0 && (
                  <details className="group rounded-2xl border border-dashed border-line-strong bg-surface/60">
                    <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 text-sm font-semibold text-muted hover:text-ink">
                      <span>Admin: stokta olmayan kayıtlar ({unavailable.length}) · ziyaretçiler görmez</span>
                      <span aria-hidden className="transition-transform group-open:rotate-180">⌄</span>
                    </summary>
                    <div className="divide-y divide-line border-t border-line">
                      {unavailable.map((listing) => (
                        <StoreListingCard
                          key={listing.product_url + listing.store}
                          listing={listing}
                          isCheapest={false}
                          adminAction={adminRemove(listing)}
                        />
                      ))}
                    </div>
                  </details>
                )}
                {isAdmin && <VolumeIsbnPanel volumeId={numId} />}
                {missingStores.length > 0 && (
                  <details className="group rounded-2xl border border-dashed border-line-strong bg-surface/60">
                    <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 text-sm font-semibold text-muted hover:text-ink">
                      <span>Admin: bu ciltte kaydı olmayan mağazalar ({missingStores.length}) · ziyaretçiler görmez</span>
                      <span aria-hidden className="transition-transform group-open:rotate-180">⌄</span>
                    </summary>
                    <div className="space-y-2 border-t border-line p-4 text-sm">
                      <p className="text-xs text-faint">
                        Serinin son fiyat taraması:{" "}
                        {detail.last_refresh_at ? formatDateTime(detail.last_refresh_at) : "henüz yok"}
                      </p>
                      <ul className="divide-y divide-line">
                        {missingStores.map((m) => (
                          <li key={m.store} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
                            <span className="font-semibold text-ink-2">{m.store}</span>
                            <span className={m.error ? "text-bad" : "text-muted"}>
                              {m.error
                                ? `Son taramada hata: ${m.error}`
                                : m.series_listings > 0
                                  ? `Bu cildi listelemiyor (seriden ${m.series_listings} başka kaydı var)`
                                  : "Bu seriden hiç kaydı yok"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </details>
                )}
              </>
            )}
          </section>

          {/* Full width, one under the other: the chart needs the room, and
              both headings sit at the same place. */}
          <section aria-labelledby="gecmis-title" className="min-w-0 space-y-3">
            <h2 id="gecmis-title" className="text-lg font-semibold text-ink">
              Fiyat geçmişi
            </h2>
            {lowestHistory.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-line-strong bg-surface/70 p-6 text-sm text-muted">
                Henüz fiyat geçmişi yok. Fiyat her değiştiğinde buraya bir nokta eklenir.
              </p>
            ) : (
              <PriceHistoryChart points={lowestHistory} now={renderedAt} current={best ? { price: best.price, store: best.stores.join(", ") } : null} />
            )}
          </section>
          <section aria-labelledby="alarm-title" className="space-y-3">
            <h2 id="alarm-title" className="text-lg font-semibold text-ink">
              Fiyat alarmı
            </h2>
            <div className="rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
              {user ? (
                <PriceAlertForm
                  volumeId={numId}
                  initialAlert={alertState?.alert ?? null}
                  suggestion={best ? Math.max(1, Math.floor((best.price * 0.9) / 5) * 5) : null}
                />
              ) : (
                <p className="text-sm text-muted">
                  Fiyat istediğin seviyeye inince haber almak için{" "}
                  <LoginLink className="font-semibold text-ink underline decoration-line-strong underline-offset-4 hover:text-accent">
                    giriş yap
                  </LoginLink>
                  .
                </p>
              )}
            </div>
          </section>
          <ReportIssue
            path={volumePath(detail.series.slug, detail.number)}
            stores={[...new Set(buyable.map((s) => s.store))]}
          />
        </div>
      </div>

      {/* A single volume's series page redirects here: its editions live here. */}
      {isOneShot && <EditionLinks editions={series.editions ?? []} />}

      {related.length > 1 && (
        <section aria-labelledby="seri-title" className="space-y-5">
          <div className="rule" aria-hidden />
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="eyebrow">Aynı seriden</p>
              <h2 id="seri-title" className="text-2xl font-semibold text-ink">
                {detail.series.title} ciltleri
              </h2>
            </div>
            <Link href={seriesPath(detail.series.slug)} className="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-ink-2 hover:text-accent">
              Tüm ciltler ({siblings.length}) <span aria-hidden>→</span>
            </Link>
          </div>
          <ul className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-4 sm:overflow-visible sm:px-0 lg:grid-cols-8">
            {related.map((v) => {
              const current = v.id === detail.id;
              return (
                <li key={v.id} className="w-28 shrink-0 snap-start sm:w-auto">
                  <Link
                    href={volumePath(detail.series.slug, v.number)}
                    aria-current={current ? "page" : undefined}
                    className={`group block space-y-2 ${current ? "pointer-events-none" : ""}`}
                  >
                    <div className={`rounded-[7px] ${current ? "ring-2 ring-accent ring-offset-2 ring-offset-paper" : ""}`}>
                      <Cover url={v.cover_url ?? null} alt={`${detail.series.title} ${volumeTitle(v.number)}`} className="w-full" />
                    </div>
                    <p className={`text-sm font-semibold ${current ? "text-accent" : "text-ink group-hover:text-accent"}`}>
                      {volumeTitle(v.number)}
                    </p>
                    <p className="tabular text-xs text-muted">
                      {v.in_stock_count > 0 && v.best_price !== null ? formatTL(v.best_price) : "Stokta yok"}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
