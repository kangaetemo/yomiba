"use client";

/**
 * Header links to home page sections ("/#yeni"). next/link alone misses the
 * section in two cases: coming from another page, the home route shows its
 * loading skeleton first, so the hash scroll runs before the section exists;
 * and on the home page, clicking a link whose hash is already in the address
 * does nothing. On the home page this scrolls by itself; from elsewhere it
 * navigates and <HashScroll /> on the home page scrolls once it has rendered.
 */

import Link from "next/link";
import { useEffect } from "react";
import { usePathname } from "next/navigation";

export function SectionLink({
  href,
  className,
  children,
}: {
  href: `/#${string}`;
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  return (
    <Link
      href={href}
      className={className}
      onClick={(event) => {
        if (pathname !== "/") return;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const id = href.slice(2);
        const target = document.getElementById(id);
        if (!target) return;
        event.preventDefault();
        history.replaceState(history.state, "", `/#${id}`);
        target.scrollIntoView();
      }}
    >
      {children}
    </Link>
  );
}

/** Scrolls to the section named in the address once the home page has
 * rendered (see SectionLink). Rendered by the home page itself, so it mounts
 * with the sections, not with the loading skeleton. */
export function HashScroll() {
  useEffect(() => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    // After the router's own scroll handling for this navigation.
    const frame = requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView());
    return () => cancelAnimationFrame(frame);
  }, []);
  return null;
}
