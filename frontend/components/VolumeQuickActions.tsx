"use client";

/**
 * VolumeQuickActions: the two one-tap actions on a volume tile.
 *
 * Bookmark = the wishlist ("İstek listesi"), check = "Bende var". They are
 * independent: owning a volume does not touch the wishlist and vice versa.
 * State follows the server response; the page is refreshed so filters and
 * counts stay in sync.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { addToWishlist, removeFromWishlist, setVolumeCollectionStatus } from "@/services/catalog";
import type { CollectionStatus } from "@/types";
import { BookmarkIcon, CheckIcon } from "@/components/volumeStock";

export function VolumeQuickActions({
  volumeId,
  label,
  initial,
  initialWishlisted,
}: {
  volumeId: number;
  /** "Cilt 3", for screen-reader button names. */
  label: string;
  initial: CollectionStatus | null;
  initialWishlisted: boolean;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<CollectionStatus | null>(initial);
  const [wishlisted, setWishlisted] = useState(initialWishlisted);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  async function run(action: () => Promise<void>) {
    if (pending) return;
    setPending(true);
    setError(false);
    try {
      await action();
      router.refresh();
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  }

  const toggleOwned = () => run(async () => {
    const updated = await setVolumeCollectionStatus(volumeId, status === "owned" ? null : "owned");
    setStatus(updated.collection_status);
  });
  const toggleWishlist = () => run(async () => {
    const updated = wishlisted ? await removeFromWishlist(volumeId) : await addToWishlist(volumeId);
    setWishlisted(updated.wishlisted);
  });

  const owned = status === "owned";
  const base =
    "grid size-9 place-items-center rounded-full border transition-colors disabled:opacity-50";

  return (
    <div className="flex shrink-0 items-center gap-1" title={error ? "Kaydedilemedi, tekrar deneyin" : undefined}>
      <button
        type="button"
        onClick={toggleWishlist}
        disabled={pending}
        aria-pressed={wishlisted}
        aria-label={wishlisted ? `${label} istek listesinden çıkar` : `${label} istek listesine ekle`}
        title={wishlisted ? "İstek listesinde" : "İstek listesine ekle"}
        className={`${base} ${
          wishlisted
            ? "border-accent/40 bg-accent-soft text-accent"
            : "border-line text-muted hover:border-line-strong hover:text-ink"
        }`}
      >
        <BookmarkIcon filled={wishlisted} />
      </button>
      <button
        type="button"
        onClick={toggleOwned}
        disabled={pending}
        aria-pressed={owned}
        aria-label={owned ? `${label} "Bende var"dan çıkar` : `${label} bende var`}
        title={owned ? "Bende var" : "Bende var olarak işaretle"}
        className={`${base} ${
          owned
            ? "border-ok/40 bg-ok-soft text-ok"
            : "border-line text-muted hover:border-line-strong hover:text-ink"
        } ${error ? "ring-2 ring-bad/40" : ""}`}
      >
        <CheckIcon />
      </button>
    </div>
  );
}
