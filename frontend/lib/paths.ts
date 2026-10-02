/** Public, number-free page URLs: /series/berserk and /series/berserk/cilt-3. */

export function seriesPath(slug: string): string {
  return `/series/${encodeURIComponent(slug)}`;
}

/** `null` = an unnumbered item (box / set / legacy row). */
export function volumePath(seriesSlug: string, number: number | null): string {
  return `${seriesPath(seriesSlug)}/${number === null ? "cilt-numarasiz" : `cilt-${number}`}`;
}

/** The only volume of a one shot, when its series page has nothing else
 * to show (no other editions): links go straight to the prices. */
export function oneShotVolumeNumber(series: {
  one_shot?: boolean;
  editions?: unknown[];
  volumes: { number: number | null }[];
}): number | null {
  if (!series.one_shot || (series.editions ?? []).length > 0) return null;
  const numbered = series.volumes.filter((v) => v.number !== null && v.number >= 0);
  return numbered.length === 1 ? numbered[0].number : null;
}

/** Inverse of the volume segment: "cilt-3" -> 3, "cilt-numarasiz" -> null,
 * anything else -> undefined (not found). */
export function parseVolumeSegment(segment: string): number | null | undefined {
  if (segment === "cilt-numarasiz") return null;
  const m = /^cilt-(\d{1,4})$/.exec(segment);
  return m ? Number(m[1]) : undefined;
}
