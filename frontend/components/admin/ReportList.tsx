"use client";

/**
 * Admin: visitors' "hatalı bilgi" reports. The reader's text is shown as
 * plain text (React escapes it, links are not clickable).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui";
import { formatDateTime } from "@/lib/time";
import { volumeLabel } from "@/lib/volumeLabel";
import { setReportStatus, type ContentReport, type ReportStatus } from "@/services/reports";

const STATUS_BADGE: Record<ReportStatus, { tone: "new" | "stock" | "neutral"; label: string }> = {
  new: { tone: "new", label: "Yeni" },
  resolved: { tone: "stock", label: "Çözüldü" },
  dismissed: { tone: "neutral", label: "Geçersiz" },
};

export function ReportList({ items }: { items: ContentReport[] }) {
  if (items.length === 0) {
    return <p className="rounded-xl border border-dashed border-line-strong bg-surface/70 p-8 text-center text-sm text-muted">
      Burada bildirim yok.
    </p>;
  }
  return <ul className="space-y-3">
    {items.map((r) => <ReportRow key={r.id} report={r} />)}
  </ul>;
}

function ReportRow({ report }: { report: ContentReport }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(status: ReportStatus) {
    setPending(true);
    setError(null);
    try {
      await setReportStatus(report.id, status);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Güncellenemedi");
    } finally {
      setPending(false);
    }
  }

  const badge = STATUS_BADGE[report.status];
  const title = report.series
    ? `${report.series}${report.volume_number !== null ? ` ${volumeLabel(report.volume_number)}` : ""}`
    : report.path;
  const button = "min-h-11 rounded-lg border px-3 text-sm font-semibold transition-colors disabled:opacity-50";
  return <li className="space-y-3 rounded-xl border border-line bg-surface p-4 shadow-card">
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge tone={badge.tone}>{badge.label}</Badge>
      <span className="font-semibold text-ink">{report.category_label}</span>
      {report.store && <Badge tone="neutral">{report.store}</Badge>}
      <span className="text-faint">· {formatDateTime(report.created_at)}</span>
    </div>
    <Link href={report.path} className="block font-semibold text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-accent">
      {title}
    </Link>
    <p className="text-[0.95rem] break-words whitespace-pre-wrap text-ink">{report.message}</p>
    <p className="text-xs text-faint">
      {report.user ? `Üye: ${report.user.name} (${report.user.email})` : "Ziyaretçi (giriş yapmamış)"}
      {" · "}gönderen kodu <span className="font-mono">{report.reporter.slice(0, 6)}</span>
      {report.resolved_at && ` · işaretlendi ${formatDateTime(report.resolved_at)}`}
    </p>
    <div className="flex flex-wrap items-center gap-2">
      {report.status !== "resolved" && (
        <button type="button" disabled={pending} onClick={() => void change("resolved")}
          className={`${button} border-ok/40 text-ok hover:bg-ok-soft`}>Çözüldü</button>
      )}
      {report.status !== "dismissed" && (
        <button type="button" disabled={pending} onClick={() => void change("dismissed")}
          className={`${button} border-line text-muted hover:text-ink`}>Geçersiz</button>
      )}
      {report.status !== "new" && (
        <button type="button" disabled={pending} onClick={() => void change("new")}
          className={`${button} border-line text-muted hover:text-ink`}>Yeniden aç</button>
      )}
      {error && <span className="text-xs text-bad">{error}</span>}
    </div>
  </li>;
}
