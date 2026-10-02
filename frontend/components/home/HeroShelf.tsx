"use client";

/**
 * HeroShelf: three covers fanned out; the price card follows the cover in
 * front. Tapping a cover at the side brings it to the front (its volume count
 * and price show up in the card); only the front cover, or the card, opens
 * the series, so the page never navigates by accident.
 */

import Link from "next/link";
import { useState } from "react";
import { Cover, formatTL } from "@/components/ui";
import { seriesPath } from "@/lib/paths";
import type { PopularSeries } from "@/types";

// Slot positions by order: [front, left, right]. Everything is a share of
// the stage, so the same fan fills a phone screen and the desktop column.
const SLOTS = [
  "top-[3%] left-1/2 z-20 w-[44%] -translate-x-1/2 rotate-0",
  "top-[9%] left-[2%] z-10 w-[36%] -rotate-[8deg] opacity-90 hover:opacity-100",
  "top-[13%] right-[2%] z-10 w-[36%] rotate-[7deg] opacity-90 hover:opacity-100",
];

export function HeroShelf({ series }: { series: PopularSeries[] }) {
  // order[slot] = index into `series`
  const [order, setOrder] = useState(() => series.map((_, i) => i));
  const front = series[order[0]];
  if (!front) return null;

  function bring(slot: number) {
    setOrder((o) => {
      const next = [...o];
      [next[0], next[slot]] = [next[slot], next[0]];
      return next;
    });
  }

  return (
    <div className="relative mx-auto aspect-[10/9] w-full max-w-[22rem] sm:max-w-md lg:max-w-[32rem]">
      <div
        aria-hidden
        className="screentone absolute inset-[4%] rounded-[2rem] opacity-70 [mask-image:radial-gradient(closest-side,black,transparent)]"
      />
      {/* The positioned element is always the same <div> per series (never
          swapped between <a> and <button>), so React keeps it mounted and
          the move between slots animates. */}
      {series.map((s, i) => {
        const slot = order.indexOf(i);
        return (
          <div
            key={s.id}
            className={`absolute transition-all duration-500 ease-out ${SLOTS[slot]}`}
          >
            {slot === 0 ? (
              <Link href={seriesPath(s.slug)} aria-label={`${s.title} serisine git`} className="block">
                <Cover url={s.cover_url} alt="" eager className="w-full" />
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => bring(slot)}
                aria-label={`${s.title}: fiyat ve cilt bilgisini göster`}
                className="block w-full cursor-pointer"
              >
                <Cover url={s.cover_url} alt="" className="w-full" />
              </button>
            )}
          </div>
        );
      })}
      {front.lowest_price !== null && (
        <Link
          href={seriesPath(front.slug)}
          className="absolute bottom-0 left-1/2 z-30 w-[72%] max-w-72 -translate-x-1/2 rounded-xl border border-line bg-surface/95 p-3.5 shadow-lift backdrop-blur transition-colors hover:border-line-strong"
        >
          <p className="truncate font-display text-base text-ink">{front.title}</p>
          <div className="mt-1 flex items-baseline justify-between gap-3">
            <span className="text-xs text-muted">
              {front.volume_count} cilt · {front.in_stock_offers} stokta fiyat
            </span>
            <span className="tabular text-sm font-bold text-ink">
              {formatTL(front.lowest_price)}
              <span className="font-normal text-muted">&apos;den</span>
            </span>
          </div>
          <p className="mt-2 text-xs font-semibold text-accent">Seriyi gör →</p>
        </Link>
      )}
    </div>
  );
}
