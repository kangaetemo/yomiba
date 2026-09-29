"use client";

/**
 * Admin-only: remove a store listing that was matched to the wrong volume
 * (e.g. a novel with the same title). The store product is also excluded
 * from future imports, so it cannot come back.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { deleteJson } from "@/lib/api";

export function RemoveListingButton({
  volumeId,
  listingId,
  store,
}: {
  volumeId: number;
  listingId: number;
  store: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    const reason = window.prompt(
      `${store} ilanı bu ciltten kaldırılsın mı? Ürün bir daha bu siteye bağlanmayacak.\n\nSebep (isteğe bağlı):`,
      "Yanlış ürün",
    );
    if (reason === null) return;
    setPending(true);
    setError(null);
    try {
      await deleteJson(`/volume/${volumeId}/listings/${listingId}?reason=${encodeURIComponent(reason)}`);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kaldırılamadı");
      setPending(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={() => void remove()}
        disabled={pending}
        className="inline-flex min-h-11 items-center rounded-lg border border-bad/40 px-3 text-xs font-semibold text-bad transition-colors hover:bg-bad-soft disabled:opacity-60"
      >
        {pending ? "Kaldırılıyor…" : "Kaldır"}
      </button>
      {error && <span className="text-xs text-bad">{error}</span>}
    </span>
  );
}
