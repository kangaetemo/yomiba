"use client";

/**
 * AccountMenu: the signed-in reader's links on phones, where the header has
 * room for one button only. Desktop shows the same links inline (layout).
 * Closes on outside tap, Escape, or choosing an item.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LogoutButton } from "@/components/LogoutButton";

export function AccountMenu({ name, admin }: { name: string; admin: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item = "flex min-h-11 w-full items-center rounded-lg px-3 text-left font-semibold text-ink transition-colors hover:bg-surface-2";
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 font-semibold text-ink transition-colors hover:border-line-strong"
      >
        Hesabım
        <svg aria-hidden viewBox="0 0 24 24" className={`size-4 text-muted transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div role="menu" className="absolute top-full right-0 z-50 mt-2 w-56 rounded-xl border border-line bg-surface p-1 shadow-lift">
          <p className="truncate px-3 pt-2 pb-1 text-xs text-muted">{name}</p>
          <Link role="menuitem" href="/collection" className={item} onClick={() => setOpen(false)}>
            Koleksiyonum
          </Link>
          {admin && (
            <Link role="menuitem" href="/admin" className={item} onClick={() => setOpen(false)}>
              Admin
            </Link>
          )}
          <div className="my-1 border-t border-line" />
          <LogoutButton className={item} />
        </div>
      )}
    </div>
  );
}
