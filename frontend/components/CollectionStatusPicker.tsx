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
    activeClass: "border-ok bg-ok/10 text-ok",
  },
  {
    value: "missing",
    label: "Eksik",
    activeClass: "border-bad bg-bad/10 text-bad",
  },
  {
    value: "wanted",
    label: "İstediğim",
    activeClass: "border-accent bg-accent/10 text-accent",
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
      <div className="flex flex-wrap items-center gap-2">
        {OPTIONS.map((opt) => {
          const active = status === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              disabled={pending}
              onClick={() => pick(active ? null : opt.value)}
              className={`rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-50 ${
                active
                  ? opt.activeClass
                  : "border-line bg-surface text-muted hover:border-muted hover:text-ink"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
        {status && (
          <button
            type="button"
            disabled={pending}
            onClick={() => pick(null)}
            className="rounded-lg px-2 py-1.5 text-xs text-muted transition-colors hover:text-ink disabled:opacity-50"
          >
            Temizle
          </button>
        )}
        {pending && <span className="text-xs text-muted">Kaydediliyor…</span>}
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
