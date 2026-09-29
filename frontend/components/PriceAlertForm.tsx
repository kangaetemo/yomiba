"use client";

/**
 * PriceAlertForm: set / update / pause / delete the single price alert for
 * the current volume ("notify me when the price drops to X or below").
 *
 * Client Component only because it is interactive. State comes from the
 * server response (no optimistic updates); failures revert and are shown.
 * The stored condition only — no notification exists in this phase.
 *
 * Input is entered in TRY and sent to the API in integer CENTS.
 */

import { useState } from "react";
import { formatPrice } from "@/components/PriceBadge";
import {
  deletePriceAlert,
  setPriceAlert,
} from "@/services/catalog";
import type { PriceAlert } from "@/types";

export function PriceAlertForm({
  volumeId,
  initialAlert,
}: {
  volumeId: number;
  initialAlert: PriceAlert | null;
}) {
  const [alert, setAlert] = useState<PriceAlert | null>(initialAlert);
  const [input, setInput] = useState<string>(
    initialAlert ? String(initialAlert.threshold_price / 100) : "",
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Parse a user-entered TRY amount into integer cents (or null if invalid).
   * Accepts Turkish formatting: "1.500,50" / "1.500" (dot = thousands) as
   * well as "150,50" and "150.50".
   */
  function toCents(raw: string): number | null {
    let text = raw.trim().replace(/\s|₺|TL/gi, "");
    if (!text) return null;
    if (text.includes(",")) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
      text = text.replace(/\./g, "");
    }
    if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
    const value = Number(text);
    if (!Number.isFinite(value) || value <= 0 || value > 10_000_000) return null;
    return Math.round(value * 100);
  }

  async function call(action: () => Promise<{ alert: PriceAlert | null }>) {
    if (pending) return;
    const previous = alert;
    setPending(true);
    setError(null);
    try {
      const state = await action();
      setAlert(state.alert);
      if (state.alert) setInput(String(state.alert.threshold_price / 100));
    } catch (e) {
      setAlert(previous);
      setError(e instanceof Error ? e.message : "Alarm güncellenemedi");
    } finally {
      setPending(false);
    }
  }

  function saveThreshold() {
    const cents = toCents(input);
    if (cents === null) {
      setError("Geçerli bir fiyat girin (ör. 150 veya 150,50).");
      return;
    }
    void call(() => setPriceAlert(volumeId, cents, null));
  }

  return (
    <div className="max-w-xl space-y-2">
      {alert && (
        <p className="text-sm text-ink-2">
          Mevcut alarm:{" "}
          <span className="font-semibold text-ink">
            {formatPrice(alert.threshold_price / 100)}
          </span>{" "}
          <span
            className={
              alert.is_active
                ? "text-ok"
                : "text-muted"
            }
          >
            {alert.is_active ? "(aktif)" : "(pasif)"}
          </span>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor={`price-alert-${volumeId}`}>
          Fiyat eşiği (TL)
        </label>
        <input
          id={`price-alert-${volumeId}`}
          type="text"
          inputMode="decimal"
          placeholder="Örn. 150 TL"
          value={input}
          disabled={pending}
          onChange={(e) => {
            setInput(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveThreshold();
          }}
          className="w-32 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          disabled={pending}
          onClick={saveThreshold}
          className="rounded-lg border border-accent/60 bg-accent/10 px-3 py-1.5 text-sm text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
        >
          {alert ? "Alarmı güncelle" : "Alarm kur"}
        </button>

        {alert && (
          <>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                void call(() => setPriceAlert(volumeId, null, !alert.is_active))
              }
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-muted transition-colors hover:border-muted hover:text-ink disabled:opacity-50"
            >
              {alert.is_active ? "Pasifleştir" : "Etkinleştir"}
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => void call(() => deletePriceAlert(volumeId))}
              className="rounded-lg px-2 py-1.5 text-xs text-muted transition-colors hover:text-bad disabled:opacity-50"
            >
              Alarmı sil
            </button>
          </>
        )}
        {pending && <span className="text-xs text-muted">Kaydediliyor…</span>}
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}
      <p className="text-xs text-faint">
        Bu fiyatın altına düşünce haber ver (kontrol ve bildirimler ilerideki
        bir aşamada etkinleşecek; şimdilik koşul kaydediliyor).
      </p>
    </div>
  );
}
