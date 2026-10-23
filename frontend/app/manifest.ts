import type { MetadataRoute } from "next";
import { SITE_NAME } from "@/lib/site";

/** Web app manifest: name and icons for "add to home screen" and search. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Yomiba - Manga fiyat karşılaştırma",
    short_name: SITE_NAME,
    start_url: "/",
    display: "standalone",
    background_color: "#f7f2e7",
    theme_color: "#b8321b",
    lang: "tr",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
