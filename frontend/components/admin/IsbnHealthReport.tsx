"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { volumePath } from "@/lib/paths";
import { formatDateTime } from "@/lib/time";
import { getIsbnHealth } from "@/services/isbn";
import type { HealthCheckKey, HealthOffer, HealthRow, IsbnHealth } from "@/services/isbn";

const checks: { key: HealthCheckKey; title: string; help: string }[] = [
  { key: "search_miss", title: "Mağazanın aramasında artık çıkmayan ilanlar", help: "Ürün sayfası hâlâ stokta diyor (sistem oradan güncelliyor), ama mağazanın araması 48 saattir bu ürünü döndürmüyor. Genelde aramanın seri adını başka ürünlerle karıştırmasıdır (BKM'de “Mavi Kutu” gibi); tarayıcının sorgusu düzeltilmeli." },
  { key: "stale_listing", title: "Bayatlamış ilanlar (sitede gizli)", help: "Mağaza taranıyor ama bu ilan uzun süredir güncellenmedi; sitede gösterilmiyor. Ürün kaldırılmış ya da arama artık bulamıyor olabilir. Ürün sayfası okunabilen mağazalarda (BKM, Kitapseç, Kitap Sepeti, Kitapbulan, Edessa, İstanbul Kitapçısı) sistem önce sayfadan kontrol eder." },
  { key: "suspect_listing", title: "Şüpheli ilanlar", help: "Başlığı kitap dışı ya da başka bir baskıyı gösteriyor (sezon, DVD, novel…), yayınevi bizdekinden farklı ya da bağlantı mağazanın sitesi dışına gidiyor. Kontrol edin; yanlışsa cilt sayfasından kaldırın." },
  { key: "isbn_issues", title: "Otomatik çözülemeyen ISBN çelişkileri", help: "Kanıtlar çelişiyor; sistem hiçbir şeyi değiştirmedi. Cilt sayfasındaki admin ISBN panelinden karar verebilirsiniz." },
  { key: "catalog_duplicate", title: "Mangakol’un iki farklı kitaba verdiği ISBN’ler", help: "Kaynak hatası (Blue Lock 28/29 gibi). Bu ISBN hiçbir cilde kendiliğinden yazılmaz; mağaza kanıtı ya da admin kararı bekler. Aynı kitabın baskıları burada sayılmaz." },
  { key: "title_isbn_conflict", title: "Başlığı bir cildi, ISBN’i başka cildi gösteren ürünler", help: "Mağazanın başlığına göre bağlandı (son 90 gün). Mağazanın ISBN’i ya da bizim ISBN’imiz yanlış; buradan kontrol edin, gerekirse cilt sayfasından düzeltin." },
  { key: "catalog_differs", title: "Mangakol’dan farklı ISBN’li ciltler", help: "Kararlaştırılmış ISBN ile Mangakol’un listelediği farklı (ya da cilt hâlâ ISBN’siz). Sebep çoğunlukla Mangakol hatası ya da henüz uzlaşı olmaması." },
  { key: "volume_price_outlier", title: "Serinin diğer ciltlerinden çok farklı fiyatlı ciltler", help: "Cildin ortanca fiyatı serinin tipik cilt fiyatının yarısından az ya da iki katından fazla. Genelde başka bir baskının (limitli, varyant) fiyatıdır." },
  { key: "listing_price_outlier", title: "Fiyatı diğer mağazalardan çok farklı ilanlar", help: "Aynı cildin diğer mağazalardaki ortanca fiyatından çok farklı (≥1,8× ya da ≤0,55×). Düşük olanlar çoğunlukla gerçek indirimdir; yüksek olanlar başka bir baskı olabilir. Hiçbiri gizlenmez." },
  { key: "missing_isbn", title: "ISBN’siz çıkmış ciltler", help: "Bu ciltlerin ilanları sadece başlıkla eşleşiyor. Henüz çıkmamış ciltler sayılmaz." },
  { key: "invalid_isbn", title: "Geçersiz ya da şüpheli ISBN’ler", help: "Kontrol basamağı hatalı, kitap barkodu olmayan, ISBN-10 ya da yabancı önekli ISBN’ler." },
  { key: "shared_product", title: "Birden fazla ciltte duran ürün", help: "Aynı mağaza ürünü birden fazla cilde bağlı." },
  { key: "recent_changes", title: "Son ISBN değişiklikleri", help: "Her otomatik ve admin değişikliği kaynağı ve gerekçesiyle kaydedilir (son 300)." },
];
const kinds: Record<string, string> = {
  empty: "Bizde boş", differs: "Farklı",
  catalog_duplicate: "Mangakol aynı ISBN’i başka kitaba da vermiş", catalog_differs: "Mangakol farklı diyor, mağaza kanıtı yok",
  stores_vs_catalog: "Mağazalar Mangakol’la çelişiyor", stores_disagree: "Mağazalar kendi aralarında çelişiyor",
  isbn_claimed: "ISBN başka bir ciltte",
};
const sources: Record<string, string> = {
  catalog: "Mangakol", stores: "mağaza uzlaşısı", admin: "admin", legacy: "eski kayıt",
  moved: "taşındı", shared: "ortak baskı", unshared: "ortaklık kaldırıldı",
};
const problems: Record<string, string> = {
  checksum: "Kontrol basamağı hatalı", not_book_barcode: "Kitap barkodu değil", isbn10: "ISBN-10", foreign: "Yabancı ISBN",
};
const button = "rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-sm font-semibold text-ink hover:bg-line disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const tl = (value: number | null | undefined) => value == null ? "—" : `${value.toLocaleString("tr-TR", { maximumFractionDigits: 2 })} TL`;
const PAGE = 100;

function VolumeLink({ slug, series, number }: { slug: string | null | undefined; series: string | null | undefined; number: number | undefined }) {
  const label = `${series ?? "?"}${number != null ? ` · Cilt ${number}` : ""}`;
  if (!slug || number == null) return <span>{label}</span>;
  return <Link href={volumePath(slug, number)} className="text-new hover:underline">{label}</Link>;
}

function Offer({ offer }: { offer: Partial<HealthOffer> }) {
  return <span>
    {offer.url ? <a href={offer.url} target="_blank" rel="noreferrer" className="text-new hover:underline">{offer.store}</a> : offer.store}
    {" "}{tl(offer.price)}{offer.in_stock === false ? " (stokta yok)" : ""}
  </span>;
}

function Ref({ v }: { v: HealthRow["title_volume"] }) {
  return v ? <VolumeLink slug={v.series_slug} series={v.series} number={v.volume_number} /> : <span>—</span>;
}

function details(key: HealthCheckKey, row: HealthRow) {
  switch (key) {
    case "isbn_issues":
      return <>{kinds[row.kind ?? ""] ?? row.kind} · <span className="font-mono text-xs">{JSON.stringify(row.detail)}</span></>;
    case "catalog_duplicate":
      return <>{(row.volumes ?? []).map((v, i) => <span key={i}>{i ? ", " : ""}<VolumeLink slug={v.series_slug} series={v.series} number={v.volume_number} /> ({v.isbn ?? "boş"})</span>)}</>;
    case "title_isbn_conflict":
      return <><Offer offer={row} /> “{row.title}” · başlık: <Ref v={row.title_volume} /> · ISBN: <Ref v={row.isbn_volume} /></>;
    case "catalog_differs":
      return <>{kinds[row.kind ?? ""]} · Mangakol {row.catalog_isbn}{row.isbn_source ? ` · bizdeki: ${sources[row.isbn_source] ?? row.isbn_source}` : ""}</>;
    case "listing_price_outlier":
      return <><Offer offer={row} /> · diğerleri {tl(row.others_median)} (×{row.ratio})</>;
    case "volume_price_outlier":
      return <>Cilt {tl(row.volume_median)}, seri {tl(row.series_median)} (×{row.ratio}) · {(row.offers ?? []).map((o, i) => <span key={i}>{i ? ", " : ""}<Offer offer={o} /></span>)}</>;
    case "missing_isbn":
      return <>{row.listings} ilan, {row.in_stock} stokta{row.catalog_isbn ? ` · Mangakol: ${row.catalog_isbn}` : ""}</>;
    case "invalid_isbn":
      return <>{problems[row.problem ?? ""] ?? row.problem}</>;
    case "shared_product":
      return <><a href={row.url} target="_blank" rel="noreferrer" className="text-new hover:underline">{row.store}</a> · {(row.volumes ?? []).map((v, i) => <span key={i}>{i ? ", " : ""}<VolumeLink slug={v.series_slug} series={v.series} number={v.volume_number} /></span>)}</>;
    case "search_miss":
    case "stale_listing":
      return <><Offer offer={row} /> · son kontrol {row.last_checked ? formatDateTime(row.last_checked) : "—"} · aramada son görülme {row.seen_in_search ? formatDateTime(row.seen_in_search) : "—"}</>;
    case "suspect_listing":
      return <><Offer offer={row} />{row.title ? <> “{row.title}”</> : null} · {(row.reasons ?? []).join(" · ")}</>;
    case "recent_changes":
      return <>{row.old_isbn ?? "boş"} → {row.new_isbn ?? "boş"} · {sources[row.source ?? ""] ?? row.source} · {row.reason}{row.at ? ` · ${formatDateTime(row.at)}` : ""}</>;
  }
}

function CheckSection({ check, data }: { check: (typeof checks)[number]; data: { count: number; items: HealthRow[] } }) {
  const [shown, setShown] = useState(PAGE);
  const rows = data.items.slice(0, shown);
  return <details className="rounded-xl border border-line bg-surface">
    <summary className="flex cursor-pointer items-center justify-between gap-3 p-4">
      <span className="font-semibold text-ink">{check.title}</span>
      <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${data.count ? "bg-accent text-on-accent" : "bg-surface-2 text-muted"}`}>{data.count.toLocaleString("tr-TR")}</span>
    </summary>
    <div className="space-y-3 border-t border-line p-4">
      <p className="text-sm text-muted">{check.help}</p>
      {data.count === 0 ? <p className="text-sm text-muted">Kayıt yok.</p> : <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-muted"><tr><th className="py-1 pr-3 font-medium">Cilt</th><th className="py-1 pr-3 font-medium">ISBN</th><th className="py-1 font-medium">Ayrıntı</th></tr></thead>
          <tbody>{rows.map((row, i) => <tr key={i} className="border-t border-line align-top">
            <td className="py-1.5 pr-3">{["shared_product", "catalog_duplicate", "title_isbn_conflict"].includes(check.key) ? "—" : <VolumeLink slug={row.series_slug} series={row.series} number={row.volume_number} />}</td>
            <td className="py-1.5 pr-3 font-mono text-xs">{row.isbn ?? "—"}</td>
            <td className="py-1.5">{details(check.key, row)}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {data.items.length > shown && <button type="button" className={button} onClick={() => setShown(n => n + PAGE)}>
        {PAGE} kayıt daha göster ({data.items.length - shown} kaldı)
      </button>}
      {data.count > data.items.length && <p className="text-xs text-muted">İlk {data.items.length} kayıt gösteriliyor; toplam {data.count}.</p>}
    </div>
  </details>;
}

export function IsbnHealthReport() {
  const [report, setReport] = useState<IsbnHealth | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => { setLoading(true); setRevision(n => n + 1); }, []);

  useEffect(() => {
    const controller = new AbortController();
    getIsbnHealth(controller.signal)
      .then(r => { setReport(r); setError(""); })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Rapor alınamadı."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  function download() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 1)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `isbn-saglik-${report.generated_at.slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) return <p role="alert" className="text-sm text-warn">{error}</p>;
  if (!report) return <p role="status" className="text-sm text-muted">Rapor hazırlanıyor…</p>;
  const t = report.totals;
  const cards: [string, number][] = [
    ["Katalogdaki cilt", t.catalog_volumes], ["Çıkmış cilt", t.released_volumes],
    ["ISBN’li çıkmış cilt", t.released_with_isbn], ["ISBN’siz çıkmış cilt", t.released_without_isbn],
    ["ISBN’siz ama ilanı olan", t.without_isbn_but_listed], ["Toplam ilan", t.listings],
    ["Mangakol ISBN’i okunan", t.catalog_isbn_read], ["Mağaza gözlemi", t.observations],
  ];
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" className={button} onClick={refresh} disabled={loading}>{loading ? "Yenileniyor…" : "Yenile"}</button>
      <button type="button" className={button} onClick={download}>Raporu indir (JSON)</button>
      <span className="text-sm text-muted">Oluşturuldu: {formatDateTime(report.generated_at)}</span>
    </div>
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {cards.map(([label, value]) => <div key={label} className="rounded-xl border border-line bg-surface p-3">
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="text-xl font-bold text-ink">{value.toLocaleString("tr-TR")}</dd>
      </div>)}
    </dl>
    <div className="space-y-3">
      {checks.map(check => <CheckSection key={check.key} check={check} data={report.checks[check.key]} />)}
    </div>
  </div>;
}
