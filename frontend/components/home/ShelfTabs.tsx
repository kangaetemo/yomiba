"use client";

/**
 * ShelfTabs: switch between home shelves ("Popüler" / "One shot") without a
 * reload. The panels are rendered on the server and passed in as children;
 * this component only decides which one is visible (WAI-ARIA tabs, arrow
 * keys move between tabs).
 */

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export function ShelfTabs({
  tabs,
  children,
}: {
  tabs: { label: string; count?: number }[];
  /** One panel per tab, in the same order. */
  children: ReactNode[];
}) {
  const [active, setActive] = useState(0);
  const base = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (active + step + tabs.length) % tabs.length;
    setActive(next);
    buttons.current[next]?.focus();
  }

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label="Seri rafları"
        onKeyDown={onKey}
        className="inline-flex gap-1 rounded-full border border-line bg-surface-2 p-1"
      >
        {tabs.map((tab, i) => {
          const selected = i === active;
          return (
            <button
              key={tab.label}
              ref={(el) => {
                buttons.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${i}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${i}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(i)}
              className={`min-h-11 rounded-full px-4 text-sm font-semibold transition-colors ${
                selected ? "bg-ink text-paper shadow-card" : "text-muted hover:text-ink"
              }`}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className={`tabular ml-1.5 font-normal ${selected ? "opacity-70" : "text-faint"}`}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {children.map((panel, i) => (
        <div
          key={i}
          role="tabpanel"
          id={`${base}-panel-${i}`}
          aria-labelledby={`${base}-tab-${i}`}
          hidden={i !== active}
        >
          {panel}
        </div>
      ))}
    </div>
  );
}
