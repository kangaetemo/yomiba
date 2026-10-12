import { pickRandom } from "./random";
import type { PopularSeries } from "../types";

export const HERO_HISTORY_COOKIE = "yomiba_hero_seen_v1";
export const HERO_HISTORY_SIZE = 12;

/** Anonymous display history only: a versioned list of recent series IDs. */
export function parseHeroHistory(value: string | undefined): number[] {
  if (!value || value.length > 2048) return [];
  try {
    const parsed: unknown = JSON.parse(decodeURIComponent(value));
    if (!parsed || typeof parsed !== "object" || !("v" in parsed) || parsed.v !== 1 || !("ids" in parsed) || !Array.isArray(parsed.ids)) return [];
    return [...new Set(parsed.ids.filter((id): id is number => Number.isSafeInteger(id) && id > 0))].slice(0, HERO_HISTORY_SIZE);
  } catch {
    return [];
  }
}

/** Newest first, bounded; redisplaying the same trio never grows the cookie. */
export function nextHeroHistory(previous: number[], shown: number[]): string {
  const ids = [...new Set([...shown, ...previous])].slice(0, HERO_HISTORY_SIZE);
  return encodeURIComponent(JSON.stringify({ v: 1, ids }));
}

export function pickHeroSeries(pool: PopularSeries[], recent: number[], count = 3): PopularSeries[] {
  const eligible = [...new Map(pool.filter((s) => s.cover_url && s.lowest_price !== null && s.in_stock_offers > 0).map((s) => [s.id, s])).values()];
  const seen = new Set(recent);
  const fresh = pickRandom(eligible.filter((s) => !seen.has(s.id)), count);
  // Tiny catalogs still show a full shelf, without duplicate cards.
  if (fresh.length < count) fresh.push(...pickRandom(eligible.filter((s) => seen.has(s.id)), count - fresh.length));
  return fresh;
}
