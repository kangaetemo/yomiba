"use client";

/**
 * PriceHistoryChart: ONE line — the volume's lowest in-stock price over
 * time (GET /volume/{id}/price-history ``lowest``, computed server-side).
 *
 * Drawn as steps: a price holds until the next change, so no straight
 * segment ever invents prices in between. A gap means no store had it in
 * stock. The line ends at today's best price (the one the page shows).
 * Hover or tap shows the date, price and store at that moment.
 *
 * Drawn at the box's real width (measured), so labels keep their size on a
 * phone and the line uses the room on a wide screen.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { TIME_ZONE, serverDate } from "@/lib/time";
import { formatPrice } from "@/components/PriceBadge";
import { formatTL } from "@/components/ui";
import type { LowestPricePoint } from "@/types";

const H = 220;
const PAD = { top: 14, right: 64, bottom: 28, left: 52 };
const DAY = 86_400_000;
const RANGES = [
  { key: "30", label: "30 gün", days: 30 },
  { key: "90", label: "90 gün", days: 90 },
  { key: "all", label: "Tümü", days: Infinity },
] as const;

interface Step { t: number; price: number | null; store: string | null }

const fmtDay = (t: number) => new Date(t).toLocaleDateString("tr-TR", { day: "numeric", month: "short", timeZone: TIME_ZONE });
const fmtLong = (t: number) => new Date(t).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric", timeZone: TIME_ZONE });

/** Time-weighted median of the in-stock steps between t0 and t1. */
function typicalPrice(steps: Step[], t0: number, t1: number): number | null {
  const spans: [number, number][] = [];
  steps.forEach((s, i) => {
    const a = Math.max(s.t, t0);
    const b = Math.min(steps[i + 1]?.t ?? t1, t1);
    if (s.price !== null && b > a) spans.push([s.price, b - a]);
  });
  if (spans.length === 0) return null;
  spans.sort((x, y) => x[0] - y[0]);
  const half = spans.reduce((n, [, d]) => n + d, 0) / 2;
  let acc = 0;
  for (const [p, d] of spans) { acc += d; if (acc >= half) return p; }
  return spans[spans.length - 1][0];
}

export function PriceHistoryChart({
  points,
  current,
  now,
}: {
  points: LowestPricePoint[];
  /** Today's best in-stock offer as the page shows it; ends the line. */
  current: { price: number; store: string } | null;
  /** Render time (ms) from the server, so server and browser draw the same. */
  now: number;
}) {
  const all: Step[] = useMemo(() => {
    const steps = points.map((p) => ({ t: serverDate(p.at).getTime(), price: p.price, store: p.store }));
    const last = steps[steps.length - 1];
    if (current && (!last || last.price !== current.price || last.store !== current.store)) {
      steps.push({ t: Math.max(now - 1, last?.t ?? now - DAY), price: current.price, store: current.store });
    }
    return steps;
  }, [points, current, now]);
  const firstT = all[0]?.t ?? now;
  const spanDays = (now - firstT) / DAY;
  const ranges = RANGES.filter((r) => r.days === Infinity ? spanDays > 90 : r.days === 30 || spanDays > 30);
  const [rangeKey, setRangeKey] = useState<string>(spanDays > 30 ? "90" : "30");
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  // Server render and first paint use 720; the measured width follows.
  const [W, setW] = useState(720);
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setW(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[0];
  const t1 = now;
  const t0 = range.days === Infinity ? firstT : Math.max(firstT, now - range.days * DAY);
  // The step in force at t0 starts the window; later ones follow.
  const startIdx = Math.max(0, all.findLastIndex((s) => s.t <= t0));
  const steps = all.slice(startIdx).map((s, i) => (i === 0 ? { ...s, t: Math.max(s.t, t0) } : s));
  if (steps.length === 0) return null;

  const priced = steps.filter((s) => s.price !== null) as (Step & { price: number })[];
  const lowestStep = priced.reduce<(Step & { price: number }) | null>((m, s) => (!m || s.price < m.price ? s : m), null);
  const typical = typicalPrice(steps, t0, t1);
  const nowPrice = current?.price ?? null;

  const prices = priced.map((s) => s.price);
  let lo = Math.min(...prices), hi = Math.max(...prices);
  const pad = Math.max((hi - lo) * 0.15, hi * 0.03, 2);
  lo = Math.max(0, lo - pad); hi = hi + pad;
  const tickStep = [5, 10, 20, 25, 50, 100].find((s) => (hi - lo) / s <= 5) ?? 100;
  const yTicks: number[] = [];
  for (let v = Math.ceil(lo / tickStep) * tickStep; v <= hi; v += tickStep) yTicks.push(v);
  const span = Math.max(t1 - t0, DAY);
  const x = (t: number) => PAD.left + ((t - t0) / span) * (W - PAD.left - PAD.right);
  const y = (p: number) => PAD.top + (1 - (p - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);
  const xTicks = [0, 1, 2, 3].map((k) => t0 + (span * k) / 3);

  let d = "";
  steps.forEach((s, i) => {
    const end = steps[i + 1]?.t ?? t1;
    if (s.price === null) return;
    const prev = steps[i - 1];
    d += prev && prev.price !== null ? `V${y(s.price)}` : `M${x(s.t)},${y(s.price)}`;
    d += `H${x(end)}`;
  });
  const last = steps[steps.length - 1];

  function onPointer(e: React.PointerEvent<SVGRectElement>) {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    const sx = ((e.clientX - box.left) / box.width) * W;
    setHover(Math.min(t1, Math.max(t0, t0 + ((sx - PAD.left) / (W - PAD.left - PAD.right)) * span)));
  }
  const at = hover === null ? null : steps[Math.max(0, steps.findLastIndex((s) => s.t <= hover))];
  const hoverX = hover === null ? 0 : x(hover);

  return (
    <div className="space-y-4 rounded-xl border border-line bg-surface p-4 shadow-card">
      {/* Same three lines per column: label, value, one short caption. */}
      <dl className="grid grid-cols-3 gap-3">
        {[
          { label: "Şu an", value: nowPrice !== null ? formatTL(nowPrice) : "Stokta yok", note: current?.store ?? "" },
          { label: "En düşük", value: lowestStep ? formatTL(lowestStep.price) : "—", note: lowestStep ? fmtDay(lowestStep.t) : "" },
          { label: "Tipik", value: typical !== null ? formatTL(typical) : "—", note: range.days === Infinity ? "tüm geçmiş" : `son ${range.days} gün` },
        ].map((stat) => (
          <div key={stat.label} className="min-w-0">
            <dt className="text-xs text-faint">{stat.label}</dt>
            <dd className="tabular truncate text-base font-bold text-ink sm:text-lg">{stat.value}</dd>
            <dd className="truncate text-xs text-muted">{stat.note || " "}</dd>
          </div>
        ))}
      </dl>

      {ranges.length > 1 && (
        <div role="group" aria-label="Zaman aralığı" className="inline-flex gap-0.5 rounded-lg bg-surface-2 p-0.5">
          {ranges.map((r) => (
            <button
              key={r.key}
              type="button"
              aria-pressed={r.key === range.key}
              onClick={() => { setRangeKey(r.key); setHover(null); }}
              className={`min-h-9 rounded-md px-3 text-sm font-semibold transition-colors ${r.key === range.key ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}

      <div ref={boxRef} className="relative">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" className="h-auto w-full touch-pan-y overflow-visible"
          aria-label={`En düşük fiyat geçmişi; şu an ${nowPrice !== null ? formatPrice(nowPrice) : "stokta yok"}, en düşük ${lowestStep ? formatPrice(lowestStep.price) : "—"}`}>
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize={13} fill="var(--faint)" className="tabular">{v} ₺</text>
            </g>
          ))}
          {xTicks.map((t, i) => (
            <text key={i} x={x(t)} y={H - 6} fontSize={13} fill="var(--faint)" textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}>{fmtDay(t)}</text>
          ))}
          {typical !== null && (
            <g>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(typical)} y2={y(typical)} stroke="var(--ink-2)" strokeWidth={1} strokeDasharray="4 4" />
              {/* The end price label wins when the two would touch. */}
              {(last.price === null || Math.abs(y(typical) - y(last.price)) >= 16) && (
                <text x={W - PAD.right + 6} y={y(typical) + 4} fontSize={12} fill="var(--muted)">tipik</text>
              )}
            </g>
          )}
          <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" />
          {last.price !== null && (
            <g>
              <circle cx={x(t1)} cy={y(last.price)} r={4.5} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
              <text x={x(t1) + 8} y={y(last.price) + 4} fontSize={13} fontWeight={700} fill="var(--ink)" className="tabular">{Math.round(last.price)} ₺</text>
            </g>
          )}
          {at && (
            <g pointerEvents="none">
              <line x1={hoverX} x2={hoverX} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--line-strong)" strokeWidth={1} />
              {at.price !== null && <circle cx={hoverX} cy={y(at.price)} r={4} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />}
            </g>
          )}
          <rect x={PAD.left} y={PAD.top} width={W - PAD.left - PAD.right} height={H - PAD.top - PAD.bottom} fill="transparent"
            onPointerMove={onPointer} onPointerDown={onPointer} onPointerLeave={() => setHover(null)} />
        </svg>
        {at && hover !== null && (
          <div
            className="pointer-events-none absolute top-2 z-10 min-w-40 rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm shadow-lift"
            style={hoverX / W > 0.6 ? { right: `${100 - (hoverX / W) * 100 + 2}%` } : { left: `${(hoverX / W) * 100 + 2}%` }}
          >
            <p className="text-xs text-faint">{fmtLong(hover)}</p>
            {at.price !== null ? (
              <p className="tabular font-bold text-ink">{formatPrice(at.price)} <span className="font-normal text-muted">· {at.store}</span></p>
            ) : (
              <p className="text-muted">Hiçbir mağazada stokta değildi</p>
            )}
          </div>
        )}
      </div>
      <p className="text-xs text-faint">Çizgi, stokta olan mağazalar arasındaki en düşük fiyatı gösterir. Boşluk, hiçbir mağazada stok olmadığı günlerdir.</p>
    </div>
  );
}
