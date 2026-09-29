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
    <div className="max-w-xl space-y-2">
      <button
        type="button"
        aria-pressed={wishlisted}
        disabled={pending}
        onClick={toggle}
        className={`rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-50 ${
          wishlisted
            ? "border-info bg-info/10 text-info"
            : "border-line bg-surface text-muted hover:border-muted hover:text-ink"
        }`}
      >
        {wishlisted ? "✓ İstek listesinde — çıkarmak için tıkla" : "İstek listesine ekle"}
      </button>
      {pending && <span className="text-xs text-muted">Kaydediliyor…</span>}
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
