"use client";

/**
 * HeroShelf: three covers fanned out; the price card follows the cover in
 * front. Tapping a cover at the side brings it to the front (its volume count
 * and price show up in the card); only the front cover, or the card, opens
 * the series, so the page never navigates by accident.
 *
 * With reduced motion the global CSS cancels the slide, so the two covers
 * that swapped places and the price card fade in at their new spots instead.
 */

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Cover, formatTL } from "@/components/ui";
import { seriesPath } from "@/lib/paths";
import { HERO_HISTORY_COOKIE, nextHeroHistory, parseHeroHistory } from "@/lib/heroSelection";
import type { PopularSeries } from "@/types";

// Slot positions by order: [front, left, right]. Everything is a share of
// the stage, so the same fan fills a phone screen and the desktop column.
const SLOTS = [
  "z-20 -translate-x-1/2 translate-y-0 scale-100 rotate-0",
  "z-10 -translate-x-[118%] translate-y-0 scale-[0.818] -rotate-[8deg] opacity-90 hover:opacity-100",
  "z-10 translate-x-[18%] translate-y-[6%] scale-[0.818] rotate-[7deg] opacity-90 hover:opacity-100",
];

export function HeroShelf({ series }: { series: PopularSeries[] }) {
  // order[slot] = index into `series`
  const [order, setOrder] = useState(() => series.map((_, i) => i));
  useEffect(() => {
    // Persist after mount, without changing the SSR selection or causing a
    // hydration flash. Blocking cookies must never break the shelf.
    try {
      const value = document.cookie.split("; ").find((c) => c.startsWith(`${HERO_HISTORY_COOKIE}=`))?.slice(HERO_HISTORY_COOKIE.length + 1);
      const history = nextHeroHistory(parseHeroHistory(value), series.map((s) => s.id));
      document.cookie = `${HERO_HISTORY_COOKIE}=${history}; Path=/; Max-Age=86400; SameSite=Lax${window.location.protocol === "https:" ? "; Secure" : ""}`;
    } catch {
      // Random selection remains usable when storage is disabled.
    }
  }, [series]);

  const covers = useRef(new Map<number, HTMLDivElement>());
  const card = useRef<HTMLAnchorElement>(null);
  const swapped = useRef<number[] | null>(null);
  // Before paint, so the moved covers never flash at full opacity.
  useLayoutEffect(() => {
    const moved = swapped.current;
    swapped.current = null;
    if (!moved || !window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Web Animations are not shortened by the global reduced-motion CSS.
    const fade = { duration: 200, easing: "ease-out" };
    for (const i of moved) covers.current.get(i)?.animate([{ opacity: 0 }], fade);
    card.current?.animate([{ opacity: 0 }], fade);
  }, [order]);

  const front = series[order[0]];
  if (!front) return null;

  function bring(slot: number) {
    swapped.current = [order[0], order[slot]];
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
      {/* Fixed geometry: only transforms and opacity animate. The cover
          itself stays mounted when its link/button changes. */}
      {series.map((s, i) => {
        const slot = order.indexOf(i);
        return (
          <div
            key={s.id}
            ref={(el) => {
              if (el) covers.current.set(i, el);
              else covers.current.delete(i);
            }}
            className={`absolute top-[3%] left-1/2 w-[44%] transition-[translate,scale,rotate,opacity] duration-300 ease-out ${SLOTS[slot]}`}
          >
            <Cover url={s.cover_url} alt="" eager={slot === 0} className="w-full" />
            {slot === 0 ? (
              <Link href={seriesPath(s.slug)} aria-label={`${s.title} serisine git`} className="absolute inset-0 block" />
            ) : (
              <button
                type="button"
                onClick={() => bring(slot)}
                aria-label={`${s.title}: fiyat ve cilt bilgisini göster`}
                className="absolute inset-0 block w-full cursor-pointer"
              />
            )}
          </div>
        );
      })}
      {front.lowest_price !== null && (
        <Link
          ref={card}
          href={seriesPath(front.slug)}
          className="absolute bottom-0 left-1/2 z-30 w-[72%] max-w-72 -translate-x-1/2 rounded-xl border border-line bg-surface p-3.5 shadow-lift transition-colors hover:border-line-strong md:bg-surface/95 md:backdrop-blur"
        >
          <p className="truncate font-display text-base text-ink">{front.title}</p>
          <div className="mt-1 flex items-baseline justify-between gap-3">
            <span className="text-xs text-muted">
              {front.volume_count} cilt
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
