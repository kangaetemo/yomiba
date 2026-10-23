import { seriesPath, volumePath } from "@/lib/paths";
import type { SeriesIndexItem } from "@/types";

export const TR = new Intl.Collator("tr");

/** Where a list entry links: the volume itself for a one shot. */
export function seriesHref(s: SeriesIndexItem): string {
  return s.only_volume !== null ? volumePath(s.slug, s.only_volume) : seriesPath(s.slug);
}

export function publisherPath(slug: string): string {
  return `/yayinevi/${encodeURIComponent(slug)}`;
}

/** Index letter: Turkish upper case ("ç" -> "Ç", "i" -> "İ"); digits and
 * symbols share "#". */
export function indexLetter(title: string): string {
  const first = title.trim().charAt(0).toLocaleUpperCase("tr");
  return /\p{L}/u.test(first) ? first : "#";
}

/** Series grouped by index letter, letters in Turkish order ("#" first). */
export function groupByLetter(series: SeriesIndexItem[]): [string, SeriesIndexItem[]][] {
  const groups = new Map<string, SeriesIndexItem[]>();
  for (const s of [...series].sort((a, b) => TR.compare(a.title, b.title))) {
    const letter = indexLetter(s.title);
    groups.set(letter, [...(groups.get(letter) ?? []), s]);
  }
  return [...groups.entries()].sort(([a], [b]) => (a === "#" ? -1 : b === "#" ? 1 : TR.compare(a, b)));
}

/** Publishers with their series counts, most series first. */
export function publishers(series: SeriesIndexItem[]): { name: string; slug: string; count: number }[] {
  const by = new Map<string, { name: string; slug: string; count: number }>();
  for (const s of series) {
    const p = by.get(s.publisher_slug) ?? { name: s.publisher, slug: s.publisher_slug, count: 0 };
    p.count += 1;
    by.set(s.publisher_slug, p);
  }
  return [...by.values()].sort((a, b) => b.count - a.count || TR.compare(a.name, b.name));
}
