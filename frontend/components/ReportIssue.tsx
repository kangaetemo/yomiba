"use client";

/**
 * "Hatalı bilgi bildir": a small link under a series or volume page that
 * opens a short form. The report goes to the admin list (/admin/bildirimler).
 * The page address is sent along, so the reader only describes the problem.
 */

import { useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { REPORT_CATEGORIES, sendReport } from "@/services/reports";

const MIN = 10;
const MAX = 1000;

export function ReportIssue({ path, stores = [] }: { path: string; stores?: string[] }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<string>(REPORT_CATEGORIES[0].key);
  const [store, setStore] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const openedAt = useRef(0);

  function show() {
    openedAt.current = Date.now();
    setOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = message.trim();
    if (text.length < MIN) {
      setError(`Lütfen hatayı en az ${MIN} karakterle anlat.`);
      return;
    }
    setPending(true);
    setError(null);
    try {
      await sendReport({
        category, message: text, path, store: store || undefined,
        filled_ms: Date.now() - openedAt.current, website,
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Bildirim gönderilemedi. Biraz sonra tekrar dene.");
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <p role="status" className="text-sm text-ok">
        Teşekkürler! Bildirimin bize ulaştı; kontrol edip düzelteceğiz.
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={show}
        className="inline-flex min-h-11 items-center gap-1.5 text-sm text-muted underline decoration-line-strong underline-offset-4 hover:text-accent"
      >
        <span aria-hidden>⚑</span> Hatalı bilgi mi gördün? Bildir
      </button>
    );
  }

  const field = "w-full rounded-lg border border-line-strong bg-surface px-3 text-base text-ink placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-50";
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">Hatalı bilgi bildir</h2>
          <p className="text-sm text-muted">Neyin yanlış olduğunu yaz; bu sayfanın adresi bildirime otomatik eklenir.</p>
        </div>
        <button type="button" onClick={() => setOpen(false)} className="min-h-11 px-2 text-sm text-muted hover:text-ink">
          Vazgeç
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span className="text-ink-2">Konu</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={pending} className={`${field} min-h-11`}>
            {REPORT_CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </label>
        {stores.length > 0 && (
          <label className="space-y-1 text-sm">
            <span className="text-ink-2">Mağaza (isteğe bağlı)</span>
            <select value={store} onChange={(e) => setStore(e.target.value)} disabled={pending} className={`${field} min-h-11`}>
              <option value="">Belirli bir mağaza değil</option>
              {stores.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        )}
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-ink-2">Ne yanlış?</span>
        <textarea
          value={message}
          onChange={(e) => { setMessage(e.target.value); setError(null); }}
          disabled={pending}
          required
          minLength={MIN}
          maxLength={MAX}
          rows={4}
          placeholder="Örn. D&R'da fiyat 320 TL görünüyor, burada 250 TL yazıyor."
          className={`${field} py-2`}
        />
        <span className="block text-right text-xs text-faint">{message.length}/{MAX}</span>
      </label>
      {/* Bot trap: hidden from people and screen readers. */}
      <div aria-hidden className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label>
          Web sitesi
          <input type="text" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
        </label>
      </div>
      {error && <p className="text-sm text-bad">{error}</p>}
      <button
        type="submit"
        disabled={pending}
        className="min-h-11 rounded-lg bg-accent px-4 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
      >
        {pending ? "Gönderiliyor…" : "Gönder"}
      </button>
    </form>
  );
}
