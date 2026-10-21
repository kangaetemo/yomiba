/** Public origin of the site, for absolute URLs (canonical, sitemap, OG). */
export const SITE_URL = (process.env.SITE_URL || "https://yomiba.net").trim().replace(/\/+$/, "");

export const SITE_NAME = "Yomiba";

/** Open Graph block for a page. A page's `openGraph` replaces the layout's
 * whole object, so the shared fields are repeated here. */
export function openGraph(og: { title: string; description?: string; url: string; image?: string | null }) {
  return {
    type: "website" as const,
    siteName: SITE_NAME,
    locale: "tr_TR",
    title: og.title,
    description: og.description,
    url: og.url,
    images: og.image ? [{ url: og.image, alt: og.title }] : undefined,
  };
}
