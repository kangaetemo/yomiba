/** Public origin of the site, for absolute URLs (canonical, sitemap, OG). */
export const SITE_URL = (process.env.SITE_URL || "https://yomiba.net").trim().replace(/\/+$/, "");

export const SITE_NAME = "Yomiba";

/** Share image for pages without a cover of their own (public/og.png). */
export const DEFAULT_OG_IMAGE = { url: "/og.png", width: 1200, height: 630, alt: "Yomiba" };

/** Search snippets are cut around 155 characters: join whole sentences
 * while they fit, so no snippet ends mid-word. */
export function metaDescription(sentences: (string | null | undefined)[], max = 155): string {
  let out = "";
  for (const s of sentences) {
    if (!s) continue;
    const next = out ? `${out} ${s}` : s;
    if (next.length > max) {
      if (out) break;
      return `${s.slice(0, max - 1).replace(/\s+\S*$/, "")}…`;
    }
    out = next;
  }
  return out;
}

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
    images: og.image ? [{ url: og.image, alt: og.title }] : [DEFAULT_OG_IMAGE],
  };
}
