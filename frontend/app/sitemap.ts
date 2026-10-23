import type { MetadataRoute } from "next";
import { oneShotVolumeNumber, seriesPath, volumePath } from "@/lib/paths";
import { SITE_URL } from "@/lib/site";
import { publisherPath } from "@/lib/seriesIndex";
import { getSeriesIndex, getSitemapEntries } from "@/services/catalog";

// Built per request from the live catalog (the Docker build has no backend).
export const dynamic = "force-dynamic";

const STATIC_PAGES = ["/", "/seriler", "/takvim", "/indirimler", "/one-shot"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const urls = STATIC_PAGES.map((path) => `${SITE_URL}${path === "/" ? "" : path}`);
  const [{ series }, index] = await Promise.all([getSitemapEntries(), getSeriesIndex()]);
  for (const slug of new Set(index.series.map((s) => s.publisher_slug))) urls.push(`${SITE_URL}${publisherPath(slug)}`);
  for (const s of series) {
    const volumes = s.volumes.map((number) => ({ number }));
    // A one shot's series page redirects to its volume: list the volume only.
    if (oneShotVolumeNumber({ volumes, upcoming_volumes: s.upcoming ? [null] : [] }) === null) {
      urls.push(`${SITE_URL}${seriesPath(s.slug)}`);
    }
    for (const number of s.volumes) urls.push(`${SITE_URL}${volumePath(s.slug, number)}`);
  }
  return [...new Set(urls)].map((url) => ({ url }));
}
