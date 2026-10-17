"use client";

/**
 * CollectionStatusPicker: mark the current volume "Bende var" / "Bende yok".
 * Wanting a volume is the separate wishlist; "Bende yok" never adds to it.
 *
 * The one interactive element on the volume page (hence a Client Component);
 * the API call goes through the catalog service, not raw fetch. State is
 * updated from the server response — no optimistic guesses — and a failure
 * reverts to the last confirmed status with a visible message.
 */

import { useState } from "react";
import { setVolumeCollectionStatus } from "@/services/catalog";
import type { CollectionStatus } from "@/types";

const OPTIONS: { value: CollectionStatus; label: string; activeClass: string; icon: string }[] = [
  {
    value: "owned",
    label: "Bende var",
    activeClass: "border-ok/50 bg-ok-soft text-ok",
    icon: "M5 12.5 10 17.5 19 7",
  },
  {
    value: "missing",
    label: "Bende yok",
    activeClass: "border-bad/40 bg-bad-soft text-bad",
    icon: "M7 7l10 10M17 7 7 17",
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
    <div className="space-y-1">
      {/* Two separate buttons (not a fused segment): each is its own state. */}
      <div role="group" aria-label="Koleksiyon durumu" className="grid grid-cols-2 gap-2">
        {OPTIONS.map((opt) => {
          const active = status === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              disabled={pending}
              onClick={() => pick(active ? null : opt.value)}
              title={active ? "Tekrar basınca kaldırılır" : undefined}
              className={`inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border px-2 text-sm font-semibold transition-colors disabled:opacity-60 ${
                active ? opt.activeClass : "border-line-strong bg-surface text-ink-2 hover:border-ink/40 hover:text-ink"
              }`}
            >
              <svg viewBox="0 0 24 24" aria-hidden className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={opt.icon} />
              </svg>
              {opt.label}
            </button>
          );
        })}
      </div>
      {/* Only when there is something to say: no reserved empty row. */}
      {(pending || error) && (
        <p className={`text-xs ${error ? "text-bad" : "text-muted"}`}>{error ?? "Kaydediliyor…"}</p>
      )}
    </div>
  );
}
