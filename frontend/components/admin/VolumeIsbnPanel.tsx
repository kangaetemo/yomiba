"use client";

/**
 * Admin-only box on a volume page: where the volume's ISBN came from, what
 * Mangakol and the stores say, why each store product is (or is not) on
 * this volume, the change log, and a form to decide the ISBN by hand.
 */

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { formatDateTime } from "@/lib/time";
import { decideVolumeIsbn, getVolumeIsbn } from "@/services/isbn";
import type { IsbnDecision, VolumeIsbnEvidence } from "@/services/isbn";

const sources: Record<string, string> = {
  catalog: "Mangakol", stores: "mağaza uzlaşısı", admin: "admin kararı", legacy: "eski kayıt",
  moved: "taşındı", shared: "ortak baskı", unshared: "ortaklık kaldırıldı",
};
const rules: Record<string, string> = {
  "isbn+title": "ISBN ve başlık aynı cildi gösteriyor", isbn: "ISBN ile", title: "sadece başlıkla",
  edition: "baskı kelimesi / fiyat aralığı ile",
  title_over_isbn: "başlıkla (ürünün ISBN’i başka bir cildi gösteriyor, kontrol edin)",
};
const reasons: Record<string, string> = {
  isbn_title_conflict: "başlık ve ISBN farklı ciltleri gösteriyor", isbn_conflict: "ISBN bu cildinkinden farklı",
  edition_ambiguous: "hangi baskı olduğu belirlenemedi", foreign_edition: "yabancı baskı",
duplicate: "aynı mağazada daha uygun baskı seçildi",
  excluded: "admin kaldırmıştı", non_book_product: "kitap değil",
};
const issues: Record<string, string> = {
  catalog_duplicate: "Mangakol bu ISBN’i başka bir kitaba da vermiş", catalog_differs: "Mangakol farklı bir ISBN listeliyor",
  stores_vs_catalog: "Mağazalar Mangakol’la çelişiyor", stores_disagree: "Mağazalar kendi aralarında çelişiyor",
  isbn_claimed: "Bu ISBN başka bir ciltte",
};
const button = "inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface-2 px-3 text-sm font-semibold text-ink hover:bg-line disabled:opacity-60";
const input = "min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink";

export function VolumeIsbnPanel({ volumeId }: { volumeId: number }) {
  const router = useRouter();
  const [data, setData] = useState<VolumeIsbnEvidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [isbn, setIsbn] = useState("");
  const [reason, setReason] = useState("");
  const [share, setShare] = useState(false);
  const [move, setMove] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await getVolumeIsbn(volumeId);
      setData(next);
      setIsbn((current) => current || next.isbn || "");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ISBN bilgisi alınamadı.");
    }
  }, [volumeId]);

  async function submit(body: IsbnDecision) {
    setBusy(true);
    setError(null);
    try {
      await decideVolumeIsbn(volumeId, body);
      setReason("");
      await load();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      className="group rounded-2xl border border-dashed border-line-strong bg-surface/60"
      onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && !data) void load(); }}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 text-sm font-semibold text-muted hover:text-ink">
        <span>Admin: ISBN ve eşleşmeler · ziyaretçiler görmez</span>
        <span aria-hidden className="transition-transform group-open:rotate-180">⌄</span>
      </summary>
      <div className="space-y-4 border-t border-line p-4 text-sm">
        {error && <p role="alert" className="text-bad">{error}</p>}
        {!data ? <p className="text-muted">Yükleniyor…</p> : <>
          <dl className="grid gap-2 sm:grid-cols-2">
            <div><dt className="text-xs text-faint">ISBN</dt>
              <dd className="font-mono text-ink">{data.isbn ?? "—"}{data.isbn_source ? <span className="ml-2 font-sans text-xs text-muted">({sources[data.isbn_source] ?? data.isbn_source})</span> : null}</dd></div>
            <div><dt className="text-xs text-faint">Mangakol</dt><dd className="font-mono text-ink">{data.catalog_isbn ?? "—"}</dd></div>
            {data.shared.length > 0 && <div><dt className="text-xs text-faint">Başka baskıyla ortak</dt><dd className="font-mono text-ink">{data.shared.join(", ")}</dd></div>}
            <div><dt className="text-xs text-faint">Mağaza oyları (başlığı bu cildi gösteren ürünler)</dt>
              <dd className="text-ink">{Object.keys(data.votes).length ? Object.entries(data.votes).map(([k, n]) => `${k} × ${n}`).join(", ") : "—"}</dd></div>
          </dl>
          {data.issue && <p className="rounded-lg bg-warn-soft p-3 text-ink">
            <strong>Çelişki:</strong> {issues[data.issue.kind] ?? data.issue.kind}. Sistem bir şey değiştirmedi; aşağıdan karar verebilirsiniz.
          </p>}

          <div className="space-y-2">
            <h3 className="font-semibold text-ink">Mağaza ürünleri: bu ilan neden burada?</h3>
            {data.observations.length === 0 ? <p className="text-muted">Henüz gözlem yok; bir sonraki fiyat taramasında dolacak.</p> :
              <ul className="divide-y divide-line">
                {data.observations.map((o) => (
                  <li key={o.url} className="space-y-0.5 py-2">
                    <div className="flex flex-wrap justify-between gap-x-3">
                      <a href={o.url} target="_blank" rel="noreferrer" className="font-semibold text-new hover:underline">{o.store}: “{o.title}”</a>
                      <span className="font-mono text-xs text-muted">{o.isbn ?? "ISBN yok"}</span>
                    </div>
                    <p className="text-xs text-muted">
                      {o.attached_volume_id === data.volume_id
                        ? `Bu cilde bağlı: ${rules[o.rule ?? ""] ?? o.rule}`
                        : o.attached_volume ? `${o.attached_volume} cildine bağlı` : `Bağlanmadı: ${reasons[o.reason ?? ""] ?? o.reason ?? "—"}`}
                      {" · "}başlık → {o.title_volume ?? "bulunamadı"} · ISBN → {o.isbn_volume ?? "katalogda yok"}
                      {" · "}{formatDateTime(o.last_seen)}
                    </p>
                  </li>
                ))}
              </ul>}
          </div>

          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); void submit({ isbn: isbn.trim() || null, reason, share, move }); }}>
            <h3 className="font-semibold text-ink">ISBN kararı</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1"><span className="text-xs text-faint">ISBN (boş bırakılırsa silinir)</span>
                <input className={input} value={isbn} onChange={(e) => setIsbn(e.target.value)} inputMode="numeric" /></label>
              <label className="space-y-1"><span className="text-xs text-faint">Gerekçe</span>
                <input className={input} value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} placeholder="ör. kitabın barkodu" /></label>
            </div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} /> Aynı kitabın başka baskısıyla ortak ISBN</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={move} onChange={(e) => setMove(e.target.checked)} /> ISBN başka bir ciltteyse oradan buraya taşı</label>
            <div className="flex flex-wrap gap-2">
              <button type="submit" className={button} disabled={busy}>Kaydet</button>
              <button type="button" className={button} disabled={busy || reason.trim().length < 3}
                onClick={() => void submit({ reason, automatic: true })}>Kararı otomatiğe bırak</button>
            </div>
            <p className="text-xs text-faint">Admin kararını otomatik sistem değiştirmez. “Otomatiğe bırak”, kararı kaldırıp Mangakol ve mağaza kanıtına göre yeniden çözer.</p>
          </form>

          {data.changes.length > 0 && <div className="space-y-1">
            <h3 className="font-semibold text-ink">Değişiklik geçmişi</h3>
            <ul className="space-y-1 text-xs text-muted">
              {data.changes.map((c, i) => <li key={i}>{formatDateTime(c.at)} · {c.old ?? "boş"} → {c.new ?? "boş"} · {sources[c.source] ?? c.source} · {c.reason}</li>)}
            </ul>
          </div>}
        </>}
      </div>
    </details>
  );
}
