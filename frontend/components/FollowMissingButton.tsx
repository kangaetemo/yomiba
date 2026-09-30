"use client";

/**
 * FollowMissingButton: track every volume of the series the user does not
 * own yet (sets them to "wanted", i.e. Takipte).
 *
 * Series-level following (automatically adding volumes released later) is
 * a backend feature still to come with notifications; until then this is a
 * one-shot bulk action over today's volumes.
 */

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { setVolumeCollectionStatus } from "@/services/catalog";
import { BellIcon } from "@/components/volumeStock";

export function FollowMissingButton({
  signedIn,
  untrackedIds,
  trackedCount,
}: {
  signedIn: boolean;
  /** Volumes neither owned nor tracked yet. */
  untrackedIds: number[];
  /** Volumes already tracked. */
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
        <BellIcon /> Eksiklerimi takip et
      </Link>
    );
  }

  if (untrackedIds.length === 0) {
    return trackedCount > 0 ? (
      <span className={`${base} border-accent/30 bg-accent-soft text-accent`}>
        <BellIcon filled /> {trackedCount} cilt takipte
      </span>
    ) : null;
  }

  async function follow() {
    setPending(true);
    setError(null);
    try {
      // Sequential: a handful of small writes, and a failure stops cleanly.
      for (const id of untrackedIds) {
        await setVolumeCollectionStatus(id, "wanted");
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Takip başlatılamadı");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <button
        type="button"
        onClick={follow}
        disabled={pending}
        className={`${base} border-line-strong bg-surface text-ink hover:border-accent hover:text-accent disabled:opacity-60`}
      >
        <BellIcon />
        {pending ? "Takibe alınıyor…" : `Eksiklerimi takip et (${untrackedIds.length})`}
      </button>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
