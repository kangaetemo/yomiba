"use client";

/**
 * StockAlertButton: "Stoğa girince haber ver" on a volume no store has in
 * stock. The alert mails once, after the next price refresh that finds the
 * volume in stock at any store; a fired alert can be set again.
 *
 * The server response is the source of truth; a failed call reverts and
 * shows the error.
 */

import { useState } from "react";
import { BellIcon } from "@/components/volumeStock";
import { deleteStockAlert, setStockAlert } from "@/services/catalog";
import type { StockAlert } from "@/types";

export function StockAlertButton({ volumeId, initial }: { volumeId: number; initial: StockAlert | null }) {
  const [alert, setAlert] = useState<StockAlert | null>(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A fired alert (mailed earlier, sold out again) waits for nothing.
  const waiting = alert !== null && alert.triggered_at === null;

  async function toggle() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const state = waiting ? await deleteStockAlert(volumeId) : await setStockAlert(volumeId);
      setAlert(state.alert);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stok alarmı güncellenemedi");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        aria-pressed={waiting}
        disabled={pending}
        onClick={toggle}
        className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors disabled:opacity-60 ${
          waiting
            ? "border border-ok/30 bg-ok-soft text-ok hover:border-ok/60"
            : "bg-accent text-on-accent hover:bg-accent-hover"
        }`}
      >
        <BellIcon filled={waiting} />
        {pending ? "Kaydediliyor…" : waiting ? "Stoğa girince haber vereceğiz" : "Stoğa girince haber ver"}
      </button>
      <p className="text-xs text-muted">
        {waiting
          ? "Bir mağazada stoğa girince e-posta atarız. Vazgeçmek için düğmeye tekrar bas."
          : "Bir mağazada stoğa girdiğini görünce e-postayla bir kez haber veririz."}
      </p>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}
