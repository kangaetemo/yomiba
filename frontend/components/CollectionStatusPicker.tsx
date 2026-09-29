"use client";

/**
 * CollectionStatusPicker: mark the current volume owned / missing / wanted.
 *
 * The one interactive element on the volume page (hence a Client Component);
 * the API call goes through the catalog service, not raw fetch. State is
 * updated from the server response — no optimistic guesses — and a failure
 * reverts to the last confirmed status with a visible message.
 */

import { useState } from "react";
import { setVolumeCollectionStatus } from "@/services/catalog";
import type { CollectionStatus } from "@/types";

const OPTIONS: { value: CollectionStatus; label: string; activeClass: string }[] = [
  {
    value: "owned",
    label: "Sahibim",
    activeClass: "border-ok/50 bg-ok-soft text-ok",
  },
  {
    value: "missing",
    label: "Eksik",
    activeClass: "border-bad/40 bg-bad-soft text-bad",
  },
  {
    value: "wanted",
    label: "İstediğim",
    activeClass: "border-accent/40 bg-accent-soft text-accent",
  },
];

export function CollectionStatusPicker({
  volumeId,
  initial,
}: {
  volumeId: number;
  initial: CollectionStatus | null;
}) {
  const [status, setStatus] = useState<CollectionStatus | null>(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(next: CollectionStatus | null) {
    if (pending) return;
    const previous = status;
    setPending(true);
    setError(null);
    try {
      const updated = await setVolumeCollectionStatus(volumeId, next);
      setStatus(updated.collection_status);
    } catch (e) {
      setStatus(previous); // revert; the server state is unchanged
      setError(e instanceof Error ? e.message : "Durum güncellenemedi");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      <div role="group" aria-label="Koleksiyon durumu" className="grid grid-cols-3 gap-1.5 rounded-xl bg-surface-2 p-1">
        {OPTIONS.map((opt) => {
          const active = status === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              disabled={pending}
              onClick={() => pick(active ? null : opt.value)}
              className={`min-h-11 rounded-lg border text-sm font-semibold transition-colors disabled:opacity-60 ${
                active ? `${opt.activeClass} shadow-card` : "border-transparent text-muted hover:bg-surface hover:text-ink"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <div className="flex min-h-5 items-center justify-between text-xs">
        <span className="text-muted">{pending ? "Kaydediliyor…" : status ? "Aynı düğmeye tekrar basınca kaldırılır." : ""}</span>
        {error && <span className="text-bad">{error}</span>}
      </div>
    </div>
  );
}
