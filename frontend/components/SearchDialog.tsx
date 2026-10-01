"use client";

/**
 * SearchDialog: the header's search button opens a modal search box on any
 * page, so searching never throws you back to the home page. Uses the native
 * <dialog> (focus trap, Esc, backdrop come for free).
 */

import { useEffect, useRef, useState } from "react";
import { SearchSection } from "@/components/SearchSection";

export function SearchDialogButton({ className = "", label = "Ara" }: { className?: string; label?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={className} aria-haspopup="dialog">
        <svg aria-hidden viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m20 20-4.2-4.2" />
        </svg>
        {label}
      </button>
      <dialog
        ref={ref}
        aria-label="Manga ara"
        onClose={() => setOpen(false)}
        onClick={(e) => {
          if (e.target === ref.current) setOpen(false); // backdrop click
        }}
        className="m-0 mx-auto mt-[8vh] max-h-[84vh] w-[min(42rem,calc(100%-2rem))] overflow-y-auto rounded-2xl border border-line-strong bg-paper p-4 text-ink shadow-lift backdrop:bg-ink/40 backdrop:backdrop-blur-sm sm:p-5"
      >
        {open && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="eyebrow">Katalogda ara</p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-semibold text-ink-2 hover:text-accent"
              >
                Kapat <span aria-hidden className="ml-1">✕</span>
              </button>
            </div>
            <SearchSection autoFocus onNavigate={() => setOpen(false)} />
          </div>
        )}
      </dialog>
    </>
  );
}
