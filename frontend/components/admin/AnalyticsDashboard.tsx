"use client";

/**
 * Admin analytics: one period's report (GET /admin/analytics), compared with
 * the period before it. Charts are single-hue (accent) so no colour has to be
 * told apart; every bar and cell shows its number on hover.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import type { AnalyticsReport, Named, Point, Totals } from "@/services/analytics";
import { formatDateTime } from "@/lib/time";

const nf = new Intl.NumberFormat("tr-TR");
const num = (n: number) => nf.format(n);
const pct = (r: number | null | undefined, digits = 1) =>
  r === null || r === undefined ? "—" : `%${(r * 100).toLocaleString("tr-TR", { maximumFractionDigits: digits })}`;
function duration(s: number) {
  if (s < 60) return `${s} sn`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} dk ${s % 60} sn` : `${Math.floor(m / 60)} sa ${m % 60} dk`;
}
const DAY_NAMES = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const DEVICE_NAMES: Record<string, string> = { mobile: "Telefon", tablet: "Tablet", desktop: "Bilgisayar" };
const fmtDay = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("tr-TR", { day: "numeric", month: "short", timeZone: "UTC" });
const fmtDayLong = (d: string) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const pointLabel = (p: Point, long = false) =>
  typeof p.t === "number" ? `${String(p.t).padStart(2, "0")}:00` : long ? fmtDayLong(p.t) : fmtDay(p.t);

function Card({ title, note, children, className = "" }: { title: string; note?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 space-y-3 rounded-xl border border-line bg-surface p-4 shadow-card ${className}`}>
      <header>
        <h2 className="font-semibold text-ink">{title}</h2>
        {note && <p className="text-xs text-muted">{note}</p>}
      </header>
      {children}
    </section>
  );
}

function Empty({ children = "Bu dönemde veri yok." }: { children?: React.ReactNode }) {
  return <p className="text-sm text-faint">{children}</p>;
}

// ------------------------------------------------------------------ KPIs

type Kpi = { key: keyof Totals; label: string; format?: (n: number) => string; lowerIsBetter?: boolean; note?: string };
const KPIS: Kpi[] = [
  { key: "visitors", label: "Ziyaretçi", note: "her gün ayrı sayılır" },
  { key: "sessions", label: "Oturum" },
  { key: "pageviews", label: "Sayfa görüntüleme" },
  { key: "pages_per_session", label: "Sayfa / oturum", format: (n) => n.toLocaleString("tr-TR") },
  { key: "avg_session_seconds", label: "Ort. oturum süresi", format: duration },
  { key: "bounce_rate", label: "Hemen çıkma", format: (n) => pct(n), lowerIsBetter: true, note: "tek sayfa, tıklama yok" },
  { key: "outbound", label: "Mağaza tıklaması" },
  { key: "click_rate", label: "Mağazaya giden oturum", format: (n) => pct(n) },
  { key: "searches", label: "Arama" },
  { key: "zero_result_searches", label: "Sonuçsuz arama", lowerIsBetter: true },
  { key: "returning_visitors", label: "Geri gelen ziyaretçi" },
  { key: "logged_in_sessions", label: "Üye oturumu" },
  { key: "new_users", label: "Yeni üye" },
  { key: "wishlist_adds", label: "İstek listesine ekleme" },
  { key: "price_alerts", label: "Yeni fiyat alarmı" },
  { key: "collection_adds", label: "Koleksiyona ekleme" },
];

function Delta({ now, before, lowerIsBetter }: { now: number; before: number; lowerIsBetter?: boolean }) {
  if (before === 0) return <span className="text-xs text-faint">{now === 0 ? "—" : "yeni"}</span>;
  const change = (now - before) / before;
  if (Math.abs(change) < 0.005) return <span className="text-xs text-faint">aynı</span>;
  const good = lowerIsBetter ? change < 0 : change > 0;
  return (
    <span className={`text-xs font-semibold ${good ? "text-ok" : "text-bad"}`}>
      {change > 0 ? "▲" : "▼"} {pct(Math.abs(change), 0)}
    </span>
  );
}

function KpiGrid({ totals, previous }: { totals: Totals; previous: Totals }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {KPIS.map((k) => (
        <div key={k.key} className="min-w-0 rounded-xl border border-line bg-surface p-3 shadow-card">
          <dt className="truncate text-xs text-muted" title={k.note}>{k.label}</dt>
          <dd className="tabular truncate text-xl font-bold text-ink">{(k.format ?? num)(totals[k.key])}</dd>
          <dd className="flex min-w-0 items-baseline gap-1.5 whitespace-nowrap">
            <Delta now={totals[k.key]} before={previous[k.key]} lowerIsBetter={k.lowerIsBetter} />
            <span className="truncate text-xs text-faint">önceki {(k.format ?? num)(previous[k.key])}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ----------------------------------------------------------------- trend

const METRICS = [
  { key: "visitors", label: "Ziyaretçi" },
  { key: "pageviews", label: "Sayfa görüntüleme" },
  { key: "outbound", label: "Mağaza tıklaması" },
  { key: "searches", label: "Arama" },
] as const;
type MetricKey = (typeof METRICS)[number]["key"];

function useWidth(initial: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceMax(v: number) {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v) ?? v;
}

function TrendChart({ points }: { points: Point[] }) {
  const [metric, setMetric] = useState<MetricKey>("visitors");
  const [hover, setHover] = useState<number | null>(null);
  const [ref, W] = useWidth(720);
  const H = 220, PAD = { top: 12, right: 8, bottom: 26, left: 40 };
  const values = points.map((p) => p[metric]);
  const max = niceMax(Math.max(...values, 0));
  const plotW = W - PAD.left - PAD.right, plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(points.length, 1);
  const barW = Math.max(1, Math.min(28, slot - 2));
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const labelEvery = Math.ceil(points.length / Math.max(2, Math.floor(plotW / 64)));
  const total = values.reduce((a, b) => a + b, 0);
  const at = hover === null ? null : points[hover];

  return (
    <Card title="Zaman içinde" note={`Toplam ${num(total)} · ${points.length === 24 ? "saat saat (bugün)" : "gün gün"}`}>
      <div role="group" aria-label="Ölçü" className="inline-flex flex-wrap gap-0.5 rounded-lg bg-surface-2 p-0.5">
        {METRICS.map((m) => (
          <button key={m.key} type="button" aria-pressed={metric === m.key} onClick={() => setMetric(m.key)}
            className={`min-h-9 rounded-md px-3 text-sm transition-colors ${metric === m.key ? "bg-surface font-semibold text-ink shadow-card" : "text-muted hover:text-ink"}`}>
            {m.label}
          </button>
        ))}
      </div>
      <div ref={ref} className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full touch-pan-y" role="img"
          aria-label={`${METRICS.find((m) => m.key === metric)?.label}: toplam ${num(total)}`}
          onPointerLeave={() => setHover(null)}>
          {ticks.map((t, i) => (
            <g key={i}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" fontSize={12} fill="var(--faint)" className="tabular">{num(t)}</text>
            </g>
          ))}
          {points.map((p, i) => {
            const v = p[metric];
            const x = PAD.left + i * slot + (slot - barW) / 2;
            const h = Math.max(v > 0 ? 2 : 0, (v / max) * plotH);
            return (
              <g key={String(p.t)}>
                <rect x={x} y={PAD.top + plotH - h} width={barW} height={h} rx={Math.min(3, barW / 2)}
                  fill="var(--accent)" opacity={hover === null || hover === i ? 1 : 0.45} />
                {i % labelEvery === 0 && (
                  <text x={x + barW / 2} y={H - 8} textAnchor="middle" fontSize={12} fill="var(--faint)">{pointLabel(p)}</text>
                )}
                <rect x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} fill="transparent"
                  onPointerEnter={() => setHover(i)} onPointerDown={() => setHover(i)} />
              </g>
            );
          })}
        </svg>
        {at && hover !== null && (
          <div className="pointer-events-none absolute top-0 z-10 min-w-44 rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm shadow-lift"
            style={(hover + 0.5) / points.length > 0.6
              ? { right: `${100 - ((PAD.left + hover * slot) / W) * 100 + 1}%` }
              : { left: `${((PAD.left + (hover + 1) * slot) / W) * 100 + 1}%` }}>
            <p className="text-xs text-faint">{pointLabel(at, true)}</p>
            {METRICS.map((m) => (
              <p key={m.key} className={`tabular flex justify-between gap-4 ${m.key === metric ? "font-bold text-ink" : "text-muted"}`}>
                <span>{m.label}</span><span>{num(at[m.key])}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------ bar lists

function BarList({ rows, empty }: { rows: { key: string; label: React.ReactNode; value: number; extra?: React.ReactNode }[]; empty?: string }) {
  if (rows.length === 0) return <Empty>{empty}</Empty>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  const total = rows.reduce((a, r) => a + r.value, 0);
  return (
    <ul className="space-y-1.5 text-sm">
      {rows.map((r) => (
        <li key={r.key} className="relative grid grid-cols-[1fr_auto] items-center gap-3 overflow-hidden rounded-md px-2 py-1"
          title={`${num(r.value)} · ${pct(r.value / Math.max(total, 1))}`}>
          <span aria-hidden className="absolute inset-y-0 left-0 rounded-md bg-accent-soft" style={{ width: `${(r.value / max) * 100}%` }} />
          <span className="relative min-w-0 truncate text-ink">{r.label}</span>
          <span className="tabular relative text-right text-ink-2">
            {num(r.value)} <span className="text-xs text-faint">{pct(r.value / Math.max(total, 1), 0)}</span>
            {r.extra}
          </span>
        </li>
      ))}
    </ul>
  );
}

function NamedList({ rows, rename, empty, fallback = "Bilinmiyor" }: {
  rows: Named[]; rename?: (n: string) => string; empty?: string; fallback?: string;
}) {
  return <BarList empty={empty} rows={rows.map((r) => ({
    key: r.name ?? "∅", label: r.name ? (rename ? rename(r.name) : r.name) : <span className="text-muted">{fallback}</span>, value: r.sessions,
  }))} />;
}

function PathLink({ path }: { path: string }) {
  return <Link href={path} className="hover:underline" title={path}>{decodeURIComponent(path)}</Link>;
}

function Table({ head, children, empty, limit = 10 }: { head: React.ReactNode[]; children: React.ReactNode[]; empty?: string; limit?: number }) {
  const [all, setAll] = useState(false);
  if (children.length === 0) return <Empty>{empty}</Empty>;
  const rows = all ? children : children.slice(0, limit);
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-faint">
            {head.map((h, i) => <th key={i} className={`py-1.5 pr-3 font-normal ${i > 0 ? "text-right" : ""}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{rows}</tbody>
      </table>
      {children.length > limit && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 min-h-9 text-sm font-semibold text-new hover:underline">
          {all ? "Daha az göster" : `Tümünü göster (${children.length})`}
        </button>
      )}
    </div>
  );
}
const td = "py-1.5 pr-3 text-right tabular text-ink-2";

function Spark({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const w = 96, h = 22, step = w / Math.max(values.length, 1);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="ml-auto h-[22px] w-24" aria-hidden>
      {values.map((v, i) => {
        const bh = v > 0 ? Math.max(2, (v / max) * h) : 0;
        return <rect key={i} x={i * step + 0.5} y={h - bh} width={Math.max(1, step - 1)} height={bh} rx={1} fill="var(--accent)" />;
      })}
    </svg>
  );
}

// -------------------------------------------------------------- heatmap

function Heatmap({ grid }: { grid: number[][] }) {
  const max = Math.max(...grid.flat(), 1);
  const [hover, setHover] = useState<{ d: number; h: number } | null>(null);
  return (
    <div className="space-y-2">
      <div className="-mx-4 overflow-x-auto px-4">
        <div className="grid min-w-[560px] grid-cols-[2.5rem_repeat(24,minmax(0,1fr))] gap-[2px] text-[11px]" onPointerLeave={() => setHover(null)}>
          <span />
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="text-center text-faint">{h % 3 === 0 ? h : ""}</span>
          ))}
          {grid.map((row, d) => (
            <div key={d} className="contents">
              <span className="pr-1 text-right leading-5 text-muted">{DAY_NAMES[d]}</span>
              {row.map((v, h) => (
                <span key={h} onPointerEnter={() => setHover({ d, h })} onPointerDown={() => setHover({ d, h })}
                  className="h-5 rounded-[3px] border border-line/60"
                  style={{ background: v ? `color-mix(in oklab, var(--accent) ${Math.round(12 + (v / max) * 88)}%, var(--surface))` : "var(--surface-2)" }}
                  title={`${DAY_NAMES[d]} ${String(h).padStart(2, "0")}:00 · ${num(v)} görüntüleme`} />
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="tabular h-5 text-xs text-muted">
        {hover ? `${DAY_NAMES[hover.d]} ${String(hover.h).padStart(2, "0")}:00–${String(hover.h).padStart(2, "0")}:59 · ${num(grid[hover.d][hover.h])} sayfa görüntüleme`
          : "Koyu kare: o gün ve saatte daha çok ziyaret. Türkiye saati."}
      </p>
    </div>
  );
}

// --------------------------------------------------------------- funnel

function Funnel({ funnel, searchClickRate }: { funnel: AnalyticsReport["funnel"]; searchClickRate: number | null }) {
  const steps = [
    { label: "Oturum", value: funnel.sessions },
    { label: "Bir cilt sayfasına baktı", value: funnel.viewed_volume },
    { label: "Mağazaya tıkladı", value: funnel.clicked_store },
  ];
  const top = Math.max(funnel.sessions, 1);
  return (
    <div className="space-y-2">
      {steps.map((s, i) => (
        <div key={s.label} className="space-y-1">
          <div className="flex justify-between text-sm">
            <span className="text-ink">{s.label}</span>
            <span className="tabular text-ink-2">
              {num(s.value)} <span className="text-xs text-faint">{i > 0 ? `${pct(s.value / Math.max(steps[i - 1].value, 1), 0)} önceki adımdan` : ""}</span>
            </span>
          </div>
          <div className="h-3 rounded-full bg-surface-2">
            <div className="h-3 rounded-full bg-accent" style={{ width: `${(s.value / top) * 100}%` }} />
          </div>
        </div>
      ))}
      <p className="pt-1 text-xs text-muted">Arama yapan oturumların {pct(searchClickRate, 0)} kadarı bir mağazaya tıkladı.</p>
    </div>
  );
}

// ------------------------------------------------------------ dashboard

export function AnalyticsDashboard({ report: r }: { report: AnalyticsReport }) {
  const router = useRouter();
  const [refreshing, startRefresh] = useTransition();
  const days = r.days;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="flex items-center gap-2 text-ink">
          <span className="relative flex size-2.5">
            {r.live.sessions > 0 && <span className="absolute inline-flex size-full animate-ping rounded-full bg-ok opacity-60" />}
            <span className={`relative inline-flex size-2.5 rounded-full ${r.live.sessions > 0 ? "bg-ok" : "bg-faint"}`} />
          </span>
          <span><b className="tabular">{num(r.live.sessions)}</b> kişi şu an sitede <span className="text-muted">(son 5 dakika)</span></span>
          {r.live.pages.length > 0 && (
            <span className="hidden text-muted md:inline">
              · {r.live.pages.slice(0, 3).map((p) => decodeURIComponent(p.path)).join(", ")}
            </span>
          )}
        </p>
        <p className="flex items-center gap-3 text-muted">
          <span>{days === 1 ? fmtDayLong(r.end) : `${fmtDay(r.start)} – ${fmtDay(r.end)}`} · güncelleme {formatDateTime(r.generated_at)}</span>
          <button type="button" onClick={() => startRefresh(() => router.refresh())} disabled={refreshing}
            className="min-h-9 rounded-lg border border-line px-3 font-semibold text-ink transition-colors hover:border-line-strong disabled:opacity-60">
            {refreshing ? "Yenileniyor…" : "Yenile"}
          </button>
        </p>
      </div>

      <KpiGrid totals={r.totals} previous={r.previous} />
      <TrendChart points={r.series} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Mağazalara giden tıklamalar" note={`${num(r.totals.outbound)} tıklama, ${num(r.totals.outbound_sessions)} oturumdan`}>
          <Table head={["Mağaza", "Tıklama", "Pay", "Oturum", "Farklı cilt", "Gidiş"]} empty="Bu dönemde mağazaya tıklanmadı.">
            {r.stores.map((s) => (
              <tr key={s.store_id}>
                <td className="py-1.5 pr-3 text-ink">{s.name}</td>
                <td className={`${td} font-semibold text-ink`}>{num(s.clicks)}</td>
                <td className={td}>{pct(s.clicks / Math.max(r.totals.outbound, 1), 0)}</td>
                <td className={td}>{num(s.sessions)}</td>
                <td className={td}>{num(s.volumes)}</td>
                <td className="py-1.5"><Spark values={s.trend} /></td>
              </tr>
            ))}
          </Table>
          {r.other_links.length > 0 && (
            <div className="space-y-1 border-t border-line pt-3">
              <p className="text-xs text-faint">Mağaza dışı bağlantılar</p>
              <BarList rows={r.other_links.map((o) => ({ key: o.host, label: o.host, value: o.clicks }))} />
            </div>
          )}
        </Card>
        <Card title="Ziyaretten tıklamaya" note="Oturumların ne kadarı mağazaya ulaşıyor">
          <Funnel funnel={r.funnel} searchClickRate={r.search_click_rate} />
          <div className="space-y-1 border-t border-line pt-3">
            <p className="text-xs text-faint">Oturum başına görülen sayfa</p>
            <BarList rows={r.session_depth.filter((d) => d.sessions > 0).map((d) => ({
              key: String(d.pages), label: d.pages === 10 ? "10 ve üzeri" : `${d.pages} sayfa`, value: d.sessions,
            }))} />
          </div>
        </Card>
      </div>

      <Card title="Yeni üyeler" note={`Bu dönemde açılan hesaplar, en yenisi üstte · toplam üye ${num(r.users_total)}`}>
        <Table head={["Üye", "Kayıt", "Yöntem", "Son giriş", "Koleksiyon", "İstek listesi", "Fiyat alarmı"]} empty="Bu dönemde yeni üye yok.">
          {r.new_members.map((m) => (
            <tr key={m.id} className={m.active ? "" : "opacity-60"}>
              <td className="max-w-72 py-1.5 pr-3">
                <span className="block truncate text-ink">
                  {m.name}
                  {m.admin && <span className="ml-1.5 text-xs text-faint">admin</span>}
                  {!m.active && <span className="ml-1.5 text-xs text-faint">kapalı</span>}
                </span>
                <span className="block truncate text-xs text-muted">{m.email}</span>
              </td>
              <td className={`${td} text-xs whitespace-nowrap`}>{formatDateTime(m.created_at)}</td>
              <td className={`${td} text-xs`}>{m.method === "email" ? "E-posta" : m.method === "google" ? "Google" : "Google + e-posta"}</td>
              <td className={`${td} text-xs whitespace-nowrap`}>{m.last_login ? formatDateTime(m.last_login) : "—"}</td>
              <td className={td}>{num(m.collection)}</td>
              <td className={td}>{num(m.wishlist)}</td>
              <td className={td}>{num(m.alerts)}</td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card title="En çok bakılan ciltler" note="Tıklama oranı: cilde bakan oturumların mağazaya tıklayan kısmı">
        <Table head={["Cilt", "Görüntüleme", "Oturum", "Mağaza tıklaması", "Tıklama oranı"]}>
          {r.top_volumes.map((v) => (
            <tr key={v.volume_id}>
              <td className="max-w-80 truncate py-1.5 pr-3 text-ink">
                {v.path ? <Link href={v.path} className="hover:underline">{v.series} · {v.number === null ? "Numarasız" : `Cilt ${v.number}`}</Link>
                  : `${v.series}${v.number !== null ? ` · Cilt ${v.number}` : ""}`}
              </td>
              <td className={td}>{num(v.pageviews)}</td>
              <td className={td}>{num(v.sessions)}</td>
              <td className={`${td} font-semibold text-ink`}>{num(v.outbound)}</td>
              <td className={td}>{pct(v.click_rate, 0)}</td>
            </tr>
          ))}
        </Table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="En çok bakılan seriler" note="Seri ve cilt sayfaları birlikte">
          <Table head={["Seri", "Görüntüleme", "Oturum", "Mağaza tıklaması"]}>
            {r.top_series.map((s) => (
              <tr key={s.series_id}>
                <td className="max-w-64 truncate py-1.5 pr-3 text-ink">
                  {s.path ? <Link href={s.path} className="hover:underline">{s.title}</Link> : s.title}
                </td>
                <td className={td}>{num(s.pageviews)}</td>
                <td className={td}>{num(s.sessions)}</td>
                <td className={`${td} font-semibold text-ink`}>{num(s.outbound)}</td>
              </tr>
            ))}
          </Table>
        </Card>
        <Card title="Sayfalar" note="Ortalama süre: sayfanın ekranda açık kaldığı süre">
          <Table head={["Sayfa", "Görüntüleme", "Ziyaretçi", "Ort. süre"]}>
            {r.pages.map((p) => (
              <tr key={p.path}>
                <td className="max-w-64 truncate py-1.5 pr-3 text-ink"><PathLink path={p.path} /></td>
                <td className={td}>{num(p.pageviews)}</td>
                <td className={td}>{num(p.visitors)}</td>
                <td className={td}>{p.avg_seconds ? duration(p.avg_seconds) : "—"}</td>
              </tr>
            ))}
          </Table>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Giriş sayfaları" note="Oturumun ilk sayfası">
          <BarList rows={r.entry_pages.map((p) => ({ key: p.path, label: <PathLink path={p.path} />, value: p.sessions }))} empty="Veri yok." />
        </Card>
        <Card title="Çıkış sayfaları" note="Oturumun son sayfası">
          <BarList rows={r.exit_pages.map((p) => ({ key: p.path, label: <PathLink path={p.path} />, value: p.sessions }))} empty="Veri yok." />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Aramalar" note="Yazmayı bitirdikten sonra sayılır; küçük harfe çevrilmiş">
          <Table head={["Arama", "Sayı", "Ort. sonuç", "Son"]} empty="Bu dönemde arama yapılmadı.">
            {r.searches.map((s) => (
              <tr key={s.query}>
                <td className="max-w-56 truncate py-1.5 pr-3 text-ink">{s.query}</td>
                <td className={`${td} font-semibold text-ink`}>{num(s.count)}</td>
                <td className={td}>{s.avg_results?.toLocaleString("tr-TR") ?? "—"}</td>
                <td className={`${td} text-xs`}>{formatDateTime(s.last)}</td>
              </tr>
            ))}
          </Table>
        </Card>
        <Card title="Sonuç bulunamayan aramalar" note="Katalogda olmayan ama aranan seriler: eklenecekler için ipucu">
          <Table head={["Arama", "Sayı", "Son"]} empty="Sonuçsuz arama yok.">
            {r.zero_searches.map((s) => (
              <tr key={s.query}>
                <td className="max-w-56 truncate py-1.5 pr-3 text-ink">{s.query}</td>
                <td className={`${td} font-semibold text-ink`}>{num(s.count)}</td>
                <td className={`${td} text-xs`}>{formatDateTime(s.last)}</td>
              </tr>
            ))}
          </Table>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Nereden geldiler" note="Oturumun geldiği site">
          <NamedList rows={r.referrers} fallback="Doğrudan / bilinmiyor" empty="Veri yok." />
        </Card>
        <Card title="Kampanya kaynağı" note="Bağlantıdaki utm_source">
          <NamedList rows={r.utm_sources.filter((x) => x.name)} empty="Etiketli bağlantıdan gelen yok." />
        </Card>
        <Card title="Kampanya" note="Bağlantıdaki utm_campaign">
          <NamedList rows={r.utm_campaigns.filter((x) => x.name)} empty="Kampanya etiketi yok." />
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Cihaz"><NamedList rows={r.devices} rename={(n) => DEVICE_NAMES[n] ?? n} /></Card>
        <Card title="Tarayıcı"><NamedList rows={r.browsers} /></Card>
        <Card title="İşletim sistemi"><NamedList rows={r.systems} /></Card>
        <Card title="Ülke" note="Cloudflare üzerinden gelen istekler için"><NamedList rows={r.countries} /></Card>
      </div>

      <Card title="Gün ve saat" note="Dönem boyunca sayfa görüntülemelerinin haftanın günü ve saate göre dağılımı">
        <Heatmap grid={r.heatmap} />
      </Card>

      <p className="text-xs text-faint">
        Çerez kullanılmaz. Ziyaretçi, IP ve tarayıcıdan her gün değişen bir anahtarla üretilen anonim bir kodla sayılır; bu yüzden aynı kişi farklı günlerde ayrı ziyaretçi sayılır.
        Ham kayıtlar {r.retention_days} gün saklanır. Toplam üye: {num(r.users_total)}.
      </p>
    </div>
  );
}
