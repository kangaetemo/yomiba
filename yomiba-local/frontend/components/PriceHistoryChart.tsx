/**
 * PriceHistoryChart: dependency-free SVG line chart of price over time,
 * one series per store.
 *
 * Deliberately a Server Component with zero client JS: native <title>
 * tooltips on each point, no chart library (keep the solo-project rule of
 * no unnecessary dependencies). The data arrives from
 * GET /volume/{id}/price-history, points already sorted chronologically.
 */

import { formatPrice } from "@/components/PriceBadge";
import type { PriceHistoryListing } from "@/types";

const PALETTE = [
  "#f97316", // orange (brand)
  "#38bdf8", // sky
  "#a78bfa", // violet
  "#34d399", // emerald
  "#fb7185", // rose
  "#fbbf24", // amber
];

/** Stable color per store name (same store -> same color on every page). */
function colorFor(store: string): string {
  let h = 0;
  for (let i = 0; i < store.length; i++) {
    h = (h * 31 + store.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}

const W = 720;
const H = 260;
const PAD = { top: 16, right: 20, bottom: 30, left: 64 };
const INNER_W = W - PAD.left - PAD.right;
const INNER_H = H - PAD.top - PAD.bottom;
const HOUR_MS = 3_600_000;

function formatTickPrice(v: number): string {
  const r = Math.round(v);
  const text = Math.abs(v - r) < 0.005 ? String(r) : v.toFixed(2);
  return `${text} ₺`;
}

function formatTickDate(d: Date, spanMs: number): string {
  const day = d.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
  // Short windows: show the time too, otherwise just the day.
  if (spanMs < 48 * HOUR_MS) {
    const time = d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    return `${day} ${time}`;
  }
  return day;
}

function formatPointDate(d: Date): string {
  return d.toLocaleString("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface SeriesPoint {
  t: number;
  price: number;
  label: string;
}

export function PriceHistoryChart({ listings }: { listings: PriceHistoryListing[] }) {
  if (listings.length === 0) return null;

  const series: { store: string; color: string; points: SeriesPoint[] }[] = [];
  for (const listing of listings) {
    if (listing.points.length === 0) continue;
    const points: SeriesPoint[] = listing.points.map((p) => {
      const d = new Date(p.checked_at);
      return {
        t: d.getTime(),
        price: p.price,
        label: `${listing.store} — ${formatPrice(p.price)} — ${formatPointDate(d)}`,
      };
    });
    series.push({ store: listing.store, color: colorFor(listing.store), points });
  }
  if (series.length === 0) return null;

  // Time scale (pad degenerate ranges so same-second imports still fit).
  const allT = series.flatMap((s) => s.points.map((p) => p.t));
  const rawT0 = Math.min(...allT);
  const rawT1 = Math.max(...allT);
  const t0 = rawT0 === rawT1 ? rawT0 - 12 * HOUR_MS : rawT0;
  const t1 = rawT0 === rawT1 ? rawT1 + 12 * HOUR_MS : rawT1;
  const tSpan = t1 - t0;
  const x = (t: number) => PAD.left + ((t - t0) / tSpan) * INNER_W;

  // Price scale (guard a flat range; never go below zero).
  const allP = series.flatMap((s) => s.points.map((p) => p.price));
  let pMin = Math.min(...allP);
  let pMax = Math.max(...allP);
  if (pMin === pMax) {
    const pad = Math.max(1, pMin * 0.02);
    pMin = Math.max(0, pMin - pad);
    pMax = pMax + pad;
  } else {
    const span = pMax - pMin;
    pMin = Math.max(0, pMin - span * 0.08);
    pMax = pMax + span * 0.08;
  }
  const y = (p: number) => PAD.top + INNER_H - ((p - pMin) / (pMax - pMin)) * INNER_H;

  const yTicks = Array.from({ length: 4 }, (_, i) => pMin + ((pMax - pMin) * i) / 3);
  const xTicks = Array.from({ length: 4 }, (_, i) => new Date(t0 + (tSpan * i) / 3));

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Fiyat geçmişi: ${series.map((s) => s.store).join(", ")}`}
        className="h-auto w-full"
      >
        {/* Horizontal grid + price labels */}
        {yTicks.map((v, i) => (
          <g key={`y${i}`}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(v)}
              y2={y(v)}
              stroke="#262626"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 8}
              y={y(v) + 4}
              textAnchor="end"
              fontSize={12}
              fill="#737373"
            >
              {formatTickPrice(v)}
            </text>
          </g>
        ))}

        {/* Time labels */}
        {xTicks.map((d, i) => (
          <g key={`x${i}`}>
            <line
              x1={x(d.getTime())}
              x2={x(d.getTime())}
              y1={PAD.top}
              y2={PAD.top + INNER_H}
              stroke="#262626"
              strokeWidth={1}
              strokeDasharray="2 4"
            />
            <text
              x={x(d.getTime())}
              y={H - 8}
              textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
              fontSize={12}
              fill="#737373"
            >
              {formatTickDate(d, tSpan)}
            </text>
          </g>
        ))}

        {/* Axes */}
        <line
          x1={PAD.left}
          x2={PAD.left}
          y1={PAD.top}
          y2={PAD.top + INNER_H}
          stroke="#404040"
          strokeWidth={1}
        />
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={PAD.top + INNER_H}
          y2={PAD.top + INNER_H}
          stroke="#404040"
          strokeWidth={1}
        />

        {/* One line + dots per store */}
        {series.map((s) => (
          <g key={s.store}>
            {s.points.length >= 2 && (
              <polyline
                points={s.points.map((p) => `${x(p.t)},${y(p.price)}`).join(" ")}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            )}
            {s.points.map((p, i) => (
              <circle
                key={i}
                cx={x(p.t)}
                cy={y(p.price)}
                r={3.5}
                fill={s.color}
                stroke="#171717"
                strokeWidth={1}
              >
                <title>{p.label}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-neutral-400">
        {series.map((s) => (
          <span key={s.store} className="inline-flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            {s.store}
          </span>
        ))}
        <span className="ml-auto text-xs text-neutral-600">
          Kesin fiyat için noktaların üzerine gelin
        </span>
      </div>
    </div>
  );
}
