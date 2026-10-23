import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Personal and admin pages; /api is the backend proxy. Filtered and
      // list views of a series repeat its page (canonical is the bare URL).
      disallow: [
        "/admin", "/api/", "/collection", "/hesap", "/login", "/register", "/eposta-onay",
        "/series/*?", "/one-shot?",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
