"use client";

/**
 * Counts page views, time on page and clicks to stores (any link to
 * another site) for the admin analytics page. Mounted once in the layout.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { track } from "@/lib/track";

export function SiteTracker() {
  const pathname = usePathname();
  // Visible time on the current page, flushed when it is left or hidden.
  const visibleSince = useRef<number | null>(null);
  const visibleMs = useRef(0);

  useEffect(() => {
    const page = location.pathname + location.search;
    function flush() {
      if (visibleSince.current !== null) visibleMs.current += Date.now() - visibleSince.current;
      visibleSince.current = null;
      const seconds = Math.round(visibleMs.current / 1000);
      visibleMs.current = 0;
      if (seconds >= 1) track("engage", { v: seconds, u: page });
    }
    function onVisibility() {
      if (document.visibilityState === "hidden") flush();
      else visibleSince.current = Date.now();
    }

    track("pageview");
    visibleMs.current = 0;
    visibleSince.current = document.visibilityState === "visible" ? Date.now() : null;
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    return () => {
      // By now the address may already show the next page: the time is
      // sent for the page captured above.
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [pathname]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.type === "auxclick" && e.button !== 1) return;
      const link = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!link || !/^https?:$/.test(link.protocol) || link.host === location.host) return;
      track("outbound", { t: link.href });
    }
    document.addEventListener("click", onClick, true);
    document.addEventListener("auxclick", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("auxclick", onClick, true);
    };
  }, []);

  return null;
}
