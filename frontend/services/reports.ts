import { getJson, patchJson, postJson } from "@/lib/api";

export type ReportStatus = "new" | "resolved" | "dismissed";

export type ContentReport = {
  id: number; created_at: string; status: ReportStatus; resolved_at: string | null;
  category: string; category_label: string; message: string; path: string;
  series: string | null; volume_number: number | null; store: string | null;
  user: { id: number; name: string; email: string } | null; reporter: string;
};

export type ReportList = { counts: Record<ReportStatus, number>; items: ContentReport[] };

export const REPORT_CATEGORIES = [
  { key: "price", label: "Fiyat yanlış" },
  { key: "stock", label: "Stok bilgisi yanlış" },
  { key: "match", label: "Yanlış ürün / mağaza eşleşmesi" },
  { key: "info", label: "Cilt bilgisi yanlış (künye, kapak, tarih)" },
  { key: "other", label: "Diğer" },
] as const;

export type ReportInput = {
  category: string; message: string; path: string; store?: string;
  /** Milliseconds the form was open; a bot sends at once. */
  filled_ms: number;
  /** Hidden from people; anything here marks a bot. */
  website: string;
};

export const sendReport = (input: ReportInput) => postJson<void>("/hata-bildir", input);
export const getReports = (status: ReportStatus | "all") =>
  getJson<ReportList>(`/admin/reports${status === "all" ? "?status=" : `?status=${status}`}`);
export const getOpenReportCount = () => getJson<{ new: number }>("/admin/reports/count");
export const setReportStatus = (id: number, status: ReportStatus) =>
  patchJson<{ id: number; status: ReportStatus }>(`/admin/reports/${id}`, { status });
