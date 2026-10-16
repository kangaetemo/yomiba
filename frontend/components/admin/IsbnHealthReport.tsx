"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { volumePath } from "@/lib/paths";
import { formatDateTime } from "@/lib/time";
import { getIsbnHealth } from "@/services/isbn";
import type { HealthCheckKey, HealthOffer, HealthRow, IsbnHealth } from "@/services/isbn";

const checks: { key: HealthCheckKey; title: string; help: string }[] = [
  { key: "off_by_one", title: "Kayma şüphesi", help: "Mangakol’un bu cilt için önerdiği ISBN aynı serinin komşu cildinde duruyor. Çoğunlukla önceki cildin barkodu yeni cilde kopyalanmıştır." },
  { key: "url_volume_mismatch", title: "Adresi başka cildi gösteren ilanlar", help: "Mağaza ürününün adresindeki cilt numarası bağlı olduğu cildinkiyle tutmuyor. Yanlış cilde bağlanmış olabilir." },
  { key: "volume_price_outlier", title: "Serinin diğer ciltlerinden çok farklı fiyatlı ciltler", help: "Cildin ortanca fiyatı serinin tipik cilt fiyatının yarısından az ya da iki katından fazla. Genelde başka bir baskının (limitli, varyant) fiyatıdır." },
  { key: "listing_price_outlier", title: "Fiyatı diğer mağazalardan çok farklı ilanlar", help: "Aynı cildin diğer mağazalardaki ortanca fiyatından çok farklı (≥1,8× ya da ≤0,55×). En az üç stokta ilanı olan ciltler." },
  { key: "deferred_catalog_isbn", title: "Mangakol’un önerip yazılmayan ISBN’leri", help: "Son katalog senkronunda okunan ama P0 kilidi yüzünden yazılmayan ISBN’ler. Sadece o senkronda yeniden okunan ciltleri kapsar." },
  { key: "missing_isbn", title: "ISBN’siz çıkmış ciltler", help: "Bu ciltlerin ilanları sadece başlıkla eşleşiyor; çakışma kontrolü olmadığı için baskılar karışabilir." },
  { key: "invalid_isbn", title: "Geçersiz ya da şüpheli ISBN’ler", help: "Kontrol basamağı hatalı, kitap barkodu olmayan, ISBN-10 ya da yabancı önekli ISBN’ler." },
  { key: "shared_product", title: "Birden fazla ciltte duran ürün", help: "Aynı mağaza ürünü birden fazla cilde bağlı." },
];
const kinds: Record<string, string> = {
  safe_to_write: "Boş alana güvenle yazılabilir", differs: "Mevcut ISBN’den farklı",
  held_by_other: "Başka bir ciltte tutuluyor", held_by_neighbor: "Komşu ciltte tutuluyor", invalid: "Kontrol basamağı hatalı",
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

function details(key: HealthCheckKey, row: HealthRow) {
  switch (key) {
    case "off_by_one":
      return <>Önerilen {row.source_isbn} → şu an <VolumeLink slug={row.holder?.series_slug} series={row.holder?.series} number={row.holder?.volume_number} /> cildinde</>;
    case "deferred_catalog_isbn":
      return <>{kinds[row.kind ?? ""] ?? row.kind}: {row.source_isbn}{row.holder ? <> · <VolumeLink slug={row.holder.series_slug} series={row.holder.series} number={row.holder.volume_number} /></> : null}</>;
    case "url_volume_mismatch":
      return <>Adreste Cilt {row.url_number} · <Offer offer={row} /></>;
    case "listing_price_outlier":
      return <><Offer offer={row} /> · diğerleri {tl(row.others_median)} (×{row.ratio})</>;
    case "volume_price_outlier":
      return <>Cilt {tl(row.volume_median)}, seri {tl(row.series_median)} (×{row.ratio}) · {(row.offers ?? []).map((o, i) => <span key={i}>{i ? ", " : ""}<Offer offer={o} /></span>)}</>;
    case "missing_isbn":
      return <>{row.listings} ilan, {row.in_stock} stokta</>;
    case "invalid_isbn":
      return <>{problems[row.problem ?? ""] ?? row.problem}</>;
    case "shared_product":
      return <><a href={row.url} target="_blank" rel="noreferrer" className="text-new hover:underline">{row.store}</a> · {(row.volumes ?? []).map((v, i) => <span key={i}>{i ? ", " : ""}<VolumeLink slug={v.series_slug} series={v.series} number={v.volume_number} /></span>)}</>;
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
            <td className="py-1.5 pr-3">{check.key === "shared_product" ? "—" : <VolumeLink slug={row.series_slug} series={row.series} number={row.volume_number} />}</td>
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
  ];
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" className={button} onClick={refresh} disabled={loading}>{loading ? "Yenileniyor…" : "Yenile"}</button>
      <button type="button" className={button} onClick={download}>Raporu indir (JSON)</button>
      <span className="text-sm text-muted">Oluşturuldu: {formatDateTime(report.generated_at)}{report.last_sync_finished_at ? ` · Son katalog senkronu: ${formatDateTime(report.last_sync_finished_at)}` : ""}</span>
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
