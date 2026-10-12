import assert from "node:assert/strict";
import { test } from "node:test";
import { nextHeroHistory, parseHeroHistory, pickHeroSeries } from "../lib/heroSelection";
import type { PopularSeries } from "../types";

function series(id: number, changes: Partial<PopularSeries> = {}): PopularSeries {
  return { id, slug: `series-${id}`, title: `Series ${id}`, publisher: "Athica", author: null, cover_url: "/cover.webp", volume_count: 1, lowest_price: 100, in_stock_offers: 1, ...changes };
}

test("fresh visits avoid the previous 12 series and keep three unique cards", () => {
  const pool = Array.from({ length: 40 }, (_, i) => series(i + 1));
  let history: number[] = [];
  for (let visit = 0; visit < 20; visit++) {
    const picked = pickHeroSeries(pool, history);
    assert.equal(picked.length, 3);
    assert.equal(new Set(picked.map((s) => s.id)).size, 3);
    assert(picked.every((s) => !history.includes(s.id)));
    history = parseHeroHistory(nextHeroHistory(history, picked.map((s) => s.id)));
    assert(history.length <= 12);
  }
});

test("tiny pools fill the shelf safely; ineligible and duplicate series are excluded", () => {
  const pool = [series(1), series(1), series(2), series(3, { cover_url: null }), series(4, { lowest_price: null }), series(5, { in_stock_offers: 0 })];
  assert.deepEqual(pickHeroSeries(pool, [1, 2]).map((s) => s.id).sort(), [1, 2]);
  assert.deepEqual(pickHeroSeries([], []), []);
  assert.equal(pickHeroSeries([series(1)], [1]).length, 1);
});

test("cookie input tolerates corruption, old schemas, and invalid IDs", () => {
  for (const value of [undefined, "oops", "%zz", "null", "{}", "%7B%22v%22%3A2%7D", "x".repeat(2049)]) assert.deepEqual(parseHeroHistory(value), []);
  const value = encodeURIComponent(JSON.stringify({ v: 1, ids: [1, 1, 0, -1, "2", null, 2, 3.5] }));
  assert.deepEqual(parseHeroHistory(value), [1, 2]);
});

test("history stays bounded and the most recently displayed cards come first", () => {
  const previous = Array.from({ length: 12 }, (_, i) => i + 1);
  const value = nextHeroHistory(previous, [15, 16, 17]);
  assert.deepEqual(parseHeroHistory(value), [15, 16, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.equal(nextHeroHistory(parseHeroHistory(value), [15, 16, 17]), value);
});
