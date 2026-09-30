"use client";

/**
 * VolumeQuickActions: the two one-tap actions on a volume tile.
 *
 * ✓ "Sahibim" and 🔔 "Takip et" are the same collection-status field
 * (owned / wanted), so owning a volume ends tracking it — one volume is
 * never both. State follows the server response; the page is refreshed so
 * filters and counts stay in sync.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setVolumeCollectionStatus } from "@/services/catalog";
import type { CollectionStatus } from "@/types";
import { BellIcon, CheckIcon } from "@/components/volumeStock";

export function VolumeQuickActions({
  volumeId,
  label,
  initial,
}: {
  volumeId: number;
  /** "Cilt 3", for screen-reader button names. */
  label: string;
  initial: CollectionStatus | null;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<CollectionStatus | null>(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  async function toggle(target: "owned" | "wanted") {
    if (pending) return;
    setPending(true);
    setError(false);
    try {
      const updated = await setVolumeCollectionStatus(volumeId, status === target ? null : target);
      setStatus(updated.collection_status);
      router.refresh();
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  }

  const owned = status === "owned";
  const tracked = status === "wanted";
  const base =
    "grid size-9 place-items-center rounded-full border transition-colors disabled:opacity-50";

  return (
    <div className="flex shrink-0 items-center gap-1" title={error ? "Kaydedilemedi, tekrar deneyin" : undefined}>
      <button
        type="button"
        onClick={() => toggle("wanted")}
        disabled={pending}
        aria-pressed={tracked}
        aria-label={tracked ? `${label} takipten çıkar` : `${label} takip et`}
        title={tracked ? "Takipte" : "Takip et"}
        className={`${base} ${
          tracked
            ? "border-accent/40 bg-accent-soft text-accent"
            : "border-line text-muted hover:border-line-strong hover:text-ink"
        }`}
      >
        <BellIcon filled={tracked} />
      </button>
      <button
        type="button"
        onClick={() => toggle("owned")}
        disabled={pending}
        aria-pressed={owned}
        aria-label={owned ? `${label} sahip olduklarımdan çıkar` : `${label} sahibim`}
        title={owned ? "Sahibim" : "Sahibim olarak işaretle"}
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
