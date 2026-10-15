"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/time";
import { controlIsbnAudit, decideIsbn, getIsbnDetail, getIsbnReviews, getIsbnSummary, recheckIsbn, startIsbnAudit } from "@/services/isbn";
import type { AuditStatus, DecisionAction, IsbnDetail, IsbnReview, IsbnSummary, ReviewQueue } from "@/services/isbn";

const labels: Record<AuditStatus, string> = {
  VERIFIED: "Doğrulandı", CONFLICT: "Çelişkili", MISSING_ISBN: "ISBN eksik",
  INSUFFICIENT_EVIDENCE: "Kanıt yetersiz", SOURCE_ERROR: "Kaynak hatası", SKIPPED_UPCOMING: "Yayın bekliyor",
};
const queueLabels: Record<ReviewQueue, string> = { APPROVAL: "ISBN onayı bekleyen", INVESTIGATE: "Çelişki incelemesi", AWAITING_EVIDENCE: "Kanıt / erişim bekleyen", REVIEWED: "İncelenen / alarm açılmayan" };
const sourceLabels: Record<string, string> = { kitapyurdu: "Kitapyurdu", bkm: "BKM Kitap", kitapsepeti: "Kitap Sepeti", bora: "Bora Dağıtım", pandora: "Pandora", dr: "D&R", mangakol: "MangaKol (katalog kaynağı)" };
const sourceStatuses: Record<string, string> = { MATCH: "Ürün eşleşti", MISMATCH: "Uyuşmuyor", INCOMPLETE: "Künye eksik · doğrulama için yetersiz", NO_RESULT: "Ürün bulunamadı", NO_ISBN: "ISBN belirtilmemiş", ERROR: "Erişilemedi", DISCOVERY: "Katalog bilgisi · bağımsız kanıt sayılmaz" };
const actions: Record<DecisionAction, string> = { KEEP: "Mevcut ISBN’yi koru", ACCEPT: "Önerilen ISBN’yi kabul et", MANUAL: "Manuel ISBN gir", DEFER: "İncelemeyi ertele" };
const button = "rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-sm font-semibold text-ink hover:bg-line disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const primary = "rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const input = "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent";
const message = (error: unknown) => error instanceof Error ? error.message : "İşlem tamamlanamadı. Yeniden deneyin.";
const volumeTitle = (row: IsbnReview) => `${row.snapshot.title}${row.snapshot.volume_number >= 0 ? ` · Cilt ${row.snapshot.volume_number}` : " · Numarasız kayıt"}`;

export function IsbnReviewCenter() {
  const [summary, setSummary] = useState<IsbnSummary | null>(null);
  const [rows, setRows] = useState<IsbnReview[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [queue, setQueue] = useState<ReviewQueue | "">("APPROVAL");
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const refresh = useCallback(() => setRevision(n => n + 1), []);
  const decisionSaved = useCallback((text: string) => { setNotice(text); refresh(); }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const params = new URLSearchParams({ offset: String(offset), limit: "30" });
        if (status) params.set("status", status);
        if (queue) params.set("queue", queue);
        if (query) params.set("q", query);
        const [nextSummary, list] = await Promise.all([getIsbnSummary(controller.signal), getIsbnReviews(params, controller.signal)]);
        if (controller.signal.aborted) return;
        setSummary(nextSummary); setRows(list.items); setTotal(list.total); setError(""); setLoading(false);
        timer = setTimeout(load, nextSummary.run?.status === "RUNNING" ? 4000 : 30000);
      } catch (e) {
        if (!controller.signal.aborted) { setError(message(e)); setLoading(false); timer = setTimeout(load, 15000); }
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [status, queue, query, offset, revision]);

  async function runAction(action: () => Promise<unknown>, text: string) {
    setBusy(true); setNotice(""); setError("");
    try { await action(); if (alive.current) { setNotice(text); refresh(); } }
    catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  }

  const open = summary?.run && ["RUNNING", "PAUSED"].includes(summary.run.status);
  if (summary && !summary.queues) return <p role="status" className="text-sm text-muted">İnceleme merkezi güncelleniyor. Yeni sayaçlar hazır olduğunda sayfa yenilenecek.</p>;
  return <div className="space-y-6">
    <section className="space-y-4 rounded-xl border border-line bg-surface p-5" aria-labelledby="isbn-scan-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 id="isbn-scan-title" className="font-semibold text-ink">Katalog denetimi</h2>
          <p className="mt-1 text-sm text-muted">İlk tarama tüm etkin kataloğu kapsar. Yakında olan ciltlerde ISBN alarmı açılmaz.</p></div>
        <button className={primary} disabled={busy || !summary || !!open} onClick={() => void runAction(startIsbnAudit, "Tarama başlatıldı. İlerleme burada güncellenecek.")}>Tüm kataloğu tara</button>
      </div>
      {summary?.run ? <div className="space-y-2 rounded-lg bg-surface-2 p-3 text-sm">
        <p className="font-medium text-ink">{summary.run.status === "RUNNING" ? "Tarama sürüyor" : summary.run.status === "PAUSED" ? "Tarama duraklatıldı" : summary.run.status === "COMPLETED" ? "Tarama tamamlandı" : "Tarama kesildi"} · {summary.run.processed} / {summary.run.total} cilt</p>
        <progress aria-label="ISBN tarama ilerlemesi" className="h-2 w-full accent-accent" value={summary.run.processed} max={Math.max(1, summary.run.total)} />
        <p className="text-muted">Başlangıç: {formatDateTime(summary.run.started_at)} · Erişim hatası görülen cilt: {summary.run.errors}</p>
        {summary.run.error && <p className="text-warn">{summary.run.error}</p>}
        {open && <button className={button} disabled={busy} onClick={() => void runAction(() => controlIsbnAudit(summary.run!.id, summary.run!.status === "PAUSED" ? "resume" : "pause"), "Tarama durumu güncellendi. Devam eden kaynak isteği bitince uygulanacak.")}>{summary.run.status === "PAUSED" ? "Kaldığı yerden sürdür" : "Taramayı duraklat"}</button>}
        {summary.run.status === "PAUSED" && <div className="space-y-2"><p className="text-muted">Yeni kaynaklarla baştan taramak için bu çalışmayı sonlandırıp “Tüm kataloğu tara” düğmesine basın. Önceki sonuçlar ve karar geçmişi saklanır.</p><button className={button} disabled={busy} onClick={() => void runAction(() => controlIsbnAudit(summary.run!.id, "stop"), "Çalışma sonlandırıldı; sonuçlar saklandı. Yeni kaynaklarla tüm kataloğu tarayabilirsiniz.")}>Taramayı sonlandır</button></div>}
      </div> : <p className="rounded-lg bg-new-soft p-3 text-sm text-new">Henüz ISBN denetimi yapılmadı. “Tüm kataloğu tara” ile başlayın; bulunan incelemeler aşağıda görünecek.</p>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {(["APPROVAL", "INVESTIGATE", "AWAITING_EVIDENCE"] as ReviewQueue[]).map(key => <button key={key} className={`rounded-lg border p-3 text-left ${queue === key ? "border-accent bg-accent-soft" : "border-line"}`} aria-pressed={queue === key} onClick={() => { setQueue(key); setOffset(0); setSelected(null); }}><span className="block text-xs text-muted">{queueLabels[key]}</span><span className="mt-1 block text-xl font-semibold tabular-nums text-ink">{summary?.queues[key] ?? "—"}</span></button>)}
      </div>
      <p className="text-sm text-muted">Yalnız ortak ISBN önerisi bulunan kayıtlar ISBN onayı bekler. Kaynak hataları ve eksik kanıt için tek tek karar vermeniz gerekmez; bu kayıtlar yeniden denenecek.</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {[{ label: "Taranan", value: summary?.scanned }, ...Object.entries(labels).map(([key, label]) => ({ label, value: summary?.counts[key as AuditStatus] || 0 }))].map(item =>
          <div className="rounded-lg border border-line p-3" key={item.label}><p className="text-xs text-muted">{item.label}</p><p className="mt-1 text-xl font-semibold tabular-nums text-ink">{summary ? item.value ?? 0 : "—"}</p></div>)}
      </div>
      <p className="text-xs text-muted">İlk tamamlanan taramadan sonra çözülmeyen kayıtlar günlük, doğrulananlar haftalık yeniden kontrol edilir. İki bağımsız kaynak aynı fiziksel baskıyı doğrulamadan ISBN uygulanmaz.</p>
    </section>
    {error && <p role="alert" className="rounded-lg bg-bad-soft p-3 text-sm text-bad">{error} <button className="underline" onClick={refresh}>Yeniden yükle</button></p>}
    {notice && <p role="status" className="rounded-lg bg-ok-soft p-3 text-sm text-ok">{notice}</p>}
    <section className="space-y-4" aria-labelledby="isbn-queue-title">
      <h2 id="isbn-queue-title" className="text-lg font-semibold text-ink">İnceleme kuyruğu <span className="font-normal text-muted">({total})</span></h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="space-y-1 text-xs text-muted">Kuyruk<select className={input} value={queue} onChange={e => { setQueue(e.target.value as ReviewQueue | ""); setOffset(0); setSelected(null); }}>{Object.entries(queueLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}<option value="">Tümü</option></select></label>
        <label className="space-y-1 text-xs text-muted">Denetim sonucu<select className={input} value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">Tüm sonuçlar</option>{Object.entries(labels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
        <form className="flex items-end gap-2" onSubmit={e => { e.preventDefault(); setQuery(draftQuery); setOffset(0); }}><label className="flex-1 space-y-1 text-xs text-muted">Seri ara<input className={input} value={draftQuery} onChange={e => setDraftQuery(e.target.value)} maxLength={200} /></label><button className={button} type="submit">Ara</button></form>
      </div>
      {loading ? <p role="status" className="text-sm text-muted">İncelemeler yükleniyor…</p> : rows.length === 0 ? <p className="rounded-xl border border-line bg-surface p-6 text-sm text-muted">{!summary?.scanned ? "İlk taramanın sonuçları henüz oluşmadı." : queue === "APPROVAL" ? "Bu filtrelerde ISBN değişikliği için onay bekleyen kayıt yok. Diğer sonuçları kuyruk seçicisinden inceleyebilirsiniz." : "Bu filtrelerde inceleme bulunamadı."}</p> : <ul className="space-y-2">{rows.map(row => <li key={row.volume_id}>
        <button className={`w-full rounded-xl border p-4 text-left transition-colors hover:bg-surface-2 ${selected === row.volume_id ? "border-accent bg-accent-soft" : "border-line bg-surface"}`} onClick={() => setSelected(row.volume_id)} aria-expanded={selected === row.volume_id}>
          <span className="flex flex-wrap justify-between gap-2"><span className="font-semibold text-ink">{volumeTitle(row)}</span><span className={`text-xs font-medium ${row.status === "VERIFIED" ? "text-ok" : "text-warn"}`}>{labels[row.status]}</span></span>
          <span className="mt-1 block text-sm text-muted">{row.snapshot.publisher} · Mevcut: {row.current_isbn || "Boş"} · Öneri: {row.proposed_isbn || "Yok"}</span>
          <span className="mt-1 block text-xs text-muted">{row.reason} · {formatDateTime(row.checked_at)}</span>
          <span className="mt-2 block text-sm font-medium text-new">Kanıtları ve karar geçmişini incele →</span>
        </button>
        {selected === row.volume_id && <ReviewDetail key={row.volume_id} id={row.volume_id} onChange={refresh} onDecision={decisionSaved} onClose={() => setSelected(null)} />}
      </li>)}</ul>}
      {total > 30 && <nav aria-label="İnceleme sayfaları" className="flex items-center justify-between"><button className={button} disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset-30)); setSelected(null); }}>Önceki</button><span className="text-sm text-muted">{offset+1}–{Math.min(total, offset+30)} / {total}</span><button className={button} disabled={offset+30 >= total} onClick={() => { setOffset(offset+30); setSelected(null); }}>Sonraki</button></nav>}
    </section>
  </div>;
}

function ReviewDetail({ id, onChange, onDecision, onClose }: { id: number; onChange: () => void; onDecision: (text: string) => void; onClose: () => void }) {
  const [detail, setDetail] = useState<IsbnDetail | null>(null);
  const [action, setAction] = useState<DecisionAction>("KEEP");
  const [reason, setReason] = useState("");
  const [isbn, setIsbn] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    getIsbnDetail(id, controller.signal).then(data => { if (!controller.signal.aborted) setDetail(data); }).catch(e => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [id, revision]);

  async function submit() {
    if (!detail) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await decideIsbn(id, { version: detail.version, result_id: detail.result_id, action, reason, ...(action === "MANUAL" ? { isbn } : {}) });
      if (alive.current) { const text = `Karar kaydedildi. ISBN: ${result.old_isbn || "Boş"} → ${result.new_isbn || "Boş"}`; setNotice(text); setReason(""); setRevision(n => n+1); onDecision(text); }
    } catch (e) {
      if (alive.current) { setError(message(e)); if (e instanceof ApiError && e.status === 409) { setRevision(n => n+1); onChange(); } }
    } finally { if (alive.current) setBusy(false); }
  }

  async function recheck() {
    setBusy(true); setError("");
    try { await recheckIsbn(id); if (alive.current) { setNotice("Bu cilt yeniden denetim sırasına alındı. Tarama bitince güncel kanıtları yükleyin."); onChange(); } }
    catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  }

  return <section aria-label="ISBN kanıtları ve karar" className="mt-2 space-y-5 rounded-xl border border-line-strong bg-surface p-4 sm:p-5">
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold text-ink">Kanıtlar ve karar</h3><button className={button} onClick={onClose}>Kapat</button></div>
    {error && <p role="alert" className="rounded-lg bg-bad-soft p-3 text-sm text-bad">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-ok-soft p-3 text-sm text-ok">{notice}</p>}
    {!detail ? <p className="text-sm text-muted">Kanıtlar yükleniyor…</p> : <>
      <div className="grid gap-3 text-sm sm:grid-cols-2"><div className="rounded-lg bg-surface-2 p-3"><p className="text-muted">Yomiba · güncel ISBN</p><p className="mt-1 font-mono font-semibold text-ink">{detail.current?.isbn || "Boş"}</p><p className="mt-1 text-muted">{detail.current?.publisher} · {detail.current?.title}</p></div><div className="rounded-lg bg-new-soft p-3"><p className="text-new">Kaynakların ortak önerisi</p><p className="mt-1 font-mono font-semibold text-ink">{detail.proposed_isbn || "Henüz yok"}</p><p className="mt-1 text-sm text-muted">{detail.reason}</p></div></div>
      {detail.stale && <p role="alert" className="rounded-lg bg-warn-soft p-3 text-sm text-warn">Bu denetimden sonra katalog bilgileri değişmiş. Karar vermeden önce cildi yeniden denetleyin.</p>}
      {detail.queue === "AWAITING_EVIDENCE" && <p className="rounded-lg bg-surface-2 p-3 text-sm text-muted">Bu kayıt kaynak erişimi veya ek kanıt bekliyor. Sizden ISBN onayı istenmiyor; mevcut ISBN korunuyor. Sonraki denetimde kaynaklar yeniden kontrol edilecek.</p>}
      {detail.queue === "INVESTIGATE" && <p className="rounded-lg bg-warn-soft p-3 text-sm text-warn">Kaynak bilgileri çelişiyor; uygulanabilecek ortak ISBN önerisi yok. Önce hangi ürün bilgisinin farklı olduğunu inceleyin.</p>}
      <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void recheck()}>Bu cildi yeniden denetle</button><button className={button} disabled={busy} onClick={() => { setRevision(n => n+1); onChange(); }}>Güncel kanıtları yükle</button></div>
      <div className="grid gap-3 sm:grid-cols-2">{detail.evidence.map((e, index) => <article key={`${e.source}-${index}`} className="space-y-2 rounded-lg border border-line p-3 text-sm">
        <div className="flex flex-wrap justify-between gap-2"><h4 className="font-semibold text-ink">{sourceLabels[e.source] || e.source}</h4><span className={e.status === "MATCH" ? "text-ok" : "text-warn"}>{sourceStatuses[e.status] || e.status}</span></div>
        <p className="font-mono text-ink">{e.isbn || e.raw_isbns?.join(" / ") || (e.status === "NO_RESULT" ? "Bu aramada ürün eşleşmedi" : e.status === "ERROR" ? "Kaynağa erişilemediği için ISBN kontrol edilemedi" : "ISBN belirtilmemiş")}</p>
        {e.title && <p className="text-ink">{e.title}</p>}
        <p className="text-muted">{[e.publisher, e.language, e.binding].filter(Boolean).join(" · ")}</p>
        <p className="text-muted">{e.reason}</p><p className="text-xs text-muted">Kontrol: {formatDateTime(e.checked_at)}</p>
        {e.url?.startsWith("https://") && <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-new underline">Ürün kaydını aç ↗</a>}
      </article>)}</div>
      {!detail.evidence.some(e => e.source === "mangakol") && <p className="text-xs text-muted">MangaKol ISBN’si bu denetimde okunmadı. MangaKol katalog bilgisi iki bağımsız dış kanıtın yerine geçmez.</p>}
      {detail.evidence.length === 0 && <p className="text-sm text-muted">Yayımlandığı doğrulanmadığı için dış kaynak sorgusu yapılmadı.</p>}
      {detail.queue !== "AWAITING_EVIDENCE" && <form className="space-y-3 border-t border-line pt-4" onSubmit={e => { e.preventDefault(); void submit(); }}>
        <h4 className="font-semibold text-ink">Yönetici kararı</h4>
        <label className="block space-y-1 text-sm text-muted">Karar<select className={input} value={action} onChange={e => setAction(e.target.value as DecisionAction)} disabled={busy}>{Object.entries(actions).map(([key, label]) => <option value={key} key={key} disabled={(key === "ACCEPT" && !detail.proposed_isbn) || (["ACCEPT", "MANUAL"].includes(key) && !detail.approval_enabled)}>{label}</option>)}</select></label>
        {action === "MANUAL" && <label className="block space-y-1 text-sm text-muted">ISBN<input className={input} value={isbn} maxLength={30} onChange={e => setIsbn(e.target.value)} required inputMode="numeric" /></label>}
        {(["ACCEPT", "MANUAL"] as string[]).includes(action) && <p className="text-sm text-muted">ISBN güncellemesi için son 24 saatte aynı fiziksel baskıyı doğrulayan iki bağımsız kanıt gerekir. Manuel girişte de bu kural uygulanır.</p>}
        <label className="block space-y-1 text-sm text-muted">Gerekçe<textarea className={input} value={reason} onChange={e => setReason(e.target.value)} required minLength={3} maxLength={2000} rows={3} placeholder="Bu kararı hangi ürün bilgilerine dayanarak verdiniz?" /></label>
        <button className={primary} type="submit" disabled={busy || detail.stale || reason.trim().length < 3}>{busy ? "İşleniyor…" : action === "ACCEPT" || action === "MANUAL" ? "Kararı kaydet ve ISBN’yi uygula" : "Kararı kaydet"}</button>
      </form>}
      <div className="space-y-3 border-t border-line pt-4"><h4 className="font-semibold text-ink">Karar geçmişi</h4>{detail.decisions.length === 0 ? <p className="text-sm text-muted">Henüz yönetici kararı yok.</p> : <ol className="space-y-3">{detail.decisions.map(d => <li key={d.id} className="rounded-lg bg-surface-2 p-3 text-sm"><p className="font-medium text-ink">{actions[d.action as DecisionAction] || d.action} · {d.admin}</p><p className="mt-1 font-mono text-ink">{d.old_isbn || "Boş"} → {d.new_isbn || "Boş"}</p><p className="mt-1 text-muted">{d.reason}</p><p className="mt-1 text-xs text-muted">{formatDateTime(d.decided_at)} · İnceleme sürümü {d.review_version}</p></li>)}</ol>}</div>
    </>}
  </section>;
}
