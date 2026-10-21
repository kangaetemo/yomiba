/**
 * Outbound store links carry a Yomiba source tag so stores see the visit
 * in their own analytics (utm_source=yomiba&utm_medium=referral).
 *
 * The store's own query string (e.g. edessa's `?vid=`) is kept; a tag the
 * URL already carries is not overwritten. Unparseable URLs pass through.
 */
export function storeLink(url: string, medium = "referral"): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return url;
  if (parsed.searchParams.has("utm_source")) return url;
  // Appended as text: rewriting searchParams would re-encode the store's
  // own query (e.g. %20 -> +).
  const tag = `utm_source=yomiba&utm_medium=${medium}`;
  parsed.search = parsed.search ? `${parsed.search}&${tag}` : `?${tag}`;
  return parsed.toString();
}
