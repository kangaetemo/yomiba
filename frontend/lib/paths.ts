/** Public, number-free page URLs: /series/berserk and /series/berserk/cilt-3. */

export function seriesPath(slug: string): string {
  return `/series/${encodeURIComponent(slug)}`;
}

/** `null` = an unnumbered item (box / set / legacy row). */
export function volumePath(seriesSlug: string, number: number | null): string {
  return `${seriesPath(seriesSlug)}/${number === null ? "cilt-numarasiz" : `cilt-${number}`}`;
}

/** Inverse of the volume segment: "cilt-3" -> 3, "cilt-numarasiz" -> null,
 * anything else -> undefined (not found). */
export function parseVolumeSegment(segment: string): number | null | undefined {
  if (segment === "cilt-numarasiz") return null;
  const m = /^cilt-(\d{1,4})$/.exec(segment);
  return m ? Number(m[1]) : undefined;
}
