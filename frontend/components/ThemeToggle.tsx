"use client";

/**
 * ThemeToggle: light / dark switch in the header.
 *
 * The choice is remembered per browser (localStorage, a convenience only);
 * without one the system setting decides. THEME_SCRIPT (inlined in <head>)
 * applies it before first paint, so a dark-mode reader never sees a light
 * flash. Both icons are rendered and CSS (`dark:`) shows the right one, so
 * the button is correct in the very first frame, before hydration.
 *
 * Switching animates where the browser can (View Transitions): the new
 * theme grows as a circle from the button. Reduced motion, or no support,
 * switches instantly.
 */

const KEY = "yomiba-theme";

/** Runs before paint: stored choice, else the system preference. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${KEY}");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}})()`;

export function ThemeToggle() {
  function apply(next: "light" | "dark") {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Private mode / blocked storage: the switch still works for this visit.
    }
  }

  function toggle(e: React.MouseEvent<HTMLButtonElement>) {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || typeof document.startViewTransition !== "function") {
      apply(next);
      return;
    }
    // From the button's centre to the farthest corner of the viewport.
    const box = e.currentTarget.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    const transition = document.startViewTransition(() => apply(next));
    transition.ready
      .then(() => {
        root.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
          { duration: 450, easing: "cubic-bezier(0.4, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)" },
        );
      })
      .catch(() => {});
  }

  const icon = "size-5";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Açık / koyu tema"
      title="Açık / koyu tema"
      className="grid size-11 shrink-0 place-items-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {/* Moon in the light theme ("go dark"), sun in the dark one. */}
      <svg viewBox="0 0 24 24" aria-hidden className={`${icon} theme-icon dark:hidden`} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
      </svg>
      <svg viewBox="0 0 24 24" aria-hidden className={`${icon} theme-icon hidden dark:block`} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
      </svg>
    </button>
  );
}
