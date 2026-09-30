"use client";

/**
 * AdminControls: no-auth operational panel (P26).
 *
 * Two independent panels sharing one component file (kept small on purpose):
 * 1. Catalog sync — live status (polled while running) + manual trigger.
 * 2. Store import — run an import for a query, show per-store results,
 *    failures and duration; below it the recent import-attempt history.
 *
 * All API calls go through services/admin.ts; the server response is the
 * source of truth (no optimistic state).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCatalogSyncStatus,
  getCoverStatus,
  getForeignEditions,
  applyForeignEditions,
  scanForeignEditions,
  getImportCoverage,
  getImportRecords,
  getMissingCoverage,
  getPriceRefreshStatus,
  runImport,
  runIsbnFix,
  startCatalogSync,
  startCoverFetch,
  startMissingPriceRefresh,
  startPriceRefresh,
} from "@/services/admin";
import type {
  CatalogSyncStatus,
  CoverStatus,
  ForeignEditionStatus,
  ImportCoverage,
  ImportRecord,
  ImportReport,
  IsbnFixResult,
  MissingCoverage,
  PriceRefreshStatus,
} from "@/types";

const SYNC_POLL_MS = 5000;
/** Shelf-coverage polling cadence while imports are in flight. */
const COVERAGE_POLL_MS = 20000;
/** The dev-server rewrite proxy drops requests longer than ~30 s, but the
 * import keeps running server-side — so after a failed POST we follow the
 * import through the record history (poll every 30 s, cap 4 min). */
const RECORD_POLL_MS = 30000;
const RECORD_POLL_ATTEMPTS = 8;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Wall-clock seconds since the (ISO) start timestamp. Module-scoped so the
 * React purity rule doesn't see Date.now() inside component code. */
function secondsSince(startIso: string): number {
  return Math.max(1, Math.round((Date.now() - new Date(startIso).getTime()) / 1000));
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function durationSeconds(start: string, end: string | null): string {
  if (!end) return "—";
  const s = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  return `${s} sn`;
}

// -- 1) Catalog sync ---------------------------------------------------------------

/** Known wrong-volume ISBNs (Akame 3 on Cilt 2, Teogonia 1-2 on Cilt 2):
 * preview first, then apply — the admin-panel form of fix_isbn_conflicts.py
 * for when no shell access is possible. */
function IsbnFixBox({ disabled }: { disabled: boolean }) {
  const [result, setResult] = useState<IsbnFixResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(apply: boolean) {
    if (busy) return;
    if (apply && !window.confirm("ISBN düzeltmeleri uygulansın mı? Önce veritabanı yedeği alınır.")) return;
    setBusy(apply ? "apply" : "preview");
    setError(null);
    try {
      setResult(await runIsbnFix(apply));
    } catch (e) {
      setError(e instanceof Error ? e.message : "ISBN düzeltmesi çalıştırılamadı");
    } finally {
      setBusy(null);
    }
  }

  const pending = result?.mode === "dry-run" && result.cases.some((c) => c.status === "ok");

  return (
    <div className="space-y-2 rounded-lg border border-line p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted">
          Bilinen yanlış cilt ISBN&apos;leri (Akame, Teogonia): ISBN doğru cilde taşınır, ilanlar
          yalnızca ürün sayfasındaki ISBN ile kanıtlanırsa taşınır.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void run(false)}
            disabled={disabled || busy !== null}
            className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 font-semibold text-ink transition-colors hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "preview" ? "Kontrol ediliyor…" : "Önizle"}
          </button>
          <button
            type="button"
            onClick={() => void run(true)}
            disabled={disabled || busy !== null || !pending}
            title={pending ? undefined : "Önce önizleyin"}
            className="rounded-lg bg-accent px-3 py-1.5 font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "apply" ? "Uygulanıyor…" : "Uygula"}
          </button>
        </div>
      </div>

      {error && <p className="text-bad">{error}</p>}
      {result?.applied && (
        <p className="text-ok">
          Uygulandı: {result.moved_listings} ilan taşındı. Yedek: {result.backup}
        </p>
      )}
      {result && !result.applied && result.mode === "apply" && (
        <p className="text-muted">Uygulanacak bir şey yok.</p>
      )}
      {result && (
        <ul className="space-y-2">
          {result.cases.map((c) => (
            <li key={c.series}>
              <p className="text-ink-2">
                <span className="font-semibold">{c.series}</span>: ISBN {c.isbn}, Cilt {c.from_volume} → Cilt{" "}
                {c.to_volume}{" "}
                {c.status === "ok" ? (
                  <span className="text-ok">{result.applied ? "düzeltildi" : "düzeltilecek"}</span>
                ) : (
                  <span className="text-muted">atlandı ({c.reason})</span>
                )}
              </p>
              {c.listings.length > 0 && (
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
                  {c.listings.map((l) => (
                    <li key={l.listing_id}>
                      {l.store}:{" "}
                      <span className={l.action === "move" ? "text-ok" : ""}>
                        {l.action === "move" ? `taşınacak (sayfa ISBN ${l.page_isbn})` : `kalacak (${l.why ?? "—"})`}
                      </span>{" "}
                      <a href={l.product_url} target="_blank" rel="noopener noreferrer" className="underline">
                        ürün
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Foreign-edition clean-up: scan (background), review, apply. */
function ForeignEditionsBox() {
  const [status, setStatus] = useState<ForeignEditionStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getForeignEditions());
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Durum alınamadı");
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [refresh]);

  useEffect(() => {
    if (status?.state !== "scanning") return;
    const id = setInterval(() => void refresh(), 3000);
    return () => clearInterval(id);
  }, [status?.state, refresh]);

  async function scan() {
    setBusy(true);
    setMessage(null);
    try {
      await scanForeignEditions();
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Tarama başlatılamadı");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!window.confirm("Yabancı baskı ilanları kaldırılsın ve engellensin mi? Önce veritabanı yedeği alınır.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await applyForeignEditions();
      setMessage(`Uygulandı: ${result?.removed_listings ?? 0} ilan kaldırıldı, ${result?.cleared_isbns ?? 0} cildin yabancı ISBN'i temizlendi.`);
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Uygulanamadı");
    } finally {
      setBusy(false);
    }
  }

  const plan = status?.plan;
  const remove = plan?.listings.filter((l) => l.action === "remove") ?? [];
  const scanning = status?.state === "scanning";
  return (
    <div className="space-y-2 rounded-lg border border-line p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted">
          Yabancı baskı taraması: İngilizce vb. baskıların ilanlarını ürün sayfasıyla kanıtlayıp kaldırır.
          {scanning && <span className="ml-1 text-accent">· taranıyor…</span>}
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void scan()}
            disabled={busy || scanning || status?.state === "applying"}
            className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 font-semibold text-ink hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
          >
            Tara
          </button>
          <button
            type="button"
            onClick={() => void apply()}
            disabled={busy || status?.state !== "ready" || remove.length + (plan?.foreign_isbn_volumes.length ?? 0) === 0}
            className="rounded-lg bg-accent px-3 py-1.5 font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            Uygula
          </button>
        </div>
      </div>
      {status?.error && <p className="text-bad">{status.error}</p>}
      {message && <p className="text-muted">{message}</p>}
      {plan && status?.state === "ready" && (
        <div className="space-y-1.5">
          <p className="text-ink-2">
            {plan.scanned}/{plan.total_candidates} ilan tarandı · {remove.length} ilan kaldırılacak ·{" "}
            {plan.foreign_isbn_volumes.length} cildin yabancı ISBN&apos;i temizlenecek
          </p>
          {remove.length > 0 && (
            <ul className="max-h-72 list-disc space-y-0.5 overflow-y-auto pl-5 text-muted">
              {remove.map((l) => (
                <li key={l.listing_id}>
                  {l.series} Cilt {l.volume_number} · {l.store} · {l.page_isbn ?? "ISBN yok"}
                  {l.page_language ? ` · ${l.page_language}` : ""}{" "}
                  <a href={l.product_url} target="_blank" rel="noopener noreferrer" className="underline">
                    ürün
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Self-hosted covers: progress + "run a pass now". */
function CoverBox() {
  const [status, setStatus] = useState<CoverStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getCoverStatus());
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Kapak durumu alınamadı");
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [refresh]);

  useEffect(() => {
    if (!status?.running) return;
    const id = setInterval(() => void refresh(), SYNC_POLL_MS);
    return () => clearInterval(id);
  }, [status?.running, refresh]);

  async function run() {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      await startCoverFetch();
      setMessage("Kapak indirme başladı.");
      setTimeout(() => void refresh(), 1500);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Başlatılamadı");
    } finally {
      setBusy(false);
    }
  }

  const pct = status && status.total > 0 ? Math.round((100 * status.stored) / status.total) : 0;
  return (
    <div className="space-y-2 rounded-lg border border-line p-3 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted">
          Kapaklar kendi sunucumuzdan: {status ? `${status.stored} / ${status.total} cilt (%${pct})` : "…"}
          {status?.running && <span className="ml-1 text-accent">· indiriliyor…</span>}
        </p>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || !status?.enabled || status.running}
          title={status && !status.enabled ? "Kapak indirici kapalı (COVERS_ENABLED)" : undefined}
          className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 font-semibold text-ink transition-colors hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
        >
          Şimdi indir
        </button>
      </div>
      {status?.last && (
        <p className="text-faint">
          Son tur: {status.last.stored} kapak kaydedildi, {status.last.downloads} indirme,{" "}
          {status.last.without_source} ciltte kaynak yok, {status.last.remaining} bekliyor.
        </p>
      )}
      {message && <p className="text-muted">{message}</p>}
    </div>
  );
}

function CatalogSyncPanel() {
  const [status, setStatus] = useState<CatalogSyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getCatalogSyncStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Senkron durumu alınamadı");
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [refresh]);

  // Poll while a sync is running; stop as soon as it finishes.
  useEffect(() => {
    if (status?.running) {
      timer.current = setInterval(() => void refresh(), SYNC_POLL_MS);
    }
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [status?.running, refresh]);

  async function trigger() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await startCatalogSync();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Senkron başlatılamadı");
    } finally {
      setBusy(false);
    }
  }

  const last = status?.last ?? null;

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">
          Katalog senkronu
          {status?.running && (
            <span className="ml-2 text-sm font-normal text-accent">
              · çalışıyor…
            </span>
          )}
        </h2>
        <button
          type="button"
          onClick={trigger}
          disabled={busy || status?.running}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status?.running ? "Senkron çalışıyor" : "Senkronu başlat"}
        </button>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      {last ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-muted">Sonuç</dt>
            <dd className={last.status === "success" ? "text-ok" : "text-bad"}>
              {last.status === "success" ? "Başarılı" : "Başarısız"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Manga</dt>
            <dd className="text-ink-2">
              {last.manga_total} (hata: {last.manga_failed})
            </dd>
          </div>
          <div>
            <dt className="text-muted">Yeni / birleştirilen seri</dt>
            <dd className="text-ink-2">
              {last.series_created} / {last.series_merged}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Yeni cilt</dt>
            <dd className="text-ink-2">{last.volumes_added}</dd>
          </div>
          <div>
            <dt className="text-muted">ISBN (eklenen / okunan sayfa / çakışma)</dt>
            <dd className="text-ink-2">
              {last.isbns_added ?? 0} / {last.isbn_pages ?? 0} / {last.isbn_conflicts ?? 0}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Birleştirilen eski “Cilt -1” kaydı</dt>
            <dd className="text-ink-2">{last.isbn_phantoms_merged ?? 0}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted">
          Bu oturumda henüz senkron çalışmadı.
        </p>
      )}

      {last && last.errors.length > 0 && (
        <p className="text-xs text-bad">
          Hatalar: {last.errors.slice(0, 3).join(" · ")}
        </p>
      )}

      {last && (last.isbn_conflict_details?.length ?? 0) > 0 && (
        <details className="text-xs text-warn">
          <summary className="cursor-pointer">
            ISBN çakışmaları ({last.isbn_conflicts}) — otomatik taşınmadı, kontrol edilmeli
          </summary>
          <ul className="mt-1 max-h-80 list-disc space-y-0.5 overflow-y-auto pl-5 text-muted">
            {last.isbn_conflict_details!.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </details>
      )}

      <IsbnFixBox disabled={Boolean(status?.running)} />
      <CoverBox />
      <ForeignEditionsBox />
    </section>
  );
}

// -- 2) Store import + history ------------------------------------------------------

const STATUS_LABEL: Record<ImportRecord["status"], string> = {
  running: "çalışıyor",
  success: "başarılı",
  partial: "kısmi",
  failed: "başarısız",
  skipped: "atlandı",
};

function ImportPanel() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [recordResult, setRecordResult] = useState<{
    record: ImportRecord;
    seconds: number;
  } | null>(null);
  const [records, setRecords] = useState<ImportRecord[]>([]);

  const refreshRecords = useCallback(async () => {
    try {
      setRecords(await getImportRecords(20));
    } catch {
      // history is a secondary view; a failure here must not break the panel
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refreshRecords(), 0);
    return () => clearTimeout(id);
  }, [refreshRecords]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setReport(null);
    setRecordResult(null);
    try {
      setReport(await runImport(q));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "İçe aktarma başarısız";
      if (msg.includes("çalışıyor")) {
        // real conflict (per-query or sync gate) — nothing to poll for
        setError(msg);
      } else {
        // proxy timeout / network error: the import keeps running
        // server-side, so follow it through the record history
        const record = await waitForRecord(q);
        if (record && record.last_attempt_at) {
          setRecordResult({ record, seconds: secondsSince(record.last_attempt_at) });
        } else {
          setError(
            "İçe aktarma 4 dakika içinde tamamlanmadı; sayfayı yenileyip \"Son içe aktarmalar\" tablosunu kontrol edin.",
          );
        }
      }
    }
    await refreshRecords();
    setBusy(false);
  }

  async function waitForRecord(q: string): Promise<ImportRecord | null> {
    const wanted = q.toLowerCase();
    for (let i = 0; i < RECORD_POLL_ATTEMPTS; i++) {
      await sleep(RECORD_POLL_MS);
      try {
        const recs = await getImportRecords(20);
        const rec = recs.find(
          (r) =>
            (r.last_query ?? "").toLowerCase() === wanted ||
            r.normalized_query.toLowerCase() === wanted,
        );
        if (rec && rec.status !== "running") return rec;
      } catch {
        // transient failure — keep polling
      }
    }
    return null;
  }

  return (
    <section className="space-y-4 rounded-xl border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold text-ink">
        Mağaza içe aktarma
      </h2>

      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Sorgu (örn. Berserk)"
          aria-label="İçe aktarma sorgusu"
          className="min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || query.trim() === ""}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "İçe aktarılıyor…" : "İçe aktar"}
        </button>
      </form>

      {busy && (
        <p className="text-sm text-muted">
          Mağazalar taranıyor — 1-2 dakika sürebilir. Bağlantı 30 saniyede
          kopsa bile işlem sunucuda devam eder; sonuç aşağıda belirir.
        </p>
      )}
      {error && <p className="text-xs text-bad">{error}</p>}

      {recordResult && (
        <div className="space-y-1 rounded-lg border border-line bg-paper/50 p-3">
          <p className="text-sm text-ink-2">
            “{recordResult.record.last_query ?? recordResult.record.normalized_query}” —{" "}
            {STATUS_LABEL[recordResult.record.status]} · {recordResult.record.created}{" "}
            yeni, {recordResult.record.updated} güncellendi ·{" "}
            {recordResult.record.stores_ok}/
            {recordResult.record.stores_ok + recordResult.record.stores_failed} mağaza
            başarılı · süre ≈ {recordResult.seconds} sn
          </p>
          {recordResult.record.error && (
            <p className="text-xs text-bad">{recordResult.record.error}</p>
          )}
        </div>
      )}

      {report && (
        <div className="space-y-2">
          <p className="text-sm text-ink-2">
            “{report.query}” — {report.total_created} yeni, {report.total_updated}{" "}
            güncellendi · süre: {durationSeconds(report.started_at, report.finished_at)}
          </p>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-muted">
                <th className="py-1 pr-3">Mağaza</th>
                <th className="py-1 pr-3">Buldu</th>
                <th className="py-1 pr-3">Yeni</th>
                <th className="py-1 pr-3">Güncellendi</th>
                <th className="py-1">Hata</th>
              </tr>
            </thead>
            <tbody>
              {report.stores.map((s) => (
                <tr key={s.store_code} className="border-t border-line">
                  <td className="py-1.5 pr-3 text-ink-2">{s.store_name}</td>
                  <td className="py-1.5 pr-3 text-muted">{s.results_found}</td>
                  <td className="py-1.5 pr-3 text-muted">{s.created}</td>
                  <td className="py-1.5 pr-3 text-muted">{s.updated}</td>
                  <td className="py-1.5 text-xs text-bad">
                    {s.error ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-2 pt-2">
        <h3 className="text-sm font-semibold text-ink-2">
          Son içe aktarmalar
        </h3>
        {records.length === 0 ? (
          <p className="text-sm text-muted">Henüz kayıt yok.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-muted">
                <th className="py-1 pr-3">Sorgu</th>
                <th className="py-1 pr-3">Durum</th>
                <th className="py-1 pr-3">Son deneme</th>
                <th className="py-1 pr-3">Son başarı</th>
                <th className="py-1 pr-3">Yeni</th>
                <th className="py-1">Güncellenen</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.normalized_query} className="border-t border-line">
                  <td className="py-1.5 pr-3 text-ink-2">
                    {r.last_query ?? r.normalized_query}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">
                    {STATUS_LABEL[r.status] ?? r.status}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">
                    {formatDateTime(r.last_attempt_at)}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">
                    {formatDateTime(r.last_success_at)}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">{r.created}</td>
                  <td className="py-1.5 text-muted">{r.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// -- 0) Shelf coverage (warmup health) --------------------------------------------

const COVERAGE_STATUS_LABEL: Record<string, string> = {
  running: "çalışıyor",
  success: "başarılı",
  partial: "kısmi",
  failed: "başarısız",
  skipped: "atlandı",
};

function CoveragePanel() {
  const [coverage, setCoverage] = useState<ImportCoverage | null>(null);
  const [priceRefresh, setPriceRefresh] = useState<PriceRefreshStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warming, setWarming] = useState<"full" | "unpriced" | null>(null);
  const [warmupMsg, setWarmupMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextCoverage, nextRefresh] = await Promise.all([
        getImportCoverage(), getPriceRefreshStatus(),
      ]);
      setCoverage(nextCoverage);
      setPriceRefresh(nextRefresh);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kapsama durumu alınamadı");
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [refresh]);

  // While any import is running (e.g. a warmup in flight) poll so the shelf
  // fills up live; otherwise a single load is enough.
  const running = priceRefresh?.running ?? 0;
  const cycleActive = priceRefresh?.current_cycle_started_at != null;
  useEffect(() => {
    if (cycleActive) {
      timer.current = setInterval(() => void refresh(), COVERAGE_POLL_MS);
    }
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [cycleActive, refresh]);

  async function triggerWarmup(mode: "full" | "unpriced") {
    if (warming) return;
    setWarming(mode);
    setWarmupMsg(null);
    try {
      if (mode === "unpriced") {
        const status = await startMissingPriceRefresh();
        setWarmupMsg(
          status.current_cycle_total > 0
            ? `Fiyatsız ${status.current_cycle_total} seri için yenileme başlatıldı.`
            : "Fiyatsız seri yok.",
        );
      } else {
        await startPriceRefresh();
        setWarmupMsg("Katalog fiyat yenileme döngüsü başlatıldı.");
      }
      await refresh();
    } catch (e) {
      setWarmupMsg(e instanceof Error ? e.message : "Isıtma başlatılamadı");
    } finally {
      setWarming(null);
    }
  }

  const pct =
    coverage && coverage.catalog_series > 0
      ? Math.round((100 * coverage.series_with_listings) / coverage.catalog_series)
      : 0;

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">
          Raf kapsaması
          {cycleActive && (
            <span className="ml-2 text-sm font-normal text-accent">
              · {priceRefresh?.current_cycle_mode === "unpriced" ? "fiyatsızlar: " : ""}
              {running} iş çalışıyor…
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void triggerWarmup("unpriced")}
            disabled={warming !== null || !priceRefresh?.enabled || cycleActive}
            title="Sadece hiç fiyatı olmayan katalog serilerini mağazalarda yeniden arar"
            className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
          >
            {warming === "unpriced" ? "Başlatılıyor…" : "Fiyatsızları yenile"}
          </button>
          <button
            type="button"
            onClick={() => void triggerWarmup("full")}
            disabled={warming !== null || !priceRefresh?.enabled || cycleActive}
            className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
          >
            {warming === "full" ? "Başlatılıyor…" : "Fiyatları yenile"}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}
      {warmupMsg && <p className="text-xs text-muted">{warmupMsg}</p>}

      {priceRefresh && (
        <div className="space-y-1 text-xs text-muted">
          <p>
            Fiyat yenileme: {priceRefresh.enabled ? "açık" : "kapalı"} · her{" "}
            {priceRefresh.interval_hours} saatte bir · {priceRefresh.worker_concurrency} worker ·{" "}
            kuyruk {priceRefresh.queue_size}/{priceRefresh.queue_capacity}
          </p>
          <p>
            Döngü: {priceRefresh.completed} tamamlandı · {priceRefresh.failed} hata ·{" "}
            {priceRefresh.running} çalışıyor · {priceRefresh.queued} kuyrukta ·{" "}
            {priceRefresh.pending} bekliyor / {priceRefresh.current_cycle_total || priceRefresh.total_catalog_series} seri
          </p>
          <p>
            Başlangıç: {formatDateTime(priceRefresh.current_cycle_started_at)} ·{" "}
            son bitiş: {formatDateTime(priceRefresh.last_cycle_completed_at)} ·{" "}
            sonraki: {formatDateTime(priceRefresh.next_scheduled_refresh)}
          </p>
        </div>
      )}

      {coverage && (
        <>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Katalog serilerinde fiyat verisi olan oranı"
          >
            <div
              className="h-full rounded-full bg-ok transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted">Fiyatlı seri</dt>
              <dd className="text-ink-2">
                {coverage.series_with_listings}/{coverage.catalog_series}
                <span className="text-muted"> ({pct}%)</span>
              </dd>
            </div>
            <div>
              <dt className="text-muted">Toplam listing</dt>
              <dd className="text-ink-2">{coverage.listings_total}</dd>
            </div>
            <div>
              <dt className="text-muted">
                Taze kayıt ({coverage.freshness_ttl_minutes} dk)
              </dt>
              <dd className="text-ink-2">
                {coverage.fresh_records}/{coverage.records_total}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Kayıt durumu</dt>
              <dd className="text-xs text-muted">
                {Object.entries(coverage.records_by_status).length === 0
                  ? "—"
                  : Object.entries(coverage.records_by_status)
                      .map(([k, v]) => `${COVERAGE_STATUS_LABEL[k] ?? k}: ${v}`)
                      .join(" · ")}
              </dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

// -- 0b) Catalog series without any price (why?) -----------------------------------

const OUTCOME_LABEL: Record<MissingCoverage["outcome"], string> = {
  unmatched: "ürün bulundu, eşleşmedi",
  empty: "mağazalar sonuç döndürmedi",
  other_series: "başka seriyle eşleşti",
  variant_no_isbn: "özel baskı: ISBN'i henüz okunmadı (sonraki katalog senkronu)",
  variant_unsold: "özel baskı: mağazalarda bu ISBN yok",
  failed: "mağazalar hata verdi",
  never: "henüz denenmedi",
};

function formatReasons(reasons: MissingCoverage["reasons"]): string {
  if (!reasons) return "";
  return Object.entries(reasons)
    .map(
      ([store, counts]) =>
        `${store}: ${Object.entries(counts)
          .map(([reason, n]) => `${reason}×${n}`)
          .join(", ")}`,
    )
    .join(" · ");
}

function MissingCoveragePanel() {
  const [rows, setRows] = useState<MissingCoverage[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setRows(await getMissingCoverage());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fiyatsız seriler alınamadı");
    } finally {
      setLoading(false);
    }
  }

  const counts = rows?.reduce<Record<string, number>>((acc, r) => {
    acc[r.outcome] = (acc[r.outcome] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">
          Fiyatsız seriler
          {rows && (
            <span className="ml-2 text-sm font-normal text-muted">· {rows.length}</span>
          )}
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg border border-line-strong bg-surface-2 px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:bg-line disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Yükleniyor…" : rows ? "Yenile" : "Listele"}
        </button>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      {counts && (
        <p className="text-xs text-muted">
          {Object.entries(counts)
            .map(([k, v]) => `${OUTCOME_LABEL[k as MissingCoverage["outcome"]] ?? k}: ${v}`)
            .join(" · ")}
        </p>
      )}

      {rows && rows.length > 0 && (
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-muted">
                <th className="py-1 pr-3">Seri</th>
                <th className="py-1 pr-3">Sonuç</th>
                <th className="py-1 pr-3">Bulunan</th>
                <th className="py-1">Ret nedenleri</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.series_id} className="border-t border-line align-top">
                  <td className="py-1.5 pr-3 text-ink-2">
                    {r.title}
                    <span className="block text-xs text-muted">
                      {r.publisher ?? "—"} · {r.volume_count} cilt
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-muted">{OUTCOME_LABEL[r.outcome]}</td>
                  <td className="py-1.5 pr-3 text-muted">{r.results_found}</td>
                  <td className="py-1.5 text-xs text-muted">
                    {formatReasons(r.reasons)}
                    {r.error && <span className="block text-bad">{r.error}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows && rows.length === 0 && (
        <p className="text-sm text-muted">Tüm katalog serilerinde en az bir fiyat var.</p>
      )}
    </section>
  );
}

export function AdminControls() {
  return (
    <div className="space-y-6">
      <CoveragePanel />
      <MissingCoveragePanel />
      <CatalogSyncPanel />
      <ImportPanel />
    </div>
  );
}
