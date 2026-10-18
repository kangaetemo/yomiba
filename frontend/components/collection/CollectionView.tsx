"use client";

/**
 * CollectionView: the Koleksiyonum page's three lists — collection (per
 * series, with completion), wishlist (grouped by series) and price alerts —
 * as tabs, each with a search box, filters and a sort order. Everything runs
 * on the already loaded lists (a reader's lists are small), so typing and
 * filtering are instant. The tab is kept in the URL (?sekme=) for sharing
 * and the back button.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge, Cover, formatTL } from "@/components/ui";
import { seriesPath, volumePath } from "@/lib/paths";
import { volumeLabel } from "@/lib/volumeLabel";
import type { MyCollectionItem, MyPriceAlert, MyVolume, MyWishlistItem } from "@/types";

export type CollectionTab = "koleksiyon" | "istek" | "alarm";

/** Case- and accent-insensitive Turkish search key ("Şifacı" ~ "sifaci"). */
function key(text: string): string {
  return text
    .toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

const TR = new Intl.Collator("tr-TR", { sensitivity: "base", numeric: true });
const byNumber = (a: MyVolume, b: MyVolume) => (a.volume_number ?? 1e6) - (b.volume_number ?? 1e6);
const latest = (dates: string[]) => dates.reduce((m, d) => (d > m ? d : m), "");

// -- small controls ------------------------------------------------------------------

function SearchBox({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="relative block min-w-0 flex-1 basis-56">
      <span className="sr-only">{label}</span>
      <svg aria-hidden viewBox="0 0 24 24" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Seri ara…"
        className="min-h-10 w-full rounded-lg border border-line bg-surface pr-3 pl-9 text-sm text-ink placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none"
      />
    </label>
  );
}

function Select<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string;
}) {
  return (
    <label className="relative inline-flex">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="min-h-10 appearance-none rounded-lg border border-line bg-surface pr-9 pl-3 text-sm font-semibold text-ink-2 hover:border-line-strong focus-visible:border-accent"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <svg aria-hidden viewBox="0 0 24 24" className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </label>
  );
}

function Chips<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[]; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="-mx-4 max-w-[calc(100%+2rem)] overflow-x-auto px-4 sm:mx-0 sm:max-w-full sm:px-0">
      <div className="inline-flex gap-0.5 rounded-lg bg-surface-2 p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={o.value === value}
            onClick={() => onChange(o.value)}
            className={`inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm whitespace-nowrap transition-colors ${
              o.value === value ? "bg-surface font-semibold text-ink shadow-card" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
            {o.count !== undefined && <span className="tabular text-xs text-faint">{o.count}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-6 text-center text-sm text-muted">{children}</div>
  );
}

const grid = "grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5";

/** A cover-first volume card (wishlist / alerts). */
function VolumeTile({ item, badge, footer, showSeries = true }: {
  item: MyVolume; badge?: React.ReactNode; footer: React.ReactNode; showSeries?: boolean;
}) {
  const href = volumePath(item.series_slug, item.volume_number);
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card transition-shadow hover:shadow-lift">
      <Link href={href} className="group relative block px-3 pt-3" aria-label={`${item.series_title} ${volumeLabel(item.volume_number)}`}>
        <Cover url={item.cover_url} alt={`${item.series_title} ${volumeLabel(item.volume_number)} kapağı`} className="w-full transition-transform duration-300 group-hover:-translate-y-0.5" />
        {badge && <span className="absolute top-5 left-5">{badge}</span>}
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="min-w-0">
          {showSeries && <p className="eyebrow truncate">{item.series_title}</p>}
          <Link href={href} className="text-[1.02rem] font-semibold text-ink hover:text-accent">{volumeLabel(item.volume_number)}</Link>
        </div>
        <div className="mt-auto border-t border-line pt-2">{footer}</div>
      </div>
    </li>
  );
}

function Price({ price }: { price: number | null }) {
  return price !== null ? (
    <div>
      <p className="text-[0.7rem] text-faint">En düşük fiyat</p>
      <p className="tabular text-lg leading-tight font-bold text-ink">{formatTL(price)}</p>
    </div>
  ) : (
    <div>
      <p className="text-[0.7rem] text-faint">Şu an satışta değil</p>
      <p className="tabular text-lg leading-tight font-bold text-faint">—</p>
    </div>
  );
}

// -- collection: one card per series -----------------------------------------------------

interface SeriesGroup {
  id: number;
  slug: string;
  title: string;
  publisher: string;
  cover: string | null;
  owned: number;
  missing: number;
  total: number;
  updated: string;
}

type CollectionFilter = "all" | "done" | "open" | "missing";
type CollectionSort = "az" | "most" | "closest" | "recent";

function groupCollection(items: MyCollectionItem[]): SeriesGroup[] {
  const groups = new Map<number, SeriesGroup>();
  for (const item of items) {
    const g = groups.get(item.series_id) ?? {
      id: item.series_id, slug: item.series_slug, title: item.series_title, publisher: item.publisher,
      cover: null, owned: 0, missing: 0, total: item.series_volume_count ?? 0, updated: "",
    };
    g.cover ??= item.cover_url;
    if (item.status === "owned") g.owned += 1;
    else g.missing += 1;
    g.updated = latest([g.updated, item.updated_at]);
    groups.set(item.series_id, g);
  }
  return [...groups.values()];
}

const complete = (g: SeriesGroup) => g.total > 0 && g.owned >= g.total;

function SeriesCard({ g }: { g: SeriesGroup }) {
  const href = seriesPath(g.slug);
  const pct = g.total > 0 ? Math.min(100, Math.round((g.owned / g.total) * 100)) : 0;
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card transition-shadow hover:shadow-lift">
      <Link href={href} className="group relative block px-3 pt-3" aria-label={g.title}>
        <Cover url={g.cover} alt={`${g.title} kapağı`} className="w-full transition-transform duration-300 group-hover:-translate-y-0.5" />
        {complete(g) && <span className="absolute top-5 left-5"><Badge tone="stock">Tamamlandı</Badge></span>}
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="min-w-0">
          <Link href={href} className="line-clamp-2 text-[1.02rem] leading-snug font-semibold text-ink hover:text-accent">{g.title}</Link>
          <p className="truncate text-xs text-muted">{g.publisher}</p>
        </div>
        <div className="mt-auto space-y-1.5 border-t border-line pt-2">
          {g.total > 0 && (
            <>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="text-muted">Sende</span>
                <span className="tabular font-semibold text-ink">{g.owned} / {g.total} cilt</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuemin={0} aria-valuemax={g.total} aria-valuenow={g.owned} aria-label={`${g.title}: ${g.total} ciltten ${g.owned} tanesi sende`}>
                <div className={`h-full rounded-full ${complete(g) ? "bg-ok" : "bg-accent"}`} style={{ width: `${pct}%` }} />
              </div>
            </>
          )}
          {g.missing > 0 && (
            <Link href={`${href}?status=missing`} className="inline-block text-xs text-muted hover:text-accent">
              “Bende yok” işaretli: {g.missing}
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

function CollectionTabPanel({ items }: { items: MyCollectionItem[] }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<CollectionFilter>("all");
  const [sort, setSort] = useState<CollectionSort>("az");
  const groups = useMemo(() => groupCollection(items), [items]);
  const counts = {
    all: groups.length,
    done: groups.filter(complete).length,
    open: groups.filter((g) => g.owned > 0 && !complete(g)).length,
    missing: groups.filter((g) => g.missing > 0).length,
  };
  const shown = groups
    .filter((g) => !q || key(g.title).includes(key(q)) || key(g.publisher).includes(key(q)))
    .filter((g) => filter === "all" || (filter === "done" ? complete(g) : filter === "open" ? g.owned > 0 && !complete(g) : g.missing > 0))
    .sort((a, b) => {
      if (sort === "most") return b.owned - a.owned || TR.compare(a.title, b.title);
      if (sort === "closest") {
        const left = (g: SeriesGroup) => (g.total > g.owned ? g.total - g.owned : 1e6);
        return left(a) - left(b) || TR.compare(a.title, b.title);
      }
      if (sort === "recent") return b.updated.localeCompare(a.updated);
      return TR.compare(a.title, b.title);
    });

  if (items.length === 0) return <Empty>Henüz işaretlediğin cilt yok. Bir cildi açıp “Bende var” ya da “Bende yok” seç.</Empty>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox value={q} onChange={setQ} label="Koleksiyonda seri ara" />
        <Select label="Sırala" value={sort} onChange={setSort} options={[
          { value: "az", label: "A → Z" },
          { value: "most", label: "En çok cilt" },
          { value: "closest", label: "Tamamlanmaya en yakın" },
          { value: "recent", label: "Son güncellenen" },
        ]} />
      </div>
      <Chips label="Seri durumu" value={filter} onChange={setFilter} options={[
        { value: "all", label: "Tümü", count: counts.all },
        { value: "open", label: "Devam eden", count: counts.open },
        { value: "done", label: "Tamamlanan", count: counts.done },
        { value: "missing", label: "Bende yok", count: counts.missing },
      ]} />
      {shown.length === 0 ? <Empty>Bu filtreye uyan seri yok.</Empty> : (
        <ul className={grid}>{shown.map((g) => <SeriesCard key={g.id} g={g} />)}</ul>
      )}
    </div>
  );
}

// -- wishlist: grouped by series ---------------------------------------------------------

type WishSort = "az" | "cheapest" | "recent";

function WishlistTabPanel({ items }: { items: MyWishlistItem[] }) {
  const [q, setQ] = useState("");
  const [stockOnly, setStockOnly] = useState(false);
  const [sort, setSort] = useState<WishSort>("az");
  const groups = useMemo(() => {
    const map = new Map<number, MyWishlistItem[]>();
    for (const item of items) map.set(item.series_id, [...(map.get(item.series_id) ?? []), item]);
    return [...map.values()].map((vols) => {
      const sorted = [...vols].sort(byNumber);
      const priced = sorted.filter((v) => v.best_price !== null);
      return {
        id: sorted[0].series_id, slug: sorted[0].series_slug, title: sorted[0].series_title,
        publisher: sorted[0].publisher, vols: sorted, inStock: priced.length,
        sum: priced.reduce((s, v) => s + (v.best_price ?? 0), 0), added: latest(sorted.map((v) => v.added_at)),
      };
    });
  }, [items]);
  const inStockTotal = groups.reduce((s, g) => s + g.inStock, 0);
  const shown = groups
    .filter((g) => !q || key(g.title).includes(key(q)) || key(g.publisher).includes(key(q)))
    .map((g) => (stockOnly ? { ...g, vols: g.vols.filter((v) => v.best_price !== null) } : g))
    .filter((g) => g.vols.length > 0)
    .sort((a, b) => {
      if (sort === "cheapest") return (a.inStock ? a.sum : 1e9) - (b.inStock ? b.sum : 1e9) || TR.compare(a.title, b.title);
      if (sort === "recent") return b.added.localeCompare(a.added);
      return TR.compare(a.title, b.title);
    });

  if (items.length === 0) return <Empty>İstek listen boş. Cilt kartlarındaki yer imi simgesiyle ekleyebilirsin.</Empty>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox value={q} onChange={setQ} label="İstek listesinde seri ara" />
        <Select label="Sırala" value={sort} onChange={setSort} options={[
          { value: "az", label: "A → Z" },
          { value: "cheapest", label: "Toplamı en ucuz" },
          { value: "recent", label: "Son eklenen" },
        ]} />
        <button
          type="button"
          aria-pressed={stockOnly}
          onClick={() => setStockOnly((v) => !v)}
          className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold transition-colors ${
            stockOnly ? "border-ok/40 bg-ok-soft text-ok" : "border-line bg-surface text-ink-2 hover:border-line-strong"
          }`}
        >
          <span aria-hidden className={`size-2 rounded-full ${stockOnly ? "bg-ok" : "border border-ok"}`} />
          Sadece stokta <span className="tabular text-xs font-normal opacity-70">{inStockTotal}</span>
        </button>
      </div>
      {shown.length === 0 ? <Empty>Bu filtreye uyan cilt yok.</Empty> : (
        <div className="space-y-8">
          {shown.map((g) => (
            <section key={g.id} aria-labelledby={`istek-${g.id}`} className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line pb-2">
                <h3 id={`istek-${g.id}`} className="min-w-0 text-lg font-semibold text-ink">
                  <Link href={seriesPath(g.slug)} className="hover:text-accent">{g.title}</Link>{" "}
                  <span className="font-sans text-sm font-normal text-muted">· {g.publisher}</span>
                </h3>
                <p className="text-sm text-muted">
                  {g.vols.length} cilt
                  {g.inStock > 0 ? <> · {g.inStock} stokta · toplam <span className="tabular font-semibold text-ink">{formatTL(g.sum)}</span></> : " · şu an stokta yok"}
                </p>
              </div>
              <ul className={grid}>
                {g.vols.map((v) => <VolumeTile key={v.volume_id} item={v} showSeries={false} footer={<Price price={v.best_price} />} />)}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

// -- price alerts ---------------------------------------------------------------------

type AlertFilter = "all" | "hit" | "on" | "off";
type AlertSort = "closest" | "az";

const target = (a: MyPriceAlert) => a.threshold_price / 100;
const hit = (a: MyPriceAlert) => a.best_price !== null && a.best_price <= target(a);

function AlertsTabPanel({ items }: { items: MyPriceAlert[] }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<AlertFilter>("all");
  const [sort, setSort] = useState<AlertSort>("closest");
  const counts = { all: items.length, hit: items.filter(hit).length, on: items.filter((a) => a.is_active).length, off: items.filter((a) => !a.is_active).length };
  const gap = (a: MyPriceAlert) => (a.best_price === null ? 1e9 : a.best_price / target(a));
  const shown = items
    .filter((a) => !q || key(a.series_title).includes(key(q)))
    .filter((a) => filter === "all" || (filter === "hit" ? hit(a) : filter === "on" ? a.is_active : !a.is_active))
    .sort((a, b) => (sort === "closest" ? gap(a) - gap(b) : 0) || TR.compare(a.series_title, b.series_title) || byNumber(a, b));

  if (items.length === 0) return <Empty>Kurulu fiyat alarmın yok. Bir cildin sayfasından hedef fiyat koyabilirsin.</Empty>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox value={q} onChange={setQ} label="Alarmlarda seri ara" />
        <Select label="Sırala" value={sort} onChange={setSort} options={[
          { value: "closest", label: "Hedefe en yakın" },
          { value: "az", label: "A → Z" },
        ]} />
      </div>
      <Chips label="Alarm durumu" value={filter} onChange={setFilter} options={[
        { value: "all", label: "Tümü", count: counts.all },
        { value: "hit", label: "Hedefte", count: counts.hit },
        { value: "on", label: "Açık", count: counts.on },
        { value: "off", label: "Kapalı", count: counts.off },
      ]} />
      {shown.length === 0 ? <Empty>Bu filtreye uyan alarm yok.</Empty> : (
        <ul className={grid}>
          {shown.map((a) => (
            <VolumeTile
              key={a.volume_id}
              item={a}
              badge={hit(a) ? <Badge tone="deal">Hedefte</Badge> : <Badge tone={a.is_active ? "alert" : "neutral"}>{a.is_active ? "Alarm açık" : "Alarm kapalı"}</Badge>}
              footer={
                <div className="space-y-1">
                  <p className="text-[0.7rem] text-faint">Hedef fiyat</p>
                  <p className={`tabular text-lg leading-tight font-bold ${a.is_active ? "text-ok" : "text-muted"}`}>≤ {formatTL(target(a))}</p>
                  <p className="text-xs text-muted">{a.best_price !== null ? `Şu an ${formatTL(a.best_price)}` : "Şu an satışta değil"}</p>
                </div>
              }
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// -- page body ---------------------------------------------------------------------------

export function CollectionView({ collection, wishlist, alerts, initialTab }: {
  collection: MyCollectionItem[]; wishlist: MyWishlistItem[]; alerts: MyPriceAlert[]; initialTab: CollectionTab;
}) {
  const [tab, setTab] = useState<CollectionTab>(initialTab);
  const groups = useMemo(() => groupCollection(collection), [collection]);
  const owned = collection.filter((c) => c.status === "owned").length;
  const wishInStock = wishlist.filter((w) => w.best_price !== null);
  const wishSum = wishInStock.reduce((s, w) => s + (w.best_price ?? 0), 0);

  function choose(next: CollectionTab) {
    setTab(next);
    // URL only (Next.js keeps its router in sync): no server round trip.
    window.history.replaceState(null, "", next === "koleksiyon" ? "/collection" : `/collection?sekme=${next}`);
  }

  const stats = [
    { label: "Bende var", value: `${owned} cilt`, note: `${groups.filter((g) => g.owned > 0).length} seri` },
    { label: "Tamamlanan seri", value: String(groups.filter(complete).length), note: `${groups.length} seriden` },
    { label: "İstek listesi", value: `${wishlist.length} cilt`, note: wishInStock.length ? `${wishInStock.length} stokta · ${formatTL(wishSum)}` : "stokta yok" },
    { label: "Fiyat alarmı", value: String(alerts.length), note: `${alerts.filter(hit).length} hedefte` },
  ];
  const tabs: { value: CollectionTab; label: string; count: number }[] = [
    { value: "koleksiyon", label: "Koleksiyon", count: groups.length },
    { value: "istek", label: "İstek listesi", count: wishlist.length },
    { value: "alarm", label: "Alarmlar", count: alerts.length },
  ];

  return (
    <div className="space-y-8">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="min-w-0 rounded-xl border border-line bg-surface p-3 shadow-card sm:p-4">
            <dt className="text-xs text-faint">{s.label}</dt>
            <dd className="tabular truncate text-xl font-bold text-ink sm:text-2xl">{s.value}</dd>
            <dd className="truncate text-xs text-muted">{s.note}</dd>
          </div>
        ))}
      </dl>

      <div className="space-y-5">
        <div role="tablist" aria-label="Listeler" className="-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0">
          {tabs.map((t) => (
            <button
              key={t.value}
              type="button"
              role="tab"
              id={`sekme-${t.value}`}
              aria-selected={tab === t.value}
              aria-controls={`panel-${t.value}`}
              onClick={() => choose(t.value)}
              className={`-mb-px inline-flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold whitespace-nowrap transition-colors ${
                tab === t.value ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {t.label}
              <span className={`tabular rounded-full px-1.5 text-xs ${tab === t.value ? "bg-accent-soft text-accent" : "bg-surface-2 text-faint"}`}>{t.count}</span>
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`sekme-${tab}`}>
          {tab === "koleksiyon" && <CollectionTabPanel items={collection} />}
          {tab === "istek" && <WishlistTabPanel items={wishlist} />}
          {tab === "alarm" && <AlertsTabPanel items={alerts} />}
        </div>
      </div>
    </div>
  );
}
