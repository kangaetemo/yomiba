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
  getImportCoverage,
  getImportRecords,
  getMissingCoverage,
  getPriceRefreshStatus,
  runImport,
  startCatalogSync,
  startMissingPriceRefresh,
  startPriceRefresh,
} from "@/services/admin";
import type {
  CatalogSyncStatus,
  ImportCoverage,
  ImportRecord,
  ImportReport,
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
