"use client";

/**
 * WishlistToggle: add / remove the current volume from the wishlist.
 *
 * Client Component only because it is interactive. The server response is
 * the source of truth (no optimistic state); a failed call reverts and shows
 * a visible error. Independent of the collection status picker.
 */

import { useState } from "react";
import { addToWishlist, removeFromWishlist } from "@/services/catalog";

export function WishlistToggle({
  volumeId,
  initial,
}: {
  volumeId: number;
  initial: boolean;
}) {
  const [wishlisted, setWishlisted] = useState(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (pending) return;
    const previous = wishlisted;
    setPending(true);
    setError(null);
    try {
      const state = wishlisted
        ? await removeFromWishlist(volumeId)
        : await addToWishlist(volumeId);
      setWishlisted(state.wishlisted);
    } catch (e) {
      setWishlisted(previous);
      setError(e instanceof Error ? e.message : "İstek listesi güncellenemedi");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        aria-pressed={wishlisted}
        disabled={pending}
        onClick={toggle}
        title={wishlisted ? "İstek listesinden çıkar" : undefined}
        className={`inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border px-4 text-sm font-semibold transition-colors disabled:opacity-60 ${
          wishlisted
            ? "border-new/40 bg-new-soft text-new"
            : "border-line-strong bg-surface text-ink hover:border-ink/40"
        }`}
      >
        <svg aria-hidden viewBox="0 0 24 24" className="size-4" fill={wishlisted ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
          <path d="M6 3.5h12v17l-6-4-6 4z" strokeLinejoin="round" />
        </svg>
        {pending ? "Kaydediliyor…" : wishlisted ? "İstek listesinde" : "İstek listesine ekle"}
      </button>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
