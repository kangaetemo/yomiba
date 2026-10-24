"use client";

/**
 * A thin bar at the top of the window while the next page is being rendered
 * on the server, so a click never looks ignored. Starts on a click on an
 * internal link to another page, ends when the address changes (or after a
 * timeout, if the navigation was cancelled). Mounted once in the layout.
 */

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

const GIVE_UP_MS = 15_000;

export function NavigationProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // The address the click was made on: once the address changes, the new
  // page is there and the bar hides by itself.
  const here = `${pathname}?${searchParams}`;
  const [startedOn, setStartedOn] = useState<string | null>(null);

  useEffect(() => {
    let timer: number | undefined;
    function onClick(event: MouseEvent) {
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a");
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin) return;
      // Same page (a "#section" link or the current address): nothing loads.
      if (url.pathname === location.pathname && url.search === location.search) return;
      setStartedOn(`${location.pathname}?${new URLSearchParams(location.search)}`);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setStartedOn(null), GIVE_UP_MS);
    }
    // Capture: next/link cancels the browser's own navigation (preventDefault)
    // before a bubbling listener would see the click.
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.clearTimeout(timer);
    };
  }, []);

  if (startedOn !== here) return null;
  return (
    <div
      role="progressbar"
      aria-label="Sayfa yükleniyor"
      className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[3px] overflow-hidden bg-accent/20"
    >
      <div className="h-full w-1/3 nav-progress bg-accent" />
    </div>
  );
}
