"use client";

/**
 * FollowMissingButton: put every volume of the series the user does not own
 * ("Bende var") and has not wishlisted yet on the wishlist, in one tap. An
 * explicit action: marking a volume "Bende yok" never does this by itself.
 */

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { addToWishlist } from "@/services/catalog";
import { BookmarkIcon } from "@/components/volumeStock";

export function FollowMissingButton({
  signedIn,
  untrackedIds,
  trackedCount,
}: {
  signedIn: boolean;
  /** Volumes neither owned nor on the wishlist yet. */
  untrackedIds: number[];
  /** Volumes already on the wishlist. */
  trackedCount: number;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base =
    "inline-flex min-h-11 items-center gap-2 rounded-lg border px-3.5 text-sm font-semibold transition-colors";

  if (!signedIn) {
    return (
      <Link href="/login" className={`${base} border-line-strong bg-surface text-ink hover:border-accent hover:text-accent`}>
        <BookmarkIcon /> Eksiklerimi istek listeme ekle
      </Link>
    );
  }

  if (untrackedIds.length === 0) {
    return trackedCount > 0 ? (
      <span className={`${base} border-accent/30 bg-accent-soft text-accent`}>
        <BookmarkIcon filled /> {trackedCount} cilt istek listende
      </span>
    ) : null;
  }

  async function add() {
    setPending(true);
    setError(null);
    try {
      // Sequential: a handful of small writes, and a failure stops cleanly.
      for (const id of untrackedIds) {
        await addToWishlist(id);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "İstek listesine eklenemedi");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button
        type="button"
        onClick={add}
        disabled={pending}
        className={`${base} border-line-strong bg-surface text-ink hover:border-accent hover:text-accent disabled:opacity-60`}
      >
        <BookmarkIcon />
        {pending ? "Ekleniyor…" : `Eksiklerimi istek listeme ekle (${untrackedIds.length})`}
      </button>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
